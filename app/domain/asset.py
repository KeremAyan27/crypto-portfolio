"""Abstract Asset base class.

OOM principles: Abstraction (abstract methods), Encapsulation (private
attributes exposed through read-only properties).
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod


class Asset(ABC):
    """A holding of a single crypto symbol inside a Portfolio."""

    def __init__(self, symbol: str, quantity: float, current_price: float = 0.0) -> None:
        if quantity < 0:
            raise ValueError("quantity cannot be negative")
        self._asset_id = str(uuid.uuid4())
        self._symbol = symbol.upper()
        self._quantity = float(quantity)
        self._current_price = float(current_price)

    @property
    def asset_id(self) -> str:
        return self._asset_id

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def quantity(self) -> float:
        return self._quantity

    @property
    def current_price(self) -> float:
        return self._current_price

    def update_price(self, price: float) -> None:
        if price < 0:
            raise ValueError("price cannot be negative")
        self._current_price = float(price)

    @property
    @abstractmethod
    def asset_type(self) -> str:
        """Short label used by the API and UI."""

    @abstractmethod
    def calculate_value(self) -> float:
        """Current market value of the holding in USDT."""

    @abstractmethod
    def calculate_profit_loss(self) -> float:
        """Unrealised profit or loss in USDT."""

    def to_dict(self) -> dict:
        return {
            "asset_id": self._asset_id,
            "symbol": self._symbol,
            "asset_type": self.asset_type,
            "quantity": self._quantity,
            "current_price": self._current_price,
            "value": self.calculate_value(),
            "profit_loss": self.calculate_profit_loss(),
        }
