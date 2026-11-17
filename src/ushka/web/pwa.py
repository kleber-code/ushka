"""Progressive Web App support, configured in ``[pwa]`` of ``ushka.toml``.

Switch it on and add the tags to your layout's ``<head>``::

    [pwa]
    enable = true
    name = "My App"
    theme_color = "#1b1720"
    icons = ["/static/icon-192.png", "/static/icon-512.png"]

    {{ pwa() }}

Ushka then serves a web app manifest (``/manifest.webmanifest``), a service
worker (``/sw.js``), a small script that registers it (``/pwa.js``) and an
offline page (``/offline``). Nothing needs inline JavaScript, so the default
Content-Security-Policy is untouched.

The service worker is deliberately conservative, because a worker that caches
pages can show one user's private page to the next person on a shared device:

- page navigations always go to the network; only when it fails is the offline page shown (pages are never cached);
- only ``GET`` requests to your own origin are handled;
- the files under ``[static]`` (and any ``cache_paths``) are cached and refreshed in the background;
- ``precache`` lists the extra URLs fetched when the worker installs.

Change ``cache_version`` to drop every cache on the next visit.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from jinja2 import pass_context
from markupsafe import Markup, escape

from ushka.http.response import Response
from ushka.templating.engine import engine
from ushka.web.seo import _list, _s, safe_url

if TYPE_CHECKING:
    from ushka.core.app import Ushka

ICON_TYPES = {".png": "image/png", ".webp": "image/webp", ".svg": "image/svg+xml", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
DISPLAYS = {"standalone", "fullscreen", "minimal-ui", "browser"}


def _icon(entry: Any) -> dict[str, str] | None:
    """One manifest icon from a path string or a ``{src, sizes, type, purpose}`` table."""
    item = {"src": entry} if isinstance(entry, str) else dict(entry) if isinstance(entry, dict) else {}
    src = safe_url(_s(item.get("src")))
    if not src:
        return None
    out = {"src": src}
    ext = "." + src.rsplit(".", 1)[-1].lower().split("?")[0] if "." in src.rsplit("/", 1)[-1] else ""
    out["type"] = _s(item.get("type")) or ICON_TYPES.get(ext, "")
    sizes = _s(item.get("sizes"))
    if not sizes:
        found = re.search(r"(\d{2,4})x(\d{2,4})", src) or re.search(r"[-_](\d{2,4})\.(?:png|webp|jpe?g)", src)
        sizes = f"{found.group(1)}x{found.group(found.lastindex if found.lastindex == 2 else 1)}" if found else ("any" if ext == ".svg" else "")
    out["sizes"] = sizes
    if item.get("purpose"):
        out["purpose"] = _s(item["purpose"])
    return {k: v for k, v in out.items() if v}


def icons(config: Any) -> list[dict[str, str]]:
    return [i for i in (_icon(e) for e in config.get("pwa_icons") or []) if i]


def manifest(config: Any) -> dict[str, Any]:
    """The web app manifest, from ``[pwa]`` with the ``[seo]``/``[app]`` names as fallback."""
    name = _s(config.get("pwa_name") or config.get("seo_site_name") or config.get("app_name") or "App")
    display = _s(config.get("pwa_display"))
    data: dict[str, Any] = {
        "name": name,
        "short_name": _s(config.get("pwa_short_name")) or name[:12],
        "description": _s(config.get("pwa_description") or config.get("seo_description")),
        "id": _s(config.get("pwa_id")) or _s(config.get("pwa_start_url") or "/"),
        "start_url": safe_url(_s(config.get("pwa_start_url") or "/")) or "/",
        "scope": safe_url(_s(config.get("pwa_scope") or "/")) or "/",
        "display": display if display in DISPLAYS else "standalone",
        "orientation": _s(config.get("pwa_orientation")),
        "theme_color": _s(config.get("pwa_theme_color")),
        "background_color": _s(config.get("pwa_background_color")),
        "lang": _s(config.get("pwa_lang")),
        "categories": _list(config.get("pwa_categories")),
        "icons": icons(config),
    }
    shortcuts = []
    for sc in config.get("pwa_shortcuts") or []:
        if isinstance(sc, dict) and sc.get("name") and safe_url(_s(sc.get("url"))):
            shortcuts.append({"name": _s(sc["name"]), "url": safe_url(_s(sc["url"]))})
    if shortcuts:
        data["shortcuts"] = shortcuts
    return {k: v for k, v in data.items() if v not in ("", [], None)}


def service_worker(config: Any) -> str:
    """The service worker script (see the module docstring for what it does)."""
    static = []
    if config.get("static_enable"):
        static.append(_s(config.get("static_url") or "/static").rstrip("/") + "/")
    static += [p if p.endswith("/") else p + "/" for p in _list(config.get("pwa_cache_paths")) if safe_url(p)]
    offline = _s(config.get("pwa_offline_path") or "/offline")
    precache = [u for u in _list(config.get("pwa_precache")) if safe_url(u)]
    settings = {
        "cache": "ushka-" + re.sub(r"[^A-Za-z0-9._-]", "", _s(config.get("pwa_cache_version") or "1")),
        "offline": offline if config.get("pwa_offline", True) else "",
        "precache": ([offline] if config.get("pwa_offline", True) else []) + precache,
        "static": static,
    }
    blob = json.dumps(settings).replace("<", "\\u003c")
    return _WORKER.replace("__SETTINGS__", blob)


_WORKER = """/* Generated by Ushka from [pwa] in ushka.toml. */
const S = __SETTINGS__;
self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(S.cache).then((c) => c.addAll(S.precache)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k.startsWith("ushka-") && k !== S.cache).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});
self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  if (req.mode === "navigate") {
    // Pages are never cached (they can be private): network first, the offline page only when it fails.
    if (S.offline) event.respondWith(fetch(req).catch(() => caches.match(S.offline)));
    return;
  }
  if (S.static.some((p) => url.pathname.startsWith(p))) {
    event.respondWith(caches.open(S.cache).then(async (cache) => {
      const hit = await cache.match(req);
      const net = fetch(req).then((res) => { if (res.ok) cache.put(req, res.clone()); return res; }).catch(() => hit);
      return hit || net;
    }));
  }
});
"""


def register_script(config: Any) -> str:
    sw = safe_url(_s(config.get("pwa_sw_path") or "/sw.js")) or "/sw.js"
    scope = safe_url(_s(config.get("pwa_scope") or "/")) or "/"
    return (
        'if ("serviceWorker" in navigator) {\n'
        '  addEventListener("load", () => navigator.serviceWorker.register('
        f"{json.dumps(sw)}, {{ scope: {json.dumps(scope)} }}).catch(() => {{}}));\n"
        "}\n"
    )


def offline_page(config: Any) -> str:
    name = escape(_s(config.get("pwa_name") or config.get("seo_site_name") or config.get("app_name") or "App"))
    title = escape(_s(config.get("pwa_offline_title") or "You are offline"))
    message = escape(_s(config.get("pwa_offline_message") or "Check your connection and try again."))
    theme = escape(_s(config.get("pwa_theme_color")) or "#1b1720")
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<meta name="robots" content="noindex"><meta name="theme-color" content="{theme}">'
        f"<title>{title} · {name}</title>"
        "<style>body{margin:0;min-height:100vh;display:grid;place-items:center;font:500 1rem/1.6 system-ui,sans-serif;"
        "background:#15121a;color:#f4f1f6;text-align:center;padding:1.5rem}h1{margin:0 0 .5rem}"
        "a{color:#ff9a5c}</style></head>"
        f'<body><main><h1>{title}</h1><p>{message}</p><p><a href="/">Try again</a></p></main></body></html>'
    )


@pass_context
def pwa(context) -> Markup:
    """``{{ pwa() }}`` in ``<head>``: manifest link, theme colour, icons and the registration script."""
    request = context.get("request")
    if request is not None:
        config = request.app.config
    else:
        from ushka.core.config import Config

        config = Config()
    if not config.get("pwa_enable"):
        return Markup("")
    path = safe_url(_s(config.get("pwa_manifest_path") or "/manifest.webmanifest")) or "/manifest.webmanifest"
    parts = [Markup('<link rel="manifest" href="{}">').format(path)]
    theme = _s(config.get("pwa_theme_color"))
    if theme:
        parts.append(Markup('<meta name="theme-color" content="{}">').format(theme))
    parts.append(Markup('<meta name="mobile-web-app-capable" content="yes">'))
    name = _s(config.get("pwa_short_name") or config.get("pwa_name") or config.get("seo_site_name") or config.get("app_name"))
    if name:
        parts.append(Markup('<meta name="apple-mobile-web-app-title" content="{}">').format(name[:12] if not config.get("pwa_short_name") else name))
    png = [i for i in icons(config) if i.get("type") == "image/png"]
    if png:
        def px(icon):
            found = re.match(r"\d+", icon.get("sizes", ""))
            return int(found.group(0)) if found else 0

        # iOS asks for 180x180: the smallest icon that is at least that, else the largest
        big = sorted((i for i in png if px(i) >= 180), key=px)
        best = big[0] if big else max(png, key=px)
        parts.append(Markup('<link rel="apple-touch-icon" href="{}">').format(best["src"]))
    script = safe_url(_s(config.get("pwa_script_path") or "/pwa.js")) or "/pwa.js"
    parts.append(Markup('<script src="{}" defer></script>').format(script))
    return Markup("\n").join(parts)


engine.add_global("pwa", pwa)


def install(app: Ushka) -> None:
    """Registers the manifest, worker, register script and offline page when ``[pwa] enable`` is true."""
    config = app.config
    if not config.get("pwa_enable"):
        return

    def path_of(key: str, default: str) -> str:
        return safe_url(_s(config.get(key) or default)) or default

    async def manifest_view():
        return Response(json.dumps(manifest(config)), media_type="application/manifest+json",
                        headers={"Cache-Control": "public, max-age=3600"})

    async def worker_view():
        scope = safe_url(_s(config.get("pwa_scope") or "/")) or "/"
        return Response(service_worker(config), media_type="text/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": scope})

    async def script_view():
        return Response(register_script(config), media_type="text/javascript",
                        headers={"Cache-Control": "public, max-age=3600"})

    async def offline_view():
        return Response(offline_page(config), media_type="text/html", headers={"Cache-Control": "no-cache"})

    app.add_builtin_route(path_of("pwa_manifest_path", "/manifest.webmanifest"), manifest_view)
    app.add_builtin_route(path_of("pwa_sw_path", "/sw.js"), worker_view)
    app.add_builtin_route(path_of("pwa_script_path", "/pwa.js"), script_view)
    if config.get("pwa_offline", True):
        app.add_builtin_route(path_of("pwa_offline_path", "/offline"), offline_view)


class Pwa:
    """``app.use(Pwa(name="Shop", icons=["/static/icon-512.png"], theme_color="#1b1720"))``.

    Using it turns the PWA on (no ``enable = true``); ``ushka.toml`` and the environment
    still win, so ``enable = false`` there switches it off. ``**options`` are any other
    keys of ``[pwa]``.
    """

    name = "pwa"

    def __init__(self, name: str | None = None, icons: list | None = None, theme_color: str | None = None, **options: Any) -> None:
        given = {"name": name, "icons": icons, "theme_color": theme_color}
        self.options = {"enable": True, **{k: v for k, v in given.items() if v is not None}, **options}

    def install(self, app: Ushka) -> None:
        app.config.defaults("pwa", **self.options)
        install(app)


__all__ = ["Pwa", "install", "manifest", "pwa", "service_worker"]
