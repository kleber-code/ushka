"""Guards against import-time dependencies leaking into the core install.

`pip install ushka` only pulls the core dependencies. Anything imported at
module level by `ushka` or `ushka.cli` therefore has to be a core dependency,
otherwise the package - and the `ushka` console script - fail to import.
"""

import subprocess
import sys
from pathlib import Path

import pytest

# `tomllib` is only in the standard library from 3.11 on, and the project
# supports 3.10; `tomlkit` is a core dependency, so it is always available.
import tomlkit

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = tomlkit.parse((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
CORE_DEPENDENCIES = PYPROJECT["project"]["dependencies"]

# Distributions that are only installed through an extra.
OPTIONAL_MODULES = ["sqlalchemy", "alembic", "aiosqlite", "asyncpg", "aiomysql"]


def _imported_modules(statement):
    """Runs `statement` in a fresh interpreter and returns the loaded modules."""
    code = f"{statement}\nimport sys\nprint('\\n'.join(sorted(sys.modules)))"
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO_ROOT,
    )
    return set(result.stdout.split())


def test_jinja2_is_a_core_dependency():
    """`ushka.core.error_handler` renders templates on every import."""
    assert any(dep.startswith("jinja2") for dep in CORE_DEPENDENCIES)


@pytest.mark.parametrize("module", OPTIONAL_MODULES)
def test_importing_ushka_does_not_pull_optional_modules(module):
    assert module not in _imported_modules("import ushka")


@pytest.mark.parametrize("module", OPTIONAL_MODULES)
def test_importing_the_cli_does_not_pull_optional_modules(module):
    """`ushka --help` must work without the ORM extra installed."""
    assert module not in _imported_modules("import ushka.cli")


def test_cli_help_runs():
    code = (
        "import sys; sys.argv = ['ushka', '--help']; from ushka.cli import main; main()"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0
    assert "Ushka Framework CLI" in result.stdout


def test_default_templates_ship_with_the_package():
    """The error/startup pages are rendered at runtime, so they must be built."""
    templates = REPO_ROOT / "src" / "ushka" / "internal" / "default_templates"
    assert {p.name for p in templates.glob("*.html")} >= {
        "error.html",
        "debug_error.html",
        "startup.html",
    }

    excludes = PYPROJECT["tool"]["pdm"]["build"].get("excludes", [])
    assert not any("default_templates" in pattern for pattern in excludes)
    assert not any(pattern.rstrip("/*") == "src/ushka/internal" for pattern in excludes)
