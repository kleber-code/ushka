# AGENTS.md — working on the Ushka framework itself

## Principles

- **Low dependency.** The core depends on `uvicorn`, `jinja2`, `python-multipart`
  (and `tomli` on 3.10). Do not add runtime dependencies; implement small things
  with the standard library. Security-critical parsers are the exception.
- **Batteries included.** Features a typical web app needs belong in the box.
- **Lightweight in concept.** One clear idea per feature; no hidden magic.
- **Secure by default.** New sinks must call a `ushka.guard.check_*` function;
  new request data sources must be wrapped in `Untrusted`.

## Layout

- `src/ushka/guard/` — taint core. Must not import anything else from `ushka`
  (enforced by `tests/test_guard.py`), so it can ship standalone.
- `src/ushka/core/` — app, router, config (read-only layered config), error handler, logging.
- `src/ushka/http/` — request, response, cookies, sessions, multipart, redirect.
- `src/ushka/cli/` — argparse CLI; output through `ushka.cli.ui`; errors exit 1.
- `docs/` — mkdocs-material; `docs/guide/guard.md` documents error codes `USHKA-G00x`
  (anchors are linked from `UnsafeValueError.docs`).

## Commands

```bash
uv venv .venv && uv pip install -e ".[orm]" pytest pytest-asyncio pyyaml
.venv/bin/python -m pytest            # whole suite; also run on 3.10 and 3.14
.venv/bin/python -m mkdocs build --strict
```

Every behaviour change needs a test and a line in `CHANGELOG.md`.
