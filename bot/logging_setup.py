"""Logging configuration.

Two sinks with different verbosity so the console stays beautiful while nothing is
lost on disk:

  - CONSOLE: clean ``HH:MM:SS  message`` at the configured level (default INFO).
    Empty messages render as true blank lines (used to space out new markets).
    Only the trade narrative (via ``bot.report``) is logged at INFO, so the
    console reads like a tidy trade blotter.
  - FILE (logs/bot.log): full ``timestamp | level | name | message`` at DEBUG, so
    every internal decision is still recoverable for forensics.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

LOGGER_NAME = "polybot"
_FILE_FMT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_FILE_DATEFMT = "%Y-%m-%dT%H:%M:%S%z"
_CONSOLE_DATEFMT = "%H:%M:%S"


class _ConsoleFormatter(logging.Formatter):
    """Clean console line; an empty message becomes a genuine blank line."""

    def format(self, record: logging.LogRecord) -> str:
        if record.getMessage() == "":
            return ""
        return super().format(record)


def setup_logging(level: str = "INFO", logs_dir: str = "logs",
                  log_file: str = "bot.log") -> logging.Logger:
    """Configure and return the shared 'polybot' logger. Idempotent."""
    os.makedirs(logs_dir, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)  # capture everything; handlers filter
    logger.propagate = False

    if logger.handlers:  # already configured
        return logger

    console = logging.StreamHandler()
    console.setLevel(getattr(logging, level.upper(), logging.INFO))
    console.setFormatter(_ConsoleFormatter("%(asctime)s  %(message)s", _CONSOLE_DATEFMT))
    logger.addHandler(console)

    file_handler = RotatingFileHandler(
        os.path.join(logs_dir, log_file), maxBytes=5_000_000, backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(_FILE_FMT, _FILE_DATEFMT))
    logger.addHandler(file_handler)

    return logger


def get_logger(name: str = LOGGER_NAME) -> logging.Logger:
    """Return a child logger that inherits the configured handlers."""
    if name == LOGGER_NAME:
        return logging.getLogger(LOGGER_NAME)
    return logging.getLogger(LOGGER_NAME).getChild(name)
