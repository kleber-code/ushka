# Configuration

Ushka reads its settings from four layers. Each one overrides the one before:

1. **Built-in defaults** (the table below).
2. **`ushka.toml`** in the application directory (the folder of the file that
   creates `Ushka()`).
3. **`.env`** next to `ushka.toml`, for secrets you keep out of Git.
4. **Environment variables**.

Every layer is optional. Ushka only *reads* `ushka.toml`: it never creates or
rewrites the file.

## `ushka.toml`

Settings are grouped in sections. This is the file `ushka new` writes:

```toml
[app]
name = "hello"
# `ushka dev` turns debug on by itself; keep it off here so production is safe.
debug = false

[database]
url = "sqlite:///hello.db"

[static]
enable = true
url = "/static"
dir = "static"
```

If the file is not valid TOML, the app refuses to start with a `ValueError`
that names the file and the position of the error.

## All settings

| Section | Key | Default | Meaning |
| --- | --- | --- | --- |
| `[app]` | `name` | `"Ushka App"` | Display name. |
| `[app]` | `debug` | `false` | Debug pages with tracebacks. Never on in production. |
| `[app]` | `auto_discover` | `true` | Load route files from `routes/`. |
| `[app]` | `secret_key` | `""` | Signs the session cookie. **Do not put it in `ushka.toml`**; use `USHKA_APP_SECRET_KEY`. |
| `[database]` | `url` | `"sqlite:///ushka.db"` | SQLAlchemy URL for the [ORM](orm.md). |
| `[server]` | `host` | `"127.0.0.1"` | Bind address for `ushka dev`, `ushka run` and `app.run()`. |
| `[server]` | `port` | `8000` | Port. |
| `[server]` | `workers` | `1` | Worker processes for `ushka run`. |
| `[static]` | `enable` | `false` | Serve [static files](static_files.md). |
| `[static]` | `url` | `"/static"` | URL prefix for static files. |
| `[static]` | `dir` | `"static"` | Folder with the files, relative to the app directory or absolute. |
| `[limits]` | `max_request_body_size_in_KB` | `2048` | Largest request body (2 MB). Bigger bodies get **413**. |
| `[limits]` | `max_request_body_multipart_size_in_KB` | `51200` | Largest multipart upload (50 MB). |
| `[security]` | `taint` | `true` | [Ushka Guard](guard.md). Turning it off is a migration aid, not a mode. |

You can add your own sections and keys too; they are read the same way:

```toml
[payments]
currency = "EUR"
```

## Environment variables and `.env`

Any setting can be overridden with a variable named `USHKA_<SECTION>_<KEY>`,
either in the real environment or as a line in `.env`:

```bash
# .env (git-ignored)
USHKA_APP_SECRET_KEY=paste-a-long-random-value-here
USHKA_DATABASE_URL=postgresql://user:pass@localhost/shop
```

```bash
USHKA_APP_DEBUG=true USHKA_SERVER_PORT=5000 python app.py
```

Values are converted to the type of the default: `true/false`, `1/0`,
`yes/no` and `on/off` for booleans, whole numbers for integers. An invalid
value (`USHKA_SERVER_PORT=abc`) stops the app with a clear error.

For the database URL two common names work as well: `DATABASE_URL` (set by
most hosting platforms) and the older `USHKA_DB_URL`.

`.env` supports `KEY=value` lines, `# comments`, optional quotes and
`export KEY=value`. Variable expansion is not supported. When a key is in both
`.env` and the real environment, the environment wins.

## The secret key

Sessions (and therefore [flash messages](flashing.md)) need a secret key to
sign the cookie.

* `ushka new` writes a random `USHKA_APP_SECRET_KEY` to `.env` for you.
* With `debug` on and no key set, Ushka generates a key for the current
  process, so sessions work in development. It is never written anywhere and
  changes on every restart.
* With `debug` off and no key set, touching `request.session` raises a
  `RuntimeError` that explains how to create one:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

`ushka check` fails when `secret_key` is found in `ushka.toml`, and
`ushka check --production` also fails when the key is missing or shorter than
32 characters.

## Reading settings in code

Every setting is available as `SECTION_KEY`: as an attribute in upper case, or
through `get()` in any case.

```python
# routes/about.py
async def get(config):
    return {
        "name": config.APP_NAME,
        "debug": config.get("app_debug"),
        "currency": config.get("payments_currency", "USD"),  # default if missing
        "debug_from": config.source_of("app_debug"),          # "default", "ushka.toml", ".env", "environment"
    }
```

A handler gets the configuration by asking for a parameter named `config` (or
annotated with `Config`); see [Dependency Injection](dependency_injection.md).
Outside a handler use `app.config`, or `Config()` once the app exists (it is a
process-wide singleton).

* `config.get(key, default=None, required=False)`: returns `default` when
  the key is missing, or raises `KeyError` when `required=True`.
* `config.source_of(key)`: where the value came from. `ushka check` prints it
  for the main settings.

Two read-only values describe the running framework: `config.USHKA_VERSION`
and `config.USHKA_WORKDIR` (the application directory).

> **Ushka Tip:** Run `ushka check` whenever a setting does not behave as you
> expect. It shows each value together with the layer it came from.
