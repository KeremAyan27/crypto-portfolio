"""BalanceValidator: checks an order against the portfolio before execution.

OOM principles: single responsibility, Encapsulation of business rules.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.portfolio import Portfolio
from app.domain.trade_order import OrderDirection, TradeOrder

MIN_ORDER_USDT = 10.0


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    reason: str = ""


class BalanceValidator:
    def __init__(self, min_order_usdt: float = MIN_ORDER_USDT) -> None:
        self._min_order = min_order_usdt

    def validate(self, portfolio: Portfolio, order: TradeOrder) -> ValidationResult:
        total = order.calculate_total_cost()
        if total < self._min_order:
            return ValidationResult(False, f"order value {total:.2f} USDT is below the {self._min_order:.0f} USDT minimum")
        if order.direction is OrderDirection.BUY:
            if total > portfolio.cash_balance + 1e-9:
                return ValidationResult(
                    False,
                    f"insufficient balance: needs {total:,.2f} USDT, available {portfolio.cash_balance:,.2f} USDT",
                )
            return ValidationResult(True)
        asset = portfolio.get_asset(order.symbol)
        held = asset.quantity if asset else 0.0
        if order.quantity > held + 1e-12:
            return ValidationResult(False, f"insufficient {order.symbol}: needs {order.quantity:g}, held {held:g}")
        return ValidationResult(True)
