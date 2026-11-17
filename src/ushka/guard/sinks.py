"""Checks run by dangerous sinks before they use a value.

A framework (or an application) calls these right before doing something
that would be exploitable with attacker-controlled input. They raise
`UnsafeValueError` with a concrete fix when the value is `Untrusted`, and do
nothing otherwise.
"""

from __future__ import annotations

from typing import Any

from .errors import UnsafeValueError
from .untrusted import Untrusted, source_of

__all__ = ["check_html", "check_markup", "check_path", "check_redirect", "check_sql"]


def _raise(value: Any, **kwargs: str) -> None:
    raise UnsafeValueError(source=source_of(value), **kwargs)


def check_html(value: Any, sink: str = "an HTML response body") -> None:
    """Refuses untrusted text that is about to be served as HTML."""
    if isinstance(value, Untrusted):
        _raise(
            value,
            code="USHKA-G001",
            sink=sink,
            risk="cross-site scripting (XSS)",
            fix=(
                "render a template (autoescaped), build the HTML with a t-string "
                't"<p>{value}</p>" on Python 3.14+, or escape it with safe.html(value)'
            ),
        )


def check_markup(value: Any) -> None:
    """Refuses untrusted text that is about to be marked as safe HTML."""
    if isinstance(value, Untrusted):
        _raise(
            value,
            code="USHKA-G002",
            sink="the |safe template filter / Markup()",
            risk="cross-site scripting (XSS)",
            fix="drop |safe and let the template escape it, or sanitise it first",
        )


def check_redirect(value: Any) -> None:
    """Refuses an untrusted redirect target."""
    if isinstance(value, Untrusted):
        _raise(
            value,
            code="USHKA-G003",
            sink="redirect()",
            risk="open redirect / phishing",
            fix=(
                'put the client data in the URL as parts, redirect("/projects/{id}/", id=value) '
                '(parts are percent-encoded), or validate the whole target: '
                'redirect(safe.url(value, allow=["/"], default="/"))'
            ),
        )


def check_path(value: Any) -> None:
    """Refuses an untrusted file-system path."""
    if isinstance(value, Untrusted):
        _raise(
            value,
            code="USHKA-G004",
            sink="a file-system path",
            risk="path traversal",
            fix="safe.path(value, root=UPLOAD_DIR)",
        )


def check_sql(value: Any) -> None:
    """Refuses untrusted text that is about to be executed as raw SQL.

    Call it on the SQL *string*: ``sqlalchemy.text()`` copies its input through
    ``re.sub``, so a `TextClause` no longer carries the mark.
    """
    if isinstance(value, Untrusted):
        _raise(
            value,
            code="USHKA-G005",
            sink="raw SQL",
            risk="SQL injection",
            fix=(
                'use bound parameters: db.text("... WHERE id = :id", id=value), '
                'or a t-string on Python 3.14+: db.execute(t"... WHERE id = {value}")'
            ),
        )
