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
