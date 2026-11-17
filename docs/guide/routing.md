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
`head` or `options` become handlers for that verb, and a function named
`websocket` handles [WebSockets](realtime.md). Handlers can be `async def` or
plain `def`.

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

### Typed path parameters

Annotate the parameter and Ushka converts and validates it. A value that does not
fit answers **422** and your handler never runs:

```python
# routes/items/[item_id].py
from typing import Annotated
from ushka import Path

async def get(item_id: Annotated[int, Path(ge=1)]):
    return {"id": item_id, "next": item_id + 1}     # item_id is a real int
```

Without an annotation the value is a `str`, and, like everything from the client,
an [`Untrusted`](guard.md) one. Convert it with an annotation, or with a sanitiser
such as `safe.integer(item_id, min=1)` (a rejected value answers 400). More in
[Validation and typed parameters](validation.md).

### Priority

Static routes always win over dynamic ones: with both `routes/users/me.py` and
`routes/users/[username].py`, `/users/me` goes to `me.py`.

## Routes per host

One app can answer several host names with different routes (a dashboard, an admin, an API):

```toml
[routes]
hosts = { "dashboard.example.com" = "routes_dashboard", "api.*" = "routes_api" }
```

Each value is a folder of route files, loaded like `routes/` (a list of folders also works). A request for that host is answered by those routes alone, and every other host by `routes/`. A folder listed here is never part of the default routes, even when it sits inside `routes/`. Hosts are globs (`*.example.com`) and a port is ignored. `[static]` files are served on every host.

The same from code:

```python
@app.host("api.*").get("/status")
async def status():
    return {"ok": True}
```

The host is `request.host`: `X-Forwarded-Host` counts only when the direct peer is in `[security] trusted_proxies`, otherwise the `Host` header. Combine with `allowed_hosts` in `[security]` so only your own names reach the app.

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
async def user(user_id: int):
    return {"user_id": user_id}


@app.post("/echo")
async def echo(request):
    return await request.json()


@app.websocket("/ws")
async def socket(ws):
    await ws.accept()


if __name__ == "__main__":
    app.run()
```

Available decorators: `@app.get`, `@app.post`, `@app.put`, `@app.patch`,
`@app.delete` and `@app.websocket`. For any other verb call the router directly:
`app.router.add_route("OPTIONS", "/echo", handler)`.

Decorator routes and filesystem routes can live in the same app. Registering
the same method and path twice keeps the last one and logs a warning.
`app.router.iter_routes()` lists everything registered.

!!! note
    Route files are compiled with a rewrite that keeps the `Untrusted` mark
    through f-strings, `.format()`, `%` and `.join()`. Handlers defined in your
    own modules (like `app.py` above) are not rewritten unless you opt in; see
    [What it does not cover](guard.md#what-it-does-not-cover).

## What goes in a handler

A handler asks for what it needs by name and type: `request`, `response`,
`config`, path, query, header, cookie and body parameters, and `Depends(...)`.
It returns a `dict`, a `str`, a `(body, status)` tuple or a `Response`. Both sides
have their own page: [Requests and responses](requests-responses.md),
[Validation and typed parameters](validation.md) and
[Dependency Injection](dependency_injection.md).

## HEAD, 405 and WebSockets

* `HEAD` requests are answered by the `GET` handler, without a body.
* A path that exists but not for the requested method answers
  **405 Method Not Allowed** with an `Allow` header (it lists `HEAD` whenever
  `GET` exists).
* WebSocket handlers are routed like any other: see
  [WebSockets and Server-Sent Events](realtime.md).

## Middleware

`@app.middleware` wraps every request, inside the [security middleware](security.md#your-own-middleware).

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
one does not stop the others. With several [workers](deploy.md#workers), each
worker runs its own hooks.

## Running the app

* `ushka dev`: development server with reload and debug on. See [CLI](cli.md).
* `ushka run`: production server. See [Deploy](deploy.md).
* `python app.py` with `app.run()`: uses `[server] host` and `port`, or the
  arguments you pass: `app.run(host="0.0.0.0", port=5000)`.

`app` is a standard ASGI application, so any ASGI server works too:
`uvicorn app:app`.
