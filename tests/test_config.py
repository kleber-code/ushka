"""Tests for `ushka.core.config.Config`."""

import tomlkit

from ushka.core.config import Config


def test_creates_a_parsable_toml_file(workdir):
    """A missing `ushka.toml` is generated and can be read back.

    Regression test: the generated file used multi-line `tomlkit` comments,
    which newer tomlkit releases reject with
    ``ValueError: Comment cannot contain line breaks``.
    """
    config = Config(workdir).load_from_file()

    path = workdir / "ushka.toml"
    assert path.exists()

    document = tomlkit.parse(path.read_text(encoding="utf-8"))
    assert document["database"]["url"] == "sqlite:///ushka.db"
    assert document["app"]["name"] == "Ushka App"
    assert config.DATABASE_URL == "sqlite:///ushka.db"


def test_generated_comments_are_single_line(workdir):
    """Every comment written to `ushka.toml` stays on its own line."""
    Config(workdir).load_from_file()

    content = (workdir / "ushka.toml").read_text(encoding="utf-8")
    comment_lines = [
        line for line in content.splitlines() if line.lstrip().startswith("#")
    ]

    assert comment_lines
    assert "SYSTEM INFORMATION (Read-only)." in content
    assert "Database connection URL (SQLAlchemy format)." in content


def test_sections_are_mapped_to_uppercase_attributes(workdir):
    """`[app] debug = false` becomes `config.APP_DEBUG`."""
    config = Config(workdir).load_from_file()

    assert config.APP_DEBUG is False
    assert config.SERVER_PORT == 8000
    assert config.STATIC_URL == "/static"


def test_get_is_case_insensitive_and_supports_defaults(workdir):
    """`get()` uppercases the key and falls back to the given default."""
    config = Config(workdir).load_from_file()

    assert config.get("server_host") == "127.0.0.1"
    assert config.get("does_not_exist", "fallback") == "fallback"


def test_get_raises_for_required_missing_keys(workdir):
    """A required key that is absent raises `KeyError`."""
    config = Config(workdir).load_from_file()

    try:
        config.get("definitely_missing", required=True)
    except KeyError as exc:
        assert "DEFINITELY_MISSING" in str(exc)
    else:
        raise AssertionError("expected KeyError")


def test_missing_sections_are_merged_into_an_existing_file(workdir):
    """An outdated `ushka.toml` gains the sections it is missing."""
    (workdir / "ushka.toml").write_text('[app]\nname = "Kept"\n', encoding="utf-8")

    config = Config(workdir).load_from_file()

    assert config.APP_NAME == "Kept"
    assert config.SERVER_PORT == 8000
    assert "[limits]" in (workdir / "ushka.toml").read_text(encoding="utf-8")
