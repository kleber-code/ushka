# Ushka ฅ^•ﻌ•^ฅ

**Ushka is the Python web framework where insecure code, whether you or an AI
wrote it, does not run silently. It stops and tells you how to fix it.**

It is an async framework with filesystem routing, built on three principles:

- **Low dependency.** The core needs only `uvicorn`, `jinja2` and `python-multipart`. Config, `.env`, the CLI, terminal colours and the guard use the standard library.
- **Batteries included.** Routing, templates, sessions, flash messages, uploads, an ORM with migrations (`ushka[orm]`), a project generator and a security checker.
- **Lightweight in concept.** One idea per feature. A route is a file, a setting is a key, and an unsafe value is a type.

```python
# routes/hello.py
async def get(request):
    name = request.query.get("name", "friend")   # Untrusted
    return t"<h1>Hello, {name}!</h1>"           # Python 3.14: escaped HTML
```

## Start here

- [Why Ushka changed](why-ushka-changed.md): the purpose behind 0.5.
- [Introduction](guide/index.md): install it and build your first app.
- [Ushka Guard](guide/guard.md): untrusted data, sinks and sanitisers.
- [CLI](guide/cli.md): `ushka new`, `dev`, `check` and friends.

Coding agents can read [`llms.txt`](llms.txt) for a compact map of the docs.
