"""Seo, Pwa, I18n, Google and GitHub as pieces: ``app.use(Pwa(...))``."""

import subprocess
import sys

import pytest

from ushka.auth import GitHub, Google, current_user
from ushka.testing import TestClient
from ushka.web import I18n, Pwa, Seo

BASE = "https://app.example.test"


def write(workdir, text):
    (workdir / "ushka.toml").write_text(text)


# -- Seo ---------------------------------------------------------------------------


async def test_seo_with_no_arguments_works(app, call):
    assert app.use(Seo()) is app.pieces["seo"]
    assert (await call(app, "GET", "/robots.txt"))["status"] == 200


async def test_seo_options_in_code_reach_the_sitemap_and_the_config(app, call):
    app.use(Seo(url="https://shop.example", description="Handmade", image="/s.png", sitemap_exclude=["/x/*"]))
    assert app.config.SEO_URL == "https://shop.example"
    assert app.config.SEO_DESCRIPTION == "Handmade" and app.config.SEO_IMAGE == "/s.png"
    assert "https://shop.example/sitemap.xml" in (await call(app, "GET", "/robots.txt"))["body"]


def test_seo_toml_and_environment_beat_code(workdir, make_app, monkeypatch):
    write(workdir, '[seo]\nurl = "https://toml.example"\n')
    app = make_app()
    app.use(Seo(url="https://code.example", description="code"))
    assert app.config.SEO_URL == "https://toml.example" and app.config.SEO_DESCRIPTION == "code"
    monkeypatch.setenv("USHKA_SEO_URL", "https://env.example")
    app.use(Seo(url="https://code.example"))
    assert app.config.SEO_URL == "https://env.example"


def test_seo_typo_is_a_type_error_with_a_suggestion(app):
    with pytest.raises(TypeError, match="did you mean 'description'"):
        app.use(Seo(descripton="x"))


def test_seo_keeps_sitemap_sources_registered_before_use(app):
    @app.sitemap_source
    def pages():
        return ["/a"]

    app.use(Seo(url="https://shop.example"))
    assert app._sitemap_sources == [pages]


async def test_seo_without_use_still_works_from_toml(workdir, make_app, call):
    write(workdir, '[seo]\nurl = "https://toml.example"\n')
    app = make_app()
    assert "https://toml.example/sitemap.xml" in (await call(app, "GET", "/robots.txt"))["body"]
    assert app.pieces == {}


# -- Pwa ---------------------------------------------------------------------------


async def test_pwa_with_no_arguments_turns_it_on(app, call):
    assert "/manifest.webmanifest" not in app._builtin_routes
    app.use(Pwa())
    assert app.config.PWA_ENABLE is True
    assert (await call(app, "GET", "/manifest.webmanifest"))["status"] == 200


async def test_pwa_options_make_the_manifest(app, call):
    app.use(Pwa(name="Shop", icons=["/static/i.png"], theme_color="#112233", display="fullscreen"))
    body = (await call(app, "GET", "/manifest.webmanifest"))["body"]
    assert '"name": "Shop"' in body and "#112233" in body and "/static/i.png" in body and "fullscreen" in body


def test_pwa_toml_and_environment_beat_code(workdir, make_app, monkeypatch):
    write(workdir, '[pwa]\nname = "From file"\n')
    app = make_app()
    app.use(Pwa(name="Code", theme_color="#abcdef"))
    assert app.config.PWA_NAME == "From file" and app.config.PWA_THEME_COLOR == "#abcdef"
    monkeypatch.setenv("USHKA_PWA_THEME_COLOR", "#000000")
    app.use(Pwa())
    assert app.config.PWA_THEME_COLOR == "#000000"


async def test_pwa_can_still_be_switched_off_by_the_file(workdir, make_app, call):
    write(workdir, "[pwa]\nenable = false\n")
    app = make_app()
    app.use(Pwa())
    assert "/manifest.webmanifest" not in app._builtin_routes


def test_pwa_typo(app):
    with pytest.raises(TypeError, match="theme_color"):
        app.use(Pwa(theme_colour="#fff"))


async def test_pwa_from_toml_only_still_works(workdir, make_app, call):
    write(workdir, '[pwa]\nenable = true\nname = "T"\n')
    assert (await call(make_app(), "GET", "/sw.js"))["status"] == 200


# -- I18n --------------------------------------------------------------------------


def test_i18n_with_no_arguments_turns_it_on(app):
    assert app.i18n.enabled is False
    app.use(I18n())
    assert app.i18n.enabled is True and app.i18n.default == "en"


def test_i18n_locales_and_default(app):
    app.use(I18n(locales=["en", "pt"], default="pt"))
    assert app.config.I18N_DEFAULT_LOCALE == "pt"
    assert app.i18n.default == "pt" and set(app.i18n.locales) == {"pt", "en"}


async def test_i18n_picks_the_language_of_the_request(app, call):
    app.use(I18n(locales=["en", "pt"]))

    @app.get("/lang")
    async def lang(request):
        return request.locale

    assert (await call(app, "GET", "/lang", headers={"accept-language": "pt-BR"}))["body"] == "pt"


def test_i18n_toml_and_environment_beat_code(workdir, make_app, monkeypatch):
    write(workdir, '[i18n]\ndefault_locale = "fr"\n')
    app = make_app()
    app.use(I18n(locales=["en", "fr"], default="en"))
    assert app.i18n.default == "fr"
    monkeypatch.setenv("USHKA_I18N_DEFAULT_LOCALE", "en")
    app.use(I18n(default="fr"))
    assert app.i18n.default == "en"


def test_i18n_typo_and_option_names(app):
    with pytest.raises(TypeError, match="did you mean 'locales'"):
        app.use(I18n(locale=["en"]))
    app.use(I18n(query_param="l"))
    assert app.i18n.query_param == "l"


def test_the_old_runtime_signature_still_builds_a_translator(workdir, app):
    from ushka.web.i18n import Translator

    assert isinstance(I18n(app.config, workdir), Translator)


def test_i18n_from_toml_only_still_works(workdir, make_app):
    write(workdir, '[i18n]\nenable = true\nlocales = ["en", "pt"]\n')
    assert make_app().i18n.enabled


# -- Google and GitHub -------------------------------------------------------------


@pytest.fixture
def oauth_env(monkeypatch):
    for k, v in {
        "USHKA_APP_SECRET_KEY": "k" * 48,
        "USHKA_OAUTH_GOOGLE_CLIENT_ID": "env-google-id",
        "USHKA_OAUTH_GOOGLE_CLIENT_SECRET": "secret-g",
        "USHKA_OAUTH_GITHUB_CLIENT_SECRET": "secret-h",
        "USHKA_OAUTH_REDIRECT_BASE": BASE,
    }.items():
        monkeypatch.setenv(k, v)


async def test_google_with_no_arguments_takes_the_environment(oauth_env, app, call):
    app.use(Google())
    resp = await call(app, "GET", "/auth/google/login")
    assert resp["status"] == 302 and "client_id=env-google-id" in resp["headers"]["location"]


async def test_id_in_code_and_domains_shortcut(oauth_env, monkeypatch, app, call):
    monkeypatch.delenv("USHKA_OAUTH_GOOGLE_CLIENT_ID")
    app.use(Google(client_id="code-id", allowed_domains=["empresa.com"]))
    assert app.config.OAUTH_ALLOWED_EMAIL_DOMAINS == ["empresa.com"]
    assert "client_id=code-id" in (await call(app, "GET", "/auth/google/login"))["headers"]["location"]


async def test_google_and_github_together(oauth_env, monkeypatch, app, call):
    monkeypatch.setenv("USHKA_OAUTH_GITHUB_CLIENT_SECRET", "secret-h")
    assert "/auth/github/login" not in app._builtin_routes
    assert app.use(Google(), GitHub(client_id="gh-id")) == (app.pieces["google"], app.pieces["github"])
    for name in ("google", "github"):
        assert (await call(app, "GET", f"/auth/{name}/login"))["status"] == 302


def test_environment_beats_the_id_in_code(oauth_env, app):
    app.use(Google(client_id="code-id"))
    assert app.config.OAUTH_GOOGLE_CLIENT_ID == "env-google-id"


def test_toml_beats_the_id_in_code(oauth_env, monkeypatch, workdir, make_app):
    monkeypatch.delenv("USHKA_OAUTH_GOOGLE_CLIENT_ID")
    write(workdir, '[oauth]\ngoogle_client_id = "toml-id"\n')
    app = make_app()
    app.use(Google(client_id="code-id"))
    assert app.config.OAUTH_GOOGLE_CLIENT_ID == "toml-id"


def test_a_secret_in_code_is_refused(oauth_env, app):
    with pytest.raises(TypeError, match="USHKA_OAUTH_GOOGLE_CLIENT_SECRET"):
        app.use(Google(client_id="x", client_secret="hunter2"))


def test_oauth_typo(oauth_env, app):
    with pytest.raises(TypeError, match="did you mean 'after_login'"):
        app.use(Google(after_logn="/"))


def test_option_passthrough(oauth_env, app):
    app.use(Google(after_login="/home", login_prefix="/entrar"))
    assert app.config.OAUTH_AFTER_LOGIN == "/home" and app.config.OAUTH_LOGIN_PREFIX == "/entrar"


@pytest.fixture
def late_credentials(monkeypatch, make_app):
    """An app built before the secret exists, in production mode and with no public address."""
    monkeypatch.setenv("USHKA_APP_DEBUG", "false")
    monkeypatch.setenv("USHKA_APP_SECRET_KEY", "k" * 48)
    app = make_app()
    monkeypatch.setenv("USHKA_OAUTH_GOOGLE_CLIENT_SECRET", "secret-g")
    return app


async def test_the_redirect_address_is_checked_at_startup_so_seo_can_come_later(late_credentials):
    late_credentials.use(Google(client_id="id"), Seo(url=BASE))
    async with TestClient(late_credentials):
        pass


async def test_without_any_trusted_address_startup_fails(late_credentials):
    late_credentials.use(Google(client_id="id"))
    with pytest.raises(RuntimeError, match="trusted address"):
        async with TestClient(late_credentials):
            pass


def test_providers_keep_their_old_constructor_and_repr():
    g = Google("id", "very-secret")
    assert g.client_id == "id" and "very-secret" not in repr(g)


async def test_login_helpers_still_work(oauth_env, app):
    app.use(Google())

    @app.get("/me")
    async def me(request):
        return str(current_user(request))

    async with TestClient(app) as client:
        assert (await client.get("/me")).text == "None"


# -- lazy imports ------------------------------------------------------------------


def test_import_ushka_does_not_import_auth():
    code = "import sys, ushka; print('ushka.auth' in sys.modules)"
    assert subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip() == "False"


def test_importing_the_web_package_imports_no_piece():
    code = "import sys, ushka.web; print([m for m in ('ushka.auth', 'ushka.web.seo_x') if m in sys.modules])"
    assert subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip() == "[]"


def test_web_pieces_resolve_lazily_and_unknown_names_fail():
    from ushka import web

    assert web.Seo.__name__ == "Seo" and web.Pwa.__name__ == "Pwa" and web.I18n.__name__ == "I18n"
    with pytest.raises(AttributeError):
        getattr(web, "Nope")
