"""FutureAsset: a leveraged futures contract position.

OOM principles: Inheritance (extends Asset), Polymorphism (leverage-aware
value and P&L calculations).
"""

from __future__ import annotations

from datetime import datetime

from app.domain.asset import Asset


class FutureAsset(Asset):
    def __init__(
        self,
        symbol: str,
        quantity: float,
        entry_price: float,
        leverage: float,
        contract_expiry: datetime,
        current_price: float = 0.0,
    ) -> None:
        super().__init__(symbol, quantity, current_price)
        if leverage <= 0:
            raise ValueError("leverage must be positive")
        self._entry_price = float(entry_price)
        self._leverage = float(leverage)
        self._contract_expiry = contract_expiry

    @property
    def asset_type(self) -> str:
        return "future"

    @property
    def leverage(self) -> float:
        return self._leverage

    @property
    def margin_requirement(self) -> float:
        """Collateral locked for the position at entry."""
        return self._entry_price * self._quantity / self._leverage

    def calculate_profit_loss(self) -> float:
        return (self._current_price - self._entry_price) * self._quantity

    def calculate_value(self) -> float:
        """Equity of the position: margin plus unrealised P&L, floored at zero."""
        return max(self.margin_requirement + self.calculate_profit_loss(), 0.0)

    def is_expired(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(self._contract_expiry.tzinfo)
        return now >= self._contract_expiry

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update(
            {
                "entry_price": self._entry_price,
                "leverage": self._leverage,
                "margin_requirement": self.margin_requirement,
                "contract_expiry": self._contract_expiry.isoformat(),
            }
        )
        return data
