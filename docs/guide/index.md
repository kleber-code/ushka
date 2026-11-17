# Introduction

Ushka is the web framework where insecure code, whether you or an AI wrote it,
does not run silently. It is small in concept (a file in `routes/` is a URL,
a function named `get` answers GET), light on dependencies, and comes with the
batteries a web app needs: validation, templates, sessions, static files, an
async ORM, real-time, a security middleware and a CLI.

## The idea in one example

Everything that comes from the client arrives as an `Untrusted` string. It
behaves like a normal `str`, but the places where it could do harm refuse it:

```python
# routes/login.py
from ushka import redirect, safe

async def get(request):
    target = request.query.get("next", "/")      # Untrusted
    # return redirect(target)                    # refused: USHKA-G003, with the fix
    return redirect(safe.url(target, allow=["/"], default="/"))
```

| Sink | Error |
| --- | --- |
| HTML response body | [USHKA-G001](guard.md#ushka-g001) |
| The `safe` filter in a template | [USHKA-G002](guard.md#ushka-g002) |
| `redirect()` target | [USHKA-G003](guard.md#ushka-g003) |
| File-system path | [USHKA-G004](guard.md#ushka-g004) |
| Raw SQL string | [USHKA-G005](guard.md#ushka-g005) |

The way out is a sanitiser from `ushka.guard.safe`, or a type annotation that
validates. Read [Ushka Guard](guard.md) for the full story.

## Start here

1. [Installation](install.md): `pip install ushka`, extras and the install script.
2. [Quickstart](quickstart.md): a running app in five minutes.
3. [Project structure](project-structure.md): what `ushka new` creates and why.

## Build your app

- **Routes and data in:** [Routing](routing.md), [Requests and responses](requests-responses.md),
  [Validation and typed parameters](validation.md) and [Dependency Injection](dependency_injection.md).
- **Pages and files:** [Templates](templates.md), [Static files](static_files.md),
  [Sessions, cookies and uploads](sessions.md) and [Flash messages](flashing.md).
- **Data:** the async [ORM](orm.md) and migrations.
- **Real time and agents:** [WebSockets and Server-Sent Events](realtime.md) and
  [Routes as agent tools (MCP)](agents.md).
- **Errors:** [Error handling](error_handling.md).

## Keep it secure

- [Ushka Guard](guard.md): sources, sinks, sanitisers and the error codes.
- [Security middleware](security.md): CSRF, headers, CORS and trusted hosts, on by default.
- [`ushka verify`](verify.md): attack your own routes and see what got through.
- [Guard on FastAPI, Starlette and Django](guard-frameworks.md): the same protection in an app you already have.

## Ship it

- [Configuration](configuration.md): `ushka.toml`, `.env`, environment variables.
- [Deploy](deploy.md): checklist, Docker, workers, health checks, proxies.
- [Performance](performance.md): what is fast by default, and how to measure.
- [Ushka Docs](docs.md): turn a folder of Markdown into a docs site, like this one.

## Reference

- [CLI](cli.md): `new`, `dev`, `run`, `check`, `verify`, `docs`, `routes`, `db`.
- [Configuration settings](configuration.md#all-settings) and [error codes](guard.md#sinks-what-refuses-untrusted-data).
- The API reference, generated from the docstrings, is in the navigation.

Prefer to learn by building? Try the [Simple API tutorial](tutorial_simple_api.md).
