from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.main import build_container, create_app
from app.config import Settings
from app.domain.news_event import NewsEvent
from app.services.exchange_service import PaperExchange
from app.services.news_source import NewsSource
from app.services.price_source import StaticPriceSource

PRICES = {"BTC": 60000.0, "ETH": 3000.0, "SOL": 150.0, "XRP": 0.5, "BNB": 500.0,
          "ADA": 0.4, "DOGE": 0.1, "AVAX": 25.0, "LINK": 12.0, "DOT": 5.0}


class StubNewsSource(NewsSource):
    name = "Stub"

    def __init__(self, events: list[NewsEvent] | None = None):
        super().__init__()
        self.next_events = events or []

    def fetch_news(self) -> list[NewsEvent]:
        return self.next_events


def make_event(title: str, minutes_ago: int = 5) -> NewsEvent:
    return NewsEvent(title=title, publish_time=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago), source="Stub")


@pytest.fixture
def stub_news() -> StubNewsSource:
    return StubNewsSource(
        [
            make_event("Bitcoin rally pushes price to record high", 5),
            make_event("Dogecoin community plans meme event", 10),
            make_event("Ethereum falls after exploit report", 60 * 30),
        ]
    )


@pytest.fixture
def client(stub_news) -> TestClient:
    exchange = PaperExchange(StaticPriceSource(PRICES))
    container = build_container(Settings(), exchange=exchange, news=stub_news)
    return TestClient(create_app(container))


@pytest.fixture
def session_headers(client) -> dict:
    sid = client.post("/session").json()["session_id"]
    return {"X-Session-Id": sid}
