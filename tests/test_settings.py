"""Nothing is hidden: every setting is declared, documented and written by `ushka new`."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

from ushka.core.config import Config
from ushka.core.settings import (
    DEFAULTS,
    RUNTIME,
    SCHEMA,
    SECTION_DOCS,
    SECTIONS,
    problems_in,
    render_markdown,
    render_toml,
)

ROOT = Path(__file__).resolve().parent.parent


def _cli(workdir, *args, check=True):
    return subprocess.run([sys.executable, "-c", "from ushka.cli import main; main()", *args],
                          cwd=workdir, capture_output=True, text=True, check=check)


def test_every_section_and_key_has_a_description():
    assert set(SECTIONS) == set(SCHEMA)
    for section, keys in SCHEMA.items():
        for key, setting in keys.items():
            assert setting.help.strip(), f"[{section}] {key} has no description"
            assert setting.help.rstrip()[-1] in ".)", f"[{section}] {key}: end the description with a full stop"


def test_defaults_come_from_the_schema():
    assert DEFAULTS == {s: {k: v.default for k, v in keys.items()} for s, keys in SCHEMA.items()}


def test_the_code_reads_no_setting_that_is_not_declared():
    declared = {f"{s}_{k}".lower() for s, keys in SCHEMA.items() for k in keys} | {f"ushka_{k}" for k in RUNTIME}
    sections = tuple(SCHEMA) + ("ushka",)
    used = {}
    for file in (ROOT / "src").rglob("*.py"):
        text = file.read_text("utf-8")
        for m in re.finditer(r"""(?:config|cfg)\.(?:get|source_of)\(\s*["']([A-Za-z_]+)["']""", text):
            used.setdefault(m.group(1).lower(), file.name)
        for m in re.finditer(r"\b(?:config|cfg)\.([A-Z][A-Z_]+)\b", text):
            used.setdefault(m.group(1).lower(), file.name)
    hidden = {k: f for k, f in used.items() if k.startswith(tuple(s + "_" for s in sections)) and k not in declared}
    assert not hidden, f"settings read by the code but missing from ushka.core.settings.SCHEMA: {hidden}"


def test_docs_table_is_generated_from_the_schema():
    text = (ROOT / "docs/guide/configuration.md").read_text("utf-8")
    block = text.split("<!-- settings:start", 1)[1].split("-->", 1)[1].split("<!-- settings:end -->", 1)[0]
    assert block.strip() == render_markdown().strip(), "run `ushka config --markdown` and paste it between the markers"
    for section, name in SECTION_DOCS.items():
        assert (ROOT / "docs/guide" / name).is_file(), f"{section}: {name} does not exist"


def test_a_new_project_lists_every_setting():
    from ushka.cli.commands.new import ushka_toml

    text = ushka_toml("shop")
    data = tomllib.loads(text)
    for section, keys in SCHEMA.items():
        for key, setting in keys.items():
            if setting.secret:
                assert f"# {key} = " in text and key not in data.get(section, {}), f"{key} must be commented out"
            else:
                assert key in data[section], f"[{section}] {key} missing from the generated ushka.toml"
                assert f"# {setting.help.split()[0]}" in text
    assert data["app"]["name"] == "shop" and data["database"]["url"] == "sqlite:///shop.db"
    assert data["static"]["enable"] is True and data["app"]["debug"] is False
    assert not problems_in(data)


def test_the_template_round_trips_to_the_defaults():
    data = tomllib.loads(render_toml())
    for section, keys in SCHEMA.items():
        for key, setting in keys.items():
            if not setting.secret:
                assert data[section][key] == setting.default, (section, key)


def test_typos_and_wrong_types_are_reported():
    found = problems_in({"security": {"tain": True, "csrf": "false", "cors_max_age": "600"}, "server": {"workers": True}})
    joined = "\n".join(found)
    assert "'taint'" in joined and "did you mean" in joined
    assert "csrf should be true/false" in joined and "cors_max_age should be a number" in joined and "workers should be a number" in joined
    assert problems_in({"payments": {"currency": "EUR"}}) == []  # your own sections are fine
    assert problems_in({"security": {"csrf": True}, "server": {"port": 9000}}) == []


def test_config_load_keeps_the_problems_and_still_applies_valid_values(workdir, caplog):
    (workdir / "ushka.toml").write_text('[security]\ncsrff = true\n[server]\nport = 9100\n')
    config = Config(workdir).load_from_file()
    assert config.get("server_port") == 9100
    assert config.problems and "csrff" in config.problems[0]


def test_check_counts_those_problems(workdir):
    from ushka.cli.commands.check import check

    (workdir / "ushka.toml").write_text('[security]\ntain = true\n')
    assert check() >= 1


def test_ushka_config_lists_everything(workdir):
    out = _cli(workdir, "config").stdout
    for section, keys in SCHEMA.items():
        assert f"[{section}]" in out
        for key in keys:
            assert f"{key} = " in out, f"{section}.{key}"
    template = _cli(workdir, "config", "--template").stdout
    assert tomllib.loads(template)["security"]["csrf"] is True
    one = _cli(workdir, "config", "pwa", "--describe").stdout
    assert "USHKA_PWA_ENABLE" in one and "[security]" not in one


def test_ushka_config_fails_on_a_typo(workdir):
    (workdir / "ushka.toml").write_text("[security]\ncsrf = 3\n")
    done = _cli(workdir, "config", check=False)
    assert done.returncode == 1 and "csrf should be true/false" in done.stdout + done.stderr


@pytest.mark.parametrize("name", ["database_url"])
def test_database_url_aliases_are_documented(name):
    from ushka.core.settings import ENV_ALIASES

    assert "DATABASE_URL" in ENV_ALIASES["USHKA_DATABASE_URL"]
