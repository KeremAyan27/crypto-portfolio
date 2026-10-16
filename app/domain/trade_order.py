"""TradeOrder and its lifecycle.

OOM principles: Encapsulation (status only changes through transition
methods), state machine matching the D2 TradeOrder statechart:
PENDING -> VALIDATED -> EXECUTED, with REJECTED and FAILED as end states.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum


class OrderDirection(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    VALIDATED = "VALIDATED"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


_ALLOWED = {
    OrderStatus.PENDING: {OrderStatus.VALIDATED, OrderStatus.REJECTED},
    OrderStatus.VALIDATED: {OrderStatus.EXECUTED, OrderStatus.FAILED},
}


class InvalidTransition(Exception):
    pass


class TradeOrder:
    def __init__(
        self,
        symbol: str,
        quantity: float,
        direction: OrderDirection,
        price: float,
        news_event_id: str | None = None,
    ) -> None:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if price <= 0:
            raise ValueError("price must be positive")
        self._order_id = str(uuid.uuid4())
        self._symbol = symbol.upper()
        self._quantity = float(quantity)
        self._direction = OrderDirection(direction)
        self._price = float(price)
        self._news_event_id = news_event_id
        self._status = OrderStatus.PENDING
        self._message = ""
        self._created_at = datetime.now(timezone.utc)
        self._exchange_order_id: str | None = None

    @property
    def order_id(self) -> str:
        return self._order_id

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def quantity(self) -> float:
        return self._quantity

    @property
    def direction(self) -> OrderDirection:
        return self._direction

    @property
    def price(self) -> float:
        return self._price

    @property
    def status(self) -> OrderStatus:
        return self._status

    @property
    def message(self) -> str:
        return self._message

    def calculate_total_cost(self) -> float:
        return self._quantity * self._price

    def mark_validated(self) -> None:
        self._transition(OrderStatus.VALIDATED, "balance check passed")

    def mark_rejected(self, reason: str) -> None:
        self._transition(OrderStatus.REJECTED, reason)

    def mark_executed(self, fill_price: float, exchange_order_id: str | None = None) -> None:
        self._price = float(fill_price)
        self._exchange_order_id = exchange_order_id
        self._transition(OrderStatus.EXECUTED, "order filled")

    def mark_failed(self, reason: str) -> None:
        self._transition(OrderStatus.FAILED, reason)

    def _transition(self, target: OrderStatus, message: str) -> None:
        if target not in _ALLOWED.get(self._status, set()):
            raise InvalidTransition(f"{self._status.value} -> {target.value} not allowed")
        self._status = target
        self._message = message

    def to_dict(self) -> dict:
        return {
            "order_id": self._order_id,
            "symbol": self._symbol,
            "quantity": self._quantity,
            "direction": self._direction.value,
            "price": self._price,
            "total": self.calculate_total_cost(),
            "status": self._status.value,
            "message": self._message,
            "news_event_id": self._news_event_id,
            "exchange_order_id": self._exchange_order_id,
            "created_at": self._created_at.isoformat(),
        }
