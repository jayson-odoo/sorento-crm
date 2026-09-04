"""Migration 465 - `inbound_shipments.container_size_id` replaces
`scm.proforma_invoice.container_size_id` (S5, PLAN-scm-pi-packing-list-feedback-3sep.md
ruling 1, AC-E3).

TEST-FIRST: at the time this file is written the migration module does not import (or its
upgrade/downgrade are no-ops), so every test here is expected to be red until it lands.

Two things are proven:

  * The DDL shape - the new column, its FK and index exist after upgrade, are idempotent to
    re-run, and downgrade reverses them (restoring the PI column).
  * The data step - a draft shipment whose lines came from exactly ONE proforma invoice
    inherits that invoice's `container_size_id`; a shipment consolidating several invoices is
    left NULL (the tenant default), because there is no single invoice's choice to inherit.

`pg_session` is the real database in a transaction that always rolls back (`tests/_pg_fixture.
py`) - the same substrate `test_migration_400_oi_place_on_po.py` uses, and for the same
reason: the migration issues literal schema-qualified DDL (`op.add_column(..., schema="scm")`),
and `Inspector` reflection with an explicit schema does not honour `blank_session`'s
`schema_translate_map`.
"""
from __future__ import annotations

import importlib.util
import uuid
from datetime import date as _date
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import text

from app.models.scm import ContainerSize
from tests._pg_fixture import pg_session, unique_code
from tests.scm.test_proforma_invoice_import import World

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "465_shipment_container_size.py"
)
_SHIPMENTS = "inbound_shipments"
_INVOICE = "proforma_invoice"
_INVOICE_SCHEMA = "scm"


def _migration_module():
    spec = importlib.util.spec_from_file_location(
        "zzt_migration_465_shipment_container_size", _MIGRATION_PATH
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
    """Puts the database back into the pre-465 shape, whatever it currently holds: the
    shipment column absent, the PI column present (create_all's own shape - see this
    backend's CLAUDE.md note on the shared dev DB's stamp lagging its actual shape)."""
    db.execute(text(f"ALTER TABLE {_SHIPMENTS} DROP COLUMN IF EXISTS container_size_id"))
    db.execute(
        text(f"ALTER TABLE {_INVOICE_SCHEMA}.{_INVOICE} ADD COLUMN IF NOT EXISTS "
             "container_size_id uuid")
    )
    db.flush()


@pytest.fixture
def db():
    with pg_session() as session:
        yield session


# --------------------------------------------------------------------------------- #
# DDL shape
# --------------------------------------------------------------------------------- #


def test_upgrade_adds_the_shipment_column_and_drops_the_pi_one(db):
    _drop_pre_migration_state(db)
    assert "container_size_id" not in _columns(db, _SHIPMENTS)
    assert "container_size_id" in _columns(db, _INVOICE, schema=_INVOICE_SCHEMA)

    _run_upgrade(db)

    db.expire_all()
    assert "container_size_id" in _columns(db, _SHIPMENTS)
    assert "container_size_id" not in _columns(db, _INVOICE, schema=_INVOICE_SCHEMA)


def test_running_the_migration_twice_is_idempotent(db):
    _drop_pre_migration_state(db)

    _run_upgrade(db)
    _run_upgrade(db)

    db.expire_all()
    assert "container_size_id" in _columns(db, _SHIPMENTS)
    assert "container_size_id" not in _columns(db, _INVOICE, schema=_INVOICE_SCHEMA)


def test_downgrade_restores_the_pi_column_and_drops_the_shipment_one(db):
    _drop_pre_migration_state(db)
    _run_upgrade(db)

    _run_downgrade(db)

    db.expire_all()
    assert "container_size_id" not in _columns(db, _SHIPMENTS)
    assert "container_size_id" in _columns(db, _INVOICE, schema=_INVOICE_SCHEMA)

    # a second downgrade against a database that no longer carries the shipment column is a
    # no-op
    _run_downgrade(db)
    db.expire_all()
    assert "container_size_id" not in _columns(db, _SHIPMENTS)
    assert "container_size_id" in _columns(db, _INVOICE, schema=_INVOICE_SCHEMA)


# --------------------------------------------------------------------------------- #
# The data step
# --------------------------------------------------------------------------------- #


def _size(db, cbm: float) -> ContainerSize:
    size = ContainerSize(
        id=str(uuid.uuid4()), code=unique_code("BOX")[:30], label=None, cbm=cbm,
        is_active=True,
    )
    db.add(size)
    db.flush()
    return size


def _invoice(db, w: World, *, size: ContainerSize | None = None) -> tuple[str, str]:
    """A minimal PI + one line, inserted by RAW SQL rather than the ORM: the model no
    longer declares `proforma_invoice.container_size_id` (this migration removes it), so
    the ORM constructor cannot set the column this test needs to seed BEFORE upgrade runs.
    """
    invoice_id = str(uuid.uuid4())
    db.execute(
        text(
            """
            INSERT INTO scm.proforma_invoice
                (id, supplier_id, pi_number, container_size_id)
            VALUES (:id, :supplier_id, :pi_number, :size_id)
            """
        ),
        {
            "id": invoice_id,
            "supplier_id": w.supplier.id,
            "pi_number": unique_code("PI"),
            "size_id": str(size.id) if size is not None else None,
        },
    )
    line_id = str(uuid.uuid4())
    db.execute(
        text(
            """
            INSERT INTO scm.proforma_invoice_line (id, invoice_id, line_no, item_code, qty)
            VALUES (:id, :invoice_id, 1, :item_code, 1)
            """
        ),
        {"id": line_id, "invoice_id": invoice_id, "item_code": unique_code("CODE")},
    )
    db.flush()
    return invoice_id, line_id


def _shipment(db) -> str:
    """A minimal draft shipment, inserted by RAW SQL: `container_size_id` may not exist
    on `inbound_shipments` yet in a test that has not run `upgrade()`."""
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


def _link(db, *, invoice_id: str, line_id: str, shipment_id: str) -> None:
    db.execute(
        text(
            """
            INSERT INTO scm.proforma_invoice_shipment_link
                (id, proforma_invoice_id, proforma_invoice_line_id, inbound_shipment_id)
            VALUES (gen_random_uuid(), :inv, :line, :ship)
            """
        ),
        {"inv": invoice_id, "line": line_id, "ship": shipment_id},
    )
    db.flush()


def test_a_shipment_from_one_invoice_inherits_its_container_size(db):
    _drop_pre_migration_state(db)
    w = World(db)
    size = _size(db, 65)
    invoice_id, line_id = _invoice(db, w, size=size)
    ship_id = _shipment(db)
    _link(db, invoice_id=invoice_id, line_id=line_id, shipment_id=ship_id)

    _run_upgrade(db)

    db.expire_all()
    got = db.execute(
        text(f"SELECT container_size_id FROM {_SHIPMENTS} WHERE id = :id"), {"id": ship_id}
    ).scalar()
    assert str(got) == str(size.id)


def test_a_shipment_consolidating_two_invoices_is_left_at_the_tenant_default(db):
    _drop_pre_migration_state(db)
    w = World(db)
    size_a = _size(db, 65)
    size_b = _size(db, 28)
    invoice_a, line_a = _invoice(db, w, size=size_a)
    invoice_b, line_b = _invoice(db, w, size=size_b)
    ship_id = _shipment(db)
    _link(db, invoice_id=invoice_a, line_id=line_a, shipment_id=ship_id)
    _link(db, invoice_id=invoice_b, line_id=line_b, shipment_id=ship_id)

    _run_upgrade(db)

    db.expire_all()
    got = db.execute(
        text(f"SELECT container_size_id FROM {_SHIPMENTS} WHERE id = :id"), {"id": ship_id}
    ).scalar()
    assert got is None


def test_a_shipment_with_no_source_invoice_is_untouched(db):
    """The ordinary packing-list upload path, unrelated to any proforma invoice - the data
    step must not invent a size for it."""
    _drop_pre_migration_state(db)
    ship_id = _shipment(db)

    _run_upgrade(db)

    db.expire_all()
    got = db.execute(
        text(f"SELECT container_size_id FROM {_SHIPMENTS} WHERE id = :id"), {"id": ship_id}
    ).scalar()
    assert got is None
