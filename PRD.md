You are Claude Code, and your task is to build a **very specific, non-generic** automated trading bot for **Polymarket V2** that trades **only the BTC 5‑minute interval market** using **Python**, with a clear project structure, internal TODO tracking, and incremental implementation (no “all in one shot” builds).

You are connected to **context7 MCP**, so you can access web APIs and documentation (e.g., Polymarket docs, Binance docs) directly. Use that capability whenever you need official details instead of guessing.

IMPORTANT META REQUIREMENTS
---------------------------
1. **Do not build everything at once.**
   - First: create a detailed, written **TODO / roadmap** and confirm it in the code environment.
   - Then implement the bot **in phases**, marking items as done.
   - Keep an explicit checklist in a file (e.g., `docs/todo.md`) or a clear comment block, and update it as you go.

2. **Avoid a generic trading bot.**
   - The bot must be tightly tailored to:
     - Polymarket **BTC 5-minute markets only**.
     - Strategy details given below (entry, hedging, locking profit, insurance logic, price thresholds).
     - Using **Binance BTC 5‑minute kline data** as the signal source.
   - No “template” strategy, no generic moving-average bot unless it is explicitly used only as the signal module and wired into the detailed logic given below.

3. **Ask clarifying questions when needed.**
   - Before implementing any part where the specification is ambiguous, **ask** me and then update the TODO list and design.
   - Do not silently assume risk parameters, symbol names, or market ids; derive them from docs or ask me.

4. **Always use official docs via context7.**
   - Use context7 to fetch:
     - Polymarket docs index: `https://docs.polymarket.com/llms.txt`  (for Gamma API, CLOB API, auth, order posting, etc.)
     - Polymarket market-data overview and CLOB/order docs.
     - Polymarket **V2** / CLOB v2 order and auth docs (order schema, signatures, GTD/FAK/FOK, etc.).
     - Polymarket maker vs taker behavior, order lifecycle, “market orders as marketable limits”. 
     - Binance BTC kline docs for **5m** interval (BTCUSDT/spot or futures, pick one clearly and stick to it).
   - Do NOT guess endpoint paths or request bodies. Always check docs with context7 first.

   (Docs to look up via context7, by URL or search keywords:
    - Polymarket overview & market data / Gamma API (/events, /markets, etc.).
    - Polymarket CLOB API order creation (`POST /order` or equivalent) and authentication.
    - Polymarket order lifecycle & order types (GTD, FOK, FAK; all orders are limit orders).
    - Polymarket prices & orderbook endpoints (`/price`, `/prices`, `/book`, etc.).
    - Binance REST Kline/candlestick endpoint for BTC 5m (`/api/v3/klines` or futures equivalent).)

5. **Maker-only trading constraint.**
   - The bot must place **maker** orders only on Polymarket (no taker/marketable orders).
   - This means:
     - Use limit orders with prices that **do not cross the spread** at creation.
     - If Polymarket supports a “post-only” or similar flag on CLOB V2 orders, use it.
     - Otherwise, implement price logic vs current best bid/ask to ensure orders rest on the book and don’t execute immediately.
   - Make sure the code comments explicitly explain how we avoid taker behavior.

6. **Main entrypoint and project structure.**
   - There must be a `main.py` at the project root which the user runs to start the bot.
   - The bot logic must be organized under a `bot/` package.
   - Historical / runtime metrics (PnL, trades, positions, logs) must be stored in a `data/` folder as CSVs.
   - A `scripts/` folder will hold any extra research/utility scripts that are **not part of the live bot**.
   - Use `.env` or config files for secrets; never hardcode private keys or API keys.

7. **Logging and tracking.**
   - Implement logging with timestamps and context (INFO/WARN/ERROR).
   - Every trade decision and execution should be recorded with:
     - Timestamp, market id, side (up/down), at what price, size, reason (signal, hedge, insurance, TP/SL), and resulting PnL.
   - PnL history should be saved to CSV in `data/` (e.g., `data/trades.csv`, `data/daily_pnl.csv`).

8. **Safety & mode control.**
   - Implement at least two modes:
     - **DRY_RUN / PAPER mode**: logs and records hypothetical trades, no real orders.
     - **LIVE mode**: real orders sent to Polymarket.
   - Default to DRY_RUN. Live mode must require explicit config or CLI flag.
   - Never attempt to trade without explicit Polymarket credentials present and confirmed.

------------------------------------
STEP 1 — CREATE DETAILED TODO LIST
------------------------------------
First, create a **clear, structured TODO plan** for the whole project. Represent it as a Markdown checklist in `docs/todo.md` and keep it updated.

The TODO should have at least these sections:

1. Documentation & Research
   - [ ] Use context7 to fetch Polymarket docs index (`https://docs.polymarket.com/llms.txt`) and relevant pages for:
         - Gamma API (market discovery for BTC 5m markets).
         - CLOB / order API (creating limit orders as maker, cancelling orders).
         - Authentication / signing (EIP-712, L2 auth, etc.).
   - [ ] Use context7 to fetch Binance BTC 5m kline docs (BTCUSDT; REST Kline endpoint).
   - [ ] Decide whether we use spot BTCUSDT or futures; document the choice in a config file or design doc.

2. Architecture & Project Layout
   - [ ] Define folder structure:
         - `main.py`
         - `bot/`
           - `__init__.py`
           - `config.py`
           - `binance_client.py`
           - `polymarket_client.py`
           - `strategy.py`
           - `position_manager.py`
           - `order_manager.py`
           - `pnl_tracker.py`
           - `state_store.py` (if needed)
           - `scheduler.py` or `runner.py`
         - `data/`
           - (CSV logs: `trades.csv`, `positions.csv`, `pnl.csv`, etc.)
         - `scripts/`
           - research utilities (e.g. fetching historical data, simulation)
         - `docs/`
           - `todo.md`
           - `config_example.md`
   - [ ] Define config system (.env + config class) for:
         - Polymarket credentials
         - Binance API details
         - Trading parameters (sizes, thresholds, etc.).
   - [ ] Define logging setup.

3. API Clients
   - [ ] Implement `BinanceClient`:
         - Fetch BTCUSDT 5m candles (recent history and streaming/polling).
         - Provide a clean interface like `get_recent_klines_5m(limit)` returning OHLCV data.
   - [ ] Implement `PolymarketClient`:
         - Authentication (via API key, L2 auth, EIP-712 signing using wallet key).
         - Market discovery for BTC 5m interval markets using Gamma API (filter events/markets by tags or series).
         - Price/Orderbook endpoints for a given BTC 5m market (CLOB API).
         - Place limit maker orders (CLOB V2).
         - Cancel orders.
         - Fetch positions for the wallet.

4. Strategy Module (Core Logic)
   - [ ] Encode the **BTC-only, 5-minute Polymarket strategy** in `strategy.py`:
         - Uses **Binance 5m BTC data** to pick direction (UP/DOWN).
         - Implements entry logic at specified price levels (e.g., when UP price ~0.58).
         - Implements profit-lock and loss-hedging logic.
         - Implements favorite logic when odds >= 0.80.
         - Implements insurance logic when odds <= 0.10.
   - [ ] Parameterize thresholds (0.58, 0.52, 0.80, 0.10, etc.) so they can be easily tuned.
   - [ ] Clearly document every step in comments.

5. Position & Order Management
   - [ ] Implement `PositionManager` to track:
         - How many shares we hold on UP and DOWN in the current BTC 5m market.
         - Our average entry prices.
         - Whether profit is already “locked” for that market.
   - [ ] Implement `OrderManager` to:
         - Place **maker-only** orders with appropriate limit price relative to order book.
         - Enforce minimum Polymarket constraints (min 5 shares, min 1 USD notional).
         - Avoid crossing the spread (so we remain maker).
   - [ ] Implement checks to prevent double-entry in the same direction when we already have the intended position.

6. PnL Tracking & CSV Logging
   - [ ] Design CSV schemas (`trades.csv`, `positions.csv`, `pnl.csv`).
   - [ ] Implement a `PnlTracker` that updates:
         - Realized PnL per resolved market.
         - Unrealized PnL while markets are live (if feasible).
   - [ ] Ensure every trade and PnL update is appended to CSV in `data/`.

7. Scheduler / Runner
   - [ ] Implement a loop/scheduler that:
         - Every 5 minutes (aligned with Polymarket BTC 5m interval), does:
             - Gathering current Binance BTC 5m data.
             - Reading current Polymarket odds/orderbook for the BTC 5m market.
             - Evaluating strategy.
             - Placing/cancelling orders as needed (as maker).
         - Handles network errors, timeouts, and retries gracefully.

8. Main Entrypoint
   - [ ] Implement `main.py` which:
         - Loads config.
         - Instantiates clients and strategy components.
         - Chooses DRY_RUN vs LIVE mode.
         - Starts the 5-minute cycle loop or scheduler.
         - Provides a simple CLI interface (e.g., `--live`, `--dry-run`).

9. Testing / Simulation
   - [ ] Implement at least one **backtest/simulation** script in `scripts/` to:
         - Use historical Binance 5m data + historical Polymarket prices (if accessible) OR approximate with simplified assumptions.
         - Replay strategy decisions and log hypothetical PnL.
   - [ ] Implement some unit or integration tests for:
         - Strategy entry/exit decisions.
         - Position sizing and insurance logic.
         - Maker-only order price calculations.

After you create `docs/todo.md`, show it (or summarize it) and ask me if I want changes before you start coding.

---------------------------------------------
STEP 2 — STRATEGY SPECIFICATION (DO NOT SKIP)
---------------------------------------------

Implement **exactly this high-level strategy logic**, but keep parameters configurable. Clarify anything ambiguous with me first.

1. Market universe:
   - Only trade **Polymarket BTC 5-minute interval markets** (e.g., BTC up/down over a 5-minute window).
   - Use Gamma API and/or Tags/Series to auto-detect the **current 5-minute BTC up/down market** and its market IDs for UP and DOWN.
   - Ensure you know the tokens or market IDs corresponding to:
     - “BTC up” 5-minute market.
     - “BTC down” 5-minute market.

2. Binance as signal source:
   - Use **Binance BTC 5m kline data** as the signal.
   - Symbol to use: default to `BTCUSDT` (spot or futures; document which in config).
   - Use the Binance REST Kline endpoint to get recent 5m candles.
   - I have not given you the exact signal logic; your job is:
     - Implement a reasonable and transparent “direction picking” module that uses 5m candle data (for example short-term momentum or simple pattern).
     - Make the signal module pluggable, so I can later swap it out.

3. Minimum trade constraints:
   - On Polymarket:
     - Minimum **5 shares**.
     - Minimum **1 USD worth of shares**.
   - The bot should respect both constraints when sizing orders.
   - Implement a helper to compute shares from a target notional and current price, and ensure it is at least 5 shares and at least 1 USD in notional.

4. Entry & hedging logic (0.58, 0.32, 0.52)
   - Suppose the strategy picks **UP** as the direction.
   - It then looks at the current UP odds/price in the BTC 5m Polymarket market.
   - Example scenario:
     - If UP price is around **0.58**, the bot:
       - Buys UP with the minimum size that satisfies 5 shares and 1 USD constraints.
       - This is considered the initial entry on UP.
   - If after buying UP at ~0.58:
     - Price moves in our favor:
       - Implement a **profit-locking mechanic**:
         - E.g., take partial profit or set up a hedge such that we lock in some guaranteed profit no matter how the market resolves.
         - You should design this part precisely and document it in code comments (use simple, deterministic rules).
     - Price moves against us:
       - If UP price falls and DOWN price becomes attractive:
         - For example, if DOWN is around **0.52** after we bought UP at 0.58:
           - Buy DOWN as a hedge, respecting min 5 shares and 1 USD constraints.
           - The idea is: if the market continues against the initial direction, the DOWN position compensates part of the loss.
   - This part is intentionally loosely specified — encode it as clear, parameterized rules, and explain your choices in comments.

5. Profit lock vs stop loss:
   - Implement logic that:
     - After the initial trade, if the market moves **in our favor** enough:
       - “Lock profit” by either:
         - Taking profit on the winning side, and/or
         - Buying the opposite side to construct a guaranteed positive net payoff at resolution.
       - Once profit is locked for that specific 5-minute market:
         - Mark that market as **“complete”** and do not enter more trades in it.
         - Wait for resolution.
     - If the market moves **against us**:
       - Have a rule-based **stop-loss or hedging** mechanism that caps maximum loss for that market.
       - Make these parameters configurable (e.g., maximum loss per market).

6. Favorite logic (>= 0.80 odds)
   - Focus especially on odds around **0.80**.
   - When UP odds are **>= 0.80**:
     - Market believes UP is a heavy favorite.
     - At this point:
       - Check UP side:
         - Compare **UP shares** vs **UP cost basis** (or vs DOWN exposure).
       - If **UP shares < cost / price** such that exposure is too low to meaningfully profit:
         - Buy additional UP shares so that:
           - `UP shares` becomes **greater than** the total cost basis we’ve put into the market (so a win yields good profit).
       - Re-check whether this new UP position still respects risk limits / maximum per-market exposure.

7. Insurance logic (<= 0.10 odds)
   - When UP odds fall to **<= 0.10**:
     - This is like “almost dead” favorite odds.
     - At this stage, implement an **insurance operation**:
       - Compare UP shares and DOWN shares:
         - If UP shares < DOWN shares:
           - Buy additional UP shares so that **UP shares == DOWN shares**.
           - The idea is: if the market reverses and UP wins despite low odds, we’re fully insured by equalizing both sides.
         - If UP shares > DOWN shares:
           - Do **nothing**: we are already “secure enough” against a reverse outcome.
   - Make sure the same logic can be mirrored if we initially bet DOWN and its odds go to 0.80 or 0.10. Either implement a symmetric version, or explicitly treat UP as “favorite side” variable, not hard-coded to literal UP.

8. Per-market lifecycle:
   - For each 5-minute BTC market:
     - Allow at most one **entry lifecycle**:
       - Initial entry (UP or DOWN).
       - Possible hedge on the opposite side.
       - Profit lock or insurance stage.
     - Once profit is locked or max loss reached, do not enter more trades for that market.
     - Mark the market as “done” and wait for final resolution to compute realized PnL.
   - Use `PositionManager` & `state_store` (if needed) to ensure you never re-enter a resolved or closed market.

-----------------------------------------
STEP 3 — POLYMARKET V2 / CLOB INTEGRATION
-----------------------------------------

1. Use context7 + Polymarket docs to:
   - Understand **CLOB V2** order schema (fields, type, price, size, side).
   - Understand authentication (API keys, EIP-712 signatures, wallet usage).
   - Understand order lifecycle: GTD, FOK, FAK, etc.
   - Understand how to:
     - Fetch orderbook for a market.
     - Post a new order.
     - Cancel an order.
   - Confirm minimum size constraints and tick sizes if defined.

2. Implement `PolymarketClient` methods:
   - `get_btc_5m_market()`: discover the current BTC 5-minute event and market (UP and DOWN token IDs).
   - `get_orderbook(market_id)`: fetch current best bid/ask for a given side.
   - `get_price(market_id)`: fetch current mid or last price.
   - `place_limit_order_maker(market_id, side, price, size, dry_run: bool)`.
   - `cancel_order(order_id, dry_run: bool)`.
   - `get_positions()`: retrieve current positions for the wallet on BTC 5m markets.

3. Maker-only implementation detail:
   - Use orderbook data to choose limit prices such that:
     - For a buy maker order: price is **<= best bid** (post on bid side) or just inside spread but not crossing.
     - For a sell maker order: price is **>= best ask** or placed to add liquidity without immediate matching.
   - Check if Polymarket CLOB V2 has a “post-only” or equivalent flag; if it exists, use it.
   - Add comments in `OrderManager` explaining how the logic ensures maker-only behavior.

--------------------------------
STEP 4 — BINANCE SIGNAL MODULE
--------------------------------

1. Use context7 + Binance docs to:
   - Confirm the REST endpoint to get BTCUSDT **5-minute** klines.
   - Confirm required parameters (symbol, interval, limit).
   - Verify response format (open time, open, high, low, close, volume, etc.).

2. Implement `BinanceClient`:
   - `get_recent_klines_5m(limit: int)` returns a structured list of candle objects or a DataFrame-like structure.
   - Add simple retry logic on network errors.

3. Implement a **pluggable signal function**:
   - Given recent N 5m candles:
     - Decide direction: `UP`, `DOWN`, or `NO_TRADE`.
   - You can implement a simple, explainable signal such as:
     - Short-term momentum, e.g., last close vs moving average or last few candles trending up/down.
   - Encapsulate this in `strategy.py`, e.g. `pick_direction_from_binance_data(candles)`.
   - All thresholds / lookback windows must be configuration parameters.

---------------------------------------
STEP 5 — PNL, LOGGING, AND STATE FILES
---------------------------------------

1. CSV files in `data/`:
   - `data/trades.csv`:
     - Columns: timestamp, market_id, side (UP/DOWN), action (BUY/SELL), price, shares, notional, mode (LIVE/DRY_RUN), reason_tag, order_id (if live), etc.
   - `data/pnl.csv`:
     - Columns: market_id, resolved_outcome, total_invested, total_return, realized_pnl, timestamp_resolved.
   - `data/positions.csv`:
     - Columns: market_id, up_shares, down_shares, avg_price_up, avg_price_down, locked_profit_flag, max_loss_reached_flag, etc.

2. Logging:
   - Use a logger that writes to console and a log file (e.g., `logs/bot.log`).
   - Every trade decision (even “no trade”) should include a clear log line explaining:
     - What conditions were evaluated.
     - Why the bot decided to trade or not trade.
   - Logs should make it easy to reconstruct what happened for each BTC 5m market.

-------------------------
STEP 6 — MAIN.PY & RUNNER
-------------------------

1. `main.py` responsibilities:
   - Parse CLI arguments or environment variables:
     - Mode: DRY_RUN (default) or LIVE.
     - Logging verbosity.
   - Load configuration (from `.env` or config file).
   - Instantiate:
     - `BinanceClient`
     - `PolymarketClient`
     - `Strategy`
     - `OrderManager`
     - `PositionManager`
     - `PnlTracker`
   - Start a loop or scheduler that:
     - Aligns with the 5-minute interval boundaries as closely as reasonable.
     - On each cycle:
       - Fetches latest Binance data.
       - Identifies current BTC 5m Polymarket market.
       - Gets current prices/orderbook for UP and DOWN.
       - Runs strategy logic.
       - Places/cancels maker orders accordingly.
       - Logs all actions.
   - Handle graceful shutdown (SIGINT) and ensure PnL/trades CSV are flushed.

-------------------------
STEP 7 — IMPLEMENT IN PHASES
-------------------------

Implement the project in **phases**, updating `docs/todo.md` as you complete tasks:

Phase 1: Research & Skeleton
- Complete documentation research (Polymarket + Binance).
- Confirm decisions: spot vs futures, exact BTC 5m market identification method, etc.
- Create project folder structure and empty module files.
- Implement basic config and logging.

Phase 2: API Clients
- Implement and test `BinanceClient` functions for 5m klines.
- Implement and test `PolymarketClient` for:
  - Fetching BTC 5m markets.
  - Getting prices/orderbook.
  - Authenticating.
- Implement minimal “place order (maker)” in DRY_RUN mode and log the hypothetical request.

Phase 3: Strategy & Position Management
- Implement `Strategy` logic including:
  - Direction picking from Binance data.
  - Entry, hedging, profit-lock, favorite (>=0.80) and insurance (<=0.10) logic.
- Implement `PositionManager` with in-memory state and simple persistence (if needed).
- Implement `OrderManager` with maker-only logic and min size constraints.

Phase 4: PnL, CSV, and Main Loop
- Wire `PnlTracker` to Polymarket positions and resolutions.
- Implement CSV logging for trades, PnL, positions.
- Implement main 5-minute loop in `main.py`, DRY_RUN only.

Phase 5: LIVE Mode & Hardening
- Add LIVE mode switching.
- Wire real Polymarket order posting and cancellation.
- Add more error handling, rate limit handling, and reconnection logic.
- Add some tests or simulation scripts under `scripts/`.

At the end of each phase, show me:
- What files were created/updated.
- The current state of `docs/todo.md`.
- Any assumptions you made and open questions you still have.

------------------------------------
FINAL REMINDERS FOR YOU (CLAUDE CODE)
------------------------------------

- Do **not** produce a generic Polymarket bot.
- Follow the described strategy and structure as the primary design.
- Use context7 for all documentation lookups and do not guess endpoints or schemas.
- Keep a living TODO checklist and show progress.
- Always prefer placing **maker** orders only on Polymarket, never taker/marketable orders.
- Start by creating `docs/todo.md` and showing it to me before writing any concrete implementation.