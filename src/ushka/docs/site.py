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


def page_url(source: str) -> str:
    """``index.md`` → ``""``; ``guide/index.md`` → ``guide/``; ``guide/cli.md`` → ``guide/cli/``."""
    stem = source[:-3]
    if stem == "index":
        return ""
    if stem.endswith("/index"):
        return stem[: -len("index")]
    return stem + "/"


class Docs:
    """A documentation site built from a folder of Markdown files.

    Parameters
    ----------
    directory : str or Path
        The Markdown folder. Relative paths resolve against the app directory.
    url : str
        Where the docs are mounted, e.g. ``"/docs"``.
    title : str
        Site name, used in titles and breadcrumbs.
    base_url : str, optional
        Public origin, e.g. ``"https://example.com"``. Enables canonical URLs,
        absolute Open Graph URLs and ``sitemap.xml``.
    nav : str
        Navigation file inside `directory` (TOML). Without it, pages are listed
        alphabetically.
    api_package : str, optional
        Package to document from docstrings (the modules listed under
        ``[api] modules`` in the nav file).
    api_path : str or Path
        Where `api_package` lives, relative to the app directory (``"src"``).
    logo, og_image : str, optional
        URLs of the header logo and of the social preview image (PNG/JPEG).
    links : list of (label, url), optional
        Extra header links, e.g. ``[("GitHub", "https://github.com/...")]``.
    edit_url : str, optional
        Prefix of a "edit this page" link, e.g.
        ``"https://github.com/me/project/edit/main/docs/"``.
    home_url : str
        Where the header logo links to.
    extra_css : list of str, optional
        Stylesheets loaded after the theme (fonts, brand colours).
    cache_control : str
        ``Cache-Control`` for pages.
    cache : str or Path, optional
        A JSON file where the rendered site is kept. Rendering the pages and the
        API reference costs about a second of CPU, and every server worker does
        it at startup. With a cache, the first start (for example while building
        a container image) renders once and later starts read the file. It is
        keyed by a hash of the Markdown, the documented sources and the renderer,
        so a stale cache is never used. Relative paths resolve against the app
        directory; an unwritable location is ignored.
    """

    def __init__(
        self,
        directory: str | Path,
        *,
        url: str = "/docs",
        title: str = "Documentation",
        base_url: str | None = None,
        nav: str = "nav.toml",
        api_package: str | None = None,
        api_path: str | Path = "src",
        logo: str | None = None,
        og_image: str | None = None,
        links: list[tuple[str, str]] | None = None,
        edit_url: str | None = None,
        home_url: str = "/",
        extra_css: list[str] | None = None,
        cache_control: str = "public, max-age=300, stale-while-revalidate=86400",
        cache: str | Path | None = None,
    ):
        self.directory = Path(directory)
        self.prefix = "/" + url.strip("/")
        self.title = title
        self.base_url = base_url.rstrip("/") if base_url else None
        self.nav_file = nav
        self.api_package = api_package
        self.api_path = Path(api_path)
        self.logo = logo
        self.og_image = og_image
        self.links = links or []
        self.edit_url = edit_url
        self.home_url = home_url
        self.extra_css = extra_css or []
        self.cache_control = cache_control
        self.cache = Path(cache) if cache else None
        self.pages: dict[str, DocsPage] = {}
        self.sections: list[dict[str, Any]] = []
        self.order: list[str] = []
        self.problems: list[DocsProblem] = []
        self.api_groups: list[dict[str, Any]] = []

    # -- building ----------------------------------------------------------------

    def _resolve(self, source: str, href: str) -> tuple[str, str | None]:
        path, _, frag = href.partition("#")
        target = posixpath.normpath(posixpath.join(posixpath.dirname(source), path))
        suffix = f"#{frag}" if frag else ""
        if target.endswith(".md"):
            return f"{self.prefix}/{page_url(target)}{suffix}", f"{target}#{frag}"
        return f"{self.prefix}/{target}{suffix}", target

    def build(self, root: Path | None = None) -> list[DocsProblem]:
        """Renders every page and returns the problems found (empty means all good)."""
        root = (root or self.directory).resolve()
        self.directory = root
        renderer = MarkdownRenderer(self._resolve)
        prose = MarkdownRenderer(self._resolve)
        pages: dict[str, DocsPage] = {}
        anchors: dict[str, set[str]] = {}
        links: list[tuple[str, str, str]] = []
        problems: list[DocsProblem] = []

        for file in sorted(root.rglob("*.md")):
            rel = file.relative_to(root).as_posix()
            if any(part.startswith(("_", ".")) for part in rel.split("/")):
                continue
            out = renderer.render(rel, file.read_text("utf-8"))
            pages[rel] = DocsPage(page_url(rel), rel, out.title, out.html, out.description,
                                  [(h.level, h.text, h.id) for h in out.headings], out.text)
            anchors[rel] = {h.id for h in out.headings}
            links += [(rel, target, frag) for target, frag in out.links]

        nav = self._load_nav(root, pages, problems)

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

    def _load_nav(self, root: Path, pages: dict[str, DocsPage], problems: list[DocsProblem]) -> dict:
        nav_path = root / self.nav_file
        data: dict = {}
        if nav_path.is_file():
            data = tomllib.loads(nav_path.read_text("utf-8"))
        sections = data.get("section") or [{"title": "", "pages": sorted(pages)}]
        self.sections, self.order = [], []
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
        self.api_groups = []
        if data.get("api") and self.api_package:
            self.api_groups = _api_groups(data["api"], problems, self.api_package, self.nav_file)
        if self.api_groups:
            api = data["api"]
            groups = [{"title": g["title"], "slug": slugify(g["title"]),
                       "items": [{"url": f"api/{m}/", "module": m, "label": label}
                                 for m, label in _labels(g["modules"])]} for g in self.api_groups]
            self.sections.append({"title": api.get("title", "API reference"), "urls": ["api/"], "groups": groups})
            self.order += ["api/"] + [i["url"] for g in groups for i in g["items"]]
        listed = set(self.order)
        for page in pages.values():
            if page.url not in listed and not page.source.startswith("api:"):
                problems.append(DocsProblem(page.source, f"not listed in {self.nav_file}"))
        return data

    # -- cache --------------------------------------------------------------------

    def _fingerprint(self, root: Path) -> str:
        """A hash of everything the rendered pages depend on."""
        digest = hashlib.sha256(f"v1|{self.api_package}|{self.nav_file}".encode())
        here = Path(__file__).resolve().parent
        sources = sorted(root.rglob("*.md")) + sorted(here.glob("*.py"))
        if (root / self.nav_file).is_file():
            sources.append(root / self.nav_file)
        if self.api_package:
            sources += sorted((self.api_path / self.api_package.split(".")[0]).rglob("*.py"))
        for file in sources:
            digest.update(file.name.encode())
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
        key = self._fingerprint(root)
        cached = self._load_cache(key)
        if cached is not None:
            self.directory = root
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

    def _context(self, page: DocsPage | None, request: "Request") -> dict[str, Any]:
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

    async def _respond(self, request: "Request", template: str, context: dict[str, Any], status: int = 200) -> Response:
        html = await render(request, template, context)
        etag = 'W/"' + hashlib.sha1(html.encode()).hexdigest()[:20] + '"'
        headers = {"ETag": etag, "Cache-Control": self.cache_control}
        if status == 200 and etag in str(request.headers.get("if-none-match", "")):
            return Response(b"", status_code=304, headers=headers)
        return Response(html, status_code=status, headers=headers, media_type="text/html")

    def mount(self, app: "Ushka") -> list[DocsProblem]:
        """Builds the site and registers its routes on `app`. Returns the problems found."""
        root = self.directory if self.directory.is_absolute() else app.workdir / self.directory
        if not self.api_path.is_absolute():
            self.api_path = app.workdir / self.api_path
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
            target = safe.path(slug, self.directory, default=None)
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
    return Markup(("…" if start else "")) + Markup("").join(out) + Markup("…")
