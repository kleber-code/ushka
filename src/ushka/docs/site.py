"""The `Docs` site: build, check, search and serve."""

from __future__ import annotations

import hashlib
import logging
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

from .render import MarkdownRenderer

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
        self.pages: dict[str, DocsPage] = {}
        self.sections: list[dict[str, Any]] = []
        self.order: list[str] = []
        self.problems: list[DocsProblem] = []

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

        api_modules = nav.get("api", {}).get("modules", []) if self.api_package else []
        if api_modules:
            from .api import ApiRenderer

            api = ApiRenderer(self.api_package, self.api_path, lambda text: prose.render("api", text).html)
            for module in api_modules:
                try:
                    p = api.page(module)
                except (KeyError, AttributeError) as exc:
                    problems.append(DocsProblem(f"api:{module}", f"cannot document module ({exc})"))
                    continue
                key = f"api:{module}"
                pages[key] = DocsPage(f"api/{module}/", key, module, p.html, p.summary, p.headings, p.text,
                                      nav["api"].get("title", "API reference"))

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
        if data.get("api", {}).get("modules") and self.api_package:
            api = data["api"]
            urls = [f"api/{m}/" for m in api["modules"]]
            self.sections.append({"title": api.get("title", "API reference"), "urls": urls})
            self.order += urls
        listed = set(self.order)
        for page in pages.values():
            if page.url not in listed and not page.source.startswith("api:"):
                problems.append(DocsProblem(page.source, f"not listed in {self.nav_file}"))
        return data

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
            items = [{"title": self.pages[u].title, "url": f"{self.prefix}/{u}", "active": page is not None and u == page.url}
                     for u in section["urls"] if u in self.pages]
            nav.append({"title": section["title"], "items": items,
                        "open": any(i["active"] for i in items) or not section["title"]})
        prev_page = next_page = None
        if page is not None and page.url in self.order:
            i = self.order.index(page.url)
            prev_page = self.pages.get(self.order[i - 1]) if i > 0 else None
            next_page = self.pages.get(self.order[i + 1]) if i + 1 < len(self.order) else None
        path = f"{self.prefix}/{page.url}" if page else f"{self.prefix}/"
        return {
            "docs": self,
            "page": page,
            "nav": nav,
            "prev_page": prev_page,
            "next_page": next_page,
            "canonical": f"{self.base_url}{path}" if self.base_url else None,
            "toc": [h for h in (page.headings if page else []) if h[0] in (2, 3)],
            "edit_link": (self.edit_url + page.source) if (self.edit_url and page and not page.source.startswith("api:")) else None,
        }

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
        problems = self.build(root)
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
