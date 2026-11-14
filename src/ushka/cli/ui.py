"""Small, consistent terminal output for the CLI (standard library only)."""

from __future__ import annotations

import sys
from typing import NoReturn

from ushka.core.log import paint, supports_color

# The mint diamond from the Ushka emblem.
MARK = "◆"


def _out(text: str = "") -> None:
    print(text, file=sys.stdout)


def _color() -> bool:
    return supports_color(sys.stdout)


def title(text: str) -> None:
    _out(f"{paint(MARK, 'pink', enabled=_color())} {paint(text, 'bold', enabled=_color())}")


def ok(text: str) -> None:
    _out(f"  {paint('✓', 'green', enabled=_color())} {text}")


def info(text: str) -> None:
    _out(f"  {paint('·', 'cyan', enabled=_color())} {text}")


def warn(text: str) -> None:
    _out(f"  {paint('!', 'yellow', enabled=_color())} {text}")


def error(text: str) -> None:
    print(f"  {paint('✗', 'red', enabled=supports_color(sys.stderr))} {text}", file=sys.stderr)


def hint(text: str) -> None:
    _out(f"    {paint(text, 'dim', enabled=_color())}")


def line(text: str = "") -> None:
    _out(text)


def code(text: str) -> str:
    return paint(text, "cyan", enabled=_color())


def fail(text: str, status: int = 1) -> NoReturn:
    """Prints an error and exits with `status` (non-zero, so scripts notice)."""
    error(text)
    raise SystemExit(status)
