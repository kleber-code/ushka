import importlib
from pathlib import Path

from ushka.core.app import Ushka


def list_routes(app_path: str):
    """
    Lists all the routes in the application.
    """
    try:
        module_str, app_str = app_path.split(":")
        module = importlib.import_module(module_str)
        app: Ushka = getattr(module, app_str)
    except (ValueError, ImportError, AttributeError) as e:
        print(f"❌ Error loading application: {e}")
        return

    print("🚀 Registered routes:")
    for url in app.router.get_urls(with_host=False):
        print(f"  - {url}")


def _path_to_file(path: str) -> Path:
    """
    Converts a URL path to a filepath in the 'routes' directory.
    Example: /users/profile -> routes/users/profile.py
    """
    # Remove leading slash and split the path
    parts = path.strip("/").split("/")
    # Join the parts and add the .py extension
    return Path("routes", *parts).with_suffix(".py")


def add_route(path: str):
    """
    Creates a new route file.
    """
    file_path = _path_to_file(path)

    if file_path.exists():
        print(f"❌ Route file already exists: {file_path}")
        return

    # Ensure the parent directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with open(file_path, "w") as f:
        f.write(
            """from ushka.http.request import Request
from ushka.http.response import Response

async def get(request: Request) -> Response:
    return Response("Hello from your new route!")
"""
        )

    print(f"✅ Route file created: {file_path}")


def remove_route(path: str):
    """
    Removes a route file.
    """
    file_path = _path_to_file(path)

    if not file_path.exists():
        print(f"❌ Route file not found: {file_path}")
        return

    try:
        file_path.unlink()
        print(f"✅ Route file removed: {file_path}")
    except Exception as e:
        print(f"❌ Error removing route file: {e}")


def move_route(old_path: str, new_path: str):
    """
    Moves or renames a route file.
    """
    old_file_path = _path_to_file(old_path)
    new_file_path = _path_to_file(new_path)

    if not old_file_path.exists():
        print(f"❌ Old route file not found: {old_file_path}")
        return

    if new_file_path.exists():
        print(f"❌ New route file already exists: {new_file_path}")
        return

    # Ensure the new parent directory exists
    new_file_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        old_file_path.rename(new_file_path)
        print(f"✅ Route file moved: {old_file_path} -> {new_file_path}")
    except Exception as e:
        print(f"❌ Error moving route file: {e}")