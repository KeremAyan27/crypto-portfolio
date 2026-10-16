"""Portfolio: the investor's holdings and cash balance.

OOM principles: Aggregation (holds Asset objects), Encapsulation (assets and
cash only change through methods), Polymorphism (calls calculate_value on any
Asset subclass without knowing its type).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.domain.asset import Asset
from app.domain.spot_asset import SpotAsset


class Portfolio:
    QUOTE_CURRENCY = "USDT"

    def __init__(self, cash_balance: float = 0.0) -> None:
        self._portfolio_id = str(uuid.uuid4())
        self._assets: list[Asset] = []
        self._cash_balance = float(cash_balance)
        self._last_updated = datetime.now(timezone.utc)

    @property
    def portfolio_id(self) -> str:
        return self._portfolio_id

    @property
    def assets(self) -> tuple[Asset, ...]:
        return tuple(self._assets)

    @property
    def cash_balance(self) -> float:
        return self._cash_balance

    @property
    def last_updated(self) -> datetime:
        return self._last_updated

    def symbols(self) -> set[str]:
        return {a.symbol for a in self._assets if a.quantity > 0}

    def get_asset(self, symbol: str) -> Asset | None:
        symbol = symbol.upper()
        return next((a for a in self._assets if a.symbol == symbol), None)

    def add_asset(self, asset: Asset) -> None:
        if self.get_asset(asset.symbol) is not None:
            raise ValueError(f"{asset.symbol} already in portfolio")
        self._assets.append(asset)
        self._touch()

    def remove_asset(self, symbol: str) -> None:
        asset = self.get_asset(symbol)
        if asset is None:
            raise KeyError(symbol)
        self._assets.remove(asset)
        self._touch()

    def update_prices(self, prices: dict[str, float]) -> None:
        for asset in self._assets:
            if asset.symbol in prices:
                asset.update_price(prices[asset.symbol])
        self._touch()

    def calculate_holdings_value(self) -> float:
        return sum(a.calculate_value() for a in self._assets)

    def calculate_total_value(self) -> float:
        return self._cash_balance + self.calculate_holdings_value()

    def calculate_total_profit_loss(self) -> float:
        return sum(a.calculate_profit_loss() for a in self._assets)

    def apply_buy(self, symbol: str, quantity: float, price: float) -> None:
        cost = quantity * price
        if cost > self._cash_balance + 1e-9:
            raise ValueError("insufficient cash balance")
        asset = self.get_asset(symbol)
        if asset is None:
            asset = SpotAsset(symbol, 0.0, average_buy_price=price, current_price=price)
            self._assets.append(asset)
        if not isinstance(asset, SpotAsset):
            raise TypeError("quick trades only support spot assets")
        asset.buy(quantity, price)
        asset.update_price(price)
        self._cash_balance -= cost
        self._touch()

    def apply_sell(self, symbol: str, quantity: float, price: float) -> None:
        asset = self.get_asset(symbol)
        if not isinstance(asset, SpotAsset):
            raise ValueError(f"no spot position in {symbol}")
        asset.sell(quantity)
        asset.update_price(price)
        self._cash_balance += quantity * price
        if asset.quantity <= 1e-12:
            self._assets.remove(asset)
        self._touch()

    def _touch(self) -> None:
        self._last_updated = datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        return {
            "portfolio_id": self._portfolio_id,
            "quote_currency": self.QUOTE_CURRENCY,
            "cash_balance": self._cash_balance,
            "holdings_value": self.calculate_holdings_value(),
            "total_value": self.calculate_total_value(),
            "total_profit_loss": self.calculate_total_profit_loss(),
            "last_updated": self._last_updated.isoformat(),
            "assets": [a.to_dict() for a in self._assets],
        }
