"""
This module provides Command Line Interface (CLI) commands for managing
application routes within the Ushka framework.

It allows users to list, add, remove, and move route files, facilitating
the organization and development of application endpoints.

Commands
--------
list_routes: Displays all registered application routes.
_path_to_file: Converts a URL path to a filesystem path for route files.
add_route: Creates a new Python file to serve as a route handler.
remove_route: Deletes an existing route file.
move_route: Renames or relocates an existing route file.
"""

import importlib
from pathlib import Path

from ushka.core.app import Ushka


def list_routes(app_path: str):
    """Lists all registered routes in the application.

    Attempts to load the Ushka application instance from the specified path
    and then prints all discovered routes to the console.

    Parameters
    ----------
    app_path : str
        The path to the Ushka application instance, in the format 'module:instance'
        (e.g., 'app:app').

    Returns
    -------
    None
        This function prints directly to stdout and does not return a value.
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
    """Converts a URL path to a filesystem path within the 'routes' directory.

    For example, the URL path "/users/profile" would be converted to
    "routes/users/profile.py" relative to the current working directory.

    Parameters
    ----------
    path : str
        The URL path to convert (e.g., "/users/profile").

    Returns
    -------
    pathlib.Path
        The corresponding filesystem path for the route file.
    """  # Remove leading slash and split the path
    parts = path.strip("/").split("/")
    # Join the parts and add the .py extension
    return Path("routes", *parts).with_suffix(".py")


def add_route(path: str):
    """Creates a new route file at the specified URL path.

    This function generates a new Python file inside the 'routes' directory
    with a basic GET handler template. If a file for the given path
    already exists, the operation is aborted. Parent directories will be
    created if they don't exist.

    Parameters
    ----------
    path : str
        The URL path for which to create the new route file (e.g., "/users/new").

    Returns
    -------
    None
        This function prints directly to stdout and does not return a value.
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
    """Removes a route file corresponding to the specified URL path.

    This function deletes the Python file associated with the given URL path
    from the 'routes' directory. If the file is not found, the operation
    is aborted with a message.

    Parameters
    ----------
    path : str
        The URL path of the route file to remove (e.g., "/users/old").

    Returns
    -------
    None
        This function prints directly to stdout and does not return a value.
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
    """Moves or renames a route file from an old URL path to a new URL path.

    This function renames or moves the Python file corresponding to `old_path`
    to `new_path` within the 'routes' directory. Parent directories for the
    `new_path` will be created if they don't exist. The operation is aborted if
    the `old_path` file is not found or if a file already exists at `new_path`.

    Parameters
    ----------
    old_path : str
        The current URL path of the route file to move (e.g., "/users/old_profile").
    new_path : str
        The new URL path for the route file (e.g., "/users/new_profile").

    Returns
    -------
    None
        This function prints directly to stdout and does not return a value.
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
