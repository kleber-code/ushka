"""Safe-by-construction HTML and SQL from t-strings (PEP 750, Python 3.14+).

A t-string keeps the literal parts written by the programmer apart from the
interpolated values, so these helpers can escape (HTML) or bind (SQL) every
value without any taint tracking at all::

    html(t"<p>Hello {name}</p>")          # name is escaped
    sql(t"SELECT * FROM users WHERE id = {user_id}")
    # -> ("SELECT * FROM users WHERE id = :p0", {"p0": user_id})

On older Pythons `TEMPLATES_SUPPORTED` is False and `is_template()` always
returns False; nothing here is imported eagerly by the rest of the package.

Limitation: `html()` escapes for text and *quoted* attribute contexts. It
does not parse the markup, so it cannot stop ``href="{url}"`` from receiving
a ``javascript:`` URL; validate URLs with `safe.url()`.
"""

from __future__ import annotations

from typing import Any

try:
    from string.templatelib import Interpolation, Template

    TEMPLATES_SUPPORTED = True
except ImportError:  # Python < 3.14
    Interpolation = Template = None  # type: ignore[assignment,misc]
    TEMPLATES_SUPPORTED = False

from .safe import html as _escape_html

__all__ = ["TEMPLATES_SUPPORTED", "html", "is_template", "sql"]


def is_template(value: Any) -> bool:
    """True if `value` is a PEP 750 `Template` (the result of a t-string)."""
    return TEMPLATES_SUPPORTED and isinstance(value, Template)


def _require_template(value: Any, fn: str) -> None:
    if not is_template(value):
        raise TypeError(f"{fn}() expects a t-string, e.g. {fn}(t\"...{{value}}...\")")


def _interpolated_value(item: Interpolation) -> Any:
    value = item.value
    if item.conversion == "r":
        value = repr(value)
    elif item.conversion == "s":
        value = str(value)
    elif item.conversion == "a":
        value = ascii(value)
    if item.format_spec:
        value = format(value, item.format_spec)
    return value


def html(template: Any) -> str:
    """Renders a t-string to HTML, escaping every interpolated value.

    Values that already declare themselves as HTML (``__html__``, e.g.
    `markupsafe.Markup` or the result of a nested `html()` call) are kept.
    A nested t-string is rendered recursively.
    """
    _require_template(template, "html")
    out: list[str] = []
    for item in template:
        if isinstance(item, str):
            out.append(item)
            continue
        value = _interpolated_value(item)
        if is_template(value):
            out.append(str(html(value)))
        elif hasattr(value, "__html__"):
            out.append(value.__html__())
        else:
            out.append(str(_escape_html(value if isinstance(value, str) else str(value))))
    rendered = "".join(out)
    try:
        from markupsafe import Markup

        return Markup(rendered)
    except ImportError:  # pragma: no cover
        return rendered


def sql(template: Any, prefix: str = "p") -> tuple[str, dict[str, Any]]:
    """Turns a t-string into SQL with named bind parameters.

    Every interpolation becomes ``:p0``, ``:p1``... and its value goes into
    the returned dict, ready for ``sqlalchemy.text(query).bindparams(**params)``
    or any DB-API driver that accepts the named style. Values are never
    pasted into the SQL text, so they cannot change the query's structure.

    Identifiers (table/column names) cannot be bound; choose them from a
    fixed list with `safe.choice()` and keep them in the literal part.
    """
    _require_template(template, "sql")
    query: list[str] = []
    params: dict[str, Any] = {}
    for item in template:
        if isinstance(item, str):
            query.append(item)
            continue
        name = f"{prefix}{len(params)}"
        params[name] = _interpolated_value(item)
        query.append(f":{name}")
    return "".join(query), params
