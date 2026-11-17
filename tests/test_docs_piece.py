"""Ushka Docs as a piece: ``app.use(Docs("docs"))`` and a menu derived from the folders."""

from pathlib import Path

import pytest

pytest.importorskip("markdown_it")
pytest.importorskip("griffe")

from ushka.docs import Docs

REPO = Path(__file__).resolve().parent.parent


def write(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        file = root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text)
    return root


@pytest.fixture
def tree(tmp_path):
    return write(tmp_path / "docs", {
        "index.md": "# Welcome\n\nA first paragraph that is long enough to be a description.\n",
        "about.md": "# About us\n",
        "02-guide/index.md": "# The guide\n",
        "02-guide/10-routing.md": "# Routing\n",
        "02-guide/01-install.md": "# Install\n\nSee [routing](10-routing.md) and [about](../about.md).\n",
        "02-guide/zeta.md": "# Zeta\n",
        "02-guide/alpha.md": "---\ntitle: Alpha page\norder: 5\n---\n\nNo heading here.\n",
        "01-start/first.md": "# First\n",
        "extras/b.md": "# B\n",
        "extras/a.md": "no title at all\n",
        "_drafts/secret.md": "# Secret\n",
        "guide-notes/.hidden.md": "# Hidden\n",
        "guide-notes/_wip.md": "# Wip\n",
        "guide-notes/ok.md": "# Ok\n",
    })


def menu(docs):
    return [(s["title"], [docs.pages[u].title for u in s["urls"]]) for s in docs.sections]


def test_menu_comes_from_the_folders(tree):
    docs = Docs(tree)
    assert docs.build() == []
    assert menu(docs) == [
        ("", ["Welcome", "About us"]),
        ("Start", ["First"]),                                  # 01- sorts first; the number is not shown
        ("The guide", ["The guide", "Install", "Alpha page", "Routing", "Zeta"]),
        ("Extras", ["A", "B"]),                                # folder name, capitalised; alphabetical
        ("Guide Notes", ["Ok"]),
    ]


def test_urls_have_no_prefix_and_links_still_resolve(tree):
    docs = Docs(tree)
    assert docs.build() == []
    assert "guide/install/" in docs.pages and "start/first/" in docs.pages
    assert not any("01-" in u or "02-" in u for u in docs.pages)
    html = docs.pages["guide/install/"].html
    assert 'href="/docs/guide/routing/"' in html and 'href="/docs/about/"' in html
    assert docs.pages["guide/install/"].source == "02-guide/01-install.md"   # the file keeps its name


def test_hidden_files_and_folders_are_left_out(tree):
    docs = Docs(tree)
    docs.build()
    titles = {p.title for p in docs.pages.values()}
    assert not titles & {"Secret", "Hidden", "Wip"}


def test_title_is_front_matter_then_h1_then_the_name(tree):
    docs = Docs(tree)
    docs.build()
    assert docs.pages["guide/alpha/"].title == "Alpha page"
    assert docs.pages["about/"].title == "About us"
    assert docs.pages["extras/a/"].title == "A"
    write(tree, {"03-x/getting-started.md": "text\n"})
    docs = Docs(tree)
    docs.build()
    assert docs.pages["x/getting-started/"].title == "Getting Started"


def test_order_front_matter_beats_the_prefix_and_bad_values_are_reported(tmp_path):
    root = write(tmp_path, {
        "index.md": "# Home\n",
        "01-b.md": "---\norder: 9\n---\n# B\n",
        "02-a.md": "# A\n",
        "c.md": "---\norder: nope\n---\n# C\n",
    })
    docs = Docs(root)
    problems = docs.build()
    assert menu(docs) == [("", ["Home", "A", "B", "C"])]
    assert [p.source for p in problems] == ["c.md"]


def test_same_url_is_a_problem(tmp_path):
    root = write(tmp_path, {"index.md": "# Home\n", "01-a.md": "# A1\n", "a.md": "# A2\n"})
    assert any("same URL" in p.message for p in Docs(root).build())


def test_unlisted_pages_are_fine_without_nav(tree):
    assert not any("not listed" in p.message for p in Docs(tree).build())


def test_nav_toml_still_overrides_everything(tree):
    write(tree, {"nav.toml": '[[section]]\ntitle = "Only"\npages = ["02-guide/01-install.md", "about.md"]\n'})
    docs = Docs(tree)
    problems = docs.build()
    assert menu(docs) == [("Only", ["Install", "About us"])]
    assert "guide/install/" not in docs.pages and "02-guide/01-install/" in docs.pages  # no prefix magic
    assert any(p.message == "not listed in nav.toml" for p in problems)


# -- the API reference ---------------------------------------------------------------


@pytest.fixture
def project(tmp_path):
    src = tmp_path / "src" / "demo"
    for pkg in ("web", "tools", "_private"):
        (src / pkg).mkdir(parents=True)
        (src / pkg / "__init__.py").write_text("")
    (src / "__init__.py").write_text('"""Demo."""\n')
    (src / "web" / "client.py").write_text('"""HTTP client."""\n\n\ndef get() -> None:\n    """Gets."""\n')
    (src / "web" / "_hidden.py").write_text('"""No."""\n')
    (src / "tools" / "cli.py").write_text('"""CLI."""\n')
    (src / "top.py").write_text('"""Top level."""\n')
    write(tmp_path / "docs", {"index.md": "# Home\n"})
    return tmp_path


def test_api_shortcut_finds_the_package_and_groups_by_subpackage(project):
    docs = Docs(project / "docs", api="demo")
    assert docs.build() == []
    assert docs.api_path == project / "src"
    assert [(g["title"], g["modules"]) for g in docs.api_groups] == [
        ("Tools", ["demo.tools.cli"]), ("Web", ["demo.web.client"]), ("General", ["demo.top"])]
    assert "api/demo.web.client/" in docs.pages and "api/" in docs.pages
    assert menu(docs)[-1][0] == "API reference"


def test_api_shortcut_fails_clearly_when_the_package_is_missing(project):
    with pytest.raises(ValueError, match=r"Docs\(api='nothere'\).*api_path="):
        Docs(project / "docs", api="nothere").build()


def test_api_shortcut_uses_the_import_path(tmp_path, monkeypatch):
    lib = write(tmp_path / "lib", {"libpkg/__init__.py": '"""Lib."""\n', "libpkg/mod.py": '"""Mod."""\n'})
    monkeypatch.syspath_prepend(str(lib))
    root = write(tmp_path / "proj" / "docs", {"index.md": "# Home\n"})
    docs = Docs(root, api="libpkg")
    docs.build()
    assert docs.api_path == lib and "api/libpkg.mod/" in docs.pages


def test_old_api_arguments_still_work(project):
    docs = Docs(project / "docs", api_package="demo", api_path=project / "src")
    assert docs.build() == []
    assert "api/demo.web.client/" in docs.pages


def test_nav_toml_api_groups_win_over_the_automatic_ones(project):
    write(project / "docs", {"nav.toml": '[[section]]\ntitle = ""\npages = ["index.md"]\n\n[api]\ntitle = "Ref"\n\n'
                             '[[api.group]]\ntitle = "Just web"\nmodules = ["demo.web.client"]\n'})
    docs = Docs(project / "docs", api="demo")
    assert docs.build() == []
    assert [g["title"] for g in docs.api_groups] == ["Just web"] and docs.sections[-1]["title"] == "Ref"


# -- constructor, docs.toml ----------------------------------------------------------


def test_constructor_takes_the_old_options_and_refuses_typos():
    docs = Docs("docs", logo="/l.png", og_image="/o.png", links=[("A", "/a")], edit_url="e/", home_url="/h",
                extra_css=["/c.css"], cache_control="no-store", base_url="https://x.org/", nav="menu.toml",
                api_package="p", api_path="lib")
    assert (docs.logo, docs.og_image, docs.links) == ("/l.png", "/o.png", [("A", "/a")])
    assert (docs.edit_url, docs.home_url, docs.extra_css) == ("e/", "/h", ["/c.css"])
    assert (docs.cache_control, docs.base_url, docs.nav_file) == ("no-store", "https://x.org", "menu.toml")
    assert (docs.api_package, docs.api_path) == ("p", Path("lib"))
    assert Docs(directory="old").directory == Path("old")
    assert Docs().directory == Path("docs") and Docs().title == "Documentation"
    with pytest.raises(TypeError, match="did you mean 'og_image'"):
        Docs("docs", og_imag="x")


def test_docs_toml_sets_the_brand_and_the_constructor_wins(tmp_path):
    root = write(tmp_path, {
        "index.md": "# Home\n",
        "docs.toml": 'title = "From file"\nlogo = "/file.png"\nbase_url = "https://file.org/"\n'
                     'edit_url = "https://git/edit/"\nextra_css = ["/a.css"]\n'
                     'links = [["GitHub", "https://github.com/x"], {label = "Blog", url = "/blog"}]\n',
    })
    docs = Docs(root, logo="/code.png")
    assert docs.build() == []
    assert docs.title == "From file" and docs.logo == "/code.png"
    assert docs.base_url == "https://file.org" and docs.extra_css == ["/a.css"]
    assert docs.links == [("GitHub", "https://github.com/x"), ("Blog", "/blog")]
    mine = Docs(root, title="Mine")
    assert mine.build() == [] and mine.title == "Mine"


def test_docs_toml_problems_are_reported_and_ignored(tmp_path):
    root = write(tmp_path, {"index.md": "# Home\n", "docs.toml": 'colour = "red"\nlogo = 3\nlinks = "x"\n'})
    docs = Docs(root)
    messages = [p.message for p in docs.build()]
    assert len(messages) == 3 and docs.logo is None and docs.links == []
    write(root, {"docs.toml": "= broken"})
    assert "cannot read it" in Docs(root).build()[0].message


async def test_docs_toml_is_not_served(tmp_path, make_app, call):
    root = write(tmp_path / "docs", {"index.md": "# Home\n", "docs.toml": 'title = "T"\n'})
    app = make_app()
    app.use(Docs(root))
    assert (await call(app, "GET", "/docs/docs.toml"))["status"] == 404


# -- the piece ------------------------------------------------------------------------


async def test_use_and_mount_give_the_same_site(tree, make_app, call):
    used, mounted = make_app(), make_app()
    piece = Docs(tree, title="T")
    assert used.use(piece) is piece and used.pieces["docs"] is piece
    Docs(tree, title="T").mount(mounted)
    for path, query in (("/docs/", b""), ("/docs/guide/install/", b""), ("/docs/search", b"q=routing")):
        a, b = await call(used, "GET", path, query=query), await call(mounted, "GET", path, query=query)
        assert a["status"] == b["status"] == 200, (path, a["status"], b["status"])
        assert a["body"] == b["body"]
    body = (await call(used, "GET", "/docs/guide/install/"))["body"]
    assert "Install" in body and "Alpha page" in body and "Start" in body
    assert (await call(used, "GET", "/docs/_drafts/secret/"))["status"] == 404


async def test_zero_argument_piece_uses_the_docs_folder(tmp_path, make_app, call, monkeypatch):
    write(tmp_path / "docs", {"index.md": "# Hi\n\nWelcome to the docs of this project, written for you.\n"})
    monkeypatch.chdir(tmp_path)
    app = make_app()
    app.use(Docs())
    assert "Hi" in (await call(app, "GET", "/docs/"))["body"]


async def test_hidden_files_are_not_served_even_if_they_are_assets(tmp_path, make_app, call):
    root = write(tmp_path / "docs", {"index.md": "# Home\n", "_notes.txt": "x", ".env.json": "{}", "ok.txt": "fine"})
    app = make_app()
    app.use(Docs(root))
    assert (await call(app, "GET", "/docs/ok.txt"))["status"] == 200
    assert (await call(app, "GET", "/docs/_notes.txt"))["status"] == 404
    assert (await call(app, "GET", "/docs/.env.json"))["status"] == 404


# -- the cache, on by default -----------------------------------------------------------


def test_cache_is_on_by_default_and_follows_the_sources(tmp_path, make_app, monkeypatch):
    root = write(tmp_path / "docs", {"index.md": "# One\n"})
    monkeypatch.chdir(tmp_path)
    app = make_app()
    piece = Docs(root)
    app.use(piece)
    assert piece.cache is not None and piece.cache.is_file() and piece.cache.parent == tmp_path / ".cache"

    again = Docs(root)
    monkeypatch.setattr(Docs, "build", lambda *a, **k: (_ for _ in ()).throw(AssertionError("rebuilt")))
    again.mount(make_app())
    assert again.pages[""].title == "One"
    monkeypatch.undo()

    write(root, {"index.md": "# Two\n"})
    changed = Docs(root)
    changed.mount(make_app())
    assert changed.pages[""].title == "Two"


def test_moving_a_page_between_folders_rebuilds_the_cache(tmp_path, make_app, monkeypatch):
    root = write(tmp_path / "docs", {"index.md": "# Home\n", "a/page.md": "# P\n", "b/other.md": "# O\n"})
    monkeypatch.chdir(tmp_path)
    Docs(root).mount(make_app())
    (root / "a" / "page.md").rename(root / "b" / "page.md")
    docs = Docs(root)
    docs.mount(make_app())
    assert "b/page/" in docs.pages and "a/page/" not in docs.pages


def test_cache_can_be_turned_off_and_an_unwritable_place_is_ignored(tmp_path, make_app, monkeypatch):
    root = write(tmp_path / "docs", {"index.md": "# Home\n"})
    monkeypatch.chdir(tmp_path)
    off = Docs(root, cache=False)
    off.mount(make_app())
    assert off.cache is None and not (tmp_path / ".cache").exists()

    (tmp_path / ".cache").write_text("a file, not a folder")  # cannot be created as a directory
    blocked = Docs(root)
    blocked.mount(make_app())
    assert blocked.pages[""].title == "Home"


def test_docs_toml_change_invalidates_the_cache(tmp_path, make_app, monkeypatch):
    root = write(tmp_path / "docs", {"index.md": "# Home\n", "docs.toml": 'logo = "/a.png"\n'})
    monkeypatch.chdir(tmp_path)
    Docs(root).mount(make_app())
    write(root, {"docs.toml": 'logo = "/b.png"\n'})
    docs = Docs(root)
    docs.mount(make_app())
    assert docs.logo == "/b.png"


# -- the site and the command ------------------------------------------------------------


def test_the_ushka_site_mounts_with_the_short_form():
    import importlib.util

    spec = importlib.util.spec_from_file_location("ushka_site_app", REPO / "site" / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    docs = module.docs
    assert module.app.pieces["docs"] is docs
    assert docs.problems == [] and docs.title == "Ushka" and docs.base_url == module.ORIGIN
    assert "guide/guard/" in docs.pages and "api/ushka.guard.safe/" in docs.pages
    assert docs.sections[0]["title"] == "" and docs.sections[1]["title"] == "Get started"


def test_ushka_docs_check_is_clean_with_and_without_nav(tmp_path, monkeypatch):
    import shutil

    from ushka.cli.commands import docs as command

    monkeypatch.chdir(REPO)
    assert command.check("docs", "ushka", None) == 0
    copy = tmp_path / "docs"
    shutil.copytree(REPO / "docs", copy)
    (copy / "nav.toml").unlink()
    assert command.check(str(copy), "ushka", str(REPO / "src")) == 0
