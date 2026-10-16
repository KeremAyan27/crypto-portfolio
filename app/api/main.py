"""FastAPI backend (API gateway layer from the D2 architecture)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.api.schemas import HealthOut, SessionOut, TradeOut, TradeRequest
from app.config import Settings, get_settings
from app.domain.trade_order import OrderDirection, OrderStatus
from app.services.balance_validator import BalanceValidator
from app.services.exchange_service import BinanceTestnetExchange, ExchangeService, PaperExchange
from app.services.news_source import FallbackNewsSource, MockNewsSource, NewsSource, RSSNewsSource
from app.services.price_source import (
    BinancePublicPriceSource,
    CoinGeckoPriceSource,
    FallbackPriceSource,
    KrakenPriceSource,
    OKXPriceSource,
    PriceUnavailable,
    StaticPriceSource,
)
from app.services.session_store import Session, SessionStore
from app.services.trade_service import TradeLimitReached, TradeService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class Container:
    settings: Settings
    exchange: ExchangeService
    news: NewsSource
    sessions: SessionStore
    trades: TradeService


def build_container(
    settings: Settings | None = None,
    exchange: ExchangeService | None = None,
    news: NewsSource | None = None,
) -> Container:
    settings = settings or get_settings()
    if exchange is None:
        prices = FallbackPriceSource(
            [BinancePublicPriceSource(), OKXPriceSource(), KrakenPriceSource(), CoinGeckoPriceSource(), StaticPriceSource()],
            cache_seconds=settings.price_cache_seconds,
        )
        if settings.trade_mode == "testnet" and settings.binance_api_key:
            exchange = BinanceTestnetExchange(settings.binance_api_key, settings.binance_api_secret, prices)
        else:
            exchange = PaperExchange(prices)
    if news is None:
        news = FallbackNewsSource(
            RSSNewsSource(settings.news_rss_url), MockNewsSource(), cache_seconds=settings.news_cache_seconds
        )
    freshness = timedelta(minutes=settings.news_freshness_minutes)
    sessions = SessionStore(news, freshness, settings.session_ttl_minutes, settings.max_sessions)
    trades = TradeService(exchange, BalanceValidator(), settings.max_trades_per_session)
    return Container(settings, exchange, news, sessions, trades)


def create_app(container: Container | None = None) -> FastAPI:
    c = container or build_container()
    app = FastAPI(
        title="Crypto Portfolio Management System (News-Driven)",
        description="MIS 326 term project prototype, rebuilt as a live web app. Trades are simulated unless testnet mode is enabled.",
        version="2.0.0",
    )
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.state.container = c
    freshness = timedelta(minutes=c.settings.news_freshness_minutes)

    def require_session(x_session_id: str | None = Header(default=None)) -> Session:
        session = c.sessions.get(x_session_id)
        if session is None:
            raise HTTPException(status_code=401, detail="unknown or expired session")
        return session

    def refresh_prices(session: Session) -> None:
        portfolio = session.user.get_portfolio()
        symbols = sorted(portfolio.symbols())
        if not symbols:
            return
        try:
            portfolio.update_prices(c.exchange.fetch_prices(symbols))
        except PriceUnavailable as exc:
            logger.warning("price refresh failed: %s", exc)

    def price_source_name() -> str:
        return getattr(c.exchange, "price_source_name", c.exchange.name)

    @app.get("/health", response_model=HealthOut, tags=["system"])
    def health() -> HealthOut:
        return HealthOut(
            status="ok",
            trade_mode="testnet" if isinstance(c.exchange, BinanceTestnetExchange) else "paper",
            exchange=c.exchange.name,
            price_source=price_source_name(),
            news_source=c.news.name,
            news_freshness_minutes=c.settings.news_freshness_minutes,
            active_sessions=c.sessions.count(),
        )

    @app.post("/session", response_model=SessionOut, tags=["session"])
    def create_session() -> SessionOut:
        c.news.poll()
        session = c.sessions.create()
        return SessionOut(session_id=session.session_id, username=session.user.username)

    @app.post("/session/reset", response_model=SessionOut, tags=["session"])
    def reset_session(session: Session = Depends(require_session)) -> SessionOut:
        new = c.sessions.reset(session.session_id)
        assert new is not None
        return SessionOut(session_id=new.session_id, username=new.user.username)

    @app.get("/portfolio", tags=["portfolio"])
    def get_portfolio(session: Session = Depends(require_session)) -> dict:
        refresh_prices(session)
        data = session.user.get_portfolio().to_dict()
        data["price_source"] = price_source_name()
        return data

    @app.get("/prices", tags=["market"])
    def get_prices() -> dict:
        try:
            prices = c.exchange.fetch_prices(list(c.settings.tracked_symbols))
        except PriceUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {"source": price_source_name(), "prices": prices}

    @app.get("/news", tags=["news"])
    def get_news(session: Session = Depends(require_session)) -> dict:
        events = c.news.poll()
        portfolio = session.user.get_portfolio()
        now = datetime.now(timezone.utc)
        items = []
        for event in events:
            item = event.to_dict(now)
            item["relevant"] = event.is_relevant_to(portfolio)
            item["expired"] = event.is_expired(freshness, now)
            items.append(item)
        return {"source": c.news.name, "freshness_minutes": c.settings.news_freshness_minutes, "items": items}

    @app.get("/quick-trades", tags=["news"])
    def quick_trades(session: Session = Depends(require_session)) -> dict:
        c.news.poll()
        suggestions = session.observer.suggestions()
        symbols = sorted({s["symbol"] for s in suggestions})
        prices: dict[str, float] = {}
        if symbols:
            try:
                prices = c.exchange.fetch_prices(symbols)
            except PriceUnavailable:
                prices = {}
        for s in suggestions:
            s["price"] = prices.get(s["symbol"])
        return {"items": suggestions}

    @app.post("/trades", response_model=TradeOut, tags=["trading"])
    def place_trade(req: TradeRequest, session: Session = Depends(require_session)) -> dict:
        symbol = req.symbol.upper()
        if symbol not in c.settings.tracked_symbols:
            raise HTTPException(status_code=400, detail=f"{symbol} is not supported in this demo")
        try:
            order = c.trades.place_order(session, symbol, OrderDirection(req.direction), req.quantity, req.news_event_id)
        except TradeLimitReached as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except PriceUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if order.status is OrderStatus.EXECUTED and order.direction is OrderDirection.BUY:
            # A newly held coin can make earlier headlines relevant.
            c.news.replay_to(session.observer)
        return order.to_dict()

    @app.get("/trades", response_model=list[TradeOut], tags=["trading"])
    def trade_history(session: Session = Depends(require_session)) -> list[dict]:
        return [o.to_dict() for o in reversed(session.history)]

    return app


app = create_app()
