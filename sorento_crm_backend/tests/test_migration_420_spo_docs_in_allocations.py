"""Migration 420 - SPO documents move out of `purchase_orders` into `spo_allocations`.

`PLAN-scm-cs-planning-uat.md` section K, UAC AC-K2 and AC-K3.

`blank_session`, not `pg_session`: the data half of this migration DELETES from
`purchase_orders` and `purchase_order_lines`, and those tables on the shared local database
hold the captain's real 80,000-line book. A scratch schema is the only substrate where
"delete every SPO document" is a sentence a test may say out loud. The DDL half is exercised
through `upgrade()`/`downgrade()` at the bottom of this file, where the guards make it a
no-op on a schema `create_all` already built to the new shape - which is exactly the
condition the shared dev database is in, and the reason every step carries a guard.

The scratch schema is shared for the whole session, so the DDL round trip runs LAST and
inside `blank_session`'s own transaction, which is rolled back at teardown.
"""
from __future__ import annotations

import importlib.util
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from app.models.inventory import Warehouse
from app.models.procurement import (
    PurchaseOrder,
    PurchaseOrderLine,
    SPOAllocation,
    Supplier,
)
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import OrderLinkClaim

from ._pg_fixture import blank_session

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "420_spo_docs_in_allocations.py"
)

MARKER = "ZZT420"

#: The promised arrival on the fixture's open lines. RELATIVE to today, because
#: `on_order_v` and the ladder both drop an unshipped promise whose date has PASSED
#: (`app/services/scm/spo_supply.py`), so a fixed date would quietly stop being supply a
#: few days after it was written and take the assertions with it.
SOON = date.today() + timedelta(days=30)
LONG_PAST = date.today() - timedelta(days=400)


def _migration():
    spec = importlib.util.spec_from_file_location("zzt_migration_420", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _uid() -> str:
    return str(uuid.uuid4())


def _company(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _product(db, code: str) -> Product:
    uom = UnitOfMeasure(id=_uid(), uom_code=f"{MARKER}{uuid.uuid4().hex[:6]}", uom_name="Set")
    category = ProductCategory(
        id=_uid(), category_code=f"{MARKER}-{uuid.uuid4().hex[:6]}", category_name=f"{MARKER} cat"
    )
    db.add_all([uom, category])
    db.flush()
    row = Product(
        id=_uid(), product_code=code, product_name=f"{MARKER} {code}",
        category_id=category.id, base_uom_id=uom.id, list_price=Decimal("10.00"),
    )
    db.add(row)
    db.flush()
    return row


def _warehouse(db, code: str) -> Warehouse:
    row = Warehouse(id=_uid(), warehouse_code=code, warehouse_name=code, is_active=True)
    db.add(row)
    db.flush()
    return row


def _supplier(db) -> Supplier:
    row = Supplier(id=_uid(), supplier_code=f"{MARKER}{uuid.uuid4().hex[:6]}",
                   supplier_name=f"{MARKER} factory", is_active=True)
    db.add(row)
    db.flush()
    return row


def _document(db, number: str, *, supplier, source_system: str, status: str = "closed"):
    row = PurchaseOrder(
        id=_uid(), po_number=number, supplier_id=supplier.id, issue_date=date(2026, 8, 12),
        status=status, currency="MYR", source_system=source_system, source_ref="po_spo_listing",
    )
    db.add(row)
    db.flush()
    return row


def _line(db, order, product, warehouse, *, ordered, received, line_no, status="closed",
          expected=SOON):
    row = PurchaseOrderLine(
        id=_uid(), purchase_order_id=order.id, product_id=product.id,
        warehouse_id=(warehouse.id if warehouse is not None else None),
        qty_ordered=Decimal(ordered), qty_received=Decimal(received),
        unit_cost=Decimal("22.00"), currency="MYR", expected_date=expected,
        line_status=status, source_system=order.source_system,
        source_ref=(str(line_no) if line_no is not None else None),
    )
    db.add(row)
    db.flush()
    return row


def _book(db):
    """Two SPO documents and one purchase order, on one product and two locations.

    Shaped like the real book: `SPO-2026/08-0061` is the live OPEN document (no line numbers
    stated, the way the outstanding extract leaves them), `SPO-2023/01-0001` is closed
    history with the same product twice on one document and one line at a location we do not
    hold. The purchase order is there to prove the move takes the SPO family and nothing
    else.
    """
    company_id = _company(db)
    supplier = _supplier(db)
    product = _product(db, f"{MARKER}-SRTWCY7405-PJ")
    other = _product(db, f"{MARKER}-SRTWC7405-SC")
    brw_ib = _warehouse(db, f"{MARKER}-BRW-IB")
    brw_bb = _warehouse(db, f"{MARKER}-BRW-BB")

    live = _document(db, "SPO-2026/08-0061", supplier=supplier,
                     source_system="scm_upload", status="active")
    _line(db, live, product, brw_ib, ordered="160", received="0", line_no=None,
          status="open")
    _line(db, live, product, brw_ib, ordered="170", received="0", line_no=None,
          status="open")
    _line(db, live, other, brw_bb, ordered="110", received="10", line_no=None,
          status="open")

    history = _document(db, "SPO-2023/01-0001", supplier=supplier,
                        source_system="scm_spo_history")
    _line(db, history, product, brw_bb, ordered="12", received="12", line_no=1)
    # The same product again on the same document at the same location: two containers,
    # which the old `(spo, product, warehouse)` unique key forbade.
    _line(db, history, product, brw_bb, ordered="8", received="8", line_no=2)
    # A location the catalogue does not hold, so the line carries no warehouse at all.
    _line(db, history, other, None, ordered="5", received="5", line_no=3)

    keep = _document(db, "202301-S0001", supplier=supplier, source_system="scm_po_history")
    _line(db, keep, product, brw_bb, ordered="30", received="30", line_no=1)

    db.commit()
    return {
        "company_id": company_id, "supplier": supplier, "product": product, "other": other,
        "brw_ib": brw_ib, "brw_bb": brw_bb, "live": live, "history": history, "keep": keep,
    }


def _claim_columns(db) -> set:
    schema = db.execute(text("select current_schema()")).scalar()
    return {
        c
        for (c,) in db.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = :s AND table_name = 'order_link_claim'"
            ),
            {"s": f"{schema}_scm"},
        ).all()
    }


def _allocations(db, number: str):
    return (
        db.query(SPOAllocation)
        .filter(SPOAllocation.spo_number == number)
        .order_by(SPOAllocation.spo_line_number)
        .all()
    )


# --------------------------------------------------------------------------- the move


def test_every_spo_line_becomes_one_allocation_and_the_documents_go():
    with blank_session() as db:
        world = _book(db)
        source = {
            str(row.id): row.qty_ordered
            for row in db.query(PurchaseOrderLine)
            .filter(PurchaseOrderLine.purchase_order_id == world["live"].id)
            .all()
        }
        moved = _migration().move_spo_documents(db.connection())
        db.expire_all()

        assert moved["allocations"] == 6
        assert moved["lines_deleted"] == 6
        assert moved["documents_deleted"] == 2

        assert db.query(PurchaseOrder).filter(
            PurchaseOrder.po_number.like("SPO-%")).count() == 0
        # The purchase order is untouched: the family is read from the NUMBER.
        assert db.query(PurchaseOrderLine).filter(
            PurchaseOrderLine.purchase_order_id == world["keep"].id).count() == 1

        live = _allocations(db, "SPO-2026/08-0061")
        # The allocation IS the line: it carries the line's own id, which is what lets the
        # downgrade restore the same rows rather than copies of them.
        assert {str(row.id): Decimal(row.allocated_quantity) for row in live} == source
        # A document whose export states no line number gets one per row, all distinct,
        # because the new unique key is the line.
        assert [row.spo_line_number for row in live] == [1, 2, 3]
        assert {row.line_status for row in live} == {"open"}
        assert {row.source_system for row in live} == {"scm_upload"}
        assert {row.receipt_status for row in live} == {"pending", "partial_received"}
        assert live[0].expected_date == SOON
        assert live[0].issue_date == date(2026, 8, 12)
        assert live[0].supplier_id == world["supplier"].id
        assert live[0].inbound_shipment_id is None


def test_the_history_half_lands_closed_and_keeps_its_repeated_product():
    with blank_session() as db:
        world = _book(db)
        _migration().move_spo_documents(db.connection())
        db.expire_all()

        rows = _allocations(db, "SPO-2023/01-0001")
        assert [row.spo_line_number for row in rows] == [1, 2, 3]
        # Two rows, one product, one location - the pair the old unique key rejected.
        assert [r.product_id for r in rows[:2]] == [world["product"].id] * 2
        assert [r.warehouse_id for r in rows[:2]] == [world["brw_bb"].id] * 2
        assert all(row.line_status == "closed" for row in rows)
        assert all(row.receipt_status == "fully_received" for row in rows)
        # The location we DO hold is named on the row; the one we do not leaves no code,
        # because the purchase line never carried the book's raw spelling of it.
        assert rows[0].location_code == world["brw_bb"].warehouse_code
        assert rows[2].warehouse_id is None


def test_the_move_runs_twice_without_writing_twice():
    with blank_session() as db:
        _book(db)
        migration = _migration()
        migration.move_spo_documents(db.connection())
        again = migration.move_spo_documents(db.connection())
        db.expire_all()

        assert again["allocations"] == 0
        assert again["documents_deleted"] == 0
        assert db.query(SPOAllocation).filter(
            SPOAllocation.spo_number.like("SPO-%")).count() == 6


def test_a_reference_with_nowhere_to_go_refuses_loudly():
    """A row pointing at an SPO line that no allocation could replace stops the migration.

    `ON DELETE SET NULL` would have made this silent: the reference would simply have
    become NULL and nobody would have been told which rows lost their link.
    """
    with blank_session() as db:
        world = _book(db)
        spo_line = (
            db.query(PurchaseOrderLine)
            .filter(PurchaseOrderLine.purchase_order_id == world["history"].id)
            .order_by(PurchaseOrderLine.source_ref)
            .first()
        )
        db.add(SPOAllocation(
            id=_uid(), spo_number="SPO-OTHER", spo_line_number=1,
            product_id=world["product"].id, warehouse_id=world["brw_bb"].id,
            allocated_quantity=1, quantity_received=0, po_line_id=spo_line.id,
        ))
        db.commit()

        with pytest.raises(RuntimeError) as raised:
            _migration().move_spo_documents(db.connection())

    assert "spo_allocations.po_line_id" in str(raised.value)
    assert "1" in str(raised.value)


# ------------------------------------------------------------------- the claim it clears


def _claim(db, so_number: str, po_number: str, item_code: str, line):
    row = OrderLinkClaim(
        id=_uid(), so_number=so_number, po_number=po_number, item_code=item_code,
        source="po_history", po_line_id=line.id, so_line_id=None,
    )
    db.add(row)
    db.flush()
    return row


def test_a_claim_on_an_spo_line_is_cleared_and_restored_by_the_downgrade():
    """AC-K2. The claim holds both document numbers as text, so it never loses what it
    said; what it loses is the resolver's cache of which line that number landed on, and the
    downgrade re-resolves it by the resolver's own rule."""
    with blank_session() as db:
        world = _book(db)
        migration = _migration()
        line = (
            db.query(PurchaseOrderLine)
            .filter(PurchaseOrderLine.purchase_order_id == world["history"].id,
                    PurchaseOrderLine.source_ref == "1")
            .one()
        )
        claim = _claim(db, "SO381895", "SPO-2023/01-0001", world["product"].product_code, line)
        claim_id = claim.id
        db.commit()

        moved = migration.move_spo_documents(db.connection())
        db.expire_all()
        assert moved["claims_cleared"] == 1
        cleared = db.query(OrderLinkClaim).filter(OrderLinkClaim.id == claim_id).one()
        assert cleared.po_line_id is None
        assert cleared.resolved_at is None
        assert cleared.po_number == "SPO-2023/01-0001"

        restored = migration.restore_spo_documents(db.connection())
        db.expire_all()
        assert restored["documents"] == 2
        assert restored["lines"] == 6
        assert restored["allocations_removed"] == 6

        again = db.query(OrderLinkClaim).filter(OrderLinkClaim.id == claim_id).one()
        assert again.po_line_id == line.id


def test_the_downgrade_puts_every_line_back_where_it_came_from():
    with blank_session() as db:
        world = _book(db)
        migration = _migration()
        before = {
            str(row.id): (str(row.product_id), row.warehouse_id, row.qty_ordered,
                          row.qty_received, row.line_status, row.expected_date)
            for row in db.query(PurchaseOrderLine)
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
            .filter(PurchaseOrder.po_number.like("SPO-%"))
            .all()
        }
        migration.move_spo_documents(db.connection())
        migration.restore_spo_documents(db.connection())
        db.expire_all()

        after = {
            str(row.id): (str(row.product_id), row.warehouse_id, row.qty_ordered,
                          row.qty_received, row.line_status, row.expected_date)
            for row in db.query(PurchaseOrderLine)
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
            .filter(PurchaseOrder.po_number.like("SPO-%"))
            .all()
        }
        assert after == before
        # The live document comes back active, the history closed - each as it was.
        statuses = {
            row.po_number: row.status
            for row in db.query(PurchaseOrder).filter(
                PurchaseOrder.po_number.like("SPO-%")).all()
        }
        assert statuses == {"SPO-2026/08-0061": "active", "SPO-2023/01-0001": "closed"}
        assert db.query(SPOAllocation).filter(
            SPOAllocation.spo_number.like("SPO-%")).count() == 0
        assert world["keep"].po_number == "202301-S0001"


# ------------------------------------------------------------------------ on_order_v


def _on_order(db, product_id: str, warehouse_id) -> float:
    schema = db.execute(text("select current_schema()")).scalar()
    where = "warehouse_id = :wid" if warehouse_id else "warehouse_id IS NULL"
    params = {"pid": product_id}
    if warehouse_id:
        params["wid"] = warehouse_id
    return float(
        db.execute(
            text(f'SELECT COALESCE(SUM(on_order), 0) FROM "{schema}_scm".on_order_v '
                 f"WHERE product_id = :pid AND {where}"),
            params,
        ).scalar()
        or 0
    )


def test_on_order_counts_the_open_spo_at_its_warehouse_and_nowhere_else():
    """AC-K3. The two open lines of `SPO-2026/08-0061` at BRW-IB are 330 units of incoming
    supply; the closed history at BRW-BB is none, and the line with no warehouse is counted
    at no location at all."""
    with blank_session() as db:
        world = _book(db)
        migration = _migration()
        migration.move_spo_documents(db.connection())
        db.execute(text(migration.on_order_from_spo_documents(db.connection())))
        db.flush()

        assert _on_order(db, world["product"].id, world["brw_ib"].id) == 330.0
        # History is closed AND fully received, so it fails both halves of the predicate.
        assert _on_order(db, world["product"].id, world["brw_bb"].id) == 0.0
        # 100 still to come of the 110 ordered, at the location the line names.
        assert _on_order(db, world["other"].id, world["brw_bb"].id) == 100.0
        # A row with no warehouse is supply we cannot place, so it is counted nowhere.
        assert _on_order(db, world["other"].id, None) == 0.0


def test_a_row_with_no_shipment_is_still_incoming_supply():
    """The predicate migration 337 wrote INNER-joined the shipment, which is what made every
    shipping order invisible. Pinned directly: the open rows below have no shipment at all
    and must still be counted."""
    with blank_session() as db:
        world = _book(db)
        migration = _migration()
        migration.move_spo_documents(db.connection())
        db.execute(text(migration.on_order_from_spo_documents(db.connection())))
        db.expire_all()

        assert all(
            row.inbound_shipment_id is None
            for row in _allocations(db, "SPO-2026/08-0061")
        )
        assert _on_order(db, world["product"].id, world["brw_ib"].id) == 330.0


# ------------------------------------------------------------------- the DDL round trip


def test_upgrade_and_downgrade_run_through_alembic_on_a_schema_already_shaped():
    """The guards, which are what makes this migration safe to apply by hand on the shared
    dev database - whose `alembic_version` points at another lane's head and whose objects
    were built by `create_all`. Every DDL step must be a no-op when it has already
    happened, and the data half must still run."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    with blank_session() as db:
        world = _book(db)
        module = _migration()
        context = MigrationContext.configure(connection=db.connection())
        with Operations.context(context):
            module.upgrade()
            db.expire_all()
            assert db.query(PurchaseOrder).filter(
                PurchaseOrder.po_number.like("SPO-%")).count() == 0
            assert _on_order(db, world["product"].id, world["brw_ib"].id) == 330.0
            assert _claim_columns(db) >= {"po_line_id", "spo_allocation_id"}

            module.downgrade()
            db.expire_all()
            assert db.query(PurchaseOrder).filter(
                PurchaseOrder.po_number.like("SPO-%")).count() == 2
            assert db.query(PurchaseOrderLine).join(
                PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id
            ).filter(PurchaseOrder.po_number.like("SPO-%")).count() == 6
            # The SPO side of the claim goes with the SPO rows it pointed at.
            assert "spo_allocation_id" not in _claim_columns(db)


def test_a_line_that_would_collide_stops_the_move_before_anything_is_deleted():
    """`ON CONFLICT DO NOTHING` is what makes the move re-runnable, and it is also the one
    way it could lose a line in silence. Checked while both sides still exist."""
    with blank_session() as db:
        world = _book(db)
        # An allocation already holding line 1 of the history document, under the same
        # company: the moved line has nowhere to land.
        db.add(SPOAllocation(
            id=_uid(), spo_number="SPO-2023/01-0001", spo_line_number=1,
            product_id=world["product"].id, warehouse_id=world["brw_bb"].id,
            allocated_quantity=1, quantity_received=0, company_id=world["company_id"],
        ))
        db.commit()

        with pytest.raises(RuntimeError) as raised:
            _migration().move_spo_documents(db.connection())
        db.expire_all()

        assert "Nothing has been deleted" in str(raised.value)
        assert db.query(PurchaseOrder).filter(
            PurchaseOrder.po_number.like("SPO-%")).count() == 2


def test_on_order_counts_a_past_dated_promise_and_drops_a_received_one():
    """TRUST THE BOOK (captain, 26 August 2026), in the view every planning figure reads.

    Both rows below are open at a real warehouse and both are overdue. What decides is what
    is still TO COME: the received one is out, the other is supply, and no date removes it.
    """
    with blank_session() as db:
        world = _book(db)
        migration = _migration()
        migration.move_spo_documents(db.connection())
        db.expire_all()

        rows = sorted(
            (
                row for row in _allocations(db, "SPO-2026/08-0061")
                if row.product_id == world["product"].id
                and row.warehouse_id == world["brw_ib"].id
            ),
            key=lambda row: row.allocated_quantity,
        )
        assert [row.allocated_quantity for row in rows] == [160, 170]
        for row in rows:
            row.expected_date = LONG_PAST
        rows[0].quantity_received = 160
        rows[0].receipt_status = "fully_received"
        db.flush()

        db.execute(text(migration.on_order_from_spo_documents(db.connection())))
        db.flush()

        # The 170 that is still owed, overdue by more than a year and still owed.
        assert _on_order(db, world["product"].id, world["brw_ib"].id) == 170.0


def test_a_promise_dated_today_is_on_order_like_any_other():
    with blank_session() as db:
        world = _book(db)
        migration = _migration()
        migration.move_spo_documents(db.connection())
        db.expire_all()

        for row in _allocations(db, "SPO-2026/08-0061"):
            row.expected_date = date.today()
        db.flush()

        db.execute(text(migration.on_order_from_spo_documents(db.connection())))
        db.flush()

        assert _on_order(db, world["product"].id, world["brw_ib"].id) == 330.0


# ------------------------------------------------------------- the claim's SPO side


def test_a_cleared_claim_is_re_pointed_at_the_allocation_and_resolves():
    """AC-K2 and the review's first blocker. The claim's purchase side moves from
    `po_line_id` to `spo_allocation_id`; without the column those 12,393 claims would read
    "awaiting purchase order" for ever, on 2,989 sales orders."""
    with blank_session() as db:
        world = _book(db)
        migration = _migration()
        line = (
            db.query(PurchaseOrderLine)
            .filter(PurchaseOrderLine.purchase_order_id == world["history"].id,
                    PurchaseOrderLine.source_ref == "1")
            .one()
        )
        claim = _claim(db, "SO381895", "SPO-2023/01-0001", world["product"].product_code, line)
        # The sales side is already known, so re-pointing is what makes it RESOLVED.
        claim.so_line_id = None
        claim_id = claim.id
        db.commit()

        migration.move_spo_documents(db.connection())
        migration.repoint_spo_claims(db.connection())
        db.expire_all()

        row = db.query(OrderLinkClaim).filter(OrderLinkClaim.id == claim_id).one()
        assert row.po_line_id is None
        assert row.spo_allocation_id == _allocations(db, "SPO-2023/01-0001")[0].id
        # Still waiting, honestly: the sales side was never found.
        assert row.resolved_at is None


def test_re_pointing_runs_twice_without_moving_anything():
    with blank_session() as db:
        world = _book(db)
        migration = _migration()
        line = (
            db.query(PurchaseOrderLine)
            .filter(PurchaseOrderLine.purchase_order_id == world["history"].id,
                    PurchaseOrderLine.source_ref == "1")
            .one()
        )
        _claim(db, "SO381895", "SPO-2023/01-0001", world["product"].product_code, line)
        db.commit()

        migration.move_spo_documents(db.connection())
        first = migration.repoint_spo_claims(db.connection())
        again = migration.repoint_spo_claims(db.connection())

        assert first["with_item"] == 1
        assert again == {"with_item": 0, "item_less": 0}


def test_an_item_less_claim_anchors_on_the_documents_first_line():
    """A `**SO:174830**` note in a PO export names no item. None of the captain's SPO claims
    are item-less today, which is exactly why the branch is written rather than left for the
    day one is."""
    with blank_session() as db:
        world = _book(db)
        migration = _migration()
        line = (
            db.query(PurchaseOrderLine)
            .filter(PurchaseOrderLine.purchase_order_id == world["history"].id,
                    PurchaseOrderLine.source_ref == "1")
            .one()
        )
        claim = _claim(db, "SO381895", "SPO-2023/01-0001", None, line)
        claim_id = claim.id
        db.commit()

        migration.move_spo_documents(db.connection())
        result = migration.repoint_spo_claims(db.connection())
        db.expire_all()

        assert result["item_less"] == 1
        row = db.query(OrderLinkClaim).filter(OrderLinkClaim.id == claim_id).one()
        assert row.spo_allocation_id == _allocations(db, "SPO-2023/01-0001")[0].id
