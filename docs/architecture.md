# Architecture

How the code is laid out, what it depends on, how a request runs, and how fast
it is. The numbers and rules below were measured on the source, and the rules
are enforced by `tests/test_architecture.py` and `tests/test_supply_chain.py`.

## Code tree

About 8,200 lines in 60 modules (Python 3.10 to 3.14).

```text
src/ushka/
├── guard/            taint core: Untrusted, sinks, sanitisers, rewrite      1,063 lines
│   └── integrations/ FastAPI, Starlette, Django adapters (framework imported lazily)
├── core/             app (ASGI entry, middleware chain), router, config,    1,525
│                     error handler, logging
├── http/             request, response, streaming/SSE, WebSocket,           2,134
│                     params (Depends), validation, cookies, sessions, multipart
├── security/         security middleware: CSRF, headers, CORS, hosts          155
├── templating/       Jinja2 engine with the guarded |safe                      164
├── static/ utils/    static files, flash messages                              182
├── orm/              async Active Record on SQLAlchemy (extra)                 661
├── docs/             Ushka Docs: Markdown site generator (extra)               598
├── cli/              new, dev, run, check, verify, docs, routes, db            810
├── openapi.py        OpenAPI 3.1 from handler signatures                       177
├── mcp.py            routes as MCP tools, capabilities, approval               318
└── verify.py         `ushka verify`: hostile probes against your own app       378
site/                 ushka.satela.com.br, served by Ushka itself
benchmarks/           reproducible load test
```

## Dependencies

| Part | Third-party packages |
| --- | --- |
| Core (`pip install ushka`) | `uvicorn`, `jinja2` (brings `markupsafe`), `python-multipart`, `tomli` on 3.10 |
| `ushka[orm]` | `sqlalchemy`, `alembic`, `aiosqlite` |
| `ushka[docs]` | `markdown-it-py`, `mdit-py-plugins`, `pygments`, `griffe` |
| `ushka.guard.integrations` | the framework you already use, imported only when you call `install()` |

A core install is 7 packages and 3 MB (FastAPI with uvicorn: 14 packages and
12 MB). `import ushka` takes about 95 ms. Rules enforced by tests:

- No import cycles between modules at runtime.
- The guard core imports nothing else from Ushka, so it can ship alone.
- The core uses only the packages in the first row.
- Importing `ushka` does not import `uvicorn` (it is about half the import time).

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

Single uvicorn worker, one laptop (12th Gen i5-1235U), Python 3.13, 128
keep-alive connections, median of 3 rounds, zero errors. Requests per second:

| | hello | typed route | POST + body validation | memory |
| --- | ---: | ---: | ---: | ---: |
| Starlette (no validation) | 9,207 | 8,970 | 6,775 | 31 MB |
| Ushka, security off | 8,335 | 7,376 | 6,305 | 33 MB |
| **Ushka, defaults** | **7,902** | **6,531** | **5,258** | **33 MB** |
| FastAPI | 6,165 | 5,085 | 4,921 | 47 MB |

With every protection on, Ushka does 28% more than FastAPI on the hello route,
28% on the typed route and 7% on the validated POST, and the whole default
security middleware costs about 5% on the hello route and up to 17% on the validated POST. It is behind bare Starlette, which
validates and protects nothing. Variation between rounds was up to 35%
(Ushka POST ranged 3,982 to 5,364), so treat differences under 10% as noise.
See `benchmarks/` to reproduce.

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
