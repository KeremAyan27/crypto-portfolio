**Crypto Portfolio Management System (News-Driven)**

A crypto portfolio tracker that reacts to news. When a headline mentions a coin in your portfolio, the app shows a Quick Trade card so you can buy or sell that coin in one step. Prices are live market prices. Orders are simulated.

I first built this as the working prototype for our MIS 326 Object-Oriented Modeling and Development term project at Boğaziçi University (Spring 2026). I did the project and wrote the code; teammates helped with some of the diagrams and the presentation. This repository is a rebuild of that prototype as a live web app, keeping the same class design and flow from the project report. Both versions were built with AI coding assistance (Claude Code).

Live demo: (add the Render URL here)

Here is how a trade happens. The news source fetches headlines from the CoinTelegraph RSS feed (a public list of the latest articles) and turns each one into a NewsEvent, which extracts the coin symbols it mentions. Every visitor has a QuickTradeObserver registered with the news source; the observer keeps an event only if it mentions a coin the visitor holds and is not older than the freshness window. The visitor picks a card, sets a quantity, and submits. The BalanceValidator checks cash or holdings first. If the check passes, the order goes to the exchange service, the portfolio is updated, and the TradeOrder moves from PENDING to VALIDATED to EXECUTED. If it fails, the order is marked REJECTED with the reason, and nothing changes.

Trades are paper trades by default (simulated fills at the current market price, no real or test money). A public page with a trade button would otherwise let any visitor spend from one shared exchange account. The code can still place real market orders on Binance Spot Testnet (Binance's sandbox exchange with fake balances): set TRADE_MODE=testnet and add testnet keys. That mode is meant for running locally.

Each visitor gets a private demo portfolio of 10,000 USDT cash plus some BTC, ETH and SOL. Sessions live in memory and expire after two hours of inactivity, so one visitor's trades never show up for another. There is also a limit of 50 trades per session. Restarting the server resets everything, which is fine for a demo and means there is no database to maintain.

Prices come from the Binance public market-data endpoint, which needs no API key. If that fails, the app tries CoinGecko, and if that also fails it shows fixed reference prices. The source in use is always shown on the page, so a fallback is never presented as live data. News works the same way: if the RSS feed is unreachable, the app shows a small set of sample headlines and labels them as such.

The freshness window is 24 hours on the live site. The course prototype used 15 minutes, which is closer to how a news-driven trade would really work, but with a 15-minute window most visitors would see no Quick Trade cards at all. The value is one environment variable (NEWS_FRESHNESS_MINUTES).

The sentiment label on each headline is a keyword count, not a model. "Surges" and "record high" count as positive, "hack" and "falls" as negative. It only sets the default side of the Quick Trade form. Nothing in this app is investment advice.

The structure follows the layered architecture from the project report. The Streamlit dashboard (a Python framework for data apps) is the UI layer and only talks to the backend over HTTP. The FastAPI backend (a Python web framework for building APIs) is the gateway layer. Under it sit the services (trade execution, balance validation, news, prices, sessions) and the domain classes.

```
app/
  domain/    Asset (abstract), SpotAsset, FutureAsset, Portfolio, User,
             NewsEvent, Observer/Subject, TradeOrder
  services/  ExchangeService (PaperExchange, BinanceTestnetExchange),
             PriceSource chain, NewsSource (RSS, Mock, Fallback),
             BalanceValidator, QuickTradeObserver, TradeService, SessionStore
  api/       FastAPI app and Pydantic schemas
  ui/        Streamlit dashboard
tests/       37 tests covering domain rules, the observer flow and the API
```

The object-oriented principles from the course are visible in the code. Asset, ExchangeService, NewsSource and PriceSource are abstract interfaces. SpotAsset and FutureAsset inherit from Asset and each override the value and profit/loss calculation, so the Portfolio can total any asset without knowing its type. A User owns exactly one Portfolio (composition), while the Portfolio holds Assets (aggregation). NewsSource is the subject of an Observer pattern and notifies QuickTradeObserver. TradeOrder enforces the state machine from the project's statechart diagram and refuses invalid transitions.

To run it locally you need Python 3.11 or newer.

```
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
./start.sh                        # API on 127.0.0.1:8001, UI on localhost:8501
```

You can also run the two parts separately. The API docs are then at http://localhost:8001/docs.

```
uvicorn app.api.main:app --port 8001
streamlit run app/ui/main.py
pytest
```

The live site runs on Render's free tier as a single Docker service in the Frankfurt region. The Docker build runs the test suite, so a failing test stops the deploy. Frankfurt matters because Binance is known to block some requests from US-based servers, though I have not tested which endpoints are affected. The free tier sleeps after about 15 minutes without traffic, so the first visit after a quiet period can take up to a minute to load.

To deploy your own copy: push this repository to GitHub, open Render, choose New, then Blueprint, and select the repository. Render reads render.yaml and creates the service. Set REPO_URL to the GitHub link if you want it shown in the sidebar.
