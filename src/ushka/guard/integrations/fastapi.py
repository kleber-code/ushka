"""Ushka Guard for FastAPI.

    from ushka.guard.integrations import fastapi as guard
    guard.install(rewrite_packages=["myapp"])      # once, before the app handles requests

It does everything `ushka.guard.integrations.starlette` does (the request
objects and the HTML, redirect and file sinks), and one more thing FastAPI
needs. FastAPI validates parameters with pydantic, which hands your endpoint a
plain ``str`` even when the request said otherwise. So the guard marks the
values FastAPI took from the request (path, query, header, cookie and body
parameters, inside pydantic models too) as `Untrusted` right before your
endpoint or dependency runs.

Only an exact ``str`` is marked. ``int``, ``bool``, ``UUID``, ``Enum`` and
``Literal`` parameters are validated values and stay as they are: that is
validation doing the sanitising.

This relies on a FastAPI internal (``solve_dependencies``). If a FastAPI
release changes it, ``install`` raises instead of quietly protecting nothing.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Iterable

from ..untrusted import Untrusted
from . import starlette as _starlette

_originals: dict = {}


def _mark(value: Any, source: str, depth: int = 0) -> Any:
    if depth > 20:
        return value
    if type(value) is str:
        return Untrusted(value, source)
    if isinstance(value, Untrusted):
        return value
    if isinstance(value, dict):
        return {_mark(k, source, depth + 1): _mark(v, source, depth + 1) for k, v in value.items()}
    if type(value) in (list, tuple, set, frozenset):
        return type(value)(_mark(v, source, depth + 1) for v in value)
    if hasattr(value, "model_fields") and hasattr(value, "__dict__"):  # a pydantic model
        for name, item in list(value.__dict__.items()):
            value.__dict__[name] = _mark(item, f"{source}.{name}", depth + 1)
        return value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        for f in dataclasses.fields(value):
            object.__setattr__(value, f.name, _mark(getattr(value, f.name), f"{source}.{f.name}", depth + 1))
        return value
    return value


def _is_literal(field: Any) -> bool:
    """A ``Literal[...]`` parameter is validation: it can only be one of your own constants."""
    import typing

    annotation = getattr(getattr(field, "field_info", None), "annotation", None)
    for _ in range(4):
        origin = typing.get_origin(annotation)
        if origin is typing.Literal:
            return True
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        if origin in (typing.Annotated, typing.Union) or str(origin) == "<class 'types.UnionType'>":
            annotation = args[0] if args else None
        else:
            return False
    return False


def install(rewrite_packages: Iterable[str] = ()) -> None:
    """Turns the guard on for FastAPI. Calling it twice is harmless."""
    if _originals:
        return
    import inspect

    from fastapi import routing
    from fastapi.dependencies import utils

    original = getattr(utils, "solve_dependencies", None)
    if original is None or not inspect.iscoroutinefunction(original):
        raise RuntimeError(
            "ushka.guard does not support this FastAPI version: fastapi.dependencies.utils.solve_dependencies "
            "changed. Please report it; nothing was installed."
        )

    async def solve_dependencies(*args: Any, **kwargs: Any):
        solved = await original(*args, **kwargs)
        dependant = kwargs.get("dependant")
        for kind, group in (
            ("path", "path_params"), ("query", "query_params"), ("header", "header_params"),
            ("cookie", "cookie_params"), ("body", "body_params"),
        ):
            for field in getattr(dependant, group, ()):
                if field.name in solved.values and not _is_literal(field):
                    solved.values[field.name] = _mark(solved.values[field.name], f"{kind}:{field.name}")
        return solved

    _originals[(utils, "solve_dependencies")] = original
    utils.solve_dependencies = solve_dependencies
    if getattr(routing, "solve_dependencies", None) is original:
        _originals[(routing, "solve_dependencies")] = original
        routing.solve_dependencies = solve_dependencies
    try:
        _starlette.install(rewrite_packages)
    except Exception:
        uninstall()
        raise


def uninstall() -> None:
    """Restores FastAPI's and Starlette's own code."""
    for (module, name), original in _originals.items():
        setattr(module, name, original)
    _originals.clear()
    _starlette.uninstall()
