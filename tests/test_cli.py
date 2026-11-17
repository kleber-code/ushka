"""Tests for the `ushka` command line interface."""

import subprocess
import sys
from pathlib import Path

import pytest

from ushka.cli import main
from ushka.cli.commands import new

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib


def test_new_creates_the_expected_layout(workdir):
    new.create_project("demo")

    project = workdir / "demo"
    assert (project / "app.py").exists()
    assert (project / "ushka.toml").exists()
    assert (project / "routes" / "index.py").exists()
    assert (project / "templates" / "index.html").exists()
    assert (project / "static").is_dir()


def test_new_writes_the_config_file_the_framework_reads(workdir):
    """The scaffold used to write `config.toml`, which nothing ever loads."""
    new.create_project("demo")

    project = workdir / "demo"
    assert not (project / "config.toml").exists()

    config = tomllib.loads((project / "ushka.toml").read_text(encoding="utf-8"))
    assert config["app"]["name"] == "demo"
    assert config["app"]["debug"] is False  # `ushka dev` turns it on by itself
    assert "secret_key" not in config["app"]  # secrets live in .env
    assert config["database"]["url"] == "sqlite:///demo.db"


def test_new_refuses_to_overwrite_an_existing_directory(workdir, capsys):
    (workdir / "demo").mkdir()

    with pytest.raises(SystemExit) as info:
        new.create_project("demo")

    assert info.value.code == 1
    assert "already exists" in capsys.readouterr().err


def test_scaffolded_app_is_importable(workdir):
    """`ushka new` used to emit `Ushka(config=config)`, which raises TypeError."""
    new.create_project("demo")

    result = subprocess.run(
        [sys.executable, "-c", "import app; print(type(app.app).__name__)"],
        cwd=workdir / "demo",
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": str(Path(__file__).resolve().parent.parent / "src"), "PATH": ""},
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "Ushka"


def test_scaffolded_project_serves_its_index_route(workdir):
    """The generated project answers `GET /` with its rendered template."""
    new.create_project("demo")

    driver = """
import asyncio
import app as project

async def main():
    scope = {
        "type": "http", "method": "GET", "path": "/",
        "query_string": b"", "headers": [], "client": ("127.0.0.1", 1),
        "scheme": "http", "server": ("testserver", 80),
    }
    sent = []
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    async def send(message):
        sent.append(message)
    await project.app(scope, receive, send)
    body = b"".join(m.get("body", b"") for m in sent[1:])
    print(sent[0]["status"])
    print(body.decode())

asyncio.run(main())
"""
    result = subprocess.run(
        [sys.executable, "-c", driver],
        cwd=workdir / "demo",
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": str(Path(__file__).resolve().parent.parent / "src"), "PATH": ""},
    )

    assert result.returncode == 0, result.stderr
    status, _, body = result.stdout.partition("\n")
    assert status.strip() == "200"
    assert "Hello, friend!" in body
    # The page title comes from the config, so an empty <title> means the
    # template referenced a variable nothing ever injects.
    assert "<title>demo</title>" in body


def test_db_command_reports_a_missing_orm_extra(monkeypatch):
    """Without Alembic the CLI must explain the extra, not raise ImportError."""
    import builtins

    from ushka import cli

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("ushka.cli.commands") and "db" in (args[2] or ()):
            raise ImportError("No module named 'alembic'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    try:
        cli._load_db_command()
    except SystemExit as exc:
        assert "ushka[orm]" in str(exc)
    else:
        raise AssertionError("expected SystemExit")


def test_new_creates_secrets_and_agent_files(workdir):
    new.create_project("demo")
    project = workdir / "demo"
    env = (project / ".env").read_text(encoding="utf-8")
    assert env.startswith("#") and "USHKA_APP_SECRET_KEY=" in env
    assert len(env.split("USHKA_APP_SECRET_KEY=")[1].strip()) >= 32
    assert ".env" in (project / ".gitignore").read_text(encoding="utf-8").split()
    assert "Untrusted" in (project / "AGENTS.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["../evil", "a/b", "1abc", "", "-x"])
def test_new_rejects_invalid_names(workdir, name):
    with pytest.raises(SystemExit):
        new.create_project(name)
    assert list(workdir.iterdir()) == []


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as info:
        main(["--version"])
    assert info.value.code == 0
    assert capsys.readouterr().out.startswith("ushka ")


@pytest.mark.parametrize(
    "url, expected",
    [("/", "routes/index.py"), ("/users", "routes/users.py"),
     ("/users/[user_id]", "routes/users/[user_id].py"), ("a/b/", "routes/a/b.py")],
)
def test_route_paths_map_to_files(url, expected):
    from ushka.cli.commands.routes import path_to_file

    assert path_to_file(url).as_posix() == expected


@pytest.mark.parametrize("url", ["/../../etc/x", "/a/../b", "/a b", "/x;rm"])
def test_route_paths_cannot_escape_routes(url):
    from ushka.cli.commands.routes import path_to_file

    with pytest.raises(SystemExit):
        path_to_file(url)


def test_routes_add_rm_mv(workdir):
    main(["routes", "add", "/users/[user_id]"])
    assert (workdir / "routes/users/[user_id].py").exists()
    main(["routes", "mv", "/users/[user_id]", "/people/[pid]"])
    assert (workdir / "routes/people/[pid].py").exists()
    main(["routes", "rm", "/people/[pid]"])
    assert not (workdir / "routes/people/[pid].py").exists()
    with pytest.raises(SystemExit) as info:
        main(["routes", "rm", "/people/[pid]"])
    assert info.value.code == 1


def test_check_flags_production_problems(workdir, monkeypatch, capsys):
    for name in ("USHKA_APP_DEBUG", "USHKA_APP_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)
    (workdir / "ushka.toml").write_text("[app]\ndebug = true\n", encoding="utf-8")
    (workdir / ".env").write_text("USHKA_APP_SECRET_KEY=short\n", encoding="utf-8")
    with pytest.raises(SystemExit) as info:
        main(["check", "--production"])
    assert info.value.code == 1
    out = capsys.readouterr()
    text = out.out + out.err
    assert "debug is on" in text
    assert "shorter than 32" in text
    assert ".env exists but is not in .gitignore" in text


def test_check_passes_for_a_fresh_project(workdir, monkeypatch):
    for name in ("USHKA_APP_DEBUG", "USHKA_APP_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)
    new.create_project("demo")
    monkeypatch.chdir(workdir / "demo")
    main(["check", "--production"])  # no SystemExit


def _csp_project(workdir, monkeypatch, toml=""):
    for name in ("USHKA_APP_DEBUG", "USHKA_APP_SECRET_KEY", "USHKA_SECURITY_CSP"):
        monkeypatch.delenv(name, raising=False)
    (workdir / "templates").mkdir()
    (workdir / "templates" / "base.html").write_text(
        "<html>\n<link rel='stylesheet' href='https://cdn.example.com/a.css'>\n"
        "<link rel='icon' href='https://img.example.com/i.png'>\n"
        '<script src="https://cdn.jsdelivr.net/npm/x.js"></script>\n'
        "<script src='/static/ok.js'></script>\n<script type='application/ld+json'>{}</script>\n"
        "<script>alert(1)</script>\n<style>a{}</style>\n",
        encoding="utf-8",
    )
    if toml:
        (workdir / "ushka.toml").write_text(toml, encoding="utf-8")


def test_check_warns_about_what_the_default_csp_blocks(workdir, monkeypatch, capsys):
    _csp_project(workdir, monkeypatch)
    main(["check"])  # warnings are not problems: no SystemExit
    text = (lambda o: o.out + o.err)(capsys.readouterr())
    assert "templates/base.html:2" in text and "cdn.example.com" in text
    assert "templates/base.html:4" in text and "cdn.jsdelivr.net" in text
    assert "templates/base.html:7: inline <script>" in text
    assert "img.example.com" not in text and "ok.js" not in text and "ld+json" not in text
    assert "[security] csp" in text


def test_check_csp_scan_respects_a_custom_or_disabled_policy(workdir, monkeypatch, capsys):
    _csp_project(workdir, monkeypatch, '[security]\ncsp = "default-src \'self\'; script-src \'self\' cdn.jsdelivr.net"\n')
    main(["check"])
    text = (lambda o: o.out + o.err)(capsys.readouterr())
    assert "cdn.jsdelivr.net" not in text  # the policy names it
    assert "cdn.example.com" in text  # not named by the policy
    (workdir / "ushka.toml").write_text('[security]\ncsp = "off"\n', encoding="utf-8")
    main(["check"])
    text = (lambda o: o.out + o.err)(capsys.readouterr())
    assert "blocked" not in text


def test_check_production_warns_about_open_allowed_hosts(workdir, capsys):
    from ushka.cli.commands.check import check

    (workdir / "ushka.toml").write_text('[app]\ndebug = false\n')
    check(production=True)
    out = capsys.readouterr()
    assert "allowed_hosts is empty" in out.out + out.err
    (workdir / "ushka.toml").write_text('[app]\ndebug = false\n[security]\nallowed_hosts = ["example.com"]\n')
    from ushka.core.config import Config

    Config._instance = None
    Config._initialized = False
    check(production=True)
    out = capsys.readouterr()
    assert "allowed_hosts is empty" not in out.out + out.err
