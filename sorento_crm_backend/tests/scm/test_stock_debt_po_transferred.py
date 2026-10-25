"""SUPPLY-SPO-LINK (owner prod report, 25 Oct 2026): a placement on a PO line that is no
longer on order stood a phantom PO back up as supply.

The shape on the book: two auto placements sit on PO lines that AutoCount has transferred in
full onto a shipping order (`qty_received = qty_ordered`, line closed), and that shipping order
has landed, so the goods are on hand at the bin. `_po_rows` rightly reads those lines as not on
order, so the PO event is not in the span; `_holds` still handed each placement on as a `po:`
hold for its full quantity, and `assign()` honoured it off an event stood up from the hold
(AC-S2-1b): kind PO, no bin, blank Received, counted as supply. The landed goods then covered
the next open lines of the same product as free stock, so the Supply tab foots twice.

Owner ruling (standing): once a PO line is received it is on-hand quantity and is never supply;
a partly received line counts only what is still on order.

`purchase_order_lines.qty_received` is the AutoCount TRANSFER onto a shipping order, not a
physical receipt (`project_supply_service._po_received_by_so_line_ref`, R7 follow-up). So the
placement follows the goods: what the PO line still has on order stays a PO hold, and what it
transferred is held on the SPO allocations the line became (OI-SPO-EXACT key), each through
the SPO branch's own rule (incoming: an SPO hold; landed: an on-hand hold at the SPO's bin,
SPO-RECEIVED-PIN).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.services.scm.supply_assignment import month_key
from tests.scm.conftest import SORENTO_COMPANY_ID, requires_pg
from tests.scm.test_stock_debt_routes import (  # noqa: F401 (helpers, not tests)
    BASE,
    _assert_pinned_on_the_bin,
    _client,
    _demand,
    _months_ahead,
    _order_back_link_on_po,
    _product,
    _project_line_for,
    _spo,
    _stock,
    _u,
    _warehouse,
)

pytestmark = requires_pg

TODAY = date.today()


def _po_line(db, product, warehouse, *, ordered, transferred, open_line=None):
    """A PO line with a `source_ref`, the key OI-SPO-EXACT resolves an SPO allocation by.
    `open_line` defaults to "still something on order"."""
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine

    still_on_order = ordered > transferred if open_line is None else open_line
    po = PurchaseOrder(
        id=_u(),
        po_number=f"ZZTPO{_u()[:6]}".upper(),
        issue_date=TODAY - timedelta(days=60),
        status="active" if still_on_order else "closed",
        company_id=SORENTO_COMPANY_ID,
    )
    db.add(po)
    db.flush()
    line = PurchaseOrderLine(
        id=_u(),
        purchase_order_id=po.id,
        product_id=product.id,
        warehouse_id=warehouse.id,
        qty_ordered=Decimal(str(ordered)),
        qty_received=Decimal(str(transferred)),
        line_status="open" if still_on_order else "closed",
        source_ref=f"ZZT:{_u()[:8]}:{_u()[:8]}",
        company_id=SORENTO_COMPANY_ID,
    )
    db.add(line)
    db.flush()
    return po, line


def _transferred_onto(
    db, product, po, po_line, warehouse, *, qty, received, receipt_status, arrives,
):
    """The SPO allocation the PO line was transferred onto: `from_po_number` +
    `from_po_line_ref` name the line, exactly as the AutoCount feed writes them."""
    allocation = _spo(
        db, product, warehouse, qty=qty, arrives=arrives, received=received,
        receipt_status=receipt_status,
    )
    allocation.from_po_number = po.po_number
    allocation.from_po_line_ref = po_line.source_ref
    db.flush()
    return allocation


def _case(db, *, ordered, transferred, open_line=None, link_qty=50):
    """SO1 (50) holds a placement on the PO line; SO2 (50) at the same bin has none.
    Returns (marker, warehouse, product, po, po_line, due)."""
    marker = f"ZZTSPL{_u()[:6]}".upper()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    product = _product(db, f"{marker}-A")
    due = _months_ahead(1)
    _order, core_line = _demand(
        db, product, warehouse, qty=50, required_date=due, so_number=f"{marker}-SO1",
    )
    _demand(db, product, warehouse, qty=50, required_date=due, so_number=f"{marker}-SO2")
    project_order, project_line = _project_line_for(db, core_line)
    po, po_line = _po_line(
        db, product, warehouse, ordered=ordered, transferred=transferred, open_line=open_line,
    )
    _order_back_link_on_po(db, project_order, project_line, po_line=po_line, qty=link_qty)
    db.flush()
    return marker, warehouse, product, po, po_line, due


def _cells(c, product, *months):
    return {
        month: c.get(f"{BASE}/{product.id}/cell", params={"month": month}).json()
        for month in months
    }


def _po_rows(*cells):
    return [row for cell in cells for row in cell["supply"] if row["kind"] == "po"]


def test_a_placement_on_a_po_line_transferred_onto_a_landed_spo_pins_the_bin_not_the_po(
    scm_app,
):
    """The owner's report: the PO line is closed (50 of 50 transferred), the SPO it became
    landed 50 into the bin. SO1's placement must hold the bin's on hand, SO2 reads short,
    and no PO row is listed in any month: the month owes 50 against 50 real units."""
    app, db = _client(scm_app)
    marker, warehouse, product, po, po_line, due = _case(db, ordered=50, transferred=50)
    _transferred_onto(
        db, product, po, po_line, warehouse, qty=50, received=50,
        receipt_status="fully_received", arrives=TODAY - timedelta(days=10),
    )
    _stock(db, product, warehouse, 50)
    with TestClient(app) as c:
        cells = _cells(c, product, month_key(TODAY), month_key(due))
        assert _po_rows(*cells.values()) == []
        _assert_pinned_on_the_bin(c, marker=marker, warehouse=warehouse, product=product, due=due)


def test_a_placement_on_a_po_line_transferred_onto_an_spo_in_transit_pins_the_spo(scm_app):
    """The same transfer, not landed yet: the goods are on the SPO, which is supply in its
    own month. The placement follows them onto it (the line reads pinned off the SPO), and
    the PO is not stood up as a second supply of the same units."""
    app, db = _client(scm_app)
    marker, warehouse, product, po, po_line, due = _case(db, ordered=50, transferred=50)
    allocation = _transferred_onto(
        db, product, po, po_line, warehouse, qty=50, received=0, receipt_status="pending",
        arrives=due,
    )
    with TestClient(app) as c:
        cells = _cells(c, product, month_key(TODAY), month_key(due))
    cell = cells[month_key(due)]

    assert _po_rows(*cells.values()) == []
    by_so = {line["so_number"]: line for line in cell["demand"]}
    so1 = by_so[f"{marker}-SO1"]
    assert so1["status"] == "pinned"
    assert so1["assigned_qty"] == 50
    assert [
        (entry["kind"], entry["spo_number"], entry["qty"]) for entry in so1["assigned_from"]
    ] == [("spo", allocation.spo_number, 50)]
    assert by_so[f"{marker}-SO2"]["status"] == "short"

    [spo_row] = [row for row in cell["supply"] if row["kind"] == "spo"]
    assert spo_row["outstanding_qty"] == 50
    assert spo_row["assigned_to"] == [
        {"so_number": f"{marker}-SO1", "line_no": None, "qty": 50},
    ]
    # 100 owed against the 50 on the SPO: the month owes 50, never 0.
    assert cell["supply_total_qty"] == 50


def test_a_placement_on_a_partly_transferred_po_line_holds_the_po_only_for_what_is_on_order(
    scm_app,
):
    """100 ordered, 20 transferred onto an SPO in transit, 80 still on order. SO1's
    placement of 50 follows the goods: the 20 already moved onto the SPO first, then 30 of
    what the PO still has on order. The PO row counts its remaining 80 and nothing more."""
    app, db = _client(scm_app)
    marker, warehouse, product, po, po_line, due = _case(db, ordered=100, transferred=20)
    allocation = _transferred_onto(
        db, product, po, po_line, warehouse, qty=20, received=0, receipt_status="pending",
        arrives=due,
    )
    from app.services.project_supply_service import ProjectSupplyService

    [po_supply] = ProjectSupplyService(db).po_by_location(
        [str(product.id)], [str(warehouse.id)]
    )[(str(product.id), str(warehouse.id))]
    po_month = month_key(max(po_supply.bought_for or po_supply.arrival_date, TODAY))

    with TestClient(app) as c:
        cells = _cells(c, product, *sorted({month_key(TODAY), month_key(due), po_month}))
    so1 = {
        line["so_number"]: line for line in cells[month_key(due)]["demand"]
    }[f"{marker}-SO1"]
    assert so1["status"] == "pinned"
    assert so1["assigned_qty"] == 50
    assert sorted(
        (entry["kind"], entry.get("po_number") or entry["spo_number"], entry["qty"])
        for entry in so1["assigned_from"]
    ) == sorted([("po", po.po_number, 30), ("spo", allocation.spo_number, 20)])

    [po_row] = _po_rows(*cells.values())
    assert (po_row["qty"], po_row["received_qty"], po_row["outstanding_qty"]) == (100, 20, 80)
    assert po_row["po_line_id"] == str(po_line.id)
    assert po_row["assigned_to"] == [
        {"so_number": f"{marker}-SO1", "line_no": None, "qty": 30},
    ]


def test_a_placement_on_a_po_line_closed_with_nothing_transferred_pins_nothing(scm_app):
    """A short-closed line: nothing on order, nothing transferred, so nothing to hold. SO1
    reads short and no PO row is stood up for it."""
    app, db = _client(scm_app)
    marker, _warehouse_row, product, _po, _po_line, due = _case(
        db, ordered=50, transferred=0, open_line=False,
    )
    with TestClient(app) as c:
        cells = _cells(c, product, month_key(TODAY), month_key(due))
    assert _po_rows(*cells.values()) == []
    so1 = {
        line["so_number"]: line for line in cells[month_key(due)]["demand"]
    }[f"{marker}-SO1"]
    assert so1["status"] == "short"
    assert so1["assigned_from"] == []
    assert all(cell["supply"] == [] for cell in cells.values())


def test_a_placement_whose_transferred_goods_have_left_the_bin_pins_nothing(scm_app):
    """Transferred, landed, and since shipped: the bin is empty, so the promise covers
    nobody (SPO-RECEIVED-PIN's own empty-bin rule), and no PO is stood up instead."""
    app, db = _client(scm_app)
    marker, warehouse, product, po, po_line, due = _case(db, ordered=50, transferred=50)
    _transferred_onto(
        db, product, po, po_line, warehouse, qty=50, received=50,
        receipt_status="fully_received", arrives=TODAY - timedelta(days=10),
    )
    with TestClient(app) as c:
        cells = _cells(c, product, month_key(TODAY), month_key(due))
    assert _po_rows(*cells.values()) == []
    so1 = {
        line["so_number"]: line for line in cells[month_key(due)]["demand"]
    }[f"{marker}-SO1"]
    assert so1["status"] == "short"
    assert so1["assigned_from"] == []
    assert all(cell["supply"] == [] for cell in cells.values())


def test_the_board_assignment_stands_no_po_up_for_a_transferred_line(scm_app):
    """The fulfilment board, the confirm recheck and the order inquiry picker read the same
    assignment through `assignments_for` (`ProjectSupplyService.planning_assignments`). It
    must not count the transferred PO line either: SO1 is held on the bin, SO2 is not
    covered by the same units, and no PO event is supply."""
    _app, db = _client(scm_app)
    marker, warehouse, product, po, po_line, _due = _case(db, ordered=50, transferred=50)
    _transferred_onto(
        db, product, po, po_line, warehouse, qty=50, received=50,
        receipt_status="fully_received", arrives=TODAY - timedelta(days=10),
    )
    _stock(db, product, warehouse, 50)

    from app.services.scm.stock_debt_service import StockDebtService

    result = StockDebtService(db).assignments_for(
        [str(product.id)], {str(warehouse.id): warehouse}
    )[str(product.id)]
    assert [event.key for event in result.supply if event.kind == "po"] == []
    covered = {
        line.line.so_number: sum(item.qty for item in line.assigned) for line in result.lines
    }
    assert covered == {f"{marker}-SO1": 50, f"{marker}-SO2": 0}
    [so1] = [line for line in result.lines if line.line.so_number == f"{marker}-SO1"]
    assert [(item.event.kind, item.event.key) for item in so1.assigned] == [
        ("on_hand", f"on_hand:{warehouse.id}")
    ]
    # Held by its placement, not handed the bin by the walk's tie-break.
    assert all(item.pinned for item in so1.assigned)


# ------------------------------------------------------------------ review round 1


def test_the_book_s_o_may_still_pin_what_the_placement_left_on_the_po(scm_app):
    """100 ordered, 20 transferred onto an SPO in transit, 80 on order; the PO line's own
    S/O names SO-B. SO-A's placement of 50 sits 20 on the SPO and 30 on the PO, so the
    S/O may still pin 80 - 30 = 50 of the PO to SO-B. Netting the whole placement (50)
    would leave SO-B short 20 beside 20 free on the PO."""
    app, db = _client(scm_app)
    marker = f"ZZTSPL{_u()[:6]}".upper()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    product = _product(db, f"{marker}-A")
    due = _months_ahead(1)
    _order_a, line_a = _demand(
        db, product, warehouse, qty=50, required_date=due, so_number=f"{marker}-SOA",
    )
    order_b, line_b = _demand(
        db, product, warehouse, qty=50, required_date=due, so_number=f"{marker}-SOB",
    )
    order_b.source_ref = f"ZZTBOOK:{marker}"
    line_b.source_ref = f"ZZTBOOK:{marker}:1"
    project_order, project_line = _project_line_for(db, line_a)
    po, po_line = _po_line(db, product, warehouse, ordered=100, transferred=20)
    po_line.from_so_line_ref = f"ZZTBOOK:{marker}:1"
    allocation = _transferred_onto(
        db, product, po, po_line, warehouse, qty=20, received=0, receipt_status="pending",
        arrives=due,
    )
    _order_back_link_on_po(db, project_order, project_line, po_line=po_line, qty=50)
    db.flush()

    with TestClient(app) as c:
        cell = c.get(f"{BASE}/{product.id}/cell", params={"month": month_key(due)}).json()
    by_so = {line["so_number"]: line for line in cell["demand"]}
    so_a, so_b = by_so[f"{marker}-SOA"], by_so[f"{marker}-SOB"]
    assert sorted(
        (entry["kind"], entry.get("po_number") or entry["spo_number"], entry["qty"])
        for entry in so_a["assigned_from"]
    ) == sorted([("po", po.po_number, 30), ("spo", allocation.spo_number, 20)])
    assert so_b["status"] == "pinned"
    assert so_b["assigned_qty"] == 50
    assert so_b["short_qty"] == 0


def test_an_spo_line_closed_with_nothing_landed_lets_the_placement_fall_to_the_po(scm_app):
    """50 of the line's 100 went onto an SPO line that was then closed with nothing
    received and nothing landed; AutoCount reopened the quantity on the PO (50 on order).
    That dead SPO line brought no goods anywhere, so it holds none of the placement: the
    placement's 50 sit on the PO's own 50 on order and SO1 reads pinned."""
    app, db = _client(scm_app)
    marker, warehouse, product, po, po_line, due = _case(db, ordered=100, transferred=50)
    dead = _transferred_onto(
        db, product, po, po_line, warehouse, qty=50, received=0, receipt_status="pending",
        arrives=due,
    )
    dead.line_status = "closed"
    db.flush()
    with TestClient(app) as c:
        cells = _cells(c, product, month_key(TODAY), month_key(due))
    so1 = {
        line["so_number"]: line for line in cells[month_key(due)]["demand"]
    }[f"{marker}-SO1"]
    assert so1["status"] == "pinned"
    assert [(entry["kind"], entry["qty"]) for entry in so1["assigned_from"]] == [("po", 50)]


def test_a_po_line_outside_the_span_is_held_only_for_what_it_still_has_on_order(scm_app):
    """The PO line's bin is outside the read span (not in fulfilment planning), so the
    placement is honoured off a stand-in event, which nothing but the hold itself caps.
    100 ordered, 70 already moved off the line, 30 on order: SO1's placement of 50 holds
    30, and SO1 reads 20 short, never 50 covered off a PO that can bring 30."""
    app, db = _client(scm_app)
    marker = f"ZZTSPL{_u()[:6]}".upper()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    outside = _warehouse(db, f"ZZTOUT{_u()[:4]}", planning=False)
    product = _product(db, f"{marker}-A")
    due = _months_ahead(1)
    _order, core_line = _demand(
        db, product, warehouse, qty=50, required_date=due, so_number=f"{marker}-SO1",
    )
    project_order, project_line = _project_line_for(db, core_line)
    _po, po_line = _po_line(db, product, outside, ordered=100, transferred=70)
    _order_back_link_on_po(db, project_order, project_line, po_line=po_line, qty=50)
    db.flush()
    with TestClient(app) as c:
        cell = c.get(f"{BASE}/{product.id}/cell", params={"month": month_key(due)}).json()
    [so1] = cell["demand"]
    assert so1["assigned_qty"] == 30
    assert so1["short_qty"] == 20
    assert [(entry["kind"], entry["qty"]) for entry in so1["assigned_from"]] == [("po", 30)]


def test_two_placements_share_what_the_transferred_spo_landed_not_the_whole_bin(scm_app):
    """50 ordered, all 50 transferred onto an SPO that landed 50 into a bin that holds 100
    (50 more from elsewhere). SO1 and SO2 each hold a placement of 50 on the PO line: the
    line's goods are 50, so only the first placement (SO1) is held on the bin; SO2's
    placement finds nothing left of what the line brought and is not pinned."""
    app, db = _client(scm_app)
    marker = f"ZZTSPL{_u()[:6]}".upper()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    product = _product(db, f"{marker}-A")
    due = _months_ahead(1)
    _o1, line1 = _demand(
        db, product, warehouse, qty=50, required_date=due, so_number=f"{marker}-SO1",
    )
    _o2, line2 = _demand(
        db, product, warehouse, qty=50, required_date=due, so_number=f"{marker}-SO2",
    )
    po, po_line = _po_line(db, product, warehouse, ordered=50, transferred=50)
    _transferred_onto(
        db, product, po, po_line, warehouse, qty=50, received=50,
        receipt_status="fully_received", arrives=TODAY - timedelta(days=10),
    )
    _stock(db, product, warehouse, 100)
    for minute, line in enumerate((line1, line2)):
        project_order, project_line = _project_line_for(db, line)
        _row, link = _order_back_link_on_po(
            db, project_order, project_line, po_line=po_line, qty=50,
        )
        # The placement made first is kept first (`linked_at`); `now()` is one instant
        # inside the test's transaction, so state the order outright.
        link.linked_at = datetime(2026, 10, 1, 9, minute)
    db.flush()
    with TestClient(app) as c:
        cell = c.get(f"{BASE}/{product.id}/cell", params={"month": month_key(due)}).json()
    by_so = {line["so_number"]: line for line in cell["demand"]}
    assert by_so[f"{marker}-SO1"]["status"] == "pinned"
    assert by_so[f"{marker}-SO2"]["status"] != "pinned"
