# Ushka Guard

![Ushka holding up her shield](../assets/stickers/shield.webp){ .ushka-sticker width="190" height="231" }

Ushka Guard makes untrusted data a **type**. Everything that comes from outside
your program arrives as an `Untrusted` string, and the places where such a
string could do harm refuse it with an error that says what the risk is and how
to fix it.

It exists because most injection bugs, whether a person or an AI assistant
wrote the code, are the same mistake: a value from the request goes straight
into HTML, a redirect, a file path or a SQL string. With the guard on, that
mistake stops the request in development instead of shipping silently.

```python
# routes/login.py
from ushka.guard import safe
from ushka.http import redirect

async def get(request):
    # redirect(request.query["next"])         -> UnsafeValueError USHKA-G003
    return redirect(safe.url(request.query.get("next"), allow=["/"], default="/"))
```

The guard is **on by default**. It is defence in depth, not a proof: read
[What it does not cover](#what-it-does-not-cover). To find the places where it would
refuse your code before a visitor does, run [`ushka verify`](verify.md). To use it in
FastAPI, Starlette or Django, see [Ushka Guard on other frameworks](guard-frameworks.md).

## Sources: what is untrusted

| Source | Example | `source` label |
| --- | --- | --- |
| Query string | `request.query["q"]` | `query:q` |
| Form fields (urlencoded and multipart) | `(await request.form())["name"]` | `form:name` |
| JSON body (every string, keys included) | `(await request.json())["name"]` | `json` |
| Text body | `await request.text()` | `body` |
| Headers | `request.headers["user-agent"]` | `header:user-agent` |
| Cookies | `request.cookies["theme"]` | `cookie:theme` |
| Path parameters | `item_id` in `/items/[item_id]` | `path:item_id` |
| Language-model output | `guard.llm(reply.text)` | `llm` |

`Untrusted` is a subclass of `str`. Comparing, hashing, slicing, `len()`,
`json.dumps()` and database parameters all work as before.

### Model output is untrusted too

Text produced by a language model can carry a prompt-injection payload from
any page or document the model read. OWASP lists this as
[LLM05: Improper Output Handling](https://genai.owasp.org/llmrisk/llm052025-improper-output-handling/).
Mark it, and the same sinks protect you:

```python
from ushka import guard

answer = guard.llm(response.content[0].text, model="claude")
return "<html>" + answer + "</html>"   # -> USHKA-G001 instead of stored XSS
```

## Sinks: what refuses untrusted data

### USHKA-G001

**Untrusted text served as HTML.** A handler returned a string built from an
untrusted value with an HTML media type, either explicit or detected from
`<html` / `<!DOCTYPE html>`.

Fix: render a template (Jinja2 escapes automatically), return a t-string on
Python 3.14+ (see [t-strings](#t-strings-python-314)), or escape the value with
`safe.html(value)`. Untrusted text served as `text/plain` or inside JSON is fine.

### USHKA-G002

**`|safe` on untrusted data in a template.** `{{ value|safe }}` disables
escaping, which is the classic way XSS returns to an autoescaped template.

Fix: drop `|safe`, or sanitise the value before passing it to the template.

### USHKA-G003

**Untrusted redirect target** (open redirect, phishing).

Fix: `redirect(safe.url(value, allow=["/"], default="/"))`.

### USHKA-G004

**Untrusted file-system path** (path traversal).

Fix: `safe.path(value, root=UPLOAD_DIR)`.

### USHKA-G005

**Untrusted raw SQL** (SQL injection), refused by `db.execute()` and `db.text()`.

Fix: bound parameters, `db.text("SELECT * FROM users WHERE id = :id", id=value)`,
or a t-string on Python 3.14+: `await db.execute(t"SELECT * FROM users WHERE id = {value}")`.
The ORM methods (`User.filter(name=value)` and so on) always bind parameters
and need no change.

## Sanitisers: the way out

Each function in `ushka.guard.safe` validates its input for one purpose and
returns a plain, trusted value. If the input cannot be made safe it raises
`RejectedValueError`, which Ushka answers with **400 Bad Request**, or it
returns `default=` when you pass one.

| Function | Use |
| --- | --- |
| `safe.url(v, allow=["/"], default=...)` | Redirect targets. `"/"` accepts same-site paths; `"https://host"` accepts that exact origin. Rejects `//host`, `/\host`, `javascript:` and control characters. |
| `safe.path(v, root, default=...)` | File names inside `root`, with symlinks and `..` resolved. |
| `safe.integer(v, min=, max=, default=...)` | Numbers. |
| `safe.choice(v, options, default=...)` | Sort orders, column names, enums. Returns *your* object, never the client's string. |
| `safe.html(v)` | Escape for HTML text and quoted attributes. |
| `safe.trust(v, reason="...")` | Explicit escape hatch. The reason is mandatory so it shows up in review and in `grep "trust("`. |

## t-strings (Python 3.14+)

[PEP 750](https://peps.python.org/pep-0750/) template strings keep the parts
you wrote separate from the interpolated values, so HTML and SQL become safe
**by construction**, with no tracking involved:

```python
async def get(request):
    return t"<h1>Hello {request.query['name']}</h1>"   # escaped, served as text/html

rows = await db.execute(t"SELECT * FROM users WHERE name = {name}")  # bound
```

`ushka.guard.templates.html()` and `.sql()` are available for use anywhere.
`html()` escapes for text and quoted attributes. It does not parse the markup,
so validate URLs placed in `href`/`src` with `safe.url()`.

## Errors for humans and for agents

Every `UnsafeValueError` has a stable `code`, the `sink`, the `source`, the
`risk`, a concrete `fix` and a `docs` link. In debug mode, a request that sends
`Accept: application/json` gets the error as JSON, so a coding agent can fix
the code on the next try:

```json
{"error": "unsafe_value", "code": "USHKA-G003", "sink": "redirect()",
 "source": "query:next", "risk": "open redirect / phishing",
 "fix": "redirect(safe.url(value, allow=[\"/\"], default=\"/\"))",
 "docs": "https://ushka.satela.com.br/docs/guide/guard/#ushka-g003"}
```

In production the client only sees a generic 500. The details go to the log,
with control characters removed so a crafted parameter name cannot forge log
lines.

## What it does not cover

CPython builds some strings in C without asking the operands, so the mark is
lost in **multi-part f-strings**, `"Hi {}".format(x)`, `"%s-%s" % (a, b)`,
`", ".join([x])` and `str(x)`.

Ushka closes these gaps by **rewriting them at compile time** in the files it
loads from `routes/`. For your own packages (for example, handlers registered
with decorators), opt in before importing them:

```python
from ushka.guard import rewrite
rewrite.install(["myapp"])   # only your packages; never the stdlib
```

These cases stay outside the guard:

- **Bytes.** `.encode()` drops the mark.
- **Sessions.** Values stored in the signed session come back as plain strings.
- **Third-party packages.** Code that builds strings internally drops the mark, `sqlalchemy.text()` included. Use `db.text()` instead.
- **`markupsafe.Markup(value)`.** Calling it directly bypasses G002.
- **`open()` and `pathlib`.** They do not check the mark. Use `safe.path()`.

Treat the guard as a seat belt, not as a reason to skip review.

## Turning it off

```toml
# ushka.toml
[security]
taint = false
```

This exists to help migrate an existing app; it is not meant as a permanent
mode. With it off, request values are plain `str` and `routes/` files are
compiled without the rewrite.

`ushka.guard` does not import the rest of Ushka, and will also ship as a
standalone package for other frameworks.
