"""Static file serving: the ``[static]`` directory and any number of mounts.

Files are served with an ``ETag`` and ``Last-Modified`` so browsers and CDNs
revalidate cheaply (``304 Not Modified``), a configurable ``Cache-Control``
and ``X-Content-Type-Options: nosniff``. Every path goes through
`ushka.guard.safe.path`, so traversal, symlink escapes and null bytes are
refused before the filesystem is touched.
"""

from __future__ import annotations

import mimetypes
from email.utils import formatdate
from pathlib import Path
from typing import TYPE_CHECKING

from ushka.core.config import Config
from ushka.guard import safe
from ushka.http import Response
from ushka.http.exceptions import HTTPStaticServerNotFound

if TYPE_CHECKING:
    from ushka.http.request import Request

DEFAULT_CACHE_CONTROL = "public, max-age=3600"


def get_static_absolute_path(workdir: Path, static_dir: Path) -> Path:
    """Resolves `static_dir` against `workdir` unless it is already absolute."""
    return static_dir if static_dir.is_absolute() else workdir.joinpath(static_dir)


def file_response(
    path: Path,
    request: "Request | None" = None,
    cache_control: str = DEFAULT_CACHE_CONTROL,
) -> Response:
    """Builds the response for one file, answering ``304`` when it is unchanged.

    Parameters
    ----------
    path : Path
        A file that has already been validated (e.g. with `safe.path`).
    request : Request, optional
        Used for ``If-None-Match`` revalidation.
    cache_control : str
        Value of the ``Cache-Control`` header. Use something like
        ``"public, max-age=31536000, immutable"`` for fingerprinted assets.
    """
    stat = path.stat()
    etag = f'W/"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
    headers = {
        "ETag": etag,
        "Last-Modified": formatdate(stat.st_mtime, usegmt=True),
        "Cache-Control": cache_control,
        "X-Content-Type-Options": "nosniff",
    }
    if request is not None:
        sent = str(request.headers.get("if-none-match", ""))
        if etag in {tag.strip() for tag in sent.split(",")} or sent.strip() == "*":
            return Response(b"", status_code=304, headers=headers)

    content_type, _ = mimetypes.guess_type(path.name)
    return Response(
        path.read_bytes(),
        status_code=200,
        headers=headers,
        media_type=content_type or "application/octet-stream",
    )


def resolve_in(root: Path, filename: str, *, html: bool = False) -> Path | None:
    """Finds the file `filename` names inside `root`, or ``None``.

    With ``html=True`` a directory resolves to its ``index.html`` (the layout
    static site generators such as MkDocs produce).
    """
    target = safe.path(filename, root, default=None) if filename else root.resolve()
    if target is None:
        return None
    if html and target.is_dir():
        target = target / "index.html"
    return target if target.is_file() else None


async def server_static_files(filename: str, config: Config, request: "Request") -> Response:
    """Serves a file from the ``[static]`` directory (registered when enabled)."""
    workdir = Path(config.get("USHKA_WORKDIR"))
    root = get_static_absolute_path(workdir, Path(config.get("STATIC_DIR")))
    target = resolve_in(root, filename)
    if target is None:
        raise HTTPStaticServerNotFound()
    return file_response(target, request, str(config.get("STATIC_CACHE_CONTROL") or DEFAULT_CACHE_CONTROL))
