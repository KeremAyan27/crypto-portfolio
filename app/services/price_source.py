"""Market price sources.

OOM principles: Abstraction (PriceSource interface), Polymorphism (each source
is used through the same fetch_prices call), Open/Closed (FallbackPriceSource
chains sources without changing them).
"""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod

import requests

logger = logging.getLogger(__name__)

TIMEOUT = 5

COINGECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "XRP": "ripple",
    "BNB": "binancecoin",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "AVAX": "avalanche-2",
    "LINK": "chainlink",
    "DOT": "polkadot",
}

# Last-resort reference prices so the demo never shows an empty table.
STATIC_PRICES = {
    "BTC": 65000.0,
    "ETH": 3000.0,
    "SOL": 150.0,
    "XRP": 0.6,
    "BNB": 580.0,
    "ADA": 0.45,
    "DOGE": 0.12,
    "AVAX": 28.0,
    "LINK": 14.0,
    "DOT": 6.0,
}


class PriceUnavailable(Exception):
    pass


class PriceSource(ABC):
    name: str = "abstract"

    @abstractmethod
    def fetch_prices(self, symbols: list[str]) -> dict[str, float]:
        """Return USDT prices for the requested symbols. Raise PriceUnavailable on failure."""


class BinancePublicPriceSource(PriceSource):
    """Binance public market-data endpoint (no API key needed)."""

    name = "Binance"

    def __init__(self, base_url: str = "https://data-api.binance.vision", session: requests.Session | None = None):
        self._base_url = base_url.rstrip("/")
        self._http = session or requests.Session()

    def fetch_prices(self, symbols: list[str]) -> dict[str, float]:
        pairs = [f"{s}USDT" for s in symbols]
        params = {"symbols": "[" + ",".join(f'"{p}"' for p in pairs) + "]"}
        try:
            resp = self._http.get(f"{self._base_url}/api/v3/ticker/price", params=params, timeout=TIMEOUT)
            resp.raise_for_status()
            rows = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise PriceUnavailable(f"Binance: {exc}") from exc
        prices = {row["symbol"].removesuffix("USDT"): float(row["price"]) for row in rows}
        if not prices:
            raise PriceUnavailable("Binance returned no prices")
        return prices


class CoinGeckoPriceSource(PriceSource):
    name = "CoinGecko"

    def __init__(self, session: requests.Session | None = None):
        self._http = session or requests.Session()

    def fetch_prices(self, symbols: list[str]) -> dict[str, float]:
        ids = {COINGECKO_IDS[s]: s for s in symbols if s in COINGECKO_IDS}
        try:
            resp = self._http.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": ",".join(ids), "vs_currencies": "usd"},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise PriceUnavailable(f"CoinGecko: {exc}") from exc
        prices = {ids[cg_id]: float(v["usd"]) for cg_id, v in data.items() if "usd" in v}
        if not prices:
            raise PriceUnavailable("CoinGecko returned no prices")
        return prices


class StaticPriceSource(PriceSource):
    name = "Static reference prices"

    def __init__(self, prices: dict[str, float] | None = None):
        self._prices = dict(prices or STATIC_PRICES)

    def fetch_prices(self, symbols: list[str]) -> dict[str, float]:
        return {s: self._prices[s] for s in symbols if s in self._prices}


class FallbackPriceSource(PriceSource):
    """Tries each source in order and caches the result for a few seconds."""

    def __init__(self, sources: list[PriceSource], cache_seconds: int = 15):
        if not sources:
            raise ValueError("at least one source required")
        self._sources = sources
        self._cache_seconds = cache_seconds
        self._cache: dict[str, float] = {}
        self._cache_time = 0.0
        self._active_name = "not fetched yet"
        self._lock = threading.Lock()

    @property
    def name(self) -> str:  # type: ignore[override]
        return self._active_name

    def fetch_prices(self, symbols: list[str]) -> dict[str, float]:
        with self._lock:
            fresh = time.monotonic() - self._cache_time < self._cache_seconds
            if fresh and all(s in self._cache for s in symbols):
                return {s: self._cache[s] for s in symbols}
            for source in self._sources:
                try:
                    prices = source.fetch_prices(symbols)
                except PriceUnavailable as exc:
                    logger.warning("price source failed: %s", exc)
                    continue
                if prices:
                    self._cache.update(prices)
                    self._cache_time = time.monotonic()
                    self._active_name = source.name
                    return {s: self._cache[s] for s in symbols if s in self._cache}
            raise PriceUnavailable("all price sources failed")
