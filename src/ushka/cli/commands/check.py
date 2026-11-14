"""``ushka check``: validates configuration and security settings.

Exits with status 1 when a problem is found, so it can run in CI or before a
deploy (``ushka check --production``).
"""

from __future__ import annotations

import sys
from pathlib import Path

from ushka.cli import ui
from ushka.core.config import Config
from ushka.guard import TEMPLATES_SUPPORTED

SETTINGS = (
    "app_debug",
    "app_secret_key",
    "database_url",
    "security_taint",
    "server_host",
    "server_port",
    "static_enable",
)


def _display(key: str, value: object) -> str:
    if key == "app_secret_key":
        return "(set)" if value else "(not set)"
    return repr(value)


def check(production: bool = False) -> int:
    """Prints a report and returns the number of problems found."""
    workdir = Path.cwd()
    try:
        config = Config(workdir).load_from_file()
    except ValueError as exc:
        ui.fail(str(exc))

    problems = 0
    ui.title(f"Ushka {config.get('ushka_version')} · checking {workdir}")

    ui.line("\n  Settings")
    for key in SETTINGS:
        ui.info(f"{key} = {_display(key, config.get(key))}  " + ui.code(f"[{config.source_of(key)}]"))

    ui.line("\n  Checks")
    toml = workdir / "ushka.toml"
    if toml.exists():
        ui.ok("ushka.toml found")
        if config.source_of("app_secret_key") == "ushka.toml":
            problems += 1
            ui.error("ushka.toml contains secret_key: move it to .env / USHKA_APP_SECRET_KEY")
    else:
        ui.warn("no ushka.toml: using defaults")

    if config.get("security_taint") is False:
        problems += 1
        ui.error("Ushka Guard is disabled ([security] taint = false)")
    else:
        ui.ok("Ushka Guard is on")

    secret_source = config.source_of("app_secret_key")
    if production:
        if config.get("app_debug"):
            problems += 1
            ui.error("debug is on: visitors would see tracebacks and local variables")
        else:
            ui.ok("debug is off")
        if not config.get("app_secret_key") or secret_source.startswith("generated"):
            problems += 1
            ui.error("USHKA_APP_SECRET_KEY is not set: sessions will fail")
        elif len(str(config.get("app_secret_key"))) < 32:
            problems += 1
            ui.error("USHKA_APP_SECRET_KEY is shorter than 32 characters")
        else:
            ui.ok("secret key is set")
    elif not config.get("app_secret_key"):
        ui.warn("USHKA_APP_SECRET_KEY is not set (needed for sessions in production)")

    gitignore = workdir / ".gitignore"
    if (workdir / ".env").exists():
        ignored = gitignore.exists() and ".env" in gitignore.read_text("utf-8").split()
        if ignored:
            ui.ok(".env is git-ignored")
        else:
            problems += 1
            ui.error(".env exists but is not in .gitignore")

    routes = workdir / "routes"
    if routes.is_dir():
        ui.ok(f"{sum(1 for _ in routes.rglob('*.py'))} route file(s) in routes/")

    if TEMPLATES_SUPPORTED:
        ui.ok(f"Python {sys.version.split()[0]}: t-strings available")
    else:
        ui.info(f"Python {sys.version.split()[0]}: t-strings need 3.14+")

    ui.line()
    if problems:
        ui.error(f"{problems} problem(s) found")
    else:
        ui.ok("all good " + ui.MASCOT)
    return problems
