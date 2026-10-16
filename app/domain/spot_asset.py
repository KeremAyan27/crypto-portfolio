"""SpotAsset: a coin the investor actually owns.

OOM principles: Inheritance (extends Asset), Polymorphism (overrides
calculate_value and calculate_profit_loss).
"""

from __future__ import annotations

from app.domain.asset import Asset


class SpotAsset(Asset):
    def __init__(
        self,
        symbol: str,
        quantity: float,
        average_buy_price: float,
        current_price: float = 0.0,
        wallet_address: str | None = None,
    ) -> None:
        super().__init__(symbol, quantity, current_price)
        self._average_buy_price = float(average_buy_price)
        self._wallet_address = wallet_address

    @property
    def asset_type(self) -> str:
        return "spot"

    @property
    def average_buy_price(self) -> float:
        return self._average_buy_price

    def calculate_value(self) -> float:
        return self._quantity * self._current_price

    def calculate_profit_loss(self) -> float:
        return (self._current_price - self._average_buy_price) * self._quantity

    def buy(self, quantity: float, price: float) -> None:
        """Increase the position and recompute the weighted average cost."""
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        total_cost = self._average_buy_price * self._quantity + price * quantity
        self._quantity += quantity
        self._average_buy_price = total_cost / self._quantity

    def sell(self, quantity: float) -> None:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if quantity > self._quantity + 1e-12:
            raise ValueError("cannot sell more than held")
        self._quantity = max(self._quantity - quantity, 0.0)

    def to_dict(self) -> dict:
        data = super().to_dict()
        data["average_buy_price"] = self._average_buy_price
        return data
