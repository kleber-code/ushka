"""Ushka Docs (ushka.docs): build, link checking, serving, search and contrast."""

import re
from pathlib import Path

import pytest

pytest.importorskip("markdown_it")
pytest.importorskip("griffe")

from ushka.docs import Docs  # noqa: E402
from ushka.docs.render import slugify  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
THEME_CSS = REPO / "src" / "ushka" / "internal" / "docs_theme" / "docs.css"


def test_project_docs_build_without_problems():
    docs = Docs(REPO / "docs", api_package="ushka", api_path=REPO / "src")
    assert docs.build() == []
    assert "guide/guard/" in docs.pages and "api/ushka.guard.safe/" in docs.pages


def test_guard_error_codes_link_to_real_anchors():
    from ushka.guard.errors import DOCS_BASE

    docs = Docs(REPO / "docs")
    docs.build()
    ids = {h[2] for h in docs.pages["guide/guard/"].headings}
    for code in ("USHKA-G001", "USHKA-G002", "USHKA-G003", "USHKA-G004", "USHKA-G005"):
        assert slugify(code) in ids
    assert DOCS_BASE.endswith("/docs/guide/guard/#")


@pytest.fixture
def tiny_docs(tmp_path):
    root = tmp_path / "docs"
    (root / "guide").mkdir(parents=True)
    (root / "index.md").write_text("# Home\n\nSee the [guide](guide/start.md#install) for a long enough first paragraph here.\n")
    (root / "guide" / "start.md").write_text("# Start\n\n## Install\n\n```python\nprint('hi')\n```\n\n![logo](../logo.png)\n")
    (root / "logo.png").write_bytes(b"\x89PNG fake")
    (root / "nav.toml").write_text('[[section]]\ntitle = ""\npages = ["index.md", "guide/start.md"]\n')
    return root


def test_broken_links_anchors_and_nav_are_reported(tiny_docs):
    (tiny_docs / "index.md").write_text("# Home\n\n[a](missing.md) [b](guide/start.md#nope) [c](nope.png)\n")
    (tiny_docs / "orphan.md").write_text("# Orphan\n")
    messages = [p.message for p in Docs(tiny_docs).build()]
    assert "link to missing page missing.md" in messages
    assert "link to missing anchor guide/start.md#nope" in messages
    assert "link to missing file nope.png" in messages
    assert "not listed in nav.toml" in messages


def test_links_are_rewritten_and_code_is_highlighted(tiny_docs):
    docs = Docs(tiny_docs, url="/docs")
    assert docs.build() == []
    home, start = docs.pages[""], docs.pages["guide/start/"]
    assert 'href="/docs/guide/start/#install"' in home.html
    assert 'src="/docs/logo.png"' in start.html
    assert '<span class="nb">print</span>' in start.html
    assert home.description.startswith("See the guide")


@pytest.fixture
def docs_app(make_app, tiny_docs):
    app = make_app()
    Docs(tiny_docs, url="/docs", title="Tiny", base_url="https://example.com").mount(app)
    return app


async def test_pages_redirects_etag_and_assets(docs_app, call):
    page = await call(docs_app, "GET", "/docs/guide/start/")
    assert page["status"] == 200 and "<h1" in page["body"]
    assert '<link rel="canonical" href="https://example.com/docs/guide/start/">' in page["body"]
    again = await call(docs_app, "GET", "/docs/guide/start/", headers={"if-none-match": page["headers"]["etag"]})
    assert again["status"] == 304

    moved = await call(docs_app, "GET", "/docs/guide/start")
    assert moved["status"] == 301 and moved["headers"]["location"] == "/docs/guide/start/"
    assert (await call(docs_app, "GET", "/docs"))["headers"]["location"] == "/docs/"
    assert (await call(docs_app, "GET", "/docs/logo.png"))["status"] == 200
    assert (await call(docs_app, "GET", "/docs/_theme/docs.css"))["status"] == 200
    assert "example.com/docs/guide/start/" in (await call(docs_app, "GET", "/docs/sitemap.xml"))["body"]


@pytest.mark.parametrize("path", ["/docs/nav.toml", "/docs/index.md", "/docs/../secret", "/docs/nope/"])
async def test_sources_and_unknown_paths_are_not_served(docs_app, call, path):
    assert (await call(docs_app, "GET", path))["status"] == 404


async def test_search_finds_pages_and_escapes_the_query(docs_app, call):
    found = await call(docs_app, "GET", "/docs/search", query=b"q=install")
    assert found["status"] == 200 and "/docs/guide/start/#install" in found["body"]
    assert found["headers"]["x-robots-tag"] == "noindex"
    attack = await call(docs_app, "GET", "/docs/search", query=b"q=%3Cscript%3Ealert(1)%3C/script%3E")
    assert attack["status"] == 200
    assert "<script>alert(1)" not in attack["body"] and "&lt;script&gt;" in attack["body"]


# --- API reference ---------------------------------------------------------------


CLIENT_SOURCE = '''"""The HTTP client.

Longer text."""


class Client:
    """Talks to a server. See `fetch()` and `Client.close`."""

    def __init__(self, url: str) -> None:
        """Makes a client.

        Parameters
        ----------
        self : Client
            The instance.
        url : str
            Where to connect.
        """

    def close(self) -> None:
        """Closes it."""

    def _hidden(self):
        """Private."""


def fetch(url: str, *, timeout: float = 3.0) -> bytes:
    """Gets `url` with a `Client`."""


def _private() -> None:
    pass
'''


@pytest.fixture
def api_docs(tmp_path):
    """A tiny package `demo` with two sub-packages and a docs folder grouping them."""
    src = tmp_path / "src" / "demo"
    (src / "web").mkdir(parents=True)
    (src / "tools").mkdir()
    for init in (src / "__init__.py", src / "web" / "__init__.py", src / "tools" / "__init__.py"):
        init.write_text("")
    (src / "web" / "client.py").write_text(CLIENT_SOURCE)
    (src / "tools" / "cli.py").write_text('"""Command line helpers."""\n\n\ndef main() -> None:\n    """Runs it."""\n')
    root = tmp_path / "docs"
    root.mkdir()
    (root / "index.md").write_text("# Home\n\nSee the guide for a long enough first paragraph here.\n")
    (root / "nav.toml").write_text(
        '[[section]]\ntitle = ""\npages = ["index.md"]\n\n[api]\ntitle = "Reference"\ndescription = "All of it."\n\n'
        '[[api.group]]\ntitle = "Web"\ndescription = "Talking HTTP."\nmodules = ["demo.web.client"]\n\n'
        '[[api.group]]\ntitle = "Tools"\nmodules = ["demo.tools.cli"]\n')
    return root, tmp_path / "src"


def _api(root, src, **kw):
    return Docs(root, api_package="demo", api_path=src, **kw)


def test_api_groups_index_page_and_order(api_docs):
    docs = _api(*api_docs)
    assert docs.build() == []
    index = docs.pages["api/"]
    assert "Talking HTTP." in index.html and 'href="/docs/api/demo.web.client/"' in index.html
    assert "The HTTP client." in index.html  # each module is described by its summary
    assert [h[1] for h in index.headings] == ["Web", "Tools"]
    assert docs.order == [""] + ["api/", "api/demo.web.client/", "api/demo.tools.cli/"]
    api = docs.sections[-1]
    assert api["title"] == "Reference" and [g["title"] for g in api["groups"]] == ["Web", "Tools"]
    assert docs.pages["api/demo.web.client/"].group == "Web"


def test_api_page_is_scannable_and_hides_private_names(api_docs):
    docs = _api(*api_docs)
    docs.build()
    page = docs.pages["api/demo.web.client/"]
    assert "In this module" in page.html and "_hidden" not in page.html and "_private" not in page.html
    assert "<th>Name</th><th>Type</th><th>Description</th>" in page.html
    assert "def fetch(url: str, *, timeout: float = 3.0) -&gt; bytes" in page.html
    assert "self" not in page.html.split("def __init__")[1].split("</section>")[0]  # no self in signature or table
    assert [(h[0], h[1]) for h in page.headings] == [(2, "Client"), (3, "Client.__init__"), (3, "Client.close"), (2, "fetch")]
    assert page.headings[0][2] == "demo-web-client-client"  # anchors keep the full path


def test_api_docstrings_link_to_documented_symbols(api_docs):
    docs = _api(*api_docs)
    docs.build()
    html = docs.pages["api/demo.web.client/"].html
    assert '<a class="api-ref" href="/docs/api/demo.web.client/#demo-web-client-fetch"><code>fetch()</code></a>' in html
    assert 'href="/docs/api/demo.web.client/#demo-web-client-client-close"' in html
    assert 'href="/docs/api/demo.web.client/#demo-web-client-client"><code>Client</code>' in html


def test_old_flat_modules_list_still_works_and_is_grouped(api_docs):
    root, src = api_docs
    (root / "nav.toml").write_text(
        '[[section]]\ntitle = ""\npages = ["index.md"]\n\n[api]\nmodules = ["demo.web.client", "demo.tools.cli"]\n')
    docs = _api(root, src)
    assert docs.build() == []
    assert [g["title"] for g in docs.sections[-1]["groups"]] == ["Web", "Tools"]
    assert "api/demo.tools.cli/" in docs.pages


def test_api_nav_problems_are_reported(api_docs):
    root, src = api_docs
    (root / "nav.toml").write_text(
        '[[section]]\ntitle = ""\npages = ["index.md"]\n\n[api]\n\n'
        '[[api.group]]\ntitle = "A"\nmodules = ["demo.web.client", "demo.web.nope", "other.pkg"]\n\n'
        '[[api.group]]\ntitle = "B"\nmodules = ["demo.web.client"]\n\n[[api.group]]\nmodules = ["demo.tools.cli"]\n')
    problems = _api(root, src).build()
    messages = [p.message for p in problems]
    assert any(p.source == "api:demo.web.nope" and "cannot document" in p.message for p in problems)
    assert "api module demo.web.client is listed twice" in messages
    assert "api module other.pkg is not in package demo" in messages
    assert any("needs a title and modules" in m for m in messages)


async def test_api_sidebar_opens_only_the_active_group_and_has_breadcrumbs(api_docs, make_app, call):
    root, src = api_docs
    app = make_app()
    _api(root, src, title="Demo", base_url="https://example.com").mount(app)
    body = (await call(app, "GET", "/docs/api/demo.tools.cli/"))["body"]
    assert '<details class="d-nav__group" open>\n            <summary>Tools</summary>' in body
    assert '<details class="d-nav__group">\n            <summary>Web</summary>' in body
    assert '<a href="/docs/api/">Reference</a>' in body and '<a href="/docs/api/#tools">Tools</a>' in body
    assert 'aria-current="page">demo.tools.cli</span>' in body
    assert '"@type": "BreadcrumbList"' in body or '"@type":"BreadcrumbList"' in body
    assert (await call(app, "GET", "/docs/api/"))["status"] == 200


async def test_search_covers_the_api(api_docs, make_app, call):
    root, src = api_docs
    app = make_app()
    _api(root, src, title="Demo").mount(app)
    found = (await call(app, "GET", "/docs/search", query=b"q=fetch"))["body"]
    assert "/docs/api/demo.web.client/#demo-web-client-fetch" in found


def test_api_cache_round_trips_groups(api_docs, tmp_path):
    cache = tmp_path / "c.json"
    first = _api(*api_docs, cache=cache)
    first.build_cached()
    second = _api(*api_docs, cache=cache)
    second.build_cached()
    assert second.sections == first.sections and second.pages["api/"].html == first.pages["api/"].html
    assert second.pages["api/demo.web.client/"].group == "Web"


# --- contrast ------------------------------------------------------------------


def _luminance(hex_colour: str) -> float:
    value = hex_colour.lstrip("#")
    channels = [int(value[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _vars(block: str) -> dict[str, str]:
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9A-Fa-f]{6})", block))


def test_theme_colour_pairs_meet_wcag_aa():
    css = THEME_CSS.read_text()
    light = _vars(css.split("@media (prefers-color-scheme: dark)")[0])
    dark = {**light, **_vars(css.split("@media (prefers-color-scheme: dark)")[1].split("}")[0])}
    pairs = [("text", "bg"), ("muted", "bg"), ("link", "bg"), ("text", "surface"), ("muted", "surface"),
             ("code-fg", "code-bg"), ("icode-fg", "icode-bg"), ("mark-fg", "mark-bg"), ("text", "admon-bg"),
             ("link", "admon-bg")]
    for scheme, palette in (("light", light), ("dark", dark)):
        for fg, bg in pairs:
            ratio = contrast(palette[fg], palette[bg])
            assert ratio >= 4.5, f"{scheme}: --{fg} on --{bg} is {ratio:.2f}:1"
    # Syntax colours on the code background (both schemes share the dark block).
    for token in re.findall(r"\.d-article pre \.[\w-]+[^{]*\{\s*color:\s*(#[0-9A-Fa-f]{6})", css):
        for code_bg in (light["code-bg"], dark["code-bg"]):
            assert contrast(token, code_bg) >= 4.5, f"token {token} on {code_bg}"


def test_cache_is_used_until_a_source_changes(tmp_path, monkeypatch):
    from ushka.docs import Docs

    (tmp_path / "index.md").write_text("# Home\n\nhello\n")
    cache = tmp_path / "out" / "docs.json"

    def make():
        return Docs(tmp_path, cache=cache)

    first = make()
    first.build_cached()
    assert cache.is_file()

    second = make()
    monkeypatch.setattr(Docs, "build", lambda *a, **k: (_ for _ in ()).throw(AssertionError("rebuilt")))
    second.build_cached()  # served from the cache: build() must not run
    assert second.pages[""].title == first.pages[""].title and second.pages[""].html == first.pages[""].html
    monkeypatch.undo()

    (tmp_path / "index.md").write_text("# Changed\n\nhello\n")
    third = make()
    third.build_cached()
    assert third.pages[""].title == "Changed"


def test_corrupt_or_unwritable_cache_falls_back_to_building(tmp_path):
    from ushka.docs import Docs

    (tmp_path / "index.md").write_text("# Home\n")
    cache = tmp_path / "docs.json"
    cache.write_text("{not json")
    docs = Docs(tmp_path, cache=cache)
    docs.build_cached()
    assert docs.pages[""].title == "Home"
    blocker = tmp_path / "file"
    blocker.write_text("x")
    Docs(tmp_path, cache=blocker / "docs.json").build_cached()  # parent is a file: ignored, no crash
