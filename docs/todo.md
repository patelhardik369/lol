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
- [!] **To verify in Phase 1 (field names):** exact JSON fields for the two outcome token IDs (`clobTokenIds`), `outcomes` ordering (which index = "Up" vs "Down"), `conditionId`, and per-market `tickSize`/`minimum_order_size`.
- [!] **To verify:** resolution source. Search/market-rules indicate **Chainlink BTC/USD** (price at window end ≥ price at window start ⇒ "Up"). Confirm exact source + timing on the live market page.

### 1.2 Polymarket — orders (CLOB API, via `py-clob-client`)
- Flow: `create_order(OrderArgs)` → signed order → `post_order(signed, OrderType)`.
- `OrderArgs`: `token_id`, `price`, `size`, `side` (BUY/SELL); optional `fee_rate_bps`, `nonce`, `expiration`, `taker`.
- Order types: **GTC, GTD, FOK, FAK**.
- **Maker control:** `postOnly` flag exists on `postOrder` (TS client confirmed: applies to GTC/GTD). [!] Confirm the Python `py-clob-client` exposes `post_only` / equivalent; if not, enforce maker purely via non‑crossing price + (optionally) raw REST field.
- Tick sizes: `"0.1" | "0.01" | "0.001" | "0.0001"`; `negRisk` flag per market.
- Auth: **L1** = wallet signer (private key, EIP‑712) for signing orders; **L2** = derived API key/secret/passphrase headers for posting. Creds can be derived via `create_or_derive_api_creds()`.
- Order book / prices: `/book`, `/price`, `/midpoint`, `/spread`, `/tick-size` (CLOB market-data endpoints).

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
- [ ] Verify Gamma field names + resolution source on a live market (§1.1 [!]) — deferred to Phase 2.

## 5. Phase 2 — API clients (DRY_RUN-safe)
- [ ] `BinanceClient.get_recent_klines_5m(limit)` → list of OHLCV dataclasses; retry/backoff.
- [ ] `PolymarketClient`:
  - [ ] `get_current_btc_5m_market()` → `{condition_id, up_token_id, down_token_id, tick_size, window_start, window_end}` via deterministic slug + Gamma.
  - [ ] `get_orderbook(token_id)` / `get_price(token_id)` / `get_spread(token_id)`.
  - [ ] auth/signing wiring (L1 sign + L2 derive) — exercised only in LIVE.
  - [ ] `place_limit_order_maker(token_id, side, price, size, dry_run)` — logs request in DRY_RUN.
  - [ ] `cancel_order(order_id, dry_run)`, `get_positions()`.

## 6. Phase 3 — Strategy, positions, orders
- [ ] `signal_engine.pick_direction(candles) -> UP | DOWN | NO_TRADE` (pluggable; default = short‑term momentum, params in config).
- [ ] `position_manager`: per‑market UP/DOWN shares, avg prices, `locked` / `max_loss_hit` flags, lifecycle guard (one entry-cycle per market).
- [ ] `order_manager`: **maker-only** price computation (non‑crossing vs best bid/ask) + `postOnly`; enforce min 5 shares & min $1 notional; `shares_for_notional()` helper; dedupe same-direction re-entry.
  - [ ] **Fill-or-requote loop:** after placing, poll fill status; if unfilled after `unfilled_timeout_sec` (3s) ⇒ cancel + re-quote at nearest non-crossing price; repeat until filled or window end.
- [ ] `strategy` lifecycle (all thresholds configurable, favorite-side variable):
  - [ ] Entry near 0.58 on signal side.
  - [ ] Hedge: if adverse and opposite side ≈0.52 ⇒ buy opposite (min size).
  - [ ] Profit-lock: when favorable, construct guaranteed‑positive net payoff (buy opposite / partial close) → mark market **done**.
  - [ ] Favorite (≥0.80): if favorite-side shares ≤ total cost basis, add until `shares > cost_basis` (within max exposure).
  - [ ] Insurance (≤0.10): if fav‑side shares < other‑side shares, buy fav side up to **equalize**; if ≥, do nothing.
  - [ ] Stop-loss: DISABLED by default (no cap, per Q3); hook left in place so a `max_loss_per_market` cap can be enabled in config.

## 7. Phase 4 — PnL, CSV, main loop (DRY_RUN)
- [ ] CSV schemas: `trades.csv` (ts, market_id, side, action, price, shares, notional, mode, reason_tag, order_id) · `positions.csv` · `pnl.csv` (market_id, resolved_outcome, invested, return, realized_pnl, ts_resolved).
- [ ] `pnl_tracker`: realized per resolved market + unrealized while live.
- [ ] `runner`: **outer loop** rolls to the new market each 300s boundary; **inner loop** ticks fast (~1s) within the window — refresh klines/odds → run strategy → drive the order_manager fill-or-requote (3s) loop → log every decision (incl. NO_TRADE reasons).
- [ ] `main.py`: load config, build components, pick mode, run loop, graceful SIGINT flush.

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
