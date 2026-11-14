# Dependency Injection

A handler declares what it needs in its signature, and Ushka passes it in.
There is nothing to register and no container to configure.

## What you can ask for

| Parameter | Matched by | You get |
| --- | --- | --- |
| `request` | name `request` or annotation `Request` | The current request. |
| `response` | name `response` or annotation `Response` | A fresh, empty `Response` to fill and return. |
| `config` | name `config` or annotation `Config` | The application [configuration](configuration.md). |
| path parameters | the name in brackets, e.g. `item_id` for `[item_id]` | The value from the URL, as an `Untrusted` string. |

Parameters can come in any order, and you only list the ones you use. A
handler with no parameters is fine too.

```python
# routes/hello.py
from ushka import Config, Request, Response


async def get(request: Request, response: Response, config: Config):
    name = request.query.get("name", "guest")

    response.body = f"Hello, {name}! Welcome to {config.APP_NAME}."
    response.headers["X-Greeting"] = "hello"
    return response
```

`GET /hello?name=Ada` answers `Hello, Ada! Welcome to Ushka App.` as
`text/plain`. Untrusted text served as plain text is fine; the same string
served as HTML would be refused ([USHKA-G001](guard.md#ushka-g001)).

The annotations are optional. This is equivalent:

```python
async def get(request, response, config):
    ...
```

And since a matching *annotation* is enough, you can also use other names:

```python
async def get(req: Request, cfg: Config):
    return {"path": req.path, "debug": cfg.APP_DEBUG}
```

## Path parameters

Path parameters are matched by name, so the parameter must be spelled like the
bracket in the file name:

```python
# routes/users/[user_id]/posts/[post_id].py
from ushka.guard import safe


async def get(request, user_id, post_id):
    return {
        "user": safe.integer(user_id, min=1),
        "post": safe.integer(post_id, min=1),
        "fields": request.query.get("fields", "all"),
    }
```

Values are always strings; annotations such as `user_id: int` do **not**
convert them. Use `safe.integer()` and the other
[sanitisers](guard.md#sanitisers-the-way-out).

!!! note
    The names `request`, `response` and `config` are reserved for the injected
    objects. Avoid them as path parameter names.

## The injected `Response`

The injected `response` is a new `Response()` (status 200, empty body). Only
what you **return** is sent, so return it after filling it in:

```python
async def get(request, response):
    response.status_code = 202
    response.body = {"queued": True}     # dict and list bodies become JSON
    response.headers["Retry-After"] = "30"
    return response
```

Cookies and the session are saved automatically on whatever response you
return; set them through the request:

```python
async def post(request):
    request.cookies.set("theme", "dark", max_age=3600)
    request.session["visits"] = request.session.get("visits", 0) + 1
    return {"ok": True}
```
