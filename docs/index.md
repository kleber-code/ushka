---
title: Documentation
description: Ushka is an async Python web framework where untrusted data is a type and dangerous sinks refuse it. Start here.
---

# Ushka documentation

![Ushka waving](assets/stickers/waving.webp){ .ushka-sticker width="150" height="182" }

Ushka is an async (ASGI) Python web framework with filesystem routing. Its main
feature is **Ushka Guard**: everything that comes from outside your program is
`Untrusted`, and the places where it could do harm refuse it. Insecure code,
whether you or an AI wrote it, does not run silently. It stops and tells you how
to fix it.

## Untrusted data is a type

Everything from outside arrives as `Untrusted`: query, form, JSON, headers,
cookies, path parameters, and model output marked with `guard.llm()`. HTML
responses, `|safe`, redirects, file paths and raw SQL refuse it, and the error
tells you the fix.

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

- **Low dependency.** The core is nine packages and 20 MB: `uvicorn`, `jinja2`,
  `python-multipart`, and the `uvloop` and `httptools` accelerators.
- **Fast without tuning.** About 2.3x the requests per second of a plain
  asyncio stack, and a server that costs close to nothing when idle.
  See [Performance](guide/performance.md).
- **Batteries included.** Filesystem routing, typed parameters and validation,
  templates, sessions, uploads, WebSockets, an ORM with migrations, a security
  middleware, `ushka verify` and a CLI for your CI.
- **Lightweight in concept.** A route is a file, a setting is a key, and an
  unsafe value is a type.

## Where to go next

- **New here?** [Install](guide/install.md), then the [Quickstart](guide/quickstart.md).
- [Why Ushka changed](why-ushka-changed.md) explains the purpose behind 0.5.
- [Ushka Guard](guide/guard.md) covers sources, sinks, sanitisers and error codes.
- [Deploy](guide/deploy.md) takes your app to production.
- [Features](features.md) is the short tour, and the [guide](guide/index.md) the full one.

Coding agents can read [`llms.txt`](llms.txt), a compact map of these docs.
