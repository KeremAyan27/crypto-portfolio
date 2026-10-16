"""NewsEvent: a parsed news headline with the crypto symbols it mentions.

OOM principles: Encapsulation, single responsibility (symbol extraction and
relevance check live with the data they use).
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.portfolio import Portfolio

# Name or ticker -> trading symbol. Tickers are matched as whole words only.
SYMBOL_ALIASES: dict[str, str] = {
    "bitcoin": "BTC",
    "btc": "BTC",
    "ethereum": "ETH",
    "ether": "ETH",
    "eth": "ETH",
    "solana": "SOL",
    "sol": "SOL",
    "xrp": "XRP",
    "ripple": "XRP",
    "bnb": "BNB",
    "cardano": "ADA",
    "ada": "ADA",
    "dogecoin": "DOGE",
    "doge": "DOGE",
    "avalanche": "AVAX",
    "avax": "AVAX",
    "chainlink": "LINK",
    "polkadot": "DOT",
}

_WORD_RE = re.compile(r"[a-z]+")

POSITIVE = {"surge", "surges", "rally", "rallies", "climbs", "jumps", "soars", "record", "high", "gains",
            "approves", "approval", "inflows", "upgrade", "bullish", "adoption", "rises", "rebound"}
NEGATIVE = {"drop", "drops", "falls", "slips", "plunge", "plunges", "crash", "hack", "hacked", "exploit",
            "lawsuit", "sues", "ban", "outflows", "bearish", "selloff", "sell-off", "delays", "low", "sinks"}


def classify_sentiment(title: str) -> str:
    words = set(_WORD_RE.findall(title.lower()))
    score = len(words & POSITIVE) - len(words & NEGATIVE)
    if score > 0:
        return "positive"
    if score < 0:
        return "negative"
    return "neutral"


class NewsEvent:
    def __init__(
        self,
        title: str,
        publish_time: datetime,
        url: str | None = None,
        source: str = "unknown",
        summary: str = "",
        sentiment: str | None = None,
    ) -> None:
        if publish_time.tzinfo is None:
            publish_time = publish_time.replace(tzinfo=timezone.utc)
        self._event_id = str(uuid.uuid4())
        self._title = title.strip()
        self._summary = summary.strip()
        self._publish_time = publish_time
        self._url = url
        self._source = source
        self._sentiment = sentiment or classify_sentiment(self._title)
        self._symbols = self.extract_symbols()

    @property
    def event_id(self) -> str:
        return self._event_id

    @property
    def title(self) -> str:
        return self._title

    @property
    def publish_time(self) -> datetime:
        return self._publish_time

    @property
    def sentiment(self) -> str:
        return self._sentiment

    @property
    def symbols(self) -> list[str]:
        return list(self._symbols)

    def extract_symbols(self) -> list[str]:
        """Return symbols mentioned in the title (and summary), in first-seen order."""
        text = f"{self._title} {self._summary}".lower()
        found: list[str] = []
        for word in _WORD_RE.findall(text):
            symbol = SYMBOL_ALIASES.get(word)
            if symbol and symbol not in found:
                found.append(symbol)
        return found

    def is_relevant_to(self, portfolio: "Portfolio") -> bool:
        return bool(set(self._symbols) & portfolio.symbols())

    def age(self, now: datetime | None = None) -> timedelta:
        now = now or datetime.now(timezone.utc)
        return now - self._publish_time

    def is_expired(self, freshness: timedelta, now: datetime | None = None) -> bool:
        return self.age(now) > freshness

    def to_dict(self, now: datetime | None = None) -> dict:
        return {
            "event_id": self._event_id,
            "title": self._title,
            "url": self._url,
            "source": self._source,
            "publish_time": self._publish_time.isoformat(),
            "age_minutes": round(self.age(now).total_seconds() / 60, 1),
            "symbols": self._symbols,
            "sentiment": self._sentiment,
        }
