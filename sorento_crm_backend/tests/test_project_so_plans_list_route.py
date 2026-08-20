"""GET /project-sales/plans (PLAN-demo-followups-19aug-ladder-v2 D1, workstream D1).

Contract in `app/services/project_supply_service.py` (`list_decisions`, `_serialize_plan_row`,
`_plan_components_summary`) and `app/schemas/project_supply.py::PlanRow`: one row per
`so_supply_decisions` revision, cross-order, with the SO number, agent code, revision, a
"Reserve N · Buy M" components summary built from `line_snapshots`, and who decided it.

A pure read - the decision rows are constructed directly here rather than driven through
`POST .../confirm`, since `list_decisions` only ever reads what is already stored.

Postgres via `tests/_pg_fixture.py::blank_session`, never sqlite. Every test seeds its own
full chain (company, project, core sales order + customer + agent, project SO, project line,
decision) rather than borrowing an existing row, per PRINCIPLES.md and the CI-is-empty lesson
in this repo's CLAUDE.md.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.order import Customer, SalesOrder
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.inventory import Warehouse
from app.models.project_so import (
    DECISION_ACTIVE,
    DECISION_SUPERSEDED,
    SO_STATUS_PUBLISHED,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
    SOSupplyDecision,
)
from app.models.sales_agent import SalesAgent
from app.models.user import User
from app.services import project_seed_service

from ._pg_fixture import blank_session

MARKER = "zzt-plans-list"
BASE = "/api/v1/project-sales"
VIEW = "projects.projects.view"
EDIT = "projects.projects.edit"


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
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:6]}", uom_name="Set")
    category = ProductCategory(
        id=_uid(), category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} cat"
    )
    db.add_all([uom, category])
    db.flush()
    row = Product(
        id=_uid(), product_code=f"ZZT-{_uid()[:8]}", product_name=f"{MARKER} Basin",
        category_id=category.id, base_uom_id=uom.id, list_price=Decimal("120.00"),
    )
    db.add(row)
    db.flush()
    return row


def _warehouse(db) -> Warehouse:
    row = Warehouse(
        id=_uid(), warehouse_code=f"ZZT-{_uid()[:6]}", warehouse_name="ZZT WH",
        location="ZZT", is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def _customer(db, name: str) -> Customer:
    row = Customer(id=_uid(), customer_code=f"ZZT-{_uid()[:8]}", customer_name=name)
    db.add(row)
    db.flush()
    return row


def _agent(db, code: str) -> SalesAgent:
    row = SalesAgent(id=_uid(), sales_agent=code, person_label=f"{MARKER} {code}")
    db.add(row)
    db.flush()
    return row


def _core_so(db, company_id: str, *, customer=None, agent=None, so_number=None) -> SalesOrder:
    row = SalesOrder(
        id=_uid(),
        company_id=company_id,
        so_number=so_number or f"ZZT-CORE-{_uid()[:8]}",
        status="open",
        demand_class="project",
        customer_id=customer.id if customer else None,
        sales_agent_id=agent.id if agent else None,
    )
    db.add(row)
    db.flush()
    return row


def _project_so(db, project, *, so_id=None) -> ProjectSalesOrder:
    row = ProjectSalesOrder(
        id=_uid(), company_id=project.company_id, project_id=project.id,
        provisional_ref=f"ZZT-PSO-{_uid()[:8]}", area_group="TOWER",
        status=SO_STATUS_PUBLISHED, so_id=so_id,
    )
    db.add(row)
    db.flush()
    return row


def _project_line(db, order, product, *, line_no=10) -> ProjectSalesOrderLine:
    row = ProjectSalesOrderLine(
        id=_uid(), company_id=order.company_id, project_sales_order_id=order.id,
        line_no=line_no, product_id=product.id, description=f"{MARKER} line {line_no}",
        qty=Decimal("10"), uom="SET", unit_price=Decimal("120.00"), amount=Decimal("1200.00"),
    )
    db.add(row)
    db.flush()
    return row


def _decision(
    db, order, *, revision_no, state, decided_by, snapshots, confirmed_at=None,
) -> SOSupplyDecision:
    row = SOSupplyDecision(
        id=_uid(), company_id=order.company_id, project_sales_order_id=order.id,
        revision_no=revision_no, state=state, line_snapshots=snapshots,
        confirmed_by=decided_by,
        confirmed_at=confirmed_at or datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(row)
    db.flush()
    return row


def _client(db, user_id: str, permissions):
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
    granted = list(permissions)
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: slug in granted
    UserPermissionService.get_user_permission_slugs = lambda self, uid: list(granted)
    return TestClient(app), originals


def _restore(originals) -> None:
    from app.main import app
    from app.services.user_service import UserPermissionService

    UserPermissionService.check_user_has_permission = originals[0]
    UserPermissionService.get_user_permission_slugs = originals[1]
    app.dependency_overrides.clear()


class _World:
    def __init__(self, db, company_id, project, product):
        self.db = db
        self.company_id = company_id
        self.project = project
        self.product = product


@pytest.fixture()
def world():
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
        db.flush()
        db.commit()
        with company_scope(db, frozenset({company_id})):
            yield _World(db, company_id, project, product)


# --------------------------------------------------------------------------- happy path


def test_the_plans_page_lists_an_active_decision_with_its_summary(world):
    db = world.db
    farah = _user(db, f"{MARKER} Farah")
    agent = _agent(db, f"ZZT-AGT-{_uid()[:4]}")
    customer = _customer(db, f"{MARKER} Buyer Sdn Bhd")
    core = _core_so(db, world.company_id, customer=customer, agent=agent)
    order = _project_so(db, world.project, so_id=core.id)
    line1 = _project_line(db, order, world.product, line_no=10)
    line2 = _project_line(db, order, world.product, line_no=20)
    decision = _decision(
        db, order, revision_no=1, state=DECISION_ACTIVE, decided_by=farah,
        snapshots=[
            {
                "line_no": 10, "project_line_id": line1.id,
                "components": [{"kind": "reserve", "qty": "120"}],
            },
            {
                "line_no": 20, "project_line_id": line2.id,
                "components": [
                    {"kind": "reserve", "qty": "93"},
                    {"kind": "buy", "qty": "45"},
                ],
            },
        ],
    )
    db.commit()

    client, originals = _client(db, farah, [VIEW])
    try:
        response = client.get(f"{BASE}/plans")
        assert response.status_code == 200, response.text
        rows = {row["project_sales_order_id"]: row for row in response.json()["data"]}
        assert order.id in rows
        row = rows[order.id]
        assert row["so_number"] == core.so_number
        assert row["agent_code"] == agent.sales_agent
        assert row["revision_no"] == 1
        assert row["state"] == "active"
        assert row["decided_by_name"] == f"{MARKER} Farah"
        assert row["line_count"] == 2
        assert row["components_summary"] == "Reserve 213 · Buy 45"
        assert row["customer_name"] == customer.customer_name
    finally:
        _restore(originals)


# --------------------------------------------------------------------------- state filter


def test_the_state_filter_separates_active_from_superseded(world):
    db = world.db
    farah = _user(db, f"{MARKER} Farah")
    order_a = _project_so(db, world.project)
    order_b = _project_so(db, world.project)
    line_a = _project_line(db, order_a, world.product, line_no=10)
    line_b = _project_line(db, order_b, world.product, line_no=10)
    active = _decision(
        db, order_a, revision_no=1, state=DECISION_ACTIVE, decided_by=farah,
        snapshots=[{"line_no": 10, "project_line_id": line_a.id, "components": []}],
    )
    superseded = _decision(
        db, order_b, revision_no=1, state=DECISION_SUPERSEDED, decided_by=farah,
        snapshots=[{"line_no": 10, "project_line_id": line_b.id, "components": []}],
    )
    db.commit()

    client, originals = _client(db, farah, [VIEW])
    try:
        default_state = client.get(f"{BASE}/plans")
        assert default_state.status_code == 200, default_state.text
        default_ids = {row["project_sales_order_id"] for row in default_state.json()["data"]}
        assert order_a.id in default_ids
        assert order_b.id not in default_ids

        superseded_only = client.get(f"{BASE}/plans", params={"state": "superseded"})
        assert superseded_only.status_code == 200, superseded_only.text
        superseded_ids = {
            row["project_sales_order_id"] for row in superseded_only.json()["data"]
        }
        assert order_b.id in superseded_ids
        assert order_a.id not in superseded_ids
    finally:
        _restore(originals)


# --------------------------------------------------------------------------- free text query


def test_querying_by_so_number_narrows_to_that_order(world):
    db = world.db
    farah = _user(db, f"{MARKER} Farah")
    core_1 = _core_so(db, world.company_id, so_number=f"ZZT-FINDME-{_uid()[:6]}")
    core_2 = _core_so(db, world.company_id, so_number=f"ZZT-OTHER-{_uid()[:6]}")
    order_1 = _project_so(db, world.project, so_id=core_1.id)
    order_2 = _project_so(db, world.project, so_id=core_2.id)
    line_1 = _project_line(db, order_1, world.product, line_no=10)
    line_2 = _project_line(db, order_2, world.product, line_no=10)
    _decision(
        db, order_1, revision_no=1, state=DECISION_ACTIVE, decided_by=farah,
        snapshots=[{"line_no": 10, "project_line_id": line_1.id, "components": []}],
    )
    _decision(
        db, order_2, revision_no=1, state=DECISION_ACTIVE, decided_by=farah,
        snapshots=[{"line_no": 10, "project_line_id": line_2.id, "components": []}],
    )
    db.commit()

    client, originals = _client(db, farah, [VIEW])
    try:
        response = client.get(f"{BASE}/plans", params={"query": core_1.so_number})
        assert response.status_code == 200, response.text
        so_numbers = {row["so_number"] for row in response.json()["data"]}
        assert so_numbers == {core_1.so_number}
    finally:
        _restore(originals)


# --------------------------------------------------------------------------- auth denial


def test_listing_plans_is_denied_without_the_view_permission(world):
    db = world.db
    farah = _user(db, f"{MARKER} Farah")
    order = _project_so(db, world.project)
    line = _project_line(db, order, world.product, line_no=10)
    _decision(
        db, order, revision_no=1, state=DECISION_ACTIVE, decided_by=farah,
        snapshots=[{"line_no": 10, "project_line_id": line.id, "components": []}],
    )
    db.commit()

    client, originals = _client(db, farah, [])
    try:
        response = client.get(f"{BASE}/plans")
        assert response.status_code == 403, response.text
    finally:
        _restore(originals)


def test_listing_plans_401s_without_a_principal(world):
    from app.dependencies import get_current_user_or_api_key
    from app.main import app

    db = world.db
    farah = _user(db, f"{MARKER} Farah")
    db.commit()

    client, originals = _client(db, farah, [VIEW])
    try:
        from fastapi import HTTPException

        def _deny():
            raise HTTPException(status_code=401, detail="Not authenticated")

        app.dependency_overrides[get_current_user_or_api_key] = _deny
        response = client.get(f"{BASE}/plans")
        assert response.status_code == 401, response.text
    finally:
        _restore(originals)
