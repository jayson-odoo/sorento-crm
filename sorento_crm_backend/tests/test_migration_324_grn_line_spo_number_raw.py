"""AC-FM-10 - migration 324 tested by running it, not by asserting on the live database.

The shared local database is a copy of production and is stamped on another
branch's lineage, so "does the column exist" there proves nothing. This builds
the PRE-migration shape on a scratch schema (the column and its index dropped,
because ``create_all`` already emits both from the model), seeds the three row
shapes the backfill has to tell apart, runs ``upgrade()``, and asserts what each
row ended up carrying:

- a line linked to an allocation takes that allocation's ``spo_number``;
- an unlinked line under a SINGLE-SPO GRN header takes the header value;
- an unlinked line under a MULTI-SPO header takes nothing, because a joined value
  names no single SPO and would put a claim on screen the matcher can never honour.
"""
from __future__ import annotations

import importlib.util
import uuid
from datetime import date
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from tests._pg_fixture import blank_session, unique_code

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "324_grn_line_spo_number_raw.py"
)

SINGLE_SPO = "SPO-2026/07-0012"
LINKED_SPO = "SPO-2026/07-0013"
MULTI_SPO = "SPO-2026/06-0020, SPO-2026/06-0021"


def _load_migration():
    spec = importlib.util.spec_from_file_location("m324", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_upgrade(db):
    module = _load_migration()
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        module.upgrade()
    return module


def _run_downgrade(db):
    module = _load_migration()
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        module.downgrade()


def _pre_migration_shape(db) -> None:
    """Undo what ``Base.metadata.create_all`` already emitted from the model."""
    db.execute(text("DROP INDEX IF EXISTS ix_picking_lines_spo_number_raw_key"))
    db.execute(text("ALTER TABLE picking_lines DROP COLUMN IF EXISTS spo_number_raw"))


def _product(db) -> str:
    """The FK chain Postgres actually enforces: category + uom + product."""
    cat, uom, pid = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO product_categories (id, category_code, category_name) "
            "VALUES (:i, :c, 'ZZT category')"
        ),
        {"i": cat, "c": unique_code("C")[:50]},
    )
    db.execute(
        text(
            "INSERT INTO units_of_measure (id, uom_code, uom_name) "
            "VALUES (:i, :c, 'Each')"
        ),
        {"i": uom, "c": unique_code("U")[:20]},
    )
    db.execute(
        text(
            "INSERT INTO products (id, product_code, product_name, category_id, "
            "base_uom_id, list_price, is_active) "
            "VALUES (:i, :c, 'ZZT product', :cat, :uom, 10, true)"
        ),
        {"i": pid, "c": unique_code("P")[:50], "cat": cat, "uom": uom},
    )
    return pid


def _warehouse(db) -> str:
    wid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO warehouses (id, warehouse_code, warehouse_name, is_active) "
            "VALUES (:i, :c, 'ZZT warehouse', true)"
        ),
        {"i": wid, "c": unique_code("W")[:50]},
    )
    return wid


def _allocation(db, *, product_id: str, warehouse_id: str, spo_number: str) -> str:
    shipment, aid = str(uuid.uuid4()), str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO inbound_shipments (id, shipment_number, shipment_date, "
            "shipment_status, synced_to_excel) VALUES (:i, :n, :d, 'pending', false)"
        ),
        {"i": shipment, "n": unique_code("SHP")[:50], "d": date(2026, 6, 1)},
    )
    db.execute(
        text(
            "INSERT INTO spo_allocations (id, spo_number, inbound_shipment_id, "
            "warehouse_id, product_id, allocated_quantity, quantity_received, "
            "quantity_rejected, receipt_status, synced_to_excel) "
            "VALUES (:i, :s, :sh, :w, :p, 100, 0, 0, 'pending', false)"
        ),
        {"i": aid, "s": spo_number, "sh": shipment, "w": warehouse_id, "p": product_id},
    )
    return aid


def _grn(db, spo_number: str | None) -> str:
    hid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO picking_headers (id, picking_number, spo_number, picking_type, "
            "picking_date, picking_status, inspection_status) "
            "VALUES (:i, :n, :s, 'goods_received', :d, 'approved', 'pending')"
        ),
        {"i": hid, "n": unique_code("GR")[:50], "s": spo_number, "d": date(2026, 7, 1)},
    )
    return hid


def _line(db, *, header_id: str, product_id: str, warehouse_id: str, allocation_id=None) -> str:
    lid = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO picking_lines (id, picking_header_id, spo_allocation_id, "
            "product_id, quantity_expected, quantity_picked, picked_condition, "
            "source_warehouse_id, synced_to_excel) "
            "VALUES (:i, :h, :a, :p, 10, 10, 'good', :w, false)"
        ),
        {"i": lid, "h": header_id, "a": allocation_id, "p": product_id, "w": warehouse_id},
    )
    return lid


def _raw(db, line_id: str):
    return db.execute(
        text("SELECT spo_number_raw FROM picking_lines WHERE id = :i"), {"i": line_id}
    ).scalar()


@pytest.fixture
def seeded():
    """The three shapes the backfill has to tell apart, on a pre-migration schema."""
    with blank_session() as db:
        _pre_migration_shape(db)
        product = _product(db)
        warehouse = _warehouse(db)
        allocation = _allocation(
            db, product_id=product, warehouse_id=warehouse, spo_number=LINKED_SPO
        )

        linked_header = _grn(db, SINGLE_SPO)
        single_header = _grn(db, SINGLE_SPO)
        multi_header = _grn(db, MULTI_SPO)
        blank_header = _grn(db, None)

        yield {
            "db": db,
            "allocation": allocation,
            "linked": _line(
                db,
                header_id=linked_header,
                product_id=product,
                warehouse_id=warehouse,
                allocation_id=allocation,
            ),
            "single": _line(
                db, header_id=single_header, product_id=product, warehouse_id=warehouse
            ),
            "multi": _line(
                db, header_id=multi_header, product_id=product, warehouse_id=warehouse
            ),
            "blank": _line(
                db, header_id=blank_header, product_id=product, warehouse_id=warehouse
            ),
        }


def test_a_linked_line_takes_its_allocations_spo_number(seeded):
    """Its allocation is the strongest possible evidence of what the sheet said,
    and it beats the header (which here names a DIFFERENT SPO)."""
    _run_upgrade(seeded["db"])

    assert _raw(seeded["db"], seeded["linked"]) == LINKED_SPO


def test_an_unlinked_line_under_a_single_spo_header_takes_the_header_value(seeded):
    _run_upgrade(seeded["db"])

    assert _raw(seeded["db"], seeded["single"]) == SINGLE_SPO


def test_an_unlinked_line_under_a_multi_spo_header_takes_nothing(seeded):
    """A joined value names no single SPO, so storing it would display a claim
    the scalar matcher can never honour."""
    _run_upgrade(seeded["db"])

    assert _raw(seeded["db"], seeded["multi"]) is None


def test_an_unlinked_line_under_a_header_with_no_spo_takes_nothing(seeded):
    _run_upgrade(seeded["db"])

    assert _raw(seeded["db"], seeded["blank"]) is None


def test_the_backfill_is_re_runnable_and_never_clobbers_a_later_value(seeded):
    """On a re-run, a value written by a LATER import is more authoritative than
    one re-derived from the header, so the guard is ``IS NULL``."""
    db = seeded["db"]
    _run_upgrade(db)
    db.execute(
        text("UPDATE picking_lines SET spo_number_raw = 'SPO-CORRECTED' WHERE id = :i"),
        {"i": seeded["single"]},
    )

    module = _load_migration()
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        module._backfill()

    assert _raw(db, seeded["single"]) == "SPO-CORRECTED"


def test_the_forward_matching_index_is_created_over_the_match_key(seeded):
    """The forward-matching query is exactly "unlinked lines whose stated SPO
    reduces to this key", so that is what is indexed."""
    _run_upgrade(seeded["db"])

    definition = seeded["db"].execute(
        text("SELECT indexdef FROM pg_indexes WHERE indexname = :n"),
        {"n": "ix_picking_lines_spo_number_raw_key"},
    ).scalar()

    assert definition is not None, "the partial functional index was not created"
    assert "upper(regexp_replace" in definition.replace(" ", " ").lower()
    assert "spo_allocation_id IS NULL" in definition


def test_downgrade_removes_the_column_and_the_index(seeded):
    db = seeded["db"]
    _run_upgrade(db)

    _run_downgrade(db)

    assert (
        db.execute(
            text(
                "SELECT 1 FROM information_schema.columns WHERE table_name = 'picking_lines' "
                "AND column_name = 'spo_number_raw' AND table_schema = current_schema()"
            )
        ).scalar()
        is None
    )
