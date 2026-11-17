"""Type-driven validation of request data, with no dependencies.

`coerce` turns what the client sent (strings from the URL, JSON from the body)
into the type a handler declared, or reports *every* problem at once, each with
its location, like ``["body", "items", 0, "price"]``.

Converting is also sanitising. A value declared ``int``, ``float``, ``bool``,
``UUID``, a date, an ``Enum`` or a ``Literal`` comes out as a plain value of
that type, never as ``Untrusted``: it can no longer carry markup or SQL. A
``str`` stays ``Untrusted``, because its content is still the client's.

Supported: ``str int float bool Decimal UUID date datetime time``, ``Enum``,
``Literal``, ``Optional`` / unions, ``list set tuple dict``, dataclasses and
``TypedDict`` (nested), and ``Annotated[..., Field(...)]`` for limits.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import enum
import inspect
import math
import re
import types
import typing
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from ushka.http.exceptions import HTTPError
from ushka.http.uploads import UploadFile

_MISSING = object()
_TRUE = {"true", "1", "yes", "on"}
_FALSE = {"false", "0", "no", "off"}


class RequestValidationError(HTTPError):
    """422: the request did not match what the handler declared.

    `errors` is a list of ``{"loc": [...], "msg": str, "type": str}``. The
    client's input is deliberately not echoed back.
    """

    def __init__(self, errors: list[dict]) -> None:
        super().__init__("error.html", 422, "Unprocessable Entity")
        self.errors = errors


class Field:
    """Limits for a value. Use inside ``Annotated[int, Field(ge=1)]``, or via
    `Query`, `Path`, `Header`, `Cookie`, `Body` and `Form`, which accept the same."""

    def __init__(
        self,
        *,
        gt=None,
        ge=None,
        lt=None,
        le=None,
        min_length: int | None = None,
        max_length: int | None = None,
        pattern: str | None = None,
        description: str | None = None,
    ) -> None:
        self.gt, self.ge, self.lt, self.le = gt, ge, lt, le
        self.min_length, self.max_length = min_length, max_length
        self.pattern = re.compile(pattern) if pattern else None
        self.description = description

    def check(self, value: Any, loc: list, errors: list) -> bool:
        before = len(errors)

        def bad(kind: str, msg: str) -> None:
            errors.append({"loc": list(loc), "msg": msg, "type": kind})

        if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
            if self.gt is not None and not value > self.gt:
                bad("greater_than", f"Input should be greater than {self.gt}")
            if self.ge is not None and not value >= self.ge:
                bad("greater_than_equal", f"Input should be greater than or equal to {self.ge}")
            if self.lt is not None and not value < self.lt:
                bad("less_than", f"Input should be less than {self.lt}")
            if self.le is not None and not value <= self.le:
                bad("less_than_equal", f"Input should be less than or equal to {self.le}")
        if hasattr(value, "__len__") and not isinstance(value, (dict,)):
            if self.min_length is not None and len(value) < self.min_length:
                bad("too_short", f"Should have at least {self.min_length} item(s) or character(s)")
            if self.max_length is not None and len(value) > self.max_length:
                bad("too_long", f"Should have at most {self.max_length} item(s) or character(s)")
        if self.pattern is not None and isinstance(value, str) and not self.pattern.search(value):
            bad("string_pattern_mismatch", f"Should match pattern {self.pattern.pattern!r}")
        return len(errors) == before


def validate(value: Any, tp: Any, loc: list | tuple = ()) -> Any:
    """Coerces `value` to `tp`; raises `RequestValidationError` listing all problems."""
    errors: list[dict] = []
    result = coerce(value, tp, list(loc), errors)
    if errors:
        raise RequestValidationError(errors)
    return result


def hints_of(obj: Any) -> dict[str, Any]:
    """Type hints of a class or function, tolerating hints that cannot be resolved."""
    try:
        return typing.get_type_hints(obj, include_extras=True)
    except Exception:  # noqa: BLE001 - get_type_hints raises NameError, TypeError... for any unresolvable hint
        return {}


def coerce(value: Any, tp: Any, loc: list, errors: list) -> Any:
    """Returns the converted value, or ``_MISSING`` after appending to `errors`."""

    def fail(kind: str, msg: str) -> Any:
        errors.append({"loc": list(loc), "msg": msg, "type": kind})
        return _MISSING

    if tp is Any or tp is object or tp is inspect.Parameter.empty:
        return value
    if tp is None or tp is type(None):
        return None if value is None else fail("none_required", "Input should be null")

    origin = typing.get_origin(tp)
    args = typing.get_args(tp)

    if origin is typing.Annotated:
        inner, *extras = args
        result = coerce(value, inner, loc, errors)
        if result is _MISSING:
            return result
        for extra in extras:
            if isinstance(extra, Field) and not extra.check(result, loc, errors):
                return _MISSING
        return result

    if origin in (typing.Union, types.UnionType):
        if value is None and type(None) in args:
            return None
        failures: list[dict] = []
        for member in (a for a in args if a is not type(None)):
            attempt: list[dict] = []
            result = coerce(value, member, loc, attempt)
            if result is not _MISSING:
                return result
            failures = failures or attempt
        errors.extend(failures or [{"loc": list(loc), "msg": "Input is not valid", "type": "union"}])
        return _MISSING

    if origin is typing.Literal:
        for option in args:
            if value == option or (isinstance(value, str) and not isinstance(option, str) and value == str(option)):
                return option  # the declared constant, never the client's string
        return fail("literal_error", "Input should be " + ", ".join(repr(a) for a in args))

    if isinstance(tp, type) and issubclass(tp, enum.Enum):
        for member in tp:
            if value == member.value or (isinstance(value, str) and value == str(member.value)):
                return member
        return fail("enum", "Input should be one of: " + ", ".join(str(m.value) for m in tp))

    if tp is bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in _TRUE | _FALSE:
            return value.lower() in _TRUE
        return fail("bool_parsing", "Input should be a valid boolean")

    if tp is int:
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            return fail("int_type", "Input should be a valid integer")
        try:
            return int(value)
        except ValueError:
            return fail("int_parsing", "Input should be a valid integer")

    if tp is float:
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            return fail("float_type", "Input should be a valid number")
        try:
            number = float(value)
        except ValueError:
            return fail("float_parsing", "Input should be a valid number")
        return number if math.isfinite(number) else fail("finite_number", "Input should be a finite number")

    if tp is Decimal:
        try:
            number = Decimal(str(value)) if not isinstance(value, bool) else None
            if number is None or not number.is_finite():
                raise InvalidOperation
            return number
        except (InvalidOperation, ValueError):
            return fail("decimal_parsing", "Input should be a valid decimal")

    if tp is str:
        return value if isinstance(value, str) else fail("string_type", "Input should be a valid string")

    if tp in (uuid.UUID, dt.date, dt.datetime, dt.time):
        if isinstance(value, tp):
            return value
        try:
            if tp is uuid.UUID:
                return uuid.UUID(str(value))
            return tp.fromisoformat(str(value))
        except (ValueError, TypeError):
            return fail(f"{tp.__name__.lower()}_parsing", f"Input should be a valid {tp.__name__}")

    if origin in (list, set, frozenset, tuple, typing.Sequence, typing.Iterable) or tp in (list, set, frozenset, tuple):
        if isinstance(value, (str, UploadFile)) or not isinstance(value, (list, tuple, set, frozenset)):
            value = [value] if isinstance(value, (str, UploadFile)) else value  # ?tag=a: one item is a list of one
        if not isinstance(value, (list, tuple, set, frozenset)):
            return fail("list_type", "Input should be a valid list")
        item_tp = args[0] if args and args[0] is not Ellipsis else Any
        items, ok = [], True
        for i, item in enumerate(value):
            converted = coerce(item, item_tp, [*loc, i], errors)
            ok = ok and converted is not _MISSING
            items.append(converted)
        if not ok:
            return _MISSING
        kind = origin or tp
        return kind(items) if kind in (set, frozenset, tuple) else items

    if origin is dict or tp is dict:
        if not isinstance(value, dict):
            return fail("dict_type", "Input should be a valid object")
        val_tp = args[1] if len(args) == 2 else Any
        out, ok = {}, True
        for key, item in value.items():
            converted = coerce(item, val_tp, [*loc, key], errors)
            ok = ok and converted is not _MISSING
            out[key] = converted
        return out if ok else _MISSING

    if dataclasses.is_dataclass(tp) and isinstance(tp, type):
        return _build_model(value, tp, loc, errors, fail)

    if typing.is_typeddict(tp):
        return _build_model(value, tp, loc, errors, fail)

    if not isinstance(tp, type):
        return value  # a type we do not know how to check: leave it to the handler
    return value if isinstance(value, tp) else fail("type_error", f"Input should be a valid {getattr(tp, '__name__', tp)}")


def _build_model(value, tp, loc, errors, fail):
    """Dataclass or TypedDict from a JSON object. Unknown keys are dropped, so
    a client can never set a field you did not declare (no mass assignment)."""
    if not isinstance(value, dict):
        return fail("model_type", "Input should be a valid object")
    hints = hints_of(tp)
    if typing.is_typeddict(tp):
        required = getattr(tp, "__required_keys__", frozenset())
        spec = {name: (name in required, _MISSING) for name in hints}
    else:
        spec = {}
        for f in dataclasses.fields(tp):
            if not f.init:
                continue
            has_default = f.default is not dataclasses.MISSING or f.default_factory is not dataclasses.MISSING
            spec[f.name] = (not has_default, _MISSING)
    out, ok = {}, True
    for name, (is_required, _) in spec.items():
        if name not in value:
            if is_required:
                errors.append({"loc": [*loc, name], "msg": "Field required", "type": "missing"})
                ok = False
            continue
        converted = coerce(value[name], hints.get(name, Any), [*loc, name], errors)
        if converted is _MISSING:
            ok = False
        else:
            out[name] = converted
    if not ok:
        return _MISSING
    if typing.is_typeddict(tp):
        return out
    try:
        return tp(**out)
    except (ValueError, TypeError) as exc:
        return fail("value_error", str(exc) or "Invalid value")
