# AGENTS.md — working on the Ushka framework itself

## Principles

- **Secure by default is tested.** Workflows pin actions to SHAs, and `tests/test_supply_chain.py` and
  `tests/test_architecture.py` fail the build when that erodes.

- **Low dependency.** The core depends on `uvicorn`, `jinja2`, `python-multipart`
  (and `tomli` on 3.10). Do not add runtime dependencies; implement small things
  with the standard library. Security-critical parsers are the exception.
- **Batteries included.** Features a typical web app needs belong in the box.
- **Lightweight in concept.** One clear idea per feature; no hidden magic.
- **Flask and Mako, not Django.** Syntax stays explicit and Pythonic: decorators, plain functions, Jinja2 in
  templates, SQLAlchemy-style attributes (`__tablename__`). Avoid Django idioms (nested `class Meta`, managers, tag
  libraries, one big settings module) in new APIs.
- **Nothing hidden.** A new setting is added to `SCHEMA` in `src/ushka/core/settings.py` (default and description) and
  nowhere else: `ushka new`, `ushka config` and the table in `docs/guide/configuration.md` are generated from it
  (run `ushka config --markdown` and paste it between the markers). `tests/test_settings.py` fails when code reads
  an undeclared setting or the docs drift.
- **Secure by default.** New sinks must call a `ushka.guard.check_*` function;
  new request data sources must be wrapped in `Untrusted`.

## Layout

- `src/ushka/guard/` — taint core. Must not import anything else from `ushka`
  (enforced by `tests/test_guard.py` and `tests/test_architecture.py`), so it can ship standalone.
  `guard/integrations/` adapts it to Starlette, FastAPI and Django (framework imported lazily).
- `src/ushka/core/` — app, router, config, `settings.py` (the schema of every setting), error handler,
  logging and `server.py` (the production server).
- `src/ushka/http/` — request, response, streaming/SSE, WebSocket, cookies, multipart, redirect,
  `params.py` (typed parameters, `Depends`, forms) and `validation.py` (stdlib-only validation).
- `src/ushka/security/` — the security middleware (CSRF, headers, CORS, trusted hosts), on by default,
  and `verify.py` (`ushka verify`).
- `src/ushka/sessions/` — signed-cookie sessions and revocable server-side sessions (database store).
- `src/ushka/crypto/` — Fernet `encrypt`/`decrypt`, keys and rotation. The only place that may import
  `cryptography` (the `crypto` extra), and only lazily; never write a cipher of our own.
- `src/ushka/templating/` (Jinja2 engine, flash), `static/` (static files).
- `src/ushka/web/` — what browsers and search engines see: `seo.py`, `pwa.py`, `i18n/`. Each has its own
  `[section]` in the schema and is off, or passive, until used.
- `src/ushka/mail/` — `imap.py`: `ImapClient` (stdlib `imaplib` in `asyncio.to_thread`, one lock). Everything from
  an e-mail is `Untrusted`; values going into IMAP commands are quoted and control characters refused. Not imported
  by `import ushka`; it has its own `[imap]` section in the schema.
- `src/ushka/api/` — what machines consume: `openapi.py` and `mcp.py` (routes as MCP tools).
- `src/ushka/orm/`, `docs/`, `testing.py` — batteries and tooling.
- `src/ushka/cli/` — argparse CLI; output through `ushka.cli.ui`; errors exit 1.
- `docs/` — Ushka Docs sources; `docs/guide/guard.md` documents error codes `USHKA-G00x`
  (anchors are linked from `UnsafeValueError.docs`). `docs/architecture.md` is the map of the code.
- `benchmarks/` — reproducible load test against Starlette and FastAPI (see its README).

## Commands

```bash
uv venv .venv && uv pip install -e ".[orm,docs]" pytest pytest-asyncio pyyaml starlette fastapi django httpx
.venv/bin/python -m pytest            # whole suite; also run on 3.10 and 3.14
.venv/bin/ushka docs check docs --api ushka
.venv/bin/ushka verify app:app        # in a project: attack your own routes
```

Every behaviour change needs a test and a line in `CHANGELOG.md`.
