"""Builds a URL from a trusted template and parts that may come from the client.

``build_url("/projects/{id}/", id=pid, query={"tab": "x"})``: the template is yours
and must not be `Untrusted`; every part is percent-encoded, so a value such as
``../x``, ``//evil.example`` or ``a?b=c`` stays inside its segment and cannot change
the host or the path. The result is a plain ``str``, so it passes the guard.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote, urlencode

from ushka.guard import check_redirect

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _plain(value: Any) -> str:
    return str.__str__(value) if isinstance(value, str) else str(value)


def build_url(template: str, params: Mapping[str, Any] | None = None, query: Mapping[str, Any] | None = None) -> str:
    """The URL for `template` with `params` in its ``{name}`` slots and `query` as the query string.

    Raises
    ------
    UnsafeValueError
        If `template` itself is `Untrusted` (only the parts may be client data).
    TypeError
        If a ``{name}`` has no value, or a value is given for a name the template lacks.
    """
    check_redirect(template)
    params = dict(params or {})
    template = _plain(template)
    names = set(_PLACEHOLDER.findall(template))
    missing = names - params.keys()
    extra = params.keys() - names
    if missing:
        raise TypeError(f"URL template {template!r} needs a value for {sorted(missing)}")
    if extra:
        raise TypeError(f"URL template {template!r} has no placeholder for {sorted(extra)}")
    url = _PLACEHOLDER.sub(lambda m: quote(_plain(params[m.group(1)]), safe=""), template)
    if query:
        pairs = [(k, [_plain(v) for v in val] if isinstance(val, (list, tuple)) else _plain(val)) for k, val in query.items()]
        url += ("&" if "?" in url else "?") + urlencode(pairs, doseq=True, quote_via=quote)
    return url
