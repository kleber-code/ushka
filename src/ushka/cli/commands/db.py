# ushka/commands/db.py
import os
import sys
from datetime import datetime
from typing import Optional

from alembic import command
from alembic.config import Config as AlembicConfig

from ushka.core.config import Config as UshkaConfig

# =============================================================================
# USHKA CUSTOM ENV.PY TEMPLATE
# =============================================================================
# This template is injected into the user's project during 'ushka db init'.
# It handles:
# 1. Loading Ushka configuration (URL).
# 2. Auto-discovering user models (so db.metadata is populated).
# 3. Enabling "batch mode" automatically for SQLite.
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
db_url = ushka_cfg.DATABASE_URL

# FORCE ASYNC DRIVER FOR ALEMBIC
if "sqlite" in db_url and "aiosqlite" not in db_url:
    db_url = db_url.replace("sqlite://", "sqlite+aiosqlite://")

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
    """
    Configures Alembic dynamically based on ushka.toml.
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
    """
    Initialize the migration environment and inject the Ushka-optimized env.py.
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


def make(message: Optional[str] = None):
    """
    Generate a new migration script.

    If no message is provided, an auto-generated timestamped message is used.
    """
    if not message:
        # Generate a timestamp slug: auto_20231015_120000
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        message = f"auto_{timestamp}"
        print(f"ℹ️  No message provided. Using: '{message}'")

    print(f"🔨 Creating migration: {message}")
    command.revision(_get_alembic_config(), message=message, autogenerate=True)


def migrate():
    """Apply all pending migrations to the database."""
    print("🚀 Applying changes (upgrade head)...")
    command.upgrade(_get_alembic_config(), "head")


def revert(revision: str = "-1"):
    """
    Revert migrations. Defaults to undoing the last step (-1).

    Args:
        revision: The revision to downgrade to (e.g., "-1", "base", or a revision ID).
    """
    target = "last step" if revision == "-1" else revision
    print(f"⏪ Reverting database changes (downgrade {target})...")
    command.downgrade(_get_alembic_config(), revision)


def status():
    """Show the current database revision."""
    print("📍 Current Revision:")
    command.current(_get_alembic_config(), verbose=True)


def history():
    """Show the full migration history."""
    print("📜 Migration History:")
    command.history(_get_alembic_config(), verbose=True)
