"""QuickTradeObserver: turns relevant, fresh news into trade suggestions.

OOM principles: Observer pattern (concrete Observer of NewsSource),
Encapsulation (suggestions are read-only from outside).
"""

from __future__ import annotations

from datetime import timedelta

from app.domain.news_event import NewsEvent
from app.domain.observer import Observer
from app.domain.portfolio import Portfolio


class QuickTradeObserver(Observer):
    def __init__(self, portfolio: Portfolio, freshness: timedelta) -> None:
        self._portfolio = portfolio
        self._freshness = freshness
        self._triggered: dict[str, NewsEvent] = {}

    def update(self, event: NewsEvent) -> None:
        # Matches the D2 activity diagram: irrelevant or expired news is discarded.
        if event.is_relevant_to(self._portfolio) and not event.is_expired(self._freshness):
            self._triggered[event.event_id] = event

    def suggestions(self) -> list[dict]:
        out = []
        held = self._portfolio.symbols()
        for event in sorted(self._triggered.values(), key=lambda e: e.publish_time, reverse=True):
            if event.is_expired(self._freshness):
                continue
            sentiment = event.sentiment
            for symbol in event.symbols:
                if symbol not in held:
                    continue
                out.append(
                    {
                        "event": event.to_dict(),
                        "symbol": symbol,
                        "sentiment": sentiment,
                        "suggested_direction": "SELL" if sentiment == "negative" else "BUY",
                    }
                )
        return out

    def get_event(self, event_id: str) -> NewsEvent | None:
        return self._triggered.get(event_id)
