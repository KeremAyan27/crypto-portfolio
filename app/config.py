"""Runtime settings read from environment variables (.env supported)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    trade_mode: str = field(default_factory=lambda: os.getenv("TRADE_MODE", "paper").lower())
    binance_api_key: str = field(default_factory=lambda: os.getenv("BINANCE_TESTNET_API_KEY", ""))
    binance_api_secret: str = field(default_factory=lambda: os.getenv("BINANCE_TESTNET_API_SECRET", ""))
    news_rss_url: str = field(default_factory=lambda: os.getenv("NEWS_RSS_URL", "https://cointelegraph.com/rss"))
    news_freshness_minutes: int = field(default_factory=lambda: _int("NEWS_FRESHNESS_MINUTES", 1440))
    news_cache_seconds: int = field(default_factory=lambda: _int("NEWS_CACHE_SECONDS", 120))
    price_cache_seconds: int = field(default_factory=lambda: _int("PRICE_CACHE_SECONDS", 15))
    session_ttl_minutes: int = field(default_factory=lambda: _int("SESSION_TTL_MINUTES", 120))
    max_sessions: int = field(default_factory=lambda: _int("MAX_SESSIONS", 1000))
    max_trades_per_session: int = field(default_factory=lambda: _int("MAX_TRADES_PER_SESSION", 50))
    tracked_symbols: tuple[str, ...] = ("BTC", "ETH", "SOL", "XRP", "BNB", "ADA", "DOGE", "AVAX", "LINK", "DOT")


def get_settings() -> Settings:
    return Settings()
