"""Ushka Guard for Starlette and FastAPI.

    from ushka.guard.integrations import starlette as guard
    guard.install(rewrite_packages=["myapp"])      # once, before the app handles requests

After that, everything a client sends is an `Untrusted` string:
``request.query_params``, ``request.headers``, ``request.cookies``,
``request.path_params``, ``await request.json()`` and ``await request.form()``.
FastAPI reads the same objects, so its ``str`` parameters arrive untrusted too.

And these sinks refuse such a string with an error that says how to fix it:
``HTMLResponse``, ``RedirectResponse`` and ``FileResponse``.

`install` changes Starlette's classes for the whole process (that is the only
way to cover code that does not know about Ushka). ``uninstall()`` restores them.

``rewrite_packages`` lists your own packages: the guard recompiles them on
import so the mark survives f-strings, ``.format`` and ``%`` (without it,
``f"<p>{name}</p>"`` is a plain str and slips past). See `ushka.guard.rewrite`.
"""

from __future__ import annotations

from collections.abc import Iterable

from .. import check_html, check_path, check_redirect, rewrite, taint, taint_deep
from ..untrusted import Untrusted

_MARKUP = ("text/html", "application/xhtml+xml", "image/svg+xml", "text/xml")
_originals: dict = {}


def _taint_list(pairs, kind: str):
    return [(Untrusted(k, f"{kind}:{k}"), Untrusted(v, f"{kind}:{k}") if isinstance(v, str) else v) for k, v in pairs]


def install(rewrite_packages: Iterable[str] = ()) -> None:
    """Turns the guard on for Starlette (and FastAPI). Calling it twice is harmless."""
    if _originals:
        return
    from starlette.datastructures import FormData, Headers, QueryParams
    from starlette.requests import HTTPConnection, Request
    from starlette.responses import FileResponse, RedirectResponse, Response

    class TaintedHeaders(Headers):
        def __getitem__(self, key):
            return taint(super().__getitem__(key), f"header:{key.lower()}")

        def getlist(self, key):
            return [taint(v, f"header:{key.lower()}") for v in super().getlist(key)]

        def items(self):
            return [(k, taint(v, f"header:{k}")) for k, v in super().items()]

        def values(self):
            return [v for _, v in self.items()]

    class TaintedQueryParams(QueryParams):
        def __init__(self, source) -> None:
            super().__init__(source.multi_items())
            # QueryParams runs str() on everything, which drops the mark: put it back.
            self._list = _taint_list(self._list, "query")
            self._dict = dict(self._list)

    def patch_property(cls, name: str, make) -> None:
        original = cls.__dict__[name]
        _originals[(cls, name)] = original
        cache = f"_ushka_guard_{name}"

        def getter(self):
            if cache not in self.__dict__:
                self.__dict__[cache] = make(original.fget(self))
            return self.__dict__[cache]

        setattr(cls, name, property(getter))

    patch_property(HTTPConnection, "query_params", TaintedQueryParams)
    patch_property(HTTPConnection, "headers", lambda h: TaintedHeaders(raw=h.raw))
    patch_property(HTTPConnection, "cookies", lambda c: {Untrusted(k, f"cookie:{k}"): Untrusted(v, f"cookie:{k}") for k, v in c.items()})
    patch_property(HTTPConnection, "path_params", lambda p: {k: taint_deep(v, f"path:{k}") for k, v in p.items()})

    def wrap(cls, name: str, make) -> None:
        original = cls.__dict__[name]
        _originals[(cls, name)] = original
        setattr(cls, name, make(original))

    def wrap_json(original):
        async def json(self):
            return taint_deep(await original(self), "json")

        return json

    def wrap_form(original):
        async def form(self, *args, **kwargs):
            data = await original(self, *args, **kwargs)
            return FormData(_taint_list(data.multi_items(), "form"))

        return form

    wrap(Request, "json", wrap_json)
    wrap(Request, "form", wrap_form)

    def wrap_response_init(original):
        def __init__(self, content=None, status_code=200, headers=None, media_type=None, background=None):
            kind = (media_type or getattr(self, "media_type", None) or "").split(";")[0].strip().lower()
            if isinstance(content, str) and kind in _MARKUP:
                check_html(content)
            original(self, content, status_code, headers, media_type, background)

        return __init__

    def wrap_redirect_init(original):
        def __init__(self, url, *args, **kwargs):
            check_redirect(str(url) if not isinstance(url, str) else url)
            original(self, url, *args, **kwargs)

        return __init__

    def wrap_file_init(original):
        def __init__(self, path, *args, **kwargs):
            check_path(path)
            original(self, path, *args, **kwargs)

        return __init__

    wrap(Response, "__init__", wrap_response_init)
    wrap(RedirectResponse, "__init__", wrap_redirect_init)
    wrap(FileResponse, "__init__", wrap_file_init)

    if rewrite_packages:
        rewrite.install(list(rewrite_packages))


def uninstall() -> None:
    """Restores Starlette's own classes."""
    for (cls, name), original in _originals.items():
        setattr(cls, name, original)
    _originals.clear()
    rewrite.uninstall()
