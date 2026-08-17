"""Absorbing the AutoCount sales-order listing as history, without inventing demand.

The governing claim, and the one this file exists to defend: **absorbed history contributes
nothing to committed demand.** The client's export carries 11,275 documents and 81,361 lines
back to 2020. Counted as commitments they would demand three million units nobody owes, and
the plan would go and buy them.

Proven against the real file before these tests were written: absorbing all 11,006 new
documents and 64,526 lines left `SUM(scm.committed_v.committed)` and
`SUM(scm.net_position_v.net_position)` byte-identical at 1,842,230 and 1,619,732. These tests
pin the mechanism that makes that true, on a chain each test seeds itself.

Everything runs inside `pg_session`, which rolls back, and every seeded row carries the
marker prefix so nothing borrows a row that is absent in CI.
"""
from __future__ import annotations

import io
import uuid
from datetime import date

import openpyxl
import pytest
from sqlalchemy import text

from app.models.inventory import Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.scm import so_history_service as svc
from tests._pg_fixture import pg_session, unique_code

MARKER = "ZZSOH"

HEADERS = [
    "Doc No", "Doc Date", "Delivery Date", "Debtor Code", "Debtor Name", "Agent",
    "Item Code", "Item Description", "Location", "Qty", "Transfered Qty",
    "Remaining Qty", "Unit Price", "Note",
]


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def chain(db):
    """Two products, two locations and one customer, all this test's own.

    Postgres enforces the NOT NULLs the ORM defaults do not cover (category_code,
    uom_code/uom_name, products.base_uom_id, list_price, customers.customer_code), so an
    approximation aborts the transaction rather than failing an assertion.
    """
    cat = ProductCategory(id=_u(), category_code=unique_code("CAT")[:40],
                          category_name=unique_code("cat"))
    uom = UnitOfMeasure(id=_u(), uom_name=unique_code("uom"), uom_code=unique_code("U")[:20])
    db.add_all([cat, uom])
    db.flush()

    p1 = Product(id=_u(), product_code=f"{MARKER}-SKU1-{uuid.uuid4().hex[:6]}",
                 product_name="wall hung wc", category_id=cat.id, base_uom_id=uom.id,
                 list_price=0)
    p2 = Product(id=_u(), product_code=f"{MARKER}-SKU2-{uuid.uuid4().hex[:6]}",
                 product_name="basin mixer", category_id=cat.id, base_uom_id=uom.id,
                 list_price=0)
    wh = Warehouse(id=_u(), warehouse_code=f"{MARKER}W{uuid.uuid4().hex[:5]}".upper()[:20],
                   warehouse_name="a bin", is_active=True)
    cust = Customer(id=_u(), customer_code=f"{MARKER}-C{uuid.uuid4().hex[:5]}",
                    customer_name="ZZ ROWENDA KITCHEN")
    db.add_all([p1, p2, wh, cust])
    db.flush()
    return {"p1": p1, "p2": p2, "wh": wh, "cust": cust,
            "so": f"{MARKER}SO{uuid.uuid4().hex[:8]}".upper()}


def _row(chain, **over):
    row = {
        "Doc No": chain["so"], "Doc Date": "2024-03-01", "Delivery Date": "2024-03-15",
        "Debtor Code": chain["cust"].customer_code,
        "Debtor Name": chain["cust"].customer_name, "Agent": "ACT",
        "Item Code": chain["p1"].product_code, "Item Description": "a wc",
        "Location": chain["wh"].warehouse_code,
        "Qty": 10, "Transfered Qty": 10, "Remaining Qty": 0,
        "Unit Price": 250, "Note": "PS24-0001",
    }
    row.update(over)
    return [row[h] for h in HEADERS]


def _wb(rows) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEADERS)
    for r in rows:
        ws.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _lines(db, so_number):
    order = db.query(SalesOrder).filter(SalesOrder.so_number == so_number).one()
    return order, db.query(SalesOrderLine).filter(
        SalesOrderLine.sales_order_id == str(order.id)
    ).order_by(SalesOrderLine.source_ref).all()


# --------------------------------------------------------------------------- #
# THE claim: history is not demand
# --------------------------------------------------------------------------- #

def test_absorbed_history_adds_nothing_to_committed_demand(db, chain):
    """The whole reason this feed is separate from the outstanding one.

    Measured across the entire view rather than on this order alone: a line that leaked into
    `committed_v` would raise the total, and asserting on the order would let a leak through
    some other join go unnoticed.
    """
    before = float(db.execute(
        text("SELECT COALESCE(SUM(committed),0) FROM scm.committed_v")).scalar())

    out = svc.apply(db, _wb([_row(chain)]))
    db.flush()

    assert out["orders_created"] == 1 and out["lines_created"] == 1
    after = float(db.execute(
        text("SELECT COALESCE(SUM(committed),0) FROM scm.committed_v")).scalar())
    assert after == before, "absorbed history reached committed demand"


def test_every_absorbed_line_is_closed_and_fully_delivered(db, chain):
    """The mechanism behind the claim above, asserted directly.

    `scm.committed_v` counts a line that is OPEN and still has quantity to deliver. Failing
    BOTH halves means the exclusion holds however that view is later rewritten - one filter
    somebody forgets cannot resurrect three million units of phantom demand.
    """
    svc.apply(db, _wb([_row(chain)]))
    db.flush()

    order, lines = _lines(db, chain["so"])
    assert order.status == "closed"
    assert [(ln.line_status, float(ln.qty_ordered), float(ln.qty_delivered))
            for ln in lines] == [("closed", 10.0, 10.0)]


def test_a_line_the_file_says_is_still_owed_is_absorbed_closed_and_reported(db, chain):
    """The honest handling of a file that is not purely history.

    Ten ordered, four delivered. This feed records finished business, so the line is written
    closed regardless - silently creating a commitment from a history upload is the failure
    mode. But writing it closed WITHOUT saying so would hide a real six-unit obligation, so
    the count is reported and the uploader is told to use the outstanding channel.
    """
    out = svc.apply(db, _wb([_row(chain, **{"Transfered Qty": 4, "Remaining Qty": 6})]))
    db.flush()

    assert out["outstanding_lines"] == 1, "the file's own outstanding line must be reported"
    _order, lines = _lines(db, chain["so"])
    assert [(ln.line_status, float(ln.qty_ordered), float(ln.qty_delivered))
            for ln in lines] == [("closed", 10.0, 10.0)]


# --------------------------------------------------------------------------- #
# re-upload
# --------------------------------------------------------------------------- #

def test_re_uploading_the_same_file_creates_nothing_a_second_time(db, chain):
    """Re-exporting a wider date range and sending the whole book again is normal.

    Without idempotency the second upload doubles six years of demand, and because every line
    is closed nothing downstream would show it until somebody read a customer's order history
    and found it twice.
    """
    data = _wb([_row(chain), _row(chain, **{"Item Code": chain["p2"].product_code})])

    first = svc.apply(db, data)
    db.flush()
    second = svc.apply(db, data)
    db.flush()

    assert (first["orders_created"], first["lines_created"]) == (1, 2)
    assert (second["orders_created"], second["lines_created"]) == (0, 0)
    # Same -> SKIP, and skipping is reported as its own outcome. An upload that reported
    # "1 order updated, 2 lines updated" after changing nothing tells the uploader nothing
    # about what their file did, and it touches `updated_at` on rows that did not change.
    assert (second["orders_updated"], second["lines_updated"]) == (0, 0)
    assert (second["orders_unchanged"], second["lines_unchanged"]) == (1, 2)
    _order, lines = _lines(db, chain["so"])
    assert len(lines) == 2


def test_a_changed_line_is_updated_rather_than_added_beside_the_old_one(db, chain):
    """Different -> UPDATE, the middle case of the rule.

    The same document re-exported with a corrected quantity. One line, restated - not two
    lines summing to fifteen, which is what any append-only feed would leave behind.
    """
    svc.apply(db, _wb([_row(chain, Qty=10, **{"Transfered Qty": 10})]))
    db.flush()

    out = svc.apply(db, _wb([_row(chain, Qty=5, **{"Transfered Qty": 5})]))
    db.flush()

    assert (out["lines_created"], out["lines_updated"], out["lines_unchanged"]) == (0, 1, 0)
    _order, lines = _lines(db, chain["so"])
    assert [float(ln.qty_ordered) for ln in lines] == [5.0]


def test_the_same_item_repeated_on_one_order_stays_several_lines(db, chain):
    """The client's SO174948 carries SRTWT5801 three times, one unit each.

    The export has no line number, so identity is the line's ORDINAL within its document. Any
    content-based key - item, location, price, date - would collapse those three into one and
    lose two units of real history, and the collapse would look like clean deduplication.
    """
    data = _wb([_row(chain, Qty=1, **{"Transfered Qty": 1}) for _ in range(3)])

    out = svc.apply(db, data)
    db.flush()

    assert out["lines_created"] == 3
    _order, lines = _lines(db, chain["so"])
    assert [ln.source_ref for ln in lines] == ["1", "2", "3"]
    assert sum(float(ln.qty_ordered) for ln in lines) == 3.0

    # And a re-upload still finds them by ordinal rather than adding three more.
    again = svc.apply(db, data)
    db.flush()
    assert again["lines_created"] == 0


def test_a_document_another_feed_owns_is_reported_as_a_conflict_not_absorbed(db, chain):
    """Two AutoCount exports disagreeing is a question about their data, not ours.

    269 of the client's 11,275 documents are open in the Order Inquiry sheet with 430,108
    units still owed, while this listing reports every one of them fully delivered. One of
    the two exports is stale.

    Answering that by upload order is the worst option available, and it was tried: settling
    those headers removed 430,108 units of committed demand from the plan and left each
    document holding two sets of lines, the original open ones and the imported closed ones.
    Both effects looked exactly like a successful import.
    """
    live = SalesOrder(id=_u(), so_number=chain["so"], status="open",
                      source_system="scm_order_inquiry")
    db.add(live)
    db.flush()
    db.add(SalesOrderLine(id=_u(), sales_order_id=str(live.id),
                          product_id=str(chain["p1"].id), qty_ordered=4, qty_delivered=0,
                          line_status="open", source_system="scm_order_inquiry"))
    db.flush()
    before = float(db.execute(
        text("SELECT COALESCE(SUM(committed),0) FROM scm.committed_v")).scalar())

    out = svc.apply(db, _wb([_row(chain)]))
    db.flush()

    assert out["conflicted_order_count"] == 1
    assert chain["so"] in out["conflicted_orders"], "the document has to be NAMED, not counted"
    assert (out["orders_created"], out["orders_updated"], out["lines_created"]) == (0, 0, 0)

    db.refresh(live)
    assert live.status == "open", "a conflicted document was settled anyway"
    _order, lines = _lines(db, chain["so"])
    assert len(lines) == 1, "a conflicted document was given a second set of lines"
    after = float(db.execute(
        text("SELECT COALESCE(SUM(committed),0) FROM scm.committed_v")).scalar())
    assert after == before, "a conflicted document lost its committed demand"


def test_a_document_this_feed_owns_is_still_reconciled_normally(db, chain):
    """GUARD: "leave conflicts alone" must not become "never update anything".

    A document this feed wrote before is its own, so the same/different/new rule applies to
    it in full - otherwise the conflict rule would quietly disable re-uploads.
    """
    svc.apply(db, _wb([_row(chain, Qty=10, **{"Transfered Qty": 10})]))
    db.flush()

    out = svc.apply(db, _wb([_row(chain, Qty=7, **{"Transfered Qty": 7})]))
    db.flush()

    assert out["conflicted_order_count"] == 0
    assert out["lines_updated"] == 1
    _order, lines = _lines(db, chain["so"])
    assert [float(ln.qty_ordered) for ln in lines] == [7.0]


def test_a_document_already_matching_the_file_is_left_completely_alone(db, chain):
    """GUARD: "reconcile everything" must not become "rewrite everything".

    Without this, the rule above would be satisfied by an implementation that updates every
    document on every upload, which is indistinguishable from the append-only feed it
    replaced right up until somebody reads the audit trail.
    """
    svc.apply(db, _wb([_row(chain)]))
    db.flush()
    _order, lines = _lines(db, chain["so"])
    stamp = lines[0].updated_at

    out = svc.apply(db, _wb([_row(chain)]))
    db.flush()

    assert out["orders_unchanged"] == 1
    assert out["orders_with_open_lines_closed"] == 0
    _order, lines = _lines(db, chain["so"])
    assert lines[0].updated_at == stamp, "an unchanged line had its updated_at touched"


# --------------------------------------------------------------------------- #
# what it refuses to invent
# --------------------------------------------------------------------------- #

def test_an_unknown_item_is_counted_and_named_never_created(db, chain):
    """Building a product catalogue out of a 2020 sales report is how a catalogue stops
    meaning anything. Seventeen of the client's 3,357 codes do not resolve."""
    missing = f"{MARKER}-NOSUCH-{uuid.uuid4().hex[:6]}"
    before = db.query(Product).count()

    out = svc.apply(db, _wb([_row(chain), _row(chain, **{"Item Code": missing})]))
    db.flush()

    assert out["unknown_item_count"] == 1
    assert missing in out["unknown_items"]
    assert db.query(Product).count() == before, "the feed created a product"
    assert out["lines_created"] == 1, "only the resolvable line is written"


def test_an_unresolved_debtor_still_produces_an_order_that_names_them(db, chain):
    """470 of the client's 882 debtor codes are not in the CRM.

    Rejecting those orders would throw away most of six years of history; inventing the
    customer would fill the CRM with rows nobody verified. The order is written with no link,
    and the printed name and code are kept so the link is fixable later - dropping them
    leaves an order nobody can attribute.
    """
    out = svc.apply(db, _wb([_row(
        chain, **{"Debtor Code": "300-NOSUCH", "Debtor Name": "A COMPANY NOT IN THE CRM"})]))
    db.flush()

    assert out["unknown_debtor_count"] == 1
    order, lines = _lines(db, chain["so"])
    assert order.customer_id is None
    assert len(lines) == 1
    assert "A COMPANY NOT IN THE CRM" in (order.internal_note or "")
    assert "300-NOSUCH" in (order.internal_note or "")


def test_a_charge_line_is_not_written_as_demand(db, chain):
    """`MISC` and `TRANSPORT CHARGE` are real money on the order with no product behind them.

    Written as a stock line, a quantity of 1 "TRANSPORT CHARGE" becomes demand for something
    that does not exist, and the code sits in the unmatched list for ever.
    """
    out = svc.apply(db, _wb([_row(chain), _row(chain, **{"Item Code": "MISC"})]))
    db.flush()

    assert out["non_stock_lines"] == 1
    assert out["lines_created"] == 1
    assert out["unknown_item_count"] == 0, "a charge code is not an unmatched product"


def test_a_package_caption_row_is_layout_rather_than_a_failure(db, chain):
    """9,141 of the client's 81,362 rows are captions and spacers.

    Reporting each as a failure buries the six rows that really did fail, and an import screen
    showing nine thousand problems reads as a broken file.
    """
    out = svc.apply(db, _wb([
        _row(chain, **{"Item Code": None, "Item Description": "ITEM PACKAGE :",
                       "Location": None, "Qty": 0, "Transfered Qty": 0}),
        _row(chain),
    ]))
    db.flush()

    assert out["layout_rows"] == 1
    assert out["problems"] == []
    assert out["lines_created"] == 1


def test_the_location_and_the_dates_survive_the_absorption(db, chain):
    """History is worth having because of WHEN and WHERE, so those are asserted separately.

    The order date is the demand record; the per-line delivery date is what a coverage
    timeline would need; the location is what makes the line poolable. A feed that kept the
    quantity and lost the other three would look successful and be worthless.
    """
    svc.apply(db, _wb([_row(chain, **{"Doc Date": "2024-03-01",
                                      "Delivery Date": "2024-04-20"})]))
    db.flush()

    order, lines = _lines(db, chain["so"])
    assert order.order_date == date(2024, 3, 1)
    assert lines[0].required_date == date(2024, 4, 20)
    assert lines[0].warehouse_id == str(chain["wh"].id)


def test_an_unknown_location_leaves_the_line_placeless_and_says_so(db, chain):
    """Thirteen of the client's 43 location codes are not warehouses in the system.

    Guessing a location would put six years of history in a bin it never sat in. The line is
    written without one, and the code is named so somebody can add the warehouse.
    """
    out = svc.apply(db, _wb([_row(chain, Location="NOSUCHLOC")]))
    db.flush()

    assert out["unknown_locations"] == ["NOSUCHLOC"]
    _order, lines = _lines(db, chain["so"])
    assert lines[0].warehouse_id is None


def test_preview_writes_nothing(db, chain):
    """The uploader looks before they leap, and looking must not be a write."""
    before = db.query(SalesOrder).count()

    out = svc.preview(db, _wb([_row(chain)]))

    assert out["orders"] == 1 and out["lines"] == 1
    assert "orders_created" not in out
    assert db.query(SalesOrder).count() == before


# --------------------------------------------------------------------------- #
# who ordered it, and what they paid (AC-4.1 / AC-4.3)
# --------------------------------------------------------------------------- #

def test_the_debtor_code_is_kept_in_its_own_column(db, chain):
    """The note has always carried it; a column is what a query can read.

    The plan's demand and trend popovers fall back to `Debtor 300-R009` when the link
    failed, and parsing that out of a free-text note is not something a screen should do.
    """
    svc.apply(db, _wb([_row(chain)]))
    db.flush()

    order, _ = _lines(db, chain["so"])
    assert order.debtor_code == chain["cust"].customer_code.upper()
    assert order.customer_id == str(chain["cust"].id), "the link itself is unchanged"
    # The printed NAME still travels in the note: no column holds it.
    assert chain["cust"].customer_name in (order.internal_note or "")


def test_two_spellings_of_one_debtor_code_become_one_stored_code(db, chain):
    """`300-r009` and `300-R009` are one debtor, so they must be one row on the plan's
    "who bought it" and one drill behind it.

    The outstanding book has always upper-cased the code it writes; this feed wrote it as
    the file printed it, so the same debtor arrived as two rows whose quantities each told
    half the story - and neither drill found the other half.
    """
    svc.apply(db, _wb([_row(chain, **{"Debtor Code": "300-r009"})]))
    db.flush()
    first = _lines(db, chain["so"])[0].debtor_code

    svc.apply(db, _wb([_row(chain, **{"Debtor Code": "300-R009"})]))
    db.flush()

    assert first == "300-R009" == _lines(db, chain["so"])[0].debtor_code


def test_an_order_whose_debtor_we_do_not_hold_still_keeps_the_code(db, chain):
    svc.apply(db, _wb([_row(chain, **{"Debtor Code": f"{MARKER}-NOBODY"})]))
    db.flush()

    order, _ = _lines(db, chain["so"])
    assert order.customer_id is None
    assert order.debtor_code == f"{MARKER}-NOBODY"


def test_the_unit_price_the_file_states_is_written(db, chain):
    """> "sells RM 0.94?" - the reader has always parsed the price and the write dropped it,
    so every price cell on the "who bought it" drill was blank."""
    svc.apply(db, _wb([_row(chain, **{"Unit Price": 0.94})]))
    db.flush()

    _order, lines = _lines(db, chain["so"])
    assert [float(ln.unit_price) for ln in lines] == [0.94]


def test_a_line_the_file_prices_at_nothing_stays_absent_rather_than_zero(db, chain):
    """A price we do not know is not 0.00, and the popover renders the difference."""
    svc.apply(db, _wb([_row(chain, **{"Unit Price": None})]))
    db.flush()

    _order, lines = _lines(db, chain["so"])
    assert lines[0].unit_price is None


def test_re_uploading_the_same_price_is_still_no_change(db, chain):
    """The house rule: same -> skip. A price compared as Decimal vs float must not read as
    an update, or a re-upload of an unchanged book reports 64,526 of them."""
    svc.apply(db, _wb([_row(chain)]))
    db.flush()

    out = svc.apply(db, _wb([_row(chain)]))

    assert out["lines_updated"] == 0 and out["lines_unchanged"] == 1


def test_a_third_decimal_in_the_file_does_not_report_a_change_every_week(db, chain):
    """The column stores two decimals, so 0.945 comes back out of it as 0.95.

    Compared as raw numbers the file and the database then disagree for ever: every
    re-upload reports the line as updated and stamps `updated_at` on a row nothing changed.
    The comparison is made at the precision the column actually holds.
    """
    svc.apply(db, _wb([_row(chain, **{"Unit Price": 0.945})]))
    db.flush()

    out = svc.apply(db, _wb([_row(chain, **{"Unit Price": 0.945})]))

    assert (out["lines_updated"], out["lines_unchanged"]) == (0, 1)


def test_a_price_that_moved_by_a_cent_is_still_an_update(db, chain):
    """GUARD: comparing at 2 decimals must not become "close enough is the same"."""
    svc.apply(db, _wb([_row(chain, **{"Unit Price": 0.94})]))
    db.flush()

    out = svc.apply(db, _wb([_row(chain, **{"Unit Price": 0.95})]))
    db.flush()

    assert out["lines_updated"] == 1
    _order, lines = _lines(db, chain["so"])
    assert [float(ln.unit_price) for ln in lines] == [0.95]
