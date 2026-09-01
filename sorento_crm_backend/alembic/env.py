"""Alembic environment configuration."""
from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
import os
import sys

# Add parent directory to path to import app
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import Base
from app.config import settings
from app.models import *  # Import all models

# this is the Alembic Config object
config = context.config

# Override sqlalchemy.url with settings
config.set_main_option("sqlalchemy.url", settings.database_url)

# Per-module migrations: append app/modules/<key>/migrations/ dirs to version_locations.
# Uses os.pathsep so Alembic locates branch-labeled per-module heads alongside the
# central alembic/versions tree.
try:
    from pathlib import Path as _Path
    _modules_dir = _Path(__file__).resolve().parent.parent / "app" / "modules"
    _extra = [
        str(d / "migrations")
        for d in _modules_dir.iterdir()
        if d.is_dir() and (d / "migrations").is_dir()
    ]
    if _extra:
        _existing = config.get_main_option("version_locations") or "alembic/versions"
        config.set_main_option(
            "version_locations",
            os.pathsep.join([_existing, *_extra]),
        )
except Exception:  # noqa: BLE001
    pass

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
target_metadata = Base.metadata

# Schemas autogenerate is allowed to compare. Derived from the models rather than listed,
# so a module that earns its own schema is covered the day its first model declares one.
# `None` is the connection's default schema (public in production).
KNOWN_SCHEMAS = {None} | {
    table.schema for table in target_metadata.tables.values() if table.schema
}


def include_name(name, type_, parent_names):
    """Keep autogenerate to the schemas the models actually describe.

    Two separate failures make this necessary. Without ``include_schemas`` alembic
    compares only the default schema on the DATABASE side while building its metadata
    table set from EVERY schema, so it proposes re-creating every `scm.*` and
    `projects.*` table on each run. Turning ``include_schemas`` on alone then surfaces
    schemas that exist in the database but not in the models (`dealer_kit`) as DROP
    candidates. Filtering by name is what makes the pair safe.
    """
    if type_ == "schema":
        return name in KNOWN_SCHEMAS
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


# DDL lock guards (1 Sep 2026 incident, lesson 96). ALTER TABLE takes ACCESS
# EXCLUSIVE; when it queues behind a long-running transaction, every new query
# on that table queues behind the waiting ALTER, so a "fast" migration stalls
# live traffic for as long as the lock holder runs. lock_timeout makes the DDL
# fail fast instead of damming production; the deploy aborts cleanly and can be
# re-run in a quiet moment. statement_timeout is the backstop for the other
# shape: DDL that acquires its lock instantly and then holds it while doing
# real work on a big table (rewrite, non-concurrent index, in-migration
# backfill). That shape must not be written at all (CONCURRENTLY / out-of-band
# backfill / expand-contract); the timeout bounds the damage when it slips
# through. Both are overridable per run, '0' disables.
MIGRATION_LOCK_TIMEOUT = os.environ.get("ALEMBIC_LOCK_TIMEOUT", "5s")
MIGRATION_STATEMENT_TIMEOUT = os.environ.get("ALEMBIC_STATEMENT_TIMEOUT", "15min")


def _apply_lock_guards(connection) -> None:
    from sqlalchemy import text

    connection.execute(
        text("SELECT set_config('lock_timeout', :v, false)"),
        {"v": MIGRATION_LOCK_TIMEOUT},
    )
    connection.execute(
        text("SELECT set_config('statement_timeout', :v, false)"),
        {"v": MIGRATION_STATEMENT_TIMEOUT},
    )
    # set_config is transactional; commit so the session-level values survive
    # into the transaction alembic opens for the migrations themselves.
    connection.commit()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        _apply_lock_guards(connection)
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_name=include_name,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
