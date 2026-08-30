"""The Stock Debt view over the wire (S2, AC-S2-6 / AC-S2-7 / AC-S2-8).

    GET /api/v1/project-sales/stock-debt
    GET /api/v1/project-sales/stock-debt/{product_id}/cell?month=

`test_supply_assignment.py` owns the arithmetic; nothing is re-derived here. What is proved
is what the WIRE has to carry, and every field is asserted BY NAME because a `response_model`
silently drops what it does not declare - a field the service computes and the schema forgets
reaches the screen as `undefined`, which reads as a backend that has no answer.

Every test narrows with `query=`, and not only for speed: the shared database is a prod copy
with a thousand products in fulfilment planning, so a test that read the whole book would
assert against somebody else's data. The seeded chain is the only thing in the answer.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.services.scm.supply_assignment import month_key
from tests.scm.conftest import (
    SORENTO_COMPANY_ID,
    as_user,
    ensure_reference_data,
    requires_pg,
    seed_user,
)

pytestmark = requires_pg

BASE = "/api/v1/project-sales/stock-debt"
VIEW = "projects.stock_debt.view"

TODAY = date.today()


def _u() -> str:
    return str(uuid.uuid4())


def _months_ahead(count: int) -> date:
    """The 15th, `count` months out - a date that cannot slip into a neighbouring month
    however late in the month the suite runs."""
    month = TODAY.month - 1 + count
    return date(TODAY.year + month // 12, month % 12 + 1, 15)


def _client(scm_app, *, permission: str | None = VIEW):
    app, db, gcu, gcuak = scm_app
    ensure_reference_data(db)
    uid = seed_user(db, None)
    if permission:
        role_id = _u()
        db.execute(
            text(
                "INSERT INTO user_roles (id, slug, name, is_trashed, is_protected, "
                "is_default, created_at) VALUES (:id, :slug, 'ZZT stock debt', false, "
                "false, false, now())"
            ),
            {"id": role_id, "slug": f"zzt-stock-debt-{role_id[:8]}"},
        )
        permission_id = db.execute(
            text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": permission}
        ).scalar()
        assert permission_id, f"{permission} must exist - migration 443 seeds it"
        db.execute(
            text(
                "INSERT INTO user_role_permissions (id, role_id, permission_id, "
                "assigned_at) VALUES (:id, :r, :p, now())"
            ),
            {"id": _u(), "r": role_id, "p": permission_id},
        )
        from app.models.user import UserRoleAssignment

        db.add(UserRoleAssignment(user_id=uid, role_id=role_id))
        db.flush()
    as_user(app, gcu, gcuak, uid)
    return app, db


# --------------------------------------------------------------------------- seeding


def _product(db, code: str):
    from app.models.product import Product

    category_id, uom_id = db.execute(
        text(
            "SELECT category_id, base_uom_id FROM products "
            "WHERE category_id IS NOT NULL AND base_uom_id IS NOT NULL LIMIT 1"
        )
    ).first()
    row = Product(
        id=_u(),
        product_code=code,
        product_name=f"{code} basin",
        category_id=category_id,
        base_uom_id=uom_id,
        list_price=Decimal("10.00"),
        company_id=SORENTO_COMPANY_ID,
    )
    db.add(row)
    db.flush()
    return row


def _warehouse(db, code: str, *, planning: bool = True):
    from app.models.inventory import Warehouse

    row = Warehouse(
        id=_u(),
        warehouse_code=code,
        warehouse_name=code,
        location="ZZT",
        is_active=True,
        fulfilment_planning=planning,
        company_id=SORENTO_COMPANY_ID,
    )
    db.add(row)
    db.flush()
    return row


def _stock(db, product, warehouse, qty):
    from app.models.inventory import Stock

    db.add(
        Stock(
            id=_u(),
            product_id=product.id,
            warehouse_id=warehouse.id,
            quantity_on_hand=Decimal(str(qty)),
            quantity_reserved=0,
            company_id=SORENTO_COMPANY_ID,
        )
    )
    db.flush()


def _agent(db, code: str):
    from app.models.sales_agent import SalesAgent

    row = SalesAgent(id=_u(), sales_agent=code, source="manual", is_active=True)
    db.add(row)
    db.flush()
    return row


def _demand(db, product, warehouse, *, qty, required_date, so_number, agent=None):
    from app.models.order import SalesOrder, SalesOrderLine

    order = SalesOrder(
        id=_u(),
        company_id=SORENTO_COMPANY_ID,
        so_number=so_number,
        status="open",
        demand_class="project",
        sales_agent_id=agent.id if agent is not None else None,
    )
    db.add(order)
    db.flush()
    line = SalesOrderLine(
        id=_u(),
        company_id=SORENTO_COMPANY_ID,
        sales_order_id=order.id,
        product_id=product.id,
        warehouse_id=warehouse.id,
        qty_ordered=Decimal(str(qty)),
        qty_delivered=Decimal("0"),
        required_date=required_date,
        line_status="open",
    )
    db.add(line)
    db.flush()
    return order, line


def _spo(db, product, warehouse, *, qty, arrives, spo_number=None):
    from app.models.procurement import SPOAllocation

    row = SPOAllocation(
        id=_u(),
        spo_number=spo_number or f"ZZT-SPO-{_u()[:6]}",
        spo_line_number=1,
        product_id=product.id,
        warehouse_id=warehouse.id,
        allocated_quantity=qty,
        quantity_received=0,
        receipt_status="pending",
        line_status="open",
        expected_date=arrives,
        company_id=SORENTO_COMPANY_ID,
    )
    db.add(row)
    db.flush()
    return row


def _row_of(body: dict, code: str) -> dict:
    rows = [row for row in body["data"] if row["product_code"] == code]
    assert rows, f"{code} is not in {[row['product_code'] for row in body['data']]}"
    return rows[0]


# --------------------------------------------------------------------------- AC-S2-6


def test_the_board_answers_one_row_per_product_with_the_whole_envelope(scm_app):
    """Every field of AC-S2-6, by name. The book: 100 on hand, 30 due next month (covered),
    200 due in three months (short 130 by then), 60 booked at 2030 and 12 with no date."""
    app, db = _client(scm_app)
    marker = f"ZZTSD{_u()[:6]}".upper()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    product = _product(db, f"{marker}-A")
    _stock(db, product, warehouse, 100)
    _demand(
        db, product, warehouse, qty=30, required_date=_months_ahead(1),
        so_number=f"{marker}-SO1",
    )
    _demand(
        db, product, warehouse, qty=200, required_date=_months_ahead(3),
        so_number=f"{marker}-SO2",
    )
    _demand(
        db, product, warehouse, qty=60, required_date=date(2030, 1, 1),
        so_number=f"{marker}-SO3",
    )
    _demand(
        db, product, warehouse, qty=12, required_date=None, so_number=f"{marker}-SO4",
    )
    db.flush()

    with TestClient(app) as c:
        got = c.get(BASE, params={"query": marker, "only_debt": False, "limit": 25})
    assert got.status_code == 200, got.text
    body = got.json()

    assert body["pagination"] == {"total": 1, "page": 1, "limit": 25}
    assert body["tba_month"] == "2029-01"
    assert "BB" in body["groups"]
    assert body["months"][0] == month_key(TODAY)
    assert body["months"][-1] == month_key(_months_ahead(3))

    row = _row_of(body, product.product_code)
    assert row["product_id"] == str(product.id)
    assert row["product_name"] == f"{product.product_code} basin"
    assert row["tba"] == -60
    assert row["undated"] == -12
    assert [month["key"] for month in row["months"]] == body["months"]
    balances = {month["key"]: month["balance"] for month in row["months"]}
    # R37, month by month: the 100 on hand is spent (30 to the near line, 70 to the far
    # one), so nothing is FREE in this month or the next, and the only month that owes
    # anything is the one the short line is due in.
    assert balances[month_key(TODAY)] == 0
    assert balances[month_key(_months_ahead(1))] == 0
    assert balances[month_key(_months_ahead(3))] == -130
    tones = {month["key"]: month["tone"] for month in row["months"]}
    assert tones[month_key(TODAY)] == "green"
    assert tones[month_key(_months_ahead(3))] in {"red", "amber"}


def test_only_debt_drops_the_product_that_covers_everything(scm_app):
    app, db = _client(scm_app)
    marker = f"ZZTSD{_u()[:6]}".upper()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    covered = _product(db, f"{marker}-COVERED")
    short = _product(db, f"{marker}-SHORT")
    _stock(db, covered, warehouse, 500)
    _stock(db, short, warehouse, 5)
    for product in (covered, short):
        _demand(
            db, product, warehouse, qty=100, required_date=_months_ahead(2),
            so_number=f"{marker}-{product.product_code}",
        )
    db.flush()

    with TestClient(app) as c:
        every = c.get(BASE, params={"query": marker, "only_debt": False}).json()
        debt = c.get(BASE, params={"query": marker, "only_debt": True}).json()

    assert sorted(row["product_code"] for row in every["data"]) == [
        covered.product_code,
        short.product_code,
    ]
    assert [row["product_code"] for row in debt["data"]] == [short.product_code]
    assert debt["pagination"]["total"] == 1


def test_the_group_filter_recomputes_rather_than_filters(scm_app):
    """`group=BB` narrows the SPAN of every read, so the balance is the BB group's own -
    and that is what makes the narrowing meaningful rather than cosmetic.

    On the WHOLE book the IB stock is IB's, and R40 says an undecided BB line does not take
    it, so the BB line is short its 40 in its own month while IB's 100 reads free in the
    month it sits in. Under `group=BB` the IB bin is not in the span at all, so there is no
    100 to be free of and the current month reads 0. Same rows, two different questions -
    which is precisely what "recomputes" means; filtering finished rows would have shown
    one answer under both.
    """
    app, db = _client(scm_app)
    marker = f"ZZTSD{_u()[:6]}".upper()
    bb = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    ib = _warehouse(db, f"ZZTBRW{_u()[:4]}-IB")
    product = _product(db, f"{marker}-A")
    _stock(db, product, ib, 100)
    _demand(
        db, product, bb, qty=40, required_date=_months_ahead(1),
        so_number=f"{marker}-SO1",
    )
    db.flush()
    due = month_key(_months_ahead(1))

    with TestClient(app) as c:
        whole = c.get(BASE, params={"query": marker, "only_debt": False}).json()
        narrowed = c.get(
            BASE, params={"query": marker, "group": "BB", "only_debt": False}
        ).json()
        whole_cell = c.get(
            f"{BASE}/{product.id}/cell", params={"month": due}
        ).json()
        narrowed_cell = c.get(
            f"{BASE}/{product.id}/cell", params={"month": due, "group": "BB"}
        ).json()

    def balance(body, key):
        row = _row_of(body, product.product_code)
        return {month["key"]: month["balance"] for month in row["months"]}[key]

    # R37 + R40: on the whole book the whole 100 of IB's on hand stays free (a BB line may
    # not take it) and the BB line owes 40 in its own month. Narrowed to BB the IB bin is
    # out of the span entirely, so the current month has nothing to be free of at all -
    # which is the difference that proves the narrowing RECOMPUTES.
    assert balance(whole, month_key(TODAY)) == 100
    assert balance(whole, due) == -40
    assert balance(narrowed, month_key(TODAY)) == 0
    assert balance(narrowed, due) == -40

    # The reason the cell route takes `group` at all: the drill has to foot with the cell
    # that opened it, and it does under both spans. The SUPPLY half is where the two differ
    # - the whole book lists IB's 100 as free, the narrowed one lists nothing.
    assert whole_cell["demand"][0]["status"] == "short"
    assert whole_cell["demand"][0]["short_qty"] == 40
    assert narrowed_cell["demand"][0]["status"] == "short"
    assert narrowed_cell["demand"][0]["assigned_qty"] == 0


def test_rows_are_sorted_by_the_earliest_red_month_then_product_code(scm_app):
    """AC-S2-6. A product that cannot be bought in time comes first; a product with no red
    month at all sorts after every product that has one, whatever its code."""
    app, db = _client(scm_app)
    marker = f"ZZTSD{_u()[:6]}".upper()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    # Codes chosen so alphabetical order and the required order disagree.
    late_debt = _product(db, f"{marker}-A-LATE")
    near_debt = _product(db, f"{marker}-B-NEAR")
    _demand(
        db, near_debt, warehouse, qty=10, required_date=TODAY + timedelta(days=3),
        so_number=f"{marker}-SO-NEAR",
    )
    _demand(
        db, late_debt, warehouse, qty=10, required_date=_months_ahead(14),
        so_number=f"{marker}-SO-LATE",
    )
    db.flush()

    with TestClient(app) as c:
        body = c.get(BASE, params={"query": marker, "only_debt": True}).json()

    assert [row["product_code"] for row in body["data"]] == [
        near_debt.product_code,
        late_debt.product_code,
    ]


def test_paging_returns_the_next_slice_on_the_same_axis(scm_app):
    """The envelope's axis and total are properties of the whole filtered set, not of a
    page - so a reader turning the page sees the columns hold still while the rows move."""
    app, db = _client(scm_app)
    marker = f"ZZTSD{_u()[:6]}".upper()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    codes = [f"{marker}-A", f"{marker}-B", f"{marker}-C"]
    for code in codes:
        product = _product(db, code)
        _demand(
            db, product, warehouse, qty=10, required_date=TODAY,
            so_number=f"{marker}-SO-{code[-1]}",
        )
    db.flush()

    with TestClient(app) as c:
        page1 = c.get(BASE, params={"query": marker, "page": 1, "limit": 1}).json()
        page2 = c.get(BASE, params={"query": marker, "page": 2, "limit": 1}).json()

    assert page1["pagination"] == {"total": 3, "page": 1, "limit": 1}
    assert page2["pagination"] == {"total": 3, "page": 2, "limit": 1}
    assert page1["months"] == page2["months"]
    assert len(page1["data"]) == 1 and len(page2["data"]) == 1
    got = [page1["data"][0]["product_code"], page2["data"][0]["product_code"]]
    assert got == codes[:2]


def test_pool_stock_never_covers_a_project_group_line(scm_app):
    """Plan 3.1 / R2: a site pool is reached through `pool_warehouse_id`, is nobody's
    ownership group, and (AC-S1-1) is seeded OUTSIDE fulfilment planning - so a pool
    holding plenty must not silently make a flagged-bin line read covered. The pool's
    stock is not merely a separate group here, it is out of this read's span entirely
    (`_warehouses` filters `fulfilment_planning_predicate()`, which excludes pools by
    construction), which is the strongest form of "never leaks into a project line"."""
    app, db = _client(scm_app)
    marker = f"ZZTSD{_u()[:6]}".upper()
    from app.models.inventory import Warehouse

    pool = Warehouse(
        id=_u(),
        warehouse_code=f"ZZTPOOL{_u()[:6]}",
        warehouse_name="ZZT pool",
        location="ZZT",
        is_active=True,
        fulfilment_planning=False,
        company_id=SORENTO_COMPANY_ID,
    )
    db.add(pool)
    db.flush()
    bb = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    bb.pool_warehouse_id = pool.id
    db.flush()
    product = _product(db, f"{marker}-A")
    _stock(db, product, pool, 500)
    _demand(
        db, product, bb, qty=40, required_date=_months_ahead(1),
        so_number=f"{marker}-SO1",
    )
    db.flush()

    with TestClient(app) as c:
        body = c.get(BASE, params={"query": marker, "only_debt": False}).json()

    row = _row_of(body, product.product_code)
    balances = {m["key"]: m["balance"] for m in row["months"]}
    # The pool's 500 never reaches this read: the BB line is short its whole 40, exactly
    # as if the pool did not exist.
    assert balances[month_key(_months_ahead(1))] == -40


def test_only_debt_keeps_a_tba_only_row_and_drops_a_fully_covered_one(scm_app):
    """`_in_debt`: a product whose every MONTH is covered but whose TBA bucket is
    negative still owes something (AC-S2-3 counts a TBA line's whole quantity as debt), so
    it must not disappear from the one screen that lists what is owed; a product with
    nothing negative anywhere drops, as the sibling test already pins for the short case."""
    app, db = _client(scm_app)
    marker = f"ZZTSD{_u()[:6]}".upper()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    tba_only = _product(db, f"{marker}-TBAONLY")
    fully_covered = _product(db, f"{marker}-COVERED")
    _stock(db, tba_only, warehouse, 100)
    _demand(
        db, tba_only, warehouse, qty=20, required_date=_months_ahead(1),
        so_number=f"{marker}-SO1",
    )
    _demand(
        db, tba_only, warehouse, qty=30, required_date=date(2030, 1, 1),
        so_number=f"{marker}-TBA",
    )
    _stock(db, fully_covered, warehouse, 100)
    _demand(
        db, fully_covered, warehouse, qty=20, required_date=_months_ahead(1),
        so_number=f"{marker}-SO2",
    )
    db.flush()

    with TestClient(app) as c:
        debt = c.get(BASE, params={"query": marker, "only_debt": True}).json()

    codes = [row["product_code"] for row in debt["data"]]
    assert tba_only.product_code in codes
    assert fully_covered.product_code not in codes
    row = _row_of(debt, tba_only.product_code)
    assert all(m["balance"] >= 0 for m in row["months"])
    assert row["tba"] == -30


def test_a_bin_outside_fulfilment_planning_is_not_on_the_board(scm_app):
    """R17: the flag is the whole test - the product's stock and its order are both at a bin
    nobody plans against, so there is no row at all."""
    app, db = _client(scm_app)
    marker = f"ZZTSD{_u()[:6]}".upper()
    outside = _warehouse(db, f"ZZTBRW{_u()[:4]}-HP", planning=False)
    product = _product(db, f"{marker}-A")
    _stock(db, product, outside, 10)
    _demand(
        db, product, outside, qty=90, required_date=_months_ahead(1),
        so_number=f"{marker}-SO1",
    )
    db.flush()

    with TestClient(app) as c:
        body = c.get(BASE, params={"query": marker, "only_debt": False}).json()

    assert body["data"] == []
    assert body["pagination"]["total"] == 0


# --------------------------------------------------------------------------- AC-S2-2 / R21


def _project_line_for(db, core_line):
    """A minimal Project SO + line over an existing core SO line - `project_id=None`
    (the ADOPTED shape the model documents), so this stays a two-table chain rather than
    dragging in `register_project` / `project_seed_service` for a hold-plumbing test."""
    from app.models.project_so import (
        SO_STATUS_PUBLISHED,
        ProjectSalesOrder,
        ProjectSalesOrderLine,
    )

    order = ProjectSalesOrder(
        id=_u(),
        company_id=SORENTO_COMPANY_ID,
        project_id=None,
        provisional_ref=f"ZZTPSO-{_u()[:8]}",
        area_group="ZZT",
        status=SO_STATUS_PUBLISHED,
        so_id=core_line.sales_order_id,
    )
    db.add(order)
    db.flush()
    line = ProjectSalesOrderLine(
        id=_u(),
        company_id=SORENTO_COMPANY_ID,
        project_sales_order_id=order.id,
        core_sales_order_line_id=core_line.id,
        line_no=1,
        product_id=core_line.product_id,
        description="ZZT hold line",
        qty=core_line.qty_ordered,
        uom="SET",
        unit_price=Decimal("10.00"),
        amount=Decimal("0"),
        delivery_date=core_line.required_date,
    )
    db.add(line)
    db.flush()
    return order, line


def _po_line_for_hold(db, product, warehouse, *, qty, issue_date):
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine

    po = PurchaseOrder(
        id=_u(),
        po_number=f"ZZTPO{_u()[:6]}".upper(),
        issue_date=issue_date,
        status="active",
        company_id=SORENTO_COMPANY_ID,
    )
    db.add(po)
    db.flush()
    line = PurchaseOrderLine(
        id=_u(),
        purchase_order_id=po.id,
        product_id=product.id,
        warehouse_id=warehouse.id,
        qty_ordered=Decimal(str(qty)),
        qty_received=Decimal("0"),
        line_status="open",
        company_id=SORENTO_COMPANY_ID,
    )
    db.add(line)
    db.flush()
    return po, line


def _order_back_link_on_po(db, project_order, so_line, *, po_line, qty):
    """An ORDER_BACK-verb inquiry row linked to a PO line - `order_inquiry_links.po_line_id`
    - the one shape `_holds()` reads besides a confirmed allocation."""
    from app.models.project_so import (
        IV_ORDER_BACK,
        OrderInquiry,
        OrderInquiryLink,
        OrderInquiryRow,
    )

    inquiry = OrderInquiry(
        id=_u(), company_id=SORENTO_COMPANY_ID, project_sales_order_id=project_order.id,
    )
    db.add(inquiry)
    db.flush()
    row = OrderInquiryRow(
        id=_u(),
        company_id=SORENTO_COMPANY_ID,
        order_inquiry_id=inquiry.id,
        so_line_id=so_line.id,
        qty=Decimal(str(qty)),
        verb=IV_ORDER_BACK,
    )
    db.add(row)
    db.flush()
    link = OrderInquiryLink(
        id=_u(),
        company_id=SORENTO_COMPANY_ID,
        row_id=row.id,
        po_line_id=po_line.id,
        qty=Decimal(str(qty)),
    )
    db.add(link)
    db.flush()
    return row, link


def test_a_po_line_hold_pins_the_quantity_to_the_askers_line(scm_app):
    """R21/AC-S2-2 through `order_inquiry_links.po_line_id`: a placement link binds the
    PO's quantity to the line it was made for, whatever first-come-by-date would otherwise
    give it. The PO is made to arrive well AFTER the line's own required date - without the
    pin the line would read `short` or `late`, never `pinned` - and the supply row's
    `assigned_to` names the asking SO in the PO's own arrival month."""
    app, db = _client(scm_app)
    marker = f"ZZTSD{_u()[:6]}".upper()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    product = _product(db, f"{marker}-A")
    due = _months_ahead(1)
    order, core_line = _demand(
        db, product, warehouse, qty=50, required_date=due, so_number=f"{marker}-SO1",
    )
    project_order, project_line = _project_line_for(db, core_line)
    po, po_line = _po_line_for_hold(db, product, warehouse, qty=50, issue_date=TODAY)
    _order_back_link_on_po(db, project_order, project_line, po_line=po_line, qty=50)
    db.flush()

    from app.services.project_supply_service import ProjectSupplyService

    po_rows = ProjectSupplyService(db).po_by_location(
        [str(product.id)], [str(warehouse.id)]
    )
    arrival = po_rows[(str(product.id), str(warehouse.id))][0].arrival_date
    assert arrival > due, "the PO must arrive after the line's own date, or the pin is untested"

    with TestClient(app) as c:
        cell = c.get(f"{BASE}/{product.id}/cell", params={"month": month_key(due)}).json()
        supply_cell = c.get(
            f"{BASE}/{product.id}/cell", params={"month": month_key(arrival)}
        ).json()

    assert len(cell["demand"]) == 1
    demand_line = cell["demand"][0]
    assert demand_line["so_number"] == f"{marker}-SO1"
    assert demand_line["status"] == "pinned"
    assert demand_line["assigned_qty"] == 50

    po_events = [event for event in supply_cell["supply"] if event["kind"] == "po"]
    assert len(po_events) == 1
    assert po_events[0]["assigned_to"] == [{"so_number": f"{marker}-SO1", "qty": 50}]


# --------------------------------------------------------------------------- AC-S2-7


def test_the_cell_lists_the_demand_with_its_bin_and_the_supply_with_its_assignment(
    scm_app,
):
    app, db = _client(scm_app)
    marker = f"ZZTSD{_u()[:6]}".upper()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    product = _product(db, f"{marker}-A")
    agent = _agent(db, f"ZZT{_u()[:4]}".upper())
    _stock(db, product, warehouse, 40)
    due = _months_ahead(1)
    _demand(
        db, product, warehouse, qty=100, required_date=due,
        so_number=f"{marker}-SO1", agent=agent,
    )
    _spo(db, product, warehouse, qty=60, arrives=_months_ahead(2))
    db.flush()

    with TestClient(app) as c:
        got = c.get(
            f"{BASE}/{product.id}/cell", params={"month": month_key(due)}
        )
    assert got.status_code == 200, got.text
    body = got.json()

    assert len(body["demand"]) == 1
    line = body["demand"][0]
    assert line["so_number"] == f"{marker}-SO1"
    assert line["agent_code"] == agent.sales_agent
    assert line["warehouse_code"] == warehouse.warehouse_code
    assert line["required_date"] == due.isoformat()
    assert line["open_qty"] == 100
    # 40 on hand at its date, the other 60 off an SPO that lands a month after it: whole,
    # and late. Short would outrank late if anything were left over (`supply_assignment`).
    assert line["assigned_qty"] == 100
    assert line["status"] == "late"
    assert warehouse.warehouse_code in line["assigned_source"]

    # The on hand sits in the CURRENT month, so this month's supply is the SPO only.
    current = c_get_supply(app, product, month_key(TODAY))
    assert [event["kind"] for event in current] == ["on_hand"]
    assert current[0]["warehouse_code"] == warehouse.warehouse_code
    assert current[0]["qty"] == 40
    assert current[0]["ref"] is None
    # By NAME, because `StockDebtSupplyEvent.date` is the field a `from __future__ import
    # annotations` module very nearly could not declare (see the schema's own note), and a
    # `response_model` drops silently what it fails to declare.
    assert current[0]["date"] == TODAY.isoformat()
    assert current[0]["bought_for"] is None
    assert current[0]["overdue"] is False
    assert current[0]["assigned_to"] == [{"so_number": f"{marker}-SO1", "qty": 40}]


def c_get_supply(app, product, month) -> list:
    with TestClient(app) as c:
        return c.get(f"{BASE}/{product.id}/cell", params={"month": month}).json()[
            "supply"
        ]


def test_an_overdue_document_is_listed_and_counted_as_nothing(scm_app):
    """AC-S2-4b / R31, on the wire: the arrival has passed with nothing received, so the
    line is short and the document is still in the drill with `overdue: true`."""
    app, db = _client(scm_app)
    marker = f"ZZTSD{_u()[:6]}".upper()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    product = _product(db, f"{marker}-A")
    _spo(db, product, warehouse, qty=50, arrives=TODAY - timedelta(days=20))
    due = _months_ahead(1)
    _demand(
        db, product, warehouse, qty=50, required_date=due, so_number=f"{marker}-SO1"
    )
    db.flush()

    with TestClient(app) as c:
        overdue = c.get(
            f"{BASE}/{product.id}/cell", params={"month": month_key(TODAY)}
        ).json()
        cell = c.get(
            f"{BASE}/{product.id}/cell", params={"month": month_key(due)}
        ).json()

    assert [event["overdue"] for event in overdue["supply"]] == [True]
    assert overdue["supply"][0]["qty"] == 50
    assert cell["demand"][0]["status"] == "short"
    assert cell["demand"][0]["assigned_qty"] == 0


def test_the_cell_answers_the_tba_and_the_undated_bucket(scm_app):
    """Both keys are addressable and both draw nothing (R14): the lines are listed with
    their whole quantity open and no supply beside them."""
    app, db = _client(scm_app)
    marker = f"ZZTSD{_u()[:6]}".upper()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    product = _product(db, f"{marker}-A")
    _stock(db, product, warehouse, 500)
    _demand(
        db, product, warehouse, qty=60, required_date=date(2030, 1, 1),
        so_number=f"{marker}-TBA",
    )
    _demand(
        db, product, warehouse, qty=12, required_date=None, so_number=f"{marker}-NODATE"
    )
    db.flush()

    with TestClient(app) as c:
        tba = c.get(f"{BASE}/{product.id}/cell", params={"month": "tba"}).json()
        undated = c.get(f"{BASE}/{product.id}/cell", params={"month": "undated"}).json()

    assert [line["so_number"] for line in tba["demand"]] == [f"{marker}-TBA"]
    assert tba["demand"][0]["assigned_qty"] == 0
    assert tba["demand"][0]["status"] == "short"
    assert tba["supply"] == []
    assert [line["so_number"] for line in undated["demand"]] == [f"{marker}-NODATE"]
    assert undated["demand"][0]["required_date"] is None
    assert undated["supply"] == []


def test_an_unknown_month_key_is_refused(scm_app):
    app, db = _client(scm_app)
    product = _product(db, f"ZZTSD{_u()[:6]}".upper())
    db.flush()
    with TestClient(app) as c:
        assert c.get(f"{BASE}/{product.id}/cell", params={"month": "soon"}).status_code == 422


# --------------------------------------------------------------------------- AC-S2-8


def test_both_routes_need_the_stock_debt_permission(scm_app):
    app, db = _client(scm_app, permission=None)
    product_id = _u()
    with TestClient(app) as c:
        assert c.get(BASE).status_code == 403
        assert (
            c.get(f"{BASE}/{product_id}/cell", params={"month": "tba"}).status_code
            == 403
        )


def test_a_role_holding_projects_view_reaches_stock_debt_through_the_443_sweep(scm_app):
    """AC-S2-8: migration 443's sweep gives `projects.stock_debt.view` to every role that
    already holds `projects.projects.view`. This runs the SWEEP'S OWN SQL (copied from
    `443_fulfilment_planning_flag_tba_date.py`, not a hand-rolled duplicate grant) against
    a role holding only the source permission, so a 200 here proves the sweep - not a test
    fixture standing in for it."""
    app, db, gcu, gcuak = scm_app
    ensure_reference_data(db)
    uid = seed_user(db, None)
    role_id = _u()
    db.execute(
        text(
            "INSERT INTO user_roles (id, slug, name, is_trashed, is_protected, "
            "is_default, created_at) VALUES (:id, :slug, 'ZZT projects view only', "
            "false, false, false, now())"
        ),
        {"id": role_id, "slug": f"zzt-projects-view-{role_id[:8]}"},
    )
    source_id = db.execute(
        text("SELECT id FROM user_permissions WHERE slug = 'projects.projects.view'")
    ).scalar()
    assert source_id, "projects.projects.view must exist"
    db.execute(
        text(
            "INSERT INTO user_role_permissions (id, role_id, permission_id, "
            "assigned_at) VALUES (:id, :r, :p, now())"
        ),
        {"id": _u(), "r": role_id, "p": source_id},
    )
    target_id = db.execute(
        text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": VIEW}
    ).scalar()
    assert target_id, f"{VIEW} must exist - migration 443 seeds it"

    # Migration 443's own sweep SQL, scoped to this one role.
    db.execute(
        text(
            """
            INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
            SELECT gen_random_uuid()::text, rp.role_id, :target, now()
            FROM user_role_permissions rp
            JOIN user_permissions src
              ON src.id = rp.permission_id AND src.slug = :source
            WHERE rp.role_id = :role
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        ),
        {"target": target_id, "source": "projects.projects.view", "role": role_id},
    )
    from app.models.user import UserRoleAssignment

    db.add(UserRoleAssignment(user_id=uid, role_id=role_id))
    db.flush()
    as_user(app, gcu, gcuak, uid)

    with TestClient(app) as c:
        got = c.get(BASE, params={"query": f"ZZTNOPE{_u()[:6]}".upper()})
    assert got.status_code == 200, got.text


# --------------------------------------------------------------------------- AC-S2-1b:
# a confirmed hold outranks the span it was read in


def _confirmed_hold(db, project_line, warehouse, qty):
    """A CONFIRMED `so_line_allocations` row - the shape `_hold_query` recognises: located,
    not an ORDER source, belonging to no decision, and confirmed."""
    from datetime import datetime

    from app.models.project_so import ALLOC_SOURCE_GROUP_TAKE, SOLineAllocation

    row = SOLineAllocation(
        id=_u(),
        company_id=SORENTO_COMPANY_ID,
        so_line_id=project_line.id,
        source_type=ALLOC_SOURCE_GROUP_TAKE,
        warehouse_id=warehouse.id,
        qty=Decimal(str(qty)),
        confirmed_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    return row


def test_a_hold_at_a_pool_or_an_unflagged_bin_still_reads_pinned(scm_app):
    """AC-S2-1b / R21: pinned means pinned.

    Both holds name a bin this read cannot see - a SITE POOL and a bin flagged out of
    fulfilment planning - so the supply event behind them is not in the span. Before this
    the hold was skipped and the board-covered line printed `short`: 16 pool holds (163
    units) and ~103 units at unflagged bins on the 30 Aug dev copy. The drill names the bin
    the HOLD carries, so the source column is a place rather than a blank.
    """
    app, db = _client(scm_app)
    marker = f"ZZTSD{_u()[:6]}".upper()
    bb = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    pool = _warehouse(db, f"ZZTPOOL{_u()[:5]}", planning=False)
    unflagged = _warehouse(db, f"ZZTBRW{_u()[:4]}-HP", planning=False)
    product = _product(db, f"{marker}-A")
    _stock(db, product, pool, 500)
    _stock(db, product, unflagged, 500)
    due = _months_ahead(1)
    _order_a, line_a = _demand(
        db, product, bb, qty=40, required_date=due, so_number=f"{marker}-SO-POOL"
    )
    _order_b, line_b = _demand(
        db, product, bb, qty=30, required_date=due, so_number=f"{marker}-SO-HP"
    )
    _pso_a, pline_a = _project_line_for(db, line_a)
    _pso_b, pline_b = _project_line_for(db, line_b)
    _confirmed_hold(db, pline_a, pool, 40)
    _confirmed_hold(db, pline_b, unflagged, 30)
    db.flush()

    with TestClient(app) as c:
        cell = c.get(
            f"{BASE}/{product.id}/cell", params={"month": month_key(due)}
        ).json()
        board = c.get(BASE, params={"query": marker, "only_debt": False}).json()

    by_so = {line["so_number"]: line for line in cell["demand"]}
    assert by_so[f"{marker}-SO-POOL"]["status"] == "pinned"
    assert by_so[f"{marker}-SO-POOL"]["assigned_qty"] == 40
    assert by_so[f"{marker}-SO-POOL"]["assigned_source"] == (
        f"On hand {pool.warehouse_code}"
    )
    assert by_so[f"{marker}-SO-HP"]["status"] == "pinned"
    assert by_so[f"{marker}-SO-HP"]["assigned_source"] == (
        f"On hand {unflagged.warehouse_code}"
    )
    # And the month agrees with the drill: 70 pinned against 70 owed owes nothing.
    row = _row_of(board, product.product_code)
    assert {m["key"]: m["balance"] for m in row["months"]}[month_key(due)] == 0


def test_a_donor_holds_stock_in_another_group_and_group_bb_still_reads_it_pinned(scm_app):
    """The third way a hold's bin leaves the span: the READER narrowed it.

    A DC1-IB donor holds 25 for a BB line. Under `group=BB` the IB bin is out of the span
    entirely - and the hold is still honoured, because narrowing the question does not
    unmake a promise (AC-S2-1b).
    """
    app, db = _client(scm_app)
    marker = f"ZZTSD{_u()[:6]}".upper()
    bb = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    ib = _warehouse(db, f"ZZTDC1{_u()[:4]}-IB")
    product = _product(db, f"{marker}-A")
    _stock(db, product, ib, 25)
    due = _months_ahead(1)
    _order, core_line = _demand(
        db, product, bb, qty=25, required_date=due, so_number=f"{marker}-SO1"
    )
    _pso, project_line = _project_line_for(db, core_line)
    _confirmed_hold(db, project_line, ib, 25)
    db.flush()

    with TestClient(app) as c:
        cell = c.get(
            f"{BASE}/{product.id}/cell",
            params={"month": month_key(due), "group": "BB"},
        ).json()

    assert cell["demand"][0]["status"] == "pinned"
    assert cell["demand"][0]["assigned_qty"] == 25
    assert cell["demand"][0]["assigned_source"] == f"On hand {ib.warehouse_code}"


def test_an_allocation_that_was_never_confirmed_holds_nothing(scm_app):
    """`_hold_query`'s own predicate, which the hand-written copy had lost: a hold counts
    when it is CONFIRMED. A decision saved and not confirmed held stock on this screen and
    on no other, so the board and the view disagreed about what was free."""
    app, db = _client(scm_app)
    marker = f"ZZTSD{_u()[:6]}".upper()
    bb = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    product = _product(db, f"{marker}-A")
    _stock(db, product, bb, 100)
    due = _months_ahead(1)
    _order, core_line = _demand(
        db, product, bb, qty=40, required_date=due, so_number=f"{marker}-SO1"
    )
    _pso, project_line = _project_line_for(db, core_line)
    hold = _confirmed_hold(db, project_line, bb, 40)
    hold.confirmed_at = None
    db.flush()

    with TestClient(app) as c:
        cell = c.get(
            f"{BASE}/{product.id}/cell", params={"month": month_key(due)}
        ).json()

    # Not `pinned`: it drew from the pile first-come like anybody else.
    assert cell["demand"][0]["status"] == "covered"


def test_a_cancelled_inquiry_row_pins_nothing(scm_app):
    """The filter every other consumer of `order_inquiry_links` applies. A withdrawn
    placement is not a promise, and pinning off it held a document to a line nobody is
    waiting on."""
    app, db = _client(scm_app)
    from app.models.project_so import INQUIRY_CANCELLED

    marker = f"ZZTSD{_u()[:6]}".upper()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    product = _product(db, f"{marker}-A")
    due = _months_ahead(1)
    _order, core_line = _demand(
        db, product, warehouse, qty=50, required_date=due, so_number=f"{marker}-SO1"
    )
    project_order, project_line = _project_line_for(db, core_line)
    _po, po_line = _po_line_for_hold(db, product, warehouse, qty=50, issue_date=TODAY)
    row, _link = _order_back_link_on_po(
        db, project_order, project_line, po_line=po_line, qty=50
    )
    row.state = INQUIRY_CANCELLED
    db.flush()

    with TestClient(app) as c:
        cell = c.get(
            f"{BASE}/{product.id}/cell", params={"month": month_key(due)}
        ).json()

    assert cell["demand"][0]["status"] != "pinned"


def test_reserved_stock_is_not_offered_as_free_supply(scm_app):
    """`_free_stock`'s own arithmetic: on hand MINUS reserved. Reserved stock is spoken for
    by a picking already under way, and offering it to a sales-order line here promised the
    same units twice."""
    app, db = _client(scm_app)
    from app.models.inventory import Stock

    marker = f"ZZTSD{_u()[:6]}".upper()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    product = _product(db, f"{marker}-A")
    db.add(
        Stock(
            id=_u(),
            product_id=product.id,
            warehouse_id=warehouse.id,
            quantity_on_hand=Decimal("100"),
            quantity_reserved=Decimal("70"),
            company_id=SORENTO_COMPANY_ID,
        )
    )
    _demand(
        db, product, warehouse, qty=50, required_date=_months_ahead(1),
        so_number=f"{marker}-SO1",
    )
    db.flush()

    with TestClient(app) as c:
        board = c.get(BASE, params={"query": marker, "only_debt": False}).json()

    row = _row_of(board, product.product_code)
    balances = {m["key"]: m["balance"] for m in row["months"]}
    # The 30 that is free of the reserve is taken by the line next month, so no month has
    # it spare (R37); the line goes without 20 on its own date.
    assert balances[month_key(TODAY)] == 0
    assert balances[month_key(_months_ahead(1))] == -20


def test_a_zero_day_lead_time_is_read_as_zero_not_as_the_default(scm_app):
    """`leads.get(...) or DEFAULT` turned a stated 0-day lead into 90 days, so a product a
    supplier ships off the shelf painted three months red. `is None` is the test - the same
    one `_po_rows` and `reserve_window_end` make."""
    app, db = _client(scm_app)
    from app.models.procurement import ProductSupplier, Supplier

    marker = f"ZZTSD{_u()[:6]}".upper()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    product = _product(db, f"{marker}-A")
    supplier = Supplier(
        id=_u(),
        supplier_code=f"ZZTSUP{_u()[:5]}".upper(),
        supplier_name="ZZT supplier",
        is_active=True,
        company_id=SORENTO_COMPANY_ID,
    )
    db.add(supplier)
    db.flush()
    db.add(
        ProductSupplier(
            id=_u(),
            product_id=product.id,
            supplier_id=supplier.id,
            standard_lead_time_days=0,
            company_id=SORENTO_COMPANY_ID,
        )
    )
    # Two months out: inside a 90-day horizon (red), outside a 0-day one (amber).
    _demand(
        db, product, warehouse, qty=20, required_date=_months_ahead(2),
        so_number=f"{marker}-SO1",
    )
    db.flush()

    with TestClient(app) as c:
        board = c.get(BASE, params={"query": marker, "only_debt": False}).json()

    row = _row_of(board, product.product_code)
    tones = {m["key"]: m["tone"] for m in row["months"]}
    assert tones[month_key(_months_ahead(2))] == "amber"


# --------------------------------------------------------------------------- unlocated


def test_unlocated_lines_are_counted_on_the_row_and_drillable(scm_app):
    """2,312 open lines on the 30 Aug dev copy name no warehouse. They are in no group's
    pile, so they draw nothing - but a screen that lists what is owed and silently omits
    them is answering a narrower question than the one it was asked. Counted in their own
    untoned total, beside TBA and No date, and addressable as a cell like any other."""
    app, db = _client(scm_app)
    marker = f"ZZTSD{_u()[:6]}".upper()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    product = _product(db, f"{marker}-A")
    _stock(db, product, warehouse, 500)
    _order, line = _demand(
        db, product, warehouse, qty=15, required_date=_months_ahead(1),
        so_number=f"{marker}-NOWHERE",
    )
    line.warehouse_id = None
    db.flush()

    with TestClient(app) as c:
        board = c.get(BASE, params={"query": marker, "only_debt": False}).json()
        cell = c.get(
            f"{BASE}/{product.id}/cell", params={"month": "unlocated"}
        ).json()

    row = _row_of(board, product.product_code)
    assert row["unlocated"] == -15
    # It never touched the 500 on hand, and it is in no month.
    assert all(m["balance"] == 500 for m in row["months"])
    assert [entry["so_number"] for entry in cell["demand"]] == [f"{marker}-NOWHERE"]
    assert cell["demand"][0]["warehouse_code"] is None
    assert cell["demand"][0]["assigned_qty"] == 0
    assert cell["supply"] == []


def test_a_product_whose_only_demand_is_unlocated_still_gets_a_row(scm_app):
    """The candidate read reaches unlocated demand too, or the product would have no row at
    all and the count would have nowhere to be stated."""
    app, db = _client(scm_app)
    marker = f"ZZTSD{_u()[:6]}".upper()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    product = _product(db, f"{marker}-A")
    _order, line = _demand(
        db, product, warehouse, qty=8, required_date=_months_ahead(1),
        so_number=f"{marker}-ONLY",
    )
    line.warehouse_id = None
    db.flush()

    with TestClient(app) as c:
        board = c.get(BASE, params={"query": marker, "only_debt": True}).json()

    row = _row_of(board, product.product_code)
    assert row["unlocated"] == -8


# --------------------------------------------------------------------------- R37


def test_a_debt_stays_in_the_month_it_was_raised_in(scm_app):
    """R37, and the defect that produced it (30 Aug, captain's feedback).

    `1/2" ULTRA CIRCULAR` read -4 in Aug 26 and -4 again in every column after it, while the
    drill for September was empty - the cell was a running balance and the drill was a
    month, so the screen could not be added up. A month now states its own month: the line
    books its shortfall where it is due, and the months after it read 0 because nothing is
    due and nothing arrives in them.
    """
    app, db = _client(scm_app)
    marker = f"ZZTSD{_u()[:6]}".upper()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    product = _product(db, f"{marker}-A")
    _demand(
        db, product, warehouse, qty=4, required_date=_months_ahead(1),
        so_number=f"{marker}-SO1",
    )
    # A second product, so the axis reaches past the month the debt is in - the columns are
    # the whole filtered set's, and without it there would be no later month to read.
    later = _product(db, f"{marker}-B")
    _demand(
        db, later, warehouse, qty=1, required_date=_months_ahead(3),
        so_number=f"{marker}-SO2",
    )
    db.flush()

    due = month_key(_months_ahead(1))
    after = month_key(_months_ahead(2))
    with TestClient(app) as c:
        board = c.get(BASE, params={"query": marker, "only_debt": False}).json()
        drill = c.get(f"{BASE}/{product.id}/cell", params={"month": after}).json()

    row = _row_of(board, product.product_code)
    balances = {m["key"]: m["balance"] for m in row["months"]}
    assert balances[due] == -4
    assert balances[month_key(TODAY)] == 0
    assert balances[after] == 0
    assert balances[month_key(_months_ahead(3))] == 0
    # The cell that reads 0 opens onto nothing, which is now the same statement twice.
    assert drill == {"demand": [], "supply": []}


def test_supply_arriving_after_the_debt_is_spare_in_its_own_month(scm_app):
    """The other half of R37: 10 arriving next month against a 4 due this one reads -4 then
    +6. The arrival clears the earlier line (it is `late`), so 4 of it is spent and only the
    6 nobody took is spare - counted once, in the month it lands in."""
    app, db = _client(scm_app)
    marker = f"ZZTSD{_u()[:6]}".upper()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    product = _product(db, f"{marker}-A")
    _demand(
        db, product, warehouse, qty=4, required_date=_months_ahead(1),
        so_number=f"{marker}-SO1",
    )
    _spo(db, product, warehouse, qty=10, arrives=_months_ahead(2))
    db.flush()

    due = month_key(_months_ahead(1))
    arrives = month_key(_months_ahead(2))
    with TestClient(app) as c:
        board = c.get(BASE, params={"query": marker, "only_debt": False}).json()
        short_cell = c.get(f"{BASE}/{product.id}/cell", params={"month": due}).json()
        spare_cell = c.get(f"{BASE}/{product.id}/cell", params={"month": arrives}).json()

    balances = {
        m["key"]: m["balance"] for m in _row_of(board, product.product_code)["months"]
    }
    assert balances[due] == -4
    assert balances[arrives] == 6

    # The line ends covered and its month still owes the 4: it went without on the date it
    # was promised, which is the fact the planner acts on.
    assert short_cell["demand"][0]["status"] == "late"
    assert short_cell["demand"][0]["short_qty"] == 4
    assert short_cell["supply"] == []
    assert spare_cell["demand"] == []
    assert spare_cell["supply"][0]["qty"] == 10
    assert spare_cell["supply"][0]["free_qty"] == 6


def test_every_cell_foots_with_its_drill(scm_app):
    """The identity R37 is worth having: for every month, the drill's free supply less its
    short-at-date demand IS the balance the cell prints. 20 on hand, 30 due next month (20
    now, 10 late off the SPO), 50 arriving the month after, 5 due the month after that."""
    app, db = _client(scm_app)
    marker = f"ZZTSD{_u()[:6]}".upper()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    product = _product(db, f"{marker}-A")
    _stock(db, product, warehouse, 20)
    _demand(
        db, product, warehouse, qty=30, required_date=_months_ahead(1),
        so_number=f"{marker}-SO1",
    )
    _spo(db, product, warehouse, qty=50, arrives=_months_ahead(2))
    _demand(
        db, product, warehouse, qty=5, required_date=_months_ahead(3),
        so_number=f"{marker}-SO2",
    )
    db.flush()

    with TestClient(app) as c:
        board = c.get(BASE, params={"query": marker, "only_debt": False}).json()
        row = _row_of(board, product.product_code)
        cells = {
            month["key"]: c.get(
                f"{BASE}/{product.id}/cell", params={"month": month["key"]}
            ).json()
            for month in row["months"]
        }

    balances = {m["key"]: m["balance"] for m in row["months"]}
    for key, cell in cells.items():
        free = sum(event["free_qty"] for event in cell["supply"])
        short = sum(line["short_qty"] for line in cell["demand"])
        assert free - short == balances[key], f"{key} does not foot with its drill"

    # And the figures themselves, so the identity cannot be satisfied by two zeroes.
    assert balances[month_key(TODAY)] == 0
    assert balances[month_key(_months_ahead(1))] == -10
    assert balances[month_key(_months_ahead(2))] == 35
    assert balances[month_key(_months_ahead(3))] == 0


def test_the_tba_undated_and_unlocated_cells_are_unchanged_by_the_month_rule(scm_app):
    """R37 is about MONTHS. The three buckets are not cumulative and never were: they draw
    nothing at all, so every line in them is short its whole open quantity and there is no
    supply to be free."""
    app, db = _client(scm_app)
    marker = f"ZZTSD{_u()[:6]}".upper()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    product = _product(db, f"{marker}-A")
    _stock(db, product, warehouse, 500)
    _demand(
        db, product, warehouse, qty=60, required_date=date(2030, 1, 1),
        so_number=f"{marker}-TBA",
    )
    _demand(
        db, product, warehouse, qty=12, required_date=None, so_number=f"{marker}-NODATE",
    )
    _order, line = _demand(
        db, product, warehouse, qty=15, required_date=_months_ahead(1),
        so_number=f"{marker}-NOWHERE",
    )
    line.warehouse_id = None
    db.flush()

    with TestClient(app) as c:
        board = c.get(BASE, params={"query": marker, "only_debt": False}).json()
        cells = {
            bucket: c.get(
                f"{BASE}/{product.id}/cell", params={"month": bucket}
            ).json()
            for bucket in ("tba", "undated", "unlocated")
        }

    row = _row_of(board, product.product_code)
    assert (row["tba"], row["undated"], row["unlocated"]) == (-60, -12, -15)
    for bucket, cell in cells.items():
        assert cell["supply"] == [], bucket
        for entry in cell["demand"]:
            assert entry["short_qty"] == entry["open_qty"], bucket
    assert sum(e["short_qty"] for e in cells["tba"]["demand"]) == 60
    assert sum(e["short_qty"] for e in cells["undated"]["demand"]) == 12
    assert sum(e["short_qty"] for e in cells["unlocated"]["demand"]) == 15
    # Nothing drew on the 500, so it is spare in the month it sits in - and only there.
    balances = {m["key"]: m["balance"] for m in row["months"]}
    assert balances[month_key(TODAY)] == 500


def test_on_hand_is_stamped_with_the_callers_as_of_not_the_clock(scm_app):
    """Review finding: `_supply()` stamped every on-hand event `date.today()`.

    A board simulated at a PAST date (`as_of`, which the ladder pins so a walk is
    reproducible) then read its own floor as arriving after every line due between the two
    dates, so a line due yesterday drew nothing on its own date and came back `late` off
    stock that has been on the shelf all along. The event belongs on the day the walk
    starts, which is the caller's `as_of`.
    """
    app, db = _client(scm_app)
    marker = f"ZZTSD{_u()[:6]}".upper()
    warehouse = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    product = _product(db, f"{marker}-A")
    _stock(db, product, warehouse, 40)
    # Due BETWEEN the simulated day and today: the window the bug lived in.
    _demand(
        db, product, warehouse, qty=40, required_date=TODAY - timedelta(days=3),
        so_number=f"{marker}-SO1",
    )
    db.flush()

    from app.services.scm.stock_debt_service import StockDebtService

    service = StockDebtService(db)
    result = service.assignments_for(
        [str(product.id)],
        {str(warehouse.id): warehouse},
        as_of=TODAY - timedelta(days=10),
    )[str(product.id)]
    line = result.lines[0]
    events = [event for event in result.supply if event.kind == "on_hand"]

    assert events and events[0].at == TODAY - timedelta(days=10)
    assert line.status == "covered", "the floor was there on the simulated day"
    assert line.short_at_date == 0
