"""
This module provides the Command Line Interface (CLI) commands for database
migration management using Alembic.

It integrates Ushka's configuration for database URL and model discovery,
and customizes the Alembic `env.py` template to provide auto-batch mode
for SQLite and automatic model discovery.

Commands
--------
_get_alembic_config: Configures Alembic based on Ushka settings.
init: Initializes the Alembic migration environment.
make: Generates a new migration script.
migrate: Applies pending migrations to the database.
revert: Reverts database migrations.
status: Shows the current database revision.
history: Shows the full migration history.
inspect: Writes Ushka models for an existing database.
check_models: Compares the app's models with the database.
"""

# ushka/commands/db.py
from __future__ import annotations

import asyncio
import contextlib
import importlib
import os
import sys
from datetime import datetime
from typing import Optional

from alembic import command
from alembic.config import Config as AlembicConfig

from ushka.cli import ui
from ushka.core.config import Config as UshkaConfig

# =============================================================================
# USHKA CUSTOM ENV.PY TEMPLATE
# =============================================================================
# Este template é injetado no projeto do usuário durante 'ushka db init'.
# Ele gerencia:
# 1. Carregamento da configuração do Ushka (URL).
# 2. Auto-descoberta de modelos do usuário.
# 3. Habilitação automática do "batch mode" para SQLite.
# =============================================================================

USHKA_ENV_TEMPLATE = """from logging.config import fileConfig
import sys
import os
import asyncio
import importlib

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

# --- 1. SETUP PATHS ---
sys.path.insert(0, os.getcwd())

# --- 2. USHKA INTEGRATION ---
from ushka.core.config import Config as UshkaConfig
from ushka.orm import db

ushka_cfg = UshkaConfig().load_from_file()
# Same URL (and async driver) the application uses at runtime.
db_url = db.url

# --- 3. MODEL DISCOVERY ---
if ushka_cfg.APP_AUTO_DISCOVER:
    discovered = False
    potential_modules = ["app.models", "app", "main"]
    for module in potential_modules:
        try:
            importlib.import_module(module)
            discovered = True
            break
        except ImportError:
            continue
    if not discovered:
         print("⚠️  [Ushka] Warning: Could not auto-discover models.")

target_metadata = db.metadata

# --- 4. ALEMBIC CONFIG ---
config = context.config
config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

def run_migrations_offline() -> None:
    \"\"\"Run migrations in 'offline' mode.\"\"\"
    url = config.get_main_option("sqlalchemy.url")
    is_sqlite = "sqlite" in url

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=is_sqlite
    )

    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection: Connection) -> None:
    \"\"\"Helper to run migrations in the sync context.\"\"\"
    is_sqlite = "sqlite" in str(connection.engine.url)
    
    context.configure(
        connection=connection, 
        target_metadata=target_metadata,
        render_as_batch=is_sqlite
    )

    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations() -> None:
    \"\"\"Run migrations in 'online' mode using AsyncEngine.\"\"\"
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()

def run_migrations_online() -> None:
    \"\"\"Entry point for online migrations.\"\"\"
    asyncio.run(run_async_migrations())

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
"""

# =============================================================================
# CLI COMMAND HANDLERS
# =============================================================================


def _get_alembic_config():
    """Configures Alembic dynamically based on ushka.toml.

    This function sets up the Alembic configuration, including the script
    location and injecting the database URL from Ushka's configuration.
    It handles cases where `alembic.ini` might not exist yet (e.g., during `db init`)
    and exits if the configuration cannot be loaded.

    Returns
    -------
    alembic.config.Config
        An initialized Alembic configuration object.

    Raises
    ------
    SystemExit
        If `alembic.ini` is not found (unless `db init` is being run),
        or if there's an error loading Ushka's configuration.
    """
    ini_path = os.path.join(os.getcwd(), "alembic.ini")

    # Allow 'init' to run even if config doesn't exist yet
    if len(sys.argv) > 1 and sys.argv[1] == "db" and sys.argv[-1] == "init":
        return AlembicConfig(ini_path)

    if not os.path.exists(ini_path):
        print("❌ alembic.ini not found. Run 'ushka db init' first.")
        sys.exit(1)

    alembic_cfg = AlembicConfig(ini_path)
    alembic_cfg.set_main_option("script_location", "migrations")

    # Inject Ushka URL into Alembic runtime config
    try:
        ushka_cfg = UshkaConfig().load_from_file()
        alembic_cfg.set_main_option("sqlalchemy.url", ushka_cfg.DATABASE_URL)
    except Exception as e:
        print(f"❌ Error loading Ushka config: {e}")
        sys.exit(1)

    return alembic_cfg


def init():
    """Initializes the Alembic migration environment and injects Ushka's custom env.py.

    This command creates the `migrations` directory and an initial `alembic.ini`
    file if they don't exist. It then overwrites the default `env.py` with
    Ushka's optimized template, which provides:

    - Automatic loading of Ushka's database configuration.
    - Auto-discovery of user models for `alembic autogenerate`.
    - Automatic enabling of "batch mode" for SQLite migrations.

    See Also
    --------
    USHKA_ENV_TEMPLATE : The custom template injected into `env.py`.
    """
    print("📦 Initializing Ushka Database environment...")

    migrations_dir = "migrations"
    env_path = os.path.join(migrations_dir, "env.py")

    try:
        # 1. Let Alembic create the default structure
        cfg = _get_alembic_config()
        command.init(cfg, migrations_dir)

        # 2. Overwrite the default env.py with our custom template
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(USHKA_ENV_TEMPLATE)

        print("✅ Structure created!")
        print(f"✅ Auto-Batch configuration injected into '{env_path}'")
        print("✅ Target metadata set to 'ushka.orm.database.db.metadata'")

    except Exception as e:
        print(f"Error during initialization: {e}")


def make(message: str | None = None):
    """Generates a new migration script based on model changes.

    If no message is provided, an auto-generated timestamped message is used.
    This command leverages Alembic's `autogenerate` feature to detect differences
    between the current database state (or `db.metadata`) and the defined SQLAlchemy models.

    Parameters
    ----------
    message : str, optional
        A short description of the migration. If `None`, a message like
        "auto_YYYYMMDD_HHMMSS" will be generated.
    """
    if not message:
        # Generate a timestamp slug: auto_20231015_120000
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        message = f"auto_{timestamp}"
        print(f"ℹ️  No message provided. Using: '{message}'")

    print(f"🔨 Creating migration: {message}")
    command.revision(_get_alembic_config(), message=message, autogenerate=True)


def migrate():
    """Applies all pending migrations to the database.

    This command upgrades the database schema to the latest revision,
    applying any migration scripts that have not yet been run.
    """
    print("🚀 Applying changes (upgrade head)...")
    command.upgrade(_get_alembic_config(), "head")


def revert(revision: str = "-1"):
    """Reverts database migrations to a specified revision.

    Defaults to undoing the last step (downgrading by one revision).

    Parameters
    ----------
    revision : str, optional
        The target revision to downgrade to.
        Common values include:
        - `"-1"`: Downgrade one step (default).
        - `"base"`: Downgrade all migrations to the initial state.
        - A specific revision ID (e.g., "abcdef123456").
    """
    target = "last step" if revision == "-1" else revision
    print(f"⏪ Reverting database changes (downgrade {target})...")
    command.downgrade(_get_alembic_config(), revision)


def status():
    """Shows the current database revision.

    This command reports the revision identifier of the latest migration
    applied to the database.
    """
    print("📍 Current Revision:")
    command.current(_get_alembic_config(), verbose=True)


def history():
    """Shows the full migration history.

    This command lists all available migration scripts, including their
    revision identifiers, timestamps, and messages.
    """
    print("📜 Migration History:")
    command.history(_get_alembic_config(), verbose=True)


# =============================================================================
# EXISTING DATABASES
# =============================================================================


def _database_url(url: str | None) -> str:
    """The async URL to read: `--url`, else the app's configured database."""
    from ushka.orm import db

    if not url:
        url = UshkaConfig().load_from_file().get("database_url") or "sqlite:///ushka.db"
    return db.to_async_url(url)


def _reflect(url: str | None, tables, schema):
    from ushka.orm.reflect import reflect

    try:
        return asyncio.run(reflect(_database_url(url), schema, list(tables) or None))
    except LookupError as exc:
        ui.fail(str(exc))
    except Exception as exc:  # driver and connection errors are many and varied
        ui.fail(f"could not read the database: {exc}")


def inspect(
    url: str | None = None,
    tables=(),
    schema: str | None = None,
    write: str | None = None,
    force: bool = False,
) -> int:
    """Reflects the database and writes Ushka models for it.

    The code goes to stdout (warnings to stderr, so ``> models.py`` stays
    clean) or to the file `write`. Returns the number of review items.
    """
    from ushka.orm.reflect import generate

    reflected = _reflect(url, tables, schema)
    if not reflected:
        ui.fail("the database has no tables to reflect.")
    if write and os.path.exists(write) and not force:
        ui.fail(f"{write} already exists; pass --force to overwrite it.")

    source, findings = generate(reflected)

    if write:
        with open(write, "w", encoding="utf-8") as fh:
            fh.write(source)
        ui.ok(f"{len(reflected)} table(s) written to {write}")
        sink = contextlib.nullcontext()
    else:
        print(source, end="")
        sink = contextlib.redirect_stdout(sys.stderr)

    review = [f for f in findings if f.kind != "mapped-default"]
    mapped = [f for f in findings if f.kind == "mapped-default"]
    with sink:
        if mapped:
            ui.info(f"{len(mapped)} server default(s) mapped to Python defaults (marked NOTE in the code).")
        if review:
            ui.warn(
                f"{len(review)} thing(s) to review. The database does not say them, and an old ORM "
                "may have applied them in Python (see the TODO comments):"
            )
            for f in review:
                ui.warn(f"{f.where()}: {f.message}")
                if f.suggestion:
                    ui.hint(f"suggestion: {f.suggestion}")
        else:
            ui.ok("nothing to review.")
    return len(review)


def _load_models(modules) -> None:
    """Imports the app's models the way the migrations do."""
    candidates = list(modules) or ["app.models", "models", "app", "main"]
    for name in candidates:
        try:
            importlib.import_module(name)
            return
        except ImportError as exc:
            if modules or getattr(exc, "name", None) not in (name, name.split(".")[0]):
                raise
    ui.fail("could not find the models: pass --models module (tried app.models, models, app, main).")


def check_models(url: str | None = None, schema: str | None = None, models=()) -> int:
    """Compares the app's models with the database. Returns the number of divergences."""
    from ushka.orm import db
    from ushka.orm.reflect import compare, table_from_model

    _load_models(models)
    mapped = [table_from_model(t) for t in db.metadata.tables.values() if (t.schema or None) == schema]
    if not mapped:
        ui.fail("no models are registered (is the module that defines them imported?).")
    reflected = _reflect(url, (), schema)

    divergences = compare(reflected, mapped)
    if not divergences:
        ui.ok(f"{len(mapped)} model(s) match the database.")
        return 0
    ui.warn(f"{len(divergences)} divergence(s) between the models and the database:")
    for d in divergences:
        ui.warn(f"{d.where()}: {d.message}")
    return len(divergences)
