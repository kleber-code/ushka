# Changelog

All notable changes to Ushka. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.8.0b1] - 2026-11-17

First beta of 0.8 (`pip install --pre ushka`). The 0.7 line stays the default install until 0.8 is final. This release adds server-side sessions, internationalisation, HTML forms, a test client, ORM transactions and strict templates (below), and reorganises the code by who uses it.

### Added (verify and sessions)

- **A supported way to forge a session for tests** (`ushka.sessions`, guides: Sessions, `ushka session`, ushka verify): `forge_session_cookie(app, {"uid": 1})` returns `"name=value"` signed with the app's secret key (`aforge_session_cookie` is the coroutine that also works with `[session] store = "database"` and creates the record). `parse_session_pairs` turns `["uid=1", "admin=true"]` into typed data.
  - `ushka verify --as-session uid=1` (repeatable) probes as that user, so routes behind a login are really attacked; `--cookie NAME=VALUE` sends a cookie you already have. Only session keys are reported, never values, and a forged server-side record is removed at the end.
  - `ushka session --set uid=1 [--app app:app]` prints `name=value` for `curl`. It needs a key from the environment or `.env` (never from the command line), and refuses when debug is off unless `--allow-non-debug`.

### Fixed (verify)

- **`ushka verify` probes the routes exempt from CSRF** (`[security] csrf_exempt_paths`), the webhooks and machine APIs, with the same method rules as the others (`--include-writes` for writes), marks them as exempt in the report, and no longer prints a "not probed" note for them. `--skip-exempt` leaves them out. The cross-site CSRF probe is not sent to them, since accepting it is their purpose.
- **A redirect is no longer a finding by itself.** Open redirect is reported only when the `Location` reflects the probe: its host is the probe's (high), or the probe is the destination in a parameter such as `next` (medium). The probe buried in the visitor's own URL is ignored, and the body of a 3xx response is not scanned for markup.

### Changed in the code layout

The top-level API (`from ushka import Ushka, render, Depends, Form, safe, _ ...`) does not change. Imports of modules by path do:

| Before | Now |
| --- | --- |
| `ushka.http.sessions`, `ushka.http.session_store` | `ushka.sessions` (`.session`, `.stores`) |
| `ushka.seo`, `ushka.pwa`, `ushka.i18n` | `ushka.web.seo`, `ushka.web.pwa`, `ushka.web.i18n` |
| `ushka.openapi`, `ushka.mcp` | `ushka.api.openapi`, `ushka.api.mcp` |
| `ushka.verify` | `ushka.security.verify` |
| `ushka.utils.flash` | `ushka.templating.flash` |
| `ushka.core.exceptions` | removed (its only used class, `ContentToJsonParserFailed`, is in `ushka.http.exceptions`) |

- `ushka check --production` warns when `[security] allowed_hosts` is empty (any `Host` header is accepted).
- Type annotations and imports modernised across the code (`ruff`), with no change in behaviour.
- Docs: the features page says what is established, new and experimental, the API reference is grouped by area, and the architecture page matches the new layout.

### Added

- **`ushka db inspect`: adopt a database another ORM created** (guide: ORM, Existing databases). It reflects the configured database (`--url`, `--table` repeatable, `--schema`, `--write FILE [--force]`) with SQLAlchemy's generic inspector (SQLite, PostgreSQL, MySQL) and writes Ushka models: `db.String/Int/BigInt/UUID/Bool/DateTime/JSON/...`, `nullable`, `unique`, indexes, foreign keys with their `ON DELETE`/`ON UPDATE`, UUID, text and composite primary keys. Server defaults are mapped to Python defaults when possible (`true`, numbers, strings, `now()` becomes `auto_now_add=True`). What the database does not say is never applied silently: `NOT NULL` columns without a default, `created_at`/`updated_at`-style timestamps and foreign keys without `ON DELETE` (with the effect of deleting a parent and the two ways out) are reported as warnings and as `TODO(ushka db inspect)` comments.
- **`ushka db check-models`** compares the app's models with the database (missing or extra columns, nullability, types, `ON DELETE`) and exits 1 on differences.
- **`db.ForeignKey(on_update=...)`**, and `on_delete=None` for no clause (a schema made by another ORM usually has none).
- **Server-side sessions you can revoke** (`ushka.http.session_store`, guide: Sessions). `[session] store = "database"` keeps the data on the server and puts only a random, signed id in the cookie, so `session.clear()` / `session.revoke()` really ends the session (a stolen cookie stops working), there is no 4 KB limit, `session.rotate()` (and the first login on an existing id) changes the id against fixation, `revoke_user_sessions(request_or_app, user_id)` logs a user out everywhere, and `[session] max_age` / `idle_timeout` expire sessions. Ids are stored hashed, the database table is created on first use, and `app.session_store` accepts your own `SessionStore` (Redis, ...). It needs a database: without a configured `[database] url` (or `DATABASE_URL`), or without SQLAlchemy, Ushka keeps the signed cookie and logs a warning (`ushka check --production` reports it); there is no in-memory store, since it would log people out at random with several workers. Off by default: the signed cookie behaves exactly as before. New `[session]` settings: `store`, `cookie_name`, `max_age`, `idle_timeout`, `user_key`, `table`.
- **ORM transactions**: `async with db.transaction():` (alias `db.atomic()`) runs several operations atomically. `Model.create/save/delete/get/all/first/filter` and `db.execute` share one session (kept in a context variable, so requests and tasks never share it), committed at the end and rolled back on an exception. Nested blocks use a `SAVEPOINT` (`savepoint=False` joins the outer one); `db.in_transaction` reports the state. Outside a block nothing changes. On SQLite the driver now issues `BEGIN` explicitly so savepoints work.
- **Automatic timestamps**: `db.DateTime(auto_now_add=True)` (insert) and `db.DateTime(auto_now=True)` (insert and every update, including bulk `update()` through `db.execute`), in UTC and timezone-aware (`timestamptz` on PostgreSQL, read back as UTC on SQLite and MySQL; `timezone=False` for a naive column). `ushka.orm.utcnow()`.
- **ORM schema options**: `__extend_existing__ = True` to mirror a table already in the metadata; `db.BaseModel`, a base without the default `id`; declaring `id = db.UUID(primary_key=True)` replaces the default key; `db.ForeignKey(..., use_alter=True)` and `db.Relationship(..., post_update=True)` for cyclic foreign keys, which removes the `Cannot correctly sort tables` warning. How UUID columns are stored on SQLite and MySQL is documented.
- **A whole HTML form as a dataclass.** `Annotated[Lead, Form()]` fills the dataclass (or `TypedDict`) from `application/x-www-form-urlencoded` and `multipart/form-data` with the same conversion, limits and body-size checks as a JSON body. An unchecked checkbox is `False`, an unchecked group is `[]`, an empty number or date input is "not filled in", repeated fields (`a=1&a=2`) are a list, and fields the model does not declare are dropped (no mass assignment). Multipart text fields that repeat are now a list too, as in urlencoded forms. A `dict` field receives an uploaded file's info.
- **Answer an invalid form yourself.** `@app.post("/lead", on_invalid=show)` (or `@on_invalid(show)` on a file route) runs `show` instead of the JSON 422. It is an ordinary handler and takes `errors: RequestValidationError`, which now has `.fields` (messages by field name) and `.values` (what was typed, still `Untrusted`, so a template escapes it) to draw the form again. Without it the answer stays a JSON 422 that never echoes the input.
- **`ushka.testing.TestClient`**, with no new dependency: `async with TestClient(app) as client` runs `on_startup` and `on_shutdown` (which `httpx.ASGITransport` does not), keeps cookies between requests, and offers `get/post/put/patch/delete/head/options` with `json=`, `data=`, `files=`, `params=`, `headers=`, `cookies=` and `follow_redirects=`. `TestClient(app, browser=True)` sends `Sec-Fetch-Site` and `Origin` like a same-origin browser for CSRF tests. Guide: Testing.
- **`ushka check` warns about what the Content-Security-Policy blocks**: `<script src>` and stylesheet `<link>` from another site and inline `<script>` in `templates/`, with `file:line` and how to fix it. Warnings only; it stays quiet when `[security] csp` is `"off"`, names the host, or allows inline code. The Security guide shows how to allow a CDN.
- **Internationalisation, from standard gettext catalogs** (`ushka.i18n`, guide: Internationalisation), with no new dependency. `[i18n]` in `ushka.toml` turns it on; `{{ _("x") }}`, `gettext`, `ngettext`, `pgettext`, `{% trans %}` (with plurals and escaped variables) and the `lang`/`locale` template variables work in templates, and `from ushka import gettext, lazy_gettext, translate` in Python, bound to the language of the request being served (a contextvar, so concurrent requests never mix). The language comes from `?lang=`, a cookie and `Accept-Language` (parsed with `q` values), in the order of `[i18n] order`, and is only ever matched against `[i18n] locales`, never used as a path. `.mo` files from Django or `msgfmt` work as they are, are cached in memory (reloaded in debug), and a missing catalog or message returns the original text. `og:locale` follows the active language. `ushka i18n extract` writes the `.pot` (Python and templates) and `ushka i18n compile` turns `.po` into `.mo` with a small built-in compiler.
- **Strict templates.** In debug a variable missing from a template raises `UndefinedError` instead of rendering empty, and the debug page names the template file and line. `[app] strict_templates = true` does the same outside debug. Production keeps Jinja's tolerant default, and the mode is set again by every app, so it never leaks between apps or tests.

### Changed

- `db.DateTime(auto_now=True)` now also refreshes the column on update (it only set a default on insert); use `auto_now_add=True` for a creation date. Automatic columns are timezone-aware, so an existing one needs a migration or `timezone=False`.
- Repeated text fields in a multipart form now become a list (as in a urlencoded form) instead of keeping only the last value.

## [0.7.0] - 2026-11-16

### Added

- **Every setting is written down, nothing is hidden** (`ushka.core.settings`, guide: Configuration). One schema lists all 76 settings with their default and meaning, and everything is generated from it:
  - `ushka new` writes a `ushka.toml` with **every** setting, annotated, instead of a few.
  - `ushka config` prints each setting, its value and where it came from (`default`, `ushka.toml`, `.env`, `environment`); `--describe` adds the meaning and the environment variable, a section name filters, `--template` prints a complete annotated `ushka.toml` for an existing project.
  - The settings table in the docs is generated from the same schema, and a test fails when it drifts or when the code reads a setting the schema does not declare.
  - Loading `ushka.toml` now warns about a key Ushka does not know in a built-in section (`tain` suggests `taint`) and about a value of the wrong type (`csrf = "false"` is a non-empty string, so it used to read as on). `ushka check` and `ushka config` count them as problems. Your own sections are not checked.
- **SEO, ready out of the box** (`ushka.seo`, guide: SEO). `{{ seo() }}` in `<head>` writes the title, description, canonical link, robots rule, Open Graph, Twitter tags and JSON-LD (`WebSite` on `/`, `Article` for `type = "article"`), from `[seo]` in `ushka.toml`. A page overrides anything with `seo(title=..., noindex=True, ...)` or a `page_seo` dict in the context. `/robots.txt` and `/sitemap.xml` are served (plain `GET` pages, minus `[seo] sitemap_exclude`; `@app.sitemap_source` adds pages from code). Your own routes win. Values are escaped, unsafe URLs are dropped, and no `Host` header is trusted for absolute URLs unless `[seo] url`, debug or `allowed_hosts` says so. `ushka new` writes the `[seo]` block and the tag, and `ushka check` reminds you to set `url`.
- **Progressive Web App, configured in `[pwa]`** (`ushka.pwa`, guide: Progressive Web App), off by default. Serves `/manifest.webmanifest`, a service worker, `/pwa.js` (a file, so the default CSP stays strict) and an offline page; `{{ pwa() }}` writes the head tags. The worker never caches pages (they can be private): navigations use the network and fall back to the offline page, and `[static]` files are cached and refreshed in the background. `ushka check` requires 192x192 and 512x512 icons.


- **A API reference that is easy to move around in** (`ushka.docs`). `docs/nav.toml` can group the modules with `[[api.group]]` (`title`, `description`, `modules`; the old `modules = [...]` list still works and is grouped by sub-package). The sidebar shows the API as collapsible groups with short labels and opens only the group you are in (the same for sections such as Guide), instead of 41 dotted module names; there is an `api/` overview page describing every module, breadcrumbs, and a scroll-spy "On this page". Each module page starts with an index of its classes and functions, a methods table for classes, the signature as a code block (one parameter per line when long, keyword-only `*` kept), parameters in a table with headers and without `self`; private names stay out. `` `Name` ``, `` `Class.method` `` and `` `function()` `` in docstrings link to the documented symbol. `ushka docs check` now also reports a module listed twice, outside the package, or a group without title or modules.
- **`uvloop` and `httptools` are installed by default** (not on Windows or PyPy, where uvloop does not exist) and Uvicorn uses them without configuration. On the project's benchmark, one worker went from about 3,200 to 7,600 requests per second on the hello route (about 2.3x; typed and POST routes 2.6x and 1.7x), ahead of FastAPI on the same loop and parser. A core install is now 9 packages and 20 MB. `benchmarks/run.sh` takes `LOOP=asyncio HTTP=h11` to measure the pure-Python stack.
- **`Docs(cache=...)`**: keeps the rendered site in a JSON file, keyed by a hash of the Markdown, the documented sources and the renderer, so it is never stale. The Ushka website builds it in its Docker image, and the server starts in 0.3 s instead of 1 s of CPU per worker (about 15 s under a 20% CPU quota).
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
- **Supply-chain hardening** (see `.github/SECURITY.md`, "Verifying a Release"):
  - Every GitHub Action is pinned to a full commit SHA and Dependabot keeps them current. A test fails the build if one is not pinned, if a script inlines attacker-controlled text, or if a workflow loses its `permissions`.
  - Releases carry a CycloneDX **SBOM** (`ushka.cdx.json`), GitHub **build-provenance and SBOM attestations** (`gh attestation verify`) and PyPI **PEP 740 attestations**.
  - Build, attest and publish are separate jobs with the least permissions each. A release is refused when its tag does not match the package version.
  - CI installs from `pdm.lock` and fails on a stale lock. The dev group now includes the frameworks used by the integration tests.
- **Ushka Guard for FastAPI, Starlette and Django** (guide: Ushka Guard on FastAPI, Starlette and Django): `ushka.guard.integrations.fastapi|starlette|django`, each with `install()` and `uninstall()` and no new dependency.
  - Client data becomes `Untrusted`: query, headers, cookies, path, JSON and forms. For FastAPI the values are marked after pydantic validation, because pydantic returns plain `str`. `int`, `Enum` and `Literal` stay as validated values.
  - `HTMLResponse`, redirects, `FileResponse` (Starlette) and `HttpResponse`, redirects and `mark_safe` (Django) refuse them.
  - `install(rewrite_packages=[...])` keeps the mark through f-strings. The FastAPI integration fails loudly if FastAPI changes the internal it relies on.
- **`ushka verify`** (guide: ushka verify): sends hostile payloads (XSS, SQL injection, template injection, path traversal, open redirect, header injection, junk) to your own routes and reports what got through. It runs in-process against your app and cannot reach any other server. `GET` routes only unless `--include-writes`. Also flags debug on, the guard, headers or CSRF turned off, and cross-site writes that are accepted. Exits 1 on findings (`--fail-on`, `--json`, `--param`).
- **Routes as agent tools over MCP** (`ushka.mcp`, guide: Routes as agent tools): mark routes with `@tool(reads=, writes=, calls=)` and serve them with `app.enable_mcp()`.
  - Only marked routes are exposed, and the input schema comes from the typed parameters.
  - Declared capabilities become MCP annotations and decide approval: sensitive tools need a human (`ApprovalQueue`, `terminal_approver` or your own callable), and are refused when no approver is configured. A `GET` route cannot declare `writes`.
  - A bearer token is required (`USHKA_MCP_TOKEN`). Calls run through the whole app, so security middleware, validation and `Depends` still apply.
  - `app.router.iter_routes()` lists the registered routes.
- **WebSockets** (guide: WebSockets and Server-Sent Events): a `websocket` function in `routes/` or `@app.websocket`. Typed parameters and `Depends` work on the handshake. Secured by default: cross-site `Origin` refused (cross-site WebSocket hijacking), trusted hosts, a message size limit, and received data is `Untrusted`.
- **Server-Sent Events and streaming**: `EventSourceResponse`, `ServerSentEvent` and `StreamingResponse`. Keep-alive pings, cleanup when the client disconnects, and field injection through line breaks is refused.
- **OpenAPI 3.1** generated from the same signatures: `app.openapi()` and `app.enable_openapi()` (opt-in, `/openapi.json`).
- `request.path_params`.
- `HTTPForbidden` (403), and list settings in environment variables (`a,b`).

### Fixed

- **`ushka run` no longer burns CPU when idle.** A site with two workers and only a healthcheck cost about 1.2 s of CPU per minute (10 to 80 times a FastAPI app), because Uvicorn wakes each worker 10 times a second and pings each worker from the supervisor twice a second. Production now runs `ushka.core.server`: workers tick once a second, the supervisor sleeps until a worker dies, a signal arrives or the next health check (every 10 s), and an idle two-worker app measured 0.32 s of CPU per minute with stock Uvicorn and 0.04 s with this. `ushka dev` is unchanged.
- **Slow starts no longer kill workers in a loop.** Uvicorn's 5 s health ping judged a worker that was still importing its app as hung and killed it, over and over, wasting CPU. A new worker is now exempt from pings for 90 s and the ping timeout is 30 s. A worker that really dies is still replaced at once.
- A response that cannot be sent (for example a header value with a line break, with the guard off) now gets a clean 500 instead of an exception escaping to the ASGI server.

### Changed

- The Ushka website now runs one worker (it serves cached pages), halving idle memory and startup CPU.
- Responses with a known body size now send `Content-Length` instead of chunked encoding (not for streaming, `204` or `304`, and a header you set yourself is kept). `HEAD` now reports the length of the `GET` body. In an alternating A/B test on small responses the median was about 15% faster, and steadier.
- `import ushka` is about 25% faster (128 ms to 95 ms): `uvicorn` is imported only when `Ushka.run()` serves.

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
