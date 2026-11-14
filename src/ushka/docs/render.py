"""Markdown to HTML for Ushka Docs: headings with stable ids, a table of
contents, links rewritten to page URLs, and server-side syntax highlighting.

Pages are trusted content written by the project, so raw HTML is allowed.
"""

from __future__ import annotations

import posixpath
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable

from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.admon import admon_plugin
from mdit_py_plugins.attrs import attrs_block_plugin, attrs_plugin
from mdit_py_plugins.deflist import deflist_plugin
from mdit_py_plugins.front_matter import front_matter_plugin
from mdit_py_plugins.tasklists import tasklists_plugin
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.util import ClassNotFound

_FORMATTER = HtmlFormatter(nowrap=True)
_LEXER_ALIASES = {"console": "shell-session", "shell": "bash", "sh": "bash", "toml": "toml", "": "text"}


def slugify(text: str) -> str:
    """Heading id compatible with Python-Markdown's toc (and so with old links)."""
    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", text)


def highlight_code(code: str, lang: str, _attrs: str = "") -> str:
    name = _LEXER_ALIASES.get(lang.strip().lower(), lang.strip().lower())
    try:
        lexer = get_lexer_by_name(name)
    except ClassNotFound:
        lexer = TextLexer()
    return highlight(code, lexer, _FORMATTER)


def parse_front_matter(text: str) -> dict[str, object]:
    """A tiny YAML subset: ``key: value`` and ``key:`` followed by ``- item`` lines."""
    data: dict[str, object] = {}
    current: str | None = None
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.startswith((" ", "\t", "-")) and current is not None:
            item = raw.strip().lstrip("-").strip().strip("\"'")
            value = data.setdefault(current, [])
            if isinstance(value, list) and item:
                value.append(item)
            continue
        key, _, value = raw.partition(":")
        current = key.strip()
        data[current] = value.strip().strip("\"'") if value.strip() else []
    return data


@dataclass
class Heading:
    level: int
    text: str
    id: str


@dataclass
class Rendered:
    html: str
    title: str
    meta: dict[str, object]
    headings: list[Heading] = field(default_factory=list)
    text: str = ""
    links: list[tuple[str, str]] = field(default_factory=list)  # (resolved target, anchor)
    description: str = ""


def _inline_text(token: Token) -> str:
    parts = []
    for child in token.children or []:
        if child.type in ("text", "code_inline"):
            parts.append(child.content)
        elif child.type == "softbreak":
            parts.append(" ")
    return "".join(parts).strip()


class MarkdownRenderer:
    """Renders one docs page. `resolve(source, href)` maps a relative href to a URL."""

    def __init__(self, resolve: Callable[[str, str], tuple[str, str | None]] | None = None):
        self.resolve = resolve
        md = MarkdownIt("commonmark", {"html": True, "linkify": False, "typographer": False, "highlight": highlight_code})
        md.enable(["table", "strikethrough"])
        md.use(front_matter_plugin).use(admon_plugin).use(attrs_plugin).use(attrs_block_plugin)
        md.use(deflist_plugin).use(tasklists_plugin)
        self.md = md

    def render(self, source: str, text: str) -> Rendered:
        env: dict = {}
        tokens = self.md.parse(text, env)
        meta: dict[str, object] = {}
        headings: list[Heading] = []
        links: list[tuple[str, str]] = []
        seen: dict[str, int] = {}
        plain: list[str] = []
        description = ""

        for i, tok in enumerate(tokens):
            if tok.type == "front_matter":
                meta = parse_front_matter(tok.content)
            elif tok.type == "heading_open":
                inline = tokens[i + 1]
                label = _inline_text(inline)
                base = tok.attrs.get("id") or slugify(label) or "section"
                count = seen.get(str(base), 0)
                seen[str(base)] = count + 1
                anchor = str(base) if count == 0 else f"{base}_{count}"
                tok.attrSet("id", anchor)
                headings.append(Heading(int(tok.tag[1]), label, anchor))
            elif tok.type == "inline":
                for child in tok.children or []:
                    if child.type in ("link_open", "image"):
                        attr = "href" if child.type == "link_open" else "src"
                        href = str(child.attrs.get(attr, ""))
                        if self.resolve and href and not re.match(r"^([a-z][a-z0-9+.-]*:|//|#|/)", href, re.I):
                            url, target = self.resolve(source, href)
                            child.attrSet(attr, url)
                            if target is not None:
                                path, _, frag = target.partition("#")
                                links.append((path, frag))
                        elif href.startswith("#"):
                            links.append((source, href[1:]))
                if i > 0 and tokens[i - 1].type in ("paragraph_open", "heading_open"):
                    words = _inline_text(tok)
                    plain.append(words)
                    if not description and tokens[i - 1].type == "paragraph_open" and len(words) > 40:
                        description = words
            elif tok.type in ("fence", "code_block"):
                plain.append(tok.content)

        html = self.md.renderer.render(tokens, self.md.options, env)
        h1 = next((h for h in headings if h.level == 1), None)
        title = str(meta.get("title") or (h1.text if h1 else posixpath.basename(source)))
        desc = str(meta.get("description") or description)
        if len(desc) > 160:
            desc = desc[:157].rsplit(" ", 1)[0] + "…"
        return Rendered(html, title, meta, headings, " ".join(plain), links, desc)


__all__ = ["MarkdownRenderer", "Rendered", "Heading", "slugify", "highlight_code"]
