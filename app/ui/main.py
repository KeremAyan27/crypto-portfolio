"""Streamlit dashboard (UI layer). Talks to the FastAPI backend only."""

from __future__ import annotations

import html
import os

import pandas as pd
import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8001").rstrip("/")
REPO_URL = os.getenv("REPO_URL", "")
TIMEOUT = 10

st.set_page_config(page_title="Crypto Portfolio · News-Driven", page_icon="📈", layout="wide")

st.markdown(
    """
    <style>
      .block-container {padding-top: 2rem; max-width: 1280px;}
      div[data-testid="stMetricValue"] {font-variant-numeric: tabular-nums; font-size: 1.55rem;}
      .chip {display:inline-block; padding:2px 10px; margin:0 6px 6px 0; border-radius:999px;
             font-size:0.78rem; border:1px solid rgba(128,128,128,.35); opacity:.9}
      .news-item {padding:8px 0; border-bottom:1px solid rgba(128,128,128,.18);}
      .news-meta {font-size:0.78rem; opacity:.7}
      .tag {font-size:0.72rem; padding:1px 7px; border-radius:6px; margin-left:4px;}
      .tag-rel {background:rgba(46,160,67,.18);}
      .tag-exp {background:rgba(128,128,128,.18);}
      .tag-pos {background:rgba(46,160,67,.18);}
      .tag-neg {background:rgba(218,54,51,.18);}
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------- API client ----------

class ApiError(Exception):
    pass


def _new_session() -> str:
    resp = requests.post(f"{API_URL}/session", timeout=TIMEOUT)
    resp.raise_for_status()
    sid = resp.json()["session_id"]
    st.session_state.session_id = sid
    return sid


def api(method: str, path: str, **kwargs):
    sid = st.session_state.get("session_id") or _new_session()
    for attempt in range(2):
        try:
            resp = requests.request(
                method, f"{API_URL}{path}", headers={"X-Session-Id": sid}, timeout=TIMEOUT, **kwargs
            )
        except requests.RequestException as exc:
            raise ApiError(f"Backend unreachable: {exc}") from exc
        if resp.status_code == 401 and attempt == 0:
            sid = _new_session()
            continue
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except ValueError:
                detail = resp.text
            raise ApiError(str(detail))
        return resp.json()
    raise ApiError("session could not be created")


def fmt_usd(value: float | None) -> str:
    if value is None:
        return "–"
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def md_usd(value: float | None) -> str:
    """Dollar amount safe for Streamlit markdown (a bare $ starts a formula)."""
    return fmt_usd(value).replace("$", "\\$")


def fmt_qty(value: float) -> str:
    return f"{value:,.6f}".rstrip("0").rstrip(".")


def news_link(title: str, url: str | None) -> str:
    """Escape feed content before it goes into HTML; only allow http(s) links."""
    safe_title = html.escape(title)
    if url and url.startswith(("https://", "http://")):
        return f"<a href='{html.escape(url, quote=True)}' target='_blank' rel='noopener'>{safe_title}</a>"
    return safe_title


def fmt_age(minutes: float) -> str:
    if minutes < 60:
        return f"{int(minutes)} min ago"
    if minutes < 1440:
        return f"{int(minutes // 60)} h ago"
    return f"{int(minutes // 1440)} d ago"


# ---------- Sidebar ----------

try:
    health = requests.get(f"{API_URL}/health", timeout=TIMEOUT).json()
    backend_ok = True
except (requests.RequestException, ValueError):
    health, backend_ok = {}, False

with st.sidebar:
    st.subheader("About")
    st.write(
        "A news-driven crypto portfolio tracker. When a headline mentions a coin you hold, "
        "a Quick Trade card appears so you can act on it in one step."
    )
    st.caption(
        "Originally built as the term project prototype for MIS 326 Object-Oriented Modeling "
        "and Development at Boğaziçi University. Rebuilt as a live web app."
    )
    st.divider()
    st.markdown("**Status**")
    if backend_ok:
        st.markdown(
            f"<span class='chip'>Backend: online</span>"
            f"<span class='chip'>Prices: {html.escape(str(health.get('price_source')))}</span>"
            f"<span class='chip'>News: {html.escape(str(health.get('news_source')))}</span>"
            f"<span class='chip'>Mode: {html.escape(str(health.get('trade_mode')))}</span>",
            unsafe_allow_html=True,
        )
    else:
        st.error("Backend is offline. If this is the free hosting tier, it may be waking up; retry in a minute.")
    st.divider()
    st.markdown("**OOM principles in the code**")
    st.caption(
        "Abstraction: Asset, ExchangeService, NewsSource, PriceSource interfaces  \n"
        "Inheritance and polymorphism: SpotAsset and FutureAsset override value and P&L  \n"
        "Composition: a User owns exactly one Portfolio  \n"
        "Aggregation: a Portfolio holds Assets  \n"
        "Observer pattern: NewsSource notifies QuickTradeObserver  \n"
        "State machine: TradeOrder PENDING → VALIDATED → EXECUTED"
    )
    if REPO_URL:
        st.markdown(f"[Source code on GitHub]({REPO_URL})")
    st.divider()
    if st.button("Reset demo portfolio", width="stretch", disabled=not backend_ok):
        try:
            st.session_state.session_id = api("POST", "/session/reset")["session_id"]
            st.session_state.pop("selected", None)
            st.rerun()
        except ApiError as exc:
            st.error(str(exc))
    st.caption("Each visitor gets a private demo portfolio. Trades are simulated at live market prices.")

if not backend_ok:
    st.title("Crypto Portfolio Management System")
    st.stop()


# ---------- Header ----------

st.title("Crypto Portfolio Management System")
st.caption("News-driven paper trading · live market prices · simulated orders")


# ---------- Portfolio (auto-refresh) ----------

@st.fragment(run_every="30s")
def portfolio_section() -> None:
    try:
        pf = api("GET", "/portfolio")
    except ApiError as exc:
        st.error(str(exc))
        return
    pl = pf["total_profit_loss"]
    c1, c2 = st.columns(2)
    c3, c4 = st.columns(2)
    c1.metric("Total value", fmt_usd(pf["total_value"]))
    c2.metric("Cash (USDT)", fmt_usd(pf["cash_balance"]))
    c3.metric("Holdings", fmt_usd(pf["holdings_value"]))
    c4.metric("Unrealised P&L", fmt_usd(pl), delta=f"{pl / max(pf['holdings_value'] - pl, 1e-9):+.2%}" if pf["assets"] else None)

    rows = [
        {
            "Symbol": a["symbol"],
            "Type": a["asset_type"].title(),
            "Quantity": a["quantity"],
            "Avg cost": a.get("average_buy_price", a.get("entry_price")),
            "Price": a["current_price"],
            "Value": a["value"],
            "P&L": a["profit_loss"],
        }
        for a in pf["assets"]
    ]
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        width="stretch",
        column_config={
            "Quantity": st.column_config.NumberColumn(format="%.6f"),
            "Avg cost": st.column_config.NumberColumn(format="dollar"),
            "Price": st.column_config.NumberColumn(format="dollar"),
            "Value": st.column_config.NumberColumn(format="dollar"),
            "P&L": st.column_config.NumberColumn(format="dollar"),
        },
    )
    st.caption(f"Prices from {pf['price_source']}. Refreshes every 30 seconds.")


left, right = st.columns([3, 2], gap="large")

with left:
    st.subheader("Portfolio")
    portfolio_section()

    st.subheader("Trade history")
    try:
        history = api("GET", "/trades")
    except ApiError as exc:
        history = []
        st.error(str(exc))
    if history:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Time (UTC)": h["created_at"][11:19],
                        "Side": h["direction"],
                        "Symbol": h["symbol"],
                        "Qty": fmt_qty(h["quantity"]),
                        "Price": fmt_usd(h["price"]),
                        "Total": fmt_usd(h["total"]),
                        "Status": h["status"],
                        "Note": h["message"],
                    }
                    for h in history
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    else:
        st.caption("No trades yet. Pick a headline in Quick Trade to place one.")


# ---------- Quick Trade ----------

def submit_trade(symbol: str, direction: str, quantity: float, news_event_id: str | None) -> None:
    try:
        order = api(
            "POST",
            "/trades",
            json={"symbol": symbol, "direction": direction, "quantity": quantity, "news_event_id": news_event_id},
        )
    except ApiError as exc:
        st.session_state.flash = ("error", str(exc))
        return
    if order["status"] == "EXECUTED":
        st.session_state.flash = (
            "success",
            f"{order['direction']} {fmt_qty(order['quantity'])} {order['symbol']} at {md_usd(order['price'])} executed.",
        )
    else:
        note = order["message"].replace("$", "\\$")
        st.session_state.flash = ("warning", f"Order {order['status'].lower()}: {note}")


with right:
    st.subheader("Quick Trade")
    flash = st.session_state.pop("flash", None)
    if flash:
        getattr(st, flash[0])(flash[1])

    try:
        suggestions = api("GET", "/quick-trades")["items"]
    except ApiError as exc:
        suggestions = []
        st.error(str(exc))

    if not suggestions:
        st.caption("No fresh headline mentions a coin you hold right now.")
    else:
        labels = [
            f"{s['symbol']} · {s['event']['title'][:70]}{'…' if len(s['event']['title']) > 70 else ''}"
            for s in suggestions
        ]
        idx = st.selectbox(
            "Triggered by news", range(len(suggestions)), format_func=lambda i: labels[i], key="selected"
        )
        s = suggestions[idx]
        ev = s["event"]
        tag = {"positive": "tag-pos", "negative": "tag-neg"}.get(s["sentiment"], "tag-exp")
        link = news_link(ev["title"], ev.get("url"))
        st.markdown(
            f"<div class='news-item'>{link}<br><span class='news-meta'>{ev['source']} · "
            f"{fmt_age(ev['age_minutes'])}</span><span class='tag {tag}'>{html.escape(s['sentiment'])}</span></div>",
            unsafe_allow_html=True,
        )
        price = s.get("price")
        with st.form("quick_trade", border=True):
            c1, c2 = st.columns(2)
            direction = c1.radio(
                "Side", ["BUY", "SELL"], index=0 if s["suggested_direction"] == "BUY" else 1, horizontal=True
            )
            default_qty = round(250 / price, 6) if price else 0.01
            quantity = c2.number_input("Quantity", min_value=0.000001, value=default_qty, format="%.6f")
            est = quantity * price if price else None
            st.caption(f"{s['symbol']} price {md_usd(price)} · estimated total {md_usd(est)}")
            if st.form_submit_button("Validate and submit", type="primary", width="stretch"):
                submit_trade(s["symbol"], direction, quantity, ev["event_id"])
                st.rerun()
        st.caption("The balance check runs before the order is sent. Fills are simulated at the live price.")

    with st.expander("Manual trade"):
        with st.form("manual_trade", border=False):
            c1, c2, c3 = st.columns([1, 1, 1.2])
            symbol = c1.selectbox("Symbol", ["BTC", "ETH", "SOL", "XRP", "BNB", "ADA", "DOGE", "AVAX", "LINK", "DOT"])
            side = c2.selectbox("Side", ["BUY", "SELL"])
            qty = c3.number_input("Quantity", min_value=0.000001, value=0.01, format="%.6f")
            if st.form_submit_button("Submit", width="stretch"):
                submit_trade(symbol, side, qty, None)
                st.rerun()

    st.subheader("News feed")
    try:
        news = api("GET", "/news")
    except ApiError as exc:
        news = {"items": [], "source": "–", "freshness_minutes": 0}
        st.error(str(exc))
    only_relevant = st.toggle("Only coins I hold", value=False)
    items = [n for n in news["items"] if n["relevant"] or not only_relevant]
    if not items:
        st.caption("No headlines to show.")
    for n in items[:15]:
        tags = ""
        if n["symbols"]:
            tags += "".join(f"<span class='tag tag-exp'>{html.escape(sym)}</span>" for sym in n["symbols"])
        if n["relevant"] and not n["expired"]:
            tags += "<span class='tag tag-rel'>in portfolio</span>"
        elif n["expired"]:
            tags += "<span class='tag tag-exp'>expired</span>"
        title = news_link(n["title"], n.get("url"))
        st.markdown(
            f"<div class='news-item'>{title}<br><span class='news-meta'>{fmt_age(n['age_minutes'])}</span>{tags}</div>",
            unsafe_allow_html=True,
        )
    hours = news["freshness_minutes"] / 60
    st.caption(f"Source: {news['source']}. Headlines older than {hours:g} h are marked expired and do not trigger trades.")
