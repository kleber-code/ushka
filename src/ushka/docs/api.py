"""API reference pages generated from docstrings (numpy style) with griffe."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any, Callable

import griffe

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


@dataclass
class ApiPage:
    module: str
    title: str
    html: str
    headings: list[tuple[int, str, str]]  # (level, text, id)
    text: str
    summary: str


def _anchor(path: str) -> str:
    return path.replace(".", "-").lower()


def _ann(value: Any) -> str:
    return "" if value is None else str(value)


def _signature(obj: griffe.Function) -> str:
    parts = []
    for p in obj.parameters:
        prefix = "*" if p.kind and p.kind.value == "variadic positional" else "**" if p.kind and p.kind.value == "variadic keyword" else ""
        text = f"{prefix}{p.name}"
        if p.annotation is not None:
            text += f": {_ann(p.annotation)}"
        if p.default is not None and not prefix:
            text += f" = {p.default}"
        parts.append(text)
    ret = f" -> {_ann(obj.returns)}" if obj.returns is not None else ""
    return f"{obj.name}({', '.join(parts)}){ret}"


def _rst_to_markdown(text: str) -> str:
    """Docstrings use a little reST: ``code`` and "Example::" literal blocks."""
    text = re.sub(r"``([^`]+)``", r"`\1`", text)
    return re.sub(r"::[ \t]*$", ":", text, flags=re.M)


def _plain(text: str) -> str:
    return re.sub(r"`+", "", text)


class ApiRenderer:
    """`markdown` renders docstring prose (so it supports code blocks and links)."""

    def __init__(self, package: str, search_path: str | Path, markdown: Callable[[str], str]):
        self.markdown = lambda text: markdown(_rst_to_markdown(text))
        self.package = griffe.load(
            package, search_paths=[str(search_path)], docstring_parser="numpy", resolve_aliases=False
        )

    def _doc(self, obj: Any) -> str:
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
                rows = []
                items = section.value if isinstance(section.value, list) else [section.value]
                for item in items:
                    name = getattr(item, "name", "") or ""
                    ann = _ann(getattr(item, "annotation", None))
                    desc = self.markdown(getattr(item, "description", "") or "")
                    rows.append(
                        "<tr>"
                        f"<td>{'<code>' + escape(name) + '</code>' if name else ''}</td>"
                        f"<td>{'<code>' + escape(ann) + '</code>' if ann else ''}</td>"
                        f"<td>{desc}</td></tr>"
                    )
                out.append(
                    f'<div class="api-section"><p class="api-section-title">{_SECTION_TITLES[kind]}</p>'
                    f'<table class="api-table"><tbody>{"".join(rows)}</tbody></table></div>'
                )
        return "".join(out)

    def _summary(self, obj: Any) -> str:
        if not obj.docstring:
            return ""
        return _plain(obj.docstring.value.strip().split("\n\n", 1)[0].replace("\n", " "))

    def page(self, module_path: str) -> ApiPage:
        module = self.package
        for part in module_path.split(".")[1:]:
            module = module.members[part]
        html = [self._doc(module)]
        headings: list[tuple[int, str, str]] = []
        text = [self._summary(module)]

        for name, member in module.members.items():
            if name.startswith("_") or member.is_alias:
                continue
            if member.is_class:
                anchor = _anchor(member.path)
                headings.append((2, name, anchor))
                bases = ", ".join(_ann(b) for b in member.bases)
                html.append(f'<section class="api-object"><h2 id="{anchor}"><span class="api-kind">class</span> '
                            f'<code>{escape(name)}{"(" + escape(bases) + ")" if bases else ""}</code></h2>')
                html.append(self._doc(member))
                text.append(self._summary(member))
                for mname, method in member.members.items():
                    if (mname.startswith("_") and mname != "__init__") or not method.is_function or method.is_alias:
                        continue
                    if mname == "__init__" and not method.docstring:
                        continue
                    manchor = _anchor(method.path)
                    headings.append((3, f"{name}.{mname}", manchor))
                    html.append(f'<div class="api-member"><h3 id="{manchor}"><code>{escape(_signature(method))}</code></h3>'
                                f"{self._doc(method)}</div>")
                html.append("</section>")
            elif member.is_function:
                anchor = _anchor(member.path)
                headings.append((2, name, anchor))
                html.append(f'<section class="api-object"><h2 id="{anchor}"><span class="api-kind">def</span> '
                            f"<code>{escape(_signature(member))}</code></h2>{self._doc(member)}</section>")
                text.append(self._summary(member))

        summary = self._summary(module)
        return ApiPage(module_path, module_path, "".join(html), headings, " ".join(t for t in text if t), summary)
