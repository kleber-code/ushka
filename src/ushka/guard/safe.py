"""Explicit sanitisers: the only sanctioned way to turn `Untrusted` into trusted.

Each function validates or transforms its input for one specific use and
returns a plain, trusted value. When the input cannot be made safe they raise
`RejectedValueError` (a `ValueError`), or return `default` when one is given.
A web framework should answer a `RejectedValueError` with ``400 Bad Request``:
it means the client sent something unacceptable, not that the server broke.

Usage::

    from ushka.guard import safe

    return redirect(safe.url(request.query.get("next"), allow=["/"], default="/"))
"""

from __future__ import annotations

import html as _html
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import urlsplit

__all__ = ["RejectedValueError", "choice", "html", "integer", "path", "plain", "trust", "url"]

T = TypeVar("T")
_MISSING: Any = object()

try:  # MarkupSafe ships with Jinja2; stay usable without it.
    from markupsafe import Markup as _Markup
    from markupsafe import escape as _escape
except ImportError:  # pragma: no cover - exercised only without markupsafe
    _Markup = None
    _escape = None


class RejectedValueError(ValueError):
    """The client-supplied value could not be made safe for its intended use."""

    status_code = 400

    def __init__(self, message: str, *, value: Any = None):
        self.value = value
        super().__init__(message)


def plain(value: str) -> str:
    """Returns an exact ``str`` copy of `value`, dropping any taint mark.

    Internal building block; application code should use a validating
    sanitiser or `trust()` so that the reason is visible in review.
    """
    return "".join((value,)) if type(value) is not str else value  # noqa: FLY002 - an f-string would call Untrusted.__format__ and keep the mark


def _fail(message: str, value: Any, default: Any) -> Any:
    if default is not _MISSING:
        return default
    raise RejectedValueError(message, value=value)


# -- HTML ----------------------------------------------------------------------


def html(value: Any) -> str:
    """Escapes `value` for HTML text and quoted attributes.

    Returns a `markupsafe.Markup` when MarkupSafe is installed, so Jinja2 and
    other HTML builders will not escape it a second time.
    """
    if _escape is not None:
        return _escape(plain(value) if isinstance(value, str) else value)
    return _html.escape(plain(value) if isinstance(value, str) else str(value))


# -- URLs ----------------------------------------------------------------------


def url(
    value: Any,
    *,
    allow: Sequence[str] = ("/",),
    default: Any = _MISSING,
) -> str:
    """Validates a redirect target.

    Parameters
    ----------
    value : str
        The candidate URL, usually from ``?next=``.
    allow : sequence of str
        Accepted targets. ``"/"`` accepts same-site paths (``/account``),
        which is the safe default. An origin such as
        ``"https://pay.example.com"`` accepts absolute URLs on exactly that
        scheme and host.
    default : str, optional
        Returned instead of raising when `value` is rejected or missing.

    Raises
    ------
    RejectedValueError
        If the URL is not allowed and no `default` was given.
    """
    if not isinstance(value, str) or not value:
        return _fail("redirect target is missing", value, default)

    candidate = plain(value)
    # Control characters and backslashes are interpreted inconsistently by
    # browsers ("/\\evil.com" goes off-site in several of them).
    if any(ord(c) < 0x20 or c == "\x7f" or c == "\\" for c in candidate):
        return _fail("redirect target contains forbidden characters", value, default)

    parts = urlsplit(candidate)

    if not parts.scheme and not parts.netloc:
        # Relative reference. Only absolute paths are accepted: "//host" is
        # protocol-relative (off-site) and "foo" depends on the current URL.
        if "/" in allow and candidate.startswith("/") and not candidate.startswith("//"):
            return candidate
        return _fail("relative redirect target is not an absolute path", value, default)

    origin = f"{parts.scheme.lower()}://{(parts.hostname or '').lower()}"
    if parts.port:
        origin += f":{parts.port}"
    allowed_origins = {a.rstrip("/").lower() for a in allow if "://" in a}
    if parts.scheme.lower() in ("http", "https") and origin in allowed_origins and not parts.username:
        return candidate
    return _fail(f"redirect to {origin!r} is not in the allow list", value, default)


# -- filesystem ----------------------------------------------------------------


def path(value: Any, root: str | Path, *, default: Any = _MISSING) -> Path:
    """Resolves `value` inside `root`, rejecting anything that escapes it.

    Symlinks are resolved before the check, so a link pointing outside `root`
    is rejected too. The returned path may not exist.
    """
    if not isinstance(value, str) or not value or "\x00" in value:
        return _fail("invalid file name", value, default)
    root_path = Path(root).resolve()
    try:
        target = (root_path / plain(value)).resolve()
    except (OSError, ValueError):
        return _fail("invalid file name", value, default)
    if not target.is_relative_to(root_path):
        return _fail("path escapes its root directory", value, default)
    return target


# -- scalars -------------------------------------------------------------------


def integer(
    value: Any,
    *,
    min: int | None = None,
    max: int | None = None,
    default: Any = _MISSING,
) -> int:
    """Parses a base-10 integer, optionally bounded. ``bool`` is rejected."""
    if isinstance(value, bool):
        return _fail("expected an integer", value, default)
    try:
        number = int(plain(value).strip()) if isinstance(value, str) else int(value)
    except (TypeError, ValueError):
        return _fail("expected an integer", value, default)
    if (min is not None and number < min) or (max is not None and number > max):
        return _fail("integer out of range", value, default)
    return number


def choice(value: Any, options: Iterable[T], *, default: Any = _MISSING) -> T:
    """Returns the element of `options` equal to `value`.

    The returned object is *your* option, not the client's string, so it is
    trusted by construction. Ideal for sort orders, column names, enums.
    """
    for option in options:
        if option == value:
            return option
    return _fail("value is not one of the accepted options", value, default)


# -- escape hatch --------------------------------------------------------------


def trust(value: str, *, reason: str) -> str:
    """Marks `value` as trusted without validating it.

    `reason` is mandatory and should say why this is safe, so the decision is
    visible in code review and easy to audit with ``grep "trust("``.
    """
    if not reason or not reason.strip():
        raise ValueError("safe.trust() needs a non-empty reason")
    return plain(value) if isinstance(value, str) else value
