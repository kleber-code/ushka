"""``ushka routes``: list, add, remove and move filesystem routes."""

from __future__ import annotations

import importlib
import re
from pathlib import Path

from ushka.cli import ui

ROUTES_DIR = Path("routes")
_SEGMENT = re.compile(r"^(\[((path|int):)?[A-Za-z_][A-Za-z0-9_]*\]|[A-Za-z0-9_.-]+)$")

ROUTE_TEMPLATE = '''\
async def get(request):
    return "Hello from {url}!"
'''


def load_app(app_path: str):
    """Imports ``module:attribute`` and returns the application object."""
    module_name, sep, attr = app_path.partition(":")
    if not sep or not module_name or not attr:
        ui.fail(f"Expected the app as 'module:attribute' (e.g. app:app), got {app_path!r}.")
    try:
        module = importlib.import_module(module_name)
        return getattr(module, attr)
    except (ImportError, AttributeError) as exc:
        ui.fail(f"Could not load {app_path}: {exc}")


def path_to_file(url: str) -> Path:
    """Maps a URL path to its route file, refusing anything outside ``routes/``.

    ``/`` → ``routes/index.py``, ``/users`` → ``routes/users.py``,
    ``/users/[user_id]`` → ``routes/users/[user_id].py``.
    """
    parts = [p for p in url.strip().strip("/").split("/") if p]
    if not parts:
        return ROUTES_DIR / "index.py"
    for part in parts:
        if part in (".", "..") or not _SEGMENT.match(part):
            ui.fail(
                f"Invalid route segment {part!r} in {url!r}. Use letters, digits, '-', '_', "
                "or a parameter like [user_id]."
            )
    return ROUTES_DIR.joinpath(*parts).with_suffix(".py")


def list_routes(app_path: str) -> None:
    app = load_app(app_path)
    urls = app.router.get_urls(with_host=False)
    ui.title(f"{len(urls)} route(s)")
    for url in urls:
        ui.info(url)


def add_route(url: str) -> None:
    file_path = path_to_file(url)
    if file_path.exists():
        ui.fail(f"Route file already exists: {file_path}")
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(ROUTE_TEMPLATE.format(url="/" + url.strip("/")), encoding="utf-8")
    ui.ok(f"created {file_path}")


def remove_route(url: str) -> None:
    file_path = path_to_file(url)
    if not file_path.exists():
        ui.fail(f"Route file not found: {file_path}")
    file_path.unlink()
    ui.ok(f"removed {file_path}")


def move_route(old_url: str, new_url: str) -> None:
    old_file, new_file = path_to_file(old_url), path_to_file(new_url)
    if not old_file.exists():
        ui.fail(f"Route file not found: {old_file}")
    if new_file.exists():
        ui.fail(f"Route file already exists: {new_file}")
    new_file.parent.mkdir(parents=True, exist_ok=True)
    old_file.rename(new_file)
    ui.ok(f"moved {old_file} → {new_file}")
