"""``ushka new``: scaffolds a project that is secure and runnable from the start."""

from __future__ import annotations

import re
import secrets
from pathlib import Path

from ushka.cli import ui
from ushka.core.settings import render_toml

_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")

APP_PY = '''\
from ushka import Ushka

app = Ushka()

if __name__ == "__main__":
    app.run()
'''

USHKA_TOML_HEADER = """\
# Ushka configuration for {name}.
#
# EVERY setting Ushka reads is listed below with its default and what it does,
# so nothing is hidden: change a value here, or override it without touching
# this file with an environment variable (or a line in .env) named
# USHKA_<SECTION>_<KEY>, for example USHKA_APP_DEBUG=true.
# Order of precedence: defaults < ushka.toml < .env < environment.
#
# Secrets never go here: the session key lives in .env (USHKA_APP_SECRET_KEY).
# `ushka config` shows the values in use and where each came from;
# `ushka check` validates them. Reference: https://ushka.satela.com.br/docs/guide/configuration/
"""


def ushka_toml(name: str) -> str:
    """The complete ``ushka.toml`` of a new project: every setting, annotated."""
    return render_toml(
        {
            "app": {"name": name, "debug": False},
            "database": {"url": f"sqlite:///{name}.db"},
            "static": {"enable": True},
            "seo": {"description": f"{name}, built with Ushka."},
        },
        header=USHKA_TOML_HEADER.format(name=name),
    )


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

Instructions for AI coding agents working on this {name} project.
It uses **Ushka**, an async Python web framework with filesystem routing and
**Ushka Guard** (request data is `Untrusted`; dangerous sinks refuse it).

## Layout

The root holds `app.py` and config only. Code goes in folders by role, and each
domain (billing, leads, accounts...) is one module in each folder that needs it:

- `routes/` — the web layer, one file per URL (`routes/index.py` → `/`,
  `routes/users/[user_id].py` → `/users/<user_id>`). Export async functions named
  after HTTP methods: `async def get(request): ...`. **Keep handlers thin**: read the
  request, call a service, return a response. One host name with its own routes
  gets `routes_<name>/` and an entry in `[routes] hosts`.
- `services/` — business rules as plain functions, one module per domain
  (`services/billing.py`). **No `request`, no templates, no `redirect` in here.**
- `models/` — ORM models, one module per domain (`models/billing.py`), imported in
  `models/__init__.py`. Never one big `models.py`.
- `integrations/` — everything that talks to the outside world, one module per
  vendor (`integrations/stripe.py`): the client and the webhook signature check.
- `deps/` — `Depends` functions (current user, permissions), one concern per file.
- `templates/` — Jinja2, autoescaped, grouped by area (`templates/billing/invoice.html`);
  `render(request, "billing/invoice.html", {{...}})` from `ushka.templating`.
- `static/` (served at `/static/`), `locale/`, `migrations/`, `scripts/` (one-off
  tools), `tests/` (mirrors the folders above).
- `ushka.toml` — settings (no secrets); your own settings go in a section of your
  own (`[{name}]`), not in a config module. `.env` — secrets, not committed.

## Where does new code go?

- A new URL → a file in `routes/`, calling a service.
- A rule, calculation or workflow → a function in `services/<domain>.py`.
- A table → `models/<domain>.py`.
- A call to an outside system → `integrations/<vendor>.py`, called by a service.
- Never add a `.py` file to the root, and name files after the domain (`billing`,
  `leads`), never after a grab-bag (`utils`, `helpers`, `core`, `manager`).
- Direction of imports: `routes` → `services` → `models` / `integrations`. A service
  never imports a route or `ushka.http`.
- A file over about 500 lines is more than one domain: split it.
- `ushka check` warns when the layout drifts.

## Rules

- Values from `request.query`, `form()`, `json()`, headers, cookies and path
  parameters are `Untrusted`. Do not bypass the guard; use a sanitiser:
  - redirect: `redirect(safe.url(value, allow=["/"], default="/"))`
  - file path: `safe.path(value, root=...)`
  - numbers: `safe.integer(value, min=..., max=...)`
  - fixed options (sort column...): `safe.choice(value, [...])`
  - HTML: render a template; never `|safe` on request data.
  - SQL: ORM methods, or `db.text("... :id", id=value)`; never build SQL strings.
  `from ushka.guard import safe`.
- Mark language-model output with `guard.llm(text)` before using it.
- An `UnsafeValueError` (`USHKA-G00x`) explains the risk and the fix: apply
  the fix, do not silence it. Docs: https://ushka.satela.com.br/docs/guide/guard/

## Commands

- `ushka dev` — development server with reload (debug on).
- `ushka check` — validate configuration and security settings.
- `ushka config` — every setting, its value and where it came from.
- `ushka routes list` — show all routes.
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
