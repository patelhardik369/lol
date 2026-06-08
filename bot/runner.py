"""Orchestration loop.

OUTER loop rolls to the new market on every 300s boundary; INNER loop ticks about
every ``inner_tick_sec`` within a window: refresh klines/odds -> run strategy ->
drive the order_manager fill-or-requote loop -> log every decision (including
NO_TRADE reasons). Handles SIGINT for a clean flush of CSVs.

INTERFACE STUB — implemented in Phase 4.
"""

from __future__ import annotations

from .config import Config


class Runner:
    def __init__(self, config: Config, binance, polymarket, signal,
                 strategy, positions, orders, pnl) -> None:
        self.config = config
        self.binance = binance
        self.polymarket = polymarket
        self.signal = signal
        self.strategy = strategy
        self.positions = positions
        self.orders = orders
        self.pnl = pnl
        self._stop = False

    def run(self) -> None:
        """Blocking main loop (outer market-roll + inner fast tick)."""
        raise NotImplementedError("Runner.run -> Phase 4")

    def stop(self) -> None:
        """Signal the loop to exit cleanly (SIGINT handler -> flush CSVs)."""
        self._stop = True
