"""Migration 395 - `sales_order_lines.uom`, the column `SalesOrderLine.uom` (app/models/
order.py) has mapped since 9a730b5dc without any migration ever adding it (code review
finding B1 on PLAN-scm-stack-followups-19aug).

`blank_session` builds its schema from `Base.metadata.create_all`, which already includes
`uom` because the model maps it - so it does NOT reproduce the bug on its own. The column
is dropped by hand first to put the scratch schema back into the pre-395 shape (no
migration in the chain ever created it), then `upgrade()` is run and asserted to restore
it. Same pattern as `tests/test_migration_ed706a98ddc6_fulfilment_policy_settings.py`:
imported by PATH, run inside `blank_session`'s rolled-back transaction, per the project
rule that a migration is tested against the CODE, not whatever the shared local database
happens to hold.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import inspect, text

from tests._pg_fixture import blank_session

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "395_so_line_uom.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("zzt_migration_395_so_line_uom", _MIGRATION_PATH)
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


def _has_uom(db) -> bool:
    cols = {c["name"] for c in inspect(db.connection()).get_columns("sales_order_lines")}
    return "uom" in cols


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def test_a_table_lacking_the_column_gets_it_added(db):
    """Reproduces the pre-395 shape: no migration ever created `uom`, so a database built
    from the migration chain alone does not have it - only `Base.metadata.create_all`
    (this fixture's normal starting point) does, because the model maps it."""
    db.execute(text("ALTER TABLE sales_order_lines DROP COLUMN uom"))
    db.flush()
    assert not _has_uom(db)

    _run_upgrade(db)

    db.expire_all()
    assert _has_uom(db)


def test_running_the_migration_twice_is_idempotent(db):
    db.execute(text("ALTER TABLE sales_order_lines DROP COLUMN uom"))
    db.flush()

    _run_upgrade(db)
    _run_upgrade(db)

    db.expire_all()
    assert _has_uom(db)


def test_a_table_that_already_carries_the_column_is_left_alone(db):
    """The common case in this repo: the shared local database converges via
    `Base.metadata.create_all`, so it has carried `uom` since 9a730b5dc - the guard must
    be a no-op, not an error, against a database built the same way."""
    assert _has_uom(db)

    _run_upgrade(db)

    db.expire_all()
    assert _has_uom(db)


def test_downgrade_drops_the_column_only_if_present(db):
    assert _has_uom(db)

    _run_downgrade(db)
    db.expire_all()
    assert not _has_uom(db)

    # a second downgrade against a database that no longer has it is a no-op, not an error
    _run_downgrade(db)
    db.expire_all()
    assert not _has_uom(db)
