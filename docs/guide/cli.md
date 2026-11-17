# Command-Line Interface

Installing Ushka gives you the `ushka` command. It is built on the standard
library (`argparse`), so it adds no dependencies.

<!-- termynal -->
```console
$ ushka --help
usage: ushka [-h] [-V] <command> ...

Ushka: the web framework where untrusted data cannot slip through.

positional arguments:
  <command>
    new          create a new project
    dev          development server (reload, debug on)
    run          production server
    check        validate configuration and security settings
    verify       attack your own routes with hostile payloads and report what
                 got through
    session      print a forged session cookie (name=value) to test as a
                 logged-in user
    docs         check or preview Markdown docs (needs ushka[docs])
    routes       list and manage filesystem routes
    db           database migrations (needs ushka[orm])

options:
  -h, --help     show this help message and exit
  -V, --version  show program's version number and exit
```

Every command has its own `--help` (`ushka dev --help`, `ushka db make --help`).
`ushka --version` prints the installed version. Errors are printed with a short
explanation and exit with status 1.

Run the commands from your project directory: `dev`, `run`, `check`, `routes`
and `db` read `ushka.toml`, `.env`, `routes/` and `app.py` from there.

## `ushka new`

```bash
ushka new my_project
```

Creates `my_project/` with a runnable, secure-by-default layout:

| File | Contents |
| --- | --- |
| `app.py` | `app = Ushka()` and `app.run()` under `__main__`. |
| `ushka.toml` | App name, `debug = false`, a SQLite URL and static files on. |
| `.env` | A freshly generated `USHKA_APP_SECRET_KEY`. |
| `.env.example` | The same keys, empty, safe to commit. |
| `.gitignore` | Excludes `.env`, `*.db`, caches and virtualenvs. |
| `AGENTS.md` | Rules for AI coding agents working on the project (layout, Ushka Guard, sanitisers). |
| `routes/index.py` | `GET /`, rendering the template. |
| `templates/index.html` | The welcome page. |
| `static/style.css` | Its stylesheet. |

The name must start with a letter and contain only letters, digits, `-` and
`_` (up to 64 characters). The command refuses to overwrite an existing
directory.

## `ushka dev`

```bash
ushka dev                          # serves app:app
ushka dev --host 0.0.0.0 --port 5000
ushka dev myapp.main:application   # another module:attribute
```

```text
usage: ushka dev [-h] [--host HOST] [--port PORT] [app]
```

The development server: it reloads when your code changes and turns
**debug on** (it sets `USHKA_APP_DEBUG=true` for the process), so you get the
debug error page and a per-process secret key if you have none. Host and port
default to `[server] host` and `port` (`127.0.0.1:8000`).

## `ushka run`

```bash
ushka run
ushka run --host 0.0.0.0 --port 8080
```

```text
usage: ushka run [-h] [--host HOST] [--port PORT] [app]
```

The production server: no reload, debug taken from your configuration, and
`[server] workers` worker processes:

```toml
# ushka.toml
[server]
host = "0.0.0.0"
port = 8080
workers = 4
```

It warns when debug is on or when `USHKA_APP_SECRET_KEY` is missing. Run
`ushka check --production` before deploying to turn those warnings into a
failing check.

`ushka run` uses Ushka's own server loop on top of Uvicorn (`uvloop` and
`httptools` included), which stays asleep when idle and does not kill workers
that are slow to start. See [Performance](performance.md#idle-cost) and
[Deploy](deploy.md).

## `ushka verify`

```console
ushka verify app:app
ushka verify app:app --include-writes --param q --json --fail-on high
```

Sends hostile payloads to your own routes, in the process, and reports what got
through. Exits 1 on findings, so it fits in CI. Routes exempt from CSRF are
probed too (`--skip-exempt` leaves them out), and `--as-session uid=1` probes as
a logged-in user. See [ushka verify](verify.md).

## `ushka session`

```console
$ ushka session --set uid=1 --set admin=true
_ushka_session=eyJ1aWQiOjEsImFkbWluIjp0cnVlfQ.1763300000.4f0c...
$ curl -H "Cookie: $(ushka session --set uid=1)" http://localhost:8000/account
```

Prints `name=value`, a session cookie signed with the app's own secret key, to
paste into `curl --cookie` or a test client. `--set KEY=VALUE` is repeatable and
`1` and `true` become an integer and a boolean (everything else is text);
`--app module:attribute` names the app (default `app:app`). With
`[session] store = "database"` it also writes the session to the store, so use a
test database. In code, the same thing is `ushka.sessions.forge_session_cookie`
(see [Sessions](sessions.md#forging-a-session-for-tests)).

This is a **testing tool**: whoever runs it holds the key to every account. So it
only signs with a key that comes from the environment or `.env` (there is no way
to type the key on the command line), refuses when `debug` is off unless you pass
`--allow-non-debug`, and prints nothing but the cookie.

## `ushka i18n`

```console
ushka i18n extract     # write locale/messages.pot from _() calls and {% trans %}
ushka i18n compile     # compile every locale/*/LC_MESSAGES/*.po to .mo
```

Both read `[i18n] catalog_dir` and `domain`; `compile` exits 1 when a `.po` is
invalid. See [Internationalisation](i18n.md).

## `ushka check`

```bash
ushka check
ushka check --production
```

Prints the main settings with the layer each one came from (all of them are in
[`ushka config`](#ushka-config)), then checks the project, including mistakes in
`ushka.toml`:

```text
◆ Ushka 0.7.0 · checking /home/me/hello

  Settings
  · app_debug = False  [ushka.toml]
  · app_secret_key = (set)  [.env]
  · database_url = 'sqlite:///hello.db'  [ushka.toml]
  · security_taint = True  [default]
  · server_host = '127.0.0.1'  [default]
  · server_port = 8000  [default]
  · static_enable = True  [ushka.toml]

  Checks
  ✓ ushka.toml found
  ✓ Ushka Guard is on
  ✓ .env is git-ignored
  ✓ 1 route file(s) in routes/
  ✓ Python 3.14.0: t-strings available

  ✓ all good
```

It reports a problem when:

* `ushka.toml` contains `secret_key` (it belongs in `.env`);
* [Ushka Guard](guard.md) is turned off (`[security] taint = false`);
* `.env` exists but is not listed in `.gitignore`;
* with `--production`: debug is on, or the secret key is missing, only
  generated for debug, or shorter than 32 characters.

The command exits with status 1 when it finds a problem, so it works as a CI
step or a pre-deploy gate:

```yaml
# .github/workflows/deploy.yml (excerpt)
- run: ushka check --production
  env:
    USHKA_APP_SECRET_KEY: ${{ secrets.USHKA_APP_SECRET_KEY }}
```

## `ushka config`

```bash
ushka config                  # every setting, its value and where it came from
ushka config security         # one section
ushka config --describe       # plus what each does and its environment variable
ushka config --template       # a complete, annotated ushka.toml
```

Lists **every** setting Ushka reads (see [Configuration](configuration.md#all-settings)),
with the layer each value came from: `default`, `ushka.toml`, `.env` or
`environment`. Secrets show only `(set)` or `(not set)`. It exits with status 1 and
names the key when `ushka.toml` has a key Ushka does not know or a value of the
wrong type, so it also works in CI.

## `ushka docs`

Needs `pip install "ushka[docs]"`. Works on any folder of Markdown, not only
Ushka's:

```bash
ushka docs check docs --api myproject    # exit 1 on broken links, anchors or nav
ushka docs serve docs                    # preview at http://127.0.0.1:8001/docs/
```

`--api PACKAGE` also builds the API reference from that package's docstrings
(`--api-path`, default `src`), and `serve` takes `--host` and `--port`. See
[Ushka Docs](docs.md).

## `ushka routes`

```bash
ushka routes list                        # every registered route
ushka routes add /users                  # creates routes/users.py
ushka routes add "/users/[user_id]"      # creates routes/users/[user_id].py
ushka routes mv /users/profile /account  # moves the file
ushka routes rm /account                 # deletes routes/account.py
```

`list` imports your app (`app:app` by default, or pass `module:attribute`) and
prints each path with its methods:

```text
◆ 2 route(s)
  · / - GET
  · /static/[path:filename] - GET
```

`add`, `rm` and `mv` map URLs to files the same way the
[router](routing.md#filesystem-routes) does: `/` is `routes/index.py`,
`/users/[user_id]` is `routes/users/[user_id].py`. New files contain a small
`get` handler. Segments may use letters, digits, `-`, `_`, `.`, or a parameter
like `[user_id]` or `[path:rest]`; `..` and anything else is rejected, so the
command cannot touch files outside `routes/`.

!!! tip
    Quote paths that contain brackets. Shells such as zsh treat `[...]` as a
    pattern and fail with "no matches found" otherwise.

## `ushka db`

Database migrations with Alembic. Needs the ORM extra:

```bash
pip install "ushka[orm]"
```

| Command | What it does |
| --- | --- |
| `ushka db init` | Creates `migrations/` and `alembic.ini` (once per project). |
| `ushka db make [-m MESSAGE]` | Generates a migration from your model changes. Without `-m`, the message is `auto_<timestamp>`. |
| `ushka db migrate` | Applies all pending migrations. |
| `ushka db revert [revision]` | Reverts one step (default `-1`), to `base` (everything) or to a revision id. |
| `ushka db history` | Lists all migrations. |
| `ushka db status` | Shows the revision the database is at. |
| `ushka db inspect [--url URL] [--table NAME ...] [--schema NAME] [--write FILE [--force]]` | Reads an existing database and writes Ushka models for it, with `TODO` comments and warnings for what the database does not say (Python-side defaults, timestamps, `ON DELETE`). Code goes to stdout (warnings to stderr) or to `FILE`. |
| `ushka db check-models [--url URL] [--schema NAME] [--models MODULE ...]` | Compares the app's models with the database; exit status 1 when they differ. |

A typical session:

```bash
ushka db init
ushka db make -m "create users"
ushka db migrate
```

The migrations use the same database URL as the app (`[database] url`,
`USHKA_DATABASE_URL` or `DATABASE_URL`) and find your models by importing
`app.models`, `app` or `main`. See [ORM](orm.md#creating-the-tables-migrations).
For a database another ORM created, start with `ushka db inspect`: see
[Existing databases](orm.md#existing-databases).
