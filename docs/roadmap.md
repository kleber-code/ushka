# Roadmap

Ushka's direction is in [Why Ushka changed](why-ushka-changed.md). This page
lists what has shipped and what is next.

## 0.5 (in progress)

- [x] Ushka Guard: `Untrusted` request data and model output, guarded sinks,
      sanitisers, and errors written for humans and for agents.
- [x] Compile-time rewrite so the mark survives f-strings in `routes/`, plus an opt-in import hook for your own packages.
- [x] t-strings (Python 3.14) for HTML responses and SQL.
- [x] Read-only configuration with `.env` and environment variables. No
      `tomlkit` and no `rich`: fewer dependencies.
- [x] CLI: `ushka check`, a secure `ushka new` (with `.env`, `.gitignore` and `AGENTS.md`), and correct exit codes.
- [x] Lifespan hooks, `(body, status)` returns, `HEAD`, and 400 for malformed JSON.

## Next

- **Security middleware on by default.** CSRF protection, security headers
  (CSP, HSTS, `nosniff`), CORS and trusted hosts.
- **Routes as agent tools.** Expose chosen routes over MCP, with declared
  capabilities (what each route reads, writes and calls) and human approval
  for sensitive actions.
- **`ushka verify`.** Send attack payloads to your own routes and report what
  got through.
- **Standalone `ushka.guard`.** The same protection for FastAPI, Starlette and Django.
- **Typed path parameters, request validation and OpenAPI.**
- **WebSockets and Server-Sent Events.**
- **Supply-chain hardening.** Pinned actions, SBOM and attestations.

## Get involved

Ideas and pull requests are welcome. See the
[contributing guidelines](https://github.com/kleber-code/ushka/blob/main/.github/CONTRIBUTING.md).
