"""
Exposes the public API for the static files feature.
"""

from .files import get_static_absolute_path, server_static_files

__all__ = ["server_static_files", "get_static_absolute_path"]
