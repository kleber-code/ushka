<p align="center">
  <img src="https://raw.githubusercontent.com/kleber-code/ushka/main/docs/assets/hero.webp" width="220" alt="Ushka, the maned-wolf guardian mascot, giving a thumbs up">
</p>

# Ushka

[![PyPI Version](https://img.shields.io/pypi/v/ushka)](https://pypi.org/project/ushka/)
[![Documentation](https://img.shields.io/badge/docs-ushka.satela.com.br-F07A3A)](https://ushka.satela.com.br/docs/)
![Python Versions](https://img.shields.io/pypi/pyversions/ushka)
![License](https://img.shields.io/pypi/l/ushka)

**Website and docs: [ushka.satela.com.br](https://ushka.satela.com.br)**

**Ushka is the Python web framework where insecure code, whether you or an AI
wrote it, does not run silently. It stops and tells you how to fix it.**

It is an async (ASGI) framework with filesystem routing, and it is small on
purpose. It needs few dependencies, but it ships everything a web app needs.
Its main feature is **Ushka Guard**: anything that comes from outside your
program arrives as an `Untrusted` string, and the places where such a string
could do harm refuse it.

```python
# routes/login.py
from ushka.guard import safe
from ushka.http import redirect

async def get(request):
    target = request.query.get("next", "/")      # Untrusted
    # return redirect(target)                    # ✗ USHKA-G003 open redirect, with the fix
    return redirect(safe.url(target, allow=["/"], default="/"))   # ✓
```

## Why

AI assistants write a growing share of web code, and studies keep finding
OWASP Top 10 flaws in
[around 45% of generated samples](https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-codegen-vulnerability-debt-20260406-csa/).
Apps also pass **model output** into HTML, redirects and SQL, where prompt
injection can steer it. Ushka puts the check where it cannot be skipped: in
the framework, at runtime, on your real code. Read
[Why Ushka changed](https://ushka.satela.com.br/docs/why-ushka-changed/).

## What's in the box

- **Ushka Guard**:
  - **Untrusted by default.** Query, form, JSON, headers, cookies and path parameters are `Untrusted`, and so is model output once marked with `guard.llm()`.
  - **Guarded sinks.** HTML, redirects, file paths and raw SQL refuse those values.
  - **Sanitisers and errors.** The way out is through explicit sanitisers. Errors give the risk and the fix, as text and as JSON for coding agents.
- **Security middleware, on by default.** CSRF protection without tokens, CSP, HSTS and `nosniff`, CORS and trusted hosts.
- **Typed parameters and validation.** Annotations convert and validate path, query, header, cookie and JSON bodies (422 with every error), `Depends` as in FastAPI, and OpenAPI generated from the same signatures. No pydantic.
- **Real time.** WebSockets (cross-site hijacking refused) and Server-Sent Events.
- **Routes as agent tools.** Expose chosen routes over MCP with declared capabilities and human approval.
- **`ushka verify`.** Sends attack payloads to your own routes and reports what got through.
- **Guard for FastAPI, Starlette and Django.** The same `Untrusted` protection in an app you already have.
- **Python 3.14 t-strings.** `t"<h1>{name}</h1>"` and `db.execute(t"... {id}")` are safe by construction.
- **Routing.** Filesystem routing (`routes/users/[user_id].py`) plus decorators (`@app.get(...)`).
- **Responses.** Return a `str`, a `dict`, a `(body, status)` tuple, `None` (204) or a `Response`. `HEAD` and `405 Allow` are handled for you.
- **Data, sessions and templates:**
  - Async Active Record ORM on SQLAlchemy, with migrations in `ushka db` (extra `ushka[orm]`).
  - Jinja2 templates, signed sessions, cookies, flash messages, file uploads and request size limits.
- **Config.** Defaults, then `ushka.toml`, then `.env`, then environment variables, all without extra packages. `DATABASE_URL` works out of the box.
- **Static files.** `app.mount_static("/assets", "public")` serves any folder, with `ETag`/`304` and your choice of `Cache-Control`.
- **Ushka Docs.** A Markdown folder becomes a searchable docs site with an API reference, served by your app (`ushka[docs]`), with a cache you can build into your Docker image.
- **CLI.** `new`, `dev`, `run`, `check` and `verify` (CI-friendly security checks), `docs`, `routes` and `db`.
- **Fast without tuning.** `uvloop` and `httptools` are installed by default (not on Windows or PyPy) and Uvicorn uses them on its own: about **2.3x the requests per second** of the pure-Python stack (the hello route on one worker went from about 3,200 to 7,600), and ahead of FastAPI on the same loop and parser. `ushka run` also stays asleep when idle: about 0.04 s of CPU per minute for two workers.
- **Low dependency.** The core is 9 packages and 20 MB: `uvicorn`, `jinja2`, `python-multipart` and the two accelerators (plus `tomli` on 3.10). The ORM, the docs engine and the database drivers are extras.
- **Ready to deploy.** `ushka check --production` for your CI, settings from environment variables, `[server] workers`, and a [deploy guide](https://ushka.satela.com.br/docs/guide/deploy/) with a Dockerfile.

## Quick start

```bash
pip install ushka        # or: uv add ushka   (Python 3.10+)
ushka new hello
cd hello
ushka dev                # http://127.0.0.1:8000, reloads on change
```

Extras are opt-in: `pip install "ushka[orm]"` (SQLAlchemy and migrations),
`"ushka[postgres]"`, `"ushka[mysql]"` and `"ushka[docs]"`.

Prefer a script? It installs the `ushka` command for your user, with no sudo.
Read it first and check it against the published SHA-256:

```bash
curl -LsSf https://ushka.satela.com.br/install.sh -o install.sh
curl -LsSf https://ushka.satela.com.br/install.sh.sha256 | sha256sum -c -
sh install.sh
```

`ushka new` creates a project that is safe from the first commit:

- `debug = false` in config (`ushka dev` turns debug on by itself)
- a generated secret in `.env`
- a `.gitignore`
- an `AGENTS.md` that teaches coding agents the rules

Or write a single-file app:

```python
from ushka import Ushka

app = Ushka()

@app.get("/greet/[name]")
async def greet(name):
    return f"Hello, {name}!"          # plain text: safe

@app.post("/items")
async def create(request):
    data = await request.json()
    return {"created": data["name"]}, 201

if __name__ == "__main__":
    app.run()
```

Before deploying:

```bash
ushka check --production   # fails (exit 1) on debug on, missing secret, guard off...
ushka verify app:app       # attacks your own routes and reports what got through
ushka run                  # the production server (see "workers" in ushka.toml)
```

## Documentation

Everything is at **https://ushka.satela.com.br/docs/**. The site is built with
Ushka itself, and its docs are rendered by Ushka Docs.

- [Installation](https://ushka.satela.com.br/docs/guide/install/) and the [Quickstart](https://ushka.satela.com.br/docs/guide/quickstart/)
- [Ushka Guard](https://ushka.satela.com.br/docs/guide/guard/), with the error codes `USHKA-G001` to `G005`
- [Validation and typed parameters](https://ushka.satela.com.br/docs/guide/validation/) and the [Security middleware](https://ushka.satela.com.br/docs/guide/security/)
- [Deploy](https://ushka.satela.com.br/docs/guide/deploy/) and [Performance](https://ushka.satela.com.br/docs/guide/performance/)
- [CLI](https://ushka.satela.com.br/docs/guide/cli/), [Configuration](https://ushka.satela.com.br/docs/guide/configuration/) and the API reference

For AI tools there is [`llms.txt`](https://ushka.satela.com.br/llms.txt). The
[changelog](https://github.com/kleber-code/ushka/blob/main/CHANGELOG.md) lists every change.

## Meet Ushka

The mascot is Ushka, a guardian with the ears and tail of a lobo-guará
(maned wolf), Brazil's tall red wolf. Her shield pin is the mint diamond you
see whenever the guard stops something.

## Contributing

Bug reports, ideas and pull requests are welcome. See the
[contributing guidelines](https://github.com/kleber-code/ushka/blob/main/.github/CONTRIBUTING.md)
and the [security policy](https://github.com/kleber-code/ushka/blob/main/SECURITY.md).

## License

[MIT](https://github.com/kleber-code/ushka/blob/main/LICENSE)
