"""Polymarket BTC 5-minute maker bot.

A tightly-scoped, maker-only trading bot for Polymarket's BTC "Up or Down"
5-minute interval markets, using Binance SPOT BTCUSDT 5m klines as a pluggable
directional signal.

Phase 1: scaffolding (config, logging, deterministic market clock, interfaces).
Submodules are intentionally NOT imported here so that `import bot` stays
dependency-free until the HTTP/CLOB clients are implemented (Phase 2+).
"""

__version__ = "0.1.0"
