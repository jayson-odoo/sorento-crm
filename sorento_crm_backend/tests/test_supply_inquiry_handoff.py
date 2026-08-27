"""Buy-only Order Inquiry handoff (PLAN-scm-front-planning.md section 4, Group D).

RED for Stage 1C: `ProjectOrderInquiryService.refresh_for_decision`, `SOSupplyDecision`
(`app.models.project_so`), `order_inquiry_rows.supply_decision_id`, and the narrow reader
`confirmed_unplaced_buy_rows()` do not exist yet, and the `/confirm` route is not mounted.
Every test either calls a route that 404s, imports something not built yet, or asserts a
response shape (`line_no` / `decision_revision` / `project_so_ref`) the current schema does
not carry -- all "right reason" RED per
`documentation/plans/scm/STAGE1C-scm-front-planning-promising.md` section 8.

Postgres via `tests/_pg_fixture.py`, never sqlite. Every test seeds its own chain.
"""
from __future__ import annotations

import re
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.inventory import Stock, Warehouse
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import (
    INQUIRY_ACTIONED,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    IV_ORDER,
    SO_STATUS_PUBLISHED,
    OrderInquiry,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from app.models.user import User
from app.services import project_seed_service
from app.services.project_order_inquiry_service import ProjectOrderInquiryService

from ._pg_fixture import blank_session

MARKER = "zzt-handoff"
BASE = "/api/v1/project-sales"
REQUIRED_DATE = date(2027, 3, 1)

# A UUID has five hyphen-separated groups of hex digits. If this pattern is found in any
# response field a display value leaked an id where a human-readable one belongs (AC-D06).
_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

#: The fields that carry an id ON PURPOSE (section 6: "addressing only ... never
#: rendered"). The row id is what the mark-actioned call posts back, and the rest are the
#: links the screen resolves to codes and references before it draws anything.
_ADDRESSING_KEYS = {
    "id",
    "order_inquiry_id",
    "so_line_id",
    "project_sales_order_id",
    "supply_decision_id",
}


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _product(db) -> Product:
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:4]}", uom_name="Set")
    category = ProductCategory(
        id=_uid(), category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} cat"
    )
    db.add_all([uom, category])
    db.flush()
    row = Product(
        id=_uid(), product_code=f"ZZT-{_uid()[:8]}", product_name=f"{MARKER} Basin",
        category_id=category.id, base_uom_id=uom.id, list_price=Decimal("100.00"),
    )
    db.add(row)
    db.flush()
    return row


def _warehouse(db, code: str) -> Warehouse:
    row = Warehouse(id=_uid(), warehouse_code=code, warehouse_name=code, location="ZZT", is_active=True)
    db.add(row)
    db.flush()
    return row


def _stock(db, product: Product, warehouse: Warehouse, on_hand, reserved=0) -> Stock:
    row = Stock(
        id=_uid(), product_id=product.id, warehouse_id=warehouse.id,
        quantity_on_hand=on_hand, quantity_reserved=reserved,
    )
    db.add(row)
    db.flush()
    return row


def _core_so(db, company_id: str, *, demand_class=None, demand_origin=None):
    from app.models.order import SalesOrder

    so = SalesOrder(
        id=_uid(), company_id=company_id, so_number=f"ZZT-CORE-{_uid()[:8]}", status="open",
        demand_class=demand_class, demand_origin=demand_origin,
    )
    db.add(so)
    db.flush()
    return so


def _core_line(db, so, product: Product, warehouse: Warehouse, *, qty_ordered, qty_delivered="0",
                required_date=REQUIRED_DATE):
    from app.models.order import SalesOrderLine

    line = SalesOrderLine(
        id=_uid(), company_id=so.company_id, sales_order_id=so.id, product_id=product.id,
        warehouse_id=warehouse.id, qty_ordered=Decimal(qty_ordered),
        qty_delivered=Decimal(qty_delivered), required_date=required_date, line_status="open",
    )
    db.add(line)
    db.flush()
    return line


def _project_so(db, project, *, status=SO_STATUS_PUBLISHED, so_id=None):
    order = ProjectSalesOrder(
        id=_uid(), company_id=project.company_id, project_id=project.id,
        provisional_ref=f"ZZT-PSO-{_uid()[:8]}", area_group="TOWER", status=status, so_id=so_id,
    )
    db.add(order)
    db.flush()
    return order


def _project_line(db, order, *, line_no, product: Product, core_line):
    line = ProjectSalesOrderLine(
        id=_uid(), company_id=order.company_id, project_sales_order_id=order.id,
        core_sales_order_line_id=core_line.id if core_line else None, line_no=line_no,
        product_id=product.id, description=f"{MARKER} line {line_no}",
        qty=core_line.qty_ordered if core_line else Decimal("0"), uom="SET",
        unit_price=Decimal("100.00"), amount=Decimal("0"),
        delivery_date=core_line.required_date if core_line else REQUIRED_DATE,
    )
    db.add(line)
    db.flush()
    return line


def _client(db, user_id: str):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    actor = {"id": user_id, "email": f"{user_id}@zzt.test", "role": "user"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    app.dependency_overrides[apply_company_scope] = lambda: None

    originals = (
        UserPermissionService.check_user_has_permission,
        UserPermissionService.get_user_permission_slugs,
    )
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: True
    UserPermissionService.get_user_permission_slugs = lambda self, uid: [
        "projects.projects.view", "projects.projects.create", "projects.projects.edit",
        "projects.order_inquiry.action",
    ]
    return TestClient(app), originals


def _restore(originals) -> None:
    from app.main import app
    from app.services.user_service import UserPermissionService

    UserPermissionService.check_user_has_permission = originals[0]
    UserPermissionService.get_user_permission_slugs = originals[1]
    app.dependency_overrides.clear()


class _World:
    def __init__(self, db, company_id, eling, project, product, own_wh, pool_wh):
        self.db = db
        self.company_id = company_id
        self.eling = eling
        self.project = project
        self.product = product
        self.own_wh = own_wh
        self.pool_wh = pool_wh


@pytest.fixture()
def api():
    from app.models.base import company_scope
    from app.services.project_service import register_project

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        eling = _user(db, f"{MARKER} Eling")
        project = register_project(
            db, company_id=company_id, actor_user_id=eling, developer_party_id=None,
            title=f"{MARKER} Tuju Residences",
        )
        product = _product(db)
        own_wh = _warehouse(db, f"ZZT-OWN-{_uid()[:4]}")
        pool_wh = _warehouse(db, f"ZZT-BRW-{_uid()[:4]}")
        own_wh.pool_warehouse_id = pool_wh.id
        db.commit()
        client, originals = _client(db, eling)
        world = _World(db, company_id, eling, project, product, own_wh, pool_wh)
        try:
            with company_scope(db, frozenset({company_id})):
                yield client, world
        finally:
            _restore(originals)


def _line_payload(project_line_id, *, timely_spo_qty="0", reserve=None, borrow=None,
                   buy_qty="0", buy_reason=None):
    body = {
        "project_line_id": project_line_id, "timely_spo_qty": timely_spo_qty,
        "reserve": reserve or [], "borrow": borrow or [], "buy_qty": buy_qty,
    }
    if buy_reason is not None:
        body["buy_reason"] = buy_reason
    return body


# --------------------------------------------------------------------------- AC-D01


def test_inquiry_rows_appear_only_at_successful_confirmation_not_at_publish_or_reconcile(api):
    """Publish and reconcile create nothing (already true today, Stage 0); the missing half
    is that a successful confirmation must create the row in the SAME transaction."""
    client, world = api
    db = world.db
    # Reconciled for real: the Project SO names the core sales order its lines are linked
    # to. Without the header link, re-running reconciliation clears the line links as
    # stale, which is Stage 1B behaviour and not what this test is about.
    core_so = _core_so(db, world.company_id)
    order = _project_so(db, world.project, so_id=core_so.id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="25")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    from app.services.project_so_reconciliation_service import ProjectSOReconciliationService

    ProjectSOReconciliationService(db).reconcile(order)
    db.commit()
    assert (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id)
        .count()
        == 0
    ), "reconcile alone must create nothing"

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, buy_qty="25")]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["inquiry_rows_created"] == 1


# --------------------------------------------------------------------------- AC-D02


def test_inquiry_row_quantity_equals_the_confirmed_buy_residual_exactly_and_zero_buy_creates_no_row(api):
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=100)
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line_buy = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="25")
    core_line_no_buy = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="40")
    buy_line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line_buy)
    reserve_line = _project_line(
        db, order, line_no=20, product=world.product, core_line=core_line_no_buy
    )
    db.commit()

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(buy_line.id, buy_qty="25"),
                _line_payload(
                    reserve_line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "40"}]
                ),
            ]
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["inquiry_rows_created"] == 1

    rows = db.query(OrderInquiryRow).filter(
        OrderInquiryRow.so_line_id.in_([buy_line.id, reserve_line.id])
    ).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.so_line_id == buy_line.id
    assert row.qty == Decimal("25")
    assert row.verb == IV_ORDER


# --------------------------------------------------------------------------- AC-D03


def test_a_wholly_reserved_line_raises_nothing_for_purchasing_at_all(api):
    """A Reserve is not purchasing demand, and under the whole-line rule (AC-L5) a line
    carrying one carries nothing else - so a reserved line raises no Order Inquiry row.

    This used to be stated as "a Reserve 30 beside a Buy 20 raises a row for 20 only"; that
    composition can no longer be confirmed, and the invariant it protected (a Reserve never
    reaches purchasing) is what survives.
    """
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=50)
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="50")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(
                    line.id,
                    reserve=[{"warehouse_id": world.pool_wh.id, "qty": "50"}],
                )
            ]
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["inquiry_rows_created"] == 0

    rows = db.query(OrderInquiryRow).filter(OrderInquiryRow.so_line_id == line.id).all()
    assert rows == [], "a Reserve must not leak into purchasing demand"


# --------------------------------------------------------------------------- AC-D05


def test_retrying_the_same_confirmation_does_not_duplicate_the_inquiry_row(api):
    client, world = api
    db = world.db
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="15")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    payload = {"lines": [_line_payload(line.id, buy_qty="15")]}
    first = client.post(f"{BASE}/sales-orders/{order.id}/confirm", json=payload)
    assert first.status_code == 200, first.text
    second = client.post(f"{BASE}/sales-orders/{order.id}/confirm", json=payload)
    assert second.status_code == 200, second.text

    active_rows = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.state != "cancelled")
        .all()
    )
    assert len(active_rows) == 1, "a retried confirm must not raise a second row"


def test_reconfirming_with_a_lower_need_cancels_unplaced_rows_and_flags_placed_ones_with_a_cancel_balance_exception(api):
    """AC-C07/AC-D05: a placed row stays in the ledger; a lower revised need raises a
    CANCEL_BALANCE exception naming the shortfall instead of quietly shrinking the row."""
    client, world = api
    db = world.db
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="40")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    first = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, buy_qty="40")]},
    )
    assert first.status_code == 200, first.text

    placed_row = db.query(OrderInquiryRow).filter(OrderInquiryRow.so_line_id == line.id).one()
    placed_row.state = INQUIRY_ACTIONED
    placed_row.actioned_by = world.eling
    db.commit()

    core_line.qty_ordered = Decimal("15")
    db.commit()

    second = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, buy_qty="15")]},
    )
    assert second.status_code == 200, second.text

    db.expire_all()
    assert db.get(OrderInquiryRow, placed_row.id).state == INQUIRY_ACTIONED, (
        "placed supply must stay in the ledger, never silently rewritten"
    )
    exceptions = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.verb == "CANCEL_BALANCE")
        .all()
    )
    assert len(exceptions) == 1
    assert "40" in (exceptions[0].note or "")
    assert "15" in (exceptions[0].note or "")

    # A THIRD confirmation at the same lower need supersedes the standing exception row
    # rather than stacking a copy beside it: exactly one raised CANCEL_BALANCE at a time.
    third = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, buy_qty="15")]},
    )
    assert third.status_code == 200, third.text
    db.expire_all()
    raised_exceptions = (
        db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.so_line_id == line.id,
            OrderInquiryRow.verb == "CANCEL_BALANCE",
            OrderInquiryRow.state == INQUIRY_RAISED,
        )
        .all()
    )
    assert len(raised_exceptions) == 1, (
        "every reconfirm at the same lower need must leave one live exception, not stack"
    )


def test_reconfirming_with_a_lower_need_after_a_real_place_on_po_flags_a_cancel_balance_exception(api):
    """The same scenario as the test above, but the row reaches its committed state
    through the REAL "Place on PO" path (section G, `ProjectOrderInquiryService.place_on_po`)
    rather than a hand-set `INQUIRY_ACTIONED` - the live workflow purchasing actually
    uses, and the one the 20 Aug regression hid behind: the netting predicate only
    recognised `INQUIRY_ACTIONED` (0 rows company-wide), so every one of the 145 live
    `INQUIRY_PLACED` rows was invisible to it and a lower reconfirm would have silently
    shrunk the placed row's own quantity instead of raising a CANCEL_BALANCE exception."""
    client, world = api
    db = world.db
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="40")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    first = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, buy_qty="40")]},
    )
    assert first.status_code == 200, first.text

    placed_row = db.query(OrderInquiryRow).filter(OrderInquiryRow.so_line_id == line.id).one()

    supplier = Supplier(
        id=_uid(), company_id=world.company_id, supplier_code=f"ZZT-{_uid()[:8]}",
        supplier_name=f"{MARKER} supplier",
    )
    po = PurchaseOrder(
        id=_uid(), company_id=world.company_id, po_number=f"ZZT-PO-{_uid()[:8]}",
        supplier_id=supplier.id,
    )
    db.add_all([supplier, po])
    db.flush()
    po_line = PurchaseOrderLine(
        id=_uid(), company_id=world.company_id, purchase_order_id=po.id,
        product_id=world.product.id, warehouse_id=world.own_wh.id,
        qty_ordered=Decimal("40"), qty_received=Decimal("0"), line_status="open",
    )
    db.add(po_line)
    db.commit()
    ProjectOrderInquiryService(db).place_on_po(placed_row.id, po_line.id, actor_user_id=world.eling)
    db.commit()
    db.expire_all()
    placed_row = db.get(OrderInquiryRow, placed_row.id)
    assert placed_row.state == INQUIRY_PLACED
    assert placed_row.po_ref == po.po_number

    core_line.qty_ordered = Decimal("15")
    db.commit()

    second = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, buy_qty="15")]},
    )
    assert second.status_code == 200, second.text

    db.expire_all()
    still_placed = db.get(OrderInquiryRow, placed_row.id)
    assert still_placed.state == INQUIRY_PLACED, (
        "placed supply must stay in the ledger, never silently rewritten"
    )
    assert still_placed.qty == Decimal("40"), "the placed row's own quantity is untouched"
    assert still_placed.po_ref == po.po_number, "the PO tag survives a reconfirm"

    exceptions = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line.id, OrderInquiryRow.verb == "CANCEL_BALANCE")
        .all()
    )
    assert len(exceptions) == 1
    assert "40" in (exceptions[0].note or "")
    assert "15" in (exceptions[0].note or "")


# --------------------------------------------------------------------------- AC-D04


def test_confirmed_unplaced_buy_rows_reader_counts_raised_order_rows_directly(api):
    """PLAN section 4: the narrow SCM reader counts current `raised` ORDER rows directly,
    with no re-netting against pre-order or inbound pools."""
    client, world = api
    db = world.db
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="18")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, buy_qty="18")]},
    )
    assert response.status_code == 200, response.text

    from app.services.project_order_inquiry_service import confirmed_unplaced_buy_rows

    rows = confirmed_unplaced_buy_rows(db, product_id=world.product.id, warehouse_id=world.own_wh.id)
    assert sum(Decimal(str(r.qty)) for r in rows) == Decimal("18")


# --------------------------------------------------------------------------- sheet-leg predicate


def test_the_sheet_leg_predicate_excludes_a_core_so_once_its_project_so_holds_an_active_decision(api):
    """PLAN section 4: the sheet leg keeps counting a sheet-named project SO until it is
    confirmed, then the confirmed Buy replaces it -- never both.

    The CLAIM is unchanged; the LEVEL it is answered at moved, and this test moved with it.
    `is_plan_demand_order()` alone used to say it, because a confirmation had to cover
    every line of its order. Since partial confirmation
    (`PLAN-fulfilment-planning-from-autocount-so.md` 13.4) it takes both halves of the
    rule: the order half says the sheet speaks for this order, the LINE half says which of
    its lines CS has already decided. Deciding it per order again would take an order's
    undecided lines out of the plan with its decided one, which is the defect 13.4 exists
    to prevent (`tests/test_partial_decision_demand_invariants.py`).
    """
    from app.models.order import SalesOrder, SalesOrderLine
    from app.services.scm.demand import is_plan_demand_line, is_plan_demand_order

    client, world = api
    db = world.db
    core_so = _core_so(
        db, world.company_id, demand_class="project", demand_origin="scm_order_inquiry"
    )
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="12")
    order = _project_so(db, world.project, so_id=core_so.id)
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    def counted_lines():
        return (
            db.query(SalesOrderLine.id)
            .join(SalesOrder, SalesOrder.id == SalesOrderLine.sales_order_id)
            .filter(
                SalesOrderLine.sales_order_id == core_so.id,
                is_plan_demand_order(),
                is_plan_demand_line(),
            )
            .all()
        )

    assert counted_lines(), "unconfirmed, the sheet leg must still count"

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, buy_qty="12")]},
    )
    assert response.status_code == 200, response.text

    db.expire_all()
    assert not counted_lines(), (
        "confirmed, the sheet leg must stop counting a second time"
    )


def test_committed_v_excludes_a_confirmed_project_sos_line_from_its_committed_sum():
    """The SQL twin of the predicate above, since `scm.committed_v` and
    `is_plan_demand_order()` must never disagree (`app/services/scm/demand.py`).

    Runs against the REAL database (`_pg_fixture.pg_session`), not the blank scratch
    schema the `api` fixture uses: `scm.committed_v` is a VIEW created by a migration, not
    an ORM table, so it does not exist inside `blank_session`'s scratch schema at all.
    """
    from app.models.base import company_scope
    from app.services.project_service import register_project

    from ._pg_fixture import pg_session

    with pg_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        eling = _user(db, f"{MARKER} Eling")
        project = register_project(
            db, company_id=company_id, actor_user_id=eling, developer_party_id=None,
            title=f"{MARKER} Committed-V Residences",
        )
        product = _product(db)
        own_wh = _warehouse(db, f"ZZT-CV-{_uid()[:4]}")
        pool_wh = _warehouse(db, f"ZZTCVP{_uid()[:6]}")
        own_wh.pool_warehouse_id = pool_wh.id
        _stock(db, product, pool_wh, on_hand=5)
        core_so = _core_so(db, company_id, demand_class="project", demand_origin="scm_order_inquiry")
        core_line = _core_line(db, core_so, product, own_wh, qty_ordered="4")
        order = _project_so(db, project, so_id=core_so.id)
        line = _project_line(db, order, line_no=10, product=product, core_line=core_line)
        db.commit()

        client, originals = _client(db, eling)
        try:
            with company_scope(db, frozenset({company_id})):
                # 4 on the sheet, wholly bought (AC-L5: a line is met entirely from stock or
                # entirely bought). The pool holds 5 and is deliberately not drawn on, so
                # "the sheet leg is gone" and "the confirmed Buy is counted" stay
                # distinguishable in the one number below.
                response = client.post(
                    f"{BASE}/sales-orders/{order.id}/confirm",
                    json={"lines": [_line_payload(line.id, buy_qty="4")]},
                )
                assert response.status_code == 200, response.text
        finally:
            _restore(originals)

        committed = Decimal(
            str(
                db.execute(
                    text(
                        "SELECT COALESCE(SUM(committed), 0) FROM scm.committed_v "
                        "WHERE product_id = :pid AND warehouse_id = :wid"
                    ),
                    {"pid": product.id, "wid": own_wh.id},
                ).scalar()
            )
        )
        # The sheet's 4 must be gone whatever else the view carries. This slice's view
        # answers 0 (the confirmed Buy reaches SCM through
        # `confirmed_unplaced_buy_rows`, and the committed Buy LEG is Stage 2's own
        # addition to this view); a database that already has Stage 2's version answers 4,
        # the confirmed Buy residual. Both count the requirement exactly once, which is
        # the criterion. 8 would be the double count this exists to stop.
        assert committed in (Decimal("0"), Decimal("4")), (
            "the sheet leg must stop being counted once the project SO is confirmed, "
            f"and the view answered {committed}"
        )


# --------------------------------------------------------------------------- AC-D06


def test_serialized_inquiry_rows_carry_human_identifiers_and_no_uuid(api):
    """AC-D06: line_no, decision_revision and project_so_ref, never a UUID."""
    client, world = api
    db = world.db
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="11")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    confirmed = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, buy_qty="11")]},
    )
    assert confirmed.status_code == 200, confirmed.text

    listed = client.get(f"{BASE}/projects/{world.project.id}/order-inquiry-rows")
    assert listed.status_code == 200, listed.text
    rows = listed.json()["data"]
    assert len(rows) == 1
    row = rows[0]
    assert row["line_no"] == 10
    assert row["decision_revision"] == 1
    assert row["project_so_ref"] == order.provisional_ref

    # Section 6 is explicit that a handful of fields are ADDRESSING and are never
    # rendered - the row's own id is what "mark actioned" posts back, and the sheet needs
    # the ids of the things it names by code. Every other field is something a person
    # reads, and a UUID in one of those is the defect this guards.
    for key, value in row.items():
        if key in _ADDRESSING_KEYS or not isinstance(value, str):
            continue
        assert not _UUID_RE.search(value), f"a UUID leaked into a display field: {value}"
