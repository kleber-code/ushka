"""``ushka new``: scaffolds a project that is secure and runnable from the start."""

from __future__ import annotations

import re
import secrets
from pathlib import Path

from ushka.cli import ui
from ushka.core.settings import toml_value

_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")

APP_PY = '''\
from ushka import Ushka

app = Ushka()
# @app.middleware  # one decorator adds a middleware: async def mw(request, call_next)

if __name__ == "__main__":
    app.run()
'''

USHKA_TOML = """\
# Only what differs from the defaults is here. `ushka config` lists the settings,
# `ushka config --template` prints every key, annotated. Secrets go in .env.
[app]
name = {name}
debug = false

[database]
url = {url}

[static]
enable = true
"""


def ushka_toml(name: str) -> str:
    """The ``ushka.toml`` of a new project: a few lines, not every setting."""
    return USHKA_TOML.format(name=toml_value(name), url=toml_value(f"sqlite:///{name}.db"))


DOTENV = '''\
# Local secrets. Never commit this file (.gitignore already excludes it).
USHKA_APP_SECRET_KEY={secret}
'''

DOTENV_EXAMPLE = '''\
# Copy to .env and fill in. Generate a key with:
#   python -c "import secrets; print(secrets.token_urlsafe(48))"
USHKA_APP_SECRET_KEY=
'''

GITIGNORE = '''\
.env
__pycache__/
*.py[cod]
*.db
.venv/
venv/
'''

INDEX_ROUTE = '''\
from services.greeting import greeting
from ushka.templating import render


async def get(request):
    # A route is thin: read the request, call a service, render. The rules live in services/.
    # Everything from the request is `Untrusted`; templates escape it for you.
    name = request.query.get("name", "friend")
    return await render(request, "index.html", {"message": greeting(name)})
'''

GREETING_SERVICE = '''\
"""Greetings: an example of a service.

A service holds the rules of one domain as plain functions. It knows nothing about
HTTP: no `request`, no templates, no `redirect`. That keeps it testable with a plain
call, and lets routes, background tasks and scripts share it.
"""


def greeting(name: str) -> str:
    return f"Hello, {name}!"
'''

PACKAGE_INITS = {
    "models/__init__.py": '"""ORM models, one module per domain (models/billing.py), imported here so migrations see them."""\n',
    "services/__init__.py": '"""Business rules, one module per domain (services/billing.py). No HTTP in here."""\n',
    "integrations/__init__.py": '"""Everything that talks to the outside: one module per vendor (integrations/stripe.py)."""\n',
}

TEST_INDEX = '''\
import asyncio

from app import app
from services.greeting import greeting
from ushka.testing import TestClient


def test_greeting_service():
    assert greeting("Ada") == "Hello, Ada!"


def test_home_page():
    async def run():
        async with TestClient(app) as client:
            res = await client.get("/?name=Ada")
            assert res.status_code == 200 and "Hello, Ada!" in res.text

    asyncio.run(run())
'''

PYTEST_INI = '''\
[pytest]
pythonpath = .
testpaths = tests
'''

INDEX_TEMPLATE = '''\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    {{ seo() }}
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <main>
        <h1>{{ message }}</h1>
        <p>Edit <code>routes/index.py</code>, <code>services/greeting.py</code> and <code>templates/index.html</code> to get started.</p>
    </main>
</body>
</html>
'''

STYLE_CSS = '''\
body { font-family: system-ui, sans-serif; background: #fff7fb; color: #3b2a35;
       display: grid; place-items: center; min-height: 100vh; margin: 0; }
main { text-align: center; }
h1 { color: #2b1e3a; }
code { background: #fde4f0; padding: .1rem .35rem; border-radius: .3rem; }
'''

AGENTS_MD = '''\
# AGENTS.md

{name} uses **Ushka**, an async Python web framework with filesystem routing and
**Ushka Guard** (request data is `Untrusted`; dangerous sinks refuse it).

## Layout

Only `app.py` and config in the root. Code goes in folders by role, one module per
domain (billing, leads...) in each:

- `routes/`: one file per URL (`routes/users/[user_id].py` → `/users/<user_id>`),
  async functions named after the method: `async def get(request)`. Keep them thin:
  read the request, call a service, return a response.
- `services/`: business rules as plain functions. No `request`, no templates, no `redirect`.
- `models/`: ORM models, imported in `models/__init__.py`. `integrations/`: one module per
  outside vendor. `deps/`: `Depends` functions. `templates/`: Jinja2, autoescaped.
- `static/`, `locale/`, `migrations/`, `scripts/`, `tests/` (mirrors the folders above).
- `ushka.toml`: settings, no secrets; your own go in a `[{name}]` section. `.env`: secrets.

## Where does new code go?

- A URL → `routes/`. A rule or workflow → `services/<domain>.py`. A table → `models/<domain>.py`.
  An outside call → `integrations/<vendor>.py`, called by a service.
- Imports flow `routes` → `services` → `models` / `integrations`. Never a `.py` in the root;
  name files after the domain, not `utils`/`helpers`; split a file over ~500 lines.
- Middleware: `@app.middleware`. `ushka check` warns when the layout drifts.

## Rules

- `request.query`, `form()`, `json()`, headers, cookies and path parameters are `Untrusted`.
  Do not bypass the guard; use `from ushka.guard import safe`:
  `redirect(safe.url(v, allow=["/"], default="/"))`, `safe.path(v, root=...)`,
  `safe.integer(v, min=, max=)`, `safe.choice(v, [...])`.
  HTML: render a template, never `|safe` on request data. SQL: ORM or `db.text("... :id", id=v)`.
- Mark language-model output with `guard.llm(text)`.
- An `UnsafeValueError` (`USHKA-G00x`) names the fix: apply it, do not silence it.
  https://ushka.satela.com.br/docs/guide/guard/

## Commands

`ushka dev` (reload) · `ushka check` · `ushka config` (settings and their source) · `ushka routes list`
'''


def create_project(project_name: str) -> None:
    """Creates `project_name/` with a runnable, secure-by-default layout."""
    if not _NAME.match(project_name):
        ui.fail(
            f"Invalid project name {project_name!r}. Use letters, digits, '-' or '_', "
            "starting with a letter."
        )
    root = Path(project_name)
    if root.exists():
        ui.fail(f"Directory '{project_name}' already exists.")

    ui.title(f"Creating {project_name}")
    files = {
        "app.py": APP_PY,
        "ushka.toml": ushka_toml(project_name),
        ".env": DOTENV.format(secret=secrets.token_urlsafe(48)),
        ".env.example": DOTENV_EXAMPLE,
        ".gitignore": GITIGNORE,
        "AGENTS.md": AGENTS_MD.format(name=project_name),
        "routes/index.py": INDEX_ROUTE,
        "services/greeting.py": GREETING_SERVICE,
        **PACKAGE_INITS,
        "templates/index.html": INDEX_TEMPLATE,
        "static/style.css": STYLE_CSS,
        "tests/test_index.py": TEST_INDEX,
        "pytest.ini": PYTEST_INI,
    }
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        ui.ok(rel)

    ui.line()
    ui.line("  Next steps:")
    ui.info(ui.code(f"cd {project_name}"))
    ui.info(ui.code("ushka dev"))
