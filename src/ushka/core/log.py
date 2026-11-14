"""Terminal output for Ushka: coloured, compact, standard-library only.

Colours are used only when the stream is a terminal, and never when the
``NO_COLOR`` environment variable is set (https://no-color.org). Setting
``FORCE_COLOR`` forces them on (useful in CI logs that render ANSI).
"""

from __future__ import annotations

import logging
import os
import sys
from typing import IO, Literal

LogLevelType = Literal["NOTSET", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

log = logging.getLogger("ushka")

RESET = "\033[0m"
STYLES = {
    "dim": "\033[2m",
    "bold": "\033[1m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "pink": "\033[38;5;211m",
}
LEVEL_STYLE = {
    logging.DEBUG: ("dim", "debug"),
    logging.INFO: ("cyan", "info "),
    logging.WARNING: ("yellow", "warn "),
    logging.ERROR: ("red", "error"),
    logging.CRITICAL: ("red", "crit "),
}


def supports_color(stream: IO | None = None) -> bool:
    """True if ANSI colours should be written to `stream` (stderr by default)."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    stream = stream if stream is not None else sys.stderr
    return bool(getattr(stream, "isatty", lambda: False)())


def paint(text: str, *styles: str, enabled: bool | None = None) -> str:
    """Wraps `text` in ANSI styles (see `STYLES`) when colour is enabled."""
    if enabled is None:
        enabled = supports_color()
    if not enabled or not styles:
        return text
    return "".join(STYLES[s] for s in styles) + text + RESET


class UshkaFormatter(logging.Formatter):
    """``12:01:02 info  message`` with a coloured level tag."""

    def __init__(self, color: bool):
        super().__init__(datefmt="%H:%M:%S")
        self.color = color

    def format(self, record: logging.LogRecord) -> str:
        style, label = LEVEL_STYLE.get(record.levelno, ("", record.levelname.lower()))
        time = self.formatTime(record, self.datefmt)
        line = (
            f"{paint(time, 'dim', enabled=self.color)} "
            f"{paint(label, style, enabled=self.color)} {record.getMessage()}"
        )
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


class _UshkaHandler(logging.StreamHandler):
    """Marker subclass so `setup_logging` can be called more than once."""


def setup_logging(level: LogLevelType = "INFO") -> logging.Logger:
    """Configures the ``ushka`` logger. Safe to call repeatedly."""
    log.setLevel(level)
    for handler in list(log.handlers):
        if isinstance(handler, _UshkaHandler):
            log.removeHandler(handler)
    handler = _UshkaHandler(sys.stderr)
    handler.setFormatter(UshkaFormatter(color=supports_color(sys.stderr)))
    log.addHandler(handler)
    log.propagate = False
    return log


def get_log_config(level: LogLevelType = "INFO") -> dict:
    """A ``logging.config`` dict that routes Uvicorn's output through Ushka's style."""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "ushka": {"()": UshkaFormatter, "color": supports_color(sys.stderr)},
        },
        "handlers": {
            "default": {
                "formatter": "ushka",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": level, "propagate": False},
            "uvicorn.error": {"level": level},
            "uvicorn.access": {"handlers": ["default"], "level": level, "propagate": False},
        },
    }
