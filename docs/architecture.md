# Architecture

How the code is laid out, what it depends on, how a request runs, and how fast
it is. The numbers and rules below were measured on the source, and the rules
are enforced by `tests/test_architecture.py` and `tests/test_supply_chain.py`.

## Code tree

About 13,800 lines in 71 modules (Python 3.10 to 3.14). The folders follow who
uses the code: the core everything depends on, what browsers and search engines
see, what machines consume, and tooling.

```text
src/ushka/
│  the core: what every app uses
├── guard/            taint core: Untrusted, sinks, sanitisers, rewrite      1,414 lines
│   └── integrations/ FastAPI, Starlette, Django adapters (framework imported lazily)
├── core/             app (ASGI entry, middleware chain), router, config      2,341
│                     and its settings schema, error handler, logging, the
│                     production server (`ushka run`)
├── http/             request, response, streaming/SSE, WebSocket, params     2,576
│                     (Depends), validation and forms, cookies, multipart
├── security/         security middleware (CSRF, headers, CORS, hosts) and      639
│                     `ushka verify`, the hostile probes against your own app
├── sessions/         signed-cookie sessions and revocable server-side          804
│                     sessions (database store)
├── crypto/           Fernet encrypt/decrypt, key rotation (needs ushka[crypto];     226
│                     `cryptography` is imported on first use, never at import)
├── templating/       Jinja2 engine with the guarded |safe, flash messages      365
├── static/           static files with ETag and 304                            110
│  what browsers and search engines see (each has its own [section])
├── web/              seo (meta tags, robots.txt, sitemap.xml), pwa            1,265
│                     (manifest, service worker), i18n (gettext catalogs)
│  what an app reads
├── mail/             imap (`ImapClient`: IMAP over TLS, safe search,           930
│                     Untrusted messages and attachments; loaded on import)
│  what machines consume
├── api/              openapi (OpenAPI 3.1 from signatures), mcp (routes as     596
│                     tools for AI agents)
│  batteries and tooling
├── orm/              async Active Record on SQLAlchemy (extra)               1,015
├── docs/             Ushka Docs: Markdown site generator (extra)             1,023
├── cli/              new, dev, run, check, config, verify, docs, routes,     1,336
│                     db, i18n
└── testing.py        `TestClient`: in-process ASGI client with lifespan and cookies
site/                 ushka.satela.com.br, served by Ushka itself
benchmarks/           reproducible load test
```

The top-level `ushka` package exports what an app needs (`Ushka`, `Request`,
`Response`, `render`, `Depends`, `Form`, `safe`, `_`...). Anything else is
imported from its folder: `ushka.sessions`, `ushka.web.seo`, `ushka.api.openapi`.

## Dependencies

| Part | Third-party packages |
| --- | --- |
| Core (`pip install ushka`) | `uvicorn`, `uvloop` (not on Windows or PyPy), `httptools`, `jinja2` (brings `markupsafe`), `python-multipart`, `tomli` on 3.10 |
| `ushka[orm]` | `sqlalchemy`, `alembic`, `aiosqlite` |
| `ushka[docs]` | `markdown-it-py`, `mdit-py-plugins`, `pygments`, `griffe` |
| `ushka.guard.integrations` | the framework you already use, imported only when you call `install()` |

A core install is 9 packages and 20 MB: the two compiled accelerators, `uvloop` and `httptools`, are most
of the size and about 2.3x the requests per second (FastAPI with uvicorn and no accelerators: 14 packages and
12 MB). `import ushka` takes about 95 ms. Rules enforced by tests:

- No import cycles between modules at runtime.
- The guard core imports nothing else from Ushka, so it can ship alone.
- The core uses only the packages in the first row.
- Importing `ushka` does not import `uvicorn` (it is about half the import time).

## The production server

`ushka run` does not call `uvicorn.run`. It starts `ushka.core.server`, which is
Uvicorn with two changes, so an idle app costs close to nothing:

- `QuietServer` wakes a worker once a second instead of ten times;
- `Supervisor` (for `workers > 1`) sleeps until a worker dies, a signal arrives or
  the next health check, every 10 seconds, instead of pinging twice a second. A new
  worker is exempt from pings for 90 seconds, so a slow import is not mistaken for a hang.

Only `ushka run` imports this module, so `import ushka` stays free of Uvicorn.
`ushka dev` keeps stock Uvicorn for reload. See [Performance](guide/performance.md)
and [Deploy](guide/deploy.md).

## How a request runs

```text
uvicorn ──► Ushka.__call__ (ASGI) ── http ──► Request(app, scope, receive)
                                    └ websocket ► WebSocket handshake: Origin/host check, then handler
Request
  └► SecurityMiddleware        trusted host, CORS preflight, CSRF, then (after) headers
       └► your middleware      app.add_middleware, in order
            └► _dispatch_safely    errors become Responses here, so every layer sees a Response
                 └► Router.get_route      static dict, then compiled regexes
                      └► Resolver         path/query/header/cookie/body typed and validated, Depends
                           └► your handler
                                └► _to_response ─► Response ─► send  (Content-Length, cookies, session)
```

Client data is `Untrusted` from the moment it is read. A guarded sink (HTML
body, redirect, file path, SQL, `|safe`) refuses it unless a sanitiser or a
validated type produced the value.

## Benchmark

On one laptop with a single worker, Ushka with every protection on does 28% more
requests per second than FastAPI on the hello route and the typed route, and is
behind bare Starlette, which validates and protects nothing. The table, the method
and how to reproduce it are in [Performance](guide/performance.md#benchmark).

## Verification done on this code

| Check | Result |
| --- | --- |
| Test suite | 343 pass on 3.13; 333 on 3.10 and 336 on 3.14 |
| `ushka verify` on the website app | 13 routes, 36 hostile requests, nothing got through |
| `pip-audit` on installed dependencies | no known vulnerabilities |
| Real servers | SSE, WebSocket and MCP exercised over real uvicorn |
| Lint (`ruff`) on the new code | clean |

## Known gaps

- `core` and `http` import each other at package level (no module cycle, but the layering is murky). Splitting `core` into leaf modules (config, exceptions, log) and orchestration (app, router) would fix it.
- `markupsafe` is imported by the guard but only declared through `jinja2`: declare it before shipping the guard alone.
- The older code has about 190 `ruff` findings that predate this work.
- `pdm.lock` pins `python-multipart` 0.0.32 (the last that supports 3.10); 3.11+ resolves 0.0.33 outside CI.
- The release workflow was not run end to end: it will first run on the next published release.
- Benchmarks are a laptop and a hello-world; they say nothing about your database-bound app.
