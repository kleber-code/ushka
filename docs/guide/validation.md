# Validation and typed parameters

Declare what a handler needs, with types. Ushka reads it from the request,
converts it, and answers **422** with every problem at once when it does not
fit. It uses only the standard library: no pydantic.

```python
# routes/items/[item_id].py
from typing import Annotated
from ushka import Depends, Header, Query

async def get(item_id: int, page: Annotated[int, Query(ge=1)] = 1, user_agent: str = Header("")):
    return {"item": item_id, "page": page}
```

`GET /items/abc` answers:

```json
{"detail": [{"loc": ["path", "item_id"], "msg": "Input should be a valid integer", "type": "int_parsing"}]}
```

The client's input is never echoed back in the error.

## Where a parameter comes from

| You write | Source |
| --- | --- |
| a name that is in the route, `[item_id]` | the path |
| `limit: int = 10` (a plain scalar) | the query string |
| `item: Item` (a dataclass, `TypedDict`, `dict` or `list`) on `POST`, `PUT`, `PATCH`, `DELETE` | the JSON body |
| `Query()`, `Header()`, `Cookie()`, `Path()`, `Body()`, `Form()` | exactly that |
| `Depends(fn)` | the result of `fn` |

`request`, `response` and `config` work as before. A `Header` named
`user_agent` reads `user-agent`; set `alias=` to read another name. A default
makes a parameter optional, and `Optional[...]` without a default means `None`.

## Types

`str`, `int`, `float`, `bool`, `Decimal`, `UUID`, `date`, `datetime`, `time`,
`Enum`, `Literal`, `Optional` and unions, `list`, `set`, `tuple`, `dict`,
dataclasses and `TypedDict` (nested). Limits go in `Field` or in any marker:
`gt ge lt le min_length max_length pattern`.

```python
from dataclasses import dataclass, field
from typing import Annotated
from ushka import Field

@dataclass
class Item:
    name: Annotated[str, Field(min_length=2, max_length=80)]
    price: float
    tags: list[str] = field(default_factory=list)

async def post(item: Item):
    return {"created": str(item.name)}
```

Only the fields you declare reach the handler, so a client cannot set
`is_admin` by adding it to the JSON (no mass assignment).

## Validation is also sanitising

This is how it fits with [Ushka Guard](guard.md):

- A parameter declared `int`, `float`, `bool`, `UUID`, a date or an `Enum` comes out as a **plain value**: it can no longer carry markup or SQL.
- A `Literal["asc", "desc"]` returns *your constant*, never the client's string, so it is safe to place in SQL.
- A `str` stays `Untrusted`. Its content is still the client's, so the guarded sinks keep refusing it.

## Depends

```python
from ushka import Depends, Header
from ushka.http.exceptions import HTTPForbidden

async def current_user(token: str = Header(""), db=Depends(get_db)):
    user = await db.find_by_token(token)
    if user is None:
        raise HTTPForbidden(message="Invalid token")
    return user

async def get(user=Depends(current_user)):
    return {"hello": user.name}
```

- A dependency may be sync or async, and may declare its own parameters and `Depends`.
- It runs **once per request**, even when several parameters need it (`Depends(fn, use_cache=False)` to call it each time).
- A `yield` dependency cleans up after the handler returns, also when the handler raises:

```python
async def get_db():
    db = await connect()
    try:
        yield db
    finally:
        await db.close()
```

- A dependency that takes `response: Response` shares the handler's response, so it can set headers and cookies.
- In tests, swap one: `app.dependency_overrides[get_db] = fake_db`.

!!! note
    Cleanup runs when the handler returns, before the body is sent.
    Do not hand a dependency's resource to a streaming response.
