# Ushka Guard on FastAPI, Starlette and Django

[Ushka Guard](guard.md) does not need the rest of Ushka. The same protection works
in an app you already have: what clients send becomes `Untrusted`, and the
places where it could do harm refuse it with an error that says how to fix it.

```console
$ pip install ushka
```

## FastAPI

```python
from fastapi import FastAPI
from ushka.guard.integrations import fastapi as guard

guard.install(rewrite_packages=["myapp"])   # once, at startup

app = FastAPI()

@app.get("/hello", response_class=HTMLResponse)
def hello(name: str):
    return HTMLResponse(f"<h1>Hello {name}</h1>")   # refused: USHKA-G001
```

FastAPI validates parameters with pydantic, which returns a plain `str`.
The guard therefore marks the values FastAPI took from the request (path, query,
header, cookie and body parameters, also inside pydantic models and in
`Depends` functions) right before your code runs. Only an exact `str` is marked:
`int`, `UUID`, `Enum` and `Literal` parameters are already validated and stay as
they are.

## Starlette

```python
from ushka.guard.integrations import starlette as guard

guard.install(rewrite_packages=["myapp"])
```

`request.query_params`, `.headers`, `.cookies`, `.path_params`,
`await request.json()` and `await request.form()` return `Untrusted` strings.
`HTMLResponse`, `RedirectResponse` and `FileResponse` refuse them.

## Django

```python
# settings.py
MIDDLEWARE = ["ushka.guard.integrations.django.GuardMiddleware", ...]
```

```python
# apps.py, in ready()
from ushka.guard.integrations import django as guard
guard.install(rewrite_packages=["myproject"])
```

`request.GET`, `request.POST`, `request.COOKIES`, `request.headers`, the URL
arguments of your view and `request.json()` (added by the middleware) are
`Untrusted`. `HttpResponse` with HTML, every `HttpResponseRedirect` (so
`redirect()` too) and `mark_safe` (what the `|safe` filter calls) refuse them.

## The way out is the same everywhere

```python
from ushka.guard import safe

HTMLResponse(f"<h1>{safe.html(name)}</h1>")
RedirectResponse(safe.url(next_url, allow=["/"], default="/"))
```

For raw SQL call `ushka.guard.check_sql(query)` before executing, or use
parameters. See [Ushka Guard](guard.md#sanitisers-the-way-out).

## What you need to know

- **`rewrite_packages` matters.** `f"<p>{name}</p>"` is a plain `str` in normal Python: the mark is lost, and the guard cannot see it. Listing your packages recompiles them on import so the mark survives f-strings, `.format`, `%` and `.join` ([details](guard.md)). Without it only values that reach a sink directly are caught.
- **It patches the framework's classes for the whole process**, because that is the only way to cover code that does not know about Ushka. `uninstall()` restores them. Call `install()` once at startup, before requests arrive.
- **What is not marked:** raw bytes (`request.body`, `request.stream()`), and URLs and paths read directly (`request.url`, Django's `request.path`). Use the parameters, or `taint(value, "source")` on what you read.
- **FastAPI relies on one internal function.** If a FastAPI release changes it, `install()` raises an error instead of quietly protecting nothing.
- **A refusal is an exception.** In production a visitor gets a 500, as in Ushka. Run [`ushka verify`](verify.md) in Ushka, or your tests, to find those places and write the fix.

The package is the one you installed: it is `ushka.guard`, which imports nothing else from Ushka, and the three integrations need no extra dependency.
