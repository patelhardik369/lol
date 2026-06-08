# Configuration reference

Copy `.env.example` to `.env` and edit. `.env` is gitignored. **DRY_RUN requires
no secrets.** Every variable below maps 1:1 to a field on `bot/config.py:Config`
(loaded via `Config.from_env()`).

## Mode
| Env | Default | Meaning |
|-----|---------|---------|
| `POLYBOT_MODE` | `DRY_RUN` | `DRY_RUN` (safe, no orders) or `LIVE` (Phase 5). |

## Binance signal (spot BTCUSDT only)
| Env | Default | Meaning |
|-----|---------|---------|
| `BINANCE_BASE_URL` | `https://api.binance.com` | Spot REST host. |
| `BINANCE_SYMBOL` | `BTCUSDT` | Scope-locked; validation rejects anything else. |
| `BINANCE_INTERVAL` | `5m` | Scope-locked to 5 minutes. |
| `BINANCE_KLINES_LIMIT` | `50` | How many recent candles to pull. |

## Polymarket endpoints
| Env | Default |
|-----|---------|
| `POLYMARKET_GAMMA_URL` | `https://gamma-api.polymarket.com` |
| `POLYMARKET_CLOB_URL` | `https://clob.polymarket.com` |
| `POLYGON_CHAIN_ID` | `137` |

## Polymarket credentials (LIVE only — leave blank for DRY_RUN)
`POLYMARKET_PRIVATE_KEY`, `POLYMARKET_API_KEY`, `POLYMARKET_API_SECRET`,
`POLYMARKET_API_PASSPHRASE`, `POLYMARKET_FUNDER_ADDRESS`.

## Strategy thresholds (share prices, 0..1)
| Env | Default | Role |
|-----|---------|------|
| `ENTRY_PRICE` | `0.58` | Entry-band MAX: signal side must be ≤ this to enter. |
| `ENTRY_MIN_PRICE` | `0.45` | Entry-band MIN: skip deep-underdog entries. |
| `HEDGE_OPPOSITE_PRICE` | `0.52` | Opposite-side price that triggers a hedge. |
| `FAVORITE_THRESHOLD` | `0.80` | At/above this, run the favorite add-on. |
| `INSURANCE_THRESHOLD` | `0.10` | At/below this, run the insurance equalize. |
| `PRICE_TOLERANCE` | `0.01` | Band around a target price for triggers. |
| `FAVORITE_MARGIN_USD` | `0.0` | Favorite buys until fav_shares > cost + this. |
| `LOCK_MARGIN_USD` | `0.0` | Min guaranteed profit ($) required to lock (0 = any profit). |
| `ENABLE_LOSS_HEDGE` | `false` | Literal-spec adverse hedge at ~0.52 (off by default; it blocks profit-locks). |

> Entry is now **pure signal** (enter the signal side at any price). `ENTRY_PRICE` / `ENTRY_MIN_PRICE` are retained but no longer gate entry.

## Sizing (Polymarket floors: >= 5 shares AND >= $1 notional)
| Env | Default |
|-----|---------|
| `BASE_NOTIONAL_USD` | `1.0` |
| `MIN_SHARES` | `5` |
| `MIN_NOTIONAL_USD` | `1.0` |

## Maker behavior + loop cadence
| Env | Default | Role |
|-----|---------|------|
| `POST_ONLY` | `true` | Post-only flag (plus non-crossing price math). |
| `DEFAULT_TICK_SIZE` | `0.01` | Fallback tick; real tick comes per-market. |
| `UNFILLED_TIMEOUT_SEC` | `3` | Cancel & re-quote if unfilled within 3s. |
| `INNER_TICK_SEC` | `1` | Fast in-window evaluation cadence. |
| `ENTRY_STOP_BUFFER_SEC` | `10` | Stop opening new entries this close to close. |
| `MIN_ACTION_BUFFER_SEC` | `2` | Place no orders at all in the last N seconds. |
| `RESOLVE_DELAY_SEC` | `150` | Wait this long after a window ends, then read the real settled outcome. |

## Signal engine
| Env | Default |
|-----|---------|
| `SIGNAL_NAME` | `momentum` |
| `SIGNAL_LOOKBACK` | `3` |
| `SIGNAL_MIN_PCT` | `0.0` (min abs return over lookback to commit to a side) |

## Paths / logging
| Env | Default |
|-----|---------|
| `DATA_DIR` | `data` |
| `LOGS_DIR` | `logs` |
| `LOG_LEVEL` | `INFO` |
