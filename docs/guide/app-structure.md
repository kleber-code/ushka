# Application structure

A small app fits in one file. A real one has billing, accounts, payments, a
dashboard and an API, and that is where projects turn into fifty modules in one
folder. Ushka has a layout for it. It is one rule, applied to every folder:

> **The root holds `app.py` and config. Code lives in folders by role, and each
> domain is one module in every folder that needs it.**

`ushka new` creates this layout, its `AGENTS.md` teaches it to coding agents, and
`ushka check` warns when a project drifts from it.

## The layout

```text
shop/
├── app.py                 # app = Ushka(), and nothing else
├── ushka.toml  .env  .env.example  AGENTS.md
├── routes/                # the web layer: one file per URL, thin
│   ├── index.py
│   ├── billing/
│   │   └── invoices/[invoice_id].py
│   └── api/orders.py
├── routes_api/            # only if a host name has its own routes ([routes] hosts)
├── services/              # business rules, one module per domain
│   ├── billing.py
│   └── orders.py
├── models/                # ORM models, one module per domain
│   ├── __init__.py        # imports them all, so migrations see them
│   ├── billing.py
│   └── orders.py
├── integrations/          # the outside world, one module per vendor
│   ├── stripe.py
│   └── whatsapp.py
├── deps/                  # Depends: current user, permissions
│   └── auth.py
├── templates/             # grouped by area: templates/billing/invoice.html
├── static/   locale/   migrations/   scripts/
└── tests/                 # mirrors the folders above
```

| Folder | Holds | Must not |
| --- | --- | --- |
| `routes/` | Reading the request, calling a service, returning a response. | Hold business rules or talk to a vendor directly. |
| `services/` | Rules, calculations and workflows as plain functions. | Use `request`, templates, `redirect` or anything from `ushka.http`. |
| `models/` | Tables. | Import services or routes. |
| `integrations/` | The client of one outside system and its webhook checks. | Be imported by routes (a service calls them). |
| `deps/` | `Depends` functions, one concern per file. | Hold rules; call a service. |

## The rules

1. **No code in the root.** Only `app.py` and configuration. A project with ten
   modules in the root cannot say what any of them is for.
2. **Routes are thin.** Read, call, return. If a handler grows past one screen, the
   rule it contains belongs in a service. A handler that does not need a service
   can stay simple; thin does not mean empty.
3. **Services know nothing about HTTP.** They take plain values and return data, so a
   route, a background task and a script can all call them, and a test needs no
   server.
4. **One domain per module.** `models/billing.py` and `services/billing.py` are the
   same domain in two roles. Never one `models.py` for the whole app.
5. **Name files after the domain**, a noun (`billing`, `leads`, `invoices`), never a
   grab-bag (`utils`, `helpers`, `core`, `manager`, `central`). If you cannot name
   what a file is for, it is several files.
6. **Imports go one way:** `routes` → `services` → `models` and `integrations`. Two
   routes never import each other; if they share logic, it is a service.
7. **Around 500 lines is the limit** for a module. Past it, split by domain.
8. **Settings in `ushka.toml`.** Your own go in a section of your own (`[shop]`), read
   with `app.config.get("shop_currency")`. No `cfg.py` next to `ushka.toml`.
9. **One language for names** inside a project (English or any other), and one
   word per concept: not `invoice`, `fatura` and `bill` for the same thing.

## Where does new code go?

| You are adding | It goes in |
| --- | --- |
| A URL | `routes/<area>/<page>.py`, calling a service |
| A rule, calculation or workflow | `services/<domain>.py` |
| A table or a query on it | `models/<domain>.py` |
| A call to Stripe, WhatsApp, a mail service | `integrations/<vendor>.py`, called by a service |
| "Only for signed-in users" | `deps/auth.py`, used with `Depends` |
| A page layout or partial | `templates/<area>/`, shared parts in `templates/_partials/` |
| A one-off or maintenance script | `scripts/` |
| A job that runs outside a request | `services/` (the rule) and `scripts/` or your scheduler (the trigger) |

## Several host names

When one app answers `www`, `api` and `admin`, each host that has its own routes gets
a `routes_<name>/` folder, declared in `ushka.toml`:

```toml
[routes]
hosts = { "api.*" = "routes_api", "admin.example.com" = "routes_admin" }
```

The folders differ only in the web layer. They call the **same** `services/`,
`models/` and `integrations/`: a rule is written once, whatever the host. See
[Routes per host](routing.md#routes-per-host). `ushka check` warns about a
`routes_*` folder that no host uses, because its routes would never answer.

## How a project grows

You do not start with all of it. Add a layer when the code asks for it:

1. **One file.** `app.py` with `@app.get(...)` handlers. Fine for a script or a demo.
2. **`routes/`.** One file per URL, as soon as there are a handful.
3. **`services/` and `models/`.** When a handler has a rule worth testing, or a second
   route needs the same logic.
4. **`integrations/` and `deps/`.** With the first outside system and the first
   sign-in check.
5. **`routes_<host>/`.** With the second host name.

`ushka new` starts at step 3, with one tiny service and a test, so the habit is there
from the first commit.

## Tidying a project that grew flat

A common state: dozens of modules in the root, one `models.py` of eight hundred lines,
and groups hiding in the file names (`panel.py`, `panel_ai.py`, `panel_client.py`).
Move one domain at a time and run the tests after each:

| You have | Move it to |
| --- | --- |
| `models.py` (everything) | `models/<domain>.py`, one per domain, imported in `models/__init__.py` |
| `billing.py`, `invoicing.py`, `payments.py` (rules) | `services/billing.py`, ... |
| `stripe_client.py`, `whatsapp_gateway.py` | `integrations/stripe.py`, `integrations/whatsapp.py` |
| `panel.py`, `panel_ai.py`, `panel_client.py` | one `services/panel.py`, or a `services/panel/` folder if each is large |
| `deps.py`, `deps_apps.py` | `deps/auth.py`, `deps/apps.py` |
| `cfg.py` | `ushka.toml`, in a section of your own |
| `tools/` | `scripts/` |
| `central.py`, `core.py`, `utils.py` | split into the domain that owns each function; delete the rest |

`ushka check` lists what is left: it names the files that share a prefix (the folders
waiting to exist), the modules over the size limit, and any service that imports HTTP.

## What `ushka check` checks

These are warnings, never errors: a project in another shape still runs. Every number
is in `ushka/cli/commands/structure.py`.

| Warning | When |
| --- | --- |
| Code in the root | More than 5 Python modules besides `app.py` (it also lists the shared prefixes) |
| Module too big | More than 500 lines (the three largest are named) |
| Unused host folder | A `routes_*` folder that no `[routes] hosts` entry uses |
| HTTP in the wrong layer | A file in `services/` or `models/` imports `ushka.http`, `ushka.templating`, `Request`, `render`, `redirect` or a `routes` module |
| Name clash | Your `models/`, `services/`, `integrations/`, `deps/` or `tasks/` has the same name as a package elsewhere on `sys.path` |

## A note on the guard

Client data keeps its `Untrusted` mark when you pass it to a service as it is. String
building (f-strings, `+`) keeps the mark only in `routes/` files, which Ushka rewrites at
compile time; in a service it produces a plain `str`. So decide in the route what the
value may be (`safe.integer`, `safe.choice`, a typed parameter) and hand the service a
value that is already clean. See [What the guard does not cover](guard.md#what-it-does-not-cover).
