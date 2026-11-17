"""The layout lint behind ``ushka check``: is the project organised the Ushka way?

The rules are the ones in the "Application structure" guide, and every number is
here, in one place, so nothing is hidden. They only ever *warn*: a project that
grew in another shape still runs.
"""

from __future__ import annotations

import ast
import collections
import sys
from pathlib import Path
from typing import Any

#: More modules than this next to ``app.py`` means business code lives in the root.
ROOT_MODULES_MAX = 5
#: A module longer than this is several domains in one file.
BIG_MODULE_LINES = 500
#: Python files in the root that are not business code.
ROOT_ALLOWED = frozenset({"app.py", "conftest.py", "setup.py", "wsgi.py", "asgi.py"})
#: Folders whose code must not know about HTTP.
PURE_DIRS = ("models", "services")
#: Top-level package names the layout recommends; a pip package of the same name would clash.
LAYER_NAMES = ("models", "services", "integrations", "deps", "tasks")
SKIP_DIRS = frozenset(
    {".git", ".venv", "venv", "env", "node_modules", "__pycache__", "migrations", "tests", "static",
     "templates", "locale", "scripts", "tools", "build", "dist", ".tox", ".mypy_cache", ".pytest_cache"}
)
HTTP_MODULES = ("ushka.http", "ushka.templating", "ushka.web")
HTTP_NAMES = frozenset({"Request", "Response", "render", "redirect", "HTTPRedirect", "HTTPResponse"})


def _modules(workdir: Path):
    for path in sorted(workdir.rglob("*.py")):
        rel = path.relative_to(workdir)
        if any(part in SKIP_DIRS or part.startswith(".") for part in rel.parts[:-1]):
            continue
        yield path, rel


def _http_imports(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text("utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            mod = node.module
            if mod == "routes" or mod.startswith(("routes.", "routes_")) or mod.startswith(HTTP_MODULES):
                found.append(mod)
            elif mod == "ushka":
                found += [f"ushka.{a.name}" for a in node.names if a.name in HTTP_NAMES]
        elif isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name.startswith(HTTP_MODULES) or a.name == "routes"]
    return sorted(set(found))


def structure_warnings(workdir: Path, config: Any = None) -> list[str]:
    """What is off in the layout of the project at `workdir`, one sentence each."""
    warnings: list[str] = []

    root = [p.name for p in sorted(workdir.glob("*.py")) if p.name not in ROOT_ALLOWED]
    if len(root) > ROOT_MODULES_MAX:
        sample = ", ".join(root[:4]) + (", ..." if len(root) > 4 else "")
        warnings.append(
            f"{len(root)} Python modules sit in the project root ({sample}). Keep the root for app.py and "
            "config, and move code into models/, services/ and integrations/ (guide: Application structure)."
        )
        prefixes = collections.Counter(name.removesuffix(".py").split("_")[0] for name in root)
        grouped = [f"{k}* ({v})" for k, v in prefixes.most_common() if v >= 2 and k != "test"]
        if grouped:
            warnings.append("Files that share a prefix are a folder waiting to exist: " + ", ".join(grouped[:5]) + ".")

    big = []
    for path, rel in _modules(workdir):
        try:
            lines = sum(1 for _ in path.open("rb"))
        except OSError:
            continue
        if lines > BIG_MODULE_LINES:
            big.append((lines, rel.as_posix()))
    for lines, rel in sorted(big, reverse=True)[:3]:
        warnings.append(f"{rel} has {lines} lines (more than {BIG_MODULE_LINES}): split it by domain, one module per domain.")

    hosts = (config.get("routes_hosts") if config is not None else None) or {}
    used: set[str] = set()
    for value in hosts.values():
        used.update([value] if isinstance(value, str) else value)
    for folder in sorted(p.name for p in workdir.glob("routes_*") if p.is_dir()):
        if folder not in used:
            warnings.append(f"{folder}/ is not used by any host in [routes] hosts, so its routes never answer.")

    for layer in PURE_DIRS:
        for path in sorted((workdir / layer).rglob("*.py")) if (workdir / layer).is_dir() else []:
            bad = _http_imports(path)
            if bad:
                warnings.append(
                    f"{path.relative_to(workdir).as_posix()} imports {', '.join(bad)}: {layer}/ must not know about "
                    "HTTP (routes call services, never the other way round)."
                )

    for name in LAYER_NAMES:
        if not ((workdir / name).is_dir() or (workdir / f"{name}.py").exists()):
            continue
        for entry in sys.path:
            if not entry or Path(entry).resolve() == workdir.resolve():
                continue
            other = Path(entry) / name
            if other.is_dir() or other.with_suffix(".py").exists():
                warnings.append(
                    f"your {name}/ has the same name as a package found in {entry}; whichever comes first on "
                    "sys.path wins, so imports can pick the wrong one. Rename yours or remove the other."
                )
                break
    return warnings


__all__ = ["structure_warnings"]
