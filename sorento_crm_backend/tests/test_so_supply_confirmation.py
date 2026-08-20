"""Atomic Project SO confirmation over HTTP (PLAN-scm-front-planning.md 3.1/5.2/5.3, Group C).

RED for Stage 1C: `projects.so_supply_decisions` (migration 374), `app.models.project_so.
SOSupplyDecision`, `app.services.project_supply_service.confirm`/`proposal_for`, and the
`/project-sales/sales-orders/{pso_id}/confirm` + `.../supply` routes do not exist yet. Every
test here either calls a route that 404s today, or imports a model that does not exist yet
-- both are the "right reason" this file is meant to fail for, per
`documentation/plans/scm/STAGE1C-scm-front-planning-promising.md` section 8.

Postgres via `tests/_pg_fixture.py::blank_session`, never sqlite. Every test seeds its own
full chain (company, project, project SO, lines linked to a real core SO+lines, warehouses,
stock, classification, reorder level, SPO/shipment where needed) rather than borrowing an
existing row, per PRINCIPLES.md and the CI-is-empty lesson in this repo's CLAUDE.md.
"""
from __future__ import annotations

import itertools
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.inventory import Stock, Warehouse
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import (
    SO_STATUS_PUBLISHED,
    AllocationClaim,
    CLAIM_ACCEPTED,
    CLAIM_REQUESTED,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from app.models.user import User
from app.services import project_seed_service

from ._pg_fixture import blank_session

MARKER = "zzt-confirm"
BASE = "/api/v1/project-sales"
VIEW = "projects.projects.view"
EDIT = "projects.projects.edit"
REQUIRED_DATE = date(2027, 3, 1)


def _uid() -> str:
    return str(uuid.uuid4())


_SUFFIX_SEQ = itertools.count()


def _suffix() -> str:
    """A deterministic, digit-free suffix for a fixture business code (warehouse
    code, product code, SO number, ...).

    Replaces a `_uid()[:4]`/`_uid()[:8]`-style random hex slice. Hex is
    digit-bearing most draws, and a code that lands one usually reads as
    ordinary test data - until an assertion checks that a refusal message does
    NOT mention a specific quantity substring and the warehouse's own random
    suffix happens to contain it (`ZZT-BRW-712c` tripping
    `assert "12" not in reason`; this file's actual flake,
    `test_re_confirming_a_larger_reserve_only_the_increase_competes_and_is_
    named_in_the_refusal`). Base-26 letters can never contain a digit, so that
    class of collision cannot recur.

    Monotonic within this process, so two calls anywhere in this file's run
    never repeat. Cross-worker uniqueness needs no extra help: every row this
    file writes lives inside `_pg_fixture.blank_session`, which rolls back at
    teardown and, ahead of that, runs on a scratch schema
    (`zzs_blank_<pid>_<hex>`) private to the xdist worker process
    (`_pg_fixture.blank_schema_engine`) - two workers' codes cannot collide
    even if they matched exactly.
    """
    n = next(_SUFFIX_SEQ) + 1
    letters = []
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters.append(chr(ord("A") + rem))
    return "".join(reversed(letters))


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _second_company(db) -> str:
    from app.models.company import Company

    cid = _uid()
    db.add(Company(id=cid, name=f"{MARKER} Other Co", code=f"ZZC{cid[:6]}"))
    db.flush()
    return cid


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _product(db, *, discontinued: bool = False) -> Product:
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_suffix()}", uom_name="Set")
    category = ProductCategory(
        id=_uid(), category_code=f"ZZT-{_suffix()}", category_name=f"{MARKER} cat"
    )
    db.add_all([uom, category])
    db.flush()
    row = Product(
        id=_uid(),
        product_code=f"ZZT-{_suffix()}",
        product_name=f"{MARKER} Basin",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("120.00"),
        is_discontinued=discontinued,
    )
    db.add(row)
    db.flush()
    return row


def _warehouse(db, code: str, *, segment=None, pool_warehouse_id=None, active: bool = True) -> Warehouse:
    row = Warehouse(
        id=_uid(),
        warehouse_code=code,
        warehouse_name=code,
        location="ZZT",
        is_active=active,
        segment=segment,
        pool_warehouse_id=pool_warehouse_id,
    )
    db.add(row)
    db.flush()
    return row


def _stock(db, product: Product, warehouse: Warehouse, on_hand, reserved=0) -> Stock:
    row = Stock(
        id=_uid(),
        product_id=product.id,
        warehouse_id=warehouse.id,
        quantity_on_hand=on_hand,
        quantity_reserved=reserved,
    )
    db.add(row)
    db.flush()
    return row


def _core_so(db, company_id: str):
    from app.models.order import SalesOrder

    so = SalesOrder(
        id=_uid(),
        company_id=company_id,
        so_number=f"ZZT-CORE-{_suffix()}",
        status="open",
        demand_class="project",
    )
    db.add(so)
    db.flush()
    return so


def _core_line(db, so, product: Product, warehouse: Warehouse, *, qty_ordered, qty_delivered="0",
                required_date=REQUIRED_DATE):
    from app.models.order import SalesOrderLine

    line = SalesOrderLine(
        id=_uid(),
        company_id=so.company_id,
        sales_order_id=so.id,
        product_id=product.id,
        warehouse_id=warehouse.id,
        qty_ordered=Decimal(qty_ordered),
        qty_delivered=Decimal(qty_delivered),
        required_date=required_date,
        line_status="open",
    )
    db.add(line)
    db.flush()
    return line


def _project_so(db, project, *, status=SO_STATUS_PUBLISHED, so_id=None):
    order = ProjectSalesOrder(
        id=_uid(),
        company_id=project.company_id,
        project_id=project.id,
        provisional_ref=f"ZZT-PSO-{_suffix()}",
        area_group="TOWER",
        status=status,
        # The reconciled core sales order. Set wherever the assertion turns on the review
        # state, because Stage 1B reads `awaiting_reconciliation` until the HEADER is
        # linked too, not only the lines (`_header` in the reconciliation service).
        so_id=so_id,
    )
    db.add(order)
    db.flush()
    return order


def _project_line(db, order, *, line_no, product: Product, core_line):
    line = ProjectSalesOrderLine(
        id=_uid(),
        company_id=order.company_id,
        project_sales_order_id=order.id,
        core_sales_order_line_id=core_line.id if core_line else None,
        line_no=line_no,
        product_id=product.id,
        description=f"{MARKER} line {line_no}",
        qty=core_line.qty_ordered if core_line else Decimal("0"),
        uom="SET",
        unit_price=Decimal("120.00"),
        amount=Decimal("0"),
        delivery_date=core_line.required_date if core_line else REQUIRED_DATE,
    )
    db.add(line)
    db.flush()
    return line


def _classification(
    db,
    product: Product,
    warehouse: Warehouse,
    *,
    abc_class_retail: str | None = "A",
    abc_class_project: str | None = None,
):
    from app.models.scm import ItemClassification

    row = ItemClassification(
        id=_uid(),
        product_id=product.id,
        warehouse_id=warehouse.id,
        abc_class_retail=abc_class_retail,
        abc_class_project=abc_class_project,
    )
    db.add(row)
    db.flush()
    return row


def _reorder_level(db, company_id: str, product: Product, warehouse: Warehouse, *, level):
    from app.models.scm import ReorderLevel

    row = ReorderLevel(
        id=_uid(), company_id=company_id, product_id=product.id, warehouse_id=warehouse.id,
        level=Decimal(level),
    )
    db.add(row)
    db.flush()
    return row


def _spo(db, company_id: str, product: Product, warehouse: Warehouse, *, qty, arrival_date,
         spo_number="ZZT-SPO-0001"):
    from app.models.procurement import InboundShipment, SPOAllocation

    shipment = InboundShipment(
        id=_uid(), company_id=company_id, shipment_date=arrival_date,
        estimated_arrival_date=arrival_date, shipment_status="in_transit",
    )
    db.add(shipment)
    db.flush()
    alloc = SPOAllocation(
        id=_uid(), company_id=company_id, spo_number=spo_number, spo_line_number=1,
        inbound_shipment_id=shipment.id, warehouse_id=warehouse.id, product_id=product.id,
        allocated_quantity=int(qty),
    )
    db.add(alloc)
    db.flush()
    return shipment, alloc


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
    UserPermissionService.get_user_permission_slugs = lambda self, uid: [VIEW, "projects.projects.create", EDIT]
    return TestClient(app), originals


def _restore(originals) -> None:
    from app.main import app
    from app.services.user_service import UserPermissionService

    UserPermissionService.check_user_has_permission = originals[0]
    UserPermissionService.get_user_permission_slugs = originals[1]
    app.dependency_overrides.clear()


def _act_as(client, user_id: str) -> None:
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app

    actor = {"id": user_id, "email": f"{user_id}@zzt.test", "role": "user"}
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)


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
        own_wh = _warehouse(db, f"ZZT-OWN-{_suffix()}", segment="project")
        pool_wh = _warehouse(db, f"ZZT-BRW-{_suffix()}", segment="dealer")
        own_wh.pool_warehouse_id = pool_wh.id
        db.flush()
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
        "project_line_id": project_line_id,
        "timely_spo_qty": timely_spo_qty,
        "reserve": reserve or [],
        "borrow": borrow or [],
        "buy_qty": buy_qty,
    }
    if buy_reason is not None:
        body["buy_reason"] = buy_reason
    return body


# --------------------------------------------------------------------------- happy path


def test_confirming_a_balanced_multi_line_so_writes_one_active_decision_with_grouped_allocations(api):
    """AC-C01/AC-C04: one Confirm writes one active revision covering every line."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=100)
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line_1 = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="50")
    core_line_2 = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="30")
    line1 = _project_line(db, order, line_no=10, product=world.product, core_line=core_line_1)
    line2 = _project_line(db, order, line_no=20, product=world.product, core_line=core_line_2)
    db.commit()

    payload = {
        "lines": [
            _line_payload(line1.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "50"}]),
            _line_payload(line2.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "30"}]),
        ]
    }
    response = client.post(f"{BASE}/sales-orders/{order.id}/confirm", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["revision_no"] == 1
    assert body["review_state"] == "confirmed"
    assert body["inquiry_rows_created"] == 0  # no Buy on either line
    assert body["exceptions"] == []

    from app.models.project_so import SOSupplyDecision, SOLineAllocation

    decisions = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id)
        .all()
    )
    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.state == "active"
    assert decision.revision_no == 1
    assert len(decision.line_snapshots) == 2

    allocations = (
        db.query(SOLineAllocation)
        .filter(SOLineAllocation.decision_id == decision.id)
        .all()
    )
    assert len(allocations) == 2
    assert {a.so_line_id for a in allocations} == {line1.id, line2.id}


def test_a_composition_spanning_pool_reserve_and_buy_still_names_one_location(api):
    """AC-H5: the ORDER row is the line's OWN fulfilment location, never a join of every
    warehouse the composition touched. A composition mixing a pool Reserve with a Buy
    residual used to stamp `"<own> + <pool>"` on the line - unreadable by purchasing, and
    unable to ever match a borrow-shortfall row netted by `(item_code, stock_location)`.
    """
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=30)
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
                    reserve=[{"warehouse_id": world.pool_wh.id, "qty": "30"}],
                    buy_qty="20",
                )
            ]
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["inquiry_rows_created"] == 1

    from app.models.project_so import IV_ORDER, OrderInquiryRow

    rows = db.query(OrderInquiryRow).filter(OrderInquiryRow.verb == IV_ORDER).all()
    assert len(rows) == 1
    assert rows[0].stock_location == world.own_wh.warehouse_code
    assert " + " not in (rows[0].stock_location or "")

    db.refresh(line)
    assert line.stock_location == world.own_wh.warehouse_code


# --------------------------------------------------------------------------- rollback


def test_one_unbalanced_line_rolls_back_the_whole_confirmation(api):
    """AC-C02: line 2's Buy is short of open qty by 10, so nothing commits, not even
    line 1's otherwise-valid Reserve."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.own_wh, on_hand=100)
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line_1 = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="50")
    core_line_2 = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="30")
    line1 = _project_line(db, order, line_no=10, product=world.product, core_line=core_line_1)
    line2 = _project_line(db, order, line_no=20, product=world.product, core_line=core_line_2)
    db.commit()

    payload = {
        "lines": [
            _line_payload(line1.id, reserve=[{"warehouse_id": world.own_wh.id, "qty": "50"}]),
            # 20 buy against an open qty of 30: unbalanced by 10.
            _line_payload(line2.id, buy_qty="20"),
        ]
    }
    response = client.post(f"{BASE}/sales-orders/{order.id}/confirm", json=payload)
    assert response.status_code in (409, 422), response.text
    body = response.json()
    failing_line_nos = {row["line_no"] for row in body["failing_lines"]}
    assert 20 in failing_line_nos

    from app.models.project_so import OrderInquiryRow, SOLineAllocation, SOSupplyDecision

    assert db.query(SOSupplyDecision).filter(
        SOSupplyDecision.project_sales_order_id == order.id
    ).count() == 0
    assert db.query(SOLineAllocation).filter(
        SOLineAllocation.so_line_id.in_([line1.id, line2.id])
    ).count() == 0
    assert db.query(OrderInquiryRow).filter(
        OrderInquiryRow.so_line_id.in_([line1.id, line2.id])
    ).count() == 0


# --------------------------------------------------------------------------- recheck


def test_confirmation_rechecks_stock_and_rejects_a_line_whose_free_stock_changed_after_the_sheet_was_read(api):
    """AC-C03: the sheet proposed Reserve 10 when 10 was free; another allocation then
    claims it, so the recheck at confirmation time must fail the line, not trust the
    payload."""
    client, world = api
    db = world.db
    stock = _stock(db, world.product, world.own_wh, on_hand=10, reserved=0)
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    # Something else claimed the stock after the sheet was opened.
    stock.quantity_reserved = 10
    db.commit()

    payload = {"lines": [_line_payload(line.id, reserve=[{"warehouse_id": world.own_wh.id, "qty": "10"}])]}
    response = client.post(f"{BASE}/sales-orders/{order.id}/confirm", json=payload)
    assert response.status_code in (409, 422), response.text
    body = response.json()
    assert any(row["line_no"] == 10 for row in body["failing_lines"])

    from app.models.project_so import SOSupplyDecision

    assert db.query(SOSupplyDecision).filter(
        SOSupplyDecision.project_sales_order_id == order.id
    ).count() == 0


# --------------------------------------------------------------------------- revision chain


def test_reconfirming_supersedes_the_active_decision_and_increments_the_revision(api):
    """AC-C04/AC-C07: a second Confirm on the same SO supersedes the first revision rather
    than replacing it in place, and the superseded revision's allocations stay for audit."""
    client, world = api
    db = world.db
    stock = _stock(db, world.product, world.pool_wh, on_hand=50)
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="50")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    first = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "50"}])]},
    )
    assert first.status_code == 200, first.text
    assert first.json()["revision_no"] == 1

    second = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(
                    line.id,
                    reserve=[{"warehouse_id": world.pool_wh.id, "qty": "30"}],
                    buy_qty="20",
                )
            ]
        },
    )
    assert second.status_code == 200, second.text
    assert second.json()["revision_no"] == 2

    from app.models.project_so import SOSupplyDecision, SOLineAllocation

    decisions = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id)
        .order_by(SOSupplyDecision.revision_no)
        .all()
    )
    assert [d.revision_no for d in decisions] == [1, 2]
    assert [d.state for d in decisions] == ["superseded", "active"]

    old_allocations = (
        db.query(SOLineAllocation).filter(SOLineAllocation.decision_id == decisions[0].id).all()
    )
    assert len(old_allocations) == 1, "the superseded revision's allocation must stay for audit"


# --------------------------------------------------------------------------- concurrency


def test_a_second_confirmation_racing_an_already_active_decision_gets_a_conflict_with_no_partial_writes(api):
    """AC-C05, driven through the DB-level singleton rather than through real threads.

    A confirmation that SEES an active decision supersedes it - that is reconfirmation,
    and it is the test above. The race is the other case: two sessions each read "nothing
    active here" and both insert, which is what the partial unique index exists to settle.

    Patching `active_decision` to answer None while an active row is committed reproduces
    exactly that: the service takes the first-confirmation path, its insert collides with
    the winner's row, and what has to be proven is that it loses WHOLE - a 409, one
    decision left, and not a single allocation or inquiry row from the loser's attempt.
    """
    from app.models.project_so import OrderInquiryRow, SOLineAllocation, SOSupplyDecision
    from app.services.project_supply_service import ProjectSupplyService

    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=50)
    order = _project_so(db, world.project, so_id=None)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="50")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    winner = SOSupplyDecision(
        id=_uid(),
        company_id=world.company_id,
        project_sales_order_id=order.id,
        revision_no=1,
        state="active",
        line_snapshots=[{"line_no": 10, "project_line_id": line.id}],
        confirmed_by=world.eling,
        confirmed_at=None,
    )
    db.add(winner)
    db.commit()

    original = ProjectSupplyService.active_decision
    try:
        ProjectSupplyService.active_decision = lambda self, pso_id: None
        response = client.post(
            f"{BASE}/sales-orders/{order.id}/confirm",
            json={"lines": [_line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "50"}])]},
        )
        assert response.status_code == 409, response.text
    finally:
        ProjectSupplyService.active_decision = original

    remaining = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id)
        .all()
    )
    assert len(remaining) == 1, "the loser must not have written a second active row"
    assert remaining[0].id == winner.id
    assert db.query(SOLineAllocation).filter(
        SOLineAllocation.so_line_id == line.id
    ).count() == 0
    assert db.query(OrderInquiryRow).filter(
        OrderInquiryRow.so_line_id == line.id
    ).count() == 0


def test_the_database_refuses_a_second_active_revision_for_one_sales_order(api):
    """The mechanism the test above leans on, stated on its own (AC-C05).

    `uq_so_supply_decisions_active` is what makes the loser of a real race lose: without
    it two confirmations would both commit and the same stock would be promised twice, with
    nothing in the data to say which promise was real.
    """
    from sqlalchemy.exc import IntegrityError

    from app.models.project_so import SOSupplyDecision

    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=50)
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="50")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    first = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "50"}])]},
    )
    assert first.status_code == 200, first.text

    db.add(
        SOSupplyDecision(
            id=_uid(),
            company_id=world.company_id,
            project_sales_order_id=order.id,
            revision_no=99,
            state="active",
            line_snapshots=[],
            confirmed_by=world.eling,
            confirmed_at=None,
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


# --------------------------------------------------------------------------- supersession


def test_publishing_an_amendment_supersedes_the_active_decision(api):
    """AC-C06 (amendment leg, PLAN 5.3): a material amendment publish must supersede the
    active revision so the SO returns to Needs CS review rather than staying confirmed
    against stale facts."""
    from app.models.project_so import (
        AMENDMENT_PROPOSED,
        OrderChangeNotice,
        SOAmendment,
        SOSupplyDecision,
    )

    client, world = api
    db = world.db
    _stock(db, world.product, world.own_wh, on_hand=50)
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="50")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    decision = SOSupplyDecision(
        id=_uid(), company_id=world.company_id, project_sales_order_id=order.id,
        revision_no=1, state="active",
        line_snapshots=[{"line_no": 10, "project_line_id": line.id}],
        confirmed_by=world.eling, confirmed_at=None,
    )
    db.add(decision)
    db.commit()

    ocn = OrderChangeNotice(
        id=_uid(), company_id=world.company_id, ocn_number=f"ZZT-OCN-{_suffix()}",
        project_id=world.project.id, project_sales_order_id=order.id,
        approver_id=world.eling, approved_at=None,
    )
    db.add(ocn)
    db.flush()
    amendment = SOAmendment(
        id=_uid(), company_id=world.company_id, project_sales_order_id=order.id,
        ocn_id=ocn.id, delta_json={"rows": []}, status=AMENDMENT_PROPOSED,
    )
    db.add(amendment)
    db.commit()

    from app.services.project_so_delta_service import ProjectSODeltaService

    ProjectSODeltaService(db).publish_amendment(amendment.id, actor_user_id=world.eling)
    db.commit()

    db.expire_all()
    refreshed = db.get(SOSupplyDecision, decision.id)
    assert refreshed.state == "superseded"
    assert refreshed.superseded_reason


def test_a_reconciliation_link_change_supersedes_the_active_decision(api):
    """AC-C06 (reconciliation leg, PLAN 5.3): `_persist` re-linking a Project line to a
    different core line must also supersede an active decision built against the old
    link."""
    from app.models.project_so import SOSupplyDecision

    client, world = api
    db = world.db
    _stock(db, world.product, world.own_wh, on_hand=50)
    core_so = _core_so(db, world.company_id)
    order = _project_so(db, world.project, so_id=core_so.id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="50")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    decision = SOSupplyDecision(
        id=_uid(), company_id=world.company_id, project_sales_order_id=order.id,
        revision_no=1, state="active",
        line_snapshots=[
            {
                "line_no": 10,
                "project_line_id": line.id,
                "core_line_id": core_line.id,
                "open_qty": "50",
            }
        ],
        confirmed_by=world.eling, confirmed_at=None,
    )
    db.add(decision)
    db.commit()

    # A material change on the CORE side: the line now needs a different quantity, which
    # reconciliation would relink or flag on its next run.
    core_line.qty_ordered = Decimal("80")
    db.commit()

    from app.services.project_so_reconciliation_service import ProjectSOReconciliationService

    ProjectSOReconciliationService(db).reconcile(order)
    db.commit()

    db.expire_all()
    refreshed = db.get(SOSupplyDecision, decision.id)
    assert refreshed.state in ("superseded", "challenged")


def test_a_fact_drift_challenges_the_active_decision_on_read(api):
    """PLAN 5.3: `proposal_for` compares each snapshot against live facts on every read and
    flips a mismatching active decision to `challenged`."""
    from app.models.project_so import SOSupplyDecision

    client, world = api
    db = world.db
    _stock(db, world.product, world.own_wh, on_hand=50)
    core_so = _core_so(db, world.company_id)
    order = _project_so(db, world.project, so_id=core_so.id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="50")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    decision = SOSupplyDecision(
        id=_uid(), company_id=world.company_id, project_sales_order_id=order.id,
        revision_no=1, state="active",
        line_snapshots=[{"line_no": 10, "project_line_id": line.id, "open_qty": "50"}],
        confirmed_by=world.eling, confirmed_at=None,
    )
    db.add(decision)
    db.commit()

    # The customer took more delivery than the snapshot knew about: open qty has moved.
    core_line.qty_delivered = Decimal("20")
    db.commit()

    response = client.get(f"{BASE}/sales-orders/{order.id}/supply")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["review_state"] == "needs_cs_review"
    assert body.get("decision", {}).get("challenged_reason")

    db.expire_all()
    assert db.get(SOSupplyDecision, decision.id).state == "challenged"


def test_review_states_for_reads_confirmed_when_an_active_decision_exists(api):
    """PLAN 5.3: review state reads `confirmed` iff the Stage 1B conditions hold AND an
    active decision exists, from the batched `review_states_for` the list route uses."""
    from app.models.project_so import SOSupplyDecision

    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    order = _project_so(db, world.project, so_id=core_so.id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    decision = SOSupplyDecision(
        id=_uid(), company_id=world.company_id, project_sales_order_id=order.id,
        revision_no=1, state="active",
        line_snapshots=[{"line_no": 10, "project_line_id": line.id}],
        confirmed_by=world.eling, confirmed_at=None,
    )
    db.add(decision)
    db.commit()

    from app.services.project_so_reconciliation_service import ProjectSOReconciliationService

    states = ProjectSOReconciliationService(db).review_states_for([order.id])
    assert states[str(order.id)]["review_state"] == "confirmed"


# --------------------------------------------------------------------------- borrow / donor


def test_borrow_without_a_reason_is_refused(api):
    """AC-B09/AC-C03: a Borrow component with a blank reason must fail confirmation."""
    client, world = api
    db = world.db
    other_wh = _warehouse(db, f"ZZT-OTH-{_suffix()}")
    _stock(db, world.product, other_wh, on_hand=100)
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="20")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    payload = {
        "lines": [
            _line_payload(
                line.id,
                borrow=[
                    {"source": "other_location", "warehouse_id": other_wh.id, "qty": "20", "reason": ""}
                ],
            )
        ]
    }
    response = client.post(f"{BASE}/sales-orders/{order.id}/confirm", json=payload)
    assert response.status_code == 422, response.text
    body = response.json()
    assert any(row["line_no"] == 10 for row in body["failing_lines"])


def test_cross_project_borrow_writes_an_accepted_claim_directly_with_no_requested_state(api):
    """AC-B10/AC-C08: cross-project Borrow is one action -- the confirming CS's own
    confirmation writes `allocation_claims` straight to `accepted`, actor-stamped, with
    `decided_at` set. No row is ever left `requested` on this path."""
    from app.services.project_service import register_project

    client, world = api
    db = world.db
    donor_wh = _warehouse(db, f"ZZT-DNR-{_suffix()}")
    _stock(db, world.product, donor_wh, on_hand=100)
    farah = _user(db, f"{MARKER} Farah")
    donor_project = register_project(
        db, company_id=world.company_id, actor_user_id=farah, developer_party_id=None,
        title=f"{MARKER} Seri Heights",
    )
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="40")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    payload = {
        "lines": [
            _line_payload(
                line.id,
                borrow=[
                    {
                        "source": "other_project",
                        "warehouse_id": donor_wh.id,
                        "donor_project_id": donor_project.id,
                        "qty": "40",
                        "reason": "Seri Heights has surplus this month.",
                    }
                ],
            )
        ]
    }
    response = client.post(f"{BASE}/sales-orders/{order.id}/confirm", json=payload)
    assert response.status_code == 200, response.text

    claims = (
        db.query(AllocationClaim)
        .filter(AllocationClaim.from_project_id == world.project.id)
        .all()
    )
    assert len(claims) == 1
    claim = claims[0]
    assert claim.state == CLAIM_ACCEPTED
    assert claim.requested_by == world.eling
    assert claim.decided_by == world.eling
    assert claim.decided_at is not None
    assert claim.reason == "Seri Heights has surplus this month."

    assert (
        db.query(AllocationClaim)
        .filter(AllocationClaim.from_project_id == world.project.id, AllocationClaim.state == CLAIM_REQUESTED)
        .count()
        == 0
    ), "no requested-state claim should ever exist on the confirmation path"


def test_a_borrow_that_leaves_the_donor_short_raises_an_order_inquiry_for_the_donor(api):
    """PLAN 13.11. The captain: "when borrowed, does it / should it trigger an order back
    via order inquiries? ... or we should order back only if the available quantity of the
    borrowed location is negative?"

    Only then. The donor here holds 100 and the book has already sold 90 of it, so its
    availability is 10 and a borrow of 20 opens a hole of 10 - and purchasing is told about
    the 10, at the DONOR's location, not the 20 that was taken.
    """
    from app.models.project_so import IV_BORROW_SHORTFALL, OrderInquiryRow

    client, world = api
    db = world.db
    donor_wh = _warehouse(db, f"ZZT-SHORT-{_suffix()}")
    _stock(db, world.product, donor_wh, on_hand=100)
    # The donor's own book: 90 of that 100 is already owed to somebody.
    theirs = _core_so(db, world.company_id)
    _core_line(db, theirs, world.product, donor_wh, qty_ordered="90")

    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="20")
    line = _project_line(db, order, line_no=20, product=world.product, core_line=core_line)
    db.commit()

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(
                    line.id,
                    borrow=[
                        {
                            "source": "other_location",
                            "warehouse_id": donor_wh.id,
                            "qty": "20",
                            "reason": "Their hand-over is in December.",
                        }
                    ],
                )
            ]
        },
    )
    assert response.status_code == 200, response.text
    # Nothing is BOUGHT for this line - it is fully borrowed - so the only row purchasing
    # gets is the hole the borrow opened.
    assert response.json()["inquiry_rows_created"] == 1

    rows = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.verb == IV_BORROW_SHORTFALL)
        .all()
    )
    assert len(rows) == 1
    row = rows[0]
    assert str(row.qty) in ("10", "10.0000")
    assert row.stock_location == donor_wh.warehouse_code
    assert row.state == "raised"
    assert row.so_line_id == line.id
    # The sentence purchasing reads: what was taken, for whom, and who it left short.
    assert "20" in row.note and donor_wh.warehouse_code in row.note
    assert "short by 10" in row.note
    assert order.provisional_ref in row.note


def test_a_borrow_a_donor_can_afford_raises_nothing(api):
    """A donor whose availability stays at or above zero needs nothing back. Borrowing from
    them is a plain transfer, and raising a buy for it would order stock nobody is short of.
    """
    from app.models.project_so import IV_BORROW_SHORTFALL, OrderInquiryRow

    client, world = api
    db = world.db
    donor_wh = _warehouse(db, f"ZZT-RICH-{_suffix()}")
    _stock(db, world.product, donor_wh, on_hand=100)

    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="20")
    line = _project_line(db, order, line_no=20, product=world.product, core_line=core_line)
    db.commit()

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(
                    line.id,
                    borrow=[
                        {
                            "source": "other_location",
                            "warehouse_id": donor_wh.id,
                            "qty": "20",
                            "reason": "They are holding far more than they will ship.",
                        }
                    ],
                )
            ]
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["inquiry_rows_created"] == 0
    assert (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.verb == IV_BORROW_SHORTFALL)
        .count()
        == 0
    )


def test_re_confirming_the_same_borrow_does_not_stack_a_second_shortfall_row(api):
    """A shortfall row is superseded like every other still-raised row, never doubled."""
    from app.models.project_so import IV_BORROW_SHORTFALL, OrderInquiryRow

    client, world = api
    db = world.db
    donor_wh = _warehouse(db, f"ZZT-SHORT-{_suffix()}")
    _stock(db, world.product, donor_wh, on_hand=100)
    theirs = _core_so(db, world.company_id)
    _core_line(db, theirs, world.product, donor_wh, qty_ordered="90")

    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="20")
    line = _project_line(db, order, line_no=20, product=world.product, core_line=core_line)
    db.commit()

    payload = {
        "lines": [
            _line_payload(
                line.id,
                borrow=[
                    {
                        "source": "other_location",
                        "warehouse_id": donor_wh.id,
                        "qty": "20",
                        "reason": "Their hand-over is in December.",
                    }
                ],
            )
        ]
    }
    assert client.post(f"{BASE}/sales-orders/{order.id}/confirm", json=payload).status_code == 200
    assert client.post(f"{BASE}/sales-orders/{order.id}/confirm", json=payload).status_code == 200

    rows = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.verb == IV_BORROW_SHORTFALL)
        .all()
    )
    assert [row.state for row in rows].count("raised") == 1
    assert len(rows) == 2, "the first is cancelled and kept, never edited in place"


# --------------------------------------------------------------------------- discontinued


def test_a_discontinued_buy_without_a_reason_is_refused(api):
    """AC-B11/AC-C03: Buy on a discontinued product needs a reason before it may confirm."""
    client, world = api
    db = world.db
    discontinued = _product(db, discontinued=True)
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, discontinued, world.own_wh, qty_ordered="15")
    line = _project_line(db, order, line_no=10, product=discontinued, core_line=core_line)
    db.commit()

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, buy_qty="15")]},
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert any(row["line_no"] == 10 for row in body["failing_lines"])


def test_a_discontinued_buy_with_a_reason_confirms(api):
    """The other half of AC-B11: the same line, with the reason supplied, confirms and its
    Buy residual reaches Purchasing without substitution."""
    client, world = api
    db = world.db
    discontinued = _product(db, discontinued=True)
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, discontinued, world.own_wh, qty_ordered="15")
    line = _project_line(db, order, line_no=10, product=discontinued, core_line=core_line)
    db.commit()

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(
                    line.id, buy_qty="15",
                    buy_reason="Customer committed; no substitute in the range.",
                )
            ]
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["inquiry_rows_created"] == 1


# --------------------------------------------------------------------------- authz


def test_confirmation_is_denied_without_the_edit_permission(api):
    """AC-C08: a view-only actor may read the proposal but may not confirm it."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.own_wh, on_hand=50)
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="50")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    from app.services.user_service import UserPermissionService

    original = UserPermissionService.check_user_has_permission
    try:
        UserPermissionService.check_user_has_permission = (
            lambda self, uid, slug: slug != EDIT
        )
        response = client.post(
            f"{BASE}/sales-orders/{order.id}/confirm",
            json={"lines": [_line_payload(line.id, reserve=[{"warehouse_id": world.own_wh.id, "qty": "50"}])]},
        )
        assert response.status_code == 403, response.text
    finally:
        UserPermissionService.check_user_has_permission = original


def test_a_cross_company_project_so_is_denied_without_a_leak():
    """AC-C08: a Sorento-scoped session confirming a Mocha-owned Project SO id gets a
    plain 404 -- never a 403 that would confirm the id exists in another company."""
    from app.models.base import company_scope
    from app.services.project_service import register_project

    with blank_session() as db:
        sorento_id = _sorento(db)
        other_id = _second_company(db)
        project_seed_service.run(db, company_id=sorento_id)
        project_seed_service.run(db, company_id=other_id)

        eling = _user(db, f"{MARKER} Eling")
        register_project(
            db, company_id=sorento_id, actor_user_id=eling, developer_party_id=None,
            title=f"{MARKER} Sorento Residences",
        )

        farah = _user(db, f"{MARKER} Farah")
        other_project = register_project(
            db, company_id=other_id, actor_user_id=farah, developer_party_id=None,
            title=f"{MARKER} Mocha Residences",
        )
        other_product = _product(db)
        other_wh = _warehouse(db, f"ZZT-OTHWH-{_suffix()}")
        other_order = _project_so(db, other_project)
        other_core_so = _core_so(db, other_id)
        other_core_line = _core_line(db, other_core_so, other_product, other_wh, qty_ordered="10")
        other_line = _project_line(
            db, other_order, line_no=10, product=other_product, core_line=other_core_line
        )
        db.commit()

        client, originals = _client(db, eling)
        try:
            with company_scope(db, frozenset({sorento_id})):
                response = client.post(
                    f"{BASE}/sales-orders/{other_order.id}/confirm",
                    json={"lines": [_line_payload(other_line.id, buy_qty="10")]},
                )
                assert response.status_code == 404, response.text
                assert "mocha" not in response.text.lower()
                assert other_order.id not in response.text

            # Confirmed here to make this test genuinely RED, not merely a coincidental
            # 404 off a route that does not exist at all yet: nothing was written for the
            # foreign order either, checked against the model this slice adds.
            from app.models.project_so import SOSupplyDecision

            assert (
                db.query(SOSupplyDecision)
                .filter(SOSupplyDecision.project_sales_order_id == other_order.id)
                .count()
                == 0
            )
        finally:
            _restore(originals)


# --------------------------------------------------------------------------- list filter


def test_the_fulfilment_planning_list_filters_by_the_confirmed_review_state(api):
    """Section 6: `GET /fulfilment-planning` `review_state` Literal gains `confirmed`."""
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    order = _project_so(db, world.project, so_id=core_so.id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    # The worklist row names the Project SO in `id` (`FulfilmentPlanningRow`, Stage 1B);
    # `project_sales_order_id` is the RECONCILIATION summary's spelling of the same thing.
    unconfirmed = client.get(f"{BASE}/fulfilment-planning?review_state=confirmed")
    assert unconfirmed.status_code == 200, unconfirmed.text
    assert order.id not in {row["id"] for row in unconfirmed.json()["data"]}

    needs_review = client.get(f"{BASE}/fulfilment-planning?review_state=needs_cs_review")
    assert needs_review.status_code == 200, needs_review.text
    assert order.id in {row["id"] for row in needs_review.json()["data"]}

    confirmed = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, buy_qty="10")]},
    )
    assert confirmed.status_code == 200, confirmed.text

    now_confirmed = client.get(f"{BASE}/fulfilment-planning?review_state=confirmed")
    assert now_confirmed.status_code == 200, now_confirmed.text
    assert order.id in {row["id"] for row in now_confirmed.json()["data"]}


# --------------------------------------------------------------- pool buckets per product


def test_two_products_sharing_one_pool_warehouse_never_share_a_reserve_bucket(api):
    """The pool ledger is per PRODUCT per pool warehouse (AC-B07, AC-B12).

    Product A has 40 free at the shared pool; product B has no stock anywhere. Keyed by
    warehouse alone, B's line would read A's remaining headroom as its own free stock:
    the proposal would offer B a Reserve out of a pile that holds none of B, and the
    confirm-time recheck would let that over-Reserve commit.
    """
    client, world = api
    db = world.db
    product_b = _product(db)
    _stock(db, world.product, world.pool_wh, on_hand=40)
    core_so = _core_so(db, world.company_id)
    core_line_a = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10")
    core_line_b = _core_line(db, core_so, product_b, world.own_wh, qty_ordered="15")
    order = _project_so(db, world.project, so_id=core_so.id)
    line_a = _project_line(db, order, line_no=10, product=world.product, core_line=core_line_a)
    line_b = _project_line(db, order, line_no=20, product=product_b, core_line=core_line_b)
    db.commit()

    proposal = client.get(f"{BASE}/sales-orders/{order.id}/supply")
    assert proposal.status_code == 200, proposal.text
    by_line = {row["line_no"]: row for row in proposal.json()["lines"]}
    kinds_b = {c["kind"]: Decimal(str(c["qty"])) for c in by_line[20]["components"]}
    assert kinds_b == {"buy": Decimal("15")}, (
        "product B holds nothing at the pool, so its whole open quantity is Buy; "
        f"proposed {by_line[20]['components']}"
    )
    kinds_a = {c["kind"]: Decimal(str(c["qty"])) for c in by_line[10]["components"]}
    assert kinds_a == {"reserve": Decimal("10")}

    payload = {
        "lines": [
            _line_payload(line_a.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "10"}]),
            _line_payload(line_b.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "15"}]),
        ]
    }
    refused = client.post(f"{BASE}/sales-orders/{order.id}/confirm", json=payload)
    assert refused.status_code in (409, 422), refused.text
    failing = refused.json().get("failing_lines") or []
    assert any(f["line_no"] == 20 for f in failing), refused.text

    from app.models.project_so import SOSupplyDecision

    assert (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id)
        .count()
        == 0
    ), "the refused confirmation must write nothing"


def test_a_negative_component_beside_a_positive_one_is_refused_not_netted(api):
    """A crafted payload of reserve [-50, +100] sums to 50 and balances, but subtracting
    the negative row would INFLATE the capacity ledger and the +100 would commit against
    50 free. Every individual component is checked, not the per-kind totals."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.own_wh, on_hand=50)
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="50")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    payload = {
        "lines": [
            _line_payload(
                line.id,
                reserve=[
                    {"warehouse_id": world.own_wh.id, "qty": "-50"},
                    {"warehouse_id": world.own_wh.id, "qty": "100"},
                ],
            ),
        ]
    }
    refused = client.post(f"{BASE}/sales-orders/{order.id}/confirm", json=payload)
    assert refused.status_code in (409, 422), refused.text
    failing = refused.json().get("failing_lines") or []
    assert any("negative" in (f.get("reason") or "").lower() for f in failing), refused.text

    from app.models.project_so import SOSupplyDecision, SOLineAllocation

    assert db.query(SOSupplyDecision).filter(
        SOSupplyDecision.project_sales_order_id == order.id
    ).count() == 0
    assert db.query(SOLineAllocation).filter(
        SOLineAllocation.so_line_id == line.id
    ).count() == 0


def test_a_line_named_twice_in_the_payload_is_refused_not_promised_twice(api):
    """Two payload entries for one line would each be offered the line's undepleted share
    and each write a full set of allocations: double the promise against the same stock."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.own_wh, on_hand=100)
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="50")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    entry = _line_payload(line.id, reserve=[{"warehouse_id": world.own_wh.id, "qty": "50"}])
    refused = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm", json={"lines": [entry, entry]}
    )
    assert refused.status_code in (409, 422), refused.text
    failing = refused.json().get("failing_lines") or []
    assert any("twice" in (f.get("reason") or "").lower() for f in failing), refused.text

    from app.models.project_so import SOSupplyDecision

    assert db.query(SOSupplyDecision).filter(
        SOSupplyDecision.project_sales_order_id == order.id
    ).count() == 0


# ------------------------------------------------- order back on a POOL reserve (13.11)


def _behind_ours(core_so):
    """A core sales order the queue ranks BEHIND every `ZZT-PSO-*` line of this file.

    With no policy row the active weights name only `po_document_sequence`, which no sales-
    order line carries, so every demand row scores 0.0 and the pile's queue falls through to
    the sales-order number. `ZZT-ZCORE-*` sorts after `ZZT-PSO-*`; the default `ZZT-CORE-*`
    sorts before it and would put this order AHEAD of ours.
    """
    core_so.so_number = f"ZZT-ZCORE-{_suffix()}"
    return core_so


def test_a_pool_reserve_asking_more_than_the_pools_available_position_is_refused(api):
    """Ladder v2 (`PLAN-demo-followups-19aug-ladder-v2.md` section E rule 2): pool capacity
    is now `max(min(free, available), 0)` for EVERY pool, not only a hot-selling one - so a
    SINGLE line can no longer oversell the pool through Reserve at all; the recheck refuses
    the ask before it is ever written, which is the whole reason the old order-back-on-
    oversell case this test used to pin (captain, 19 August 2026, "if available quantity is
    negative ... we must have an order back") can no longer occur through this rung -
    ladder v2's `group_borrow` (see `test_a_group_borrow_raises_its_own_order_back` in
    `tests/scm/test_project_supply_service_ladder_v2.py`) is where an order-back now comes
    from instead.

    The pool holds 100 with 90 of it already owed to its own book (ranked behind our line),
    leaving `available` at 10 - and 20 is refused, not silently capped.
    """
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=100)
    # The pool's OWN book: 90 of that 100 is already owed there, ranked behind our line.
    theirs = _behind_ours(_core_so(db, world.company_id))
    _core_line(db, theirs, world.product, world.pool_wh, qty_ordered="90")

    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="20")
    line = _project_line(db, order, line_no=20, product=world.product, core_line=core_line)
    db.commit()

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(
                    line.id,
                    reserve=[{"warehouse_id": world.pool_wh.id, "qty": "20"}],
                )
            ]
        },
    )
    assert response.status_code in (409, 422), response.text
    failing = response.json()["failing_lines"]
    assert failing[0]["line_no"] == 20
    assert "10" in failing[0]["reason"]


def test_a_pool_reserve_up_to_the_pools_available_position_succeeds_and_raises_no_shortfall(api):
    """The boundary of the same rule: asking for EXACTLY the pool's available position (10)
    is allowed - the capacity formula caps it, so `available` lands at 0, never negative,
    and no order-back is raised."""
    from app.models.project_so import IV_BORROW_SHORTFALL, OrderInquiryRow

    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=100)
    theirs = _behind_ours(_core_so(db, world.company_id))
    _core_line(db, theirs, world.product, world.pool_wh, qty_ordered="90")

    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10")
    line = _project_line(db, order, line_no=20, product=world.product, core_line=core_line)
    db.commit()

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(
                    line.id,
                    reserve=[{"warehouse_id": world.pool_wh.id, "qty": "10"}],
                )
            ]
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["inquiry_rows_created"] == 0
    assert (
        db.query(OrderInquiryRow).filter(OrderInquiryRow.verb == IV_BORROW_SHORTFALL).count()
        == 0
    )


def test_a_pool_reserve_the_pool_can_afford_raises_nothing(api):
    """A pool still covering its own book is not short of anything."""
    from app.models.project_so import IV_BORROW_SHORTFALL, OrderInquiryRow

    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=100)

    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="20")
    line = _project_line(db, order, line_no=20, product=world.product, core_line=core_line)
    db.commit()

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(
                    line.id,
                    reserve=[{"warehouse_id": world.pool_wh.id, "qty": "20"}],
                )
            ]
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["inquiry_rows_created"] == 0
    assert (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.verb == IV_BORROW_SHORTFALL)
        .count()
        == 0
    )


def test_an_own_location_reserve_is_refused_ladder_v2_removed_that_rung(api):
    """Ladder v2, section E rule 7 (`PLAN-demo-followups-19aug-ladder-v2.md`): "the
    own-location Reserve rung is REMOVED" - stock sitting at a line's own location is
    committed to whichever customer it is queued for, and the only way another line
    reaches it is a group borrow, with an order-back. A Reserve submission naming the
    line's OWN warehouse is refused outright, never silently accepted."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.own_wh, on_hand=20)
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="20")
    line = _project_line(db, order, line_no=20, product=world.product, core_line=core_line)
    db.commit()

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(
                    line.id,
                    reserve=[{"warehouse_id": world.own_wh.id, "qty": "20"}],
                )
            ]
        },
    )
    assert response.status_code == 422, response.text
    failing = response.json()["failing_lines"]
    assert failing[0]["line_no"] == 20
    assert world.own_wh.warehouse_code in failing[0]["reason"]


def test_a_pool_reserve_across_two_lines_of_one_confirmation_shares_the_pools_available_capacity(api):
    """S7 (`documentation/plans/scm/PLAN-demo-followups-19aug-ladder-v2.md`, review fixes):
    the pool's SIGNED availability (`max(min(free, available), 0)`, section E rule 2) is a
    RUNNING LEDGER across every line of one confirmation, not judged per line against the
    same live figure read afresh.

    100 on hand, 90 owed to the pool's own book leaves `available` at 10. Before this fix,
    each line's own ask (6) cleared that cap independently - `_check_line` rebuilt its
    capacity dict from live figures on every line and only ever carried the line's OWN
    site pool forward - so the confirmation wrote both Reserves and oversold the pool by 2,
    caught only afterwards by an order-back. Now the second line is refused outright: the
    pool has nothing left to give it, so the confirmation writes nothing at all (AC-C01).
    """
    from app.models.project_so import SOSupplyDecision

    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=100)
    theirs = _behind_ours(_core_so(db, world.company_id))
    _core_line(db, theirs, world.product, world.pool_wh, qty_ordered="90")

    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    first = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="6")
    second = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="6")
    line_one = _project_line(db, order, line_no=1, product=world.product, core_line=first)
    line_two = _project_line(db, order, line_no=2, product=world.product, core_line=second)
    db.commit()

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(
                    line_one.id,
                    reserve=[{"warehouse_id": world.pool_wh.id, "qty": "6"}],
                ),
                _line_payload(
                    line_two.id,
                    reserve=[{"warehouse_id": world.pool_wh.id, "qty": "6"}],
                ),
            ]
        },
    )
    assert response.status_code == 409, response.text
    body = response.json()
    failing = {row["line_no"] for row in body["failing_lines"]}
    assert failing == {2}, body
    assert "4" in body["failing_lines"][0]["reason"]

    # Atomic (AC-C01): the second line's refusal rolls the whole confirmation back, so
    # the first line's own Reserve never lands either.
    assert (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id)
        .first()
        is None
    )


# --------------------------------------------------- the donor's availability nets holds


def test_a_donor_hole_counts_what_other_confirmed_borrows_already_hold_there(api):
    """F4(a). A confirmed borrow writes a hold that the donor's `on hand - SO + SPO`
    knows nothing about (a borrow is an allocation, not a sales-order line at the donor),
    so a second borrower judged on the triple alone sees stock the first one has already
    taken. Donor: 100 on hand, 60 sold on its own book, so 40 available. Order B borrows
    30 (fine, 10 left). Order A then borrows 30: the hole is 20, not nothing."""
    from app.models.project_so import IV_BORROW_SHORTFALL, OrderInquiryRow

    client, world = api
    db = world.db
    donor_wh = _warehouse(db, f"ZZT-TWICE-{_suffix()}")
    _stock(db, world.product, donor_wh, on_hand=100)
    theirs = _core_so(db, world.company_id)
    _core_line(db, theirs, world.product, donor_wh, qty_ordered="60")

    def borrower():
        order = _project_so(db, world.project)
        core_so = _core_so(db, world.company_id)
        core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="30")
        line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
        db.commit()
        return order, line

    order_b, line_b = borrower()
    order_a, line_a = borrower()

    def borrow(order, line):
        return client.post(
            f"{BASE}/sales-orders/{order.id}/confirm",
            json={
                "lines": [
                    _line_payload(
                        line.id,
                        borrow=[
                            {
                                "source": "other_location",
                                "warehouse_id": donor_wh.id,
                                "qty": "30",
                                "reason": "Their hand-over is in December.",
                            }
                        ],
                    )
                ]
            },
        )

    first = borrow(order_b, line_b)
    assert first.status_code == 200, first.text
    assert first.json()["inquiry_rows_created"] == 0, "40 available, 30 taken: no hole"

    second = borrow(order_a, line_a)
    assert second.status_code == 200, second.text
    assert second.json()["inquiry_rows_created"] == 1

    rows = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.verb == IV_BORROW_SHORTFALL)
        .all()
    )
    assert len(rows) == 1
    assert rows[0].so_line_id == line_a.id
    assert str(rows[0].qty) in ("20", "20.0000")
    assert "short by 20" in rows[0].note


def test_a_dealer_hot_selling_line_reserving_the_pool_still_opens_no_hole_when_it_fits(api):
    """F4(b), re-expressed for ladder v2 (19 August 2026 follow-up, section E rule 7):
    own-location Reserve is GONE - a dealer hot-selling line's own 10 units at its own
    location are simply not offered by this ladder at all any more (dealer-hot also
    excludes the pool), so the whole 20 is bought. Purchasing is told about the 20, and
    about no hole - a Buy is never a donor's hole."""
    from app.models.project_so import IV_BORROW_SHORTFALL, IV_ORDER, OrderInquiryRow

    client, world = api
    db = world.db
    _classification(db, world.product, world.pool_wh, abc_class_retail="A")
    _stock(db, world.product, world.own_wh, on_hand=10)

    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="20")
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, buy_qty="20")]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["inquiry_rows_created"] == 1, "the Buy, and nothing else"

    rows = db.query(OrderInquiryRow).all()
    assert [row.verb for row in rows] == [IV_ORDER]
    assert not [row for row in rows if row.verb == IV_BORROW_SHORTFALL]


def test_a_dealer_hot_selling_line_may_not_borrow_its_own_location_as_free_stock(api):
    """Ladder v2 (section E rule 7): naming the line's OWN location as a plain free-stock
    Borrow source is refused - own-location stock is never Reserve-eligible any more
    either, so the only way to reach it is a GROUP BORROW naming the donor SO line, never
    a bare `other_location` ask."""
    client, world = api
    db = world.db
    _classification(db, world.product, world.pool_wh, abc_class_retail="A")
    _stock(db, world.product, world.own_wh, on_hand=10)

    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="20")
    line = _project_line(db, order, line_no=1, product=world.product, core_line=core_line)
    db.commit()

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(
                    line.id,
                    borrow=[
                        {
                            "source": "other_location",
                            "warehouse_id": world.own_wh.id,
                            "qty": "10",
                            "reason": "It is our own stock; the pool has none.",
                        }
                    ],
                    buy_qty="10",
                )
            ]
        },
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert any(
        "own location" in (row.get("reason") or "")
        for row in body["failing_lines"]
    )


# ---------------------------------------------- a placed shortfall is not raised again


def test_a_shortfall_purchasing_already_placed_is_netted_off_the_next_revision(api):
    """F5. Revision 1 opens a hole of 10 at the donor and purchasing actions it. A re-confirm
    of the same hole raises nothing new; a re-confirm that widens the hole to 15 raises only
    the 5 still outstanding - the same rule the ORDER rows already follow, because placed
    supply is in the ledger and this service does not get to ask for it twice."""
    from app.models.project_so import (
        INQUIRY_ACTIONED,
        IV_BORROW_SHORTFALL,
        OrderInquiryRow,
    )

    client, world = api
    db = world.db
    donor_wh = _warehouse(db, f"ZZT-PLACED-{_suffix()}")
    _stock(db, world.product, donor_wh, on_hand=100)
    theirs = _core_so(db, world.company_id)
    _core_line(db, theirs, world.product, donor_wh, qty_ordered="90")

    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="25")
    line = _project_line(db, order, line_no=20, product=world.product, core_line=core_line)
    db.commit()

    def confirm(borrow_qty, buy_qty):
        return client.post(
            f"{BASE}/sales-orders/{order.id}/confirm",
            json={
                "lines": [
                    _line_payload(
                        line.id,
                        borrow=[
                            {
                                "source": "other_location",
                                "warehouse_id": donor_wh.id,
                                "qty": borrow_qty,
                                "reason": "Their hand-over is in December.",
                            }
                        ],
                        buy_qty=buy_qty,
                    )
                ]
            },
        )

    def shortfall_rows():
        return (
            db.query(OrderInquiryRow)
            .filter(OrderInquiryRow.verb == IV_BORROW_SHORTFALL)
            .order_by(OrderInquiryRow.created_at.asc())
            .all()
        )

    # Revision 1: 10 available, 20 borrowed, hole of 10. Purchasing places it.
    assert confirm("20", "5").status_code == 200
    rows = shortfall_rows()
    assert len(rows) == 1 and str(rows[0].qty) in ("10", "10.0000")
    rows[0].state = INQUIRY_ACTIONED
    db.commit()

    # Revision 2, the same hole: nothing outstanding, so nothing new.
    assert confirm("20", "5").status_code == 200
    db.expire_all()
    rows = shortfall_rows()
    assert [row.state for row in rows] == [INQUIRY_ACTIONED]

    # Revision 3 widens the hole to 15: only the 5 not yet placed is raised.
    assert confirm("25", "0").status_code == 200
    db.expire_all()
    rows = shortfall_rows()
    assert [row.state for row in rows] == [INQUIRY_ACTIONED, "raised"]
    assert str(rows[1].qty) in ("5", "5.0000")


# ------------------------------------------------------- carried holds (defect A)
#
# PLAN-so-book-diff-replanning.md section 10, defect A: a re-confirm names every covered
# line verbatim (there is no un-decide verb), and `_facts_for` un-nets a NAMED line's own
# hold so the composition can be re-judged. That un-netting used to put the WHOLE
# resubmitted quantity back in the queue, so a component this order already held could
# lose to demand that only showed up after the hold was taken - "BRW has nothing free for
# this line now" against stock the order itself was still sitting on. `_check_line` now
# credits back what this order's own active (or just-superseded) revision already held for
# that exact (line, kind, location[, donor]) before checking the rest against free stock.


def test_re_confirming_an_unchanged_reserve_survives_a_rival_taking_the_rest_of_the_location(api):
    """(a) Reserve 10 at W holds it. Something else then claims every unit of W that was
    freed by un-netting this order's own hold for the recheck - simulating a rival that
    only appeared after revision 1 was confirmed. Resubmitting the SAME 10 is not a new
    ask, so it must not be refused for "nothing free", and the hold must still read 10."""
    client, world = api
    db = world.db
    stock = _stock(db, world.product, world.pool_wh, on_hand=10)
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    first = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "10"}])]},
    )
    assert first.status_code == 200, first.text
    assert first.json()["revision_no"] == 1

    # A rival claims the location dry - everything this order's own un-netted hold would
    # otherwise have shown as free.
    stock.quantity_reserved = 10
    db.commit()

    second = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "10"}])]},
    )
    assert second.status_code == 200, second.text
    assert second.json()["revision_no"] == 2

    from app.models.project_so import SOLineAllocation, SOSupplyDecision

    active = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id, SOSupplyDecision.state == "active")
        .one()
    )
    allocations = (
        db.query(SOLineAllocation)
        .filter(SOLineAllocation.decision_id == active.id, SOLineAllocation.so_line_id == line.id)
        .all()
    )
    assert len(allocations) == 1
    assert allocations[0].qty == Decimal("10")


def test_re_confirming_a_larger_reserve_only_the_increase_competes_and_is_named_in_the_refusal(api):
    """(b) Revision 1 holds Reserve 10 of an open qty of 12 (the other 2 bought). The
    location then has only 1 unit free for anyone beyond this order's own carried 10.
    Asking for 12 (an increase of 2) is refused - but only the 2 is checked and named, not
    the 12 the order is resubmitting."""
    client, world = api
    db = world.db
    stock = _stock(db, world.product, world.pool_wh, on_hand=10)
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="12")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    first = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(
                    line.id,
                    reserve=[{"warehouse_id": world.pool_wh.id, "qty": "10"}],
                    buy_qty="2",
                )
            ]
        },
    )
    assert first.status_code == 200, first.text

    # Only 1 unit is free beyond this order's own carried 10 - not enough for the 2-unit
    # increase.
    stock.quantity_reserved = 9
    db.commit()

    second = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(
                    line.id,
                    reserve=[{"warehouse_id": world.pool_wh.id, "qty": "12"}],
                )
            ]
        },
    )
    assert second.status_code in (409, 422), second.text
    body = second.json()
    failing = body["failing_lines"]
    assert len(failing) == 1 and failing[0]["line_no"] == 10
    # Quote the exact phrase `_check_line` composes (`f"{warehouse} now has {room}
    # free for this line, and {ask} was asked for."` in project_supply_service.py)
    # rather than a bare digit search: a bare "12" (the whole resubmitted qty, which
    # must NOT be named) is a substring a random warehouse code could also contain
    # (`ZZT-BRW-712c`), which is exactly how this assertion flaked.
    assert "and 2 was asked for" in failing[0]["reason"]
    assert "and 12 was asked for" not in failing[0]["reason"]

    from app.models.project_so import SOSupplyDecision

    decisions = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id)
        .all()
    )
    assert len(decisions) == 1 and decisions[0].revision_no == 1  # nothing written


def test_re_confirming_the_reserve_at_a_different_location_competes_fully(api):
    """(c) Moving an already-held Reserve from one pool to a DIFFERENT (empty) pool is a
    real new ask there - the carried credit is keyed by (line, kind, WAREHOUSE), so it
    carries nothing to a location this order never held, and it is refused for nothing
    being free exactly as an ordinary first ask would be.

    A second, unrelated site pool - ladder v2 reaches every active pool (section E rule
    2), not only this line's own, so any other pool is a real candidate to move to.
    """
    client, world = api
    db = world.db
    other_pool = _warehouse(db, f"ZZT-OTHERPOOL-{_suffix()}")
    other_owner = _warehouse(db, f"ZZT-OTHEROWN-{_suffix()}", pool_warehouse_id=other_pool.id)
    _stock(db, world.product, world.pool_wh, on_hand=10)
    # `other_pool` has no stock at all.
    order = _project_so(db, world.project)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    first = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "10"}])]},
    )
    assert first.status_code == 200, first.text

    second = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line.id, reserve=[{"warehouse_id": other_pool.id, "qty": "10"}])]},
    )
    assert second.status_code in (409, 422), second.text
    body = second.json()
    assert any(row["line_no"] == 10 for row in body["failing_lines"])

    from app.models.project_so import SOSupplyDecision

    decisions = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id)
        .all()
    )
    assert len(decisions) == 1 and decisions[0].revision_no == 1  # nothing written
