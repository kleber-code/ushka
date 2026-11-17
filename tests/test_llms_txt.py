"""docs/llms.txt is what an AI tool reads first: it must list every page and name only things that exist."""

import re
import sys
from pathlib import Path

import pytest

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent.parent
LLMS = (ROOT / "docs" / "llms.txt").read_text("utf-8")
BASE = "https://ushka.satela.com.br/docs/"


def _url(page: str) -> str:
    stem = page[:-3]
    if stem == "index":
        return ""
    return (stem[: -len("index")] if stem.endswith("/index") else stem + "/")


def test_every_page_of_the_navigation_is_listed():
    nav = tomllib.loads((ROOT / "docs" / "nav.toml").read_text("utf-8"))
    listed = set(re.findall(re.escape(BASE) + r"([^)\s]*)", LLMS))
    missing = [p for s in nav["section"] for p in s["pages"] if _url(p) not in listed]
    assert not missing, f"docs/llms.txt does not list: {missing}"


def test_every_listed_page_exists():
    nav = tomllib.loads((ROOT / "docs" / "nav.toml").read_text("utf-8"))
    pages = {_url(p) for s in nav["section"] for p in s["pages"]}
    listed = set(re.findall(re.escape(BASE) + r"([^)\s]*)", LLMS))
    unknown = [u for u in listed if u not in pages and not u.startswith("api")]
    assert not unknown, f"docs/llms.txt links to pages that do not exist: {unknown}"


def test_it_does_not_use_module_paths_that_moved():
    old = re.findall(r"ushka\.(?:seo|pwa|i18n|openapi|mcp|verify|utils|http\.sessions|http\.session_store|core\.exceptions)\b", LLMS)
    assert not old, f"old module paths in docs/llms.txt: {old}"


@pytest.mark.parametrize(
    "module,name",
    [
        ("ushka", "HTTPRedirect"),
        ("ushka", "UploadFile"),
        ("ushka", "ngettext"),
        ("ushka", "_"),
        ("ushka", "Form"),
        ("ushka.sessions", "revoke_user_sessions"),
        ("ushka.testing", "TestClient"),
        ("ushka.api.mcp", "tool"),
        ("ushka.http.exceptions", "HTTPForbidden"),
    ],
)
def test_names_the_file_tells_you_to_import_exist(module, name):
    import importlib

    assert hasattr(importlib.import_module(module), name)
    assert name in LLMS or name == "_"


def test_the_commands_it_mentions_exist():
    from ushka.cli import build_parser

    parser = build_parser()
    choices = next(a for a in parser._actions if getattr(a, "choices", None)).choices
    for command in ("new", "dev", "run", "check", "config", "session", "verify", "docs", "routes", "db", "i18n"):
        assert command in choices, command
        assert f"`ushka {command}" in LLMS or command in LLMS.split("[CLI]")[1].split("\n")[0], command
    for flag in ("--as-session", "--describe"):
        assert flag in LLMS
    db = choices["db"]._subparsers._group_actions[0].choices
    assert "inspect" in db and "check-models" in db


def test_every_setting_section_it_names_is_real():
    from ushka.core.settings import SCHEMA

    for section in re.findall(r"`\[(\w+)\]", LLMS):
        assert section in SCHEMA or section in {"myapp"}, f"[{section}] is not a settings section"
    for pair in re.findall(r"`\[(\w+)\] (\w+)", LLMS):
        section, key = pair
        assert key in SCHEMA.get(section, {}), f"[{section}] {key} is not a setting"
