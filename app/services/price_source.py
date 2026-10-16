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

# Last-resort reference prices (snapshot from 16 Oct 2026) so the demo never shows an empty table.
STATIC_PRICES = {
    "BTC": 81650.0,
    "ETH": 2440.0,
    "SOL": 104.6,
    "XRP": 1.32,
    "BNB": 726.0,
    "ADA": 0.23,
    "DOGE": 0.081,
    "AVAX": 10.2,
    "LINK": 12.4,
    "DOT": 1.18,
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


class OKXPriceSource(PriceSource):
    """OKX public spot tickers (no API key; one call returns every pair)."""

    name = "OKX"

    def __init__(self, session: requests.Session | None = None):
        self._http = session or requests.Session()

    def fetch_prices(self, symbols: list[str]) -> dict[str, float]:
        try:
            resp = self._http.get(
                "https://www.okx.com/api/v5/market/tickers", params={"instType": "SPOT"}, timeout=TIMEOUT
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise PriceUnavailable(f"OKX: {exc}") from exc
        if str(data.get("code")) != "0":
            raise PriceUnavailable(f"OKX: {data.get('msg', 'error')}")
        wanted = {f"{s}-USDT": s for s in symbols}
        prices = {wanted[row["instId"]]: float(row["last"]) for row in data.get("data", []) if row.get("instId") in wanted}
        if not prices:
            raise PriceUnavailable("OKX returned no prices")
        return prices


KRAKEN_BASES = {"BTC": "XBT", "DOGE": "XDG"}


class KrakenPriceSource(PriceSource):
    name = "Kraken"

    def __init__(self, session: requests.Session | None = None):
        self._http = session or requests.Session()

    def fetch_prices(self, symbols: list[str]) -> dict[str, float]:
        pairs = {f"{KRAKEN_BASES.get(s, s)}USDT": s for s in symbols}
        try:
            resp = self._http.get(
                "https://api.kraken.com/0/public/Ticker", params={"pair": ",".join(pairs)}, timeout=TIMEOUT
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise PriceUnavailable(f"Kraken: {exc}") from exc
        if data.get("error"):
            raise PriceUnavailable(f"Kraken: {data['error']}")
        prices = {pairs[k]: float(v["c"][0]) for k, v in data.get("result", {}).items() if k in pairs}
        if not prices:
            raise PriceUnavailable("Kraken returned no prices")
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
            found: dict[str, float] = {}
            used: list[str] = []
            for source in self._sources:
                missing = [s for s in symbols if s not in found]
                if not missing:
                    break
                try:
                    prices = source.fetch_prices(missing)
                except PriceUnavailable as exc:
                    logger.warning("price source failed: %s", exc)
                    continue
                if prices:
                    found.update(prices)
                    used.append(source.name)
            if not found:
                raise PriceUnavailable("all price sources failed")
            self._cache.update(found)
            self._cache_time = time.monotonic()
            self._active_name = " + ".join(used)
            return {s: self._cache[s] for s in symbols if s in self._cache}
