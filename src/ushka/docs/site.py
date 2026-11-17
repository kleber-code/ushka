"""The `Docs` site: build, check, search and serve."""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import posixpath
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from markupsafe import Markup, escape

from ushka.guard import safe
from ushka.http import HttpNotFound, Response, redirect
from ushka.static import file_response
from ushka.templating import render

from .render import MarkdownRenderer, shorten, slugify

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

if TYPE_CHECKING:
    from ushka.core.app import Ushka
    from ushka.http.request import Request

log = logging.getLogger("ushka")

THEME_DIR = Path(__file__).resolve().parent.parent / "internal" / "docs_theme"
# Files in the docs folder that may be served as-is (images, text, fonts...).
ASSET_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".svg", ".ico", ".txt", ".pdf",
                  ".woff2", ".woff", ".css", ".js", ".json", ".xml", ".mp4", ".webm"}


# The options of `Docs(...)` besides path, url, title and api: name -> default.
_OPTIONS: dict[str, Any] = {
    "logo": None, "og_image": None, "links": None, "edit_url": None, "home_url": "/", "extra_css": None,
    "cache_control": "public, max-age=300, stale-while-revalidate=86400", "cache": None, "base_url": None,
    "nav": "nav.toml", "api_package": None, "api_path": None,
}
# What `docs/docs.toml` may set (the constructor wins).
_BRAND = ("title", "logo", "og_image", "links", "edit_url", "base_url", "extra_css")


def _links(value: Any) -> list[tuple[str, str]] | None:
    """``[["GitHub", "https://..."]]`` or ``[{label = "GitHub", url = "https://..."}]``."""
    if not isinstance(value, list):
        return None
    out = []
    for item in value:
        if isinstance(item, dict) and isinstance(item.get("label"), str) and isinstance(item.get("url"), str):
            out.append((item["label"], item["url"]))
        elif isinstance(item, list) and len(item) == 2 and all(isinstance(x, str) for x in item):
            out.append((item[0], item[1]))
        else:
            return None
    return out


def _rel(file: Path, root: Path, here: Path) -> str:
    for base in (root, here):
        with contextlib.suppress(ValueError):
            return file.relative_to(base).as_posix()
    return file.name


@dataclass
class DocsProblem:
    """Something `Docs.build` could not resolve: a broken link, anchor or file."""

    source: str
    message: str

    def __str__(self) -> str:
        return f"{self.source}: {self.message}"


@dataclass
class DocsPage:
    url: str                 # relative to the docs prefix: "", "guide/", "guide/guard/"
    source: str              # "guide/guard.md" or "api:ushka.guard.safe"
    title: str
    html: str
    description: str = ""
    headings: list[tuple[int, str, str]] = field(default_factory=list)
    text: str = ""
    section: str = ""
    group: str = ""          # API pages: the title of the group the module belongs to


_ORDER_PREFIX = re.compile(r"^(\d{1,3})[-_]+")


def _unprefix(name: str) -> str:
    """``01-install`` → ``install`` (the number only orders the menu)."""
    return _ORDER_PREFIX.sub("", name) or name


def _humanize(name: str) -> str:
    """``getting-started`` → ``Getting Started``."""
    return " ".join(w[:1].upper() + w[1:] for w in _unprefix(name).replace("-", " ").replace("_", " ").split())


def page_url(source: str, strip: bool = False) -> str:
    """``index.md`` → ``""``; ``guide/index.md`` → ``guide/``; ``guide/cli.md`` → ``guide/cli/``.

    With `strip`, numeric order prefixes are dropped: ``02-guide/01-cli.md`` → ``guide/cli/``.
    """
    stem = source[:-3]
    if strip:
        stem = "/".join(_unprefix(part) for part in stem.split("/"))
    if stem == "index":
        return ""
    if stem.endswith("/index"):
        return stem[: -len("index")]
    return stem + "/"


class Docs:
    """A documentation site built from a folder of Markdown files: ``app.use(Docs("docs"))``.

    The menu comes from the folders (see the guide); ``nav.toml`` overrides it. An optional
    ``docs.toml`` in the folder sets the brand (`title`, `logo`, `og_image`, `links`,
    `edit_url`, `base_url`, `extra_css`); what you pass here wins over the file.

    Parameters
    ----------
    path : str or Path
        The Markdown folder. Relative paths resolve against the app directory.
    url : str
        Where the docs are mounted, e.g. ``"/docs"``.
    title : str, optional
        Site name, used in titles and breadcrumbs.
    api : str, optional
        A package to document from docstrings, e.g. ``"myproject"``. Found in ``src/``, the
        project folder or the import path; grouped by sub-package.
    **options
        ``logo``, ``og_image`` (URLs), ``links`` (list of (label, url)), ``edit_url`` (prefix of
        an "edit this page" link), ``base_url`` (public origin: canonical URLs, ``sitemap.xml``),
        ``extra_css`` (stylesheets after the theme), ``home_url``, ``cache_control``, ``cache``
        (a JSON file for the rendered site; the default is ``.cache/`` in the app directory,
        ``False`` turns it off; keyed by a hash of the sources, so it is never stale and an
        unwritable location is ignored), ``nav`` (the navigation file name, default
        ``"nav.toml"``), and the older ``api_package`` and ``api_path``.
    """

    def __init__(
        self,
        path: str | Path = "docs",
        *,
        url: str = "/docs",
        title: str | None = None,
        api: str | None = None,
        **options: Any,
    ):
        if "directory" in options:  # the old name of `path`
            path = options.pop("directory")
        unknown = [k for k in options if k not in _OPTIONS]
        if unknown:
            import difflib

            hint = difflib.get_close_matches(unknown[0], _OPTIONS, n=1)
            raise TypeError(
                f"Docs() got an unexpected option {unknown[0]!r}"
                + (f"; did you mean {hint[0]!r}?" if hint else f"; options: {', '.join(_OPTIONS)}")
            )
        o = {**_OPTIONS, **options}
        self._explicit = {k for k in options if k in _BRAND} | ({"title"} if title is not None else set())
        self.directory = Path(path)
        self.prefix = "/" + url.strip("/")
        self.title = title or "Documentation"
        self.base_url = o["base_url"].rstrip("/") if o["base_url"] else None
        self.nav_file = o["nav"]
        self.api_package = o["api_package"] or api
        self._api_wanted = api is not None and not o["api_package"]  # `api=` must be found; the old way is lenient
        self._api_path_set = o["api_path"] is not None
        self.api_path = Path(o["api_path"] or "src")
        self.logo = o["logo"]
        self.og_image = o["og_image"]
        self.links = o["links"] or []
        self.edit_url = o["edit_url"]
        self.home_url = o["home_url"]
        self.extra_css = o["extra_css"] or []
        self.cache_control = o["cache_control"]
        self._cache_auto = o["cache"] is None
        self.cache = Path(o["cache"]) if o["cache"] else None
        self._strip = False
        self._auto = True
        self.pages: dict[str, DocsPage] = {}
        self.sections: list[dict[str, Any]] = []
        self.order: list[str] = []
        self.problems: list[DocsProblem] = []
        self.api_groups: list[dict[str, Any]] = []

    # -- brand (docs.toml) and the API package ------------------------------------

    def _load_brand(self, root: Path) -> list[DocsProblem]:
        """Reads the optional ``docs.toml``; what you passed to the constructor wins."""
        file = root / "docs.toml"
        if not file.is_file():
            return []
        problems: list[DocsProblem] = []
        try:
            data = tomllib.loads(file.read_text("utf-8"))
        except (OSError, ValueError) as exc:
            return [DocsProblem("docs.toml", f"cannot read it ({exc})")]
        for key, value in data.items():
            if key not in _BRAND:
                problems.append(DocsProblem("docs.toml", f"unknown key {key!r}; keys: {', '.join(_BRAND)}"))
                continue
            if key in self._explicit:
                continue
            if key == "links":
                links = _links(value)
                if links is None:
                    problems.append(DocsProblem("docs.toml", "links must be a list of [label, url] pairs"))
                    continue
                value = links
            elif key == "extra_css":
                if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                    problems.append(DocsProblem("docs.toml", "extra_css must be a list of URLs"))
                    continue
            elif not isinstance(value, str):
                problems.append(DocsProblem("docs.toml", f"{key} must be a string"))
                continue
            setattr(self, key, value.rstrip("/") if key == "base_url" else value)
        return problems

    def _find_api(self, *bases: Path) -> None:
        """Finds where the package of ``api=`` lives: ``src/``, the project folder, then the import path."""
        if self._api_path_set or not self.api_package:
            return
        import importlib.util

        top = self.api_package.split(".")[0]
        for base in bases:
            for folder in (base / "src", base):
                if (folder / top / "__init__.py").is_file() or (folder / f"{top}.py").is_file():
                    self.api_path, self._api_path_set = folder, True
                    return
        try:
            spec = importlib.util.find_spec(top)
        except (ImportError, ValueError):
            spec = None
        if spec is not None and spec.origin:
            origin = Path(spec.origin).resolve()
            self.api_path = origin.parent.parent if origin.name == "__init__.py" else origin.parent
            self._api_path_set = True
            return
        if self._api_wanted:
            looked = ", ".join(str(f) for b in bases for f in (b / "src", b))
            raise ValueError(
                f"Docs(api={self.api_package!r}): cannot find the package {top!r} in {looked} or on the "
                "import path; pass api_path= with the folder that contains it"
            )

    # -- building ----------------------------------------------------------------

    def _resolve(self, source: str, href: str) -> tuple[str, str | None]:
        path, _, frag = href.partition("#")
        target = posixpath.normpath(posixpath.join(posixpath.dirname(source), path))
        suffix = f"#{frag}" if frag else ""
        if target.endswith(".md"):
            return f"{self.prefix}/{page_url(target, self._strip)}{suffix}", f"{target}#{frag}"
        return f"{self.prefix}/{target}{suffix}", target

    def build(self, root: Path | None = None) -> list[DocsProblem]:
        """Renders every page and returns the problems found (empty means all good)."""
        root = (root or self.directory).resolve()
        self.directory = root
        self._auto = not (root / self.nav_file).is_file()
        self._strip = self._auto
        self._find_api(root.parent, Path.cwd())
        renderer = MarkdownRenderer(self._resolve)
        prose = MarkdownRenderer(self._resolve)
        pages: dict[str, DocsPage] = {}
        anchors: dict[str, set[str]] = {}
        links: list[tuple[str, str, str]] = []
        problems: list[DocsProblem] = self._load_brand(root)
        meta: dict[str, dict] = {}

        for file in sorted(root.rglob("*.md")):
            rel = file.relative_to(root).as_posix()
            if any(part.startswith(("_", ".")) for part in rel.split("/")):
                continue
            out = renderer.render(rel, file.read_text("utf-8"))
            title = out.title
            if self._auto and not out.meta.get("title") and not any(h.level == 1 for h in out.headings):
                title = _humanize(posixpath.basename(rel)[:-3])
            url = page_url(rel, self._strip)
            if any(p.url == url for p in pages.values()):
                problems.append(DocsProblem(rel, f"same URL as another page ({url or '/'})"))
            pages[rel] = DocsPage(url, rel, title, out.html, out.description,
                                  [(h.level, h.text, h.id) for h in out.headings], out.text)
            meta[rel] = out.meta
            anchors[rel] = {h.id for h in out.headings}
            links += [(rel, target, frag) for target, frag in out.links]

        nav = self._load_nav(root, pages, meta, problems)

        groups = self.api_groups if self.api_package else []
        if groups:
            from .api import ApiRenderer

            api_cfg = nav["api"]
            api_title = api_cfg.get("title", "API reference")
            modules = [m for g in groups for m in g["modules"]]
            api = ApiRenderer(self.api_package, self.api_path, lambda text: prose.render("api", text).html,
                              modules, f"{self.prefix}/api/")
            summaries: dict[str, str] = {}
            for group in groups:
                for module in group["modules"]:
                    try:
                        p = api.page(module)
                    except (KeyError, AttributeError) as exc:
                        problems.append(DocsProblem(f"api:{module}", f"cannot document module ({exc})"))
                        continue
                    key = f"api:{module}"
                    summaries[module] = p.summary
                    pages[key] = DocsPage(f"api/{module}/", key, module, p.html, p.summary, p.headings, p.text,
                                          api_title, group["title"])
            index = self._api_index(groups, summaries, api_cfg, api_title)
            pages["api:index"] = index
            # a module that failed to build must not stay in the sidebar
            for section in self.sections:
                for group in section.get("groups", []):
                    group["items"] = [i for i in group["items"] if f"api:{i['module']}" in pages]
            self.order = [u for u in self.order if u in {p.url for p in pages.values()}]

        for source, target, frag in links:
            if target.endswith(".md"):
                if target not in pages:
                    problems.append(DocsProblem(source, f"link to missing page {target}"))
                elif frag and frag not in anchors.get(target, set()):
                    problems.append(DocsProblem(source, f"link to missing anchor {target}#{frag}"))
            elif not (root / target).is_file():
                problems.append(DocsProblem(source, f"link to missing file {target}"))

        self.pages = {p.url: p for p in pages.values()}
        self.problems = problems
        return problems

    def _api_index(self, groups: list[dict[str, Any]], summaries: dict[str, str], cfg: dict, title: str) -> DocsPage:
        """The ``api/`` page: every group with its modules and what they are for."""
        html = [f"<p>{escape(cfg['description'])}</p>"] if cfg.get("description") else []
        headings, text = [], [cfg.get("description", "")]
        for group in groups:
            slug = slugify(group["title"])
            headings.append((2, group["title"], slug))
            html.append(f'<h2 id="{slug}">{escape(group["title"])}</h2>')
            if group.get("description"):
                html.append(f"<p>{escape(group['description'])}</p>")
                text.append(group["description"])
            rows = []
            for module, label in _labels(group["modules"]):
                if module not in summaries:
                    continue
                rows.append(f'<tr><td><a href="{self.prefix}/api/{module}/"><code>{escape(module)}</code></a></td>'
                            f"<td>{escape(shorten(summaries[module]))}</td></tr>")
                text.append(f"{module} {summaries[module]}")
            html.append(f'<table class="api-table api-modules"><tbody>{"".join(rows)}</tbody></table>')
        return DocsPage("api/", "api:index", title, "".join(html), cfg.get("description", ""), headings,
                        " ".join(t for t in text if t), title)

    def _load_nav(self, root: Path, pages: dict[str, DocsPage], meta: dict[str, dict],
                  problems: list[DocsProblem]) -> dict:
        nav_path = root / self.nav_file
        data: dict = {}
        self.sections, self.order = [], []
        if nav_path.is_file():
            data = tomllib.loads(nav_path.read_text("utf-8"))
            self._nav_from_file(data, pages, problems)
        else:
            self._nav_from_folders(pages, meta, problems)
        api = data.get("api") or {}
        self.api_groups = []
        if self.api_package:
            if api:
                self.api_groups = _api_groups(api, problems, self.api_package, self.nav_file)
            else:
                self.api_groups = self._auto_api_groups()
        if self.api_groups:
            groups = [{"title": g["title"], "slug": slugify(g["title"]),
                       "items": [{"url": f"api/{m}/", "module": m, "label": label}
                                 for m, label in _labels(g["modules"])]} for g in self.api_groups]
            self.sections.append({"title": api.get("title", "API reference"), "urls": ["api/"], "groups": groups})
            self.order += ["api/"] + [i["url"] for g in groups for i in g["items"]]
        if not self._auto:
            listed = set(self.order)
            for page in pages.values():
                if page.url not in listed and not page.source.startswith("api:"):
                    problems.append(DocsProblem(page.source, f"not listed in {self.nav_file}"))
        return {**data, "api": api}

    def _nav_from_file(self, data: dict, pages: dict[str, DocsPage], problems: list[DocsProblem]) -> None:
        sections = data.get("section") or [{"title": "", "pages": sorted(pages)}]
        for section in sections:
            items = []
            for source in section.get("pages", []):
                page = pages.get(source)
                if page is None:
                    problems.append(DocsProblem(self.nav_file, f"lists missing page {source}"))
                    continue
                page.section = section.get("title", "")
                items.append(page.url)
                self.order.append(page.url)
            self.sections.append({"title": section.get("title", ""), "urls": items})

    def _nav_from_folders(self, pages: dict[str, DocsPage], meta: dict[str, dict],
                          problems: list[DocsProblem]) -> None:
        """The menu from the structure: a folder is a section, ``index.md`` opens it, and the order
        comes from ``order:`` in the front matter, a numeric prefix in the name, or the alphabet."""

        def number(source: str, name: str) -> float:
            raw = meta.get(source, {}).get("order")
            if raw not in (None, "", []):
                try:
                    return float(str(raw))
                except ValueError:
                    problems.append(DocsProblem(source, f"order must be a number, got {raw!r}"))
            m = _ORDER_PREFIX.match(name)
            return float(m.group(1)) if m else float("inf")

        folders: dict[str, list[str]] = {}
        for source in pages:
            folders.setdefault(posixpath.dirname(source), []).append(source)

        def page_key(source: str):
            name = posixpath.basename(source)[:-3]
            return (name != "index", number(source, name), _unprefix(name).lower())

        def folder_key(folder: str):
            if not folder:
                return ((0, 0.0, ""),)
            parts, key = folder.split("/"), []
            for i, part in enumerate(parts):
                key.append((1, number("/".join(parts[: i + 1] + ["index.md"]), part), _unprefix(part).lower()))
            return tuple(key)

        for folder in sorted(folders, key=folder_key):
            sources = sorted(folders[folder], key=page_key)
            if not folder:
                title = ""
            else:
                index = pages.get(f"{folder}/index.md")
                title = index.title if index else _humanize(posixpath.basename(folder))
            for source in sources:
                pages[source].section = title
            self.sections.append({"title": title, "urls": [pages[s].url for s in sources]})
            self.order += [pages[s].url for s in sources]

    def _auto_api_groups(self) -> list[dict[str, Any]]:
        """One group per sub-package of ``api=``; its public modules (no ``_name``) are the pages."""
        top = self.api_package.split(".")[0]  # type: ignore[union-attr]
        base = self.api_path / top
        if not base.is_dir():
            return []
        groups: dict[str, list[str]] = {}

        def visible(path: Path) -> bool:
            return not any(part.startswith("_") or part in ("tests", "test") for part in path.parts)

        for file in sorted(base.rglob("*.py")):
            rel = file.relative_to(base)
            if file.name == "__init__.py" or not visible(rel):
                continue
            parts = [top, *rel.with_suffix("").parts]
            groups.setdefault(parts[1] if len(parts) > 2 else "general", []).append(".".join(parts))
        for pkg in sorted(p for p in base.iterdir() if (p / "__init__.py").is_file() and visible(p.relative_to(base))):
            if pkg.name not in groups:  # a package with no modules of its own is one page
                groups[pkg.name] = [f"{top}.{pkg.name}"]
        scope = self.api_package
        result = []
        for name, mods in sorted(groups.items(), key=lambda kv: (kv[0] == "general", kv[0])):
            mods = [m for m in mods if m == scope or m.startswith(scope + ".")]  # type: ignore[operator]
            if mods:
                result.append({"title": _humanize(name), "description": "", "modules": mods})
        return result

    # -- cache --------------------------------------------------------------------

    def _fingerprint(self, root: Path) -> str:
        """A hash of everything the rendered pages depend on."""
        digest = hashlib.sha256(f"v2|{self.api_package}|{self.nav_file}".encode())
        here = Path(__file__).resolve().parent
        sources = sorted(root.rglob("*.md")) + sorted(here.glob("*.py"))
        sources += [f for f in (root / self.nav_file, root / "docs.toml") if f.is_file()]
        if self.api_package:
            package = self.api_path / self.api_package.split(".")[0]
            sources += sorted(package.rglob("*.py")) + [package.with_suffix(".py")] * package.with_suffix(".py").is_file()
        for file in sources:
            digest.update(_rel(file, root, here).encode())
            digest.update(file.read_bytes())
        return digest.hexdigest()

    def _load_cache(self, key: str) -> list[DocsProblem] | None:
        try:
            data = json.loads(self.cache.read_text("utf-8"))  # type: ignore[union-attr]
            if data["key"] != key:
                return None
            self.pages = {
                p["url"]: DocsPage(**{**p, "headings": [tuple(h) for h in p["headings"]]}) for p in data["pages"]
            }
            self.sections, self.order = data["sections"], data["order"]
            self.problems = [DocsProblem(**x) for x in data["problems"]]
        except (OSError, ValueError, KeyError, TypeError):
            return None
        return self.problems

    def _save_cache(self, key: str) -> None:
        data = {
            "key": key,
            "pages": [vars(p) for p in self.pages.values()],
            "sections": self.sections,
            "order": self.order,
            "problems": [vars(p) for p in self.problems],
        }
        tmp = self.cache.with_name(f"{self.cache.name}.{os.getpid()}.tmp")  # type: ignore[union-attr]
        try:
            self.cache.parent.mkdir(parents=True, exist_ok=True)  # type: ignore[union-attr]
            tmp.write_text(json.dumps(data), "utf-8")
            os.replace(tmp, self.cache)  # atomic: a worker never reads half a file
        except OSError:
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)

    def build_cached(self, root: Path | None = None) -> list[DocsProblem]:
        """`build`, reading the rendered site from `cache` when it is still valid."""
        if self.cache is None:
            return self.build(root)
        root = (root or self.directory).resolve()
        self._auto = not (root / self.nav_file).is_file()
        self._strip = self._auto
        self._find_api(root.parent, Path.cwd())
        key = self._fingerprint(root)
        cached = self._load_cache(key)
        if cached is not None:
            self.directory = root
            self._load_brand(root)
            return cached
        problems = self.build(root)
        self._save_cache(key)
        return problems

    # -- search --------------------------------------------------------------------

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Pages matching every term of `query`, best first, with a highlighted snippet."""
        terms = [t for t in safe.plain(str(query)).lower().split() if len(t) >= 2][:8]
        if not terms:
            return []
        results = []
        for page in self.pages.values():
            title, body = page.title.lower(), page.text.lower()
            heads = " ".join(h[1] for h in page.headings).lower()
            if not all(t in title or t in heads or t in body for t in terms):
                continue
            score = sum(10 * title.count(t) + 4 * heads.count(t) + min(body.count(t), 10) for t in terms)
            anchor = next((h[2] for h in page.headings if h[0] > 1 and any(t in h[1].lower() for t in terms)), "")
            results.append({"page": page, "score": score, "anchor": anchor, "snippet": _snippet(page.text, terms)})
        results.sort(key=lambda r: -r["score"])
        return results[:limit]

    # -- serving --------------------------------------------------------------------

    def _context(self, page: DocsPage | None, request: Request) -> dict[str, Any]:
        nav = []
        for section in self.sections:
            items = [{"title": "Overview" if u == "api/" else self.pages[u].title, "url": f"{self.prefix}/{u}", "active": page is not None and u == page.url}
                     for u in section["urls"] if u in self.pages]
            groups = []
            for group in section.get("groups", []):
                entries = [{"title": i["label"], "url": f"{self.prefix}/{i['url']}", "active": page is not None and i["url"] == page.url}
                           for i in group["items"] if i["url"] in self.pages]
                groups.append({"title": group["title"], "items": entries, "open": any(e["active"] for e in entries)})
            active = any(i["active"] for i in items) or any(g["open"] for g in groups)
            # Only the section you are in is open; short or untitled ones stay open.
            nav.append({"title": section["title"], "items": items, "groups": groups,
                        "open": active or not section["title"] or (len(items) <= 5 and not groups)})
        prev_page = next_page = None
        if page is not None and page.url in self.order:
            i = self.order.index(page.url)
            prev_page = self.pages.get(self.order[i - 1]) if i > 0 else None
            next_page = self.pages.get(self.order[i + 1]) if i + 1 < len(self.order) else None
        path = f"{self.prefix}/{page.url}" if page else f"{self.prefix}/"
        crumbs = self._crumbs(page)
        trail = [{"@type": "ListItem", "position": n, "name": label,
                  "item": (self.base_url or "") + (url or path)} for n, (label, url) in enumerate(crumbs, 1)]
        return {
            "crumbs": crumbs,
            "crumb_ld": {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": trail},
            "docs": self,
            "page": page,
            "nav": nav,
            "prev_page": prev_page,
            "next_page": next_page,
            "canonical": f"{self.base_url}{path}" if self.base_url else None,
            "toc": [h for h in (page.headings if page else []) if h[0] in (2, 3)],
            "is_api": bool(page and page.source.startswith("api:")),
            "edit_link": (self.edit_url + page.source) if (self.edit_url and page and not page.source.startswith("api:")) else None,
        }

    def _crumbs(self, page: DocsPage | None) -> list[tuple[str, str | None]]:
        """Breadcrumb trail as (label, url); the last item is the page itself (no url)."""
        if page is None or not page.url:
            return []
        trail: list[tuple[str, str | None]] = [(self.title, f"{self.prefix}/")]
        if page.source.startswith("api:"):
            trail.append((page.section, None if page.source == "api:index" else f"{self.prefix}/api/"))
            if page.group and page.source != "api:index":
                trail.append((page.group, f"{self.prefix}/api/#{slugify(page.group)}"))
        elif page.section:
            trail.append((page.section, None))
        if page.source != "api:index":
            trail.append((page.title, None))
        return trail

    async def _respond(self, request: Request, template: str, context: dict[str, Any], status: int = 200) -> Response:
        html = await render(request, template, context)
        etag = 'W/"' + hashlib.sha1(html.encode()).hexdigest()[:20] + '"'
        headers = {"ETag": etag, "Cache-Control": self.cache_control}
        if status == 200 and etag in str(request.headers.get("if-none-match", "")):
            return Response(b"", status_code=304, headers=headers)
        return Response(html, status_code=status, headers=headers, media_type="text/html")

    def install(self, app: Ushka) -> None:
        """``app.use(Docs("docs"))``: the same as `mount`."""
        self.mount(app)

    def mount(self, app: Ushka) -> list[DocsProblem]:
        """Builds the site and registers its routes on `app`. Returns the problems found."""
        root = self.directory if self.directory.is_absolute() else app.workdir / self.directory
        if self._api_path_set and not self.api_path.is_absolute():
            self.api_path = app.workdir / self.api_path
        elif self.api_package and not self._api_path_set:
            self._find_api(app.workdir)
            if not self._api_path_set:  # the old way: nothing found, `src/` as before
                self.api_path = app.workdir / self.api_path
        if self.cache is None and self._cache_auto:
            digest = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:10]
            self.cache = app.workdir / ".cache" / f"ushka-docs-{digest}.json"
        problems = self.build_cached(root)
        for problem in problems:
            log.warning("docs: %s", problem)

        prefix = self.prefix

        async def index(request):
            if not request.path.endswith("/"):
                return redirect(request.path + "/", status_code=301)
            page = self.pages.get("")
            if page is None:
                raise HttpNotFound()
            return await self._respond(request, "docs/page.html", self._context(page, request))

        async def page_view(request, slug: str):
            key = safe.plain(slug).strip("/") + "/"
            page = self.pages.get(key)
            if page is not None:
                if not request.path.endswith("/"):
                    return redirect(request.path + "/", status_code=301)
                return await self._respond(request, "docs/page.html", self._context(page, request))
            hidden = any(part.startswith(("_", ".")) for part in slug.split("/"))
            target = None if hidden else safe.path(slug, self.directory, default=None)
            if target is not None and target.is_file() and target.suffix.lower() in ASSET_SUFFIXES:
                return file_response(target, request, "public, max-age=86400, stale-while-revalidate=604800")
            raise HttpNotFound()

        async def search_view(request):
            query = request.query.get("q", "")
            if isinstance(query, list):
                query = query[0] if query else ""
            query = query[:100]
            context = self._context(None, request)
            context.update({"query": query, "results": self.search(query) if query else []})
            response = await self._respond(request, "docs/search.html", context)
            response.headers["X-Robots-Tag"] = "noindex"
            return response

        async def sitemap(request):
            if not self.base_url:
                raise HttpNotFound()
            urls = "".join(f"<url><loc>{escape(self.base_url + prefix + '/' + u)}</loc></url>" for u in self.order)
            xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
            return Response(xml, media_type="application/xml", headers={"Cache-Control": self.cache_control})

        app.router.add_route("GET", prefix, index)
        app.router.add_route("GET", prefix + "/search", search_view)
        app.router.add_route("GET", prefix + "/sitemap.xml", sitemap)
        app.mount_static(prefix + "/_theme", THEME_DIR, cache_control="public, max-age=86400, stale-while-revalidate=604800")
        app.router.add_route("GET", prefix + "/[path:slug]", page_view)
        return problems


def _api_groups(api: dict, problems: list[DocsProblem], package: str, nav_file: str) -> list[dict[str, Any]]:
    """The API groups of the nav file. ``[[api.group]]`` tables win; a plain
    ``modules = [...]`` list is grouped by sub-package (``ushka.http.*`` → "http")."""
    groups: list[dict[str, Any]] = []
    for raw in api.get("group", []):
        title = str(raw.get("title", "")).strip()
        modules = [str(m) for m in raw.get("modules", [])]
        if not title or not modules:
            problems.append(DocsProblem(nav_file, f"api group {title or '(untitled)'!r} needs a title and modules"))
            continue
        groups.append({"title": title, "description": str(raw.get("description", "")), "modules": modules})
    if not groups and api.get("modules"):
        by_name: dict[str, list[str]] = {}
        for module in api["modules"]:
            parts = str(module).split(".")
            by_name.setdefault(parts[1] if len(parts) > 2 else "general", []).append(str(module))
        groups = [{"title": name.replace("_", " ").capitalize(), "description": "", "modules": mods}
                  for name, mods in by_name.items()]
    seen: set[str] = set()
    for group in groups:
        unique = []
        for module in group["modules"]:
            if module in seen:
                problems.append(DocsProblem(nav_file, f"api module {module} is listed twice"))
            elif module != package and not module.startswith(package + "."):
                problems.append(DocsProblem(nav_file, f"api module {module} is not in package {package}"))
            else:
                unique.append(module)
            seen.add(module)
        group["modules"] = unique
    return [g for g in groups if g["modules"]]


def _labels(modules: list[str]) -> list[tuple[str, str]]:
    """Sidebar labels: the module path without what the whole group shares."""
    if len(modules) == 1:
        return [(modules[0], modules[0].rsplit(".", 1)[-1])]
    split = [m.split(".") for m in modules]
    common = 0
    while all(len(p) > common + 1 and p[common] == split[0][common] for p in split):
        common += 1
    return [(m, ".".join(p[common:])) for m, p in zip(modules, split)]


def _snippet(text: str, terms: list[str], radius: int = 90) -> Markup:
    lower = text.lower()
    hits = [lower.find(t) for t in terms if lower.find(t) >= 0]
    start = max(0, (min(hits) if hits else 0) - radius)
    chunk = text[start : start + radius * 2 + 40]
    pattern = re.compile("|".join(re.escape(t) for t in terms), re.IGNORECASE)
    out, last = [], 0
    for m in pattern.finditer(chunk):
        out.append(escape(chunk[last : m.start()]))
        out.append(Markup("<mark>") + escape(m.group(0)) + Markup("</mark>"))
        last = m.end()
    out.append(escape(chunk[last:]))
    return Markup("…" if start else "") + Markup("").join(out) + Markup("…")
