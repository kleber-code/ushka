"""The error raised when an untrusted value reaches a dangerous sink.

The message is written for two readers at once: a developer reading a
traceback, and a coding agent that has to fix the code on the next try. That
is why every error carries the sink, the source, a concrete fix and a stable
code, and why `to_dict()` exists.
"""

from __future__ import annotations

from typing import Any

__all__ = ["UnsafeValueError"]

DOCS_BASE = "https://kleber-code.github.io/ushka/guide/guard/#"


class UnsafeValueError(Exception):
    """An `Untrusted` value was about to be used somewhere it could do harm.

    Attributes
    ----------
    code : str
        Stable identifier, e.g. ``"USHKA-G001"``. Safe to match on.
    sink : str
        Where the value was going, e.g. ``"redirect"``.
    source : str
        Where the value came from, e.g. ``"query:next"``.
    risk : str
        The attack this prevents, e.g. ``"open redirect"``.
    fix : str
        A concrete line of code that makes the call safe.
    """

    def __init__(self, *, code: str, sink: str, source: str | None, risk: str, fix: str):
        self.code = code
        self.sink = sink
        # The source embeds client-chosen names (e.g. a query key): keep it
        # printable and short so it cannot forge log lines.
        self.source = "".join(c if c.isprintable() else "?" for c in (source or "unknown"))[:80]
        self.risk = risk
        self.fix = fix
        super().__init__(self._message())

    def _message(self) -> str:
        return (
            f"[{self.code}] untrusted value from {self.source} reached {self.sink} "
            f"({self.risk}). Fix: {self.fix}  Docs: {self.docs}"
        )

    @property
    def docs(self) -> str:
        return DOCS_BASE + self.code.lower()

    def to_dict(self) -> dict[str, Any]:
        """A JSON-ready description, for tools and coding agents."""
        return {
            "error": "unsafe_value",
            "code": self.code,
            "sink": self.sink,
            "source": self.source,
            "risk": self.risk,
            "fix": self.fix,
            "docs": self.docs,
        }
