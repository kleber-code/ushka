# Ushka Guide

Ushka is the web framework where insecure code, whether you or an AI wrote it,
does not run silently. It is small in concept (a file in `routes/` is a URL,
a function named `get` answers GET), light on dependencies (the core needs only
`uvicorn`, `jinja2`, `python-multipart`, plus `tomli` on Python 3.10) and comes
with the batteries a web app needs: templates, sessions, flash messages, static
files, an async ORM and a CLI.

## Your first app in a minute

```bash
pip install ushka
ushka new hello
cd hello
ushka dev
```

Open <http://127.0.0.1:8000>. `ushka new` creates a project that is secure and
runnable from the start:

```text
hello/
├── app.py              # app = Ushka()
├── ushka.toml          # settings (no secrets)
├── .env                # USHKA_APP_SECRET_KEY, git-ignored
├── .env.example
├── .gitignore
├── AGENTS.md           # rules for AI coding agents
├── routes/index.py     # GET /
├── templates/index.html
└── static/style.css
```

## Ushka Guard is on

Everything that comes from the client (query string, form fields, JSON,
headers, cookies, path parameters, text body) arrives as an `Untrusted` string.
It behaves like a normal `str`, but the places where it could do harm refuse it:

| Sink | Error |
| --- | --- |
| HTML response body | [USHKA-G001](guard.md#ushka-g001) |
| The `safe` filter in a template | [USHKA-G002](guard.md#ushka-g002) |
| `redirect()` target | [USHKA-G003](guard.md#ushka-g003) |
| File-system path | [USHKA-G004](guard.md#ushka-g004) |
| Raw SQL string | [USHKA-G005](guard.md#ushka-g005) |

The way out is a sanitiser from `ushka.guard.safe` (`safe.url`, `safe.path`,
`safe.integer`, `safe.choice`, `safe.html`, `safe.trust`). When a sanitiser
rejects a value the client gets **400 Bad Request**. Every example in this guide
follows these rules; read [Ushka Guard](guard.md) for the full story.

## Contents

* **[Configuration](configuration.md):** `ushka.toml`, `.env`, environment variables and every setting.
* **[Routing](routing.md):** filesystem routes, decorators, path parameters and return values.
* **[Templates](templates.md):** Jinja2 rendering, filters, globals and context processors.
* **[Static Files](static_files.md):** serving CSS, JavaScript and images.
* **[ORM](orm.md):** async models, queries and migrations.
* **[CLI](cli.md):** `ushka new`, `dev`, `run`, `check`, `routes` and `db`.
* **[Dependency Injection](dependency_injection.md):** what a handler can ask for.
* **[Flashing](flashing.md):** one-time messages between requests.
* **[Error Handling](error_handling.md):** HTTP errors, custom error pages and debug mode.
* **[Ushka Guard](guard.md):** untrusted data, sinks and sanitisers.

Prefer to learn by building? Try the [Simple API tutorial](tutorial_simple_api.md).
