"""Every setting Ushka reads, in one place: its default and what it does.

``SCHEMA`` is the single source of truth. From it come the defaults
(``DEFAULTS``), the annotated ``ushka.toml`` that ``ushka new`` writes, the
settings table in the docs, ``ushka config`` and the warnings about unknown or
wrongly typed keys. Nothing Ushka reads from the configuration is missing here,
so nothing is hidden: if a setting is not in this file, Ushka does not use it.

This module imports nothing from Ushka.
"""

from __future__ import annotations

import difflib
import textwrap
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Setting:
    default: Any
    help: str
    #: Never written to ``ushka.toml``: it belongs in ``.env`` or the environment.
    secret: bool = False


def _s(default: Any, help: str, secret: bool = False) -> Setting:
    return Setting(default, help, secret)


#: ``{section: description}``, in the order they are written and documented.
SECTIONS: dict[str, str] = {
    "app": "Your application.",
    "database": "The database used by the async ORM.",
    "server": "How `ushka dev`, `ushka run` and `app.run()` serve the app.",
    "static": "Serving static files.",
    "limits": "Size limits that protect the server from huge requests.",
    "session": "Sessions: a signed cookie by default, or revocable sessions kept on the server.",
    "security": "Ushka Guard and the security middleware, all on by default.",
    "seo": "SEO tags, robots.txt and sitemap.xml, ready out of the box.",
    "pwa": "Progressive Web App: manifest, service worker and offline page (off by default).",
    "mcp": "The MCP endpoint that exposes routes as tools for AI agents.",
}

#: Where each section is explained, relative to ``docs/guide/``.
SECTION_DOCS: dict[str, str] = {
    "database": "orm.md",
    "server": "deploy.md",
    "static": "static_files.md",
    "session": "sessions.md",
    "security": "security.md",
    "seo": "seo.md",
    "pwa": "pwa.md",
    "mcp": "agents.md",
}

SCHEMA: dict[str, dict[str, Setting]] = {
    "app": {
        "name": _s("Ushka App", "Display name. Used in page titles, the SEO site name and the PWA name."),
        "debug": _s(False, "Debug pages with tracebacks and local variables. Never turn it on in production."),
        "auto_discover": _s(True, "Load route files from the routes/ folder."),
        "secret_key": _s("", "Signs the session cookie. Use USHKA_APP_SECRET_KEY in .env, never this file.", secret=True),
    },
    "database": {
        "url": _s("sqlite:///ushka.db", "SQLAlchemy URL. Plain sqlite://, postgresql:// and mysql:// get an async driver. DATABASE_URL also works."),
    },
    "server": {
        "host": _s("127.0.0.1", 'Address to bind. Use "0.0.0.0" in a container.'),
        "port": _s(8000, "Port to listen on."),
        "workers": _s(1, "Worker processes for `ushka run` (`ushka dev` always uses one)."),
    },
    "static": {
        "enable": _s(False, "Serve the static folder under `url`."),
        "url": _s("/static", "URL prefix of the static files."),
        "dir": _s("static", "Folder with the files, relative to the app directory or absolute."),
        "cache_control": _s("public, max-age=3600", "Cache-Control sent with every static file."),
    },
    "session": {
        "store": _s("cookie", 'Where sessions live: "cookie" (signed, in the browser) or "database" (revocable, no size limit; needs [database] url, else cookies are used).'),
        "cookie_name": _s("_ushka_session", "Name of the session cookie."),
        "max_age": _s(1209600, "Seconds a session lasts, counted from its creation (14 days). 0 means no limit."),
        "idle_timeout": _s(0, "Server-side stores only: seconds without a request after which a session ends. 0 turns it off."),
        "user_key": _s("user_id", "Server-side stores only: the session key that holds the user id, used to revoke all of a user's sessions."),
        "table": _s("ushka_sessions", 'Table used by store = "database". Created on first use.'),
    },
    "limits": {
        "max_request_body_size_in_KB": _s(2048, "Largest request body, in KB. Bigger bodies get 413."),
        "max_request_body_multipart_size_in_KB": _s(51200, "Largest multipart upload, in KB."),
        "websocket_max_message_in_KB": _s(1024, "Largest WebSocket message, in KB. Bigger ones close the socket with 1009."),
    },
    "security": {
        "taint": _s(True, "Ushka Guard: request data arrives as `Untrusted` and dangerous sinks refuse it. Turning it off is a migration aid, not a mode."),
        "headers": _s(True, "Security headers on every response (nosniff, frame options, referrer policy, CSP, HSTS)."),
        "csp": _s("", 'Content-Security-Policy. Empty is the strict default policy; "off" sends none.'),
        "frame_options": _s("DENY", "X-Frame-Options."),
        "referrer_policy": _s("strict-origin-when-cross-origin", "Referrer-Policy."),
        "hsts_seconds": _s(31536000, "Strict-Transport-Security max-age, sent on https requests only. 0 turns it off."),
        "csrf": _s(True, "CSRF protection for writes from browsers, without tokens."),
        "csrf_trusted_origins": _s([], "Other origins allowed to send writes."),
        "csrf_exempt_paths": _s([], "Paths that skip the CSRF check (webhooks, for example)."),
        "allowed_hosts": _s([], "Accepted Host headers. Empty means any host: set it in production."),
        "cors_origins": _s([], "Origins allowed by CORS. Empty means no CORS headers."),
        "cors_methods": _s(["GET", "POST", "PUT", "PATCH", "DELETE"], "Methods CORS allows."),
        "cors_headers": _s([], "Request headers CORS allows. Empty echoes what the preflight asks for."),
        "cors_credentials": _s(False, 'Let other origins send cookies. Refused together with "*".'),
        "cors_max_age": _s(600, "Seconds a browser may cache the preflight answer."),
    },
    "seo": {
        "enable": _s(True, "`{{ seo() }}` tags, /robots.txt and /sitemap.xml. false turns all of it off."),
        "url": _s("", 'Public origin, such as "https://example.com". Needed for canonical links and the sitemap.'),
        "site_name": _s("", "Site name in titles and social cards. Empty uses [app] name."),
        "title": _s("", "Title of pages that set none (usually the home page)."),
        "title_template": _s("{title} · {site_name}", "How a page title is combined with the site name."),
        "description": _s("", "Default meta and social description."),
        "image": _s("", "Default social preview image, a path or a URL."),
        "image_alt": _s("", "Alternative text of that image."),
        "locale": _s("en_US", "Open Graph locale."),
        "type": _s("website", "Default Open Graph type."),
        "robots": _s("index, follow", 'Robots rule. "noindex, nofollow" keeps a staging site out of search.'),
        "author": _s("", "Default author."),
        "twitter_site": _s("", 'Twitter/X handle of the site, such as "@example".'),
        "twitter_card": _s("summary_large_image", "Twitter/X card type when there is an image."),
        "jsonld": _s(True, "Structured data: WebSite on the home page, Article for articles."),
        "robots_txt": _s(True, "Serve /robots.txt."),
        "robots_disallow": _s([], "Paths written as Disallow lines in robots.txt."),
        "sitemap": _s(True, "Serve /sitemap.xml."),
        "sitemap_paths": _s([], "Extra paths to list in the sitemap (pages with parameters)."),
        "sitemap_exclude": _s(["/api/*", "/admin/*", "/_*"], "Patterns left out of the sitemap. Plain GET pages are listed otherwise."),
    },
    "pwa": {
        "enable": _s(False, "Serve the manifest, service worker and offline page."),
        "name": _s("", "App name. Empty uses [seo] site_name, then [app] name."),
        "short_name": _s("", "Short name under the home-screen icon (12 characters work best)."),
        "description": _s("", "Empty uses [seo] description."),
        "start_url": _s("/", "Where the installed app opens."),
        "scope": _s("/", "Which URLs the installed app and the service worker control."),
        "display": _s("standalone", "standalone, fullscreen, minimal-ui or browser."),
        "orientation": _s("", 'Optional lock, such as "portrait" or "landscape".'),
        "theme_color": _s("#1b1720", "Colour of the title bar."),
        "background_color": _s("#ffffff", "Colour of the splash screen."),
        "lang": _s("", "Language of the manifest, such as pt-BR."),
        "id": _s("", "Stable identity of the app. Empty uses start_url."),
        "categories": _s([], 'Store categories, such as ["productivity"].'),
        "icons": _s([], 'Paths, or [[pwa.icons]] tables with src, sizes, type and purpose. Chrome wants 192x192 and 512x512 PNGs.'),
        "shortcuts": _s([], "[[pwa.shortcuts]] tables with name and url, shown on long-press."),
        "offline": _s(True, "Show an offline page when a navigation fails for lack of network."),
        "offline_title": _s("You are offline", "Title of the built-in offline page."),
        "offline_message": _s("Check your connection and try again.", "Text of the built-in offline page."),
        "precache": _s([], "Extra URLs fetched when the worker installs. They must all exist."),
        "cache_paths": _s([], "Extra URL prefixes cached at runtime. [static] is always included."),
        "cache_version": _s("1", "Change it to drop every cache on the next visit."),
        "manifest_path": _s("/manifest.webmanifest", "Where the manifest is served."),
        "sw_path": _s("/sw.js", "Where the service worker is served."),
        "script_path": _s("/pwa.js", "Where the script that registers the worker is served."),
        "offline_path": _s("/offline", "Where the offline page is served."),
    },
    "mcp": {
        "token": _s("", "Bearer token of the MCP endpoint. Use USHKA_MCP_TOKEN, never this file.", secret=True),
    },
}

#: Built-in defaults, ``{section: {key: value}}``.
DEFAULTS: dict[str, dict[str, Any]] = {
    section: {key: setting.default for key, setting in keys.items()} for section, keys in SCHEMA.items()
}

#: Environment names honoured in addition to ``USHKA_<SECTION>_<KEY>``.
ENV_ALIASES = {"USHKA_DATABASE_URL": ("DATABASE_URL", "USHKA_DB_URL")}

#: Read-only information Ushka adds itself (``[ushka]``); it cannot be set.
RUNTIME = {"version": "Installed Ushka version.", "workdir": "The application directory."}


def env_name(section: str, key: str) -> str:
    return f"USHKA_{section}_{key}".upper()


# -- checking what the user wrote ---------------------------------------------------


def _type_name(value: Any) -> str:
    return {bool: "true/false", int: "a number", float: "a number", str: "a string", list: "a list"}.get(type(value), type(value).__name__)


def _fits(default: Any, value: Any) -> bool:
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, int):
        return isinstance(value, int) and not isinstance(value, bool)
    if isinstance(default, float):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if isinstance(default, str):
        return isinstance(value, str)
    if isinstance(default, list):
        return isinstance(value, list)
    return True


def problems_in(file_data: dict[str, Any]) -> list[str]:
    """What is wrong with the settings found in ``ushka.toml``.

    Unknown keys inside a built-in section (almost always a typo) and values of
    the wrong type (``csrf = "false"`` is a non-empty string, so it would read as
    on). Your own sections are fine and are not checked.
    """
    found: list[str] = []
    for section, content in file_data.items():
        if section not in SCHEMA or not isinstance(content, dict):
            continue
        for key, value in content.items():
            setting = SCHEMA[section].get(key)
            if setting is None:
                close = difflib.get_close_matches(key, SCHEMA[section], n=1)
                hint = f" (did you mean {close[0]!r}?)" if close else "; put your own settings in a section of your own, like [myapp]"
                found.append(f"[{section}] {key} is not a Ushka setting{hint}")
            elif not _fits(setting.default, value):
                found.append(f"[{section}] {key} should be {_type_name(setting.default)}, got {value!r}")
    return found


# -- rendering -----------------------------------------------------------------------


def toml_value(value: Any) -> str:
    """`value` as TOML."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{k} = {toml_value(v)}" for k, v in value.items()) + " }"
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def render_toml(overrides: dict[str, dict[str, Any]] | None = None, header: str = "") -> str:
    """A complete, annotated ``ushka.toml``: every setting, with its default and its meaning.

    `overrides` replaces defaults, ``{section: {key: value}}`` (``ushka new`` uses
    it for the project name). Secrets are written commented out.
    """
    overrides = overrides or {}
    out = [header.rstrip("\n")] if header else []
    for section, keys in SCHEMA.items():
        out += ["", f"# {'-' * 70}", *(f"# {line}" for line in textwrap.wrap(SECTIONS[section], 72)),
                f"# Environment: {env_name(section, '<KEY>')}", f"[{section}]"]
        for key, setting in keys.items():
            value = overrides.get(section, {}).get(key, setting.default)
            out += [f"# {line}" for line in textwrap.wrap(setting.help, 74)]
            if setting.secret:
                out.append(f"# {key} = {toml_value(value)}   # secret: keep it in the environment")
            else:
                out.append(f"{key} = {toml_value(value)}")
            out.append("")
        out.pop()
    return "\n".join(out) + "\n"


def render_markdown() -> str:
    """The settings reference for the docs: one table per section. Generated, never hand-edited."""
    out: list[str] = []
    for section, keys in SCHEMA.items():
        out += [f"### `[{section}]`", "", SECTIONS[section]]
        if section in SECTION_DOCS:
            out[-1] += f" See [{SECTION_DOCS[section].removesuffix('.md').replace('_', ' ')}]({SECTION_DOCS[section]})."
        out += ["", "| Key | Default | Meaning |", "| --- | --- | --- |"]
        for key, setting in keys.items():
            default = "*(set it in the environment)*" if setting.secret else f"`{toml_value(setting.default)}`"
            meaning = setting.help.replace("|", "\\|")
            out.append(f"| `{key}` | {default} | {meaning} |")
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"
