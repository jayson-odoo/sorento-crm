"""Applying the outstanding PURCHASE-ORDER book writes purchase orders, not sales orders.

This file exists because of a live corruption. `outstanding_import_service` is doc-type aware
only in its READER: `preview()` correctly parses the PO extract, and then `_existing_lines()`
and `apply()` query and write `SalesOrder` / `SalesOrderLine` unconditionally, including
literally `SalesOrder(so_number=<the PO number>, ...)`. So uploading the supply book through
`POST /api/v1/scm/outstanding/purchase-orders/apply` invented sales DEMAND out of incoming
SUPPLY - the plan's two inputs, with the sign flipped. Nothing caught it.

The first test below is therefore the one that must never go green-to-red again: after
applying the PO book, no `sales_orders` row carries a PO number. Every other test here pins
what the PO path must actually do, and the last one pins that the SO path is unchanged by
whatever it takes to get there.

Same discipline as the SO service tests. Every product, warehouse, supplier, order and line
is seeded by the test under codes the test generates
(`tests/scm/_outstanding_workbooks.py`), and the upload is generated from the SAME codes, so
the file and the rows cannot drift apart and nothing is borrowed with `LIMIT 1` off a table
that is empty in CI. Everything runs inside `pg_session()`, which rolls back.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.services.scm import outstanding_import_service as svc
from app.services.scm.outstanding_reader import PO, SO
from tests._pg_fixture import pg_session
from tests.scm._outstanding_workbooks import (
    MARKER,
    SUPPLIER_ALT_LABEL,
    SUPPLIER_MAIN_LABEL,
    Codes,
    make_codes,
    po_week1,
    po_week2,
    po_workbook,
    seed_catalogue,
    seed_suppliers,
    week1,
)

# A short header set for the one-off files, mapped by the `outstanding_po` aliases.
_MINIMAL = ("PO NO", "CREDITOR CODE", "ITEM CODE", "QTY ORDERED", "ETA", "STOCK LOCATION")

# The captain's real "PO & SPO outstanding.xlsx" shape: a CREDITOR NAME column and no
# CREDITOR CODE column at all.
_NAME_ONLY = ("PO NO", "CREDITOR NAME", "ITEM CODE", "QTY ORDERED", "ETA", "STOCK LOCATION")
# No creditor evidence whatsoever - neither a code nor a name column.
_NO_CREDITOR = ("PO NO", "ITEM CODE", "QTY ORDERED", "ETA", "STOCK LOCATION")


def _name_only_workbook(rows):
    return po_workbook(rows, headers=_NAME_ONLY)


def _slug(name: str) -> str:
    """The same rule `outstanding_import_service._supplier_slug` applies to a fresh name:
    upper-cased alphanumerics only, nothing else. Recomputed here rather than imported, so
    the test pins the OBSERVABLE behaviour rather than calling the function under test."""
    return "".join(ch for ch in name.upper() if ch.isalnum())


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def codes() -> Codes:
    return make_codes()


@pytest.fixture()
def seeded(db, codes):
    """Products, warehouses and suppliers under the exact codes this test's upload names."""
    seed_catalogue(db, codes, doc_type="outstanding_po")
    seed_suppliers(db, codes)
    return codes


# --------------------------------------------------------------------------- #
# readers. Raw SQL on purpose: the assertion must see what actually landed in the
# table, including a row that landed in the WRONG table.
# --------------------------------------------------------------------------- #

def _po_lines(db, po_number, item):
    return db.execute(text(
        """
        SELECT (pol.qty_ordered - pol.qty_received) AS outstanding,
               pol.expected_date, pol.line_status, pol.qty_ordered, pol.qty_received,
               pol.unit_cost, pol.currency, w.warehouse_code
        FROM purchase_order_lines pol
        JOIN purchase_orders po ON po.id = pol.purchase_order_id
        JOIN products p ON p.id = pol.product_id
        LEFT JOIN warehouses w ON w.id = pol.warehouse_id
        WHERE po.po_number = :po AND p.product_code = :item
        ORDER BY pol.expected_date NULLS LAST
        """
    ), {"po": po_number, "item": item}).mappings().fetchall()


def _po_line_ids(db, po_number, item):
    return {str(r[0]) for r in db.execute(text(
        "SELECT pol.id FROM purchase_order_lines pol "
        "JOIN purchase_orders po ON po.id = pol.purchase_order_id "
        "JOIN products p ON p.id = pol.product_id "
        "WHERE po.po_number = :po AND p.product_code = :item"
    ), {"po": po_number, "item": item}).fetchall()}


def _supplier_of(db, po_number):
    """(supplier_code, supplier_name) on the purchase order header, or (None, None)."""
    row = db.execute(text(
        "SELECT s.supplier_code, s.supplier_name FROM purchase_orders po "
        "LEFT JOIN suppliers s ON s.id = po.supplier_id "
        "WHERE po.po_number = :po"
    ), {"po": po_number}).fetchone()
    assert row is not None, f"no purchase order was created for {po_number}"
    return (row[0], row[1])


def _ordered(db, item):
    """What `scm.po_ordered_v` counts as ORDERED for this item, across warehouses.

    Not `on_order_v`, which is now the SPO allocation: incoming stock (decision, 6 Aug 2026,
    migration 337). What the PO importer writes is an ORDER placed with a supplier, and the
    view that counts those is the right observable for a test about the PO book.
    """
    return float(db.execute(text(
        "SELECT COALESCE(SUM(oo.ordered), 0) FROM scm.po_ordered_v oo "
        "JOIN products p ON p.id = oo.product_id WHERE p.product_code = :item"
    ), {"item": item}).scalar())


def _counts(db):
    return db.execute(text(
        "SELECT (SELECT count(*) FROM purchase_orders), "
        "       (SELECT count(*) FROM purchase_order_lines), "
        "       (SELECT count(*) FROM sales_orders), "
        "       (SELECT count(*) FROM sales_order_lines)"
    )).fetchone()


# --------------------------------------------------------------------------- #
# 1. the regression: the PO book must never reach the sales-order tables
# --------------------------------------------------------------------------- #

def test_applying_the_purchase_order_book_writes_no_sales_order(db, seeded):
    """The corruption, asserted directly on the table that was being written.

    `apply()` took `doc_type` only to choose the READER and to stamp `source_ref`; the write
    path had no branch on it at all, so a PO number was inserted as `sales_orders.so_number`
    and its lines as sales demand. Incoming supply counted as customer commitment is the
    worst possible failure for a planning module: it moves the net position by twice the
    quantity, in the wrong direction.
    """
    before = _counts(db)

    svc.apply(db, po_week1(seeded), PO)

    after = _counts(db)
    assert db.execute(text(
        "SELECT count(*) FROM sales_orders WHERE so_number IN (:a, :b)"
    ), {"a": seeded.main_po, "b": seeded.alt_po}).scalar() == 0, \
        "a purchase order number was written into sales_orders"
    assert after[2] == before[2], "the PO upload created sales orders"
    assert after[3] == before[3], "the PO upload created sales order lines"
    assert after[0] == before[0] + 2, "the two purchase orders were not created"
    assert after[1] == before[1] + 5, "the five purchase order lines were not created"


# --------------------------------------------------------------------------- #
# 2. what the line has to carry for the plan to use it
# --------------------------------------------------------------------------- #

def test_apply_creates_the_purchase_orders_and_lines(db, seeded):
    out = svc.apply(db, po_week1(seeded), PO)

    assert out["ok"] and out["applied"]["added"] == 5
    assert out["scope_documents"] == list(seeded.po_documents)
    # Reported counts are not evidence on their own: the broken version returns exactly
    # these while writing five sales order lines, so the rows are counted too.
    assert db.execute(text(
        "SELECT count(*) FROM purchase_order_lines pol "
        "JOIN purchase_orders po ON po.id = pol.purchase_order_id "
        "WHERE po.po_number = :po"
    ), {"po": seeded.main_po}).scalar() == 3
    assert db.execute(text(
        "SELECT count(*) FROM purchase_order_lines pol "
        "JOIN purchase_orders po ON po.id = pol.purchase_order_id "
        "WHERE po.po_number = :po"
    ), {"po": seeded.alt_po}).scalar() == 2


def test_the_line_carries_the_outstanding_quantity_not_the_ordered_quantity(db, seeded):
    """The file states 150 ordered against 15 received. What is still coming is 135.

    Asserted as the DIFFERENCE `qty_ordered - qty_received`, because that is the expression
    `scm.on_order_v` sums - it is the number the plan reads, whichever way the two columns
    are filled.
    """
    svc.apply(db, po_week1(seeded), PO)

    rows = _po_lines(db, seeded.main_po, seeded.item_rl)
    assert [(float(r["outstanding"]), r["expected_date"]) for r in rows] == [
        (135.0, date(2026, 7, 1)),
        (72.0, date(2026, 8, 3)),
    ]


def test_the_line_carries_the_stock_location_and_the_expected_arrival(db, seeded):
    svc.apply(db, po_week1(seeded), PO)

    project = _po_lines(db, seeded.main_po, seeded.item_wt)
    assert [(r["warehouse_code"], r["expected_date"]) for r in project] == [
        (seeded.loc_project, date(2026, 9, 30))
    ]
    dealer = _po_lines(db, seeded.alt_po, seeded.item_wt)
    assert [(r["warehouse_code"], r["expected_date"]) for r in dealer] == [
        (seeded.loc_dealer, date(2026, 10, 30))
    ]


def test_the_supplier_is_resolved_from_the_creditor_code(db, seeded):
    """Who is late is the whole point of an expediting list, so the creditor code has to
    resolve to a real supplier rather than being carried as a string."""
    svc.apply(db, po_week1(seeded), PO)

    assert _supplier_of(db, seeded.main_po) == (seeded.creditor_main, SUPPLIER_MAIN_LABEL)
    assert _supplier_of(db, seeded.alt_po) == (seeded.creditor_alt, SUPPLIER_ALT_LABEL)


def test_unit_cost_and_currency_persist_when_the_file_supplies_them(db, seeded):
    """Cost is what the cash co-pilot ranks on. A row that leaves the columns empty stays
    empty rather than acquiring a guessed zero, which would read as free goods."""
    svc.apply(db, po_week1(seeded), PO)

    priced = _po_lines(db, seeded.main_po, seeded.item_rl)
    assert [(float(r["unit_cost"]), r["currency"]) for r in priced] == [
        (12.5, "MYR"), (12.5, "MYR")
    ]

    unpriced = _po_lines(db, seeded.main_po, seeded.item_wt)
    assert unpriced[0]["unit_cost"] is None, "an empty unit cost became a number"
    assert unpriced[0]["currency"] is None

    foreign = _po_lines(db, seeded.alt_po, seeded.item_blue)
    assert (float(foreign[0]["unit_cost"]), foreign[0]["currency"]) == (0.85, "USD")


# --------------------------------------------------------------------------- #
# 3. supplier resolution: reported, and back-created (never for an item)
# --------------------------------------------------------------------------- #

def test_an_unknown_creditor_code_is_reported_and_back_created_as_a_minimal_supplier(
    db, seeded
):
    """A creditor code AutoCount has not reconciled against the supplier master yet is not a
    typo - 2,177 of 5,243 PO-book documents in the captain's own file arrived exactly this
    way. `apply()` creates a minimal supplier for it (code + name, `is_active=True`) and
    links the document, but the code is still reported so the operator sees which ones this
    run invented rather than discovering it later.

    Contrast `test_outstanding_import.py`'s item-code rule, which this file does NOT change:
    an unknown item code is still never invented, because a typo there becomes a SKU that
    gets planned and bought - a creditor code carries no such risk.
    """
    unknown = f"{MARKER}-CRX-{uuid.uuid4().hex[:8]}".upper()
    file = po_workbook(
        [
            [seeded.main_po, seeded.creditor_main, seeded.item_rl, 10, date(2026, 7, 1),
             seeded.loc_project],
            [seeded.alt_po, unknown, seeded.item_wt, 5, date(2026, 7, 1),
             seeded.loc_project],
        ],
        headers=_MINIMAL,
    )

    res = svc.preview(db, file, PO)

    assert [(i.row_number, i.field, i.value) for i in res.resolution_issues] == [
        (3, "creditor_code", unknown)
    ]
    assert db.execute(text("SELECT count(*) FROM suppliers WHERE supplier_code = :c"),
                      {"c": unknown}).scalar() == 0, "preview must not write"

    out = svc.apply(db, file, PO)

    assert db.execute(text("SELECT count(*) FROM suppliers WHERE supplier_code = :c"),
                      {"c": unknown}).scalar() == 1
    # `_MINIMAL` carries no SUPPLIER name column, so the created row's name falls back to
    # the code itself - the file supplied nothing else to call it.
    assert _supplier_of(db, seeded.alt_po) == (unknown, unknown)
    assert out["suppliers_created"] == 1
    assert out["suppliers_created_codes"] == [unknown]


def test_the_same_unknown_code_twice_in_one_file_creates_one_supplier(db, seeded):
    """One upload, one creation per distinct code - not one per row or one per document."""
    unknown = f"{MARKER}-CRX-{uuid.uuid4().hex[:8]}".upper()
    file = po_workbook(
        [
            [seeded.main_po, unknown, seeded.item_rl, 10, date(2026, 7, 1),
             seeded.loc_project],
            [seeded.alt_po, unknown, seeded.item_wt, 5, date(2026, 7, 1),
             seeded.loc_project],
        ],
        headers=_MINIMAL,
    )

    out = svc.apply(db, file, PO)

    assert db.execute(text("SELECT count(*) FROM suppliers WHERE supplier_code = :c"),
                      {"c": unknown}).scalar() == 1
    assert out["suppliers_created"] == 1
    assert _supplier_of(db, seeded.main_po)[0] == unknown
    assert _supplier_of(db, seeded.alt_po)[0] == unknown


def test_an_existing_supplier_is_matched_case_insensitively_not_duplicated(db, seeded):
    """A creditor code the master already holds, spelled in a different case, must attach to
    the existing row - not spawn a second one under the file's own casing."""
    file = po_workbook(
        [[seeded.main_po, seeded.creditor_main.lower(), seeded.item_rl, 10,
          date(2026, 7, 1), seeded.loc_project]],
        headers=_MINIMAL,
    )

    out = svc.apply(db, file, PO)

    assert out["suppliers_created"] == 0
    assert db.execute(text("SELECT count(*) FROM suppliers WHERE upper(supplier_code) = :c"),
                      {"c": seeded.creditor_main.upper()}).scalar() == 1
    assert _supplier_of(db, seeded.main_po) == (seeded.creditor_main, SUPPLIER_MAIN_LABEL)


def test_a_line_whose_creditor_was_unknown_still_counts_as_incoming_supply(db, seeded):
    """The judgement call, stated explicitly so it can be argued with rather than inferred.

    An unresolvable ITEM or STOCK LOCATION skips the line, because a quantity with no product
    cannot be planned and a quantity in the wrong warehouse makes every coverage number for
    that location wrong. An unresolvable CREDITOR is different: the quantity and the arrival
    date are still true, so the line lands and a minimal supplier is created for the code
    instead of leaving `purchase_orders.supplier_id` unset - dropping the line, or leaving it
    permanently unlinked, would make on-order UNDERSTATE supply, which is what causes a
    second, unnecessary purchase.
    """
    unknown = f"{MARKER}-CRX-{uuid.uuid4().hex[:8]}".upper()
    file = po_workbook(
        [[seeded.alt_po, unknown, seeded.item_wt, 5, date(2026, 7, 1), seeded.loc_dealer]],
        headers=_MINIMAL,
    )

    out = svc.apply(db, file, PO)

    assert out["applied"]["added"] == 1
    assert _supplier_of(db, seeded.alt_po) == (unknown, unknown)
    assert _ordered(db, seeded.item_wt) == 5.0


# --------------------------------------------------------------------------- #
# 4. preview writes nothing
# --------------------------------------------------------------------------- #

def test_preview_of_the_po_book_writes_nothing_to_either_side(db, seeded):
    """Both tables are counted, not just the purchase-order one: the bug being fixed wrote to
    the OTHER pair, so a count of only `purchase_order_lines` would have stayed green."""
    before = _counts(db)
    res = svc.preview(db, po_week1(seeded), PO)
    after = _counts(db)

    assert res.ok and res.counts["added"] == 5
    assert res.scope_documents == seeded.po_documents
    assert res.resolution_issues == []
    assert before == after, "preview must not write"


def test_apply_matches_what_preview_promised(db, seeded):
    """A preview computed differently from the commit is a preview that lies."""
    svc.apply(db, po_week1(seeded), PO)

    promised = svc.preview(db, po_week2(seeded), PO).counts
    actual = svc.apply(db, po_week2(seeded), PO)["counts"]

    assert promised == actual


# --------------------------------------------------------------------------- #
# 5. the diff semantics carry over
# --------------------------------------------------------------------------- #

def test_the_second_upload_reads_as_moves_and_changes_not_as_churn(db, seeded):
    """A slipped ETA is the single most common thing this module exists to react to, so it
    must read as one line moving, not as one line closed plus a different one added."""
    svc.apply(db, po_week1(seeded), PO)

    counts = svc.preview(db, po_week2(seeded), PO).counts

    assert counts["date_moved"] == 1
    assert counts["qty_changed"] == 1
    assert counts["added"] == 1
    assert counts["closed"] == 1
    assert counts["unchanged"] == 2
    assert counts["date_and_qty_changed"] == 0


def test_a_moved_eta_updates_the_line_in_place(db, seeded):
    svc.apply(db, po_week1(seeded), PO)
    ids_before = _po_line_ids(db, seeded.main_po, seeded.item_rl)

    svc.apply(db, po_week2(seeded), PO)

    rows = _po_lines(db, seeded.main_po, seeded.item_rl)
    assert [(float(r["outstanding"]), r["expected_date"]) for r in rows] == [
        (135.0, date(2026, 7, 15)),   # slipped two weeks, same row
        (90.0, date(2026, 8, 3)),     # grew 72 -> 90, did not move
    ]
    assert _po_line_ids(db, seeded.main_po, seeded.item_rl) == ids_before, \
        "the line was replaced instead of updated"


def test_a_line_absent_from_an_in_scope_po_is_closed_not_deleted(db, seeded):
    """The line was planned against; erasing it makes last week's plan unexplainable."""
    svc.apply(db, po_week1(seeded), PO)
    svc.apply(db, po_week2(seeded), PO)

    rows = _po_lines(db, seeded.main_po, seeded.item_wt)
    assert [r["line_status"] for r in rows] == ["closed"]


def test_a_purchase_order_outside_the_file_is_untouched(db, seeded):
    """A single-supplier export must not read as every other supplier having delivered."""
    svc.apply(db, po_week1(seeded), PO)

    unrelated = f"{MARKER}-POX-{uuid.uuid4().hex[:8]}".upper()
    other = PurchaseOrder(id=_u(), po_number=unrelated, status="active")
    db.add(other)
    db.flush()
    pid = db.execute(text("SELECT id FROM products WHERE product_code = :c"),
                     {"c": seeded.item_new}).scalar()
    db.add(PurchaseOrderLine(id=_u(), purchase_order_id=other.id, product_id=str(pid),
                             qty_ordered=500, qty_received=0, line_status="open",
                             expected_date=date(2026, 12, 1)))
    db.flush()

    svc.apply(db, po_week2(seeded), PO)

    rows = _po_lines(db, unrelated, seeded.item_new)
    assert [(float(r["outstanding"]), r["line_status"]) for r in rows] == [(500.0, "open")]


def test_reapplying_the_same_file_changes_nothing(db, seeded):
    """Uploading twice by accident must be a no-op, not a doubling.

    Run on BOTH weeks, because the second run also proves a closed line stays closed: if
    `_existing_lines` still returned it, week 2 re-applied would report the close a second
    time, and if the diff missed it the line would be resurrected as an add.
    """
    svc.apply(db, po_week1(seeded), PO)
    again = svc.apply(db, po_week1(seeded), PO)
    assert again["applied"] == {"added": 0, "updated": 0, "closed": 0, "unchanged": 5}

    svc.apply(db, po_week2(seeded), PO)
    once_more = svc.apply(db, po_week2(seeded), PO)
    assert once_more["applied"] == {"added": 0, "updated": 0, "closed": 0, "unchanged": 5}

    assert db.execute(text(
        "SELECT count(*) FROM purchase_order_lines pol "
        "JOIN purchase_orders po ON po.id = pol.purchase_order_id "
        "WHERE po.po_number IN (:a, :b) AND pol.line_status = 'open'"
    ), {"a": seeded.main_po, "b": seeded.alt_po}).scalar() == 5


def test_a_part_received_line_is_not_silently_unreceived(db, seeded):
    """The extract states what is OUTSTANDING. Writing it straight into `qty_ordered` would
    erase a receipt that has already been booked in, and the goods would be counted as still
    at sea."""
    svc.apply(db, po_week1(seeded), PO)
    line = db.execute(text(
        "SELECT pol.id FROM purchase_order_lines pol "
        "JOIN purchase_orders po ON po.id = pol.purchase_order_id "
        "JOIN products p ON p.id = pol.product_id "
        "WHERE po.po_number = :po AND p.product_code = :item "
        "  AND pol.expected_date = '2026-08-03'"
    ), {"po": seeded.main_po, "item": seeded.item_rl}).scalar()
    assert line is not None, "week 1 wrote no purchase order line to book a receipt against"
    db.execute(text("UPDATE purchase_order_lines SET qty_received = 20 WHERE id = :i"),
               {"i": str(line)})
    db.flush()

    # Week 2 states 90 still outstanding on that line.
    svc.apply(db, po_week2(seeded), PO)

    ordered, received = db.execute(text(
        "SELECT qty_ordered, qty_received FROM purchase_order_lines WHERE id = :i"
    ), {"i": str(line)}).fetchone()
    assert float(received) == 20.0, "a booked receipt must never be rewritten"
    assert float(ordered) == 110.0, "ordered = already received 20 + still outstanding 90"


# --------------------------------------------------------------------------- #
# 6. closing a line has to stop it counting as supply
# --------------------------------------------------------------------------- #

def test_applying_the_po_book_makes_the_lines_count_as_incoming_supply(db, seeded):
    """Nothing else in this file would notice if the orders landed as drafts.

    `scm.on_order_v` counts a line only when its order's `status` is one of
    ('active','received','partial','closed') - drafts are deliberately NOT supply (M4-D5).
    An outstanding-PO extract is a book of PLACED orders, so its rows have to be visible to
    that view, and asserting the on-order figure pins it without pinning a status string.
    """
    svc.apply(db, po_week1(seeded), PO)

    assert _ordered(db, seeded.item_rl) == 207.0    # 135 + 72, both at the project location
    assert _ordered(db, seeded.item_blue) == 7646.0


def test_a_closed_po_line_stops_counting_as_incoming_supply(db, seeded):
    """The point of closing, and the PO analogue of the SO side's `committed_v` assertion.

    What "closed" has to mean here took working out, because `scm.on_order_v` does NOT look
    at `line_status` - it filters on `po.status IN ('active','received','partial','closed')`
    and `pol.qty_ordered > pol.qty_received`, and nothing else. So of the three ways to make
    the view drop a line:

    * flipping the ORDER's status is wrong - the other lines on that purchase order are still
      coming, and one arrived container would erase the whole order from supply;
    * setting `qty_received = qty_ordered` is wrong - it fabricates a receipt no GRN
      supports, and `scm.receipt_lead_v` and the picking reconciliation both read that
      column. It is also exactly what the SO side refuses to do to `qty_delivered`;
    * so the line is closed with `line_status = 'closed'` (retaining it, because it was
      planned against) and `scm.on_order_v` must gain the `pol.line_status = 'open'`
      predicate that migration 311 already added to `scm.committed_v` for the same reason.

    That is a view change, deliberately: two readers disagreeing about what "on order" means
    is the failure that makes a planning report untrustworthy. Both halves are asserted, and
    they fail separately - the receipt column must be untouched AND the figure must drop.
    """
    svc.apply(db, po_week1(seeded), PO)
    before = _ordered(db, seeded.item_wt)

    svc.apply(db, po_week2(seeded), PO)
    after = _ordered(db, seeded.item_wt)

    assert before == 67.0, "60 on the main PO plus 7 on the alt PO"
    assert after == 7.0, "the main PO's line closed; only the alt PO's remains"

    closed = _po_lines(db, seeded.main_po, seeded.item_wt)[0]
    assert closed["line_status"] == "closed"
    assert float(closed["qty_received"]) == 0.0, \
        "closing a line invented a receipt: nothing arrived, the line simply left the book"


# --------------------------------------------------------------------------- #
# 7. the sales-order path is unaffected
# --------------------------------------------------------------------------- #

def test_the_sales_order_path_still_writes_sales_orders(db, codes):
    """Whatever it takes to make the PO path write purchase orders must not be a swap.

    Guards the obvious wrong fix (branching one way and forgetting the other) and the subtle
    one (a shared write helper that now stamps the wrong table for both).
    """
    seed_catalogue(db, codes, doc_type="outstanding_so")

    out = svc.apply(db, week1(codes), SO)

    assert out["ok"] and out["applied"]["added"] == 5
    assert db.execute(text(
        "SELECT count(*) FROM sales_order_lines sol "
        "JOIN sales_orders so ON so.id = sol.sales_order_id "
        "WHERE so.so_number = :so"
    ), {"so": codes.project_so}).scalar() == 3
    assert db.execute(text(
        "SELECT count(*) FROM purchase_orders WHERE po_number IN (:a, :b)"
    ), {"a": codes.project_so, "b": codes.dealer_so}).scalar() == 0, \
        "a sales order number was written into purchase_orders"


# --------------------------------------------------------------------------- #
# 8. supplier resolution by NAME, when the file states no creditor CODE at all
#
# The captain's real "PO & SPO outstanding.xlsx" carries no CREDITOR CODE column - only
# CREDITOR NAME, spelled with AutoCount's own trailing currency note ("XIAMEN TAIYANG
# TECHNOLOGY CO.,LTD (RMB)", "AFANNI FAUCET WARE （RMB)" - note the mismatched full-width
# open paren). The by-code path above never fires on these files at all: `party_code` is
# blank on every row, so this is a second, independent path through `_resolve`/`apply`.
# --------------------------------------------------------------------------- #

def test_a_name_only_creditor_matches_an_existing_supplier_case_insensitively(db, seeded):
    """The master holds the clean legal name, never the currency-suffixed one - so the
    suffix has to come off before the match, or every supplier the file names looks
    unknown and gets duplicated."""
    clean_name = f"{MARKER} XIAMEN TAIYANG TECHNOLOGY {uuid.uuid4().hex[:6]}".upper()
    code = f"{MARKER}-SC-{uuid.uuid4().hex[:8]}".upper()
    db.add(Supplier(id=_u(), supplier_code=code, supplier_name=clean_name, is_active=True))
    db.flush()

    file = _name_only_workbook([
        [seeded.main_po, f"{clean_name} (RMB)", seeded.item_rl, 10, date(2026, 7, 1),
         seeded.loc_project],
    ])

    out = svc.apply(db, file, PO)

    assert out["suppliers_created"] == 0
    assert _supplier_of(db, seeded.main_po) == (code, clean_name)


def test_full_width_parens_and_lower_case_are_both_handled(db, seeded):
    """Mismatched paren styles (full-width open, ASCII close) and a differently-cased file
    value must resolve to the same supplier as the clean master name."""
    clean_name = f"{MARKER} AFANNI FAUCET WARE {uuid.uuid4().hex[:6]}".upper()
    code = f"{MARKER}-SC-{uuid.uuid4().hex[:8]}".upper()
    db.add(Supplier(id=_u(), supplier_code=code, supplier_name=clean_name, is_active=True))
    db.flush()

    file = _name_only_workbook([
        [seeded.alt_po, f"{clean_name.title()} （RMB)", seeded.item_wt, 5, date(2026, 7, 1),
         seeded.loc_dealer],
    ])

    out = svc.apply(db, file, PO)

    assert out["suppliers_created"] == 0
    assert _supplier_of(db, seeded.alt_po) == (code, clean_name)


def test_an_unknown_creditor_name_is_back_created_with_a_slug_code(db, seeded):
    """No master row named this creditor at all - a minimal supplier is back-created with
    the CLEANED name (the currency suffix is AutoCount's own notation, never part of the
    legal name, so it appears nowhere in what gets stored) and a deterministic code
    derived from it, since the file gave no code to use."""
    unknown = f"{MARKER} Y CO {uuid.uuid4().hex[:6]}".upper()
    file = _name_only_workbook([
        [seeded.alt_po, f"{unknown} （RMB)", seeded.item_wt, 5, date(2026, 7, 1),
         seeded.loc_dealer],
    ])

    out = svc.apply(db, file, PO)

    assert out["suppliers_created"] == 1
    assert out["suppliers_created_codes"] == [unknown]
    assert _supplier_of(db, seeded.alt_po) == (_slug(unknown), unknown)


def test_the_same_creditor_name_twice_in_one_file_creates_one_supplier(db, seeded):
    """One upload, one creation per distinct CLEANED name - the same rule the code path
    already follows, stated for the name fallback. Different currency notes on the two
    rows must not read as two different creditors."""
    unknown = f"{MARKER} DUPNAME {uuid.uuid4().hex[:6]}".upper()
    file = _name_only_workbook([
        [seeded.main_po, f"{unknown} (RMB)", seeded.item_rl, 10, date(2026, 7, 1),
         seeded.loc_project],
        [seeded.alt_po, f"{unknown} (USD)", seeded.item_wt, 5, date(2026, 7, 1),
         seeded.loc_dealer],
    ])

    out = svc.apply(db, file, PO)

    assert out["suppliers_created"] == 1
    assert _supplier_of(db, seeded.main_po)[1] == unknown
    assert _supplier_of(db, seeded.alt_po)[1] == unknown


def test_no_code_and_no_name_leaves_the_document_unlinked_and_creates_nothing(db, seeded):
    """A file with no creditor evidence at all must not invent one - the document lands
    with the quantity and date intact and simply no supplier attached, same as an
    unresolvable code would leave it."""
    file = po_workbook(
        [[seeded.main_po, seeded.item_rl, 10, date(2026, 7, 1), seeded.loc_project]],
        headers=_NO_CREDITOR,
    )

    out = svc.apply(db, file, PO)

    assert out["applied"]["added"] == 1
    assert out["suppliers_created"] == 0
    assert _supplier_of(db, seeded.main_po) == (None, None)


def test_reuploading_a_name_only_file_is_idempotent(db, seeded):
    """A second upload of the same name-only file must create nothing new and keep the
    same link - the point of the by-code path's own idempotency test, restated for the
    fallback."""
    unknown = f"{MARKER} REUP CO {uuid.uuid4().hex[:6]}".upper()
    file = _name_only_workbook([
        [seeded.main_po, f"{unknown} (RMB)", seeded.item_rl, 10, date(2026, 7, 1),
         seeded.loc_project],
    ])

    first = svc.apply(db, file, PO)
    second = svc.apply(db, file, PO)

    assert first["suppliers_created"] == 1
    assert second["suppliers_created"] == 0
    assert _supplier_of(db, seeded.main_po) == (_slug(unknown), unknown)
    assert db.execute(text("SELECT count(*) FROM suppliers WHERE supplier_name = :n"),
                      {"n": unknown}).scalar() == 1
