"""Options given in code (app.use(Seo(url=...))) sit between the defaults and ushka.toml."""

import pytest

from ushka.core.config import Config


def test_code_sets_the_default_and_says_so(workdir):
    config = Config(workdir).load_from_file()
    assert config.get("seo_url") == "" and config.source_of("seo_url") == "default"
    config.defaults("seo", url="https://example.com", description="Hi")
    assert config.get("seo_url") == "https://example.com" and config.source_of("seo_url") == "code"
    assert config.get("seo_description") == "Hi" and config.get("seo_site_name") == ""


def test_the_file_and_the_environment_win_over_code(workdir, monkeypatch):
    (workdir / "ushka.toml").write_text('[seo]\nurl = "https://from-file.example"\ndescription = "file"\n')
    config = Config(workdir).load_from_file()
    config.defaults("seo", url="https://code.example", description="code", site_name="Shop")
    assert config.get("seo_url") == "https://from-file.example" and config.source_of("seo_url") == "ushka.toml"
    assert config.get("seo_site_name") == "Shop" and config.source_of("seo_site_name") == "code"
    monkeypatch.setenv("USHKA_SEO_DESCRIPTION", "env")
    config.load_from_file()
    assert config.get("seo_description") == "env" and config.source_of("seo_description") == "environment"


def test_later_calls_add_to_earlier_ones(workdir):
    config = Config(workdir).load_from_file()
    config.defaults("pwa", name="A")
    config.defaults("pwa", short_name="B")
    config.defaults("pwa", name="C")
    assert (config.get("pwa_name"), config.get("pwa_short_name")) == ("C", "B")


def test_a_typo_is_refused_with_a_suggestion(workdir):
    config = Config(workdir).load_from_file()
    with pytest.raises(TypeError, match=r"descripton is not a Ushka setting.*did you mean 'description'"):
        config.defaults("seo", descripton="x")
    with pytest.raises(TypeError, match="should be true/false"):
        config.defaults("seo", jsonld="yes")
    with pytest.raises(TypeError, match="not a settings section"):
        config.defaults("nope", a=1)


def test_a_secret_cannot_be_set_in_code(workdir):
    config = Config(workdir).load_from_file()
    with pytest.raises(TypeError, match="USHKA_OAUTH_GOOGLE_CLIENT_SECRET in the environment"):
        config.defaults("oauth", google_client_secret="hunter2")
    assert config.get("oauth_google_client_secret") == ""
