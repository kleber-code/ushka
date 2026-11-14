# Features

## Ushka Guard

Everything that comes from outside your program arrives as `Untrusted`: query,
form, JSON, headers, cookies, path parameters, and model output marked with
`guard.llm()`. Raw HTML responses, `|safe`, redirects, file paths and raw SQL
refuse it with an error that names the risk and the fix. Explicit sanitisers
(`safe.url`, `safe.path`, `safe.integer`, `safe.choice`, `safe.html`) are the way
out. See [Ushka Guard](guide/guard.md).

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
`Allow`) are handled for you. See [Routing](guide/routing.md).

## Async Active Record ORM

```python
from ushka.orm import db

class User(db.Model):
    name = db.String(length=100)

user = await User.create(name="Alice")
```

Built on SQLAlchemy, with migrations through `ushka db`. Install it with
`pip install "ushka[orm]"`. See [ORM](guide/orm.md).

## Templates, sessions and flash messages

Jinja2 with autoescaping, project templates that override the built-in ones,
signed cookie sessions and flash messages. See [Templates](guide/templates.md)
and [Flashing](guide/flashing.md).

## Configuration without extra packages

Defaults, then `ushka.toml`, then `.env`, then `USHKA_<SECTION>_<KEY>`
environment variables. `DATABASE_URL` from your host works as is. Ushka never
rewrites your files. See [Configuration](guide/configuration.md).

## CLI

`ushka new` scaffolds a project that is secure from the first commit.
`ushka dev` reloads the app on change. `ushka check --production` fails your
CI if debug is on or the secret key is missing. `routes` and `db` cover the
rest. See [CLI](guide/cli.md).

## Lifespan hooks

```python
@app.on_startup
async def connect():
    ...
```
