"""SEO (ready by default) and PWA (opt-in): tags, robots.txt, sitemap.xml, manifest, worker."""

import json
import logging

import pytest

from ushka import render
from ushka.guard import Untrusted

PAGE = "<html><head>{{ seo() }}{{ pwa() }}</head><body>hi</body></html>"


def _app(make_app, workdir, toml="", page=PAGE):
    (workdir / "templates").mkdir(exist_ok=True)
    (workdir / "templates" / "p.html").write_text(page)
    (workdir / "ushka.toml").write_text('[app]\nauto_discover = false\n' + toml)
    app = make_app()

    @app.get("/")
    async def home(request):
        return await render(request, "p.html", {})

    @app.get("/about")
    async def about(request):
        return await render(request, "p.html", {"page_seo": {"title": "About us", "description": "Who we are"}})

    return app


SEO = '[seo]\nurl = "https://example.com"\ndescription = "A site"\nimage = "/static/og.png"\n'


async def test_seo_tags_come_from_the_config(make_app, workdir, call):
    app = _app(make_app, workdir, SEO)
    html = (await call(app, "GET", "/"))["body"]
    assert '<link rel="canonical" href="https://example.com/">' in html
    assert '<meta name="description" content="A site">' in html
    assert '<meta property="og:image" content="https://example.com/static/og.png">' in html
    assert '<meta name="twitter:card" content="summary_large_image">' in html
    assert '"@type":"WebSite"' in html  # structured data on the home page


async def test_a_page_adjusts_its_own_tags(make_app, workdir, call):
    app = _app(make_app, workdir, SEO + 'site_name = "Demo"\n')
    html = (await call(app, "GET", "/about"))["body"]
    assert "<title>About us · Demo</title>" in html
    assert '<meta name="description" content="Who we are">' in html
    assert 'href="https://example.com/about"' in html
    assert '"@type":"WebSite"' not in html  # only on "/"


async def test_template_call_overrides_and_noindex(make_app, workdir, call):
    page = '<head>{{ seo(title="Draft", noindex=True, type="article", published="2026-01-02", author="Ada") }}</head>'
    app = _app(make_app, workdir, SEO, page)
    html = (await call(app, "GET", "/"))["body"]
    assert '<meta name="robots" content="noindex, nofollow">' in html
    assert '<meta property="og:type" content="article">' in html
    assert '"@type":"Article"' in html and '"headline":"Draft"' in html and '"datePublished":"2026-01-02"' in html
    assert '"author":{"@type":"Person","name":"Ada"}' in html


async def test_unknown_seo_option_is_an_error_not_silence(make_app, workdir, call):
    app = _app(make_app, workdir, SEO, "<head>{{ seo(titel='x') }}</head>")
    assert (await call(app, "GET", "/"))["status"] == 500


async def test_values_are_escaped_and_unsafe_urls_dropped(make_app, workdir, call):
    app = _app(make_app, workdir, SEO)

    @app.get("/evil")
    async def evil(request):
        hostile = Untrusted('"><script>alert(1)</script>', "query:q")
        ctx = {"page_seo": {"title": hostile, "description": hostile, "image": "javascript:alert(1)",
                            "jsonld": {"name": "</script><script>alert(2)</script>"}}}
        return await render(request, "p.html", ctx)

    html = (await call(app, "GET", "/evil"))["body"]
    assert "<script>alert" not in html and "</script><script>" not in html
    assert "&lt;script&gt;" in html
    assert "javascript:" not in html
    assert "\\u003c/script\\u003e" in html  # JSON-LD cannot close its own tag


async def test_without_a_public_url_no_origin_is_guessed_from_the_host(make_app, workdir, call):
    app = _app(make_app, workdir)
    res = await call(app, "GET", "/", headers={"Host": "evil.example"})
    assert "evil.example" not in res["body"] and 'rel="canonical"' not in res["body"]
    assert "Sitemap:" not in (await call(app, "GET", "/robots.txt", headers={"Host": "evil.example"}))["body"]
    assert (await call(app, "GET", "/sitemap.xml", headers={"Host": "evil.example"}))["status"] == 404


async def test_origin_comes_from_the_request_in_debug_or_with_allowed_hosts(make_app, workdir, call):
    app = _app(make_app, workdir, '[security]\nallowed_hosts = ["ok.example"]\n')
    res = await call(app, "GET", "/", headers={"Host": "ok.example"})
    assert 'href="http://ok.example/"' in res["body"]


async def test_origin_comes_from_the_request_in_debug(make_app, workdir, call):
    (workdir / "templates").mkdir(exist_ok=True)
    (workdir / "templates" / "p.html").write_text(PAGE)
    (workdir / "ushka.toml").write_text("[app]\nauto_discover = false\ndebug = true\n")
    app = make_app()

    @app.get("/")
    async def home(request):
        return await render(request, "p.html", {})

    res = await call(app, "GET", "/", headers={"Host": "localhost:8000"})
    assert 'href="http://localhost:8000/"' in res["body"]


async def test_robots_txt_and_sitemap(make_app, workdir, call):
    app = _app(make_app, workdir, SEO + 'robots_disallow = ["/private"]\nsitemap_paths = ["/blog/first"]\n')

    @app.get("/api/users")
    async def api():
        return {}

    @app.get("/admin/panel")
    async def admin():
        return "x"

    @app.get("/data.json")
    async def data():
        return {}

    @app.sitemap_source
    async def posts():
        return [("/blog/second", "2026-11-16"), "/blog/third"]

    robots = await call(app, "GET", "/robots.txt")
    assert robots["headers"]["content-type"].startswith("text/plain")
    assert "Disallow: /private" in robots["body"] and "Sitemap: https://example.com/sitemap.xml" in robots["body"]

    sitemap = await call(app, "GET", "/sitemap.xml")
    body = sitemap["body"]
    assert sitemap["headers"]["content-type"].startswith("application/xml")
    for listed in ("https://example.com/</loc>", "/about</loc>", "/blog/first</loc>", "/blog/second</loc>", "/blog/third</loc>"):
        assert listed in body, listed
    assert "<lastmod>2026-11-16</lastmod>" in body
    for hidden in ("/api/users", "/admin/panel", "/data.json", "/robots.txt", "/sitemap.xml"):
        assert hidden not in body, hidden


async def test_noindex_site_disallows_everything(make_app, workdir, call):
    app = _app(make_app, workdir, SEO.replace("[seo]\n", '[seo]\nrobots = "noindex, nofollow"\n'))
    assert "Disallow: /\n" in (await call(app, "GET", "/robots.txt"))["body"]


async def test_your_routes_win_over_the_built_in_ones(make_app, workdir, call, caplog):
    app = _app(make_app, workdir, SEO)

    @app.get("/robots.txt")
    async def mine():
        return "User-agent: *\nDisallow: /\n"

    with caplog.at_level(logging.WARNING):
        res = await call(app, "GET", "/robots.txt")
    assert "Disallow: /\n" in res["body"] and "Sitemap" not in res["body"]
    assert not [r for r in caplog.records if "Overwriting" in r.getMessage()]


async def test_seo_can_be_switched_off(make_app, workdir, call):
    app = _app(make_app, workdir, SEO + "enable = false\n")
    assert (await call(app, "GET", "/robots.txt"))["status"] == 404
    assert (await call(app, "GET", "/sitemap.xml"))["status"] == 404
    assert "<title>" not in (await call(app, "GET", "/"))["body"]


async def test_built_in_pages_do_not_count_as_app_routes(make_app, workdir, call):
    (workdir / "ushka.toml").write_text('[app]\nauto_discover = false\n')
    app = make_app()  # no routes of its own: the welcome page must still show
    res = await call(app, "GET", "/")
    assert res["status"] == 200 and "Ushka" in res["body"]


# -- PWA ------------------------------------------------------------------------------

PWA_KEYS = (
    '[pwa]\nenable = true\nname = "Demo App"\ntheme_color = "#112233"\n'
    'icons = ["/static/icon-192.png", "/static/icon-512.png", "javascript:alert(1)"]\n'
    'cache_paths = ["/assets"]\nprecache = ["/about"]\ncache_version = "7"\n'
)
SHORTCUTS = '[[pwa.shortcuts]]\nname = "About"\nurl = "/about"\n'
PWA = PWA_KEYS + SHORTCUTS


async def test_pwa_is_off_by_default(make_app, workdir, call):
    app = _app(make_app, workdir, SEO)
    for path in ("/manifest.webmanifest", "/sw.js", "/pwa.js", "/offline"):
        assert (await call(app, "GET", path))["status"] == 404, path
    assert "manifest" not in (await call(app, "GET", "/"))["body"]


async def test_manifest_from_the_config(make_app, workdir, call):
    app = _app(make_app, workdir, SEO + PWA)
    res = await call(app, "GET", "/manifest.webmanifest")
    assert res["headers"]["content-type"].startswith("application/manifest+json")
    m = json.loads(res["body"])
    assert m["name"] == "Demo App" and m["display"] == "standalone" and m["theme_color"] == "#112233"
    assert m["description"] == "A site"  # falls back to [seo]
    assert [i["sizes"] for i in m["icons"]] == ["192x192", "512x512"]  # sizes read from the names; the unsafe one is dropped
    assert all(i["type"] == "image/png" for i in m["icons"])
    assert m["shortcuts"] == [{"name": "About", "url": "/about"}]


async def test_head_tags_and_a_csp_friendly_register_script(make_app, workdir, call):
    app = _app(make_app, workdir, SEO + PWA)
    page = await call(app, "GET", "/")
    html = page["body"]
    assert '<link rel="manifest" href="/manifest.webmanifest">' in html
    assert '<meta name="theme-color" content="#112233">' in html
    assert '<link rel="apple-touch-icon" href="/static/icon-192.png">' in html
    assert '<script src="/pwa.js" defer></script>' in html
    assert "script-src" not in page["headers"]["content-security-policy"]  # untouched: 'self' only
    script = await call(app, "GET", "/pwa.js")
    assert script["headers"]["content-type"].startswith("text/javascript")
    assert 'register("/sw.js", { scope: "/" })' in script["body"]


async def test_service_worker_is_conservative(make_app, workdir, call):
    app = _app(make_app, workdir, '[static]\nenable = true\n' + SEO + PWA)
    res = await call(app, "GET", "/sw.js")
    assert res["headers"]["cache-control"] == "no-cache" and res["headers"]["service-worker-allowed"] == "/"
    js = res["body"]
    settings = json.loads(js.split("const S = ", 1)[1].split(";\n", 1)[0])
    assert settings["cache"] == "ushka-7"
    assert settings["precache"] == ["/offline", "/about"]
    assert settings["static"] == ["/static/", "/assets/"]
    # pages are never cached, only the network is tried for navigations
    assert 'req.mode === "navigate"' in js and "cache.put" in js
    assert 'if (req.method !== "GET") return;' in js and "url.origin !== location.origin" in js


async def test_offline_page_and_switching_it_off(make_app, workdir, call):
    app = _app(make_app, workdir, SEO + PWA_KEYS + 'offline_title = "No signal"\n')
    page = await call(app, "GET", "/offline")
    assert "No signal" in page["body"] and 'content="noindex"' in page["body"]
    app = _app(make_app, workdir, SEO + PWA_KEYS + "offline = false\n")
    assert (await call(app, "GET", "/offline"))["status"] == 404
    assert '"offline": ""' in (await call(app, "GET", "/sw.js"))["body"]


async def test_check_wants_installable_icons(make_app, workdir, monkeypatch, capsys):
    from ushka.cli.commands.check import check

    (workdir / "ushka.toml").write_text('[pwa]\nenable = true\nicons = ["/static/icon-192.png"]\n')
    assert check() >= 1
    (workdir / "ushka.toml").write_text('[pwa]\nenable = true\nicons = ["/i-192.png", "/i-512.png"]\n')
    from ushka.core.config import Config

    Config._instance = None
    Config._initialized = False
    assert check() == 0


@pytest.mark.parametrize("raw,expected", [("/static/a.png", "/static/a.png"), ("//evil.example/x", ""), ("javascript:x", ""),
                                          ("https://cdn.example/a.png", "https://cdn.example/a.png"), ("data:text/html,x", "")])
def test_safe_url(raw, expected):
    from ushka.web.seo import safe_url

    assert safe_url(raw) == expected
