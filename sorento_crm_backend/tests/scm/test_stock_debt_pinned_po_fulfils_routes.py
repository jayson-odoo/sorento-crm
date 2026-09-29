"""R43 (owner, 28 Sep 2026, #1346): a PO line pinned to a sales order fulfils it, over the wire.

The arithmetic is `test_stock_debt_pinned_po_fulfils.py`'s. What is proved here is the read
and the drill: the S/O line reference (`purchase_order_lines.from_so_line_ref` against
`sales_order_lines.source_ref`) reaching the pin, the demand rows' Short and Covered by, the
Supply tab listing the pinned lines, and the board's month cell reading what the drill does.

The owner's production case, re-seeded relative to today: SO419208 x CSK14A-NL at one BB
bin, two open lines due 14 days ago (4 outstanding of 135 ordered, and 1,305), and PO
202609-S0029 dated 18 days ago: 41 with no S/O, 4 naming the 4-unit line, 1,305 naming the
1,305 line. Nothing received, nothing placed.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.services.scm.supply_assignment import month_key
from tests.scm.conftest import SORENTO_COMPANY_ID, requires_pg
from tests.scm.test_stock_debt_po_supply_routes import _po_line, _policy, _purchase_order
from tests.scm.test_stock_debt_routes import (
    BASE,
    TODAY,
    _client,
    _demand,
    _months_ahead,
    _product,
    _row_of,
    _u,
    _warehouse,
)

pytestmark = requires_pg


def _production(db, *, grace: int, dead: int, line_refs: bool = True):
    from app.models.order import SalesOrderLine

    _policy(db, grace, dead)
    marker = f"ZZTPF{_u()[:6]}".upper()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    product = _product(db, f"{marker}-CSK14A-NL")
    due = TODAY - timedelta(days=14)
    order, row_4 = _demand(
        db, product, warehouse, qty=135, qty_delivered=131, required_date=due,
        so_number=f"{marker}-SO419208",
    )
    order.source_ref = f"ZZTBOOK:{marker}"
    row_4.line_no = 1
    row_1305 = SalesOrderLine(
        id=_u(), company_id=SORENTO_COMPANY_ID, sales_order_id=order.id,
        product_id=product.id, warehouse_id=warehouse.id, qty_ordered=Decimal("1305"),
        qty_delivered=Decimal("0"), required_date=due, line_status="open", line_no=2,
    )
    db.add(row_1305)
    if line_refs:
        row_4.source_ref = f"ZZTBOOK:{marker}:d1"
        row_1305.source_ref = f"ZZTBOOK:{marker}:d2"
    db.flush()
    po = _purchase_order(db, f"{marker}-202609-S0029", issue_date=TODAY - timedelta(days=30))
    delivery = TODAY - timedelta(days=18)
    free = _po_line(db, po, product, warehouse, qty=41, delivery=delivery)
    line_2 = _po_line(
        db, po, product, warehouse, qty=4, delivery=delivery,
        so_ref=f"ZZTBOOK:{marker}:d1",
    )
    line_3 = _po_line(
        db, po, product, warehouse, qty=1305, delivery=delivery,
        so_ref=f"ZZTBOOK:{marker}:d2",
    )
    db.flush()
    return {
        "product": product, "row_4": row_4, "row_1305": row_1305, "free": free,
        "line_2": line_2, "line_3": line_3, "marker": marker,
    }


def _cell(c, seed, month):
    got = c.get(f"{BASE}/{seed['product'].id}/cell", params={"month": month})
    assert got.status_code == 200, got.text
    return got.json()


def _board_balance(c, seed, month):
    got = c.get(BASE, params={"query": seed["marker"], "only_debt": False, "limit": 25})
    assert got.status_code == 200, got.text
    row = _row_of(got.json(), seed["product"].product_code)
    return {m["key"]: m["balance"] for m in row["months"]}[month]


def _assert_fulfilled(cell, seed):
    rows = {row["open_qty"]: row for row in cell["demand"]}
    assert set(rows) == {4, 1305}, cell["demand"]
    for qty, po_line in ((4, seed["line_2"]), (1305, seed["line_3"])):
        row = rows[qty]
        assert row["status"] == "pinned", row
        assert row["assigned_qty"] == qty
        assert row["short_qty"] == 0
        assert [(e["po_line_id"], e["qty"]) for e in row["assigned_from"]] == [
            (str(po_line.id), qty)
        ], "Covered by lists only the PO line that gave this row its quantity"
    assert sum(row["assigned_qty"] for row in cell["demand"]) == 1309
    assert sum(row["short_qty"] for row in cell["demand"]) == 0

    so_number = f"{seed['marker']}-SO419208"
    supply = {row["po_line_id"]: row for row in cell["supply"] if row["kind"] == "po"}
    assert supply[str(seed["line_2"].id)]["assigned_to"] == [
        {"so_number": so_number, "qty": 4, "line_no": 1}
    ]
    assert supply[str(seed["line_3"].id)]["assigned_to"] == [
        {"so_number": so_number, "qty": 1305, "line_no": 2}
    ]
    assert len([row for row in cell["supply"] if row["kind"] == "po"]) == len(supply), (
        "each PO line is listed once"
    )


@pytest.mark.parametrize("line_refs", [True, False])
def test_production_case_at_the_0_day_rule(scm_app, line_refs):
    """AC-PO-10..13 at the shipped 0-day rule: the PO is 18 days past its date and still
    fulfils SO419208. Assigned 1,309, Short 0, line 2 on the 4 row and line 3 on the 1,305
    row, the Supply tab lists both with Assigned to. Line 1's 41 has no S/O; R44 (#1359)
    keeps the overdue rule off this page, so it is free supply and the month reads +41.

    `line_refs=False`: the S/O resolves only to the ORDER, and quantity decides the row."""
    app, db = _client(scm_app)
    seed = _production(db, grace=0, dead=0, line_refs=line_refs)
    month = month_key(TODAY)

    with TestClient(app) as c:
        cell = _cell(c, seed, month)
        balance = _board_balance(c, seed, month)

    _assert_fulfilled(cell, seed)
    free = [row for row in cell["supply"] if row["po_line_id"] == str(seed["free"].id)]
    assert [(row["overdue"], row["free_qty"], row["assigned_to"]) for row in free] == [
        (False, 41, [])
    ]
    assert balance == 41


def test_production_case_under_a_raised_rule_is_not_short_1309(scm_app):
    """AC-PO-11 + AC-PO-13, the owner's second screen (raised to 30 there; 45 here). Before
    R44 (#1359) the PO counted 45 days from today, in a later month; the stock debt page
    now ignores the grace, so every line lands in the current month. The rows are still
    fulfilled (Short 0), the month reads +41 (the unpinned line), and the later month lists
    no PO line at all."""
    app, db = _client(scm_app)
    seed = _production(db, grace=45, dead=45)
    month = month_key(TODAY)

    with TestClient(app) as c:
        cell = _cell(c, seed, month)
        balance = _board_balance(c, seed, month)
        later = _cell(c, seed, month_key(TODAY + timedelta(days=45)))

    _assert_fulfilled(cell, seed)
    assert cell["supply_total_qty"] == 1350
    home = {row["po_line_id"]: row for row in cell["supply"] if row["kind"] == "po"}
    assert home[str(seed["free"].id)]["free_qty"] == 41
    assert home[str(seed["line_3"].id)]["free_qty"] == 0
    assert balance == 41
    assert [row for row in later["supply"] if row["kind"] == "po"] == []


def test_a_partly_pinned_po_line_is_free_only_in_its_own_month(scm_app):
    """AC-PO-13, the footing half: a PO line of 100 delivering two months out names an order
    whose row this month needs 30. This month's drill lists it with Assigned to and Free 0,
    so Free less Short still foots with the board cell; its own month lists the other 70
    free. `supply_total_qty` sums the column as listed."""
    app, db = _client(scm_app)
    _policy(db, 0, 0)
    marker = f"ZZTPF{_u()[:6]}".upper()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    product = _product(db, f"{marker}-A")
    order, row = _demand(
        db, product, warehouse, qty=30, required_date=TODAY, so_number=f"{marker}-SO1",
    )
    order.source_ref = f"ZZTBOOK:{marker}"
    row.source_ref = f"ZZTBOOK:{marker}:d1"
    delivery = _months_ahead(2)
    po = _purchase_order(db, f"{marker}-PO", issue_date=TODAY)
    po_line = _po_line(
        db, po, product, warehouse, qty=100, delivery=delivery,
        so_ref=f"ZZTBOOK:{marker}:d1",
    )
    db.flush()
    seed = {"product": product, "marker": marker}

    with TestClient(app) as c:
        here = _cell(c, seed, month_key(TODAY))
        home = _cell(c, seed, month_key(delivery))
        balance = _board_balance(c, seed, month_key(TODAY))
        home_balance = _board_balance(c, seed, month_key(delivery))

    [demand] = here["demand"]
    assert (demand["status"], demand["short_qty"]) == ("pinned", 0)
    [listed] = [r for r in here["supply"] if r["po_line_id"] == str(po_line.id)]
    assert listed["free_qty"] == 0
    assert listed["assigned_to"][0]["qty"] == 30
    assert here["supply_total_qty"] == 100
    assert balance == 0
    [own] = [r for r in home["supply"] if r["po_line_id"] == str(po_line.id)]
    assert own["free_qty"] == 70
    assert home_balance == 70
