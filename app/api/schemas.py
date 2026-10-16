"""Pydantic v2 request/response models (DTOs)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.trade_order import OrderDirection


class SessionOut(BaseModel):
    session_id: str
    username: str


class TradeRequest(BaseModel):
    symbol: str = Field(min_length=2, max_length=10, examples=["BTC"])
    direction: OrderDirection
    quantity: float = Field(gt=0, le=1_000_000)
    news_event_id: str | None = None


class TradeOut(BaseModel):
    order_id: str
    symbol: str
    quantity: float
    direction: str
    price: float
    total: float
    status: str
    message: str
    news_event_id: str | None
    exchange_order_id: str | None
    created_at: str


class HealthOut(BaseModel):
    status: str
    trade_mode: str
    exchange: str
    price_source: str
    news_source: str
    news_freshness_minutes: int
    active_sessions: int
