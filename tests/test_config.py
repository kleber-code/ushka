"""Tests for `ushka.core.config.Config`: defaults < ushka.toml < .env < environment."""

import pytest

from ushka.core.config import Config, parse_dotenv


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("USHKA_APP_DEBUG", "USHKA_APP_SECRET_KEY", "USHKA_DATABASE_URL",
                 "DATABASE_URL", "USHKA_DB_URL", "USHKA_SERVER_PORT"):
        monkeypatch.delenv(name, raising=False)


def test_defaults_without_any_file(workdir):
    config = Config(workdir).load_from_file()
    assert config.APP_DEBUG is False
    assert config.SERVER_PORT == 8000
    assert config.DATABASE_URL == "sqlite:///ushka.db"
    assert config.source_of("server_port") == "default"


def test_the_config_file_is_never_created_or_rewritten(workdir):
    Config(workdir).load_from_file()
    assert not (workdir / "ushka.toml").exists()

    original = '[app]\nname = "Kept"  # my comment\n'
    (workdir / "ushka.toml").write_text(original, encoding="utf-8")
    Config._instance, Config._initialized = None, False
    config = Config(workdir).load_from_file()
    assert config.APP_NAME == "Kept"
    assert config.SERVER_PORT == 8000  # missing keys come from the defaults
    assert (workdir / "ushka.toml").read_text(encoding="utf-8") == original


def test_get_is_case_insensitive_and_supports_defaults(workdir):
    config = Config(workdir).load_from_file()
    assert config.get("server_host") == "127.0.0.1"
    assert config.get("does_not_exist", "fallback") == "fallback"
    with pytest.raises(KeyError, match="DEFINITELY_MISSING"):
        config.get("definitely_missing", required=True)


def test_environment_overrides_with_type_conversion(workdir, monkeypatch):
    (workdir / "ushka.toml").write_text("[server]\nport = 9000\n", encoding="utf-8")
    monkeypatch.setenv("USHKA_SERVER_PORT", "7000")
    monkeypatch.setenv("USHKA_APP_DEBUG", "yes")
    config = Config(workdir).load_from_file()
    assert config.SERVER_PORT == 7000
    assert config.APP_DEBUG is True
    assert config.source_of("server_port") == "environment"


def test_invalid_boolean_in_environment_is_an_error(workdir, monkeypatch):
    monkeypatch.setenv("USHKA_APP_DEBUG", "maybe")
    with pytest.raises(ValueError, match="USHKA_APP_DEBUG"):
        Config(workdir).load_from_file()


def test_dotenv_is_read_but_environment_wins(workdir, monkeypatch):
    (workdir / ".env").write_text(
        "# secrets\nUSHKA_APP_SECRET_KEY='from-dotenv'\nexport USHKA_SERVER_PORT=8100\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("USHKA_SERVER_PORT", "8200")
    config = Config(workdir).load_from_file()
    assert config.APP_SECRET_KEY == "from-dotenv"
    assert config.source_of("app_secret_key") == ".env"
    assert config.SERVER_PORT == 8200


@pytest.mark.parametrize("name", ["DATABASE_URL", "USHKA_DB_URL", "USHKA_DATABASE_URL"])
def test_database_url_aliases(workdir, monkeypatch, name):
    monkeypatch.setenv(name, "postgresql://u:p@h/db")
    assert Config(workdir).load_from_file().DATABASE_URL == "postgresql://u:p@h/db"


def test_secret_key_is_generated_only_in_debug(workdir, monkeypatch):
    assert Config(workdir).load_from_file().APP_SECRET_KEY == ""

    Config._instance, Config._initialized = None, False
    monkeypatch.setenv("USHKA_APP_DEBUG", "true")
    config = Config(workdir).load_from_file()
    assert len(config.APP_SECRET_KEY) >= 32
    assert config.source_of("app_secret_key").startswith("generated")


def test_invalid_toml_reports_the_file(workdir):
    (workdir / "ushka.toml").write_text("[app\n", encoding="utf-8")
    with pytest.raises(ValueError, match="ushka.toml"):
        Config(workdir).load_from_file()


def test_parse_dotenv():
    assert parse_dotenv('A=1\n# c\nB="two words"\nC=x # note\n\nexport D=4\nbad line\n') == {
        "A": "1",
        "B": "two words",
        "C": "x",
        "D": "4",
    }
