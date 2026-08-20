"""Migration 400 - `order_inquiry_rows.po_ref` / `po_line_id` (section G, "Place on PO").

`blank_session` cannot be used here: the migration's guards (`_has_table`/`_has_column`)
call `sa.inspect(op.get_bind())` with an EXPLICIT `schema="projects"` argument, and
`Inspector` reflection with an explicit schema does not honour `schema_translate_map` the
way DDL compiled off a `Table` object does - it resolves against the LITERAL `projects`
schema, which under `blank_session` is the real shared database's schema, not the scratch
copy. Proven by spiking it: `Inspector(scoped_connection).get_columns("order_inquiry_rows",
schema="projects")` returned the real production-copy table's columns, not the empty
scratch table's. Running this migration's `upgrade()`/`downgrade()` there would silently
read (and, on downgrade, alter) the real database while the test believes it is isolated.

`pg_session` is the real database in a transaction that always rolls back, so the DDL here
runs for real and is undone by Postgres's transactional DDL the moment the test ends -
the same substrate `test_migration_396_oi_single_location.py` uses for a different reason
(literal schema-qualified names in that migration's own SQL). Mirrors the
`test_migration_395_so_line_uom.py` upgrade/downgrade shape otherwise.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import inspect, text

from tests._pg_fixture import pg_session

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "400_oi_place_on_po.py"
)

_TABLE = "order_inquiry_rows"
_SCHEMA = "projects"
_FK = "fk_project_order_inquiry_rows_po_line"
_INDEX = "ix_project_order_inquiry_rows_po_line"


def _migration_module():
    spec = importlib.util.spec_from_file_location("zzt_migration_400_oi_place_on_po", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_upgrade(db) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _migration_module()
    context = MigrationContext.configure(connection=db.connection())
    with Operations.context(context):
        module.upgrade()


def _run_downgrade(db) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _migration_module()
    context = MigrationContext.configure(connection=db.connection())
    with Operations.context(context):
        module.downgrade()


def _columns(db) -> set[str]:
    return {c["name"] for c in inspect(db.connection()).get_columns(_TABLE, schema=_SCHEMA)}


def _has_fk(db) -> bool:
    names = {fk["name"] for fk in inspect(db.connection()).get_foreign_keys(_TABLE, schema=_SCHEMA)}
    return _FK in names


def _has_index(db) -> bool:
    names = {ix["name"] for ix in inspect(db.connection()).get_indexes(_TABLE, schema=_SCHEMA)}
    return _INDEX in names


def _drop_pre_migration_state(db) -> None:
    """Puts the real (already-migrated) table back into the pre-400 shape."""
    db.execute(text(f"ALTER TABLE {_SCHEMA}.{_TABLE} DROP COLUMN IF EXISTS po_line_id"))
    db.execute(text(f"ALTER TABLE {_SCHEMA}.{_TABLE} DROP COLUMN IF EXISTS po_ref"))
    db.flush()


@pytest.fixture
def db():
    with pg_session() as session:
        yield session


def test_a_table_lacking_the_columns_gets_them_added(db):
    _drop_pre_migration_state(db)
    assert "po_ref" not in _columns(db)
    assert "po_line_id" not in _columns(db)

    _run_upgrade(db)

    db.expire_all()
    assert {"po_ref", "po_line_id"} <= _columns(db)
    assert _has_fk(db)
    assert _has_index(db)


def test_running_the_migration_twice_is_idempotent(db):
    _drop_pre_migration_state(db)

    _run_upgrade(db)
    _run_upgrade(db)

    db.expire_all()
    assert {"po_ref", "po_line_id"} <= _columns(db)
    assert _has_fk(db)
    assert _has_index(db)


def test_a_table_that_already_carries_the_columns_is_left_alone(db):
    """The common case: the real database already has po_ref / po_line_id (this migration
    is applied to the stack). The guard must be a no-op, not an error."""
    assert {"po_ref", "po_line_id"} <= _columns(db)

    _run_upgrade(db)

    db.expire_all()
    assert {"po_ref", "po_line_id"} <= _columns(db)


def test_downgrade_drops_the_index_the_fk_and_the_columns_only_if_present(db):
    assert {"po_ref", "po_line_id"} <= _columns(db)

    _run_downgrade(db)

    db.expire_all()
    assert "po_line_id" not in _columns(db)
    assert "po_ref" not in _columns(db)
    assert not _has_fk(db)
    assert not _has_index(db)

    # a second downgrade against a database that no longer carries them is a no-op
    _run_downgrade(db)
    db.expire_all()
    assert "po_line_id" not in _columns(db)
    assert "po_ref" not in _columns(db)
