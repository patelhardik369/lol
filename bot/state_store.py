"""Lightweight JSON persistence (data/state.json) so a restart doesn't double-act
on a window already handled this session.

Atomic writes via a temp file + os.replace so a crash mid-write can't corrupt the
state file.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Dict

from .config import Config
from .logging_setup import get_logger

log = get_logger("state")


class StateStore:
    def __init__(self, config: Config) -> None:
        self.config = config
        os.makedirs(config.data_dir, exist_ok=True)
        self.path = os.path.join(config.data_dir, "state.json")

    def load(self) -> Dict[str, Any]:
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except Exception as e:  # corrupt/unreadable -> start clean rather than crash
            log.warning("state load failed (%s); starting fresh", e)
            return {}

    def save(self, state: Dict[str, Any]) -> None:
        try:
            directory = os.path.dirname(self.path) or "."
            fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            os.replace(tmp, self.path)
        except Exception as e:
            log.warning("state save failed: %s", e)
