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

# Start FRESH — wipe prior trades/positions/pnl CSVs + state.json first:
python main.py --dry-run --reset
```

Each 5-minute window the bot discovers the market, computes the Binance 5m signal
once, then ticks ~1×/sec: reads the UP/DOWN order books, runs the strategy, and
**logs hypothetical maker orders** (nothing is sent) as a clean trade blotter.
~2.5 min after a window closes (`RESOLVE_DELAY_SEC`) it reads the **real settled
outcome** from Polymarket (Binance candle only as a fallback), records realized
PnL, and prints the running + final **session P&L**.

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
- `data/positions.csv` — final position snapshot, one row per resolved market.
- `data/pnl.csv` — realized PnL per resolved market.
- `data/state.json` — restart-safety state (finalized windows + positions).

(`data/` and `logs/` contents are gitignored.)

## Pull data from a VPS run

If you run the bot on a server, pull its results to your machine with an instant
P&L summary. Run from your **local** PowerShell (not inside SSH):

```powershell
.\scripts\pull_vps_data.ps1
# override defaults if needed:
.\scripts\pull_vps_data.ps1 -Server root@1.2.3.4 -RemotePath /home/claude/lol -Dest .\vps_data
```

It copies `trades/positions/pnl.csv + state.json + bot.log` into `.\vps_data\`
(separate from your local `data\`) and prints markets / wins / losses / total P&L.
Raw equivalent: `scp -r root@HOST:/home/claude/lol/data .\vps_data`.

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
