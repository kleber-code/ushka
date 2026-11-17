# Features

The short tour. Each section links to the page that goes deep.

## Ushka Guard

Everything that comes from outside your program arrives as `Untrusted`: query,
form, JSON, headers, cookies, path parameters, and model output marked with
`guard.llm()`. Raw HTML responses, `|safe`, redirects, file paths and raw SQL
refuse it with an error that names the risk and the fix. Explicit sanitisers
(`safe.url`, `safe.path`, `safe.integer`, `safe.choice`, `safe.html`) are the way
out. See [Ushka Guard](guide/guard.md), and
[Guard on FastAPI, Starlette and Django](guide/guard-frameworks.md) for apps you
already have.

## Security middleware

On by default: CSRF protection (no tokens), CSP, HSTS, `nosniff`, CORS and trusted
hosts. See [Security middleware](guide/security.md).

## Typed parameters, validation and OpenAPI

`item_id: int`, `Query(ge=1)`, dataclass bodies and `Depends(...)`, with 422 errors
that list every problem. No pydantic. OpenAPI 3.1 comes from the same signatures.
See [Validation and typed parameters](guide/validation.md).

## WebSockets, SSE and agents

[WebSockets and Server-Sent Events](guide/realtime.md), secured by default, and
[routes as agent tools over MCP](guide/agents.md) with human approval.

## ushka verify

[`ushka verify`](guide/verify.md) sends hostile payloads to your own routes, inside
your process, and reports what got through.

## t-strings (Python 3.14+)

```python
return t"<p>{comment}</p>"                                  # escaped HTML
rows = await db.execute(t"SELECT * FROM posts WHERE id = {post_id}")  # bound
```

## Filesystem and decorator routing

- `routes/index.py` → `/`
- `routes/users/[user_id].py` → `/users/<user_id>`
- `@app.get("/health")` for anything else

Handlers return a `str`, `dict`, `list`, `None` (204), a `(body, status)`
tuple, a t-string or a `Response`. `HEAD` and `405 Method Not Allowed` (with
`Allow`) are handled for you. See [Routing](guide/routing.md) and
[Requests and responses](guide/requests-responses.md).

## Async Active Record ORM

```python
from ushka.orm import db

class User(db.Model):
    name = db.String(length=100)

user = await User.create(name="Alice")
```

Built on SQLAlchemy, with migrations through `ushka db`. Install it with
`pip install "ushka[orm]"`. See [ORM](guide/orm.md).

## Templates, sessions, uploads and static files

Jinja2 with autoescaping, project templates that override the built-in ones,
[signed cookie sessions](guide/sessions.md), [flash messages](guide/flashing.md),
multipart uploads with size limits, and [static files](guide/static_files.md) with
`ETag`/`304` and any folder you mount. See [Templates](guide/templates.md).

## Configuration without extra packages

Defaults, then `ushka.toml`, then `.env`, then `USHKA_<SECTION>_<KEY>`
environment variables. `DATABASE_URL` from your host works as is. Ushka never
rewrites your files. See [Configuration](guide/configuration.md).

## Fast, and quiet when idle

`uvloop` and `httptools` come with the install: about 2.3x the requests per second
of the pure-Python stack. `ushka run` has its own server loop that sleeps when
nothing happens (about 0.04 s of CPU per minute for two idle workers). See
[Performance](guide/performance.md).

## Ready to deploy

`ushka check --production` fails your CI if debug is on or the secret key is
missing. Environment variables configure everything, and `[server] workers` sets
the processes. See [Deploy](guide/deploy.md).

## Ushka Docs

A folder of Markdown becomes a searchable documentation site with an API reference,
served by your app, with a cache you can build into your Docker image. The page you
are reading is made with it. See [Ushka Docs](guide/docs.md).

## CLI

`ushka new` scaffolds a project that is secure from the first commit.
`ushka dev` reloads the app on change. `ushka check --production` and
`ushka verify` are made for CI. `routes`, `db` and `docs` cover the rest. See
[CLI](guide/cli.md).

## Lifespan hooks

```python
@app.on_startup
async def connect():
    ...
```
