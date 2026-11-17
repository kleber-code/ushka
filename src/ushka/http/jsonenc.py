"""JSON encoding for responses: the types an app returns every day.

``json.dumps`` refuses `datetime`, `Decimal` and `UUID`, so a handler returning
one answered 500. `dumps` writes them like Django's ``JsonResponse`` does
(ISO 8601 text; a `Decimal` as a string so no precision is lost).
"""

from __future__ import annotations

import datetime
import json
import uuid
from decimal import Decimal
from typing import Any


def default(value: Any) -> Any:
    """``json.dumps(default=...)`` hook for dates, times, decimals and UUIDs."""
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, (Decimal, uuid.UUID)):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def dumps(value: Any, **kwargs: Any) -> str:
    """`json.dumps` that also understands `datetime`, `date`, `time`, `Decimal` and `UUID`."""
    return json.dumps(value, default=default, **kwargs)
