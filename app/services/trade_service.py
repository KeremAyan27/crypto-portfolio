"""TradeService: orchestrates the Quick Trade flow from the D2 sequence diagram.

create order -> validate balance -> submit to exchange -> update portfolio.
"""

from __future__ import annotations

import logging

from app.domain.trade_order import OrderDirection, TradeOrder
from app.services.balance_validator import BalanceValidator
from app.services.exchange_service import ExchangeError, ExchangeService
from app.services.price_source import PriceUnavailable
from app.services.session_store import Session

logger = logging.getLogger(__name__)


class TradeLimitReached(Exception):
    pass


class TradeService:
    def __init__(self, exchange: ExchangeService, validator: BalanceValidator, max_trades_per_session: int = 50):
        self._exchange = exchange
        self._validator = validator
        self._max_trades = max_trades_per_session

    def place_order(
        self,
        session: Session,
        symbol: str,
        direction: OrderDirection,
        quantity: float,
        news_event_id: str | None = None,
    ) -> TradeOrder:
        if len(session.history) >= self._max_trades:
            raise TradeLimitReached(f"demo limit of {self._max_trades} trades per session reached; reset the portfolio")
        symbol = symbol.upper()
        price = self._exchange.fetch_price(symbol)
        order = TradeOrder(symbol, quantity, direction, price, news_event_id=news_event_id)
        portfolio = session.user.get_portfolio()

        result = self._validator.validate(portfolio, order)
        if not result.ok:
            order.mark_rejected(result.reason)
            session.history.append(order)
            return order
        order.mark_validated()

        try:
            fill = self._exchange.submit_order(order)
        except (ExchangeError, PriceUnavailable) as exc:
            logger.warning("order failed: %s", exc)
            order.mark_failed(str(exc))
            session.history.append(order)
            return order

        if direction is OrderDirection.BUY:
            # Re-check with the fill price; market may have moved since validation.
            if fill.price * quantity > portfolio.cash_balance + 1e-9:
                order.mark_failed("price moved, balance no longer sufficient")
                session.history.append(order)
                return order
            portfolio.apply_buy(symbol, quantity, fill.price)
        else:
            portfolio.apply_sell(symbol, quantity, fill.price)
        order.mark_executed(fill.price, fill.exchange_order_id)
        session.history.append(order)
        return order
