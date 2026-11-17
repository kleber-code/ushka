# ORM

Ushka ships an async ORM built on SQLAlchemy 2.0 with a small Active Record
interface: models know how to save, delete and query themselves. Migrations
are handled by Alembic through `ushka db`.

## Installing

The ORM is an optional extra, so the core install stays small:

```bash
pip install "ushka[orm]"        # SQLAlchemy, Alembic and the SQLite driver (aiosqlite)
pip install "ushka[postgres]"   # + asyncpg
pip install "ushka[mysql]"      # + aiomysql
```

## Choosing the database

The URL comes from the [configuration](configuration.md), in this order of
precedence: environment / `.env` (`USHKA_DATABASE_URL`, or `DATABASE_URL`, or
the older `USHKA_DB_URL`), then `[database] url` in `ushka.toml`, then the
default `sqlite:///ushka.db`.

```toml
# ushka.toml
[database]
url = "sqlite:///shop.db"
```

```bash
# .env, keep credentials out of ushka.toml
USHKA_DATABASE_URL=postgresql://user:password@localhost/shop
```

Write plain URLs: `sqlite://`, `postgresql://` (or `postgres://`) and
`mysql://` are switched to their async drivers (`aiosqlite`, `asyncpg`,
`aiomysql`) automatically. A URL that already names a driver
(`postgresql+psycopg://...`) is used as is.

A relative SQLite path such as `sqlite:///shop.db` is relative to the directory
the process runs in, so start the server (and `ushka db`) from the project
directory, or use an absolute path: `sqlite:////srv/shop/shop.db`.

The engine is created lazily on first use. To point the ORM somewhere else from
code (in tests, for example) call `db.configure(url)` before the first query.

## Defining models

```python
# models.py
import enum

from ushka.orm import db


class Status(enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


class User(db.Model):
    __tablename__ = "users"

    name = db.String(length=100)
    email = db.String(unique=True)
    is_active = db.Bool(default=True)
    created_at = db.DateTime(auto_now=True)
    posts = db.Relationship("Post", back_populates="author")


class Post(db.Model):
    __tablename__ = "posts"

    title = db.String(length=200)
    body = db.Text(nullable=True)
    status = db.Enum(Status, default=Status.DRAFT)
    tags = db.JSON(default=list)
    author_id = db.ForeignKey("users.id")
    author = db.Relationship("User", back_populates="posts")
```

Every model needs a `__tablename__`. **Do not declare `id`**: `db.Model` already
provides an auto-incrementing `BigInteger` primary key named `id`.

### Column helpers

Columns are `NOT NULL` unless you pass `nullable=True`.

| Helper | Signature |
| --- | --- |
| `db.String` | `(length=255, unique=False, nullable=False, default=None, choices=None)`. `choices=[...]` restricts the values. |
| `db.Text` | `(nullable=False, default=None)` |
| `db.Int` | `(unique=False, nullable=False, default=None)` |
| `db.BigInt` | `(unique=False, nullable=False, default=None)` |
| `db.Float` | `(nullable=False, default=0.0)` |
| `db.Decimal` | `(precision=10, scale=2, nullable=False, default=0)` |
| `db.Bool` | `(default=False, nullable=False)` |
| `db.DateTime` | `(auto_now=False, nullable=False)`. `auto_now=True` defaults to the current time on insert. |
| `db.Date` | `(auto_now=False, nullable=False)` |
| `db.Time` | `(nullable=False)` |
| `db.JSON` | `(nullable=False, default=None)`. Defaults to a fresh `{}` per row; a `dict`/`list` default is copied per row. |
| `db.Enum` | `(enum_cls, nullable=False, default=None)` |
| `db.Binary` | `(length=None, nullable=False)` |
| `db.UUID` | `(unique=False, nullable=False, primary_key=False, default=None)`. With `primary_key=True` the default is `uuid.uuid4`. |
| `db.ForeignKey` | `(target, dtype=None, on_delete=db.CASCADE, nullable=False, on_update=None)`. `target` is `"table.column"`; the type defaults to `BigInteger` (`dtype` takes another helper, e.g. `db.UUID()`). `on_delete` is `db.CASCADE`, `db.SET_NULL` (makes the column nullable), `db.RESTRICT` or `None` for no clause (what a schema made by another ORM usually has). |
| `db.Relationship` | `(model, back_populates=None)`. `model` is the class name as a string. |

`db.Model` is a regular SQLAlchemy declarative base, so plain SQLAlchemy
`Column(...)` definitions work as well.

## Existing databases

When the tables were created by another ORM (Django, SQLAlchemy, Prisma...),
let Ushka read them and write the models:

```bash
ushka db inspect --write models.py        # [database] url, or --url
ushka db inspect --table leads --table customers   # only these (repeatable)
ushka db inspect --schema crm             # a PostgreSQL schema
ushka db inspect > models.py              # warnings go to stderr, stdout stays code
```

It reads the real schema (SQLite, PostgreSQL and MySQL, through SQLAlchemy's
reflection) and writes `class Lead(db.Model): ...` with the right
`__tablename__`, column helpers, `nullable`, `unique`, indexes, foreign keys
(with their `ON DELETE` / `ON UPDATE`) and composite unique constraints. A table
whose primary key is an integer `id` extends `db.Model`; any other key (a UUID, a
text code, a composite key) extends `db.BaseModel`, the same base without the
`id` column, and declares its own. A column no helper can express exactly (an
enum, a timezone-aware timestamp, a name such as `metadata`) is written as a plain
SQLAlchemy `Column`. `--write` refuses to overwrite a file unless you add
`--force`.

Server defaults are mapped when they can be: `true`/`false`, numbers, strings,
`'{}'` for JSON, `now()` / `CURRENT_TIMESTAMP` becomes `auto_now=True`, and
`gen_random_uuid()` becomes `uuid.uuid4`. Each mapping is marked `NOTE` in the code
for you to confirm. A default it cannot translate is kept as `server_default`.

### Review the TODO comments

The important part is what the database **does not** say. Another ORM often
applies defaults, timestamps and deletes **in Python**, so none of it is in the
schema, and a model that only mirrors the schema then breaks or, worse, writes
something else. `ushka db inspect` lists these as `TODO(ushka db inspect)` comments
in the file and as warnings, and applies none of them for you:

- **`NOT NULL` without a default** (booleans, numbers, enums, dates). The old code
  probably declared `default=True` or `default=0` in Python. Ushka writes
  `default=None` so a forgotten value fails loudly instead of saving a wrong one
  (`db.Bool` alone would store `False`). Set the default the old code used.
- **`created_at` / `updated_at` / `criado_em` / `atualizado_em`**. Use
  `auto_now=True` for the value on insert. It does not refresh on update: set
  `updated_at` yourself before `save()`, or declare
  `Column(DateTime, onupdate=func.now())`.
- **Foreign keys without `ON DELETE`**. Each one is listed with its current
  behaviour (`NO ACTION` or `RESTRICT`): deleting a parent that still has children
  fails with an `IntegrityError`, because the old ORM deleted the children itself.
  SQLite does not even enforce foreign keys unless you run `PRAGMA foreign_keys=ON`,
  and then leaves orphans. Either delete the children first, inside one session:

  ```python
  async with db.Session() as session:
      for lead in (await session.execute(Lead.select().where(Lead.customer_id == cid))).scalars():
          await session.delete(lead)
      await session.delete(await session.get(Customer, cid))
      await session.commit()
  ```

  or change the constraint in the database with a migration and set
  `on_delete=db.CASCADE` (or `db.SET_NULL` on a nullable column) in the model.
  Changing the model alone does not alter the database, and Alembic's
  autogenerate does not detect `ON DELETE` changes, so write that migration by
  hand.
- Smaller hints: `CHAR(32)` that may be a UUID, MySQL `TINYINT(1)` that may be a
  boolean, tables without a primary key (they cannot be mapped), expression indexes
  (skipped).

Relationships are not generated: add `db.Relationship(...)` where you need them.

### Keeping the models honest

`ushka db check-models` compares the models of the app (found in `app.models`,
`models`, `app` or `main`, or `--models module`) with the database and lists every
divergence: missing tables and columns, columns only in the database (and whether
they make inserts fail), nullability, type, and foreign keys with a different
`ON DELETE` / `ON UPDATE`. It exits with 1 when there is any, so it can run in CI.

## Creating the tables: migrations

Tables are created and changed through migrations. Alembic has to see your
models, and it looks for them by importing `app.models`, `app` or `main` from
the project directory, so import your models in `app.py`:

```python
# app.py
from ushka import Ushka

import models  # noqa: F401  (registers the models for `ushka db make`)

app = Ushka()
```

Then, from the project directory:

```bash
ushka db init                       # once: creates migrations/ and alembic.ini
ushka db make -m "create users"     # generates a migration from your models
ushka db migrate                    # applies it
```

Every time you change a model, run `ushka db make -m "..."` and
`ushka db migrate` again. `ushka db revert` undoes the last migration. Review
the generated file in `migrations/versions/` before applying it. The full list
of commands is in the [CLI guide](cli.md#ushka-db).

SQLite migrations run in Alembic's batch mode automatically, so columns can be
altered and dropped there too.

## CRUD

All database methods are coroutines: remember the `await`.

### Create

```python
user = await User.create(name="Alice", email="alice@example.com")

bob = User(name="Bob", email="bob@example.com")
await bob.save()
```

### Read

```python
users = await User.all()                     # list
user = await User.get(1)                     # by primary key, or None
alice = await User.first(name="Alice")       # first match, or None
active = await User.filter(is_active=True)   # list of matches
```

`first()` and `filter()` take keyword arguments and compare for equality.
For anything richer, build a SQLAlchemy statement with `Model.select()` and run
it with `db.execute()`:

```python
result = await db.execute(
    User.select().where(User.email.endswith("@example.com")).order_by(User.name)
)
users = result.scalars().all()
```

### Update

```python
user = await User.get(1)
if user:
    user.name = "Alicia"
    await user.save()
```

### Delete

```python
user = await User.first(name="Bob")
if user:
    await user.delete()
```

### Serialising

`instance.to_dict()` returns the columns as a dict (enums become their value,
UUIDs become strings). Dates and times stay `datetime` objects, so convert them
before returning the dict as JSON:

```python
data = user.to_dict()
data["created_at"] = user.created_at.isoformat()
return data
```

## Request data and the ORM

Values from the request are `Untrusted` strings. The ORM methods and SQLAlchemy
expressions always send them as bound parameters, so they need no special care.
Declare the type and Ushka converts it, answering 422 when it does not fit:

```python
# routes/users/[user_id].py
from ushka.http.exceptions import HttpNotFound

from models import User


async def get(user_id: int):
    user = await User.get(user_id)
    if user is None:
        raise HttpNotFound(message="No such user")
    return {"id": user.id, "name": user.name}
```

## Raw SQL

`db.execute()` accepts a SQLAlchemy construct, a SQL string, or (on Python
3.14+) a t-string. SQL strings are guarded: if any part came from the request,
the call is refused with [USHKA-G005](guard.md#ushka-g005). Pass values as
parameters instead:

```python
# :name placeholders, values bound by the driver
result = await db.execute(
    db.text("SELECT id, name FROM users WHERE email = :email", email=email)
)
rows = result.all()

# Python 3.14+: every {value} in a t-string becomes a bound parameter
result = await db.execute(t"SELECT id, name FROM users WHERE email = {email}")
```

Use `db.text()` rather than `sqlalchemy.text()`: SQLAlchemy copies the string
internally and the guard would lose track of where it came from.

## Relationships and sessions

The Active Record methods open a short session per call, so the objects they
return are detached. Accessing a relationship that was not loaded
(`post.author`) then raises `DetachedInstanceError`. Load it up front:

```python
from sqlalchemy.orm import selectinload

result = await db.execute(Post.select().options(selectinload(Post.author)))
for post in result.scalars().all():
    print(post.title, post.author.name)
```

For several operations in one transaction, open a session yourself:

```python
async with db.Session() as session:
    session.add_all([User(name="Ann", email="ann@example.com"),
                     User(name="Ben", email="ben@example.com")])
    await session.commit()
```

`db.engine` (the `AsyncEngine`) and `db.metadata` are available for anything
else SQLAlchemy can do.
