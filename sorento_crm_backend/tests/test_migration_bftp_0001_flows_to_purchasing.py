"""Migration `bftp_0001_flows_to_purchasing` (PLAN-brand-flows-to-purchasing.md, AC-1).

RED for Phase 2: the migration module does not exist yet at the path below - every test here
fails on import (`FileNotFoundError` from `spec_from_file_location`/`exec_module`) against
TODAY's code.

`pg_session` (the real database, one transaction rolled back at teardown) rather than
`blank_session`'s schema-translated scratch copy: the same reasoning
`test_migration_465_shipment_container_size.py` and `test_migration_443_...py` record for
their own single-column adds - `brands` is also one of the seven bare table names that
`blank_session`'s own docstring calls out as colliding with the `{company}_projects` module
schema, so the safest substrate for a plain unqualified `ALTER TABLE brands` is the real
table, not a name that could quietly resolve elsewhere.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import text

from tests._pg_fixture import pg_session, unique_code

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "bftp_0001_flows_to_purchasing.py"
)
_TABLE = "brands"
_COLUMN = "flows_to_purchasing"


def _migration_module():
    spec = importlib.util.spec_from_file_location(
        "zzt_migration_bftp_0001_flows_to_purchasing", _MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, direction: str = "upgrade") -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _migration_module()
    context = MigrationContext.configure(connection=db.connection())
    with Operations.context(context):
        getattr(module, direction)()


def _columns(db) -> set[str]:
    return {c["name"] for c in sa.inspect(db.connection()).get_columns(_TABLE)}


def _drop_pre_migration_state(db) -> None:
    db.execute(text(f"ALTER TABLE {_TABLE} DROP COLUMN IF EXISTS {_COLUMN}"))
    db.flush()


@pytest.fixture
def db():
    with pg_session() as session:
        yield session


def test_upgrade_adds_a_not_null_column_defaulting_true(db):
    _drop_pre_migration_state(db)
    assert _COLUMN not in _columns(db)

    _run(db, "upgrade")

    db.expire_all()
    assert _COLUMN in _columns(db)
    col = next(c for c in sa.inspect(db.connection()).get_columns(_TABLE) if c["name"] == _COLUMN)
    assert col["nullable"] is False


def test_a_brand_row_that_already_existed_reads_true_after_upgrade(db):
    """AC-1: every existing brand reads true after upgrade - the server default applies
    to rows already present at ALTER TABLE time, not only to rows inserted after."""
    _drop_pre_migration_state(db)
    brand_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO brands (id, brand_code, brand_name, is_active) "
            "VALUES (:id, :code, :name, true)"
        ),
        {"id": brand_id, "code": unique_code("BFTP"), "name": "ZZT Pre-existing Brand"},
    )
    db.flush()

    _run(db, "upgrade")

    db.expire_all()
    value = db.execute(
        text(f"SELECT {_COLUMN} FROM {_TABLE} WHERE id = :id"), {"id": brand_id}
    ).scalar()
    assert value is True


def test_downgrade_drops_the_column(db):
    _drop_pre_migration_state(db)
    _run(db, "upgrade")
    assert _COLUMN in _columns(db)

    _run(db, "downgrade")

    db.expire_all()
    assert _COLUMN not in _columns(db)


def test_upgrade_then_downgrade_then_upgrade_round_trips(db):
    _drop_pre_migration_state(db)

    _run(db, "upgrade")
    db.expire_all()
    assert _COLUMN in _columns(db)

    _run(db, "downgrade")
    db.expire_all()
    assert _COLUMN not in _columns(db)

    _run(db, "upgrade")
    db.expire_all()
    assert _COLUMN in _columns(db)
