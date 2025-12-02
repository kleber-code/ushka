"""
This module provides functionality for serving static files in the Ushka framework.

It includes functions to resolve static file paths and to serve files with
appropriate security checks and HTTP headers.
"""

import mimetypes
from pathlib import Path

from ushka.core.config import Config
from ushka.core.exceptions import CantCompleteResponse
from ushka.http import Response
from ushka.http.exceptions import HTTPStaticServerNotFound


@staticmethod
async def get_static_absolute_path(workdir: Path, static_dir: Path) -> Path:
    """Resolves the absolute path for a static directory.

    This function handles both relative and absolute paths for the static
    directory. If the path is relative, it is resolved against the application's
    working directory.

    Args:
        workdir: The application's working directory.
        static_dir: The configured static directory path (can be relative or
            absolute).

    Returns:
        The absolute path to the static directory.
    """
    if not str(static_dir).startswith("/"):
        return workdir.joinpath(static_dir)
    return static_dir


async def server_static_files(
    filename: str, config: Config, response: Response
) -> Response:
    """Serves a static file based on the provided filename.

    This function performs security checks to prevent path traversal attacks,
    verifies that the file exists, and sets the appropriate HTTP headers
    (e.g., `Content-Type`, `Content-Length`).

    Args:
        filename: The name of the file to serve, relative to the static
            directory.
        config: The application configuration object.
        response: The response object to populate with the file content and
            headers.

    Returns:
        The populated response object.

    Raises:
        HttpStaticServerNotFound: If the file is not found, is not a file,
            or if a path traversal attack is detected.
        CantCompleteResponse: If there is an error reading the file or
            populating the response.
    """
    static_dir = Path(config.get("STATIC_DIR"))
    workdir = Path(config.get("USHKA_WORKDIR"))
    static_root = await get_static_absolute_path(workdir, static_dir)

    try:
        file_path = (static_root / filename).resolve()
    except Exception as exc:
        raise HTTPStaticServerNotFound() from exc

    # SECURITY CHECK (Anti-Path Traversal)
    if not str(file_path).startswith(str(static_root)):
        raise HTTPStaticServerNotFound()

    # CHECK IF EXIST
    if not file_path.exists() or not file_path.is_file():
        raise HTTPStaticServerNotFound()

    content_type, _ = mimetypes.guess_type(file_path)
    if not content_type:
        content_type = "application/octet-stream"

    try:
        body = file_path.read_bytes()
        response.body = body
        response.status_code = 200
        response.headers["content-type"] = content_type
        response.headers["content-length"] = str(len(body))
        response.headers["cache-control"] = "public, max-age=3600"
        return response
    except Exception as exc:
        raise CantCompleteResponse("Static Cant Return a Valid Response") from exc
