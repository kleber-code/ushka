# Routing

In Ushka your folder structure *is* the URL map. Drop a Python file into
`routes/`, define a function named after an HTTP verb, and the route is live.

## Filesystem routes

| File | URL |
| --- | --- |
| `routes/index.py` | `/` |
| `routes/about.py` | `/about` |
| `routes/users/index.py` | `/users` |
| `routes/blog/posts.py` | `/blog/posts` |
| `routes/users/[username].py` | `/users/<username>` |

Inside a route file, functions named `get`, `post`, `put`, `patch`, `delete`,
`head` or `options` become handlers for that verb. Handlers can be `async def`
or plain `def`.

```python
# routes/index.py
async def get():
    return {"message": "Welcome to the home page!"}


async def post(request):
    data = await request.json()
    return {"received": data}, 201
```

A few rules worth knowing:

* Only functions **defined in the route file** count. `from helpers import get`
  does not silently become a route.
* Files whose name starts with `__` (such as `__init__.py`) are skipped.
* A route file that fails to import is logged and skipped; the rest of the app
  still starts.
* Discovery runs when `Ushka()` is created. Set `[app] auto_discover = false`
  in `ushka.toml` to turn it off.

You can create, move and delete route files from the terminal with
[`ushka routes`](cli.md#ushka-routes).

## Dynamic segments

Square brackets in a file or folder name capture part of the URL. The value is
passed to the handler as a keyword argument with the same name.

```python
# routes/users/[username].py
async def get(username):
    return {"profile": username}
```

`GET /users/charlie` returns `{"profile": "charlie"}`.

| Segment | Matches |
| --- | --- |
| `[name]` | One path segment (anything except `/`). |
| `[int:name]` | Digits only. `/items/abc` does not match (404). |
| `[path:name]` | The rest of the path, slashes included: `routes/docs/[path:page].py` matches `/docs/a/b/c`. |

Folders can be dynamic too: `routes/users/[user_id]/posts.py` serves
`/users/42/posts`.

### Path parameters are strings, and untrusted

Ushka does **not** convert path parameters based on type annotations. Even
`[int:item_id]` hands you the string `"42"`, and like every value from the
client it is an `Untrusted` string ([Ushka Guard](guard.md)). Convert and
validate it with a sanitiser:

```python
# routes/items/[int:item_id].py
from ushka.guard import safe


async def get(item_id):
    item_id = safe.integer(item_id, min=1)  # int; a rejected value answers 400
    return {"id": item_id, "next": item_id + 1}
```

### Priority

Static routes always win over dynamic ones: with both `routes/users/me.py` and
`routes/users/[username].py`, `/users/me` goes to `me.py`.

## Decorator routes

For small apps or scripts, register handlers on the app object instead. Paths
use the same bracket syntax.

```python
# app.py
from ushka import Ushka

app = Ushka()


@app.get("/")
async def home():
    return "Hello, Ushka!"


@app.get("/users/[user_id]")
async def user(user_id):
    return {"user_id": user_id}


@app.post("/echo")
async def echo(request):
    return await request.json()


if __name__ == "__main__":
    app.run()
```

Available decorators: `@app.get`, `@app.post`, `@app.put`, `@app.patch` and
`@app.delete`. For any other verb call the router directly:
`app.router.add_route("OPTIONS", "/echo", handler)`.

Decorator routes and filesystem routes can live in the same app. Registering
the same method and path twice keeps the last one and logs a warning.

!!! note
    Route files are compiled with a rewrite that keeps the `Untrusted` mark
    through f-strings, `.format()`, `%` and `.join()`. Handlers defined in your
    own modules (like `app.py` above) are not rewritten unless you opt in; see
    [What it does not cover](guard.md#what-it-does-not-cover).

## What a handler can receive

Handlers declare what they need and Ushka passes it in:

* `request`: the current [`Request`](#the-request).
* `response`: a fresh `Response` you can fill and return.
* `config`: the application [configuration](configuration.md).
* Path parameters, by name.

Details in [Dependency Injection](dependency_injection.md).

## The request

| Attribute | What it is |
| --- | --- |
| `request.method`, `request.path` | `"GET"`, `"/users/42"`. |
| `request.query` | Query string as a `dict`. A repeated key (`?tag=a&tag=b`) gives a list. |
| `request.headers` | Headers as a `dict` with **lower-case** names: `request.headers["user-agent"]`. |
| `request.cookies` | Cookies; also used to set them (`request.cookies.set(...)`). |
| `request.session` | Signed cookie session (`dict`). Needs a [secret key](configuration.md#the-secret-key). |
| `await request.body()` | Raw body (`bytes`). |
| `await request.text()` | Body decoded as UTF-8. |
| `await request.json()` | Parsed JSON. |
| `await request.form()` | URL-encoded or multipart form fields. |
| `await request.files()` | Uploaded files: `{"field": {"filename", "content_type", "file"}}`. |
| `request.stream()` | Async iterator over body chunks, for large uploads. |

Invalid JSON, invalid UTF-8 or a malformed form answers **400 Bad Request**; a
body larger than the [`[limits]`](configuration.md#all-settings) answers
**413 Payload Too Large**. You do not need to catch those yourself.

## Return values

Return whatever is most natural; Ushka turns it into a response.

| You return | Response |
| --- | --- |
| `dict`, `list`, `bool`, `float` | JSON (`application/json`). |
| `str` | `text/plain`, or `text/html` when it contains `<html` or `<!DOCTYPE html>`. |
| `bytes` | The bytes as they are. |
| `int` | The number as text. |
| `None` | `204 No Content`. |
| A t-string (Python 3.14+) | HTML with every value escaped. |
| `(body, status)` or `(body, status, headers)` | That body with that status code (and headers). |
| `Response(...)` | Used as is. |

Anything else raises a `TypeError` explaining what is allowed. Text and JSON
get `; charset=utf-8` in their `content-type`.

```python
# routes/items/index.py
async def post(request):
    data = await request.json()
    if not data.get("name"):
        return {"error": "name is required"}, 400
    return {"created": data["name"]}, 201, {"Location": "/items/1"}
```

!!! warning "HTML built from request data is refused"
    A string served as HTML that contains an `Untrusted` value raises
    [USHKA-G001](guard.md#ushka-g001). Render a [template](templates.md), return
    a t-string on Python 3.14+, or escape the value with `safe.html()`. As
    `text/plain` or JSON the same value is fine.

### Building a `Response` yourself

```python
from ushka.http import Response


async def get():
    return Response(
        "id,name\n1,Ada\n",
        status_code=200,
        headers={"Content-Disposition": "attachment; filename=users.csv"},
        media_type="text/csv",
    )
```

For redirects use `redirect()`, and validate any target that came from the
client ([USHKA-G003](guard.md#ushka-g003)):

```python
# routes/login.py
from ushka.guard import safe
from ushka.http import redirect


async def post(request):
    form = await request.form()
    # ... check the credentials ...
    return redirect(safe.url(form.get("next"), allow=["/"], default="/"))
```

`redirect(to, status_code=302)` also accepts 301, 303, 307 and 308.

## HEAD, 405 and WebSockets

* `HEAD` requests are answered by the `GET` handler, without a body.
* A path that exists but not for the requested method answers
  **405 Method Not Allowed** with an `Allow` header (it lists `HEAD` whenever
  `GET` exists).
* WebSockets are not supported yet; the handshake is closed.

## Startup and shutdown hooks

```python
# app.py
from ushka import Ushka

app = Ushka()


@app.on_startup
async def open_pools():
    print("starting")


@app.on_shutdown
def close_pools():
    print("stopping")
```

Hooks can be sync or async. If a startup hook raises, the server refuses to
start and logs the error. Shutdown hooks run in reverse order, and a failing
one does not stop the others.

## Running the app

* `ushka dev`: development server with reload and debug on. See [CLI](cli.md).
* `ushka run`: production server.
* `python app.py` with `app.run()`: uses `[server] host` and `port`, or the
  arguments you pass: `app.run(host="0.0.0.0", port=5000)`.

`app` is a standard ASGI application, so any ASGI server works too:
`uvicorn app:app`.
