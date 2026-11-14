"""Ushka Guard for Django.

    # settings.py
    MIDDLEWARE = ["ushka.guard.integrations.django.GuardMiddleware", ...]

    # e.g. in apps.py ready(), or manage.py / wsgi.py
    from ushka.guard.integrations import django as guard
    guard.install(rewrite_packages=["myproject"])

The middleware makes what a client sends `Untrusted`: ``request.GET``,
``request.POST``, ``request.COOKIES``, ``request.headers``, the URL keyword
arguments of your view, and ``request.json()`` (added by the middleware).

``install()`` makes these sinks refuse such a string: ``HttpResponse`` with HTML,
every ``HttpResponseRedirect`` (and so ``redirect()``) and ``mark_safe`` (which
is what the ``|safe`` filter calls). It patches Django's classes for the whole
process, and ``uninstall()`` restores them.

``rewrite_packages`` lists your own packages: the guard recompiles them on
import so the mark survives f-strings (see `ushka.guard.rewrite`). Without it,
``HttpResponse(f"<p>{name}</p>")`` is a plain str and slips past.
"""

from __future__ import annotations

import json as _json
from typing import Iterable

from .. import check_html, check_markup, check_redirect, rewrite, taint, taint_deep
from ..untrusted import Untrusted

_MARKUP = ("text/html", "application/xhtml+xml", "image/svg+xml", "text/xml")
_originals: dict = {}


def _tainted_querydict(source, kind: str):
    from django.http import QueryDict

    out = QueryDict(mutable=True, encoding=getattr(source, "encoding", None))
    for key, values in source.lists():
        out.setlist(Untrusted(key, f"{kind}:{key}"), [Untrusted(v, f"{kind}:{key}") if isinstance(v, str) else v for v in values])
    out._mutable = False
    return out


class GuardMiddleware:
    """Marks the request's client data as `Untrusted`."""

    def __init__(self, get_response) -> None:
        self.get_response = get_response

    def __call__(self, request):
        request.GET = _tainted_querydict(request.GET, "query")
        request.COOKIES = {Untrusted(k, f"cookie:{k}"): Untrusted(v, f"cookie:{k}") for k, v in request.COOKIES.items()}
        request.META = {
            k: (taint(v, f"header:{k.removeprefix('HTTP_').lower().replace('_', '-')}") if isinstance(v, str) and (k.startswith("HTTP_") or k in ("CONTENT_TYPE", "QUERY_STRING")) else v)
            for k, v in request.META.items()
        }
        load = request._load_post_and_files

        def load_tainted():  # taint the form after Django parses it, without reading the body early
            load()
            request._post = _tainted_querydict(request._post, "form")

        request._load_post_and_files = load_tainted
        request.json = lambda: taint_deep(_json.loads(request.body), "json")
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        for key, value in list(view_kwargs.items()):
            view_kwargs[key] = taint_deep(value, f"path:{key}")


def install(rewrite_packages: Iterable[str] = ()) -> None:
    """Turns the sink checks on for Django. Calling it twice is harmless."""
    if _originals:
        return
    from django.http import response as http_response
    from django.utils import safestring

    def wrap(owner, name: str, make) -> None:
        original = getattr(owner, name)
        _originals[(owner, name)] = original
        setattr(owner, name, make(original))

    def wrap_http_response(original):
        def __init__(self, content=b"", *args, **kwargs):
            content_type = kwargs.get("content_type") or (args[0] if args and isinstance(args[0], str) else None) or "text/html"
            if isinstance(content, str) and content_type.split(";")[0].strip().lower() in _MARKUP:
                check_html(content)
            original(self, content, *args, **kwargs)

        return __init__

    def wrap_redirect(original):
        def __init__(self, redirect_to, *args, **kwargs):
            # str() would drop the Untrusted mark, so only convert what is not text already
            check_redirect(redirect_to if isinstance(redirect_to, str) else str(redirect_to))
            original(self, redirect_to, *args, **kwargs)

        return __init__

    def wrap_mark_safe(original):
        def mark_safe(s):
            check_markup(s)
            return original(s)

        return mark_safe

    wrap(http_response.HttpResponse, "__init__", wrap_http_response)
    wrap(http_response.HttpResponseRedirectBase, "__init__", wrap_redirect)
    wrap(safestring, "mark_safe", wrap_mark_safe)

    if rewrite_packages:
        rewrite.install(list(rewrite_packages))


def uninstall() -> None:
    """Restores Django's own classes."""
    for (owner, name), original in _originals.items():
        setattr(owner, name, original)
    _originals.clear()
    rewrite.uninstall()
