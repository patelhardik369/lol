# Polymarket BTC 5-Minute Maker Bot

Maker-only bot that trades **only** Polymarket's BTC "Up or Down" **5-minute** markets
(`btc-updown-5m-<unix_ts>`, the active slug computed from the clock — no scraping),
using a **Binance SPOT BTCUSDT 5m** signal. Lifecycle: entry (~0.58) → hedge (~0.52)
→ favorite (≥0.80) → insurance (≤0.10), with guaranteed-profit **lock** detection.

> **DRY_RUN by default. No real orders are sent until LIVE mode (Phase 5).**

Full roadmap/status: [`docs/todo.md`](docs/todo.md) · config reference: [`docs/config_example.md`](docs/config_example.md).

## Requirements
- **Python 3.9+** (developed on 3.13).
- **Paper / DRY_RUN needs NOTHING installed** — read + paper-trade paths use only the
  standard library. `python-dotenv` is an optional convenience.
- **LIVE (Phase 5)** uses the official **`py-clob-client-v2`** (`pip install py-clob-client-v2`).

## Paper test (DRY_RUN) — quickest path
No install required. From the project root:

```powershell
# Bounded run against the live market (recommended first look):
python main.py --dry-run --max-seconds 60

# Verbose — see every per-tick decision, including holds:
python main.py --dry-run --max-seconds 60 --log-level DEBUG

# Unbounded loop (Ctrl-C to stop; state is flushed on exit):
python main.py --dry-run
```

Each 5-minute window the bot discovers the market, computes the Binance 5m signal
once, then ticks ~1×/sec: reads the UP/DOWN order books, runs the strategy, and
**logs hypothetical maker orders** (nothing is sent). At window end it resolves the
outcome (Binance candle as a Chainlink proxy) and records realized PnL.

> Tip: trades only fire when the signal side is priced inside the entry band
> `[0.45, 0.58]`. If BTC is trending hard, the favorite is often already >0.58 and
> the bot correctly **holds**. The offline sims below always exercise the full path.

### Deterministic offline demos (no network)
```powershell
python scripts/sim_strategy.py   # entry->hedge->favorite, + favorite/insurance/lock checks
python scripts/sim_runner.py     # full runner loop; writes & prints data/sim/*.csv
```

### Live read-only probes (network, but no orders, no credentials)
```powershell
python scripts/probe_market.py   # raw Gamma/CLOB fields for the current 5m market
python scripts/smoke_clients.py  # klines + discovery + book + one DRY_RUN order log
```

## Outputs
- `logs/bot.log` — full timestamped log (rotating).
- `data/trades.csv` — every paper fill (ts, slug, direction, side, price, shares, notional, mode, reason_tag, order_id).
- `data/positions.csv` — position snapshot after each fill.
- `data/pnl.csv` — realized PnL per resolved market.
- `data/state.json` — restart-safety state (finalized windows + positions).

(`data/` and `logs/` contents are gitignored.)

## Optional: virtualenv + .env
```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install python-dotenv          # optional, only to load a local .env
Copy-Item .env.example .env        # DRY_RUN needs NO secrets
```

## LIVE mode (Phase 5 — not enabled yet)
`--live` is currently **refused** by design (no half-trading). Phase 5 wires the
official **`py-clob-client-v2`** for L1/L2 auth + EIP-712 signing and the real
3-second fill-or-requote loop. LIVE will require your Polymarket wallet / API
credentials in `.env` and an explicit opt-in. Maker-only is enforced two ways:
non-crossing limit price **and** the client's post-only flag.
