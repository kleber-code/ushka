# Roadmap

Ushka's direction is in [Why Ushka changed](why-ushka-changed.md). This page
lists what has shipped and what is next. The full detail is in the
[changelog](https://github.com/kleber-code/ushka/blob/main/CHANGELOG.md).

## 0.5 and 0.6 (released)

- [x] Ushka Guard: `Untrusted` request data and model output, guarded sinks,
      sanitisers, and errors written for humans and for agents.
- [x] Compile-time rewrite so the mark survives f-strings in `routes/`, plus an opt-in import hook for your own packages.
- [x] t-strings (Python 3.14) for HTML responses and SQL.
- [x] Read-only configuration with `.env` and environment variables. No
      `tomlkit` and no `rich`: fewer dependencies.
- [x] CLI: `ushka check`, a secure `ushka new` (with `.env`, `.gitignore` and `AGENTS.md`), and correct exit codes.
- [x] Lifespan hooks, `(body, status)` returns, `HEAD`, and 400 for malformed JSON.
- [x] Ushka Docs, `app.mount_static` and the project website (0.6).

## Next release (unreleased)

Merged on `main`, waiting for a version number.

- [x] [Security middleware](guide/security.md), on by default: CSRF protection,
      security headers (CSP, HSTS, `nosniff`), CORS and trusted hosts.
- [x] `app.add_middleware` / `@app.middleware`.
- [x] Typed parameters, request validation, `Depends` and OpenAPI.
- [x] WebSockets and Server-Sent Events.
- [x] Routes as agent tools over MCP, with declared capabilities and human approval.
- [x] `ushka verify`.
- [x] Ushka Guard for FastAPI, Starlette and Django.
- [x] Supply-chain hardening: pinned actions, SBOM and attestations.
- [x] `ushka run` serves with `ushka.core.server`: idle CPU close to zero, and
      workers that are slow to start are no longer killed in a loop.
- [x] `uvloop` and `httptools` installed by default: about 2.3x the requests per
      second, with a core install of nine packages and 20 MB.
- [x] `Docs(cache=...)`: render the docs once, in the Docker build.
- [x] Typed path parameters: an annotation converts and validates (422).

## Next

- **Publish `ushka.guard` as its own package**, declaring `markupsafe`, so non-Ushka apps install only the guard.
- **Split `ushka.core`** into leaf modules and orchestration, so `core` and `http` stop importing each other.
- **Cut the cost of the default middleware** on small requests, and more adapters (Flask, Litestar).

## Get involved

Ideas and pull requests are welcome. See the
[contributing guidelines](https://github.com/kleber-code/ushka/blob/main/.github/CONTRIBUTING.md).
