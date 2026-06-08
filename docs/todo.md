# Polymarket BTC 5‑Minute Maker Bot — Roadmap & TODO

> Single source of truth for scope, design decisions, and progress.
> Status legend: `[ ]` not started · `[~]` in progress · `[x]` done · `[!]` blocked / needs your input
> Last updated: 2026-06-08

---

## 0. Scope (what this bot is — and is NOT)

**IS:** A tightly‑scoped maker‑only bot that trades **only** Polymarket's **BTC "Up or Down" 5‑minute** interval markets, using **Binance BTCUSDT 5‑minute klines** as a *pluggable* directional signal, with explicit entry → hedge → profit‑lock → favorite(≥0.80) → insurance(≤0.10) lifecycle logic per market.

**IS NOT:** A generic MA‑crossover bot, a multi‑market bot, or a taker/momentum scalper. No template strategy. The signal module is the *only* generic-ish piece and it is pluggable behind one function.

---

## 1. Confirmed API facts (researched via context7 + official docs — do NOT re-guess)

### 1.1 Polymarket — market identity & discovery (Gamma API)
- Active market URL/slug is **deterministic**: `btc-updown-5m-<unix_ts>` where `<unix_ts>` is the window **start**, divisible by 300. → We compute the current/next slug from the clock; no scraping.
- Gamma base: `https://gamma-api.polymarket.com` · endpoints `/events`, `/markets`, `/tags`, `/sports`.
- Discovery path: `GET /events?slug=btc-updown-5m-<ts>` → event → its `markets[]` → outcome token IDs.
- Filter params available: `slug`, `tag_id`, `related_tags`, `exclude_tag_id`, `active`, `closed`, `order`, `ascending`, `limit`, `offset`.
- [x] **CONFIRMED (live probe):** market fields = `conditionId`, `clobTokenIds` (JSON-encoded string array), `outcomes` = `["Up","Down"]` (mapped by label, not index), `orderPriceMinTickSize` (0.01), `orderMinSize` (5). Exactly one market per event.
- [x] **CONFIRMED:** event/market carry a `resolutionSource` field; rules resolve via **Chainlink BTC/USD** (window end ≥ start ⇒ Up). Resolution is automatic on Polymarket; the bot reads it only for PnL.
- [x] **GOTCHA CONFIRMED:** Gamma `bestBid`/`bestAsk` can be STALE — trust CLOB `/book` / `/price` / `/midpoint` for live quotes. `/book` lists aren't reliably sorted, so the client sorts them (bids high→low, asks low→high).

### 1.2 Polymarket — orders (CLOB **V2**, via `py-clob-client-v2`)
- **Client = `py-clob-client-v2`** (PyPI `py-clob-client-v2`, import `py_clob_client_v2`, v1.0.1, Python ≥3.9.10). Official; Polymarket asks users to migrate off the legacy `py-clob-client`. (Verified via PyPI + docs, 2026-06.)
- Imports: `ApiCreds, ClobClient, OrderArgs, OrderType, PartialCreateOrderOptions, Side, MarketOrderArgs`.
- Init: `ClobClient(host, chain_id=137, key=<PK>, creds=<ApiCreds>)`; derive L2 creds via `creds = client.create_or_derive_api_key()`.
- Post a limit order: `client.create_and_post_order(order_args=OrderArgs(token_id, price, side, size), options=PartialCreateOrderOptions(tick_size="0.01"), order_type=OrderType.GTC)`.
- Order types: **GTC, GTD, FOK, FAK**. Tick sizes `0.1/0.01/0.001/0.0001`; `negRisk` per market.
- **Maker control:** primary guarantee = our non-crossing price math; confirm v2's post-only/options field in Phase 5 as the belt. [!] Verify v2 method names for read-book/cancel/positions in Phase 5 (README only showed order posting).
- Order book / prices: `/book`, `/price`, `/midpoint`, `/spread`, `/tick-size` (public; already implemented with stdlib).

### 1.3 Binance — signal source
- Spot: `GET https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=N` (limit ≤ 1000).
- Futures alt: `GET https://fapi.binance.com/fapi/v1/klines?...` (USDⓈ‑M perp).
- Response = array of arrays: `[openTime, open, high, low, close, volume, closeTime, quoteVol, numTrades, takerBuyBase, takerBuyQuote, ignore]`.
- 5m candles align to UTC :00/:05/:10… — matches Polymarket's 300‑second windows.

---

## 2. Decisions (LOCKED 2026-06-08)

- [x] **Q1 Signal feed → Binance SPOT** `BTCUSDT` (`api.binance.com/api/v3/klines`, `interval=5m`). Configurable to futures later.
- [x] **Q2 Base entry size → exchange minimum** (~$1, sized to satisfy ≥5 shares AND ≥$1 notional at the current price/tick).
- [x] **Q3 Max loss per market → NO CAP.** No hard per-market stop. Risk is governed *only* by the strategy rules (hedge / profit-lock / favorite≥0.80 / insurance≤0.10). `max_loss_per_market` defaults to `None` (disabled) but stays in config so a cap can be switched on later. ⚠️ Means favorite/insurance legs can keep adding size while odds qualify.
- [x] **Q4 Unfilled maker → 3s fill timeout + re-quote.** Place maker order; if not (fully) filled within `unfilled_timeout_sec = 3`, cancel and immediately re-place at the *nearest current* non-crossing price ("nearest new odd"). Repeat until filled or the window ends ⇒ runner needs a **fast inner loop**, not just a 5-min tick.

### Design notes / risks to keep visible
- **Basis risk:** signal (Binance) ≠ resolution (Chainlink). Document; never treat signal as ground truth for payout.
- **Maker on a 5‑min clock:** resting orders may not fill before resolution. This is *intended* (we accept missed trades over taking liquidity). Handling governed by Q4.
- **Symmetry:** "UP/DOWN" must be a *favorite-side variable*, not hard-coded. If we enter DOWN, the 0.80/0.10 logic mirrors automatically.

---

## 3. Architecture & project layout
- [x] Create structure:
  - `main.py` — entrypoint + CLI (`--dry-run` default / `--live`).
  - `bot/` — `__init__.py`, `config.py`, `models.py`, `logging_setup.py`, `binance_client.py`, `polymarket_client.py`, `signal_engine.py`, `strategy.py`, `position_manager.py`, `order_manager.py`, `pnl_tracker.py`, `state_store.py`, `market_clock.py`, `runner.py`.
  - `data/` — `trades.csv`, `positions.csv`, `pnl.csv` (+ `state.json`).
  - `logs/` — `bot.log`.
  - `scripts/` — research/backtest utilities (NOT part of live bot).
  - `docs/` — `todo.md`, `config_example.md`.
  - `.env.example`, `requirements.txt`, `.gitignore`.
- [x] `config.py`: dataclass loaded from `.env` — creds + all strategy params (thresholds 0.58/0.52/0.80/0.10, base size, feed choice, dry/live). Secrets redacted in logs via `safe_summary()`.
- [x] `logging_setup.py`: timestamped console + rotating `logs/bot.log`, INFO/WARN/ERROR.

## 4. Phase 1 — Research & skeleton
- [x] Polymarket + Binance doc research (this file §1).
- [x] Decide spot vs futures -> SPOT BTCUSDT (locked, Q1).
- [x] Decide BTC 5m market identification = deterministic slug `btc-updown-5m-<ts/300*300>`.
- [x] Create folders + interface-stub module files (all 13 `bot/` modules import cleanly on Python 3.13).
- [x] Implement `config.py`, `logging_setup.py`, `market_clock.py` (window math), `models.py`, `.env.example`, `requirements.txt`, `.gitignore`.
- [x] `main.py` offline self-check runs (prints deterministic current/next slug; no network; DRY_RUN).
- [x] Verify Gamma field names + resolution source on a live market — DONE via `scripts/probe_market.py` (see §1.1 CONFIRMED).

## 5. Phase 2 — API clients (DRY_RUN-safe)  ✅ done (LIVE auth deferred to Phase 5)
- [x] `bot/net.py`: stdlib (urllib) GET+JSON helper with retry/backoff (keeps Phases 2–4 dependency-free).
- [x] `BinanceClient.get_recent_klines_5m(limit, closed_only)` → list of `Kline`; drops in-progress candle.
- [x] `PolymarketClient`:
  - [x] `get_current_btc_5m_market()` / `get_market_by_slug()` → `MarketRef` (condition_id, up/down token ids by label, tick_size, min_order_size, neg_risk, window bounds) via deterministic slug + Gamma.
  - [x] `get_orderbook(token_id)` (self-sorted, best-first) / `get_price(token_id, side)` / `get_midpoint(token_id)`.
  - [ ] auth/signing wiring (L1 sign + L2 derive via py-clob-client) — **deferred to Phase 5 (LIVE only)**.
  - [x] `place_limit_order_maker(order, dry_run)` — logs the fully-formed maker request in DRY_RUN.
  - [x] `cancel_order(order_id, dry_run)` (DRY_RUN logs); `get_positions()` — **deferred to Phase 5**.
- [x] `scripts/probe_market.py` + `scripts/smoke_clients.py` (read-only/DRY_RUN) — both run green.

## 6. Phase 3 — Strategy, positions, orders  ✅ done (LIVE requote loop -> Phase 5)
- [x] `signal_engine`: pluggable `pick_direction(candles)`; default `MomentumSignal` (lookback + min-%); `build_signal()` factory.
- [x] `position_manager`: per-market UP/DOWN shares + cost basis, `entry_direction`/`hedged`/`locked`/`done`; `apply_fill`, `check_lock`, `realized_pnl`.
- [x] `order_manager`: pure `floor_shares` (≥5 shares AND ≥$1), `maker_limit_price` (non-crossing vs best bid/ask) + `post_only`; `execute()` with DRY_RUN optimistic fill.
  - [~] **Fill-or-requote loop:** `place_with_requote` skeleton (place → 3s → cancel → re-quote at nearest price); real fill-status polling is **Phase 5 (LIVE)**.
- [x] `strategy` lifecycle (thresholds configurable; favorite = entry-side variable, symmetric UP/DOWN; one action/tick):
  - [x] Entry: signal side priced in `[entry_min, entry_price]` (0.45–0.58).
  - [x] Hedge: opposite side ≥ ~0.52 (adverse move), once, base size.
  - [x] Favorite (≥0.80): top up entry side until `shares > cost` (a win profits).
  - [x] Insurance (≤0.10): equalize entry side up to opposite side; else nothing.
  - [x] Profit-lock: `check_lock` marks market done when `min(up,down) shares > cost` (guaranteed both-way). Payoffs are built by BUYING (no sell-leg), per the concrete thresholds.
  - [x] Stop-loss: DISABLED by design (no per-market cap); config hook retained.
- [x] `scripts/sim_strategy.py` — offline path sim + favorite/insurance/lock checks (all pass).

## 7. Phase 4 — PnL, CSV, main loop (DRY_RUN)  ✅ done
- [x] CSV schemas in `pnl_tracker`: `trades.csv` (ts, slug, direction, side, price, shares, notional, mode, reason_tag, order_id) · `positions.csv` (snapshot per fill) · `pnl.csv` (ts_resolved, slug, outcome, up/down shares, invested, return, realized_pnl).
- [x] `pnl_tracker`: realized PnL per resolved market (record_trade / record_position / record_resolution). Live position snapshots double as cost-basis state; mark-to-market unrealized = optional, not implemented.
- [x] `state_store`: atomic JSON (`data/state.json`) — done-windows + position snapshot for restart safety; `position_manager.snapshot/restore`.
- [x] `runner`: outer 300s market-roll + inner ~1s tick; signal computed once/window; per-tick book read → strategy → execute → CSV; window-end resolve (Binance candle as Chainlink proxy) → PnL; resilient (per-tick try/except).
- [x] `main.py`: load config, wire components, DRY_RUN default, `--live` refused until Phase 5, `--max-seconds`, graceful SIGINT/SIGTERM flush.
- [x] Validated: `scripts/sim_runner.py` (offline CSVs) + live `python main.py --dry-run --max-seconds 7` (discovery/signal/ticks/hold/stop).

## 8. Phase 5 — LIVE mode & hardening
- [ ] LIVE switch (requires creds present + explicit `--live`).
- [ ] Real post/cancel via CLOB; reconcile `get_positions()`.
- [ ] Rate-limit/timeout/reconnect handling; idempotency on restart via `state_store`.
- [ ] `scripts/backtest.py` (replay Binance 5m + simplified Polymarket odds) + unit tests for sizing, maker-price, favorite/insurance math.

---

## 9. Safety rails (always-on)
- Default **DRY_RUN**; LIVE requires explicit flag **and** confirmed creds.
- Never hardcode keys — `.env` only; `.gitignore` covers `.env`, `data/`, `logs/`.
- One entry-cycle per market; never re-enter a `done`/resolved market.
- Maker-only enforced two ways: `postOnly` flag **and** non-crossing price math (commented in `order_manager`).
