# Installation

Ushka needs **Python 3.10 or newer** (3.14 adds t-strings). It runs on Linux,
macOS and Windows.

## Install it

```bash
pip install ushka        # or: uv add ushka
pip install "ushka==0.8.0b5"  # the 0.8 beta (see the note below)
ushka --version
```

That is the whole core. It installs nine packages and about 20 MB:
`uvicorn`, `jinja2` (with `markupsafe`), `python-multipart`, the two accelerators
`uvloop` and `httptools`, and `tomli` on Python 3.10. The accelerators make
Ushka about 2.3 times faster out of the box (see [Performance](performance.md)).
Windows and PyPy have no `uvloop`, so they quietly use the pure-Python loop.

Use a virtual environment, as you would for any project:

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install ushka
```

## Extras

Everything beyond the core is opt-in, so you only install what you use.

| Extra | Adds | Needed for |
| --- | --- | --- |
| `ushka[orm]` | SQLAlchemy, Alembic, `aiosqlite` | The [ORM](orm.md) and `ushka db` |
| `ushka[postgres]` | the ORM and `asyncpg` | PostgreSQL |
| `ushka[mysql]` | the ORM and `aiomysql` | MySQL |
| `ushka[crypto]` | `cryptography` | [Encryption](crypto.md): `ushka.crypto`, encrypted sessions, `db.Encrypted` |
| `ushka[docs]` | `markdown-it-py`, `pygments`, `griffe` | [Ushka Docs](docs.md) |
| `ushka[full]` | all of the above | Trying everything |

```bash
pip install "ushka[orm]"
```

Quote the brackets: zsh treats `[...]` as a pattern.

## The install script

If you only want the `ushka` command (to scaffold projects, for example), the
script installs it for your user with `uv`, `pipx` or a private virtualenv. It
needs no sudo and touches nothing outside your home directory. Read it first and
check it against the published SHA-256:

```bash
curl -LsSf https://ushka.satela.com.br/install.sh -o install.sh
curl -LsSf https://ushka.satela.com.br/install.sh.sha256 | sha256sum -c -
sh install.sh
```

Options are environment variables: `USHKA_EXTRAS=orm` installs an extra and
`USHKA_VERSION=0.6.0` pins a version.

## Using Ushka Guard without Ushka

[Ushka Guard](guard-frameworks.md) works in FastAPI, Starlette and Django apps.
`pip install ushka` is all it takes, and the guard imports nothing else from
Ushka.

## Next

[Build your first app](quickstart.md) in five minutes.

### Installing the beta

Pin the beta version, as above, instead of using `pip install --pre ushka`. An exact
pre-release version installs only that pre-release, while `--pre` lets pip pick
pre-releases of **every** package it installs, which can pull in an unfinished
dependency (for example `httpx` 1.0 development builds). If you must use `--pre`, pin
what you depend on (`httpx<1`).
