# Ushka ฅ^•ﻌ•^ฅ

[![PyPI Version](https://img.shields.io/pypi/v/ushka)](https://pypi.org/project/ushka/)
[![Documentation](https://img.shields.io/badge/docs-kleber--code.github.io%2Fushka-pink)](https://kleber-code.github.io/ushka/)
![Python Versions](https://img.shields.io/pypi/pyversions/ushka)
![License](https://img.shields.io/pypi/l/ushka)

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
[Why Ushka changed](https://kleber-code.github.io/ushka/why-ushka-changed/).

## What's in the box

- **Ushka Guard**:
  - **Untrusted by default.** Query, form, JSON, headers, cookies and path parameters are `Untrusted`, and so is model output once marked with `guard.llm()`.
  - **Guarded sinks.** HTML, redirects, file paths and raw SQL refuse those values.
  - **Sanitisers and errors.** The way out is through explicit sanitisers. Errors give the risk and the fix, as text and as JSON for coding agents.
- **Python 3.14 t-strings.** `t"<h1>{name}</h1>"` and `db.execute(t"... {id}")` are safe by construction.
- **Routing.** Filesystem routing (`routes/users/[user_id].py`) plus decorators (`@app.get(...)`).
- **Responses.** Return a `str`, a `dict`, a `(body, status)` tuple, `None` (204) or a `Response`. `HEAD` and `405 Allow` are handled for you.
- **Data, sessions and templates:**
  - Async Active Record ORM on SQLAlchemy, with migrations in `ushka db` (extra `ushka[orm]`).
  - Jinja2 templates, signed sessions, cookies, flash messages, file uploads and request size limits.
- **Config.** Defaults, then `ushka.toml`, then `.env`, then environment variables, all without extra packages. `DATABASE_URL` works out of the box.
- **CLI.** `new`, `dev`, `run`, `check` (CI-friendly security check), `routes` and `db`.
- **Low dependency.** The core needs only `uvicorn`, `jinja2` and `python-multipart` (plus `tomli` on 3.10).

## Quick start

```bash
pip install ushka
ushka new hello
cd hello
ushka dev
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
```

## Documentation

Guides, the Ushka Guard reference and the API reference are at
**https://kleber-code.github.io/ushka/**. For AI tools there is
[`llms.txt`](https://kleber-code.github.io/ushka/llms.txt).

## Contributing

Bug reports, ideas and pull requests are welcome. See the
[contributing guidelines](https://github.com/kleber-code/ushka/blob/main/.github/CONTRIBUTING.md)
and the [security policy](https://github.com/kleber-code/ushka/blob/main/SECURITY.md).

## License

[MIT](https://github.com/kleber-code/ushka/blob/main/LICENSE)
