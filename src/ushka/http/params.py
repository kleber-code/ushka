"""Declared handler parameters: typed path/query/header/cookie/body and `Depends`.

A handler states what it needs in its signature and Ushka resolves it, then
validates it (see `ushka.http.validation`):

* a path parameter whose name is in the route (``[item_id]``) is converted to its annotation;
* ``Query()``, ``Header()``, ``Cookie()``, ``Body()``, ``Form()`` and ``Path()`` pick the source explicitly;
* a plain scalar annotation (``limit: int = 10``) is a query parameter;
* a dataclass, ``TypedDict``, ``dict`` or ``list`` annotation is the JSON body;
* an ``UploadFile`` (or ``list[UploadFile]``) annotation is a file of a multipart form;
* ``Depends(fn)`` runs ``fn`` first and passes you its result.

`request`, `response` and `config` keep working by name or annotation.
"""

from __future__ import annotations

import contextlib
import dataclasses
import inspect
import typing
from collections.abc import Callable
from typing import Any

from ushka.core.config import Config
from ushka.http.request import Request
from ushka.http.response import Response
from ushka.http.uploads import UploadFile
from ushka.http.validation import (
    _MISSING,
    Field,
    RequestValidationError,
    coerce,
    hints_of,
)
from ushka.http.websocket import WebSocket

_BODY_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_SCALARS = (str, int, float, bool)
_REQUIRED = object()


class Param(Field):
    """Base of `Query`, `Header`, `Cookie`, `Path`, `Body` and `Form`."""

    source = "query"

    def __init__(self, default: Any = _REQUIRED, *, alias: str | None = None, embed: bool = False, **limits) -> None:
        super().__init__(**limits)
        self.default = default
        self.alias = alias
        self.embed = embed


class Query(Param):
    source = "query"


class Header(Param):
    """A request header. ``user_agent`` is read as ``user-agent`` unless you set `alias`."""

    source = "header"


class Cookie(Param):
    source = "cookie"


class Path(Param):
    source = "path"


class Body(Param):
    source = "body"


class Form(Param):
    source = "form"


@dataclasses.dataclass(frozen=True)
class Depends:
    """``user = Depends(current_user)``: call `dependency` and inject its result.

    The dependency may be sync or async, may itself declare parameters and
    ``Depends``, and is called once per request (``use_cache=False`` to call
    it every time it is asked for). A generator dependency (``yield``) can
    clean up after the handler returns. Override in tests with
    ``app.dependency_overrides[original] = replacement``.
    """

    dependency: Callable[..., Any]
    use_cache: bool = True


@dataclasses.dataclass
class _Spec:
    name: str
    annotation: Any
    kind: str  # request response config depends path query header cookie body form
    marker: Param | None = None
    default: Any = _REQUIRED
    depends: Depends | None = None


_plans: dict[tuple, list[_Spec]] = {}


def _special(name: str, ann: Any, method: str = "") -> str | None:
    if ann is WebSocket or (method == "WEBSOCKET" and name in ("ws", "websocket")):
        return "websocket"
    if name == "request" or ann is Request:
        return "request"
    if name == "response" or ann is Response:
        return "response"
    if name == "config" or ann is Config:
        return "config"
    return None


def wants_upload(tp: Any) -> bool:
    """True for ``UploadFile``, ``UploadFile | None``, ``list[UploadFile]``, ``Annotated[...]`` of those."""
    if tp is UploadFile:
        return True
    return any(wants_upload(a) for a in typing.get_args(tp) if a is not type(None))


def _is_model(tp: Any) -> bool:
    tp = typing.get_args(tp)[0] if typing.get_origin(tp) is typing.Annotated else tp
    return (dataclasses.is_dataclass(tp) and isinstance(tp, type)) or typing.is_typeddict(tp)


def _is_body_type(tp: Any) -> bool:
    tp = typing.get_args(tp)[0] if typing.get_origin(tp) is typing.Annotated else tp
    origin = typing.get_origin(tp) or tp
    if origin in (typing.Union,) or str(origin) == "<class 'types.UnionType'>":
        return any(_is_body_type(a) for a in typing.get_args(tp) if a is not type(None))
    return (
        (dataclasses.is_dataclass(tp) and isinstance(tp, type))
        or typing.is_typeddict(tp)
        or origin in (dict, list)
    )


def build_plan(func: Callable, path_names: frozenset, method: str) -> list[_Spec]:
    key = (func, path_names, method)
    plan = _plans.get(key)
    if plan is not None:
        return plan
    hints = hints_of(func)
    plan = []
    for name, p in inspect.signature(func).parameters.items():
        if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        ann = hints.get(name, p.annotation)
        if isinstance(ann, str):  # could not be resolved (e.g. a TYPE_CHECKING import)
            ann = {"Request": Request, "Response": Response, "Config": Config}.get(ann.strip("'\""), inspect.Parameter.empty)
        marker, depends, inner = None, None, ann
        if typing.get_origin(ann) is typing.Annotated:
            inner, *extras = typing.get_args(ann)
            for extra in extras:
                if isinstance(extra, Depends):
                    depends = extra
                elif isinstance(extra, Param):
                    marker = extra
        default = p.default if p.default is not p.empty else _REQUIRED
        if isinstance(default, Depends):
            depends, default = default, _REQUIRED
        elif isinstance(default, Param):
            marker, default = default, default.default
        elif marker is not None and default is _REQUIRED:
            default = marker.default
        if depends:
            plan.append(_Spec(name, ann, "depends", default=default, depends=depends))
            continue
        special = _special(name, inner, method)
        if special:
            plan.append(_Spec(name, ann, special))
            continue
        if marker is not None:
            kind = "path" if name in path_names and marker.source == "query" else marker.source
        elif name in path_names:
            kind = "path"
        elif wants_upload(inner):
            kind = "form"
        elif _is_body_type(inner) and method in _BODY_METHODS:
            kind = "body"
        else:
            kind = "query"
        plan.append(_Spec(name, ann, kind, marker, default))
    _plans[key] = plan
    return plan


class Resolver:
    """Per-request state: the dependency cache and what to clean up afterwards."""

    def __init__(self, request: Request, response: Response | None = None) -> None:
        self.request = request
        self.response = response
        self.websocket: WebSocket | None = None
        self.cache: dict[Any, Any] = {}
        self.stack = contextlib.AsyncExitStack()

    async def close(self) -> None:
        await self.stack.aclose()

    async def call(self, func: Callable, supplied: dict | None = None) -> dict:
        """Builds the keyword arguments for `func`. `supplied` holds what the
        router already injected (request, response, config, path values).
        Raises `RequestValidationError` listing every problem."""
        supplied = supplied or {}
        path_params = self.request.path_params
        plan = build_plan(func, frozenset(path_params), self.request.method)
        kwargs: dict[str, Any] = {}
        errors: list[dict] = []
        body_specs = [s for s in plan if s.kind == "body" and s.name not in supplied]
        for spec in plan:
            if spec.kind == "response" and isinstance(supplied.get(spec.name), Response):
                self.response = supplied[spec.name]  # dependencies share the handler's response
        for spec in plan:
            if spec.name in supplied:
                value = supplied[spec.name]
                if spec.kind == "path":  # the router's Untrusted string, now typed
                    value = self._convert(spec, value, ["path", spec.name], errors)
                if value is not _MISSING:
                    kwargs[spec.name] = value
                continue
            value = await self._value(spec, body_specs, errors)
            if value is not _MISSING:
                kwargs[spec.name] = value
        if errors:
            raise RequestValidationError(errors)
        return kwargs

    async def _value(self, spec: _Spec, body_specs: list, errors: list) -> Any:
        req = self.request
        if spec.kind == "request":
            return req
        if spec.kind == "response":
            if self.response is None:
                self.response = Response()
            return self.response
        if spec.kind == "config":
            return req.app.config
        if spec.kind == "websocket":
            return self.websocket
        if spec.kind == "depends":
            return await self._depends(spec.depends, errors)
        name = (spec.marker.alias if spec.marker and spec.marker.alias else spec.name)
        if spec.kind == "path":
            raw = req.path_params.get(name, _MISSING)
            loc = ["path", name]
        elif spec.kind == "query":
            raw, loc = req.query.get(name, _MISSING), ["query", name]
        elif spec.kind == "header":
            raw = req.headers.get(name.lower().replace("_", "-") if not (spec.marker and spec.marker.alias) else name.lower(), _MISSING)
            loc = ["header", name]
        elif spec.kind == "cookie":
            raw, loc = req.cookies.get(name, _MISSING), ["cookie", name]
        elif spec.kind == "form":
            form = await req.form()
            if wants_upload(spec.annotation):
                raw, loc = await self._upload_value(spec.annotation, name), ["form", name]
            elif _is_model(spec.annotation):
                raw, loc = await self._form_model(form, spec.annotation), ["form"]
            else:
                raw, loc = form.get(name, _MISSING), ["form", name]
        else:  # body
            data = await req.json()
            embed = len(body_specs) > 1 or bool(spec.marker and spec.marker.embed)
            raw, loc = (data.get(name, _MISSING) if embed and isinstance(data, dict) else (_MISSING if embed else data)), ["body", *([name] if embed else [])]
        if raw is _MISSING:
            if spec.default is not _REQUIRED:
                return spec.default
            if typing.get_origin(spec.annotation) is typing.Union and type(None) in typing.get_args(spec.annotation):
                return None
            errors.append({"loc": loc, "msg": "Field required", "type": "missing"})
            return _MISSING
        return self._convert(spec, raw, loc, errors)

    async def _upload_value(self, tp: Any, name: str) -> Any:
        """The file(s) a field sent: a list for ``list[UploadFile]``, else the last one.
        A browser sends an empty part for a file input left blank: that is no file."""
        found = [u for u in (await self.request.uploads()).get(name, []) if u.filename or u.size]
        if not found:
            return _MISSING
        return found if _wants_list(tp) else found[-1]

    async def _form_model(self, form: dict, model: Any) -> dict:
        """The whole form as a dict for a dataclass/TypedDict: text fields plus files."""
        model = typing.get_args(model)[0] if typing.get_origin(model) is typing.Annotated else model
        data = dict(form)
        for field, hint in hints_of(model).items():
            if wants_upload(hint):
                value = await self._upload_value(hint, field)
                if value is not _MISSING:
                    data[field] = value
        return data

    @staticmethod
    def _convert(spec: _Spec, raw: Any, loc: list, errors: list) -> Any:
        tp = spec.annotation
        if tp is inspect.Parameter.empty:
            return raw  # unannotated stays Untrusted text
        if spec.marker is not None:
            tp = typing.Annotated[tp, spec.marker]
        return coerce(raw, tp, loc, errors)

    async def _depends(self, dep: Depends, errors: list) -> Any:
        func = self.request.app.dependency_overrides.get(dep.dependency, dep.dependency)
        if dep.use_cache and func in self.cache:
            return self.cache[func]
        kwargs = await self.call(func)
        if inspect.isasyncgenfunction(func):
            value = await self.stack.enter_async_context(contextlib.asynccontextmanager(func)(**kwargs))
        elif inspect.isgeneratorfunction(func):
            value = self.stack.enter_context(contextlib.contextmanager(func)(**kwargs))
        else:
            value = func(**kwargs)
            if inspect.isawaitable(value):
                value = await value
        if dep.use_cache:
            self.cache[func] = value
        return value


def _wants_list(tp: Any) -> bool:
    if typing.get_origin(tp) in (list, set, tuple, frozenset, typing.Sequence):
        return True
    return any(_wants_list(a) for a in typing.get_args(tp) if a is not type(None))
