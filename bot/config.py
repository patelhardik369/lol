"""Central configuration for the Polymarket BTC 5-minute maker bot.

Every tunable lives here and is loaded from environment variables (optionally via
a local .env file). Secrets are read from the environment only — never hardcoded,
never logged (see `safe_summary`). DRY_RUN is the default mode; LIVE must be
selected explicitly and additionally requires credentials (validated here and,
more strictly, in later phases).
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import List, Optional

# python-dotenv is a convenience, not a hard requirement. Guard the import so the
# bot still loads in Phase 1 before dependencies are installed.
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except Exception:  # pragma: no cover - absence of dotenv is fine
    pass


DRY_RUN = "DRY_RUN"
LIVE = "LIVE"


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _get_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw not in (None, "") else default


def _get_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw not in (None, "") else default


def _get_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw in (None, ""):
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    # --- mode ---------------------------------------------------------------
    mode: str = DRY_RUN  # DRY_RUN | LIVE

    # --- Binance signal source (SPOT BTCUSDT only) --------------------------
    binance_base_url: str = "https://api.binance.com"
    binance_symbol: str = "BTCUSDT"
    binance_interval: str = "5m"
    binance_klines_limit: int = 50

    # --- Polymarket endpoints ----------------------------------------------
    gamma_base_url: str = "https://gamma-api.polymarket.com"
    clob_base_url: str = "https://clob.polymarket.com"
    chain_id: int = 137  # Polygon mainnet

    # --- Polymarket credentials (LIVE only; blank in DRY_RUN) ---------------
    private_key: str = ""       # EOA signer private key (L1 / EIP-712 signing)
    api_key: str = ""           # derived CLOB API key (L2 headers)
    api_secret: str = ""
    api_passphrase: str = ""
    funder_address: str = ""    # proxy / funder wallet address

    # --- strategy thresholds (share prices in 0..1) -------------------------
    entry_price: float = 0.58          # entry-band MAX: signal side must be <= this
    entry_min_price: float = 0.45      # entry-band MIN: skip entering a deep underdog
    hedge_opposite_price: float = 0.52
    favorite_threshold: float = 0.80
    insurance_threshold: float = 0.10
    price_tolerance: float = 0.01      # band around a target price for triggers
    favorite_margin_usd: float = 0.0   # favorite rule buys until fav_shares > cost + this
    lock_margin_usd: float = 0.0       # lock when min(up,down) shares > cost + this
    enable_loss_hedge: bool = False    # literal-spec adverse hedge at ~0.52 (off: it blocks locks)

    # --- sizing (Polymarket floors apply on top) ----------------------------
    base_notional_usd: float = 1.0  # "exchange minimum" base entry
    min_shares: int = 5             # Polymarket hard floor
    min_notional_usd: float = 1.0   # Polymarket hard floor

    # --- maker order behavior + loop cadence --------------------------------
    post_only: bool = True              # belt; non-crossing price math is the suspenders
    default_tick_size: str = "0.01"
    unfilled_timeout_sec: float = 3.0   # cancel & re-quote if not filled in 3s
    inner_tick_sec: float = 1.0         # fast in-window evaluation cadence
    entry_stop_buffer_sec: float = 10.0  # stop opening new ENTRIES this close to window end
    min_action_buffer_sec: float = 2.0   # place no orders at all in the last N seconds
    resolve_delay_sec: float = 150.0     # wait this long after window end, then resolve the REAL outcome

    # --- per-market risk cap (disabled by design) ---------------------------
    max_loss_per_market: Optional[float] = None

    # --- signal engine ------------------------------------------------------
    signal_name: str = "momentum"
    signal_lookback: int = 3
    signal_min_pct: float = 0.0  # min |return| over lookback to commit to a side

    # --- paths / logging ----------------------------------------------------
    data_dir: str = "data"
    logs_dir: str = "logs"
    log_level: str = "INFO"

    @property
    def is_live(self) -> bool:
        return self.mode == LIVE

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            mode=_get("POLYBOT_MODE", DRY_RUN).upper(),
            binance_base_url=_get("BINANCE_BASE_URL", "https://api.binance.com"),
            binance_symbol=_get("BINANCE_SYMBOL", "BTCUSDT"),
            binance_interval=_get("BINANCE_INTERVAL", "5m"),
            binance_klines_limit=_get_int("BINANCE_KLINES_LIMIT", 50),
            gamma_base_url=_get("POLYMARKET_GAMMA_URL", "https://gamma-api.polymarket.com"),
            clob_base_url=_get("POLYMARKET_CLOB_URL", "https://clob.polymarket.com"),
            chain_id=_get_int("POLYGON_CHAIN_ID", 137),
            private_key=_get("POLYMARKET_PRIVATE_KEY"),
            api_key=_get("POLYMARKET_API_KEY"),
            api_secret=_get("POLYMARKET_API_SECRET"),
            api_passphrase=_get("POLYMARKET_API_PASSPHRASE"),
            funder_address=_get("POLYMARKET_FUNDER_ADDRESS"),
            entry_price=_get_float("ENTRY_PRICE", 0.58),
            entry_min_price=_get_float("ENTRY_MIN_PRICE", 0.45),
            hedge_opposite_price=_get_float("HEDGE_OPPOSITE_PRICE", 0.52),
            favorite_threshold=_get_float("FAVORITE_THRESHOLD", 0.80),
            insurance_threshold=_get_float("INSURANCE_THRESHOLD", 0.10),
            price_tolerance=_get_float("PRICE_TOLERANCE", 0.01),
            favorite_margin_usd=_get_float("FAVORITE_MARGIN_USD", 0.0),
            lock_margin_usd=_get_float("LOCK_MARGIN_USD", 0.0),
            enable_loss_hedge=_get_bool("ENABLE_LOSS_HEDGE", False),
            base_notional_usd=_get_float("BASE_NOTIONAL_USD", 1.0),
            min_shares=_get_int("MIN_SHARES", 5),
            min_notional_usd=_get_float("MIN_NOTIONAL_USD", 1.0),
            post_only=_get_bool("POST_ONLY", True),
            default_tick_size=_get("DEFAULT_TICK_SIZE", "0.01"),
            unfilled_timeout_sec=_get_float("UNFILLED_TIMEOUT_SEC", 3.0),
            inner_tick_sec=_get_float("INNER_TICK_SEC", 1.0),
            entry_stop_buffer_sec=_get_float("ENTRY_STOP_BUFFER_SEC", 10.0),
            min_action_buffer_sec=_get_float("MIN_ACTION_BUFFER_SEC", 2.0),
            resolve_delay_sec=_get_float("RESOLVE_DELAY_SEC", 150.0),
            signal_name=_get("SIGNAL_NAME", "momentum"),
            signal_lookback=_get_int("SIGNAL_LOOKBACK", 3),
            signal_min_pct=_get_float("SIGNAL_MIN_PCT", 0.0),
            data_dir=_get("DATA_DIR", "data"),
            logs_dir=_get("LOGS_DIR", "logs"),
            log_level=_get("LOG_LEVEL", "INFO"),
        )

    def validate(self) -> List[str]:
        """Return a list of human-readable problems; empty list == OK.

        Phase 1 keeps this to sanity checks plus an early warning when LIVE is
        selected without credentials. Strict LIVE enforcement happens in Phase 5.
        """
        problems: List[str] = []
        if self.mode not in (DRY_RUN, LIVE):
            problems.append(f"mode must be DRY_RUN or LIVE, got {self.mode!r}")
        if not (0.0 < self.entry_price < 1.0):
            problems.append("entry_price must be strictly between 0 and 1")
        if self.min_shares < 5:
            problems.append("min_shares must be >= 5 (Polymarket floor)")
        if self.min_notional_usd < 1.0:
            problems.append("min_notional_usd must be >= 1 (Polymarket floor)")
        if self.binance_symbol != "BTCUSDT":
            problems.append("this bot is scoped to BTCUSDT only")
        if self.binance_interval != "5m":
            problems.append("this bot is scoped to the 5m interval only")
        if self.is_live and not self.private_key:
            problems.append("LIVE mode requires POLYMARKET_PRIVATE_KEY")
        return problems

    def safe_summary(self) -> dict:
        """Config snapshot with secrets redacted — safe to log."""
        d = asdict(self)
        for secret in ("private_key", "api_key", "api_secret", "api_passphrase"):
            if d.get(secret):
                d[secret] = "***redacted***"
        return d
