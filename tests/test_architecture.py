"""Architecture rules, checked from the source so they cannot quietly erode.

* no import cycles between modules at runtime (imports for type checkers only,
  under ``if TYPE_CHECKING``, and imports inside functions are not runtime cycles);
* ``ushka.guard`` core imports nothing else from ushka, so it can ship alone;
* the core needs only the dependencies listed in AGENTS.md. Optional parts
  (docs, orm, cli, the framework integrations) may use their own extras.
"""

import ast
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
ROOT = SRC / "ushka"
STDLIB = set(sys.stdlib_module_names)

#: third-party modules the core may import at top level (jinja2 brings markupsafe)
# tomllib is stdlib on 3.11+; sys.stdlib_module_names does not list it on 3.10
CORE_ALLOWED = {"uvicorn", "jinja2", "markupsafe", "python_multipart", "multipart", "tomli", "tomllib"}
#: parts that belong to an extra or to another framework, with what they may use
OPTIONAL = {
    "ushka.docs": {"markdown_it", "mdit_py_plugins", "pygments", "griffe"},
    "ushka.orm": {"sqlalchemy", "alembic"},
    "ushka.crypto": {"cryptography"},
    "ushka.cli": {"alembic"},
}


def modules() -> dict[str, Path]:
    found = {}
    for f in sorted(ROOT.rglob("*.py")):
        parts = list(f.relative_to(SRC).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        found[".".join(parts)] = f
    return found


def runtime_imports(name: str, path: Path):
    """(internal module names, third-party top-level names) imported at module level."""
    tree = ast.parse(path.read_text())
    is_pkg = path.name == "__init__.py"
    package = name.split(".") if is_pkg else name.split(".")[:-1]
    internal, external = set(), set()

    def walk(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue  # imported when called, not when loaded
            if isinstance(child, ast.If) and "TYPE_CHECKING" in ast.dump(child.test):
                continue
            if isinstance(child, ast.Import):
                targets = [a.name for a in child.names]
            elif isinstance(child, ast.ImportFrom):
                if child.level:
                    base = package[: len(package) - (child.level - 1)]
                    targets = [".".join(base + ([child.module] if child.module else []))]
                    targets += [f"{targets[0]}.{a.name}" for a in child.names]
                else:
                    targets = [child.module or ""]
                    targets += [f"{child.module}.{a.name}" for a in child.names]
            else:
                walk(child)
                continue
            for t in targets:
                top = t.split(".")[0]
                if top == "ushka":
                    internal.add(t)
                elif top and top not in STDLIB and top != "__future__":
                    external.add(top)

    walk(tree)
    return internal, external


def test_no_runtime_import_cycles():
    mods = modules()
    graph = {}
    for name, path in mods.items():
        internal, _ = runtime_imports(name, path)
        resolved = set()
        for target in internal:
            while target and target not in mods:
                target = target.rpartition(".")[0]
            if target and target != name:
                resolved.add(target)
        graph[name] = resolved

    cycles = []

    def dfs(node, stack):
        for nxt in graph.get(node, ()):
            if nxt in stack:
                cycles.append(" -> ".join(stack[stack.index(nxt):] + [nxt]))
            elif nxt not in done:
                dfs(nxt, stack + [nxt])
        done.add(node)

    done: set = set()
    for start in graph:
        if start not in done:
            dfs(start, [start])
    assert not cycles, "import cycles:\n  " + "\n  ".join(cycles[:5])


def test_guard_core_is_standalone():
    for name, path in modules().items():
        if name.startswith("ushka.guard") and not name.startswith("ushka.guard.integrations"):
            internal, _ = runtime_imports(name, path)
            outside = sorted(t for t in internal if not t.startswith("ushka.guard"))
            assert not outside, f"{name} imports {outside}: the guard core must not import the rest of ushka"


def test_core_needs_only_its_declared_dependencies():
    offenders = []
    for name, path in modules().items():
        _, external = runtime_imports(name, path)
        allowed = set(CORE_ALLOWED)
        for prefix, extra in OPTIONAL.items():
            if name == prefix or name.startswith(prefix + "."):
                allowed |= extra
        extra_used = external - allowed
        if extra_used:
            offenders.append(f"{name}: {sorted(extra_used)}")
    assert not offenders, "undeclared third-party imports:\n  " + "\n  ".join(offenders)


def test_framework_integrations_only_import_their_framework_lazily():
    # Importing ushka.guard must work without FastAPI, Starlette or Django installed.
    for name, path in modules().items():
        if name.startswith("ushka.guard.integrations."):
            _, external = runtime_imports(name, path)
            assert not external & {"fastapi", "starlette", "django"}, f"{name} imports its framework at module level"


def test_uvicorn_is_not_imported_just_by_importing_ushka():
    import subprocess

    code = "import sys, ushka; print('uvicorn' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert out == "False", "import ushka pulled in uvicorn: keep it lazy (it is about half of the import time)"
