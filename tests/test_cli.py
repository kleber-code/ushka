"""Tests for the `ushka` command line interface."""

import subprocess
import sys
from pathlib import Path

import tomlkit

from ushka.cli.commands import new


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

    config = tomlkit.parse((project / "ushka.toml").read_text(encoding="utf-8"))
    assert config["app"]["name"] == "demo"
    assert config["database"]["url"] == "sqlite+aiosqlite:///demo.db"


def test_new_refuses_to_overwrite_an_existing_directory(workdir, capsys):
    (workdir / "demo").mkdir()

    new.create_project("demo")

    assert "already exists" in capsys.readouterr().out


def test_scaffolded_app_is_importable(workdir):
    """`ushka new` used to emit `Ushka(config=config)`, which raises TypeError."""
    new.create_project("demo")

    result = subprocess.run(
        [sys.executable, "-c", "import app; print(type(app.app).__name__)"],
        cwd=workdir / "demo",
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": str(Path(__file__).resolve().parent.parent / "src")},
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
        env={"PYTHONPATH": str(Path(__file__).resolve().parent.parent / "src")},
    )

    assert result.returncode == 0, result.stderr
    status, _, body = result.stdout.partition("\n")
    assert status.strip() == "200"
    assert "Welcome to Ushka!" in body
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
