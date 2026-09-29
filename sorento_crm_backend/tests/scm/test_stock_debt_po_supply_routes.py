"""R42 (owner, 28 Sep 2026, #1331): purchase orders as Stock Debt supply, over the wire.

The arithmetic is `test_stock_debt_po_supply_walk.py`'s. What is proved here is the READ:
the S/O column's own reference (`purchase_order_lines.from_so_line_ref`, resolved against
`sales_orders.source_ref`) turned into a pin, the placement read beside it without double
counting, the overdue rule kept out of the page for a PO exactly as for an SPO (R44, owner,
29 Sep 2026, #1359), the drill's PO fields
by name (`response_model` drops what it does not declare), and the board's own path left
exactly as it was.

The owner's CSK14A-NL case (PO 202609-S0029) is re-seeded relative to today: the 1,305 and
the 4 are 14 days late and the free line 18 days late, as they were on 28 Sep 2026. The 41
went to BRW, a site pool; here the free line sits in the same group as the demand so it can
be seen covering something.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.services.scm import priority
from app.services.scm.supply_assignment import month_key
from tests.scm.conftest import SORENTO_COMPANY_ID, requires_pg
from tests.scm.test_stock_debt_routes import (
    BASE,
    TODAY,
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


def _policy(db, grace: int, dead: int) -> None:
    priority.create_revision(
        db, name=f"ZZT-po-{_u()[:6]}", factors={}, demand_class_weights={},
        reorder_coverage_until=None, overdue_grace_days=grace, overdue_dead_days=dead,
    )


def _purchase_order(db, number: str, *, issue_date):
    from app.models.procurement import PurchaseOrder

    po = PurchaseOrder(
        id=_u(), po_number=number, issue_date=issue_date, status="active",
        company_id=SORENTO_COMPANY_ID,
    )
    db.add(po)
    db.flush()
    return po


def _po_line(db, po, product, warehouse, *, qty, delivery, so_ref=None, seq=0):
    from app.models.procurement import PurchaseOrderLine

    line = PurchaseOrderLine(
        id=_u(), purchase_order_id=po.id, product_id=product.id,
        warehouse_id=warehouse.id, qty_ordered=Decimal(str(qty)),
        qty_received=Decimal("0"), line_status="open", expected_date=delivery,
        from_so_line_ref=so_ref, company_id=SORENTO_COMPANY_ID,
    )
    db.add(line)
    db.flush()
    return line


def _csk14a(db, *, grace: int, dead: int):
    """SO419208 (1,309 due next month) and an EARLIER unnamed order at the same bin, and
    PO 202609-S0029: 41 free (18 days late), 1,305 naming SO419208 (14 days late), 4
    naming SO419208 and placed 4 (14 days late)."""
    _policy(db, grace, dead)
    marker = f"ZZTPO{_u()[:6]}".upper()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    product = _product(db, f"{marker}-CSK14A-NL")
    due = _months_ahead(1)
    earlier = TODAY + timedelta(days=15) if grace else TODAY
    # 100, more than the free 41: without the S/O pins it would eat into the named lines.
    other_order, _other = _demand(
        db, product, warehouse, qty=100, required_date=earlier,
        so_number=f"{marker}-SO-OTHER",
    )
    order, core_line = _demand(
        db, product, warehouse, qty=1309, required_date=due,
        so_number=f"{marker}-SO419208",
    )
    order.source_ref = f"ZZTBOOK:{marker}"
    db.flush()
    po = _purchase_order(db, f"{marker}-202609-S0029", issue_date=TODAY - timedelta(days=30))
    free = _po_line(db, po, product, warehouse, qty=41, delivery=TODAY - timedelta(days=18))
    named = _po_line(
        db, po, product, warehouse, qty=1305, delivery=TODAY - timedelta(days=14),
        so_ref=f"ZZTBOOK:{marker}:11",
    )
    placed = _po_line(
        db, po, product, warehouse, qty=4, delivery=TODAY - timedelta(days=14),
        so_ref=f"ZZTBOOK:{marker}:12",
    )
    project_order, project_line = _project_line_for(db, core_line)
    _order_back_link_on_po(db, project_order, project_line, po_line=placed, qty=4)
    db.flush()
    return {
        "product": product, "due": due, "po": po, "free": free, "named": named,
        "placed": placed, "marker": marker, "warehouse": warehouse,
    }


def _by_so(cell, suffix):
    rows = [row for row in cell["demand"] if row["so_number"].endswith(suffix)]
    assert len(rows) == 1, cell["demand"]
    return rows[0]


def test_a_po_line_naming_a_sales_order_covers_it_first_at_14_90(scm_app):
    """AC-PO-3 + AC-PO-5 + AC-PO-6 (recommended policy). The book S/O pins 1,305 and the
    placement 4 to SO419208 - 1,309 in all, never counted twice - even though another
    order is due earlier and would take the PO first-come; the 41 with no S/O is free and
    covers that earlier order. All three are late; R44 (#1359) lands them today on this
    page whatever the policy's grace, with the paperwork's own date beside it."""
    app, db = _client(scm_app)
    seed = _csk14a(db, grace=14, dead=90)
    assumed = TODAY

    with TestClient(app) as c:
        cell = c.get(
            f"{BASE}/{seed['product'].id}/cell", params={"month": month_key(seed["due"])}
        ).json()
        earlier = c.get(
            f"{BASE}/{seed['product'].id}/cell",
            params={"month": month_key(TODAY + timedelta(days=15))},
        ).json()
        landing = c.get(
            f"{BASE}/{seed['product'].id}/cell", params={"month": month_key(assumed)}
        ).json()

    line = _by_so(cell, "SO419208")
    assert line["status"] == "pinned"
    assert line["assigned_qty"] == 1309
    assert line["short_qty"] == 0
    entries = {entry["po_line_id"]: entry for entry in line["assigned_from"]}
    assert set(entries) == {str(seed["named"].id), str(seed["placed"].id)}
    assert entries[str(seed["named"].id)]["qty"] == 1305
    assert entries[str(seed["placed"].id)]["qty"] == 4
    for entry in entries.values():
        assert entry["kind"] == "po"
        assert entry["po_number"] == seed["po"].po_number
        assert entry["po_id"] == str(seed["po"].id)
    # The line's position in its document is `_po_rows`' own numbering (created_at, id);
    # rows made in one test transaction share `created_at`, so read it rather than guess.
    from app.services.project_supply_service import ProjectSupplyService

    numbers = {
        row.line_id: row.po_line_no
        for row in ProjectSupplyService(db).po_by_location(
            [str(seed["product"].id)], [str(seed["warehouse"].id)]
        )[(str(seed["product"].id), str(seed["warehouse"].id))]
    }
    for line_id, entry in entries.items():
        assert entry["po_line_number"] == numbers[line_id]
    assert entries[str(seed["placed"].id)]["oi_number"] is not None, (
        "the placement names the order inquiry it came through; the book S/O names none"
    )
    assert entries[str(seed["named"].id)]["oi_number"] is None

    other = _by_so(earlier, "SO-OTHER")
    assert other["assigned_qty"] == 41
    assert other["short_qty"] == 59, "the free 41 lands today, before it is due"
    assert [entry["po_line_id"] for entry in other["assigned_from"]] == [
        str(seed["free"].id)
    ]

    rows = {row["po_line_id"]: row for row in landing["supply"] if row["kind"] == "po"}
    assert set(rows) == {str(seed["free"].id), str(seed["named"].id), str(seed["placed"].id)}
    named = rows[str(seed["named"].id)]
    assert named["date"] == assumed.isoformat()
    assert named["stated_date"] == (TODAY - timedelta(days=14)).isoformat()
    assert named["days_late"] == 14
    assert named["overdue"] is False
    assert (named["qty"], named["received_qty"], named["outstanding_qty"]) == (1305, 0, 1305)
    assert named["free_qty"] == 0
    assert rows[str(seed["free"].id)]["days_late"] == 18


def test_at_the_shipped_0_0_a_late_po_naming_the_order_still_fulfils_it(scm_app):
    """AC-PO-6 as R43 (#1346) and R44 (#1359) amend it: 14 and 18 days late are past a
    dead line of 0, which the stock debt page no longer applies, so all three PO lines are
    listed in the CURRENT month, not overdue, and count as supply. SO419208 is pinned
    1,305 from the book and 4 from the placement, short nothing. The 41 with no S/O is
    free supply, so the earlier order (due today) takes it and is short 59."""
    app, db = _client(scm_app)
    seed = _csk14a(db, grace=0, dead=0)

    with TestClient(app) as c:
        cell = c.get(
            f"{BASE}/{seed['product'].id}/cell", params={"month": month_key(seed["due"])}
        ).json()
        today = c.get(
            f"{BASE}/{seed['product'].id}/cell", params={"month": month_key(TODAY)}
        ).json()

    line = _by_so(cell, "SO419208")
    assert line["status"] == "pinned"
    assert line["short_qty"] == 0
    assert line["assigned_qty"] == 1309
    assert sorted((entry["po_line_id"], entry["qty"]) for entry in line["assigned_from"]) == (
        sorted([(str(seed["placed"].id), 4), (str(seed["named"].id), 1305)])
    )

    other = _by_so(today, "SO-OTHER")
    assert other["status"] == "short"
    assert other["assigned_qty"] == 41
    assert other["short_qty"] == 59

    rows = [row for row in today["supply"] if row["kind"] == "po"]
    assert len(rows) == 3
    assert all(row["overdue"] is False and row["free_qty"] == 0 for row in rows)


def test_an_s_o_that_names_no_sales_order_held_here_leaves_the_po_free(scm_app):
    """AC-PO-4: "Linked, not held" pins nothing, so the whole line is free supply on its
    delivery date and the walk gives it first-come to whoever is due first."""
    app, db = _client(scm_app)
    _policy(db, 0, 0)
    marker = f"ZZTPO{_u()[:6]}".upper()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    product = _product(db, f"{marker}-A")
    delivery = _months_ahead(1)
    due = _months_ahead(2)
    _demand(db, product, warehouse, qty=30, required_date=due, so_number=f"{marker}-SO1")
    po = _purchase_order(db, f"{marker}-PO", issue_date=TODAY)
    _po_line(
        db, po, product, warehouse, qty=30, delivery=delivery,
        so_ref=f"ZZTBOOK:{marker}-missing:1",
    )
    db.flush()

    with TestClient(app) as c:
        cell = c.get(f"{BASE}/{product.id}/cell", params={"month": month_key(due)}).json()

    line = cell["demand"][0]
    assert line["status"] == "covered"
    assert line["assigned_qty"] == 30


def test_a_po_line_with_no_date_at_all_is_listed_uncounted_and_still_fulfils(scm_app):
    """AC-PO-2's second half, as R43 (#1346) amends it: no Delivery date and no issue date,
    so no date to park it on. It is listed in the current month and counts as nothing as
    supply, but its S/O pins the order "regardless of the PO's delivery date", so the line
    is pinned and short nothing, and its own month's Supply tab lists the PO."""
    app, db = _client(scm_app)
    _policy(db, 14, 90)
    marker = f"ZZTPO{_u()[:6]}".upper()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    product = _product(db, f"{marker}-A")
    due = _months_ahead(1)
    order, _line = _demand(
        db, product, warehouse, qty=30, required_date=due, so_number=f"{marker}-SO1"
    )
    order.source_ref = f"ZZTBOOK:{marker}"
    po = _purchase_order(db, f"{marker}-PO", issue_date=None)
    po_line = _po_line(
        db, po, product, warehouse, qty=30, delivery=None, so_ref=f"ZZTBOOK:{marker}:1"
    )
    db.flush()

    with TestClient(app) as c:
        cell = c.get(f"{BASE}/{product.id}/cell", params={"month": month_key(due)}).json()
        today = c.get(f"{BASE}/{product.id}/cell", params={"month": month_key(TODAY)}).json()

    assert cell["demand"][0]["status"] == "pinned"
    assert cell["demand"][0]["short_qty"] == 0
    assert [entry["po_line_id"] for entry in cell["demand"][0]["assigned_from"]] == [
        str(po_line.id)
    ]
    [pinned] = [row for row in cell["supply"] if row["kind"] == "po"]
    assert pinned["po_line_id"] == str(po_line.id)
    assert pinned["assigned_to"][0]["qty"] == 30
    [row] = [row for row in today["supply"] if row["kind"] == "po"]
    assert row["po_line_id"] == str(po_line.id)
    assert row["date"] is None
    assert row["free_qty"] == 0


def test_the_board_path_is_unchanged_and_differs_from_the_view_only_by_r42(scm_app):
    """AC-PO-8: one fixture, both paths. The board (`assignments_for`, the ladder's own
    read) keeps plan v7 R29 - the PO lands at `issue + lead` and its S/O pins nothing - and
    everything else it reads is the view's own answer event for event: the on hand, the
    SPO, the demand lines. The two differ in exactly the two things R42 changed."""
    app, db = _client(scm_app)
    _policy(db, 0, 0)
    marker = f"ZZTPO{_u()[:6]}".upper()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    product = _product(db, f"{marker}-A")
    _stock(db, product, warehouse, 20)
    _spo(db, product, warehouse, qty=30, arrives=TODAY + timedelta(days=10))
    _demand(
        db, product, warehouse, qty=40, required_date=TODAY + timedelta(days=30),
        so_number=f"{marker}-SOA",
    )
    order_b, _line_b = _demand(
        db, product, warehouse, qty=100, required_date=TODAY + timedelta(days=60),
        so_number=f"{marker}-SOB",
    )
    order_b.source_ref = f"ZZTBOOK:{marker}"
    po = _purchase_order(db, f"{marker}-PO", issue_date=TODAY)
    delivery = TODAY + timedelta(days=20)
    po_line = _po_line(
        db, po, product, warehouse, qty=100, delivery=delivery,
        so_ref=f"ZZTBOOK:{marker}:1",
    )
    db.flush()

    from app.services.project_supply_service import ProjectSupplyService
    from app.services.scm.stock_debt_service import StockDebtService

    arrival = ProjectSupplyService(db).po_by_location(
        [str(product.id)], [str(warehouse.id)]
    )[(str(product.id), str(warehouse.id))][0].arrival_date
    assert arrival != delivery, "the fixture must tell the two dates apart"

    span = {str(warehouse.id): warehouse}
    service = StockDebtService(db)
    board = service.assignments_for([str(product.id)], span)[str(product.id)]
    view = service._assignments(
        [(str(product.id), "", None)], span, view=True
    )[str(product.id)]

    def events(result):
        return {event.key: event for event in result.supply}

    board_events, view_events = events(board), events(view)
    assert set(board_events) == set(view_events)
    po_key = f"po:{po_line.id}"
    for key in board_events:
        if key == po_key:
            continue
        assert (board_events[key].at, board_events[key].qty) == (
            view_events[key].at, view_events[key].qty,
        )
    assert board_events[po_key].qty == view_events[po_key].qty == 100
    assert board_events[po_key].at == arrival
    assert board_events[po_key].bought_for == delivery
    assert view_events[po_key].at == delivery

    def pinned(result):
        return sorted(
            (row.line.so_number, item.event.key, item.qty)
            for row in result.lines
            for item in row.assigned
            if item.pinned
        )

    assert pinned(board) == []
    assert pinned(view) == [(f"{marker}-SOB", po_key, 100)]
    assert {row.line.key for row in board.lines} == {row.line.key for row in view.lines}
