"""Migration 466 - `inbound_shipment_lines.description` (S9,
PLAN-scm-pi-packing-list-feedback-3sep.md Round 2, AC-I1).

TEST-FIRST: at the time this file is written the migration module does not exist, so every
test here is expected to be red until it lands.

Two things are proven:

  * The DDL shape - the new nullable Text column exists after upgrade, is idempotent to
    re-run, and downgrade drops it.
  * The data step - a shipment line linked (via `scm.proforma_invoice_shipment_link`) to a PI
    line that states a description is backfilled with that PI line's description; a shipment
    line that already carries its own description is left alone; a shipment line with no link
    at all is left NULL.

`pg_session` is the real database in a transaction that always rolls back - the same substrate
`test_migration_465_shipment_container_size.py` uses.
"""
from __future__ import annotations

import importlib.util
import uuid
from datetime import date as _date
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import text

from tests._pg_fixture import pg_session, unique_code
from tests.scm.test_proforma_invoice_import import World

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "466_shipment_line_description.py"
)
_LINES = "inbound_shipment_lines"


def _migration_module():
    spec = importlib.util.spec_from_file_location(
        "zzt_migration_466_shipment_line_description", _MIGRATION_PATH
    )
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


def _columns(db, table: str, schema: str | None = None) -> set[str]:
    return {c["name"] for c in sa.inspect(db.connection()).get_columns(table, schema=schema)}


def _drop_pre_migration_state(db) -> None:
    db.execute(text(f"ALTER TABLE {_LINES} DROP COLUMN IF EXISTS description"))
    db.flush()


@pytest.fixture
def db():
    with pg_session() as session:
        yield session


# --------------------------------------------------------------------------------- #
# DDL shape
# --------------------------------------------------------------------------------- #


def test_upgrade_adds_the_description_column(db):
    _drop_pre_migration_state(db)
    assert "description" not in _columns(db, _LINES)

    _run_upgrade(db)

    db.expire_all()
    assert "description" in _columns(db, _LINES)


def test_running_the_migration_twice_is_idempotent(db):
    _drop_pre_migration_state(db)

    _run_upgrade(db)
    _run_upgrade(db)

    db.expire_all()
    assert "description" in _columns(db, _LINES)


def test_downgrade_drops_the_column(db):
    _drop_pre_migration_state(db)
    _run_upgrade(db)

    _run_downgrade(db)

    db.expire_all()
    assert "description" not in _columns(db, _LINES)

    # a second downgrade against a database that no longer carries the column is a no-op
    _run_downgrade(db)
    db.expire_all()
    assert "description" not in _columns(db, _LINES)


# --------------------------------------------------------------------------------- #
# The data step
# --------------------------------------------------------------------------------- #


def _invoice_line(db, w: World, *, description: str | None) -> tuple[str, str]:
    """A minimal PI + one line, by raw SQL - matches the shape `_invoice` in the 465 test
    seeds, so the two files stay comparable."""
    invoice_id = str(uuid.uuid4())
    db.execute(
        text(
            """
            INSERT INTO scm.proforma_invoice (id, supplier_id, pi_number)
            VALUES (:id, :supplier_id, :pi_number)
            """
        ),
        {"id": invoice_id, "supplier_id": w.supplier.id, "pi_number": unique_code("PI")},
    )
    line_id = str(uuid.uuid4())
    db.execute(
        text(
            """
            INSERT INTO scm.proforma_invoice_line
                (id, invoice_id, line_no, item_code, qty, description)
            VALUES (:id, :invoice_id, 1, :item_code, 1, :description)
            """
        ),
        {
            "id": line_id,
            "invoice_id": invoice_id,
            "item_code": unique_code("CODE"),
            "description": description,
        },
    )
    db.flush()
    return invoice_id, line_id


def _shipment(db) -> str:
    shipment_id = str(uuid.uuid4())
    db.execute(
        text(
            """
            INSERT INTO inbound_shipments (id, shipment_number, shipment_date, shipment_status)
            VALUES (:id, :number, :shipment_date, 'draft')
            """
        ),
        {"id": shipment_id, "number": unique_code("PL"), "shipment_date": _date(2026, 9, 3)},
    )
    db.flush()
    return shipment_id


def _shipment_line(db, *, shipment_id: str, product_id: str, description: str | None) -> str:
    line_id = str(uuid.uuid4())
    db.execute(
        text(
            """
            INSERT INTO inbound_shipment_lines
                (id, shipment_id, product_id, quantity_shipped, cartons_count, description)
            VALUES (:id, :shipment_id, :product_id, 1, 1, :description)
            """
        ),
        {
            "id": line_id,
            "shipment_id": shipment_id,
            "product_id": product_id,
            "description": description,
        },
    )
    db.flush()
    return line_id


def _link(db, *, invoice_id: str, line_id: str, shipment_id: str, shipment_line_id: str) -> None:
    db.execute(
        text(
            """
            INSERT INTO scm.proforma_invoice_shipment_link
                (id, proforma_invoice_id, proforma_invoice_line_id, inbound_shipment_id,
                 inbound_shipment_line_id)
            VALUES (gen_random_uuid(), :inv, :line, :ship, :ship_line)
            """
        ),
        {"inv": invoice_id, "line": line_id, "ship": shipment_id, "ship_line": shipment_line_id},
    )
    db.flush()


def _pre_migration_state_with_the_column_already_present(db) -> None:
    """The realistic pre-migration shape on the shared dev DB (this backend's own CLAUDE.md
    note): `create_all` already added the column the moment the model declared it, well
    before this migration's stamp lands - so seeding a row that already carries a value has
    to add the column back first, exactly as `create_all` would, rather than assume it is
    still absent."""
    _drop_pre_migration_state(db)
    db.execute(text(f"ALTER TABLE {_LINES} ADD COLUMN IF NOT EXISTS description text"))
    db.flush()


def test_a_linked_line_with_no_description_is_backfilled_from_the_pi_line(db):
    _pre_migration_state_with_the_column_already_present(db)
    w = World(db)
    invoice_id, pi_line_id = _invoice_line(db, w, description="304 STAINLESS STEEL BASIN TAP")
    ship_id = _shipment(db)
    ship_line_id = _shipment_line(
        db, shipment_id=ship_id, product_id=str(w.product("A").id), description=None
    )
    _link(db, invoice_id=invoice_id, line_id=pi_line_id, shipment_id=ship_id,
          shipment_line_id=ship_line_id)

    _run_upgrade(db)

    db.expire_all()
    got = db.execute(
        text(f"SELECT description FROM {_LINES} WHERE id = :id"), {"id": ship_line_id}
    ).scalar()
    assert got == "304 STAINLESS STEEL BASIN TAP"


def test_a_line_that_already_carries_its_own_description_is_left_alone(db):
    _pre_migration_state_with_the_column_already_present(db)
    w = World(db)
    invoice_id, pi_line_id = _invoice_line(db, w, description="PI WORDING")
    ship_id = _shipment(db)
    ship_line_id = _shipment_line(
        db, shipment_id=ship_id, product_id=str(w.product("A").id),
        description="ALREADY TYPED ON THE SHEET",
    )
    _link(db, invoice_id=invoice_id, line_id=pi_line_id, shipment_id=ship_id,
          shipment_line_id=ship_line_id)

    _run_upgrade(db)

    db.expire_all()
    got = db.execute(
        text(f"SELECT description FROM {_LINES} WHERE id = :id"), {"id": ship_line_id}
    ).scalar()
    assert got == "ALREADY TYPED ON THE SHEET"


def test_a_line_with_no_link_at_all_is_left_null(db):
    _pre_migration_state_with_the_column_already_present(db)
    w = World(db)
    ship_id = _shipment(db)
    ship_line_id = _shipment_line(
        db, shipment_id=ship_id, product_id=str(w.product("A").id), description=None
    )

    _run_upgrade(db)

    db.expire_all()
    got = db.execute(
        text(f"SELECT description FROM {_LINES} WHERE id = :id"), {"id": ship_line_id}
    ).scalar()
    assert got is None


def test_a_linked_pi_line_with_no_description_leaves_the_shipment_line_null(db):
    _pre_migration_state_with_the_column_already_present(db)
    w = World(db)
    invoice_id, pi_line_id = _invoice_line(db, w, description=None)
    ship_id = _shipment(db)
    ship_line_id = _shipment_line(
        db, shipment_id=ship_id, product_id=str(w.product("A").id), description=None
    )
    _link(db, invoice_id=invoice_id, line_id=pi_line_id, shipment_id=ship_id,
          shipment_line_id=ship_line_id)

    _run_upgrade(db)

    db.expire_all()
    got = db.execute(
        text(f"SELECT description FROM {_LINES} WHERE id = :id"), {"id": ship_line_id}
    ).scalar()
    assert got is None
