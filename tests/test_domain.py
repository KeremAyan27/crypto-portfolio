from datetime import datetime, timedelta, timezone

import pytest

from app.domain.asset import Asset
from app.domain.future_asset import FutureAsset
from app.domain.portfolio import Portfolio
from app.domain.spot_asset import SpotAsset
from app.domain.trade_order import InvalidTransition, OrderDirection, OrderStatus, TradeOrder
from app.domain.user import User


def test_asset_is_abstract():
    with pytest.raises(TypeError):
        Asset("BTC", 1)  # type: ignore[abstract]


def test_spot_asset_value_and_pl():
    a = SpotAsset("btc", 0.5, average_buy_price=50000, current_price=60000)
    assert a.symbol == "BTC"
    assert a.calculate_value() == 30000
    assert a.calculate_profit_loss() == 5000


def test_spot_buy_updates_weighted_average():
    a = SpotAsset("ETH", 1, average_buy_price=2000)
    a.buy(1, 3000)
    assert a.quantity == 2
    assert a.average_buy_price == 2500


def test_spot_cannot_oversell():
    a = SpotAsset("SOL", 1, average_buy_price=100)
    with pytest.raises(ValueError):
        a.sell(2)


def test_future_asset_polymorphic_value():
    expiry = datetime.now(timezone.utc) + timedelta(days=30)
    f = FutureAsset("BTC", 1, entry_price=60000, leverage=10, contract_expiry=expiry, current_price=63000)
    assert f.margin_requirement == 6000
    assert f.calculate_profit_loss() == 3000
    assert f.calculate_value() == 9000
    assert not f.is_expired()


def test_future_value_floors_at_zero_on_liquidation():
    expiry = datetime.now(timezone.utc) + timedelta(days=1)
    f = FutureAsset("BTC", 1, entry_price=60000, leverage=10, contract_expiry=expiry, current_price=50000)
    assert f.calculate_value() == 0


def test_portfolio_total_uses_polymorphism():
    p = Portfolio(cash_balance=1000)
    p.add_asset(SpotAsset("BTC", 0.1, 50000, current_price=60000))
    expiry = datetime.now(timezone.utc) + timedelta(days=30)
    p.add_asset(FutureAsset("ETH", 1, 3000, 5, expiry, current_price=3300))
    assert p.calculate_total_value() == pytest.approx(1000 + 6000 + 600 + 300)


def test_portfolio_rejects_duplicate_symbol():
    p = Portfolio()
    p.add_asset(SpotAsset("BTC", 1, 1))
    with pytest.raises(ValueError):
        p.add_asset(SpotAsset("BTC", 1, 1))


def test_portfolio_buy_and_sell_cycle():
    p = Portfolio(cash_balance=1000)
    p.apply_buy("SOL", 2, 100)
    assert p.cash_balance == 800
    assert p.get_asset("SOL").quantity == 2
    p.apply_sell("SOL", 2, 150)
    assert p.cash_balance == 1100
    assert p.get_asset("SOL") is None


def test_user_owns_one_portfolio():
    u = User("kerem")
    assert u.get_portfolio() is u.get_portfolio()


def test_trade_order_happy_path():
    o = TradeOrder("BTC", 0.01, OrderDirection.BUY, 60000)
    assert o.status is OrderStatus.PENDING
    assert o.calculate_total_cost() == 600
    o.mark_validated()
    o.mark_executed(60100, "x1")
    assert o.status is OrderStatus.EXECUTED
    assert o.price == 60100


def test_trade_order_rejects_invalid_transition():
    o = TradeOrder("BTC", 0.01, OrderDirection.BUY, 60000)
    with pytest.raises(InvalidTransition):
        o.mark_executed(60000)
    o.mark_rejected("no money")
    with pytest.raises(InvalidTransition):
        o.mark_validated()
