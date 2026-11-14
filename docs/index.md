---
title: Ushka
template: home.html
hide:
  - navigation
  - toc
---

# Ushka { .ushka-home-heading }

## Untrusted data is a type

Everything from outside your program arrives as `Untrusted`: query, form,
JSON, headers, cookies, path parameters, and model output marked with
`guard.llm()`. HTML responses, `|safe`, redirects, file paths and raw SQL
refuse it, and the error tells you the fix.

```python
# routes/login.py
from ushka import redirect, safe

async def get(request):
    target = request.query.get("next", "/")
    # redirect(target)  -> USHKA-G003 open redirect, with the fix
    return redirect(safe.url(target, allow=["/"], default="/"))
```

On Python 3.14, t-strings make HTML and SQL safe by construction:

```python
async def get(request):
    return t"<h1>Hello, {request.query['name']}!</h1>"   # escaped
```

## Small core, full box

- **Low dependency.** The core needs only `uvicorn`, `jinja2` and `python-multipart`.
- **Batteries included.** Filesystem routing, templates, sessions, flash
  messages, uploads, an ORM with migrations, a project generator and
  `ushka check` for your CI.
- **Lightweight in concept.** A route is a file, a setting is a key, and an
  unsafe value is a type.

## Where to go next

- [Why Ushka changed](why-ushka-changed.md) explains the purpose behind 0.5.
- [Introduction](guide/index.md) gets you from `pip install` to a running app.
- [Ushka Guard](guide/guard.md) covers sources, sinks, sanitisers and error codes.
- [CLI](guide/cli.md) documents `ushka new`, `dev`, `check` and the others.

Coding agents can read [`llms.txt`](llms.txt), a compact map of these docs.
