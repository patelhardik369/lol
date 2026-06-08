"""Lightweight JSON persistence (data/state.json) so a restart doesn't double-act
on a window already handled this session.

INTERFACE STUB — implemented in Phase 3/4.
"""

from __future__ import annotations

from typing import Any, Dict

from .config import Config


class StateStore:
    def __init__(self, config: Config) -> None:
        self.config = config

    def load(self) -> Dict[str, Any]:
        raise NotImplementedError("StateStore.load -> Phase 3/4")

    def save(self, state: Dict[str, Any]) -> None:
        raise NotImplementedError("StateStore.save -> Phase 3/4")
