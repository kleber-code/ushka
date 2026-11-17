"""The Ushka application layout: what `ushka new` creates and what `ushka check` warns about."""

import subprocess
import sys
from pathlib import Path

import pytest

from ushka.cli.commands import structure
from ushka.cli.commands.structure import structure_warnings


@pytest.fixture(autouse=True)
def clean_sys_path(monkeypatch):
    """Other tests leave temporary project folders on sys.path; the clash check would see them."""
    monkeypatch.setattr(sys, "path", ["/nonexistent"])


def make(tmp_path, files: dict[str, str]):
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, "utf-8")
    return tmp_path


def test_a_tidy_project_has_no_warnings(tmp_path):
    make(tmp_path, {
        "app.py": "x = 1\n", "routes/index.py": "x = 1\n", "services/billing.py": "def pay(): ...\n",
        "models/billing.py": "x = 1\n", "integrations/stripe.py": "x = 1\n", "tests/test_a.py": "x = 1\n",
    })
    assert structure_warnings(tmp_path) == []


def test_code_in_the_root_is_named_with_its_shared_prefixes(tmp_path):
    names = ["painel", "painel_ia", "painel_cliente", "dados", "dados_escrita", "nucleo", "cfg"]
    make(tmp_path, {"app.py": "", **{f"{n}.py": "x = 1\n" for n in names}})
    out = structure_warnings(tmp_path)
    assert any("7 Python modules sit in the project root" in w for w in out)
    prefix = next(w for w in out if "share a prefix" in w)
    assert "painel* (3)" in prefix and "dados* (2)" in prefix


def test_five_modules_in_the_root_are_still_fine(tmp_path):
    make(tmp_path, {"app.py": "", "conftest.py": "", **{f"m{i}.py": "" for i in range(structure.ROOT_MODULES_MAX)}})
    assert structure_warnings(tmp_path) == []


def test_a_module_over_the_limit_is_named(tmp_path):
    make(tmp_path, {"app.py": "", "models/all.py": "x = 1\n" * (structure.BIG_MODULE_LINES + 1), "services/ok.py": "x = 1\n"})
    out = structure_warnings(tmp_path)
    assert len(out) == 1 and "models/all.py has 501 lines" in out[0] and "split it by domain" in out[0]


def test_big_files_in_tests_and_migrations_are_not_flagged(tmp_path):
    big = "x = 1\n" * 900
    make(tmp_path, {"app.py": "", "tests/test_big.py": big, "migrations/versions/001.py": big, ".venv/lib/x.py": big})
    assert structure_warnings(tmp_path) == []


def test_a_host_folder_nobody_uses_is_reported(tmp_path):
    class Cfg:
        def get(self, key, default=None):
            return {"routes_hosts": {"api.*": "routes_api", "x.*": ["routes_x"]}}.get(key, default)

    make(tmp_path, {"app.py": "", "routes_api/a.py": "", "routes_x/a.py": "", "routes_ai/a.py": ""})
    out = structure_warnings(tmp_path, Cfg())
    assert out == ["routes_ai/ is not used by any host in [routes] hosts, so its routes never answer."]


@pytest.mark.parametrize(
    "source,named",
    [
        ("from ushka.http import redirect\n", "ushka.http"),
        ("from ushka.templating import render\n", "ushka.templating"),
        ("from ushka import Request\n", "ushka.Request"),
        ("from routes.billing import x\n", "routes.billing"),
        ("import ushka.http.request\n", "ushka.http.request"),
    ],
)
def test_services_and_models_must_not_know_about_http(tmp_path, source, named):
    make(tmp_path, {"app.py": "", "services/pay.py": source, "models/ok.py": "import datetime\n"})
    out = structure_warnings(tmp_path)
    assert len(out) == 1 and "services/pay.py imports" in out[0] and named in out[0] and "must not know about HTTP" in out[0]


def test_integrations_and_routes_may_use_http(tmp_path):
    make(tmp_path, {"app.py": "", "integrations/hook.py": "from ushka import Request\n", "routes/a.py": "from ushka.http import redirect\n"})
    assert structure_warnings(tmp_path) == []


def test_a_folder_named_like_an_installed_package_is_reported(tmp_path, monkeypatch):
    other = tmp_path / "site"
    (other / "services").mkdir(parents=True)
    project = tmp_path / "proj"
    make(project, {"app.py": "", "services/a.py": "x = 1\n"})
    monkeypatch.setattr(sys, "path", [str(project), str(other)])
    out = structure_warnings(project)
    assert len(out) == 1 and "services/ has the same name as a package" in out[0]


def test_syntax_errors_do_not_crash_the_lint(tmp_path):
    make(tmp_path, {"app.py": "", "services/broken.py": "def (:\n"})
    assert structure_warnings(tmp_path) == []


# --- what `ushka new` creates -----------------------------------------------------------


@pytest.fixture
def new_project(tmp_path, monkeypatch):
    from ushka.cli.commands.new import create_project

    monkeypatch.chdir(tmp_path)
    create_project("shop")
    return tmp_path / "shop"


def test_new_creates_the_layout(new_project):
    for rel in ("app.py", "routes/index.py", "services/greeting.py", "services/__init__.py", "models/__init__.py",
                "integrations/__init__.py", "templates/index.html", "static/style.css", "tests/test_index.py", "pytest.ini", "AGENTS.md"):
        assert (new_project / rel).is_file(), rel
    assert [p.name for p in new_project.glob("*.py")] == ["app.py"], "only app.py in the root"
    assert structure_warnings(new_project) == []


def test_the_generated_agents_md_teaches_the_layout(new_project):
    text = (new_project / "AGENTS.md").read_text("utf-8")
    for needle in ("Where does new code go?", "`services/`", "`models/`", "`integrations/`", "No `request`, no templates",
                   "Never a `.py` in the root", "`@app.middleware`", "safe.url", "routes` → `services` → `models`", "[shop]"):
        assert needle in text, needle
    assert len(text.splitlines()) <= 45


def test_the_generated_route_calls_the_service(new_project):
    route = (new_project / "routes" / "index.py").read_text("utf-8")
    assert "from services.greeting import greeting" in route
    service = (new_project / "services" / "greeting.py").read_text("utf-8")
    assert "request" not in service.replace("`request`", "") and "ushka" not in service


def test_the_generated_project_passes_its_own_tests_and_check(new_project):
    done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:warnings"],
                          cwd=new_project, capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stdout + done.stderr
    check = subprocess.run([sys.executable, "-c", "from ushka.cli import main; main()", "check"],
                           cwd=new_project, capture_output=True, text=True, check=False)
    assert "project layout follows the Ushka structure" in check.stdout + check.stderr


def test_check_prints_each_warning(tmp_path, monkeypatch, capsys):
    from ushka.cli.commands.check import check

    make(tmp_path, {"app.py": "", **{f"m{i}.py": "x\n" for i in range(7)}})
    monkeypatch.chdir(tmp_path)
    check()
    out = capsys.readouterr()
    assert "7 Python modules sit in the project root" in out.out + out.err and Path(tmp_path).exists()
