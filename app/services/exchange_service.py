"""Exchange integration.

OOM principles: Abstraction (ExchangeService interface), Polymorphism
(PaperExchange and BinanceTestnetExchange are interchangeable for
TradeService).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from urllib.parse import urlencode

import requests

from app.domain.trade_order import TradeOrder
from app.services.price_source import PriceSource

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Fill:
    price: float
    exchange_order_id: str


class ExchangeError(Exception):
    pass


class ExchangeService(ABC):
    name: str = "abstract"

    @abstractmethod
    def fetch_prices(self, symbols: list[str]) -> dict[str, float]: ...

    def fetch_price(self, symbol: str) -> float:
        prices = self.fetch_prices([symbol])
        if symbol not in prices:
            raise ExchangeError(f"no price for {symbol}")
        return prices[symbol]

    @abstractmethod
    def submit_order(self, order: TradeOrder) -> Fill: ...


class PaperExchange(ExchangeService):
    """Simulated fills at the current market price. Safe for a public demo."""

    name = "Paper trading (simulated fills)"

    def __init__(self, price_source: PriceSource):
        self._prices = price_source

    @property
    def price_source_name(self) -> str:
        return self._prices.name

    def fetch_prices(self, symbols: list[str]) -> dict[str, float]:
        return self._prices.fetch_prices(symbols)

    def submit_order(self, order: TradeOrder) -> Fill:
        price = self.fetch_price(order.symbol)
        return Fill(price=price, exchange_order_id=f"paper-{uuid.uuid4().hex[:12]}")


class BinanceTestnetExchange(ExchangeService):
    """Market orders on Binance Spot Testnet (signed REST calls)."""

    name = "Binance Spot Testnet"
    BASE_URL = "https://testnet.binance.vision"

    def __init__(self, api_key: str, api_secret: str, price_source: PriceSource):
        if not api_key or not api_secret:
            raise ValueError("testnet API key and secret are required")
        self._key = api_key
        self._secret = api_secret.encode()
        self._prices = price_source
        self._http = requests.Session()
        self._http.headers["X-MBX-APIKEY"] = api_key

    @property
    def price_source_name(self) -> str:
        return self._prices.name

    def fetch_prices(self, symbols: list[str]) -> dict[str, float]:
        return self._prices.fetch_prices(symbols)

    def submit_order(self, order: TradeOrder) -> Fill:
        params = {
            "symbol": f"{order.symbol}USDT",
            "side": order.direction.value,
            "type": "MARKET",
            "quantity": f"{order.quantity:.6f}".rstrip("0").rstrip("."),
            "timestamp": int(time.time() * 1000),
            "recvWindow": 5000,
        }
        query = urlencode(params)
        signature = hmac.new(self._secret, query.encode(), hashlib.sha256).hexdigest()
        try:
            resp = self._http.post(f"{self.BASE_URL}/api/v3/order?{query}&signature={signature}", timeout=8)
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise ExchangeError(f"testnet request failed: {exc}") from exc
        if resp.status_code != 200:
            raise ExchangeError(data.get("msg", f"HTTP {resp.status_code}"))
        fills = data.get("fills") or []
        qty = sum(float(f["qty"]) for f in fills)
        price = sum(float(f["price"]) * float(f["qty"]) for f in fills) / qty if qty else order.price
        return Fill(price=price, exchange_order_id=str(data.get("orderId")))
