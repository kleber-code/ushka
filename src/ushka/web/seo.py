"""SEO that ships ready: meta tags for your templates, ``robots.txt`` and ``sitemap.xml``.

Everything is configured in ``[seo]`` of ``ushka.toml`` (or ``USHKA_SEO_*``).
Put ``{{ seo() }}`` inside ``<head>`` instead of ``<title>`` and every page gets
a title, description, canonical URL, robots rule, Open Graph and Twitter tags
and JSON-LD. A page adjusts what it needs, in the template::

    {{ seo(title="About us", description="Who we are", image="/static/team.png") }}

or from the handler, with a ``page_seo`` dict in the template context::

    return await render(request, "post.html", {"page_seo": {"title": post.title, "type": "article"}})

Absolute URLs need the public address: set ``[seo] url``. Without it the origin
is taken from the request only in debug or when ``[security] allowed_hosts`` is
set, because a ``Host`` header nobody checked must not end up in a canonical
link or a sitemap.

Nothing is injected behind your back: the tags appear where you call
``seo()``. ``/robots.txt`` and ``/sitemap.xml`` are served unless you define
those routes yourself.
"""

from __future__ import annotations

import fnmatch
import inspect
import json
import posixpath
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from jinja2 import pass_context
from markupsafe import Markup, escape

from ushka.http.exceptions import HttpNotFound
from ushka.http.response import Response
from ushka.templating.engine import engine
from ushka.web.i18n import get_locale

if TYPE_CHECKING:
    from ushka.core.app import Ushka
    from ushka.http.request import Request

#: Never listed in a sitemap, whatever the configuration says.
ALWAYS_EXCLUDED = ("/mcp", "/openapi.json", "/healthz", "/health", "/robots.txt", "/sitemap.xml")
#: Per-page keys that ``seo()`` (or a ``page_seo`` dict in the context) accepts.
PAGE_KEYS = (
    "title", "description", "image", "image_alt", "type", "noindex", "robots", "canonical",
    "published", "modified", "author", "alternates", "jsonld", "path", "locale",
)


def _s(value: Any) -> str:
    """A plain ``str`` (client data may arrive as `Untrusted`)."""
    if value is None:
        return ""
    return str.__str__(value) if isinstance(value, str) else str(value)


def _list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = value.split(",")
    return [str(v).strip() for v in (value or []) if str(v).strip()]


def safe_url(value: str) -> str:
    """`value` when it is a path or an http(s) URL, else an empty string."""
    value = _s(value).strip()
    if value.startswith("/") and not value.startswith("//"):
        return value
    parts = urlsplit(value)
    return value if parts.scheme in ("http", "https") and parts.netloc else ""


def origin_of(request: Request | None, config: Any) -> str | None:
    """The public origin: ``[seo] url``, else the request's when that is safe."""
    configured = _s(config.get("seo_url")).strip().rstrip("/")
    if configured:
        return configured if safe_url(configured) else None
    if request is None or not (config.get("app_debug") or _list(config.get("security_allowed_hosts"))):
        return None
    host = str(request.host)
    scheme = request.scheme
    return f"{scheme}://{host}" if host and scheme in ("http", "https") else None


def _absolute(origin: str | None, value: str) -> str:
    value = safe_url(value)
    if value.startswith("/") and origin:
        return origin + value
    return value


def _excluded(path: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if fnmatch.fnmatchcase(path, pattern):
            return True
        if pattern.endswith("/*") and path == pattern[:-2]:
            return True
    return False


def _json_ld(data: Any) -> Markup:
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    text = text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return Markup('<script type="application/ld+json">') + Markup(text) + Markup("</script>")


def _meta(attr: str, name: str, content: str) -> Markup:
    return Markup('<meta {}="{}" content="{}">').format(attr, name, content) if content else Markup("")


def page_title(config: Any, title: str = "") -> str:
    """The ``<title>``: the page title through ``title_template``, or the site name."""
    site = _s(config.get("seo_site_name") or config.get("app_name") or "")
    title = _s(title).strip()
    if not title:
        return _s(config.get("seo_title")).strip() or site
    if not site or title == site:
        return title
    template = _s(config.get("seo_title_template") or "{title} · {site_name}")
    return template.replace("{title}", title).replace("{site_name}", site)


def _active_og_locale(config: Any) -> str:
    """``[seo] locale``, unless i18n is on and the request has its own language.

    Open Graph wants ``language_TERRITORY``: ``pt-BR`` becomes ``pt_BR``. A bare
    language (``en``) keeps ``[seo] locale`` when that is a variant of it.
    """
    configured = _s(config.get("seo_locale"))
    current = get_locale() if config.get("i18n_enable") else None
    if not current:
        return configured
    name = current.replace("-", "_")
    if "_" not in name and configured.lower().startswith(name.lower() + "_"):
        return configured
    return name


def tags(request: Request | None, config: Any, page: dict[str, Any]) -> Markup:
    """The ``<head>`` tags for one page. `page` holds the per-page overrides."""
    if not config.get("seo_enable", True):
        return Markup("")
    site = _s(config.get("seo_site_name") or config.get("app_name") or "")
    origin = origin_of(request, config)
    path = _s(page.get("path") or (request.path if request is not None else "/"))

    title = page_title(config, page.get("title", ""))
    description = _s(page.get("description") or config.get("seo_description")).strip()
    kind = _s(page.get("type") or config.get("seo_type") or "website")
    image = _absolute(origin, _s(page.get("image") or config.get("seo_image")))
    image_alt = _s(page.get("image_alt") or config.get("seo_image_alt"))
    canonical = _absolute(origin, _s(page.get("canonical"))) or (origin + path if origin else "")
    robots = _s(page.get("robots") or config.get("seo_robots"))
    if page.get("noindex"):
        robots = "noindex, nofollow"
    locale = _s(page.get("locale") or _active_og_locale(config))
    author = _s(page.get("author") or config.get("seo_author"))
    card = _s(config.get("seo_twitter_card"))
    twitter_site = _s(config.get("seo_twitter_site"))

    out = [Markup("<title>{}</title>").format(title)]
    out += [
        _meta("name", "description", description),
        _meta("name", "robots", robots),
        _meta("name", "author", author),
    ]
    if canonical:
        out.append(Markup('<link rel="canonical" href="{}">').format(canonical))
    for lang, url in (page.get("alternates") or {}).items():
        url = _absolute(origin, _s(url))
        if url:
            out.append(Markup('<link rel="alternate" hreflang="{}" href="{}">').format(_s(lang), url))
    out += [
        _meta("property", "og:site_name", site),
        _meta("property", "og:title", title),
        _meta("property", "og:description", description),
        _meta("property", "og:type", "article" if kind == "article" else kind),
        _meta("property", "og:url", canonical),
        _meta("property", "og:image", image),
        _meta("property", "og:image:alt", image_alt if image else ""),
        _meta("property", "og:locale", locale),
        _meta("name", "twitter:card", card if image else "summary"),
        _meta("name", "twitter:title", title),
        _meta("name", "twitter:description", description),
        _meta("name", "twitter:image", image),
        _meta("name", "twitter:site", twitter_site),
    ]
    if kind == "article":
        out += [
            _meta("property", "article:published_time", _s(page.get("published"))),
            _meta("property", "article:modified_time", _s(page.get("modified"))),
        ]
    if config.get("seo_jsonld", True):
        out += [_json_ld(block) for block in _structured_data(page, config, site, origin, canonical, title, description, image, kind, author, path)]
    return Markup("\n").join(part for part in out if part)


def _structured_data(page, config, site, origin, canonical, title, description, image, kind, author, path) -> list[Any]:
    blocks: list[Any] = []
    if path == "/" and origin and site:
        blocks.append({"@context": "https://schema.org", "@type": "WebSite", "name": site, "url": origin})
    if kind == "article":
        article: dict[str, Any] = {
            "@context": "https://schema.org", "@type": "Article", "headline": _s(page.get("title")).strip() or title,
        }
        if description:
            article["description"] = description
        if image:
            article["image"] = image
        if canonical:
            article["mainEntityOfPage"] = canonical
        if page.get("published"):
            article["datePublished"] = _s(page["published"])
        if page.get("modified"):
            article["dateModified"] = _s(page["modified"])
        if author:
            article["author"] = {"@type": "Person", "name": author}
        blocks.append(article)
    extra = page.get("jsonld")
    if isinstance(extra, dict):
        blocks.append(extra)
    elif isinstance(extra, list):
        blocks += [b for b in extra if isinstance(b, dict)]
    return blocks


def _request_config(request: Request | None):
    if request is not None:
        return request.app.config
    from ushka.core.config import Config

    return Config()


@pass_context
def seo(context, **overrides: Any) -> Markup:
    """``{{ seo() }}`` in ``<head>``: every SEO tag for this page."""
    request = context.get("request")
    page: dict[str, Any] = {}
    from_context = context.get("page_seo")
    if isinstance(from_context, dict):
        page.update({k: v for k, v in from_context.items() if k in PAGE_KEYS})
    unknown = set(overrides) - set(PAGE_KEYS)
    if unknown:
        raise TypeError(f"seo() got unknown option(s) {sorted(unknown)}; use {list(PAGE_KEYS)}")
    page.update(overrides)
    return tags(request, _request_config(request), page)


engine.add_global("seo", seo)


# -- robots.txt and sitemap.xml ------------------------------------------------------


def robots_txt(request: Request | None, config: Any) -> str:
    lines = ["User-agent: *"]
    if "noindex" in _s(config.get("seo_robots")).lower():
        lines.append("Disallow: /")
    else:
        lines.append("Allow: /")
        lines += [f"Disallow: {p}" for p in _list(config.get("seo_robots_disallow"))]
    origin = origin_of(request, config)
    if origin and config.get("seo_sitemap", True):
        lines += ["", f"Sitemap: {origin}/sitemap.xml"]
    return "\n".join(lines) + "\n"


def static_paths(app: Ushka) -> list[str]:
    """Paths of the app's plain GET pages that belong in a sitemap."""
    config = app.config
    patterns = _list(config.get("seo_sitemap_exclude"))
    skip = list(ALWAYS_EXCLUDED)
    if config.get("static_enable"):
        skip.append(_s(config.get("static_url") or "/static").rstrip("/") + "/*")
    found = []
    for path in sorted(app.router.static_routes.get("GET", {})):
        ext = posixpath.splitext(path)[1].lower()
        if ext not in ("", ".html", ".htm") or path in skip or _excluded(path, skip + patterns):
            continue
        found.append(path)
    return found


async def sitemap_xml(app: Ushka, origin: str) -> str:
    config = app.config
    entries: dict[str, str] = {}
    for path in static_paths(app):
        entries[path] = ""
    for path in _list(config.get("seo_sitemap_paths")):
        if safe_url(path):
            entries[path] = ""
    for source in getattr(app, "_sitemap_sources", []):
        result = source()
        if inspect.isawaitable(result):
            result = await result
        for item in result or []:
            path, lastmod = (item, "") if isinstance(item, str) else (item[0], _s(item[1]))
            if safe_url(_s(path)):
                entries[_s(path)] = lastmod
    rows = []
    for path, lastmod in entries.items():
        url = path if path.startswith("http") else origin + path
        rows.append(f"<url><loc>{escape(url)}</loc>" + (f"<lastmod>{escape(lastmod)}</lastmod>" if lastmod else "") + "</url>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(rows) + "</urlset>"
    )


def install(app: Ushka) -> None:
    """Registers ``/robots.txt`` and ``/sitemap.xml`` as built-in routes (yours win)."""
    config = app.config
    if not config.get("seo_enable", True):
        return
    app._sitemap_sources = []

    def sitemap_source(func):
        """Adds pages from code (a database, say): a function returning paths or ``(path, lastmod)``."""
        app._sitemap_sources.append(func)
        return func

    app.sitemap_source = sitemap_source

    if config.get("seo_robots_txt", True):

        async def robots(request):
            return Response(robots_txt(request, config), media_type="text/plain",
                            headers={"Cache-Control": "public, max-age=3600"})

        app.add_builtin_route("/robots.txt", robots)

    if config.get("seo_sitemap", True):

        async def sitemap(request):
            origin = origin_of(request, config)
            if not origin:
                raise HttpNotFound()  # no trustworthy address: set [seo] url
            body = await sitemap_xml(app, origin)
            return Response(body, media_type="application/xml", headers={"Cache-Control": "public, max-age=3600"})

        app.add_builtin_route("/sitemap.xml", sitemap)


__all__ = ["install", "robots_txt", "seo", "sitemap_xml", "tags"]
