"""Translations: language choice, gettext catalogs, templates, the .po compiler and the CLI."""

import asyncio
import gettext
import shutil
import sys
import subprocess

import pytest

from ushka import render
from ushka.web.i18n import LazyString, get_locale, lazy_gettext, parse_accept_language
from ushka.web.i18n import gettext as _t
from ushka.web.i18n import ngettext as _n
from ushka.web.i18n import tools

PO = r'''# Portuguese
msgid ""
msgstr ""
"Content-Type: text/plain; charset=UTF-8\n"
"Plural-Forms: nplurals=2; plural=(n > 1);\n"

msgid "Welcome"
msgstr "Bem-vindo"

msgid "Hello %(name)s"
msgstr "Olá %(name)s"

msgid "Saved"
msgstr "Salvo"

msgid "%(num)d item"
msgid_plural "%(num)d items"
msgstr[0] "%(num)d item"
msgstr[1] "%(num)d itens"

msgctxt "menu"
msgid "File"
msgstr "Arquivo"

#, fuzzy
msgid "Maybe"
msgstr "Talvez"

msgid "Untranslated"
msgstr ""

msgid "Multi "
"line"
msgstr "Várias "
"linhas\tcom \"aspas\""
'''

PAGE = """<html lang="{{ lang }}"><head>{{ seo() }}</head><body>
<h1>{{ _("Welcome") }}</h1>
<p>{% trans name=name %}Hello {{ name }}{% endtrans %}</p>
<p>{% trans count=n %}{{ count }} item{% pluralize %}{{ count }} items{% endtrans %}</p>
<p>{{ ngettext("%(num)d item", "%(num)d items", n) }}</p>
<p>{{ pgettext("menu", "File") }}</p>
<p>{{ _("Missing key") }}</p>
<i>{{ locale }}</i>
</body></html>"""


def _catalog(workdir, lang="pt_BR", po=PO, domain="messages"):
    folder = workdir / "locale" / lang / "LC_MESSAGES"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{domain}.po").write_text(po, "utf-8")
    tools.compile_po(folder / f"{domain}.po")
    return folder / f"{domain}.mo"


def _app(make_app, workdir, extra="", app_extra="", page=PAGE):
    (workdir / "templates").mkdir(exist_ok=True)
    (workdir / "templates" / "p.html").write_text(page)
    (workdir / "ushka.toml").write_text(
        f'[app]\nauto_discover = false\n{app_extra}\n[i18n]\nenable = true\ndefault_locale = "en"\nlocales = ["en", "pt-BR"]\n{extra}'
    )
    app = make_app()

    @app.get("/")
    async def home(request):
        return await render(request, "p.html", {"name": "<b>Ann</b>", "n": 2})

    @app.get("/py")
    async def py(request):
        return f"{_t('Saved')}|{_t('Hello %(name)s', name='Zed')}|{_n('%(num)d item', '%(num)d items', 3)}|{get_locale()}"

    return app


# -- choosing the language -----------------------------------------------------------


def test_accept_language_respects_q_values():
    assert parse_accept_language("pt-BR,pt;q=0.9,en;q=0.8,*;q=0.1") == ["pt-br", "pt", "en"]
    assert parse_accept_language("en;q=0.5, fr;q=0.9, de;q=0") == ["fr", "en"]
    assert parse_accept_language("en;q=abc, pt") == ["pt"]
    assert parse_accept_language("../../etc/passwd, en;q=0.2") == ["en"]
    assert parse_accept_language("") == []


async def test_query_beats_cookie_beats_header_beats_default(make_app, workdir, call):
    _catalog(workdir)
    app = _app(make_app, workdir)
    pt = "Bem-vindo"
    assert pt not in (await call(app, "GET", "/"))["body"]  # default: English source text
    assert pt in (await call(app, "GET", "/", headers={"accept-language": "pt-BR,en;q=0.5"}))["body"]
    assert pt in (await call(app, "GET", "/", headers={"cookie": "lang=pt-BR", "accept-language": "en"}))["body"]
    assert pt not in (await call(app, "GET", "/", headers={"cookie": "lang=pt-BR"}, query=b"lang=en"))["body"]
    assert pt in (await call(app, "GET", "/", headers={"cookie": "lang=en"}, query=b"lang=pt_br"))["body"]


async def test_header_picks_the_best_supported_language(make_app, workdir, call):
    _catalog(workdir)
    app = _app(make_app, workdir)
    headers = {"accept-language": "fr;q=1.0, pt-PT;q=0.8, en;q=0.1"}  # fr is unknown, pt-PT falls to pt-BR
    assert "Bem-vindo" in (await call(app, "GET", "/", headers=headers))["body"]


async def test_an_unsupported_or_hostile_language_is_ignored(make_app, workdir, call):
    _catalog(workdir)
    app = _app(make_app, workdir)
    for value in ("fr", "../../etc", "pt-BR/../../x", "%00", "a" * 500, "pt_BR\r\nX: 1"):
        response = await call(app, "GET", "/", query=("lang=" + value).encode().replace(b"\r\n", b"%0d%0a"))
        assert response["status"] == 200
        assert 'lang="en"' in response["body"], value
    odd = await call(app, "GET", "/", headers={"cookie": "lang=../../x", "accept-language": "xx"})
    assert 'lang="en"' in odd["body"]


async def test_the_chosen_language_is_remembered_in_a_cookie(make_app, workdir, call):
    app = _app(make_app, workdir)
    response = await call(app, "GET", "/", query=b"lang=pt-br")
    assert "lang=pt-BR" in response["headers"]["set-cookie"]  # the configured name, not the client's text
    assert "set-cookie" not in (await call(app, "GET", "/", headers={"cookie": "lang=pt-BR"}, query=b"lang=pt-BR"))["headers"]
    off = _app(make_app, workdir, "remember = false\n")
    assert "set-cookie" not in (await call(off, "GET", "/", query=b"lang=pt-br"))["headers"]


async def test_the_order_is_configurable(make_app, workdir, call):
    _catalog(workdir)
    app = _app(make_app, workdir, 'order = ["header"]\n')
    body = (await call(app, "GET", "/", query=b"lang=pt-BR"))["body"]
    assert "Bem-vindo" not in body  # the query is not consulted


# -- translating -----------------------------------------------------------------------


async def test_templates_translate_with_plural_context_and_fallback(make_app, workdir, call):
    _catalog(workdir)
    app = _app(make_app, workdir)
    html = (await call(app, "GET", "/", query=b"lang=pt-BR"))["body"]
    assert "<h1>Bem-vindo</h1>" in html
    assert "<p>2 itens</p>" in html  # ngettext, catalog plural rule
    assert "<p>Arquivo</p>" in html  # pgettext
    assert "Missing key" in html  # no entry: the message itself, no error
    assert '<html lang="pt-BR">' in html and "<i>pt_BR</i>" in html
    # {% trans %} with no catalog entry for its message falls back to the source text, plural included
    assert "<p>2 items</p>" in html


async def test_trans_variables_stay_escaped(make_app, workdir, call):
    _catalog(workdir)
    app = _app(make_app, workdir)
    for query in (b"", b"lang=pt-BR"):
        html = (await call(app, "GET", "/", query=query))["body"]
        assert "&lt;b&gt;Ann&lt;/b&gt;" in html
        assert "<b>Ann</b>" not in html
    assert "Olá &lt;b&gt;Ann&lt;/b&gt;" in (await call(app, "GET", "/", query=b"lang=pt-BR"))["body"]


async def test_python_code_uses_the_language_of_the_request(make_app, workdir, call):
    _catalog(workdir)
    app = _app(make_app, workdir)
    assert (await call(app, "GET", "/py", query=b"lang=pt-BR"))["body"] == "Salvo|Olá Zed|3 itens|pt-BR"
    assert (await call(app, "GET", "/py"))["body"] == "Saved|Hello Zed|3 items|en"
    assert _t("Saved") == "Saved" and get_locale() is None  # outside a request


async def test_concurrent_requests_do_not_share_a_language(make_app, workdir, call):
    _catalog(workdir)
    app = _app(make_app, workdir)

    @app.get("/slow")
    async def slow(request):
        before = _t("Saved")
        await asyncio.sleep(0.05)
        return f"{before}/{_t('Saved')}"

    results = await asyncio.gather(
        *[call(app, "GET", "/slow", query=b"lang=pt-BR" if i % 2 else b"lang=en") for i in range(10)]
    )
    assert [r["body"] for r in results] == ["Salvo/Salvo" if i % 2 else "Saved/Saved" for i in range(10)]


async def test_translate_helpers_and_lazy_strings(make_app, workdir, call):
    from ushka import ntranslate, translate

    _catalog(workdir)
    app = _app(make_app, workdir)
    title = lazy_gettext("Saved")
    assert isinstance(title, LazyString) and str(title) == "Saved"

    @app.get("/helpers")
    async def helpers(request):
        return f"{translate(request, 'Hello %(name)s', name='Bia')}|{ntranslate(request, '%(num)d item', '%(num)d items', 1)}|{title}"

    assert (await call(app, "GET", "/helpers", query=b"lang=pt-BR"))["body"] == "Olá Bia|1 item|Salvo"
    assert (await call(app, "GET", "/helpers"))["body"] == "Hello Bia|1 item|Saved"


async def test_disabled_i18n_passes_texts_through(make_app, workdir, call):
    (workdir / "templates").mkdir()
    (workdir / "templates" / "p.html").write_text('<html lang="{{ lang }}">{{ _("Welcome") }}')
    (workdir / "ushka.toml").write_text("[app]\nauto_discover = false\n")
    app = make_app()

    @app.get("/")
    async def home(request):
        return await render(request, "p.html", {})

    assert (await call(app, "GET", "/", query=b"lang=pt-BR"))["body"] == '<html lang="en">Welcome'


async def test_catalogs_are_cached_and_reloaded_in_debug(make_app, workdir, call):
    mo = _catalog(workdir)
    app = _app(make_app, workdir)
    assert (await call(app, "GET", "/py", query=b"lang=pt-BR"))["body"].startswith("Salvo")
    _catalog(workdir, po=PO.replace('"Salvo"', '"Gravado"'))
    assert (await call(app, "GET", "/py", query=b"lang=pt-BR"))["body"].startswith("Salvo")  # cached
    assert mo.exists()
    debug = _app(make_app, workdir, app_extra="debug = true\n")
    assert (await call(debug, "GET", "/py", query=b"lang=pt-BR"))["body"].startswith("Gravado")
    _catalog(workdir, po=PO.replace('"Salvo"', '"Guardado"'))
    import os

    os.utime(mo, ns=(mo.stat().st_atime_ns, mo.stat().st_mtime_ns + 5_000_000_000))
    assert (await call(debug, "GET", "/py", query=b"lang=pt-BR"))["body"].startswith("Guardado")


async def test_a_broken_catalog_is_ignored(make_app, workdir, call):
    folder = workdir / "locale" / "pt_BR" / "LC_MESSAGES"
    folder.mkdir(parents=True)
    (folder / "messages.mo").write_bytes(b"not a catalog")
    app = _app(make_app, workdir)
    assert (await call(app, "GET", "/py", query=b"lang=pt-BR"))["body"].startswith("Saved")


async def test_a_language_falls_back_to_its_base_catalog(make_app, workdir, call):
    _catalog(workdir, lang="pt")  # only pt exists, pt-BR is requested
    app = _app(make_app, workdir)
    assert (await call(app, "GET", "/py", query=b"lang=pt-BR"))["body"].startswith("Salvo")


def test_bad_settings_are_refused(make_app, workdir):
    (workdir / "ushka.toml").write_text('[i18n]\nenable = true\nlocales = ["en", "../x"]\n')
    with pytest.raises(ValueError, match="language code"):
        make_app()
    (workdir / "ushka.toml").write_text('[i18n]\nenable = true\ndomain = "../messages"\n')
    with pytest.raises(ValueError, match="domain"):
        make_app()


async def test_seo_follows_the_active_language(make_app, workdir, call):
    app = _app(make_app, workdir)
    assert '<meta property="og:locale" content="pt_BR">' in (await call(app, "GET", "/", query=b"lang=pt-BR"))["body"]
    # a bare language keeps [seo] locale when that is a variant of it
    assert '<meta property="og:locale" content="en_US">' in (await call(app, "GET", "/"))["body"]


# -- .po compiler, real .mo files ------------------------------------------------------


def test_the_compiler_output_is_read_by_the_standard_library(tmp_path):
    po = tmp_path / "x.po"
    po.write_text(PO, "utf-8")
    mo = tools.compile_po(po)
    t = gettext.GNUTranslations(open(mo, "rb"))
    assert t.gettext("Welcome") == "Bem-vindo"
    assert t.ngettext("%(num)d item", "%(num)d items", 5) == "%(num)d itens"
    assert t.ngettext("%(num)d item", "%(num)d items", 1) == "%(num)d item"
    assert t.pgettext("menu", "File") == "Arquivo"
    assert t.gettext("Multi line") == "Várias linhas\tcom \"aspas\""
    assert t.gettext("Maybe") == "Maybe"  # fuzzy entries are not used
    assert t.gettext("Untranslated") == "Untranslated"
    assert t.charset() == "UTF-8"


def test_a_malformed_po_names_the_line(tmp_path):
    po = tmp_path / "bad.po"
    po.write_text('msgid "a"\nmsgstr nope\n')
    with pytest.raises(ValueError, match="bad.po: line 2"):
        tools.compile_po(po)


@pytest.mark.skipif(shutil.which("msgfmt") is None, reason="GNU gettext is not installed")
def test_our_mo_matches_msgfmt_and_django_style_files_load(tmp_path, workdir):
    po = tmp_path / "django.po"
    po.write_text(PO, "utf-8")
    ours = gettext.GNUTranslations(open(tools.compile_po(po), "rb"))
    reference = tmp_path / "ref.mo"
    subprocess.run(["msgfmt", "-o", str(reference), str(po)], check=True)
    theirs = gettext.GNUTranslations(open(reference, "rb"))
    assert ours._catalog == theirs._catalog
    # a catalog produced by msgfmt (what Django ships) is used as it is
    folder = workdir / "locale" / "pt_BR" / "LC_MESSAGES"
    folder.mkdir(parents=True)
    (folder / "django.mo").write_bytes(reference.read_bytes())
    from ushka.core.config import Config
    from ushka.web.i18n import I18n

    (workdir / "ushka.toml").write_text('[i18n]\nenable = true\ndomain = "django"\nlocales = ["pt-BR"]\n')
    i18n = I18n(Config(workdir).load_from_file(), workdir)
    assert i18n.translations("pt-BR").gettext("Welcome") == "Bem-vindo"


# -- extraction and the CLI -------------------------------------------------------------


def test_extract_finds_python_and_template_messages(tmp_path):
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "a.html").write_text(
        '{{ _("Welcome") }}{% trans %}Plain {{ x }}{% endtrans %}{{ ngettext("one", "many", n) }}{{ pgettext("menu", "File") }}'
    )
    (tmp_path / "app.py").write_text(
        "from ushka import gettext as _, translate\n"
        "a = _('Saved')\nb = translate(request, 'Hello')\nc = _(variable)\nd = ngettext('x', 'xs', 2)\n"
    )
    found = {(m.context, m.msgid, m.plural) for m in tools.extract(tmp_path)}
    assert {("", "Welcome", ""), ("menu", "File", ""), ("", "one", "many"), ("", "Saved", ""), ("", "Hello", ""), ("", "x", "xs")} <= found
    assert any("Plain %(x)s" in m for _c, m, _p in found)
    assert not any(m == "variable" for _c, m, _p in found)
    pot = tools.write_pot(tools.extract(tmp_path))
    assert 'msgid_plural "many"' in pot and 'msgctxt "menu"' in pot and "#: app.py:2" in pot


def test_the_cli_extracts_then_compiles(workdir):
    (workdir / "templates").mkdir()
    (workdir / "templates" / "a.html").write_text('{{ _("Welcome") }}')
    run = lambda *a: subprocess.run(
        [sys.executable, "-c", "from ushka.cli import main; main()", "i18n", *a], cwd=workdir, capture_output=True, text=True
    )
    out = run("extract")
    assert out.returncode == 0, out.stderr
    pot = (workdir / "locale" / "messages.pot").read_text()
    assert 'msgid "Welcome"' in pot
    folder = workdir / "locale" / "pt" / "LC_MESSAGES"
    folder.mkdir(parents=True)
    (folder / "messages.po").write_text(pot.replace('msgid "Welcome"\nmsgstr ""', 'msgid "Welcome"\nmsgstr "Bem-vindo"'))
    assert run("compile").returncode == 0
    assert gettext.GNUTranslations(open(folder / "messages.mo", "rb")).gettext("Welcome") == "Bem-vindo"
    (folder / "messages.po").write_text("garbage")
    assert run("compile").returncode == 1
