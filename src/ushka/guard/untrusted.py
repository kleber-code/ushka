"""The `Untrusted` string type and its propagation rules.

An `Untrusted` value is a `str` that remembers it came from outside the
program: an HTTP request, a cookie, a header, or the output of a language
model. It behaves exactly like `str` for reading, comparing, hashing and
serialising, so existing code keeps working. What changes is that the
dangerous sinks (raw HTML, redirects, file paths, raw SQL, ...) refuse it
until it goes through an explicit sanitiser from `ushka.guard.safe`.

Propagation
-----------
Operations that build a new string *from* an `Untrusted` value return an
`Untrusted` value too: ``+`` (on either side), ``*``, ``%`` (with the
untrusted value on either side), slicing, ``.format()``/``.join()`` called on
it, and every case/whitespace/replace method. ``split`` and ``partition``
return lists/tuples of `Untrusted`.

Known gaps (documented, tested as such)
---------------------------------------
CPython builds some strings in C without asking the operands, so the mark is
lost in:

* f-strings with more than one part: ``f"<b>{name}</b>"``
* ``.format`` on a *trusted* template with more than one part:
  ``"Hi {}".format(name)``
* ``%`` with a tuple of arguments: ``"%s-%s" % (a, b)``
* ``.join`` called on a *trusted* separator: ``", ".join([name])``
* ``str(value)`` (see the note on ``__str__`` below)
* ``.encode()`` (bytes are not tracked)

`ushka.guard.rewrite` closes the first five for modules it compiles (Ushka
applies it to the files in ``routes/``). Even so this is defence in depth,
not a proof. On Python 3.14+ prefer t-strings (``t"<b>{name}</b>"``) for
HTML and SQL: they keep every interpolated value separate by construction.

This module has no dependency on the rest of Ushka on purpose.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

__all__ = ["Untrusted", "is_untrusted", "source_of", "taint", "taint_deep"]

UNKNOWN = "unknown"


class Untrusted(str):
    """A string whose content came from outside the program.

    Create one with ``Untrusted(value, source)``: `value` is anything `str()`
    accepts; `source` says where it came from (e.g. ``"query:next"`` or
    ``"llm"``) and appears in error messages. If `source` is omitted and
    `value` is already `Untrusted`, its source is kept.
    """

    source: str

    def __new__(cls, value: object = "", source: str | None = None) -> Untrusted:
        obj = super().__new__(cls, value)
        obj.source = source if source is not None else getattr(value, "source", UNKNOWN)
        return obj

    # -- identity -----------------------------------------------------------

    # `__repr__` is inherited on purpose: `repr(x)` / `f"{x!r}"` must produce
    # exactly what a plain string would, or output and JSON-in-JS break.
    # Use `describe()` for debugging.

    def describe(self) -> str:
        """A debugging representation showing the value and its source."""
        return f"Untrusted({str.__repr__(self)}, source={self.source!r})"

    def __reduce__(self):
        return (Untrusted, (str(self), self.source))

    # `__str__` is deliberately NOT overridden: `str(x)` returns a plain copy.
    # Returning `self` would keep the mark, but pathlib (< 3.13) feeds
    # `str(part)` to `sys.intern()`, which rejects str subclasses, so
    # `Path(request.query["f"])` would crash with a cryptic TypeError.

    def __format__(self, spec: str) -> Untrusted:
        return self._wrap(str.__format__(self, spec))

    # -- helpers --------------------------------------------------------------

    def _wrap(self, value: Any) -> Any:
        if isinstance(value, str):
            return Untrusted(value, self.source)
        return value

    # -- operators ------------------------------------------------------------

    def __add__(self, other: Any) -> Untrusted:
        result = str.__add__(self, other)
        if result is NotImplemented:
            return result
        return self._wrap(result)

    def __radd__(self, other: Any) -> Untrusted:
        if not isinstance(other, str):
            return NotImplemented
        return self._wrap(str.__add__(other, self))

    def __mul__(self, n: Any) -> Untrusted:
        result = str.__mul__(self, n)
        return result if result is NotImplemented else self._wrap(result)

    __rmul__ = __mul__

    def __mod__(self, args: Any) -> Untrusted:
        result = str.__mod__(self, args)
        return result if result is NotImplemented else self._wrap(result)

    def __rmod__(self, template: Any) -> Untrusted:
        if not isinstance(template, str):
            return NotImplemented
        return self._wrap(str.__mod__(template, self))

    def __getitem__(self, key: Any) -> Untrusted:
        return self._wrap(str.__getitem__(self, key))

    def __iter__(self):
        for ch in str.__iter__(self):
            yield Untrusted(ch, self.source)

    # -- methods returning lists/tuples --------------------------------------

    def split(self, sep: str | None = None, maxsplit: int = -1) -> list:
        return [self._wrap(p) for p in str.split(self, sep, maxsplit)]

    def rsplit(self, sep: str | None = None, maxsplit: int = -1) -> list:
        return [self._wrap(p) for p in str.rsplit(self, sep, maxsplit)]

    def splitlines(self, keepends: bool = False) -> list:
        return [self._wrap(p) for p in str.splitlines(self, keepends)]

    def partition(self, sep: str) -> tuple:
        return tuple(self._wrap(p) for p in str.partition(self, sep))

    def rpartition(self, sep: str) -> tuple:
        return tuple(self._wrap(p) for p in str.rpartition(self, sep))

    def join(self, iterable: Iterable[str]) -> Untrusted:
        return self._wrap(str.join(self, iterable))


# Methods that take a string and return one new string: wrap them all.
_STR_RETURNING = ["capitalize", "casefold", "center", "expandtabs", "format", "format_map", "ljust", "lower", "lstrip", "removeprefix", "removesuffix", "replace", "rjust", "rstrip", "strip", "swapcase", "title", "translate", "upper", "zfill"]


def _make_wrapper(name: str):
    base = getattr(str, name)

    def method(self, *args, **kwargs):
        return self._wrap(base(self, *args, **kwargs))

    method.__name__ = name
    method.__qualname__ = f"Untrusted.{name}"
    method.__doc__ = base.__doc__
    return method


for _name in _STR_RETURNING:
    setattr(Untrusted, _name, _make_wrapper(_name))
del _name


# -- public helpers ----------------------------------------------------------


def taint(value: Any, source: str = UNKNOWN) -> Any:
    """Marks `value` as untrusted if it is a string; returns other types as-is."""
    if isinstance(value, str):
        return Untrusted(value, source)
    return value


def taint_deep(value: Any, source: str = UNKNOWN) -> Any:
    """Marks every string inside dicts/lists/tuples as untrusted.

    Dictionary *keys* are marked too: they come from the same payload.
    """
    if isinstance(value, str):
        return Untrusted(value, source)
    if isinstance(value, dict):
        return {taint_deep(k, source): taint_deep(v, source) for k, v in value.items()}
    if isinstance(value, list):
        return [taint_deep(v, source) for v in value]
    if isinstance(value, tuple):
        return tuple(taint_deep(v, source) for v in value)
    return value


def is_untrusted(value: Any) -> bool:
    """True if `value` is an `Untrusted` string."""
    return isinstance(value, Untrusted)


def source_of(value: Any) -> str | None:
    """The recorded source of an `Untrusted` value, or ``None``."""
    return value.source if isinstance(value, Untrusted) else None
