"""News sources.

OOM principles: Observer pattern (NewsSource is the Subject), Abstraction
(fetch_news is abstract), Polymorphism and Open/Closed (RSS, Mock and the
fallback chain share one interface).
"""

from __future__ import annotations

import logging
import threading
import time
from abc import abstractmethod
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from app.domain.news_event import NewsEvent
from app.domain.observer import Observer, Subject

logger = logging.getLogger(__name__)


class NewsSource(Subject):
    name: str = "abstract"

    def __init__(self) -> None:
        super().__init__()
        self._seen: dict[str, NewsEvent] = {}
        self._lock = threading.RLock()

    @abstractmethod
    def fetch_news(self) -> list[NewsEvent]:
        """Fetch the latest events. Return [] on failure, never raise."""

    def poll(self) -> list[NewsEvent]:
        """Fetch, notify observers about events not seen before, return all known events."""
        with self._lock:
            for event in self.fetch_news():
                key = event.title.lower()
                if key not in self._seen:
                    self._seen[key] = event
                    self.notify_observers(event)
            return self.events()

    def events(self) -> list[NewsEvent]:
        with self._lock:
            return sorted(self._seen.values(), key=lambda e: e.publish_time, reverse=True)

    def replay_to(self, observer: Observer) -> None:
        """Send already-known events to a newly registered observer."""
        for event in self.events():
            observer.update(event)


class RSSNewsSource(NewsSource):
    name = "CoinTelegraph RSS"

    def __init__(self, url: str = "https://cointelegraph.com/rss", limit: int = 30):
        super().__init__()
        self._url = url
        self._limit = limit
        self._http = requests.Session()
        self._http.headers["User-Agent"] = "Mozilla/5.0 (crypto-portfolio demo)"

    def fetch_news(self) -> list[NewsEvent]:
        try:
            resp = self._http.get(self._url, timeout=6)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("RSS fetch failed: %s", exc)
            return []
        feed = feedparser.parse(resp.content)
        events = []
        for entry in feed.entries[: self._limit]:
            parsed = entry.get("published_parsed") or entry.get("updated_parsed")
            published = (
                datetime(*parsed[:6], tzinfo=timezone.utc) if parsed else datetime.now(timezone.utc)
            )
            title = entry.get("title", "").strip()
            if not title:
                continue
            events.append(
                NewsEvent(title=title, publish_time=published, url=entry.get("link"), source=self.name)
            )
        return events


MOCK_HEADLINES = [
    ("Bitcoin climbs as spot ETF inflows hit a weekly high", 4),
    ("Ethereum developers confirm date for next network upgrade", 11),
    ("Solana network sees record daily transactions", 23),
    ("XRP slips after court filing delays settlement talks", 37),
    ("Regulators publish draft rules for stablecoin issuers", 52),
    ("Bitcoin miners sell part of reserves as fees drop", 75),
    ("Cardano foundation announces new developer grants", 96),
]


class MockNewsSource(NewsSource):
    """Deterministic headlines, timestamped relative to the first fetch."""

    name = "Mock headlines"

    def __init__(self, headlines: list[tuple[str, int]] | None = None):
        super().__init__()
        self._headlines = headlines or MOCK_HEADLINES
        self._anchor = datetime.now(timezone.utc)

    def fetch_news(self) -> list[NewsEvent]:
        return [
            NewsEvent(title=title, publish_time=self._anchor - timedelta(minutes=minutes), source=self.name)
            for title, minutes in self._headlines
        ]


class FallbackNewsSource(NewsSource):
    """Uses the primary source; falls back to the secondary when the primary returns nothing.

    Results are cached so the upstream feed is not hit on every page refresh.
    """

    def __init__(self, primary: NewsSource, fallback: NewsSource, cache_seconds: int = 120):
        super().__init__()
        self._primary = primary
        self._fallback = fallback
        self._cache_seconds = cache_seconds
        self._last_fetch = 0.0
        self._active_name = "not fetched yet"

    @property
    def name(self) -> str:  # type: ignore[override]
        return self._active_name

    def fetch_news(self) -> list[NewsEvent]:
        if time.monotonic() - self._last_fetch < self._cache_seconds and self._seen:
            return []
        self._last_fetch = time.monotonic()
        events = self._primary.fetch_news()
        if events:
            self._active_name = self._primary.name
            return events
        if self._active_name == self._primary.name and self._seen:
            # Keep showing earlier real headlines during a short outage.
            return []
        self._active_name = self._fallback.name
        return self._fallback.fetch_news()
