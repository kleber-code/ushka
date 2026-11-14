"""Static files: the ``[static]`` directory, mounts and single-file responses."""

from .files import (
    DEFAULT_CACHE_CONTROL,
    file_response,
    get_static_absolute_path,
    resolve_in,
    server_static_files,
)

__all__ = [
    "DEFAULT_CACHE_CONTROL",
    "file_response",
    "get_static_absolute_path",
    "resolve_in",
    "server_static_files",
]
