# Changelog

All notable changes to Ushka. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- **Security middleware, on by default** (`ushka.security`, guide: Security middleware):
  - Headers on every response, error pages included: `nosniff`, `X-Frame-Options`, `Referrer-Policy`, a restrictive `Content-Security-Policy`, `Cross-Origin-Opener-Policy`, and HSTS on https.
  - CSRF protection without tokens or a secret key, based on `Sec-Fetch-Site` and `Origin`.
  - Trusted hosts (`allowed_hosts`) and CORS with preflight (`cors_*`). A wildcard origin with credentials is refused at startup.
  - Configured in `[security]`; each part can be turned off.
- **`app.add_middleware` / `@app.middleware`**: `async def mw(request, call_next)`. Errors reach middleware as ordinary responses.
- **Typed parameters and validation** (guide: Validation and typed parameters), standard library only:
  - Path, query, header, cookie, JSON body and form parameters are converted to their annotations, with `Query`, `Header`, `Cookie`, `Path`, `Body`, `Form` and `Field` for sources and limits.
  - Bodies can be dataclasses or `TypedDict`s, nested. Undeclared fields are dropped (no mass assignment).
  - Invalid requests get **422** with every error and its location, never echoing the input.
  - Converted values (`int`, `UUID`, `Enum`, `Literal`...) are plain, so conversion also sanitises. `str` stays `Untrusted`.
- **`Depends`**: sync, async and `yield` dependencies, once per request, nested, sharing the handler's `Response`, with `app.dependency_overrides` for tests.
- **OpenAPI 3.1** generated from the same signatures: `app.openapi()` and `app.enable_openapi()` (opt-in, `/openapi.json`).
- `request.path_params`.
- `HTTPForbidden` (403), and list settings in environment variables (`a,b`).

### Changed

- **Behaviour change:** an annotation on a path parameter (`user_id: int`) now converts and validates it (422 when invalid). Before, annotations were ignored. Unannotated parameters are unchanged.
- A parameter that is not injected, not in the route and has no default is now a required query parameter (422 when missing) instead of a 500.
- **Behaviour change:** browser requests from another site that write (`POST`, `PUT`, `PATCH`, `DELETE`) now get 403, and responses carry a CSP that blocks inline scripts and third-party resources. Adjust with `csp`, `csrf_trusted_origins` or `csrf = false`.

### Fixed

- Website: the CSS URLs carry a content hash, so browsers no longer show a cached old stylesheet (for example, the hero dots behind the text) after a deploy. On narrow screens the dots are hidden, since the illustration moves under the text.

## [0.6.0] - 2026-11-14

### Added

- **Ushka Docs** (`ushka.docs`, extra `ushka[docs]`): a folder of Markdown becomes a documentation site served by your app.
  - Rendering: pages are rendered at startup with Pygments highlighting on the server and served with ETags.
  - Search runs on the server, and the query is untrusted and escaped.
  - The API reference is generated from docstrings with griffe.
  - SEO: canonical URLs, Open Graph, JSON-LD breadcrumbs and `sitemap.xml`.
  - The theme can be overridden and its contrast meets WCAG AA, which is checked in tests.
  - `ushka docs check` fails on broken links or anchors, and `ushka docs serve` previews the site.
- **`app.mount_static(url, directory, html=..., cache_control=...)`**: serves any folder with `ETag`/`304`, `Last-Modified`, `nosniff` and an html mode. `[static] cache_control` sets the header for the `[static]` folder.
- **The project website**, https://ushka.satela.com.br, built with Ushka in `site/`. It serves the docs, an `install.sh` with a published SHA-256, `llms.txt`, `robots.txt` and `sitemap.xml`.
- **Ushka, the mascot**: a maned-wolf (lobo-guará) guardian with 12 stickers. The built-in pages show her inline.

### Changed

- **The docs no longer use MkDocs.** They are rendered by Ushka Docs at https://ushka.satela.com.br/docs/, and GitHub Pages now redirects there. The `UnsafeValueError` docs links point to the new site.
- **The dev dependency group** drops MkDocs and its plugins.

## [0.5.0] - 2026-11-14

Ushka now has one purpose: insecure code, whether a person or an AI wrote it,
does not run silently. See
[Why Ushka changed](https://ushka.satela.com.br/docs/why-ushka-changed/).

### Added

- **Ushka Guard** (`ushka.guard`), on by default:
  - Request query, form, JSON, text body, headers, cookies and path parameters arrive as `Untrusted` (a `str` subclass that records its source).
  - `guard.llm(text)` marks language-model output as untrusted.
  - Guarded sinks refuse `Untrusted` values with `UnsafeValueError`: HTML response bodies (`USHKA-G001`), the `|safe` filter (`G002`), `redirect()` (`G003`), raw SQL in `db.execute()` / `db.text()` (`G005`).
  - Every error carries a stable code, the risk, a concrete fix and a docs link. In debug it is returned as JSON for `Accept: application/json`.
  - Sanitisers: `safe.url`, `safe.path`, `safe.integer`, `safe.choice`, `safe.html` and `safe.trust(reason=...)`. A rejected value becomes `400 Bad Request`.
  - A compile-time rewrite keeps the mark through f-strings, `.format`, `%`, `.join` and `str()` in `routes/` files. `guard.rewrite.install([...])` does the same for your own packages.
- **t-strings (Python 3.14):**
  - Handlers can return `t"..."` for escaped HTML.
  - `db.execute(t"...")` binds every value.
  - `ushka.guard.templates.html()` and `.sql()` work anywhere.
- **Configuration:**
  - `.env` support and `USHKA_<SECTION>_<KEY>` environment overrides with type conversion.
  - `DATABASE_URL` and `USHKA_DB_URL` aliases.
  - `config.source_of(key)` tells where a value came from.
- **CLI:**
  - `ushka check [--production]`, which exits 1 on problems.
  - `ushka --version`.
  - `ushka new` now writes `.env` (with a generated secret), `.env.example`, `.gitignore`, `AGENTS.md` and a stylesheet.
- **App:**
  - `@app.on_startup` / `@app.on_shutdown`; a failing startup hook aborts the server.
  - `(body, status[, headers])` return values, `None` → `204`, and automatic `HEAD`.
  - `config` is injected by parameter name.
- Top-level exports: `from ushka import redirect, render, guard, safe`.
- Python 3.14 in the CI matrix and classifiers.

### Changed (breaking)

- **Request values are `Untrusted`.** Code that passes them straight into a
  redirect, a raw HTML string or raw SQL now raises. Use a sanitiser.
  `[security] taint = false` turns the guard off temporarily while you migrate.
- **`ushka.toml` is read-only.** Ushka no longer creates the file or rewrites it with missing keys. Defaults live in code.
- **Secret key:**
  - `secret_key` is no longer generated into `ushka.toml`. Set `USHKA_APP_SECRET_KEY` in the environment or in `.env`.
  - In debug mode a per-process key is generated. Without a key outside debug, sessions raise a clear error. The fixed `"insecure-debug-key"` fallback is gone.
- **The ORM reads its URL from the configuration.** It uses `[database] url`, `USHKA_DATABASE_URL` or `DATABASE_URL`. Before, it read only `USHKA_DB_URL`, so the app and `ushka db` could target different databases.
- **The engine is created lazily.** Plain `postgresql://` and `mysql://` URLs get async drivers automatically.
- **Responses:**
  - Text and JSON responses carry `; charset=utf-8`.
  - Unsupported return types raise `TypeError` instead of sending an empty 200.
  - `bool`, `float` and `None` bodies are JSON.
- `405` responses list `HEAD` in `Allow` when `GET` exists.
- WebSocket connections are closed properly instead of getting an HTTP 501 message.
- **CLI errors exit with status 1.** `ushka dev` forces debug on, and `ushka new` scaffolds `debug = false`.
- **Dependencies:** removed `rich` and `tomlkit`; added `tomli` on Python 3.10 only. `ushka[orm]` now installs `sqlalchemy[asyncio]` (greenlet).

### Fixed

- `ushka routes add /` created `routes/.py`, and `ushka routes add ../x` could write outside `routes/`.
- `ushka[orm]` installed an ORM that failed to import on SQLAlchemy 2.1 (missing greenlet).
- Malformed JSON or non-UTF-8 bodies returned 500 instead of 400.
- Functions imported into a route file (`from helpers import get`) became routes.
- Templates were looked up in the process's current directory instead of the app directory.
- `[app] auto_discover = false` did not disable route discovery.
- `app.run()` printed nothing (the logger was never configured) and ignored `[server] host/port`.
- An exception inside the error handler left the client without a response, and cookies or session changes were dropped on error responses.
- The ORM leaked one scoped session per request, and nested calls closed each other's session.
- `db.JSON()` shared one mutable default dict across rows, and `db.Date(auto_now=True)` used a timestamp.
- `raise_error()` always raised 404.
- On SQLite (the default database) every ORM insert failed: the `BIGINT` primary key did not auto-increment.
- A flash message was lost when older unread messages were still in the session.
- Static files, and any response with a custom `Content-Type`, were sent with two `Content-Type` headers.
- Run from another directory (`ushka run pkg.app:app`), the app looked for `static/`, `ushka.toml` and `.env` in the current directory instead of its own.
- `ushka routes add` refused `[int:name]` segments.
- **Built-in pages:** the error, debug and startup pages no longer load Tailwind, Google Fonts, Font Awesome or highlight.js from CDNs. They are self-contained, have no JavaScript and work offline.
- `setup_logging()` added a duplicate handler on every call.

### Security hardening (planned as 0.4.1, shipped in 0.5.0)

- **Static files:** traversal through sibling directories and symlinks is blocked. Null bytes in paths are rejected.
- **Response headers:** header values keep their case. CR/LF/NUL in headers are rejected.
- **Status codes:** 413 for oversized bodies, 400 for malformed forms and queries, 405 with `Allow` for a wrong method.
- **Exceptions:** fixed exceptions that turned every 400/404/413 into a 500.
- **Sessions:** session contents are never logged.
