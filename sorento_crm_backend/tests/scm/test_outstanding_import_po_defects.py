"""Eleven confirmed defects in the outstanding-orders PURCHASE-ORDER write path.

Written red, before the fix, one test per defect (two where the defect has two halves), and
every docstring says what the defect costs the PLAN rather than what the code does. The plan
is the only consumer that matters here: `scm.on_order_v` feeds `scm.net_position_v`, which
feeds the reorder engine, the dashboard and the cash co-pilot. A wrong on-order figure does
not read as wrong - it reads as a confident recommendation to buy, or not to buy.

The defects cluster into four families, which is why they are worth fixing together:

* **liveness** (1, 2) - the importer's idea of "this document is live" is narrower than every
  reader's, so re-uploads double supply and lifted drafts import supply then hide it;
* **identity** (6, 8) - a line is identified by content, so a line that comes back is
  inserted twice, and a line stated twice in one file must not creep the supply upward on
  every re-upload (defect 8, whose reader-level complaint has since been removed: see the
  test, and AC-2.1);
* **honesty** (3, 7, 11) - a file that is wrong, stale or self-contradicting is applied in
  silence, and nothing ever surfaces it;
* **one definition** (4, 5, 9, 10) - `line_status`, cost and `issue_date` are read by the
  views, the dashboard, the PO service and the lead-time measurement, and they disagree.

Same discipline as the rest of this suite: every product, warehouse, supplier, order and line
is seeded by the test from codes it generates (`tests/scm/_outstanding_workbooks.py`), the
upload is generated from the SAME codes so file and rows cannot drift, nothing is borrowed
with `LIMIT 1` off a table that is empty in CI, and everything runs inside `pg_session()`,
which rolls back.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import date

import pytest
from sqlalchemy import text

from app.models.procurement import PurchaseOrder, PurchaseOrderLine
from app.services.scm import outstanding_import_service as svc
from app.services.scm.dashboard_service import ScmDashboardService, ScmFilters
from app.services.scm.outstanding_reader import PO
from app.services.scm.purchase_order_service import PurchaseOrderService
from tests._pg_fixture import pg_session
from tests.scm._outstanding_workbooks import (
    PO_MINIMAL,
    SUPPLIER_ALT_LABEL,
    SUPPLIER_MAIN_LABEL,
    Codes,
    make_codes,
    po_minimal_row,
    po_row,
    po_week1,
    po_workbook,
    seed_catalogue,
    seed_suppliers,
)

# The live write status for a purchase order, per `_BINDINGS[PO].open_status`. Named once so
# the tests read as "the status the importer writes" rather than repeating a string.
LIVE = "active"

# Every status in which a purchase order is a LIVE document for `scm.on_order_v`,
# `dashboard_service.PLACED_PO_STATUSES` and `purchase_order_service._ON_ORDER_STATUSES`.
# The importer recognises only the first.
LIVE_STATUSES = ("active", "received", "partial", "closed")

# Statuses in which a purchase order is NOT supply. `create_gr` and the recommendation flow
# both produce these, and an extract naming such a document is a document that has since been
# placed.
DRAFT_STATUSES = ("draft", "draft_recommendation")


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
# readers. Raw SQL on purpose: the assertion must see what actually landed.
# --------------------------------------------------------------------------- #

def _po_lines(db, po_number, item):
    return db.execute(text(
        """
        SELECT pol.id, (pol.qty_ordered - pol.qty_received) AS outstanding,
               pol.expected_date, pol.line_status, pol.qty_ordered, pol.qty_received,
               pol.unit_cost, pol.currency, w.warehouse_code
        FROM purchase_order_lines pol
        JOIN purchase_orders po ON po.id = pol.purchase_order_id
        JOIN products p ON p.id = pol.product_id
        LEFT JOIN warehouses w ON w.id = pol.warehouse_id
        WHERE po.po_number = :po AND p.product_code = :item
        ORDER BY pol.expected_date NULLS LAST, pol.created_at
        """
    ), {"po": po_number, "item": item}).mappings().fetchall()


def _line_count(db, *po_numbers) -> int:
    return db.execute(text(
        "SELECT count(*) FROM purchase_order_lines pol "
        "JOIN purchase_orders po ON po.id = pol.purchase_order_id "
        "WHERE po.po_number = ANY(:pos)"
    ), {"pos": list(po_numbers)}).scalar()


def _header(db, po_number):
    row = db.execute(text(
        "SELECT po.id, po.status, po.issue_date, po.currency, s.supplier_code, "
        "       s.supplier_name "
        "FROM purchase_orders po LEFT JOIN suppliers s ON s.id = po.supplier_id "
        "WHERE po.po_number = :po"
    ), {"po": po_number}).mappings().fetchone()
    assert row is not None, f"no purchase order exists for {po_number}"
    return row


def _supplier_of(db, po_number):
    row = _header(db, po_number)
    return (row["supplier_code"], row["supplier_name"])


def _ordered(db, item) -> float:
    """What `scm.po_ordered_v` counts as ORDERED for this item, across warehouses.

    `on_order_v` is the SPO allocation now (migration 337): incoming stock, which a purchase
    order alone is not. These tests are about the PO book, so they read the PO view.
    """
    return float(db.execute(text(
        "SELECT COALESCE(SUM(oo.ordered), 0) FROM scm.po_ordered_v oo "
        "JOIN products p ON p.id = oo.product_id WHERE p.product_code = :item"
    ), {"item": item}).scalar())


def _receipt_observations(db, item) -> int:
    """Rows `scm.receipt_lead_v` offers as lead-time evidence for this item."""
    return db.execute(text(
        "SELECT count(*) FROM scm.receipt_lead_v rl "
        "JOIN products p ON p.id = rl.product_id WHERE p.product_code = :item"
    ), {"item": item}).scalar()


def _picking_lines_for(db, po_line_id) -> int:
    return db.execute(text(
        "SELECT count(*) FROM picking_lines WHERE po_line_id = :i"
    ), {"i": str(po_line_id)}).scalar()


def _reported(result) -> list[dict]:
    """Everything the response puts in front of a human, from either entry point.

    `preview()` returns dataclasses and `apply()` returns their dicts; a defect about
    "was this surfaced at all" must not care which of the two it is looking at.
    """
    if isinstance(result, dict):
        return list(result.get("row_problems") or []) + \
               list(result.get("resolution_issues") or [])
    return [asdict(p) for p in result.row_problems] + \
           [asdict(i) for i in result.resolution_issues]


def _report_blob(result) -> str:
    return json.dumps(_reported(result))


# --------------------------------------------------------------------------- #
# 1. liveness: every status the readers call live, the importer must call live too
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("status", LIVE_STATUSES)
def test_reapplying_a_file_after_the_po_moved_to_a_live_status_is_a_no_op(db, seeded, status):
    """A part-received purchase order is still the same order, and re-uploading Monday's
    extract must not order the goods again.

    `purchase_order_service.create_gr` stamps `received` the moment a goods receipt is booked,
    and `scm.on_order_v` / `dashboard_service.PLACED_PO_STATUSES` /
    `purchase_order_service._ON_ORDER_STATUSES` all treat `active`, `received`, `partial` and
    `closed` alike as placed supply. The importer's `_existing_lines` recognises only `active`,
    so for the other three it sees a document with no lines, inserts every line a second time,
    and on-order doubles: the plan then believes twice the containers are at sea and defers a
    purchase that is genuinely needed. Nothing in the response hints at it - it reads as a
    clean `added: N`.
    """
    svc.apply(db, po_week1(seeded), PO)
    lines_before = _line_count(db, seeded.main_po, seeded.alt_po)
    ordered_before = _ordered(db, seeded.item_rl)
    db.execute(text("UPDATE purchase_orders SET status = :s WHERE po_number = :po"),
               {"s": status, "po": seeded.main_po})
    db.flush()

    again = svc.apply(db, po_week1(seeded), PO)

    assert again["applied"] == {"added": 0, "updated": 0, "closed": 0, "unchanged": 5}, \
        f"a purchase order in status {status!r} was treated as a document with no lines"
    assert _line_count(db, seeded.main_po, seeded.alt_po) == lines_before, \
        "the same extract inserted its lines a second time"
    assert _ordered(db, seeded.item_rl) == ordered_before, \
        "on-order doubled: the plan now sees supply that was never ordered"


# --------------------------------------------------------------------------- #
# 2. liveness: a document named by the extract HAS been placed
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("status", DRAFT_STATUSES)
def test_a_draft_header_named_by_the_extract_is_lifted_to_the_live_status(db, seeded, status):
    """An outstanding-PO extract is a book of orders already placed with suppliers, so a
    document it names is by definition no longer a draft.

    A draft that the buyer has since actually placed keeps its draft status through the import,
    and `scm.on_order_v` deliberately ignores drafts (M4-D5) - so the lines land, the supply
    is invisible, and the engine recommends buying what is already on the water. The response
    meanwhile reports `added: 3`, so the operator has no way to tell a real import from this
    silent no-op. Reporting the lift is half the fix: changing a document's status is exactly
    the kind of side effect that has to be visible on the confirm screen.
    """
    db.add(PurchaseOrder(id=_u(), po_number=seeded.main_po, status=status))
    db.flush()

    out = svc.apply(db, po_week1(seeded), PO)

    assert _header(db, seeded.main_po)["status"] == LIVE, \
        f"a {status!r} header named by the extract was left as a draft"
    assert _ordered(db, seeded.item_rl) == 207.0, \
        "the lines landed on a draft, so the plan cannot see the supply at all"
    assert out.get("activated_documents") == [seeded.main_po], \
        "the response does not name the document whose status it changed"


# --------------------------------------------------------------------------- #
# 3. honesty: a file with no arrival date is a different report
# --------------------------------------------------------------------------- #

def _no_date_file(codes: Codes) -> bytes:
    """The same extract with the ETA column removed, and nothing else changed."""
    return po_workbook(
        [
            (codes.main_po, codes.creditor_main, codes.item_rl, 135, codes.loc_project),
            (codes.main_po, codes.creditor_main, codes.item_wt, 60, codes.loc_project),
        ],
        headers=("PO NO", "CREDITOR CODE", "ITEM CODE", "QTY ORDERED", "STOCK LOCATION"),
    )


def test_preview_refuses_a_po_extract_with_no_arrival_date_column(db, seeded):
    """A supply book with no dates is not an outstanding-PO extract, it is a different report.

    The sales side already refuses this at the header (`_REQUIRED_COLUMNS[SO]` lists
    `required_date`) because importing it would blank every date in scope. The PO side accepts
    it: on-order stays right, so nothing looks broken, while every `expected_date` in scope
    becomes NULL and the plan loses its time axis entirely - coverage timelines, the arrival
    calendar and every "when does this land" answer silently collapse to "unknown". Refused at
    the header rather than row by row, since 4,000 rows cannot answer a question the header
    cannot.
    """
    res = svc.preview(db, _no_date_file(seeded), PO)

    assert res.ok is False, "a PO extract with no arrival-date column was accepted"
    assert "expected_date" in res.missing_columns, \
        "the screen cannot name the column the file has to grow"
    assert res.counts == {}, "a file that cannot be read must promise no changes"


def test_apply_refuses_a_po_extract_with_no_arrival_date_column(db, seeded):
    """The refusal has to hold on the write path too, not only on the preview.

    Preview and apply share one code path precisely so the commit cannot disagree with what
    the operator was shown. If only preview refused, a client posting straight to apply would
    still wipe every arrival date in scope.
    """
    before = _line_count(db, seeded.main_po, seeded.alt_po)

    out = svc.apply(db, _no_date_file(seeded), PO)

    assert out["ok"] is False, "apply wrote a PO extract that has no arrival-date column"
    assert "expected_date" in out["missing_columns"]
    assert _line_count(db, seeded.main_po, seeded.alt_po) == before, \
        "lines landed with a NULL arrival date"


# --------------------------------------------------------------------------- #
# 4. one definition: a goods receipt must not book a cancelled quantity
# --------------------------------------------------------------------------- #

def test_a_goods_receipt_skips_a_line_the_importer_closed(db, seeded):
    """Goods that were cancelled never arrive, so booking them in invents inventory.

    `create_gr` walks every line whose `qty_ordered > qty_received` and stamps a full receipt,
    with no regard for `line_status`. A line the importer closed (the supplier cancelled it, or
    it left the order book) is therefore received in full: stock is credited for goods that do
    not exist, and `scm.receipt_lead_v` gains a fabricated lead-time observation whose
    `lead_days` then skews the supplier's measured lead time and, through it, every safety
    stock and reorder point computed from it. Wrong lead time is worse than no lead time,
    because it is trusted.
    """
    file_a = po_workbook([
        po_minimal_row(seeded.main_po, seeded.creditor_main, seeded.item_wt, 60,
                       date(2026, 9, 30), seeded.loc_project),
        po_minimal_row(seeded.main_po, seeded.creditor_main, seeded.item_rl, 100,
                       date(2026, 7, 1), seeded.loc_project),
    ], headers=PO_MINIMAL)
    # The same document a week later, with the item_wt line gone: cancelled, not received.
    file_b = po_workbook([
        po_minimal_row(seeded.main_po, seeded.creditor_main, seeded.item_rl, 100,
                       date(2026, 7, 1), seeded.loc_project),
    ], headers=PO_MINIMAL)
    svc.apply(db, file_a, PO)
    svc.apply(db, file_b, PO)
    cancelled = _po_lines(db, seeded.main_po, seeded.item_wt)[0]
    assert cancelled["line_status"] == "closed", "the importer did not close the line"

    PurchaseOrderService(db).create_gr(str(_header(db, seeded.main_po)["id"]))

    assert _picking_lines_for(db, cancelled["id"]) == 0, \
        "the goods receipt booked a cancelled quantity as arrived"
    after = _po_lines(db, seeded.main_po, seeded.item_wt)[0]
    assert float(after["qty_received"]) == 0.0, \
        "a receipt was invented for goods that were never coming"
    assert after["line_status"] == "closed", "a closed line was reopened as received"
    assert _receipt_observations(db, seeded.item_wt) == 0, \
        "scm.receipt_lead_v gained a fabricated lead-time observation"


# --------------------------------------------------------------------------- #
# 5. one definition: the readers have to agree on what "on order" means
# --------------------------------------------------------------------------- #

def test_every_reader_agrees_a_closed_po_line_is_not_incoming(db, seeded):
    """Two readers disagreeing about "on order" is what makes a planning report untrustworthy.

    `scm.on_order_v` (migration 311) excludes a line whose `line_status` is not `open`, because
    a line that left the order book is not incoming. `dashboard_service._placed_po_rows` and
    `purchase_order_service` never gained that predicate, so the SAME closed line is not
    supply in the net position, is supply in the dashboard's incoming-PO count, and is still
    counted in the purchase order's own total quantity and line count. Whichever number the
    buyer happens to be looking at decides whether they re-order, and both are on screen.

    Asserted as AGREEMENT rather than as three separate figures: the invariant is that the
    readers cannot diverge, so the failure message has to show which one dissented.
    """
    # The importer closes the only line anywhere for item_wt: the document is still in the
    # extract, that line is not.
    svc.apply(db, po_workbook([
        po_minimal_row(seeded.main_po, seeded.creditor_main, seeded.item_wt, 60,
                       date(2026, 9, 30), seeded.loc_project),
    ], headers=PO_MINIMAL), PO)
    svc.apply(db, po_workbook([
        po_minimal_row(seeded.main_po, seeded.creditor_main, seeded.item_new, 5,
                       date(2026, 9, 1), seeded.loc_project),
    ], headers=PO_MINIMAL), PO)

    dash = ScmDashboardService(db)
    filters = ScmFilters(q=seeded.item_wt)
    incoming = {
        "scm.po_ordered_v": _ordered(db, seeded.item_wt) > 0,
        "dashboard placed-PO rows": bool(dash._placed_po_rows(filters)),
        "dashboard incoming_po_count": dash.rollups(filters)["incoming_po_count"] > 0,
    }
    assert set(incoming.values()) == {False}, \
        f"the readers disagree about a closed line being incoming: {incoming}"

    # The document's own SUPPLY figures must exclude it too: 5 outstanding on one open line.
    # `open_qty` / `open_line_count` are the figures the plan reads. `total_qty` /
    # `line_count` are what the order SAYS and deliberately still include the closed line -
    # a column labelled "Total qty" reading 0 on a fully-received order is the label lying,
    # which is how a year of imported purchase history rendered as empty orders.
    view = PurchaseOrderService(db).get_one(str(_header(db, seeded.main_po)["id"]))
    assert (view["open_qty"], view["open_line_count"]) == (5.0, 1), \
        "the purchase order still counts a closed line as incoming supply"
    assert (view["total_qty"], view["line_count"]) == (65.0, 2), \
        "the order says 65 over two lines, and the detail page must be able to say so"

    # And a purchase order whose ONLY line is closed is not on order at all. Seeded directly
    # with the exact row `apply()` writes when a line leaves the book (asserted above), because
    # a file can only close a document's lines while naming that document, which necessarily
    # leaves it one open line.
    spent = PurchaseOrder(id=_u(), po_number=seeded.alt_po, status=LIVE)
    db.add(spent)
    db.flush()
    pid = db.execute(text("SELECT id FROM products WHERE product_code = :c"),
                     {"c": seeded.item_blue}).scalar()
    db.add(PurchaseOrderLine(id=_u(), purchase_order_id=spent.id, product_id=str(pid),
                             qty_ordered=40, qty_received=0, line_status="closed",
                             expected_date=date(2026, 11, 15)))
    db.flush()

    spent_view = PurchaseOrderService(db).get_one(spent.id)
    spent_incoming = {
        "scm.po_ordered_v": _ordered(db, seeded.item_blue) > 0,
        "purchase_order_service is_on_order": spent_view["is_on_order"],
    }
    assert set(spent_incoming.values()) == {False}, \
        f"the readers disagree about a wholly closed purchase order: {spent_incoming}"


# --------------------------------------------------------------------------- #
# 6. identity: a line that comes back is the same line
# --------------------------------------------------------------------------- #

def test_a_closed_line_that_reappears_is_reopened_in_place(db, seeded):
    """A line that comes back is the same line, and its booked receipt belongs to it.

    `_existing_lines` only ever sees `line_status = 'open'` rows, so a line the importer closed
    last week is invisible this week and reappears as an ADD. The consequence is not one extra
    row: the receipt already booked against the old row stays stranded on it while the new row
    starts at zero received, so the two rows together claim the full ordered quantity is still
    at sea. Supply is then overstated by everything already delivered, indefinitely, and the
    doubling is stable - re-uploading never corrects it.
    """
    at = date(2026, 9, 30)
    present = po_workbook([
        po_minimal_row(seeded.main_po, seeded.creditor_main, seeded.item_wt, 60, at,
                       seeded.loc_project),
        po_minimal_row(seeded.main_po, seeded.creditor_main, seeded.item_rl, 100,
                       date(2026, 7, 1), seeded.loc_project),
    ], headers=PO_MINIMAL)
    absent = po_workbook([
        po_minimal_row(seeded.main_po, seeded.creditor_main, seeded.item_rl, 100,
                       date(2026, 7, 1), seeded.loc_project),
    ], headers=PO_MINIMAL)
    svc.apply(db, present, PO)
    original = _po_lines(db, seeded.main_po, seeded.item_wt)[0]["id"]
    # 15 of the 60 arrive and are booked in, then the line drops out of the extract.
    db.execute(text("UPDATE purchase_order_lines SET qty_received = 15 WHERE id = :i"),
               {"i": str(original)})
    db.flush()
    svc.apply(db, absent, PO)

    # It is back, with the 45 that never arrived still outstanding.
    svc.apply(db, po_workbook([
        po_minimal_row(seeded.main_po, seeded.creditor_main, seeded.item_wt, 45, at,
                       seeded.loc_project),
        po_minimal_row(seeded.main_po, seeded.creditor_main, seeded.item_rl, 100,
                       date(2026, 7, 1), seeded.loc_project),
    ], headers=PO_MINIMAL), PO)

    rows = _po_lines(db, seeded.main_po, seeded.item_wt)
    assert len(rows) == 1, \
        "the line that came back was inserted again instead of being reopened"
    assert rows[0]["id"] == original, "the reopened line is not the row the receipt sits on"
    assert rows[0]["line_status"] == "open", "the line is back in the book but still closed"
    assert float(rows[0]["qty_received"]) == 15.0, "the booked receipt was stranded"
    assert _ordered(db, seeded.item_wt) == 45.0, \
        "supply is not ordered minus what already arrived"


# --------------------------------------------------------------------------- #
# 7. honesty: a quantity that grows on a line with receipts is a question, not a fact
# --------------------------------------------------------------------------- #

def test_a_rising_quantity_on_a_part_received_line_is_reported(db, seeded):
    """A stale file and a genuine increase look identical from the file alone, so a human
    has to see it.

    Apply reads the extract as OUTSTANDING and writes `qty_ordered = already_received +
    outstanding`, which is right for a fresh file. Re-upload a file taken BEFORE the goods
    receipt and the same arithmetic inflates the order by exactly the quantity that has already
    arrived: 100 ordered, 30 received, a stale file still saying 100 outstanding becomes 130
    ordered. The plan then expects a container that no supplier is sending. The write itself is
    not the problem - the silence is, because the two cases cannot be told apart without asking
    the buyer.
    """
    at = date(2026, 7, 1)
    file = po_workbook([
        po_minimal_row(seeded.main_po, seeded.creditor_main, seeded.item_rl, 100, at,
                       seeded.loc_project),
    ], headers=PO_MINIMAL)
    svc.apply(db, file, PO)
    line = _po_lines(db, seeded.main_po, seeded.item_rl)[0]["id"]
    db.execute(text("UPDATE purchase_order_lines SET qty_received = 30 WHERE id = :i"),
               {"i": str(line)})
    db.flush()

    # The same file again, which now restates the pre-receipt outstanding figure.
    out = svc.apply(db, file, PO)

    blob = _report_blob(out)
    assert _reported(out), \
        "the order grew on a line that already carries receipts and nothing was reported"
    assert seeded.main_po in blob and seeded.item_rl in blob, \
        f"the report does not name the document and item that grew: {blob}"


# --------------------------------------------------------------------------- #
# 8. identity: a repeated line is a second line, and stays one line on re-upload
# --------------------------------------------------------------------------- #

def test_a_line_stated_twice_becomes_two_lines_and_stays_two_on_re_upload(db, seeded):
    """The defect this pinned was double supply that then sits perfectly stable.

    Its original fix was a reader-level complaint, and that was measured wrong. On the client's
    real export 605 groups share a document, item and location: 567 of them differ in quantity
    (SO339706 asks for 31 and for 20, which is one order with two deliveries and is exactly
    what the plan must see) and the other 38 are byte-identical and legitimate - "totally
    acceptable in 1 SO". The complaint therefore fired 605 times on a good file, on the same
    lists that carry the rows which really did fail, so it has been removed (AC-2.1).

    What actually prevents the doubling is grouped pairing in `outstanding_diff`, and this test
    now pins THAT: a file stating the line twice writes two lines, and re-uploading the same
    file writes nothing further and reads `unchanged` twice - so supply cannot creep upward one
    upload at a time, which was the real fear. The sales-order equivalents live in
    `tests/scm/test_outstanding_duplicate_lines.py`.
    """
    at = date(2026, 7, 1)
    row = po_minimal_row(seeded.main_po, seeded.creditor_main, seeded.item_rl, 100, at,
                         seeded.loc_project)
    doubled = po_workbook([row, row], headers=PO_MINIMAL)
    svc.apply(db, po_workbook([row], headers=PO_MINIMAL), PO)

    grown = svc.apply(db, doubled, PO)
    again = svc.apply(db, doubled, PO)

    assert "stated twice" not in _report_blob(grown), \
        "a legitimately repeated line is still reported as a duplicate"
    assert len(_po_lines(db, seeded.main_po, seeded.item_rl)) == 2
    assert again["applied"] == {"added": 0, "updated": 0, "closed": 0, "unchanged": 2}, \
        f"re-uploading the same file was not a no-op: {again['applied']}"
    assert len(_po_lines(db, seeded.main_po, seeded.item_rl)) == 2, \
        "the second upload added a third line, so on-order creeps upward per upload"


# --------------------------------------------------------------------------- #
# 9. one definition: the cost the co-pilot ranks on has to be current
# --------------------------------------------------------------------------- #

def test_unit_cost_and_currency_are_refreshed_when_a_line_is_updated(db, seeded):
    """A price is only worth ranking on if it is this week's price.

    `money_cols` is applied on the ADD branch only, so a line's `unit_cost` and `currency` are
    frozen at whatever the first extract said. The cash co-pilot then ranks and budgets on a
    stale price - and a line that arrived with the cost column blank, priced in a later
    extract, stays blank forever, so it is ranked as if it were free. Both directions are
    asserted: a price that changed, and a price that arrived late.
    """
    po_date = date(2026, 4, 6)

    def _file(rl_qty, rl_cost, rl_ccy, wt_qty, wt_cost, wt_ccy):
        return po_workbook([
            po_row(SUPPLIER_MAIN_LABEL, seeded.main_po, po_date, seeded.creditor_main,
                   seeded.item_rl, rl_qty, 0, date(2026, 7, 1), seeded.loc_project,
                   rl_cost, rl_ccy),
            po_row(SUPPLIER_MAIN_LABEL, seeded.main_po, po_date, seeded.creditor_main,
                   seeded.item_wt, wt_qty, 0, date(2026, 9, 30), seeded.loc_project,
                   wt_cost, wt_ccy),
        ])

    svc.apply(db, _file(100, 12.5, "MYR", 60, None, None), PO)

    # A week later: both quantities moved, one line was repriced, the other finally priced.
    svc.apply(db, _file(120, 14.0, "USD", 80, 5.0, "MYR"), PO)

    repriced = _po_lines(db, seeded.main_po, seeded.item_rl)[0]
    assert (float(repriced["unit_cost"]), repriced["currency"]) == (14.0, "USD"), \
        "the co-pilot is still ranking this line on last week's price"
    late = _po_lines(db, seeded.main_po, seeded.item_wt)[0]
    assert late["unit_cost"] is not None, "a cost supplied later never arrived"
    assert (float(late["unit_cost"]), late["currency"]) == (5.0, "MYR")


# --------------------------------------------------------------------------- #
# 10. one definition: no PO date, no measured lead time
# --------------------------------------------------------------------------- #

def test_the_po_date_and_currency_from_the_file_land_on_the_header(db, seeded):
    """Without the order date there is nothing to measure supplier lead time against.

    `PO DATE` is alias-mapped (`import_field_alias`, doc_type `outstanding_po`) and then
    dropped on the floor: the reader never carries it and the write never stores it, so
    `purchase_orders.issue_date` stays NULL. `scm.receipt_lead_v` computes `lead_days` as
    `picking_date - po.issue_date`, so every imported order contributes NOTHING to the measured
    lead time, the supplier scorecard has no observations, and safety stock falls back to a
    default lead time for suppliers we have years of history with. The header currency goes the
    same way, which is what a purchase order is denominated in for the cash plan.
    """
    svc.apply(db, po_week1(seeded), PO)

    main, alt = _header(db, seeded.main_po), _header(db, seeded.alt_po)
    assert (main["issue_date"], alt["issue_date"]) == (date(2026, 4, 6), date(2026, 4, 20)), \
        "the file's PO DATE was discarded, so lead time can never be measured"
    assert (main["currency"], alt["currency"]) == ("MYR", "USD"), \
        "the purchase order is not denominated in anything"


# --------------------------------------------------------------------------- #
# 11. honesty: who we are chasing must be what the file says
# --------------------------------------------------------------------------- #

def test_two_creditor_codes_on_one_po_number_are_reported(db, seeded):
    """One purchase order has one supplier, so a file naming two is a file to fix.

    `party_by_doc.setdefault` keeps whichever row the reader met first and discards the rest in
    silence. Half of that document's lines are then attributed to a supplier that did not sell
    them: the expediting list chases the wrong company, and the supplier scorecard blames
    them for a late delivery they were never asked to make. A good report names the document
    and both codes so the operator can see which two disagree.
    """
    file = po_workbook([
        po_minimal_row(seeded.main_po, seeded.creditor_main, seeded.item_rl, 100,
                       date(2026, 7, 1), seeded.loc_project),
        po_minimal_row(seeded.main_po, seeded.creditor_alt, seeded.item_wt, 60,
                       date(2026, 9, 30), seeded.loc_project),
    ], headers=PO_MINIMAL)

    res = svc.preview(db, file, PO)

    blob = _report_blob(res)
    assert _reported(res), \
        "two different creditor codes on one PO number: first row won, in silence"
    assert seeded.main_po in blob, \
        f"the report does not name the document whose supplier is ambiguous: {blob}"


def test_a_contradicted_supplier_link_is_overwritten_and_reported(db, seeded):
    """AutoCount is the system of record for who we bought from.

    `apply` attaches a supplier only when the header has none, so an existing link is never
    corrected - not when it was wrong, and not when the supplier genuinely changed. Chasing the
    wrong supplier is the failure mode: the expediting call goes to a company with no such
    order, and the late delivery is scored against them. Overwriting alone is not enough
    either, because a link changing under the operator is exactly the kind of thing they need
    told.
    """
    def _file(creditor):
        return po_workbook([
            po_minimal_row(seeded.main_po, creditor, seeded.item_rl, 100, date(2026, 7, 1),
                           seeded.loc_project),
        ], headers=PO_MINIMAL)

    svc.apply(db, _file(seeded.creditor_main), PO)
    assert _supplier_of(db, seeded.main_po) == (seeded.creditor_main, SUPPLIER_MAIN_LABEL)

    out = svc.apply(db, _file(seeded.creditor_alt), PO)

    assert _supplier_of(db, seeded.main_po) == (seeded.creditor_alt, SUPPLIER_ALT_LABEL), \
        "the file's supplier was ignored: we would chase the wrong company"
    blob = _report_blob(out)
    assert _reported(out), "the supplier on a purchase order changed and nobody was told"
    assert seeded.main_po in blob, \
        f"the report does not name the document whose supplier changed: {blob}"
