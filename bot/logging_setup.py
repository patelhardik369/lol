"""Logging configuration: timestamped, leveled output to both the console and a
rotating file at logs/bot.log.

Every strategy decision and order action in later phases flows through these
loggers (including NO_TRADE reasons), so an entire session can be reconstructed
from the log + the CSVs in data/.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

LOGGER_NAME = "polybot"
_FMT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATEFMT = "%Y-%m-%dT%H:%M:%S%z"


def setup_logging(level: str = "INFO", logs_dir: str = "logs",
                  log_file: str = "bot.log") -> logging.Logger:
    """Configure and return the shared 'polybot' logger.

    Idempotent: repeated calls won't stack duplicate handlers.
    """
    os.makedirs(logs_dir, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    if logger.handlers:  # already configured
        return logger

    formatter = logging.Formatter(_FMT, datefmt=_DATEFMT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    file_handler = RotatingFileHandler(
        os.path.join(logs_dir, log_file),
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def get_logger(name: str = LOGGER_NAME) -> logging.Logger:
    """Return a child logger that inherits the configured handlers."""
    if name == LOGGER_NAME:
        return logging.getLogger(LOGGER_NAME)
    return logging.getLogger(LOGGER_NAME).getChild(name)
