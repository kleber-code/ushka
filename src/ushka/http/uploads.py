"""`UploadFile`: a file the client sent in a ``multipart/form-data`` form.

Everything about an upload except its bytes is written by the client:
``filename`` and ``content_type`` are therefore `Untrusted` (when the guard is
on), and `save` never builds a path from them without cleaning it first.
"""

from __future__ import annotations

import os
import re
import unicodedata
import uuid
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import IO, Any

from ushka.guard import Untrusted, check_path
from ushka.http.exceptions import HTTPBadRequest

_CHUNK = 64 * 1024
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_NAME = 100
_MAX_EXT = 16
_KEYS = ("filename", "content_type", "size", "file")


def safe_filename(name: str, default: str = "upload") -> str:
    """A name that is safe to use on disk: letters, digits, dot, dash, underscore.

    Directories (``../``, ``C:\\``) are dropped, accents are transliterated when
    possible, everything else becomes ``_``, leading dots are removed and the
    length is limited. An empty result becomes `default`.
    """
    base = str(name).replace("\\", "/").rsplit("/", 1)[-1]
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii")
    base = _UNSAFE.sub("_", base).strip("._-").lstrip(".")
    stem, dot, ext = base.rpartition(".")
    if not dot:
        stem, ext = base, ""
    stem, ext = stem[: _MAX_NAME - 1 - min(len(ext), _MAX_EXT)] or "", ext[:_MAX_EXT]
    result = f"{stem}.{ext}" if stem and ext else (stem or ext)
    return result or default


class UploadRejected(HTTPBadRequest, ValueError):
    """The visitor sent a file the app does not accept (for example a disallowed extension).

    It is a 400 answer, so letting it propagate out of a handler shows the visitor
    "File type not allowed" instead of a 500. It is also a `ValueError`, so code
    that caught that keeps working. The message never repeats the file name.
    """

    def __init__(self, message: str) -> None:
        HTTPBadRequest.__init__(self, message=message)


class UploadFile:
    """One uploaded file.

    Attributes
    ----------
    filename : str
        The name the client gave it. `Untrusted`: never put it in a path. Use
        `safe_filename` (a plain ``str``) or let `save` pick the name.
    content_type : str
        What the client *claims* it is. `Untrusted`, and not proof of anything:
        check the content (magic bytes) when it matters.
    size : int
        Bytes received.
    file : IO[bytes]
        A seekable binary file: in memory up to a limit, on disk beyond it.

    For code written against the old ``request.files()`` dictionaries,
    ``upload["filename"]``, ``["content_type"]``, ``["size"]`` and ``["file"]``
    keep working.
    """

    def __init__(
        self,
        filename: str,
        content_type: str,
        file: IO[bytes],
        size: int | None = None,
        *,
        taint: bool = True,
    ) -> None:
        self.filename: str = Untrusted(filename, "upload:filename") if taint else filename
        self.content_type: str = Untrusted(content_type, "upload:content_type") if taint else content_type
        self.file = file
        if size is None:
            size = file.seek(0, os.SEEK_END)
            file.seek(0)
        self.size = size

    # -- what the client called it -------------------------------------------------

    @property
    def safe_filename(self) -> str:
        """`filename` cleaned for the file system (plain ``str``, never empty)."""
        return safe_filename(self.filename)

    @property
    def extension(self) -> str:
        """The lower-case extension of the cleaned name, with its dot (``".png"``), or ``""``."""
        return Path(self.safe_filename).suffix.lower()

    # -- content ----------------------------------------------------------------------

    def read(self, size: int = -1) -> bytes:
        """Reads up to `size` bytes (all by default) from the current position."""
        return self.file.read(size)

    def seek(self, offset: int, whence: int = 0) -> int:
        return self.file.seek(offset, whence)

    def head(self, size: int = 16) -> bytes:
        """The first `size` bytes, to check magic numbers. The position is restored."""
        position = self.file.tell()
        self.file.seek(0)
        try:
            return self.file.read(size)
        finally:
            self.file.seek(position)

    def save(
        self,
        directory: str | os.PathLike[str],
        name: str | None = None,
        *,
        extensions: Iterable[str] | None = None,
        overwrite: bool = False,
    ) -> Path:
        """Writes the file into `directory` and returns its `Path`.

        Parameters
        ----------
        directory : path
            Created (with its parents) when missing. Must be a trusted path.
        name : str, optional
            The file name, which must be a plain name chosen by you (no ``/``).
            Without it a random name is used (``<32 hex>.<extension>``), so
            two uploads never collide and the client picks nothing.
        extensions : iterable of str, optional
            Allowed extensions (``[".png", ".jpg"]``, dots optional, any case).
            Anything else raises `ValueError`. Applies to the final name.
        overwrite : bool
            Replace an existing file. Default False: `FileExistsError` instead.

        Raises
        ------
        ValueError
            The name is not a plain file name (``ValueError``), or the extension is not allowed (`UploadRejected`, a 400).
        FileExistsError
            The file exists and `overwrite` is False.
        UnsafeValueError
            `directory` or `name` is `Untrusted`.
        """
        check_path(directory)
        if name is None:
            name = uuid.uuid4().hex + self.extension
        else:
            check_path(name)
            name = str(name)
            if (
                not name
                or name in (".", "..")
                or "/" in name
                or "\\" in name
                or "\x00" in name
                or name != Path(name).name
            ):
                raise ValueError(f"{name!r} is not a plain file name; pass the directory separately")
        if extensions is not None:
            allowed = {"." + e.lower().lstrip(".") for e in extensions}
            if Path(name).suffix.lower() not in allowed:
                raise UploadRejected(f"File type not allowed (allowed: {', '.join(sorted(allowed))})")

        folder = Path(directory)
        folder.mkdir(parents=True, exist_ok=True)
        target = folder.resolve() / name
        flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_BINARY", 0)
        flags |= (os.O_TRUNC if overwrite else os.O_EXCL) | getattr(os, "O_NOFOLLOW", 0)
        position = self.file.tell()
        self.file.seek(0)
        try:
            fd = os.open(target, flags, 0o644)
            with os.fdopen(fd, "wb") as out:
                while chunk := self.file.read(_CHUNK):
                    out.write(chunk)
        finally:
            self.file.seek(position)
        return target

    def close(self) -> None:
        """Releases the temporary file."""
        self.file.close()

    def __enter__(self) -> UploadFile:  # noqa: PYI034
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- mapping access, for code that used the old dictionaries --------------

    def __getitem__(self, key: str) -> Any:
        if key not in _KEYS:
            raise KeyError(key)
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key) if key in _KEYS else default

    def keys(self) -> list[str]:
        return list(_KEYS)

    def __contains__(self, key: object) -> bool:
        return key in _KEYS

    def __iter__(self) -> Iterator[str]:
        return iter(_KEYS)

    def __len__(self) -> int:
        return len(_KEYS)

    def __repr__(self) -> str:
        return f"UploadFile(filename={str.__repr__(self.filename)}, content_type={str.__repr__(self.content_type)}, size={self.size})"
