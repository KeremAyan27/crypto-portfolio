from datetime import timedelta

from app.domain.news_event import NewsEvent, classify_sentiment
from app.domain.observer import Observer
from app.domain.portfolio import Portfolio
from app.domain.spot_asset import SpotAsset
from app.domain.trade_order import OrderDirection, OrderStatus, TradeOrder
from app.services.balance_validator import BalanceValidator
from app.services.exchange_service import ExchangeError, Fill, PaperExchange
from app.services.news_source import FallbackNewsSource, MockNewsSource
from app.services.price_source import FallbackPriceSource, PriceSource, PriceUnavailable, StaticPriceSource
from app.services.quick_trade import QuickTradeObserver
from app.services.session_store import SessionStore
from app.services.trade_service import TradeLimitReached, TradeService
from tests.conftest import PRICES, StubNewsSource, make_event

import pytest


def test_extract_symbols_names_and_tickers():
    e = make_event("Bitcoin breaks $80K while ETH and Solana lag")
    assert e.symbols == ["BTC", "ETH", "SOL"]


def test_extract_symbols_ignores_substrings():
    e = make_event("Absolute solutions for adaptive solvers")
    assert e.symbols == []


def test_sentiment_classifier():
    assert classify_sentiment("Bitcoin surges to record high") == "positive"
    assert classify_sentiment("Exchange hacked, Ethereum drops") == "negative"
    assert classify_sentiment("Ethereum developers meet") == "neutral"


def test_relevance_and_expiry():
    p = Portfolio()
    p.add_asset(SpotAsset("BTC", 1, 1))
    fresh = make_event("Bitcoin news", 5)
    old = make_event("Bitcoin news old", 120)
    assert fresh.is_relevant_to(p)
    assert not make_event("Dogecoin news").is_relevant_to(p)
    assert old.is_expired(timedelta(minutes=15))
    assert not fresh.is_expired(timedelta(minutes=15))


def test_observer_notified_once_per_new_event():
    received = []

    class Collector(Observer):
        def update(self, event):
            received.append(event.title)

    src = StubNewsSource([make_event("Bitcoin a"), make_event("Bitcoin b")])
    obs = Collector()
    src.register_observer(obs)
    src.poll()
    src.poll()
    assert received == ["Bitcoin a", "Bitcoin b"]
    src.unregister_observer(obs)
    src.next_events = [make_event("Bitcoin c")]
    src.poll()
    assert len(received) == 2


def test_quick_trade_observer_filters_irrelevant_and_expired():
    p = Portfolio()
    p.add_asset(SpotAsset("BTC", 1, 1))
    obs = QuickTradeObserver(p, timedelta(minutes=15))
    obs.update(make_event("Bitcoin crash hits market", 3))
    obs.update(make_event("Dogecoin moon", 3))
    obs.update(make_event("Bitcoin old story", 90))
    items = obs.suggestions()
    assert len(items) == 1
    assert items[0]["symbol"] == "BTC"
    assert items[0]["suggested_direction"] == "SELL"


def test_fallback_news_uses_mock_when_primary_empty():
    src = FallbackNewsSource(StubNewsSource([]), MockNewsSource(), cache_seconds=0)
    events = src.poll()
    assert events and src.name == "Mock headlines"


def test_fallback_price_source_skips_failures():
    class Broken(PriceSource):
        name = "Broken"

        def fetch_prices(self, symbols):
            raise PriceUnavailable("down")

    src = FallbackPriceSource([Broken(), StaticPriceSource(PRICES)], cache_seconds=0)
    assert src.fetch_prices(["BTC"]) == {"BTC": 60000.0}
    assert src.name == "Static reference prices"


def test_balance_validator_rules():
    p = Portfolio(cash_balance=100)
    p.add_asset(SpotAsset("ETH", 0.01, 3000))
    v = BalanceValidator()
    assert v.validate(p, TradeOrder("BTC", 0.001, OrderDirection.BUY, 60000)).ok
    assert not v.validate(p, TradeOrder("BTC", 0.01, OrderDirection.BUY, 60000)).ok
    assert not v.validate(p, TradeOrder("ETH", 0.02, OrderDirection.SELL, 3000)).ok
    assert not v.validate(p, TradeOrder("BTC", 0.0001, OrderDirection.BUY, 60000)).ok  # below minimum


def _store():
    return SessionStore(StubNewsSource(), timedelta(minutes=15))


def test_trade_service_executes_and_updates_portfolio():
    store = _store()
    session = store.create()
    svc = TradeService(PaperExchange(StaticPriceSource(PRICES)), BalanceValidator())
    order = svc.place_order(session, "BTC", OrderDirection.BUY, 0.01)
    assert order.status is OrderStatus.EXECUTED
    pf = session.user.get_portfolio()
    assert pf.cash_balance == pytest.approx(10_000 - 600)
    assert pf.get_asset("BTC").quantity == pytest.approx(0.06)


def test_trade_service_rejects_insufficient_balance():
    session = _store().create()
    svc = TradeService(PaperExchange(StaticPriceSource(PRICES)), BalanceValidator())
    order = svc.place_order(session, "BTC", OrderDirection.BUY, 1)
    assert order.status is OrderStatus.REJECTED
    assert session.user.get_portfolio().cash_balance == 10_000


def test_trade_service_marks_failed_on_exchange_error():
    class Failing(PaperExchange):
        def submit_order(self, order) -> Fill:
            raise ExchangeError("exchange down")

    session = _store().create()
    svc = TradeService(Failing(StaticPriceSource(PRICES)), BalanceValidator())
    order = svc.place_order(session, "ETH", OrderDirection.SELL, 0.5)
    assert order.status is OrderStatus.FAILED
    assert session.user.get_portfolio().get_asset("ETH").quantity == 1.0


def test_trade_limit_per_session():
    session = _store().create()
    svc = TradeService(PaperExchange(StaticPriceSource(PRICES)), BalanceValidator(), max_trades_per_session=1)
    svc.place_order(session, "SOL", OrderDirection.BUY, 1)
    with pytest.raises(TradeLimitReached):
        svc.place_order(session, "SOL", OrderDirection.BUY, 1)


def test_session_reset_unregisters_old_observer():
    news = StubNewsSource()
    store = SessionStore(news, timedelta(minutes=15))
    s = store.create()
    assert len(news._observers) == 1
    new = store.reset(s.session_id)
    assert new.session_id != s.session_id
    assert store.get(s.session_id) is None
    assert len(news._observers) == 1


def test_sessions_are_isolated():
    store = _store()
    a, b = store.create(), store.create()
    svc = TradeService(PaperExchange(StaticPriceSource(PRICES)), BalanceValidator())
    svc.place_order(a, "BTC", OrderDirection.BUY, 0.01)
    assert b.user.get_portfolio().cash_balance == 10_000


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, payload):
        self._payload = payload

    def get(self, *args, **kwargs):
        return _FakeResp(self._payload)


def test_okx_parser():
    from app.services.price_source import OKXPriceSource

    payload = {"code": "0", "data": [{"instId": "BTC-USDT", "last": "81655.4"}, {"instId": "BTC-USDC", "last": "1"}]}
    assert OKXPriceSource(_FakeSession(payload)).fetch_prices(["BTC", "ETH"]) == {"BTC": 81655.4}


def test_kraken_parser_maps_xbt_and_xdg():
    from app.services.price_source import KrakenPriceSource

    payload = {"error": [], "result": {"XBTUSDT": {"c": ["81651.6", "0.1"]}, "XDGUSDT": {"c": ["0.0808", "5"]}}}
    assert KrakenPriceSource(_FakeSession(payload)).fetch_prices(["BTC", "DOGE"]) == {"BTC": 81651.6, "DOGE": 0.0808}


def test_fallback_fills_gaps_from_next_source():
    partial = StaticPriceSource({"BTC": 1.0})
    partial.name = "Partial"
    full = StaticPriceSource({"BTC": 2.0, "ETH": 3.0})
    src = FallbackPriceSource([partial, full], cache_seconds=0)
    assert src.fetch_prices(["BTC", "ETH"]) == {"BTC": 1.0, "ETH": 3.0}
    assert src.name == "Partial + Static reference prices"
