"""One definition of "on order", from the purchase order's own side.

`test_outstanding_import_po_defects.py::test_every_reader_agrees_a_closed_po_line_is_not_incoming`
pins that a closed line stops counting. Two halves of the same fix are not covered there, and
both are the kind of thing a narrowing predicate breaks by accident:

* the closed line is still LISTED, carrying its `line_status`, so the screen can show it as
  closed. Dropping it from `lines` would be the other silent lie - the operator would see a
  quantity ordered with no line explaining it;
* a goods receipt still receives the OPEN lines. `create_gr` gaining a "skip closed" branch
  must not become "skip everything", which the defect test alone cannot tell apart: it only
  asserts that the cancelled line was left alone.

Rows are seeded directly rather than through the importer: the subject is the PO service's
reads, and a file would only add a second thing that could be wrong. `pg_session()` rolls back.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app.models.procurement import PurchaseOrder, PurchaseOrderLine
from app.services.scm.purchase_order_service import PurchaseOrderService
from tests._pg_fixture import pg_session
from tests.scm._outstanding_workbooks import Codes, make_codes, seed_catalogue


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def order(db) -> tuple[str, Codes, dict]:
    """An active purchase order with one open line (5) and one closed line (60)."""
    codes = make_codes()
    seed_catalogue(db, codes, doc_type="outstanding_po")
    po = PurchaseOrder(id=_u(), po_number=codes.main_po, status="active")
    db.add(po)
    db.flush()

    def _product(code: str) -> str:
        return str(db.execute(text("SELECT id FROM products WHERE product_code = :c"),
                              {"c": code}).scalar())

    lines = {
        "open": PurchaseOrderLine(id=_u(), purchase_order_id=po.id,
                                  product_id=_product(codes.item_new), qty_ordered=5,
                                  qty_received=0, line_status="open",
                                  expected_date=date(2026, 9, 1)),
        "closed": PurchaseOrderLine(id=_u(), purchase_order_id=po.id,
                                    product_id=_product(codes.item_wt), qty_ordered=60,
                                    qty_received=0, line_status="closed",
                                    expected_date=date(2026, 9, 30)),
    }
    db.add_all(list(lines.values()))
    db.flush()
    return po.id, codes, lines


def test_a_closed_line_is_still_listed_and_says_so(order, db):
    """Excluded from the totals, never hidden: a line that vanished from the detail page is
    indistinguishable from a line that never existed, and it was planned against."""
    po_id, codes, lines = order

    view = PurchaseOrderService(db).get_one(po_id)

    by_status = {ln["line_status"]: ln for ln in view["lines"]}
    assert set(by_status) == {"open", "closed"}, \
        "every line must be listed, each carrying its own status"
    assert by_status["closed"]["qty_ordered"] == 60.0
    # ... and it contributes to neither figure the plan reads.
    assert (view["total_qty"], view["line_count"]) == (5.0, 1)
    assert view["is_on_order"] is True, "the open line is still incoming"


def test_a_goods_receipt_still_receives_the_open_lines(order, db):
    """The control for "skip closed": it must skip the closed line and nothing else."""
    po_id, _codes, lines = order
    open_id, closed_id = lines["open"].id, lines["closed"].id

    PurchaseOrderService(db).create_gr(po_id)

    received = db.execute(text(
        "SELECT pol.id::text, pol.qty_received, pol.line_status, "
        "       (SELECT count(*) FROM picking_lines pl WHERE pl.po_line_id = pol.id) AS picked "
        "FROM purchase_order_lines pol WHERE pol.id::text = ANY(:ids)"
    ), {"ids": [str(open_id), str(closed_id)]}).mappings().all()
    rows = {r["id"]: r for r in received}

    assert (float(rows[str(open_id)]["qty_received"]), rows[str(open_id)]["picked"]) == (5.0, 1)
    assert rows[str(open_id)]["line_status"] == "received"
    assert (float(rows[str(closed_id)]["qty_received"]),
            rows[str(closed_id)]["picked"]) == (0.0, 0)
    assert rows[str(closed_id)]["line_status"] == "closed"
