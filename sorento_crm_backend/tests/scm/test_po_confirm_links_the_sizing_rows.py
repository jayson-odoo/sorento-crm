"""P7: confirming a purchase order links the rows that SIZED it, before anybody else.

`PLAN-scm-purchasing-uat-journey.md` P7. A purchase order raised off the plan is a buy for
particular plan ROWS, and a plan row is a `(product, location)` cell whose Project figure is
the un-linked remainder of the Order Inquiry rows sitting at it. The cascade on its own
walks the earliest open row by date across the WHOLE product, so a confirm could satisfy a
row at the other end of the country while the row that asked for the buy stayed raised and
the PO's "Allocated to" panel named a stranger.

The case is the captain's own: a plan row sized by two raised rows (5 + 3) against a PO line
of 8, with an OLDER raised row for the same product at a different warehouse. Two passes
must give the 8 to the two rows that sized it.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text

from app.services.scm.purchase_order_service import PurchaseOrderService
from tests.scm.conftest import requires_pg, seed_user
from tests.scm.test_channel_read_model import _confirmed_leg
from tests.scm.test_m3_run import _mk_product, _mk_warehouse

pytestmark = requires_pg

MARKER = "ZZTP7"


def _u() -> str:
    return str(uuid.uuid4())


def _linked_qty(db, row_id) -> float:
    return float(db.execute(text(
        "SELECT COALESCE(SUM(qty), 0) FROM projects.order_inquiry_links WHERE row_id = :r"
    ), {"r": row_id}).scalar() or 0)


def test_the_confirm_links_the_two_rows_that_sized_the_line_not_the_older_one(scm_app):
    _, db, _, _ = scm_app
    actor = seed_user(db, None)
    here = _mk_warehouse(db, f"{MARKER}-HERE")
    elsewhere = _mk_warehouse(db, f"{MARKER}-AWAY")
    pid = _mk_product(db, f"{MARKER}-SKU")

    # OLDEST first, so the plain cascade would reach for it before either of the two below.
    older = _confirmed_leg(db, product_id=pid, warehouse_id=elsewhere, buy_qty=9)
    five = _confirmed_leg(db, product_id=pid, warehouse_id=here, buy_qty=5)
    three = _confirmed_leg(db, product_id=pid, warehouse_id=here, buy_qty=3)

    poid = _u()
    db.execute(text(
        "INSERT INTO purchase_orders (id, po_number, status, issue_date, currency, "
        "source_system) VALUES (:i, :n, 'draft_recommendation', :d, 'MYR', "
        "'scm_recommendation')"),
        {"i": poid, "n": f"{MARKER}-{uuid.uuid4().hex[:8]}", "d": date(2026, 7, 1)})
    db.execute(text(
        "INSERT INTO purchase_order_lines (id, purchase_order_id, product_id, "
        "warehouse_id, qty_ordered, qty_received, unit_cost, currency, line_status) "
        "VALUES (:i, :po, :p, :w, 8, 0, 10, 'MYR', 'open')"),
        {"i": _u(), "po": poid, "p": pid, "w": here})
    db.flush()

    PurchaseOrderService(db).bulk_confirm([poid], actor=actor)

    assert _linked_qty(db, five["inquiry_row"].id) == 5.0
    assert _linked_qty(db, three["inquiry_row"].id) == 3.0
    assert _linked_qty(db, older["inquiry_row"].id) == 0.0, (
        "the older row at another warehouse took the buy the two rows at this one sized"
    )


def test_a_product_with_a_located_and_an_unlocated_line_does_not_kill_the_cascade(scm_app):
    """The `sorted(cells)` trap. Cells are `(product_id, warehouse_id | None)`, and a bare
    sort compares element by element - one line of a product with a warehouse and another
    without gives `str < None`, a TypeError, INSIDE the best-effort try. The whole cascade
    would be skipped and one log line left behind, which is the worst shape a defect can
    take: a confirm that reports success and links nothing.
    """
    _, db, _, _ = scm_app
    actor = seed_user(db, None)
    here = _mk_warehouse(db, f"{MARKER}-MIXED")
    pid = _mk_product(db, f"{MARKER}-MIXSKU")
    row = _confirmed_leg(db, product_id=pid, warehouse_id=here, buy_qty=4)

    poid = _u()
    db.execute(text(
        "INSERT INTO purchase_orders (id, po_number, status, issue_date, currency, "
        "source_system) VALUES (:i, :n, 'draft_recommendation', :d, 'MYR', "
        "'scm_recommendation')"),
        {"i": poid, "n": f"{MARKER}-{uuid.uuid4().hex[:8]}", "d": date(2026, 7, 1)})
    for warehouse in (here, None):
        db.execute(text(
            "INSERT INTO purchase_order_lines (id, purchase_order_id, product_id, "
            "warehouse_id, qty_ordered, qty_received, unit_cost, currency, line_status) "
            "VALUES (:i, :po, :p, :w, 4, 0, 10, 'MYR', 'open')"),
            {"i": _u(), "po": poid, "p": pid, "w": warehouse})
    db.flush()

    out = PurchaseOrderService(db).bulk_confirm([poid], actor=actor)

    assert out["confirmed_count"] == 1
    assert _linked_qty(db, row["inquiry_row"].id) == 4.0, (
        "the cascade was skipped, which is what the TypeError did silently"
    )


def test_rows_needed_at_reads_the_location_the_view_reads(scm_app):
    """The helper on its own: a row lands at the reconciled core line's warehouse, and a
    cell naming a DIFFERENT warehouse must not claim it."""
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    _, db, _, _ = scm_app
    here = _mk_warehouse(db, f"{MARKER}-NEEDA")
    elsewhere = _mk_warehouse(db, f"{MARKER}-NEEDB")
    pid = _mk_product(db, f"{MARKER}-NEEDSKU")
    row = _confirmed_leg(db, product_id=pid, warehouse_id=here, buy_qty=6)
    db.flush()

    service = ProjectOrderInquiryService(db)

    assert str(row["inquiry_row"].id) in service.rows_needed_at([(pid, here)])
    assert str(row["inquiry_row"].id) not in service.rows_needed_at([(pid, elsewhere)])
    assert service.rows_needed_at([(pid, None)]) == [], "a NULL cell claims a located row"
    assert service.rows_needed_at([]) == []
