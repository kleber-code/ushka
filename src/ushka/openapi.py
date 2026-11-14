"""OpenAPI 3.1 description of your app, generated from the handler signatures.

It reads the same parameter plans the request validation uses, so the document
cannot drift from what the app actually accepts. ``app.openapi()`` returns the
dict and ``app.enable_openapi()`` serves it as JSON.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import enum
import inspect
import re
import typing
import uuid
from decimal import Decimal
from typing import Any

from ushka.http.params import Depends, Param, build_plan
from ushka.http.validation import Field, hints_of

_PATH_SEGMENT = re.compile(r"\[(?:(?:path|int):)?([A-Za-z_][A-Za-z0-9_]*)\]")
_IN = {"query": "query", "header": "header", "cookie": "cookie", "path": "path"}
_PRIMITIVES = {
    str: {"type": "string"},
    int: {"type": "integer"},
    float: {"type": "number"},
    bool: {"type": "boolean"},
    Decimal: {"type": "string", "format": "decimal"},
    uuid.UUID: {"type": "string", "format": "uuid"},
    dt.datetime: {"type": "string", "format": "date-time"},
    dt.date: {"type": "string", "format": "date"},
    dt.time: {"type": "string", "format": "time"},
}


class _Schemas:
    """Collects reusable models into ``components.schemas``."""

    def __init__(self) -> None:
        self.components: dict[str, dict] = {}

    def of(self, tp: Any) -> dict:
        origin, args = typing.get_origin(tp), typing.get_args(tp)
        if tp in (Any, inspect.Parameter.empty, object):
            return {}
        if origin is typing.Annotated:
            schema = dict(self.of(args[0]))
            for extra in args[1:]:
                if isinstance(extra, Field):
                    schema.update(_limits(extra, schema.get("type")))
            return schema
        if origin in (typing.Union, getattr(__import__("types"), "UnionType", None)):
            members = [self.of(a) for a in args if a is not type(None)]
            if type(None) in args:
                members.append({"type": "null"})
            return members[0] if len(members) == 1 else {"anyOf": members}
        if origin is typing.Literal:
            return {"enum": list(args)}
        if origin in (list, set, frozenset, typing.Sequence) or tp in (list, set, frozenset):
            schema = {"type": "array", "items": self.of(args[0]) if args else {}}
            return {**schema, "uniqueItems": True} if origin in (set, frozenset) else schema
        if origin is tuple:
            return {"type": "array", "items": self.of(args[0]) if args and args[0] is not Ellipsis else {}}
        if origin is dict or tp is dict:
            return {"type": "object", "additionalProperties": self.of(args[1]) if len(args) == 2 else {}}
        if isinstance(tp, type) and issubclass(tp, enum.Enum):
            return self._named(tp, lambda: {"enum": [m.value for m in tp]})
        if tp in _PRIMITIVES:
            return dict(_PRIMITIVES[tp])
        if dataclasses.is_dataclass(tp) and isinstance(tp, type):
            return self._named(tp, lambda: self._model(tp, hints_of(tp), {
                f.name: f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
                for f in dataclasses.fields(tp) if f.init
            }))
        if typing.is_typeddict(tp):
            required = getattr(tp, "__required_keys__", frozenset())
            return self._named(tp, lambda: self._model(tp, hints_of(tp), {n: n in required for n in hints_of(tp)}))
        return {}

    def _named(self, tp: type, build) -> dict:
        name = tp.__name__
        if name not in self.components:
            self.components[name] = {}  # break recursion before building
            self.components[name] = build()
        return {"$ref": f"#/components/schemas/{name}"}

    def _model(self, tp: type, hints: dict, required: dict) -> dict:
        schema: dict[str, Any] = {"type": "object", "properties": {n: self.of(hints.get(n, Any)) for n in required}}
        needed = [n for n, req in required.items() if req]
        if needed:
            schema["required"] = needed
        return schema


def _limits(f: Field, kind: str | None) -> dict:
    out: dict[str, Any] = {}
    for src, dst in (("gt", "exclusiveMinimum"), ("ge", "minimum"), ("lt", "exclusiveMaximum"), ("le", "maximum")):
        if getattr(f, src) is not None:
            out[dst] = getattr(f, src)
    length = ("minItems", "maxItems") if kind == "array" else ("minLength", "maxLength")
    if f.min_length is not None:
        out[length[0]] = f.min_length
    if f.max_length is not None:
        out[length[1]] = f.max_length
    if f.pattern is not None:
        out["pattern"] = f.pattern.pattern
    if f.description:
        out["description"] = f.description
    return out


def _specs(func, path_names: frozenset, method: str):
    """Every declared parameter of `func`, following `Depends` into the dependency's own."""
    for spec in build_plan(func, path_names, method):
        if spec.kind == "depends":
            yield from _specs(spec.depends.dependency, path_names, method)
        else:
            yield spec


def _operation(func, path_names: frozenset, method: str, schemas: _Schemas) -> dict:
    doc = inspect.getdoc(func) or ""
    summary, _, description = doc.partition("\n")
    op: dict[str, Any] = {"operationId": f"{method.lower()}_{func.__name__}"}
    if summary:
        op["summary"] = summary.strip()
    if description.strip():
        op["description"] = description.strip()
    parameters, body, seen = [], [], set()
    for spec in _specs(func, path_names, method):
        if spec.kind in ("request", "response", "config") or (spec.kind, spec.name) in seen:
            continue
        seen.add((spec.kind, spec.name))
        marker: Param | None = spec.marker
        name = marker.alias if marker and marker.alias else spec.name
        tp = typing.Annotated[spec.annotation, marker] if marker else spec.annotation
        if spec.kind in _IN:
            if spec.kind == "header" and not (marker and marker.alias):
                name = name.replace("_", "-")
            parameters.append({
                "name": name,
                "in": _IN[spec.kind],
                "required": spec.kind == "path" or spec.default is _required(),
                "schema": schemas.of(tp),
            })
        elif spec.kind in ("body", "form"):
            body.append((spec, name, tp))
    if parameters:
        op["parameters"] = parameters
    if body:
        op["requestBody"] = _request_body(body, schemas)
    op["responses"] = {
        "200": {"description": "Successful response"},
        "422": {"description": "Validation error"},
    }
    return op


def _required():
    from ushka.http import params

    return params._REQUIRED


def _request_body(body: list, schemas: _Schemas) -> dict:
    kind = body[0][0].kind
    if len(body) == 1 and not (body[0][0].marker and body[0][0].marker.embed):
        schema = schemas.of(body[0][2])
    else:
        schema = {
            "type": "object",
            "properties": {name: schemas.of(tp) for _, name, tp in body},
            "required": [name for spec, name, _ in body if spec.default is _required()],
        }
    media = "application/x-www-form-urlencoded" if kind == "form" else "application/json"
    return {"required": True, "content": {media: {"schema": schema}}}


def build(router, title: str = "Ushka API", version: str = "0.1.0", skip: set | None = None) -> dict:
    """The OpenAPI document for every route registered on `router`."""
    schemas, paths = _Schemas(), {}
    skip = skip or set()

    def add(method: str, raw_path: str, func) -> None:
        if func in skip:
            return
        names = frozenset(_PATH_SEGMENT.findall(raw_path))
        url = _PATH_SEGMENT.sub(r"{\1}", raw_path)
        paths.setdefault(url, {})[method.lower()] = _operation(func, names, method, schemas)

    for method, routes in router.static_routes.items():
        for path, (func, _) in routes.items():
            add(method, path, func)
    for method, routes in router.dynamic_routes.items():
        for _, _, func, _, raw in routes:
            add(method, raw, func)

    doc: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": title, "version": version},
        "paths": dict(sorted(paths.items())),
    }
    if schemas.components:
        doc["components"] = {"schemas": schemas.components}
    return doc
