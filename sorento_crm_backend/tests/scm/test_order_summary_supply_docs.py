"""issue #796 (PLAN-product-grain-project-buy-no-level.md Slice 3, AC-13..AC-15):
document numbers under the BRW PO qty and BRW incoming qty cells.

Owner: "the rows where we have BRW PO and BRW incoming quantity, better put down the PO and
SPO number as new lines below for traceability".

`_po_open_qty_map` / `_incoming_spo_qty_map` already total the open remainder at a SITE POOL
warehouse (`pool_predicate.ACTIVE_SITE_POOL_SQL`) - this slice makes both return the
per-document breakdown alongside the total, freezes it onto two NEW JSONB columns
(`OrderSummaryRow.po_open_docs` / `.incoming_spo_docs`, migration 508 alongside slice 2's
`suggestion`), and renders it under the totals in the PDF/xlsx export cells (indices 11 and
12 on the slice 2 16-column `_EXPORT_COLUMNS` layout).

A NEW file, not `test_order_summary_sheet.py` (the coder is mid-edit on slice 2's tests
there) - seeding is self-contained, reusing only the read-only `_product`/`_warehouse`/
`_run`/`_row` helpers from `test_product_grain_summary.py` (the same product-grain harness
slice 2's tests already reuse) plus local PO/SPO builders that take an EXPLICIT document
number, because the shared `_po`/`_spo` helpers elsewhere auto-generate one and this slice
is entirely about what that number renders as.

Every reference to `OrderSummaryRow.po_open_docs` / `.incoming_spo_docs` is deliberately
against a column the model does not carry yet - that is what makes the row-level tests fail
with AttributeError ("the feature does not exist yet") rather than a fixture bug. The two
export-shape tests (12, 13) work against hand-built row dicts, same idiom the slice 2 S14
tests use, so they are red on the OLD 14-column tuple shape alone, independent of whether
the DB column exists.

Postgres, marker-prefixed seeding, rolled back at teardown (`pg_session` via the `db`
fixture imported below). Nothing borrowed with LIMIT 1.
"""
from __future__ import annotations

import uuid

from app.models.inventory import Warehouse
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, SPOAllocation
from app.models.scm import ReorderRecommendation
from app.services.scm import summary_order_service as svc
from tests.scm.conftest import requires_pg
from tests.scm.test_product_grain_summary import _product, _row, _run, _warehouse, db  # noqa: F401

pytestmark = requires_pg

MARKER = "ZZTSDOC"


def _u() -> str:
    return str(uuid.uuid4())


def _project_bin(db) -> Warehouse:
    """A SITE-EXCLUDED warehouse (`segment='project'`) - the same shape
    `test_order_summary_sheet.py::_project_bin` builds, kept local so this file borrows
    nothing from a file the coder is mid-edit on."""
    wh = Warehouse(
        id=_u(), warehouse_code=f"{MARKER}-PBIN-{_u()[:8]}"[:30],
        warehouse_name="project bin", is_active=True, counts_as_available=True,
        segment="project",
    )
    db.add(wh)
    db.flush()
    return wh


def _open_po_line(db, product, wh, *, po_number, qty_ordered, qty_received=0) -> PurchaseOrder:
    """One open PO line, on its OWN purchase order, named exactly `po_number` - the shared
    `_po` helper elsewhere auto-generates a number, which this slice's whole point (the
    number reaching the cell) needs control over."""
    po = PurchaseOrder(id=_u(), po_number=po_number, status="active")
    db.add(po)
    db.flush()
    db.add(PurchaseOrderLine(
        id=_u(), purchase_order_id=po.id, product_id=product.id, warehouse_id=wh.id,
        qty_ordered=qty_ordered, qty_received=qty_received, line_status="open",
    ))
    db.flush()
    return po


def _spo_line(db, product, wh, *, spo_number, allocated, received=0) -> None:
    """One SPO allocation - the document IS the line (D3, no header table) - named exactly
    `spo_number` for the same reason `_open_po_line` takes an explicit `po_number`."""
    db.add(SPOAllocation(
        id=_u(), spo_number=spo_number, product_id=product.id,
        warehouse_id=(wh.id if wh else None),
        allocated_quantity=allocated, quantity_received=received,
    ))
    db.flush()


def _buy_rec(db, run, product, wh, *, rounded_qty=1) -> None:
    """A trivial `buy` recommendation, purely so the product reaches the book
    (`_belongs_on_the_book`) regardless of where Slice 1/2's own admission-gate work has
    landed - this slice is about the two supply-document cells, not book admission."""
    db.add(ReorderRecommendation(
        id=_u(), run_id=run.id, rec_type="buy", product_id=product.id,
        warehouse_id=wh.id, rounded_qty=rounded_qty, status="proposed",
    ))
    db.flush()


# =========================================================================== #
# test 11 (AC-13/AC-15): write_rows freezes the qty AND the per-document list
# =========================================================================== #

def test_write_rows_freezes_po_and_spo_document_breakdowns(db):
    """Two open PO lines on two different POs (PO-A owes 4, PO-B owes 1) and one open SPO
    allocation (SPO-X, 30) at the site pool - the book row's `po_open_qty` is 5 with
    `po_open_docs` naming both POs sorted by number, and `incoming_spo_qty` is 30 with
    `incoming_spo_docs` naming the one SPO. The serialised report row carries both lists
    too, for the on-screen grid (AC-11's sibling for these two columns).
    """
    run = _run(db, decision_grain="product", contract_version=1)
    wh = _warehouse(db)
    product = _product(db, stem="S796DOC")
    _buy_rec(db, run, product, wh)

    _open_po_line(db, product, wh, po_number="PO-A", qty_ordered=4)
    _open_po_line(db, product, wh, po_number="PO-B", qty_ordered=1)
    _spo_line(db, product, wh, spo_number="SPO-X", allocated=30)

    assert svc.write_rows(db, run.id) == 1
    row = _row(db, run, product)

    assert float(row.po_open_qty) == 5.0
    assert row.po_open_docs == [
        {"number": "PO-A", "qty": 4}, {"number": "PO-B", "qty": 1},
    ], "sorted by document number, qty is the open remainder of that document"
    assert float(row.incoming_spo_qty) == 30.0
    assert row.incoming_spo_docs == [{"number": "SPO-X", "qty": 30}]

    report_row = svc.report(db, run_id=run.id)["rows"][0]
    assert report_row["po_open_docs"] == row.po_open_docs
    assert report_row["incoming_spo_docs"] == row.incoming_spo_docs


# =========================================================================== #
# test 12 (AC-13/AC-14): export cell text/number shape
# =========================================================================== #

_FULL_ROW = {
    "product_code": "ZZTSDOC-SKU",
    "pool_on_hand": 100,
    "reorder_level": 250,
    "project_demand": 0,
    "project_customers": [],
    "dealer_outstanding": 0,
    "suggested_qty": 5,
    "suggestion": "below level: net 5 <= ROP 10",
    "chosen_qty": None,
    "delivery_by_month": [],
    "supplier_name": "Acme Supplier",
    "po_open_qty": 5,
    "po_open_docs": [{"number": "PO-A", "qty": 4}, {"number": "PO-B", "qty": 1}],
    "incoming_spo_qty": 30,
    "incoming_spo_docs": [{"number": "SPO-X", "qty": 30}],
    "last_receipt": None,
    "moq": None,
}

_EMPTY_DOCS_ROW = {
    **_FULL_ROW,
    "product_code": "ZZTSDOC-EMPTY",
    "po_open_qty": 0,
    "po_open_docs": [],
    "incoming_spo_qty": 0,
    "incoming_spo_docs": [],
}


def test_export_rows_and_xlsx_rows_render_document_breakdown_lines():
    """On the slice 2 16-column layout, BRW PO qty (index 11) and BRW incoming qty (index
    12) carry the total on the first line and one "<number> - <qty>" line per document
    below it (AC-13), in both the PDF's text shape (`_export_rows`) and the workbook's
    shape (`_export_xlsx_rows` - TEXT once documents exist, the one exception to the H1
    "quantities are numbers" rule). A row with nothing open keeps the bare numeric total,
    unchanged (AC-14): text "0" in `_export_rows`, numeric 0.0 in `_export_xlsx_rows`.
    """
    (text_row,) = svc._export_rows([_FULL_ROW])
    assert text_row[11] == "5\nPO-A - 4\nPO-B - 1"
    assert text_row[12] == "30\nSPO-X - 30"

    (text_empty,) = svc._export_rows([_EMPTY_DOCS_ROW])
    assert text_empty[11] == "0"
    assert text_empty[12] == "0"

    (xlsx_row,) = svc._export_xlsx_rows([_FULL_ROW])
    assert xlsx_row[11] == "5\nPO-A - 4\nPO-B - 1"
    assert xlsx_row[12] == "30\nSPO-X - 30"

    (xlsx_empty,) = svc._export_xlsx_rows([_EMPTY_DOCS_ROW])
    assert xlsx_empty[11] == 0.0, "no documents keeps the numeric total (H1), not text"
    assert xlsx_empty[12] == 0.0


# =========================================================================== #
# test 13 (AC-13): PDF renders one document per line
# =========================================================================== #

def test_export_pdf_html_renders_one_document_per_line():
    """The PDF's own two supply cells wrap one document per line - the same check the
    Delivery column's own S14 test makes
    (`test_s14_export_pdf_html_renders_a_two_month_delivery_cell_with_a_line_break`)."""
    rows = svc._export_rows([_FULL_ROW])
    html = svc._export_pdf_html(rows, "2026-09-10")
    assert "5\nPO-A - 4\nPO-B - 1" in html or "5<br>PO-A - 4<br>PO-B - 1" in html
    assert "30\nSPO-X - 30" in html or "30<br>SPO-X - 30" in html


# =========================================================================== #
# test 14 (AC-15): out-of-scope supply contributes nothing
# =========================================================================== #

def test_a_project_bin_po_and_a_fully_received_spo_contribute_nothing(db):
    """A PO line at a project bin - excluded by the SAME site-pool predicate the totals
    already use - and a fully-received SPO allocation at the pool (its open remainder is
    0) both contribute nothing to either the totals or the document lists. The pool
    predicate and the open-incoming clauses still apply to the new breakdown exactly as
    they do to the totals today (AC-15)."""
    run = _run(db, decision_grain="product", contract_version=1)
    pool_wh = _warehouse(db)
    project_wh = _project_bin(db)
    product = _product(db, stem="S796NIL")
    _buy_rec(db, run, product, pool_wh)

    _open_po_line(db, product, project_wh, po_number="PO-PROJECT", qty_ordered=9)
    _spo_line(db, product, pool_wh, spo_number="SPO-DONE", allocated=20, received=20)

    assert svc.write_rows(db, run.id) == 1
    row = _row(db, run, product)

    assert float(row.po_open_qty) == 0.0
    assert row.po_open_docs == []
    assert float(row.incoming_spo_qty) == 0.0
    assert row.incoming_spo_docs == []
