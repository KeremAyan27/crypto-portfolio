def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["trade_mode"] == "paper"


def test_requires_session(client):
    assert client.get("/portfolio").status_code == 401
    assert client.get("/portfolio", headers={"X-Session-Id": "nope"}).status_code == 401


def test_portfolio_has_live_prices(client, session_headers):
    pf = client.get("/portfolio", headers=session_headers).json()
    btc = next(a for a in pf["assets"] if a["symbol"] == "BTC")
    assert btc["current_price"] == 60000.0
    assert pf["cash_balance"] == 10_000


def test_news_marks_relevance_and_expiry(client, session_headers):
    items = client.get("/news", headers=session_headers).json()["items"]
    by_title = {i["title"]: i for i in items}
    assert by_title["Bitcoin rally pushes price to record high"]["relevant"] is True
    assert by_title["Dogecoin community plans meme event"]["relevant"] is False
    assert by_title["Ethereum falls after exploit report"]["expired"] is True


def test_quick_trades_only_fresh_relevant(client, session_headers):
    items = client.get("/quick-trades", headers=session_headers).json()["items"]
    assert [i["symbol"] for i in items] == ["BTC"]
    assert items[0]["suggested_direction"] == "BUY"
    assert items[0]["price"] == 60000.0


def test_trade_flow_end_to_end(client, session_headers):
    event_id = client.get("/quick-trades", headers=session_headers).json()["items"][0]["event"]["event_id"]
    r = client.post(
        "/trades",
        headers=session_headers,
        json={"symbol": "BTC", "direction": "BUY", "quantity": 0.01, "news_event_id": event_id},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "EXECUTED"
    history = client.get("/trades", headers=session_headers).json()
    assert len(history) == 1 and history[0]["news_event_id"] == event_id
    pf = client.get("/portfolio", headers=session_headers).json()
    assert pf["cash_balance"] == 10_000 - 600


def test_buying_new_coin_makes_its_news_relevant(client, session_headers):
    client.post("/trades", headers=session_headers, json={"symbol": "DOGE", "direction": "BUY", "quantity": 200})
    symbols = {i["symbol"] for i in client.get("/quick-trades", headers=session_headers).json()["items"]}
    assert "DOGE" in symbols


def test_rejected_trade_returns_reason(client, session_headers):
    r = client.post("/trades", headers=session_headers, json={"symbol": "BTC", "direction": "BUY", "quantity": 5})
    assert r.json()["status"] == "REJECTED"
    assert "insufficient balance" in r.json()["message"]


def test_unsupported_symbol_and_bad_input(client, session_headers):
    assert client.post("/trades", headers=session_headers, json={"symbol": "PEPE", "direction": "BUY", "quantity": 1}).status_code == 400
    assert client.post("/trades", headers=session_headers, json={"symbol": "BTC", "direction": "HOLD", "quantity": 1}).status_code == 422
    assert client.post("/trades", headers=session_headers, json={"symbol": "BTC", "direction": "BUY", "quantity": -1}).status_code == 422


def test_reset_session(client, session_headers):
    new_sid = client.post("/session/reset", headers=session_headers).json()["session_id"]
    assert client.get("/portfolio", headers=session_headers).status_code == 401
    assert client.get("/portfolio", headers={"X-Session-Id": new_sid}).status_code == 200
