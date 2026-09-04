"""The upload is the ORDER BOOK - outstanding or completed - not an outstanding list.

A row whose remaining quantity is zero used to be filed as "nothing outstanding" and
dropped, on the theory that a settled line is reached by its ABSENCE from the next upload.
That theory only holds for a file that states the open half of the book. The captain's real
export does not: `PO & SPO 2026.xlsx` is a whole year, 21,445 rows, every one of them with
`Remaining Qty` 0, and it imported NOTHING (job b1a41d40 filed 21,030 rows as
`nothing_outstanding`). The document existed, the quantities were stated, the money was
stated, and the system was left with no record of any of it.

So a netted row that states nothing still outstanding is a REAL LINE:

  * `qty_ordered` = the file's Qty,
  * `qty_delivered` / `qty_received` = the Transferred figure (or the whole Qty when the
    file states only Qty and a Remaining of 0),
  * `line_status` = closed, and a document whose every line is closed is closed too, which
    is what the screen words as Completed.

What must NOT change is the diff that the rest of the module is built on: absence still
closes a line, and added / qty_changed / date_moved / closed still mean what they meant. A
completed document the database has never seen is `added`; an open line the new book states
as fully delivered is `closed` - and it is closed WITH its delivered figure filled in,
rather than merely flagged.

A row with a single netted quantity column reading 0 stays a skip: there is no ordered
figure anywhere in it, so the only line it could produce would be a zero that states
nothing.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app.services import import_outcome_codes as oc
from app.services.import_alias_service import AliasResolver
from app.services.import_outcome import ImportOutcome
from app.services.scm import outstanding_import_service as svc
from app.services.scm.outstanding_reader import PO, SO, read_workbook
from tests._pg_fixture import pg_session
from tests.scm._outstanding_workbooks import (
    Codes,
    make_codes,
    seed_catalogue,
    seed_suppliers,
    so_headers,
    so_row,
    workbook,
)

#: The AutoCount detail listing, sales-order side: the ordered quantity, what has already
#: gone out, and what is left. All three, which is what makes a settled row readable.
#: `ORDER TYPE` is here because since QP1 an SO upload naming an order nothing can classify
#: is refused outright, and `300-T012` carries no market segment - a test about settled
#: quantities must not be measuring the refusal instead.
SO_HEADERS = so_headers("S/O NO", "SO DATE", "DEBTOR CODE", "ITEM CODE", "UOM", "QTY",
                        "TRANSFERED QTY", "REMAINING QTY", "UNIT PRICE", "DELIVERY DATE",
                        "STOCK LOCATION")

#: The same shape on the purchase side.
PO_HEADERS = ("PO NO", "PO DATE", "CREDITOR CODE", "SUPPLIER", "ITEM CODE", "UOM",
              "QTY ORDERED", "QTY RECEIVED", "REMAINING QTY", "UNIT COST", "ETA",
              "STOCK LOCATION")

#: A file that states ONE netted quantity and nothing else - no ordered figure to write.
SO_SINGLE_QTY = ("S/O NO", "DEBTOR CODE", "ITEM CODE", "QTY", "DELIVERY DATE",
                 "STOCK LOCATION")


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def seeded(db) -> Codes:
    codes = make_codes()
    seed_catalogue(db, codes)
    return codes


@pytest.fixture()
def seeded_po(db) -> Codes:
    codes = make_codes()
    seed_catalogue(db, codes, doc_type="outstanding_po")
    seed_suppliers(db, codes)
    return codes


def _so_row(doc, item, qty, transferred, remaining, when, location, price=None):
    return so_row(doc, date(2026, 5, 4), "300-T012", item, "PCS", qty, transferred,
                  remaining, price, when, location)


def _po_row(doc, creditor, supplier, item, ordered, received, remaining, when, location,
            cost=None):
    return (doc, date(2026, 4, 6), creditor, supplier, item, "PCS", ordered, received,
            remaining, cost, when, location)


def _so_lines(db, so_number):
    return db.execute(text(
        "SELECT p.product_code, sol.qty_ordered, sol.qty_delivered, sol.line_status, "
        "       sol.required_date, sol.unit_price "
        "FROM sales_order_lines sol "
        "JOIN sales_orders so ON so.id = sol.sales_order_id "
        "JOIN products p ON p.id = sol.product_id "
        "WHERE so.so_number = :n ORDER BY p.product_code"
    ), {"n": so_number}).mappings().all()


def _so_status(db, so_number):
    return db.execute(text("SELECT status FROM sales_orders WHERE so_number = :n"),
                      {"n": so_number}).scalar()


def _po_lines(db, po_number):
    return db.execute(text(
        "SELECT p.product_code, pol.qty_ordered, pol.qty_received, pol.line_status, "
        "       pol.unit_cost "
        "FROM purchase_order_lines pol "
        "JOIN purchase_orders po ON po.id = pol.purchase_order_id "
        "JOIN products p ON p.id = pol.product_id "
        "WHERE po.po_number = :n ORDER BY p.product_code"
    ), {"n": po_number}).mappings().all()


def _po_status(db, po_number):
    return db.execute(text("SELECT status FROM purchase_orders WHERE po_number = :n"),
                      {"n": po_number}).scalar()


# --------------------------------------------------------------------------- #
# the reader
# --------------------------------------------------------------------------- #

def test_the_reader_carries_a_settled_row_as_a_line_with_its_ordered_figure(seeded, db):
    """The row states 40 ordered, 40 delivered, 0 left. All three facts survive.

    It used to survive as a row NUMBER on `settled_row_numbers` and nothing else, which is
    exactly as much as the database got from a 21,445-row book: nothing.
    """
    codes = seeded
    resolver = AliasResolver.for_doc_type(db, SO)
    data = workbook([_so_row(codes.project_so, codes.item_rl, 40, 40, 0,
                             date(2026, 7, 1), codes.loc_project)],
                    headers=SO_HEADERS)

    read = read_workbook(data, SO, resolver)

    assert read.problems == [], [p.reason for p in read.problems]
    assert len(read.lines) == 1, "a settled row was dropped instead of read"
    line = read.lines[0]
    assert line.qty == 0, "a settled line has nothing outstanding"
    extra = read.extras[str(line.row_ref)]
    assert extra["qty_ordered"] == pytest.approx(40)
    assert extra["qty_fulfilled"] == pytest.approx(40)
    assert read.settled_row_numbers == [], "the row is a line now, not a skip"


def test_a_remaining_of_zero_with_no_transferred_column_reads_the_whole_qty_as_delivered(
    seeded, db,
):
    """The file gives Qty and Remaining and nothing between them, so the difference IS what
    has gone out. Anything else leaves a closed line claiming it delivered nothing."""
    codes = seeded
    resolver = AliasResolver.for_doc_type(db, SO)
    headers = ("S/O NO", "DEBTOR CODE", "ITEM CODE", "QTY", "REMAINING QTY",
               "DELIVERY DATE", "STOCK LOCATION")
    data = workbook([(codes.project_so, "300-T012", codes.item_rl, 25, 0,
                      date(2026, 7, 1), codes.loc_project)], headers=headers)

    read = read_workbook(data, SO, resolver)

    assert len(read.lines) == 1
    extra = read.extras[str(read.lines[0].row_ref)]
    assert extra["qty_ordered"] == pytest.approx(25)
    assert extra["qty_fulfilled"] == pytest.approx(25)


def test_a_single_netted_quantity_of_zero_is_still_a_skip(seeded, db):
    """Nothing in the row says how much was ordered, so there is no line to write - only a
    zero that would claim an order for nothing."""
    codes = seeded
    resolver = AliasResolver.for_doc_type(db, SO)
    data = workbook([(codes.project_so, "300-T012", codes.item_rl, 0, date(2026, 7, 1),
                      codes.loc_project)], headers=SO_SINGLE_QTY)

    read = read_workbook(data, SO, resolver)

    assert read.lines == []
    assert read.settled_row_numbers == [2]


# --------------------------------------------------------------------------- #
# the write: a book carrying both halves
# --------------------------------------------------------------------------- #

def _both_halves(codes: Codes) -> bytes:
    """One outstanding document and one already completed, in one book."""
    return workbook([
        # still owed: 100 ordered, 40 gone, 60 to come
        _so_row(codes.project_so, codes.item_rl, 100, 40, 60, date(2026, 7, 1),
                codes.loc_project, price=12.5),
        # finished: 30 ordered, 30 gone, nothing left
        _so_row(codes.dealer_so, codes.item_wt, 30, 30, 0, date(2026, 6, 1),
                codes.loc_dealer, price=3.0),
    ], headers=SO_HEADERS)


def test_a_book_with_one_outstanding_and_one_completed_document_creates_both(seeded, db):
    """The upload is the book. A completed document is imported, and imported as completed."""
    codes = seeded

    out = svc.apply(db, _both_halves(codes), SO)

    assert out["ok"] is True
    assert out["applied"]["added"] == 2, out["applied"]

    open_line = _so_lines(db, codes.project_so)[0]
    # The OPEN half is untouched by any of this: a line still owed is written as what is
    # still owed against nothing delivered, because the delivered figure on an open line
    # belongs to the receipts booked against it (`_honesty_issues` reads it that way, and a
    # later upload adds its outstanding on top of it). Only a SETTLED line takes both
    # figures from the file - there are no receipts left to contradict.
    assert float(open_line["qty_ordered"]) == 60
    assert float(open_line["qty_delivered"]) == 0
    assert open_line["line_status"] == "open"
    assert _so_status(db, codes.project_so) == "open"

    done_line = _so_lines(db, codes.dealer_so)[0]
    assert float(done_line["qty_ordered"]) == 30, "the ordered quantity was lost"
    assert float(done_line["qty_delivered"]) == 30, "the delivered quantity was lost"
    assert done_line["line_status"] == "closed"
    assert done_line["required_date"] == date(2026, 6, 1), "the date was dropped"
    assert float(done_line["unit_price"]) == 3.0, "the money was dropped"
    # A document whose every line is closed is closed: the screen words that Completed.
    assert _so_status(db, codes.dealer_so) == "closed"


def test_the_preview_counts_a_new_completed_document_as_added(seeded, db):
    """The verdict's "would import" has to reflect them, so they are in the counts."""
    codes = seeded

    result = svc.preview(db, _both_halves(codes), SO)

    assert result.ok is True
    assert result.counts["added"] == 2
    assert result.counts["closed"] == 0, "nothing existed to close"


def test_re_uploading_the_same_completed_book_changes_nothing(seeded, db):
    """Idempotency is the property that lets an operator upload a year twice.

    Without it the second run either inserts a duplicate closed line or revives the first
    one as open, and a delivered 2026 order reads as stock on its way in.
    """
    codes = seeded
    svc.apply(db, _both_halves(codes), SO)

    out = svc.apply(db, _both_halves(codes), SO)

    assert out["applied"]["added"] == 0, out["applied"]
    assert out["applied"]["updated"] == 0, out["applied"]
    lines = _so_lines(db, codes.dealer_so)
    assert len(lines) == 1, "the re-upload inserted a second copy of a completed line"
    assert lines[0]["line_status"] == "closed", "a completed line was reopened"
    assert float(lines[0]["qty_ordered"]) == 30
    assert float(lines[0]["qty_delivered"]) == 30
    assert _so_status(db, codes.dealer_so) == "closed"


def test_an_open_line_the_new_book_states_as_delivered_goes_closed_with_its_qty(seeded, db):
    """The book is the record of what happened, and what happened is a delivery.

    Closing by ABSENCE still works and is still the common case; this is the other half -
    the row is present, and it states settlement. Counted as `closed`, not as a quantity
    change, because that is what it is.
    """
    codes = seeded
    svc.apply(db, workbook([
        _so_row(codes.project_so, codes.item_rl, 100, 40, 60, date(2026, 7, 1),
                codes.loc_project),
    ], headers=SO_HEADERS), SO)

    settled = workbook([
        _so_row(codes.project_so, codes.item_rl, 100, 100, 0, date(2026, 7, 1),
                codes.loc_project),
    ], headers=SO_HEADERS)
    result = svc.preview(db, settled, SO)
    out = svc.apply(db, settled, SO)

    assert result.counts["closed"] == 1, result.counts
    assert result.counts["qty_changed"] == 0, "a settlement is not a quantity change"
    assert out["applied"]["closed"] == 1, out["applied"]
    line = _so_lines(db, codes.project_so)[0]
    assert line["line_status"] == "closed"
    assert float(line["qty_ordered"]) == 100
    assert float(line["qty_delivered"]) == 100, "the delivery the file stated was not written"
    assert _so_status(db, codes.project_so) == "closed"


def test_a_document_with_one_line_left_open_stays_open(seeded, db):
    """The header follows its LINES. Half a book delivered is not a completed order."""
    codes = seeded

    svc.apply(db, workbook([
        _so_row(codes.project_so, codes.item_rl, 30, 30, 0, date(2026, 6, 1),
                codes.loc_project),
        _so_row(codes.project_so, codes.item_wt, 12, 0, 12, date(2026, 9, 1),
                codes.loc_project),
    ], headers=SO_HEADERS), SO)

    assert _so_status(db, codes.project_so) == "open"
    statuses = {r["product_code"]: r["line_status"] for r in _so_lines(db, codes.project_so)}
    assert statuses[codes.item_rl] == "closed"
    assert statuses[codes.item_wt] == "open"


def test_a_completed_row_is_accounted_for_on_the_job_rather_than_skipped(seeded, db):
    """Every source row gets exactly one outcome, and a written row is not a skip."""
    codes = seeded
    outcome = ImportOutcome(None, persist=False)

    svc.apply(db, _both_halves(codes), SO, outcome=outcome)

    breakdown = outcome.breakdown()
    assert oc.NOTHING_OUTSTANDING not in {e["code"] for e in breakdown["skipped"]}, \
        "a completed line was reported as nothing outstanding"
    created = [e for e in breakdown["successful"] if e["code"] == oc.CREATED]
    assert created and created[0]["count"] == 2, breakdown


# --------------------------------------------------------------------------- #
# the purchase side, same rule
# --------------------------------------------------------------------------- #

def test_the_purchase_book_imports_a_completed_order_too(seeded_po, db):
    """The two feeds must not diverge on what a book IS. Received, not delivered."""
    codes = seeded_po

    out = svc.apply(db, workbook([
        _po_row(codes.main_po, codes.creditor_main, "SIN HENG TRADING", codes.item_rl,
                50, 50, 0, date(2026, 4, 20), codes.loc_project, cost=8.25),
    ], headers=PO_HEADERS), PO)

    assert out["applied"]["added"] == 1, out["applied"]
    line = _po_lines(db, codes.main_po)[0]
    assert float(line["qty_ordered"]) == 50
    assert float(line["qty_received"]) == 50
    assert line["line_status"] == "closed"
    assert float(line["unit_cost"]) == 8.25
    assert _po_status(db, codes.main_po) == "closed"


def test_re_uploading_a_completed_purchase_book_changes_nothing(seeded_po, db):
    """The purchase header carries `closed` among its LIVE statuses, so the activation
    rule has to know a completed document from a document that fell out of the book."""
    codes = seeded_po
    data = workbook([
        _po_row(codes.main_po, codes.creditor_main, "SIN HENG TRADING", codes.item_rl,
                50, 50, 0, date(2026, 4, 20), codes.loc_project, cost=8.25),
    ], headers=PO_HEADERS)
    svc.apply(db, data, PO)

    result = svc.preview(db, data, PO)
    out = svc.apply(db, data, PO)

    assert result.activated_documents == [], "a completed order was lifted back to active"
    assert out["applied"]["added"] == 0, out["applied"]
    assert len(_po_lines(db, codes.main_po)) == 1
    assert _po_status(db, codes.main_po) == "closed"


def test_a_completed_document_that_reopens_is_active_again(seeded_po, db):
    """A later book that states something still to come is the same order, live again."""
    codes = seeded_po
    svc.apply(db, workbook([
        _po_row(codes.main_po, codes.creditor_main, "SIN HENG TRADING", codes.item_rl,
                50, 50, 0, date(2026, 4, 20), codes.loc_project),
    ], headers=PO_HEADERS), PO)
    assert _po_status(db, codes.main_po) == "closed"

    svc.apply(db, workbook([
        _po_row(codes.main_po, codes.creditor_main, "SIN HENG TRADING", codes.item_new,
                12, 0, 12, date(2026, 9, 1), codes.loc_project),
    ], headers=PO_HEADERS), PO)

    assert _po_status(db, codes.main_po) == "active"
    statuses = {r["product_code"]: r["line_status"] for r in _po_lines(db, codes.main_po)}
    assert statuses[codes.item_rl] == "closed"
    assert statuses[codes.item_new] == "open"


def test_a_settled_row_never_revives_the_history_line_it_matches(seeded_po, db):
    """`po_history_service` writes closed, fully received lines into these same tables so
    the on-order views cannot count them. A completed book must not wake one up: it is the
    guard `_preload_closed_lines` already carries, and a settled row reaches that code path
    too."""
    codes = seeded_po
    supplier_id = db.execute(text("SELECT id FROM suppliers WHERE supplier_code = :c"),
                             {"c": codes.creditor_main}).scalar()
    product_id = db.execute(text("SELECT id FROM products WHERE product_code = :c"),
                            {"c": codes.item_rl}).scalar()
    warehouse_id = db.execute(text("SELECT id FROM warehouses WHERE warehouse_code = :c"),
                              {"c": codes.loc_project}).scalar()
    header_id, line_id = str(uuid.uuid4()), str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO purchase_orders (id, po_number, supplier_id, status, source_system) "
        "VALUES (:id, :n, :s, 'closed', 'po_spo_history')"
    ), {"id": header_id, "n": codes.main_po, "s": supplier_id})
    db.execute(text(
        "INSERT INTO purchase_order_lines (id, purchase_order_id, product_id, warehouse_id, "
        "qty_ordered, qty_received, expected_date, line_status, source_system) "
        "VALUES (:id, :h, :p, :w, 50, 50, :d, 'closed', 'po_spo_history')"
    ), {"id": line_id, "h": header_id, "p": product_id, "w": warehouse_id,
        "d": date(2026, 4, 20)})
    db.flush()

    svc.apply(db, workbook([
        _po_row(codes.main_po, codes.creditor_main, "SIN HENG TRADING", codes.item_rl,
                50, 50, 0, date(2026, 4, 20), codes.loc_project),
    ], headers=PO_HEADERS), PO)

    rows = _po_lines(db, codes.main_po)
    assert all(r["line_status"] == "closed" for r in rows), "a history line was reopened"
