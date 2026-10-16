"""Per-visitor demo sessions, kept in memory.

Every visitor gets their own User + Portfolio so people trying the public demo
do not affect each other. Sessions expire after a period of inactivity.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import timedelta

from app.domain.portfolio import Portfolio
from app.domain.spot_asset import SpotAsset
from app.domain.trade_order import TradeOrder
from app.domain.user import User
from app.services.news_source import NewsSource
from app.services.quick_trade import QuickTradeObserver

STARTING_CASH = 10_000.0
STARTING_HOLDINGS = [("BTC", 0.05, 70_000.0), ("ETH", 1.0, 2_500.0), ("SOL", 10.0, 180.0)]


def build_demo_portfolio() -> Portfolio:
    portfolio = Portfolio(cash_balance=STARTING_CASH)
    for symbol, qty, avg in STARTING_HOLDINGS:
        portfolio.add_asset(SpotAsset(symbol, qty, average_buy_price=avg, current_price=avg))
    return portfolio


@dataclass
class Session:
    session_id: str
    user: User
    observer: QuickTradeObserver
    history: list[TradeOrder] = field(default_factory=list)
    last_seen: float = field(default_factory=time.monotonic)


class SessionStore:
    def __init__(self, news_source: NewsSource, freshness: timedelta, ttl_minutes: int = 120, max_sessions: int = 1000):
        self._news = news_source
        self._freshness = freshness
        self._ttl = ttl_minutes * 60
        self._max = max_sessions
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def create(self) -> Session:
        user = User("Demo Investor", build_demo_portfolio())
        observer = QuickTradeObserver(user.get_portfolio(), self._freshness)
        session = Session(session_id=secrets.token_urlsafe(16), user=user, observer=observer)
        with self._lock:
            self._evict_locked()
            self._sessions[session.session_id] = session
        self._news.register_observer(observer)
        self._news.replay_to(observer)
        return session

    def get(self, session_id: str | None) -> Session | None:
        if not session_id:
            return None
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if time.monotonic() - session.last_seen > self._ttl:
                self._drop_locked(session_id)
                return None
            session.last_seen = time.monotonic()
            return session

    def reset(self, session_id: str) -> Session | None:
        with self._lock:
            if session_id not in self._sessions:
                return None
            self._drop_locked(session_id)
        return self.create()

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def _evict_locked(self) -> None:
        now = time.monotonic()
        for sid in [sid for sid, s in self._sessions.items() if now - s.last_seen > self._ttl]:
            self._drop_locked(sid)
        while len(self._sessions) >= self._max:
            oldest = min(self._sessions.values(), key=lambda s: s.last_seen)
            self._drop_locked(oldest.session_id)

    def _drop_locked(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session:
            self._news.unregister_observer(session.observer)
