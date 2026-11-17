"""API reference pages generated from docstrings (numpy style) with griffe.

Each module becomes one page: a summary, an index of its public symbols, then
one section per class or function (signature, parameters table, examples).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

import griffe

from .render import shorten

_SECTION_TITLES = {
    "parameters": "Parameters",
    "other parameters": "Other parameters",
    "raises": "Raises",
    "warns": "Warns",
    "returns": "Returns",
    "yields": "Yields",
    "receives": "Receives",
    "attributes": "Attributes",
}
# Sections whose rows have a name; the others (returns, raises...) list only a type.
_NAMED = {"parameters", "other parameters", "attributes"}
_DECORATORS = ("property", "classmethod", "staticmethod")
_LONG_SIGNATURE = 78


@dataclass
class ApiPage:
    module: str
    title: str
    html: str
    headings: list[tuple[int, str, str]]  # (level, text, id)
    text: str
    summary: str
    symbols: int = 0


def _anchor(path: str) -> str:
    return path.replace(".", "-").lower()


def _ann(value: Any) -> str:
    return "" if value is None else str(value)


def _signature(obj: griffe.Function, *, method: bool = False) -> str:
    """The signature as Python source: one line, or one parameter per line when long."""
    parts = []
    star_done = False
    for p in obj.parameters:
        if method and p.name in ("self", "cls"):
            continue
        kind = p.kind.value if p.kind else ""
        if kind == "variadic positional":
            star_done = True
        elif kind == "keyword-only" and not star_done:
            parts.append("*")
            star_done = True
        prefix = "*" if kind == "variadic positional" else "**" if kind == "variadic keyword" else ""
        text = f"{prefix}{p.name}"
        if p.annotation is not None:
            text += f": {_ann(p.annotation)}"
        if p.default is not None and not prefix:
            text += f" = {p.default}"
        parts.append(text)
    labels = getattr(obj, "labels", set())
    decorators = "".join(f"@{name}\n" for name in _DECORATORS if name in labels)
    ret = f" -> {_ann(obj.returns)}" if obj.returns is not None else ""
    head = ("async def " if "async" in labels else "def ") + obj.name
    line = f"{head}({', '.join(parts)}){ret}"
    if len(line) > _LONG_SIGNATURE and parts:
        line = f"{head}(\n" + "".join(f"    {p},\n" for p in parts) + f"){ret}"
    return decorators + line


def _sig_block(obj: griffe.Function, *, method: bool = False) -> str:
    # Plain text: highlighting every signature would double the size of a page.
    return f'<pre class="api-sig"><code>{escape(_signature(obj, method=method))}</code></pre>'


def _rst_to_markdown(text: str) -> str:
    """Docstrings use a little reST: ``code`` and "Example::" literal blocks."""
    text = re.sub(r"``([^`]+)``", r"`\1`", text)
    return re.sub(r"::[ \t]*$", ":", text, flags=re.MULTILINE)


def _plain(text: str) -> str:
    return re.sub(r"`+", "", text)


def _public_members(obj: Any) -> list[tuple[str, Any]]:
    """Public classes and functions defined in a module (not re-exports)."""
    return [(n, m) for n, m in obj.members.items()
            if not n.startswith("_") and not m.is_alias and (m.is_class or m.is_function)]


def _public_methods(cls: Any) -> list[tuple[str, Any]]:
    out = []
    for name, method in cls.members.items():
        if not method.is_function or method.is_alias:
            continue
        if name.startswith("_") and not (name == "__init__" and method.docstring):
            continue
        out.append((name, method))
    return out


class ApiRenderer:
    """`markdown` renders docstring prose (so it supports code blocks and links).

    `base` is the URL prefix of the API pages (``"/docs/api/"``). With it,
    `Name`, `Class.method`, `function()` and dotted paths in docstrings that
    name a symbol documented in `modules` become links to that symbol.
    """

    def __init__(self, package: str, search_path: str | Path, markdown: Callable[[str], str],
                 modules: list[str] | None = None, base: str = "/api/"):
        self._markdown = markdown
        self.base = base
        self.package = griffe.load(
            package, search_paths=[str(search_path)], docstring_parser="numpy", resolve_aliases=False
        )
        self.links: dict[str, str] = {}
        self._index(modules or [])

    def markdown(self, text: str) -> str:
        return self._link(self._markdown(_rst_to_markdown(text)))

    def module(self, module_path: str) -> Any:
        module = self.package
        for part in module_path.split(".")[1:]:
            module = module.members[part]
        return module

    # -- cross references ----------------------------------------------------------

    def _index(self, modules: list[str]) -> None:
        """Maps the names a docstring may use to the URL of the symbol it means."""
        short: dict[str, set[str]] = {}
        for path in modules:
            try:
                module = self.module(path)
            except (KeyError, AttributeError):
                continue
            for name, member in _public_members(module):
                url = f"{self.base}{path}/#{_anchor(member.path)}"
                self.links[member.path] = url
                short.setdefault(name if member.is_class else f"{name}()", set()).add(url)
                if member.is_class:
                    for mname, method in _public_methods(member):
                        murl = f"{self.base}{path}/#{_anchor(method.path)}"
                        self.links[method.path] = murl
                        self.links[f"{name}.{mname}"] = murl
        for key, urls in short.items():
            if len(urls) == 1:  # an ambiguous short name is better left unlinked
                self.links[key] = next(iter(urls))

    def _link(self, html: str) -> str:
        if not self.links:
            return html
        parts = re.split(r"(<pre\b.*?</pre>|<a\b.*?</a>)", html, flags=re.DOTALL)

        def code(match: re.Match) -> str:
            name = match.group(1)
            url = self.links.get(name)
            return f'<a class="api-ref" href="{url}"><code>{name}</code></a>' if url else match.group(0)

        for i in range(0, len(parts), 2):
            parts[i] = re.sub(r"<code>([\w.]+(?:\(\))?)</code>", code, parts[i])
        return "".join(parts)

    # -- one docstring --------------------------------------------------------------

    def _doc(self, obj: Any, *, method: bool = False) -> str:
        if not obj.docstring:
            return ""
        out = []
        for section in obj.docstring.parsed:
            kind = section.kind.value
            if kind == "text":
                out.append(self.markdown(section.value))
            elif kind == "examples":
                for item_kind, value in section.value:
                    if item_kind.value == "text":
                        out.append(self.markdown(value))
                    else:
                        out.append(self.markdown(f"```python\n{value}\n```"))
            elif kind == "admonition":
                adm = section.value
                out.append(f'<div class="admonition {escape(adm.kind or "note")}"><p class="admonition-title">'
                           f"{escape(section.title or adm.kind or 'Note')}</p>{self.markdown(adm.contents)}</div>")
            elif kind in _SECTION_TITLES:
                items = section.value if isinstance(section.value, list) else [section.value]
                named = kind in _NAMED
                rows = []
                for item in items:
                    name = getattr(item, "name", "") or ""
                    if method and name in ("self", "cls"):
                        continue
                    ann = _ann(getattr(item, "annotation", None))
                    desc = self.markdown(getattr(item, "description", "") or "")
                    cells = f"<td><code>{escape(name)}</code></td>" if named else ""
                    if not named and name and not ann:  # "raises" rows may name the exception
                        ann = name
                    typ = f"<code>{escape(ann)}</code>" if ann else ""
                    rows.append(f"<tr>{cells}<td>{typ}</td><td>{desc}</td></tr>")
                if not rows:
                    continue
                head = ("<th>Name</th>" if named else "") + "<th>Type</th><th>Description</th>"
                out.append(
                    f'<div class="api-section"><p class="api-section-title">{_SECTION_TITLES[kind]}</p>'
                    f'<table class="api-table"><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
                )
        return "".join(out)

    def _summary(self, obj: Any) -> str:
        if not obj.docstring:
            return ""
        return _plain(obj.docstring.value.strip().split("\n\n", 1)[0].replace("\n", " "))

    def _row(self, label: str, summary: str, anchor: str, kind: str = "") -> str:
        badge = f'<span class="api-kind">{kind}</span> ' if kind else ""
        return (f'<tr><td>{badge}<a href="#{anchor}"><code>{escape(label)}</code></a></td>'
                f"<td>{escape(shorten(summary))}</td></tr>")

    # -- one page -------------------------------------------------------------------

    def page(self, module_path: str) -> ApiPage:
        module = self.module(module_path)
        summary = self._summary(module)
        headings: list[tuple[int, str, str]] = []
        text = [summary]
        body: list[str] = []
        index_rows: list[str] = []

        for name, member in _public_members(module):
            anchor = _anchor(member.path)
            headings.append((2, name, anchor))
            text.append(self._summary(member))
            if member.is_class:
                index_rows.append(self._row(name, self._summary(member), anchor, "class"))
                bases = ", ".join(_ann(b) for b in member.bases)
                body.append(f'<section class="api-object"><h2 id="{anchor}"><span class="api-kind">class</span> '
                            f'<code>{escape(name)}</code>{" <small>(" + escape(bases) + ")</small>" if bases else ""}</h2>')
                body.append(self._doc(member))
                methods = _public_methods(member)
                if len(methods) > 3:
                    rows = "".join(self._row(m, self._summary(x), _anchor(x.path)) for m, x in methods)
                    body.append('<div class="api-section"><p class="api-section-title">Methods</p>'
                                f'<table class="api-table api-methods"><tbody>{rows}</tbody></table></div>')
                for mname, method in methods:
                    manchor = _anchor(method.path)
                    headings.append((3, f"{name}.{mname}", manchor))
                    body.append(f'<div class="api-member"><h3 id="{manchor}"><code>{escape(mname)}</code></h3>'
                                f"{_sig_block(method, method=True)}{self._doc(method, method=True)}</div>")
                body.append("</section>")
            else:
                index_rows.append(self._row(f"{name}()", self._summary(member), anchor, "def"))
                body.append(f'<section class="api-object"><h2 id="{anchor}"><span class="api-kind">def</span> '
                            f"<code>{escape(name)}</code></h2>{_sig_block(member)}{self._doc(member)}</section>")

        index = ""
        if len(index_rows) > 1:
            index = ('<div class="api-section api-index"><p class="api-section-title">In this module</p>'
                     f'<table class="api-table"><tbody>{"".join(index_rows)}</tbody></table></div>')
        html = self._doc(module) + index + "".join(body)
        return ApiPage(module_path, module_path, html, headings, " ".join(t for t in text if t), summary,
                       len(index_rows))
