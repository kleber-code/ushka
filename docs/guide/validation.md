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

## HTML forms

A browser form sends `application/x-www-form-urlencoded` or `multipart/form-data`,
not JSON. Mark the dataclass with `Form()` and the whole object is filled from
the form, with the **same** types, `Field` limits, body-size limits and
no-mass-assignment rule as a JSON body:

```python
# routes/lead.py
from dataclasses import dataclass, field
from datetime import date
from typing import Annotated, Optional
from ushka import Field, Form, RequestValidationError, Response, render, on_invalid

@dataclass
class Lead:
    name: Annotated[str, Field(min_length=2, max_length=80)]
    email: str
    age: Optional[int] = None
    newsletter: bool = False                    # a checkbox
    interests: list[str] = field(default_factory=list)   # <input name="interests"> repeated
    born: Optional[date] = None

async def show(request, errors: RequestValidationError):
    html = await render(request, "lead.html", {"errors": errors.fields, "values": errors.values})
    return Response(html, status_code=422)

@on_invalid(show)
async def post(lead: Annotated[Lead, Form()]):
    ...
    return redirect("/thanks")
```

(With decorators: `@app.post("/lead", on_invalid=show)`.)

How a form differs from JSON, and what Ushka does about it:

| The browser sends | You get |
| --- | --- |
| nothing for an unchecked checkbox | a `bool` field is `False` |
| nothing for a group of unchecked boxes | a `list` field is `[]` |
| `a=1&a=2` | `["1", "2"]` (one value is a list of one) |
| `""` from an empty number or date input | "not filled in": the default, `None` for `Optional`, else `Field required` |
| a field you did not declare (`is_admin=1`) | dropped: never reaches the object |
| a file in `multipart/form-data` | a `dict` field gets `filename`, `content_type` and the file object |

`str` fields stay `Untrusted`, like a JSON string. Only flat models are
supported in forms (no nested dataclass).

### Draw the form again with the errors

Without `on_invalid`, a bad form answers the JSON **422** above (without
echoing the input), which is right for an API client. With it, your function
runs instead. It is an ordinary handler: it can take `request`, `Depends(...)`
and `errors: RequestValidationError`, and it returns whatever you like. Set
the status yourself (`Response(html, status_code=422)`, or return `(html, 422)`).

- `errors.fields` is `{"email": ["Field required"], ...}`: the messages for each field.
- `errors.values` is what the visitor typed. These are client strings (`Untrusted`):
  put them in a template and the autoescape handles them.
- `errors.errors` is the full list with locations, as in the JSON answer.

```html
<!-- templates/lead.html -->
<input name="email" value="{{ values.email }}">
{% for message in errors.email %}<p class="error">{{ message }}</p>{% endfor %}
```

The error messages never contain the client's input, so it is safe to show
them. If the handler itself fails validation (a missing `Depends`), that error
is answered as usual.

!!! warning
    Do not mark `errors.values` with `|safe` or build HTML from it by hand:
    Ushka Guard refuses an `Untrusted` value there for a reason.

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

## OpenAPI

The same signatures describe your API. It is off until you ask, because the
document is a map of your routes:

```python
app.enable_openapi()                    # GET /openapi.json
doc = app.openapi(title="Shop", version="1.0")   # or get the dict
```

Paths, parameters (including those of `Depends`), request bodies, enums and
limits come from the annotations, so the document matches what the app
really validates. Paste `/openapi.json` into any OpenAPI viewer or client
generator. Ushka does not bundle a browser UI: that would mean shipping
third-party scripts that the default [CSP](security.md) blocks.
