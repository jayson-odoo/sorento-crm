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
from datetime import date

from app.models.inventory import Warehouse
from app.models.procurement import (
    InboundShipment,
    PurchaseOrder,
    PurchaseOrderLine,
    SPOAllocation,
)
from app.models.scm import ReorderRecommendation
from app.services.scm import site_pool_supply
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

    # The substrings above pass whether or not the cell actually wraps - `_export_pdf_html`
    # only wraps (`class="list"`, `white-space: pre-line`) a column index listed in
    # `_PDF_LIST_COLUMNS`, so pin the indices AND the class on the cell itself, or removing
    # the wrap here stays green.
    assert 11 in svc._PDF_LIST_COLUMNS and 12 in svc._PDF_LIST_COLUMNS, (
        "BRW PO qty (11) and BRW incoming qty (12) must be in the wrapped set"
    )
    assert '<td class="list">5\nPO-A - 4\nPO-B - 1</td>' in html, (
        "the BRW PO qty cell itself must carry the list (wrap) class"
    )
    assert '<td class="list">30\nSPO-X - 30</td>' in html, (
        "the BRW incoming qty cell itself must carry the list (wrap) class"
    )


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


# =========================================================================== #
# review round: an over-received still-open PO line clamps at 0 per document
# =========================================================================== #

def test_an_over_received_still_open_po_line_clamps_at_zero_per_document(db):
    """Ruling (review round): an over-received but still-open PO line (`qty_received >
    qty_ordered`, so its own remainder is negative) must not subtract from the total and
    must not appear in the document list - clamp per document at 0, in both places, not
    only at the end. PO-A owes 4; PO-OVER's remainder is -3 (5 ordered, 8 received, still
    `line_status = 'open'`). The listed lines must keep summing to the printed total
    (AC-15): `po_open_qty` 4, `po_open_docs` naming PO-A alone.
    """
    run = _run(db, decision_grain="product", contract_version=1)
    wh = _warehouse(db)
    product = _product(db, stem="S796CLAMP")
    _buy_rec(db, run, product, wh)

    _open_po_line(db, product, wh, po_number="PO-A", qty_ordered=4)
    _open_po_line(db, product, wh, po_number="PO-OVER", qty_ordered=5, qty_received=8)

    assert svc.write_rows(db, run.id) == 1
    row = _row(db, run, product)

    assert float(row.po_open_qty) == 4.0, (
        "PO-OVER's negative remainder must be clamped at 0, not subtracted from PO-A's 4"
    )
    assert row.po_open_docs == [{"number": "PO-A", "qty": 4}], (
        "an over-received document has nothing open to list, so it is left off entirely"
    )


# =========================================================================== #
# S2 (PLAN-low-stock-report.md, low-stock-report-acceptance-criteria.md
# AC-20..AC-23, issue #888): the incoming cell NAMES THE CONTAINER
#
# The client's own `Stock Balance 28 Aug 2026.xls` writes the incoming cell as
# `TLLU8306312 - 180 nos` - the CONTAINER, not only the SPO number. So
# `open_spo_by_product` groups by `(spo_number, container)` where container is
# `COALESCE(NULLIF(spo_allocations.container_number, ''),
# inbound_shipments.shipping_container_number)`, each doc entry gains a
# `"container"` key when one is known, and `_docs_text` prints a three-part line.
#
# Written BEFORE the implementation exists (Phase 2 is test-first), so every
# reference below is to the CONTRACT in the plan, not to code that has been read.
# The new-behaviour tests are red today because `open_spo_by_product` selects a
# 3-tuple with no container in it and `_docs_text` has no third part to print.
#
# Seeding stays self-contained, reusing the same read-only `_product`/`_warehouse`
# helpers the file already borrows.
# =========================================================================== #

def _shipment(db, *, container, arrived=None) -> InboundShipment:
    """One inbound shipment carrying a container number - the SECOND of the two places a
    container can come from, and the one that covers 395 of the 920 open allocations
    measured on the 0907 copy (the plan's table).

    `actual_arrival_date` stays NULL: `spo_supply.open_incoming_clauses` drops a landed
    shipment from incoming supply entirely, so a fixture that set it would seed a row the
    query is right to ignore and the failure would read as a container bug.
    """
    shipment = InboundShipment(
        id=_u(),
        shipment_number=f"{MARKER}-SHIP-{_u()[:8]}"[:50],
        shipment_date=date(2026, 8, 28),
        actual_arrival_date=arrived,
        shipping_container_number=container,
    )
    db.add(shipment)
    db.flush()
    return shipment


def _spo_alloc(db, product, wh, *, spo_number, allocated, received=0,
               shipment=None, container_number=None) -> None:
    """`_spo_line`'s sibling that can also say WHICH container the line sits in - either
    on the allocation itself (`container_number`, set on 14 rows of the live copy and the
    value a person typed) or via the inbound shipment it was booked onto.

    A separate helper rather than more keyword arguments on `_spo_line`, so the four tests
    already in this file keep the builder they were written against.
    """
    db.add(SPOAllocation(
        id=_u(), spo_number=spo_number, product_id=product.id,
        warehouse_id=(wh.id if wh else None),
        inbound_shipment_id=(shipment.id if shipment else None),
        container_number=container_number,
        allocated_quantity=allocated, quantity_received=received,
    ))
    db.flush()


# --------------------------------------------------------------------------- AC-20

def test_open_spo_by_product_groups_by_spo_and_container(db):
    """AC-20: two allocations on the SAME SPO number, one booked onto a container and one
    not yet loaded, are TWO doc entries, not one - the buyer reads the incoming cell to
    find out which box the goods are in, and "SPO-A - 300" hides that half of it has a
    container number while half has not been loaded yet.

    The grouping key is `(spo_number, container)` and the entry carries `"container"`
    ONLY when one is known, so the not-yet-loaded half keeps exactly the shape it has
    today. `qty` totals are unchanged by the regrouping: 180 + 120 is still 300.

    Order follows the plan's sort key `(number, container or "")`, so the entry with no
    container sorts ahead of `TLLU8306312`.
    """
    wh = _warehouse(db)
    product = _product(db, stem="S888GRP")
    shipment = _shipment(db, container="TLLU8306312")

    _spo_alloc(db, product, wh, spo_number="SPO-A", allocated=200, received=20,
               shipment=shipment)                                # 180, in TLLU8306312
    _spo_alloc(db, product, wh, spo_number="SPO-A", allocated=120)   # 120, not loaded

    got = site_pool_supply.open_spo_by_product(db, [product.id])[str(product.id)]

    assert got["qty"] == 300.0, "regrouping must not change the total the cell prints"
    assert got["docs"] == [
        {"number": "SPO-A", "qty": 120},
        {"number": "SPO-A", "container": "TLLU8306312", "qty": 180},
    ], "one entry per (SPO number, container); no container key when none is known"


def test_spo_allocation_container_number_wins_over_shipment_container(db):
    """AC-20: `COALESCE(NULLIF(spo_allocations.container_number, ''),
    inbound_shipments.shipping_container_number)`, both halves of it.

    SPO-WIN carries a container on the ALLOCATION ('CMAU4318062') while its shipment says
    'OTHER' - the allocation wins, because that column is the value a person put on the
    line itself. SPO-BLANK carries an EMPTY STRING, which is not a container number: the
    `NULLIF` makes it fall through to the shipment's 'TLLU8306312' rather than printing a
    blank where a box number belongs.
    """
    wh = _warehouse(db)
    product = _product(db, stem="S888WIN")

    _spo_alloc(db, product, wh, spo_number="SPO-WIN", allocated=50,
               shipment=_shipment(db, container="OTHER"),
               container_number="CMAU4318062")
    _spo_alloc(db, product, wh, spo_number="SPO-BLANK", allocated=70,
               shipment=_shipment(db, container="TLLU8306312"),
               container_number="")

    docs = site_pool_supply.open_spo_by_product(db, [product.id])[str(product.id)]["docs"]

    assert docs == [
        {"number": "SPO-BLANK", "container": "TLLU8306312", "qty": 70},
        {"number": "SPO-WIN", "container": "CMAU4318062", "qty": 50},
    ], "the allocation's own container wins; an empty string is not a container"


def test_open_po_by_product_docs_carry_no_container_key(db):
    """AC-20: a PURCHASE ORDER has no container - the goods have not been shipped under
    one yet - so its doc entries keep exactly two keys and the PO half of the cell prints
    the way it does today (AC-21's last sentence). The plan hands `_grouped_supply_map` a
    4-tuple with `NULL AS container` from both callers so the two share one shape; that
    NULL must not become a `"container": None` key nobody can print.
    """
    wh = _warehouse(db)
    product = _product(db, stem="S888PO")
    _open_po_line(db, product, wh, po_number="PO-A", qty_ordered=4)

    docs = site_pool_supply.open_po_by_product(db, [product.id])[str(product.id)]["docs"]

    assert docs == [{"number": "PO-A", "qty": 4}]
    assert set(docs[0]) == {"number", "qty"}, (
        "a PO doc entry must carry no container key at all, not a null one"
    )


# --------------------------------------------------------------------------- AC-21

def test_docs_text_prints_spo_container_qty_when_container_known():
    """AC-21: `<SPO number> - <container> - <qty>` when a container is known, the existing
    `<SPO number> - <qty>` when it is not, and the first line stays the total.

    This is the client's own cell shape (`TLLU8306312 - 180 nos`) with the document number
    kept in front of it, because the sheet's cell has always named the document and the
    container is additional traceability, not a replacement for it.
    """
    assert svc._docs_text(380, [
        {"number": "SPO-A", "container": "TLLU8306312", "qty": 180},
        {"number": "SPO-B", "qty": 200},
    ]) == "380\nSPO-A - TLLU8306312 - 180\nSPO-B - 200"


# --------------------------------------------------------------------------- AC-22

_CONTAINER_ROW = {
    **_FULL_ROW,
    "product_code": "ZZTSDOC-CONTAINER",
    "incoming_spo_qty": 380,
    "incoming_spo_docs": [
        {"number": "SPO-A", "container": "TLLU8306312", "qty": 180},
        {"number": "SPO-B", "qty": 200},
    ],
}


def test_export_rows_and_xlsx_rows_render_container_lines():
    """AC-22: the order sheet PDF and Excel both show the new line shape in "BRW incoming
    qty" (index 12) - and EVERY OTHER CELL is byte-identical to what the same row renders
    today. The container is one cell's worth of change; comparing against the file's
    existing `_FULL_ROW` tuple is what says so, rather than asserting the new cell alone
    and leaving the other fifteen unwatched.
    """
    base_text, = svc._export_rows([_FULL_ROW])
    text_row, = svc._export_rows([_CONTAINER_ROW])
    assert text_row[12] == "380\nSPO-A - TLLU8306312 - 180\nSPO-B - 200"
    assert text_row[1:12] == base_text[1:12], "no other PDF cell may move"
    assert text_row[13:] == base_text[13:], "no other PDF cell may move"

    base_xlsx, = svc._export_xlsx_rows([_FULL_ROW])
    xlsx_row, = svc._export_xlsx_rows([_CONTAINER_ROW])
    assert xlsx_row[12] == "380\nSPO-A - TLLU8306312 - 180\nSPO-B - 200"
    assert xlsx_row[1:12] == base_xlsx[1:12], "no other workbook cell may move"
    assert xlsx_row[13:] == base_xlsx[13:], "no other workbook cell may move"


# --------------------------------------------------------------------------- AC-23

def test_frozen_docs_without_container_key_still_print():
    """AC-23: no migration. A run frozen BEFORE this slice has `incoming_spo_docs` entries
    of the old `{number, qty}` shape, and re-opening its order sheet must still print
    `SPO-A - 200` rather than raising a KeyError or printing "SPO-A - None - 200".

    Green before the slice and green after is the whole point: it is the pin that stops
    the new printer from assuming the key is always there.
    """
    frozen_row = {
        **_FULL_ROW,
        "product_code": "ZZTSDOC-FROZEN",
        "incoming_spo_qty": 200,
        "incoming_spo_docs": [{"number": "SPO-A", "qty": 200}],
    }
    text_row, = svc._export_rows([frozen_row])
    assert text_row[12] == "200\nSPO-A - 200"
    assert svc._docs_text(200, [{"number": "SPO-A", "qty": 200}]) == "200\nSPO-A - 200"
