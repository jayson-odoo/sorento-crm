"""Stage 1B reconciliation ROUTES (STAGE1B-scm-front-planning-reconciliation.md section 3,
UAC-scm-front-planning.md AC-A01..AC-A04). TEST-FIRST: written before the routes exist, so
every test here is expected to fail collection or return 404 for the whole module until the
coder adds `GET /project-sales/fulfilment-planning`,
`GET /project-sales/sales-orders/{pso_id}/reconciliation` and
`POST /project-sales/sales-orders/{pso_id}/reconcile`, and adds `review_state` +
`exception_count` to the existing project SO list row and detail.

Route pattern (TestClient + dependency_overrides + permission monkeypatch) copied from
``tests/test_project_so_worksheet.py`` and ``tests/test_project_order_inquiry_routes.py``.
Reads need ``projects.projects.view``; the rerun needs ``projects.projects.edit`` -- the
same two grants the sibling sales-order routes already use.

Postgres, blank scratch schema via ``tests/_pg_fixture.py::blank_session``, rolled back at
teardown. Every FK target is seeded here.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.project_so import (
    SO_STATUS_PUBLISHED,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from app.models.order import SalesOrder, SalesOrderLine
from app.models.user import User
from app.services import project_seed_service

from ._pg_fixture import blank_session

MARKER = "zzt-so-recon-route"
BASE = "/api/v1/project-sales"
VIEW = "projects.projects.view"
EDIT = "projects.projects.edit"

D1 = date(2027, 1, 7)

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


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
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:6]}", uom_name="Unit")
    category = ProductCategory(
        id=_uid(), category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} cat"
    )
    db.add_all([uom, category])
    db.flush()
    row = Product(
        id=_uid(),
        product_code=f"ZZT-{_uid()[:8]}",
        product_name=f"{MARKER} product",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
    )
    db.add(row)
    db.flush()
    return row


def _project(db, company_id: str, owner: str):
    from app.services.project_service import register_project

    return register_project(
        db,
        company_id=company_id,
        actor_user_id=owner,
        developer_party_id=None,
        title=f"{MARKER} Tuju Residences {_uid()[:12]}",
    )


def _core_order(db, *, so_number: str) -> SalesOrder:
    row = SalesOrder(id=_uid(), so_number=so_number, status="open")
    db.add(row)
    db.flush()
    return row


def _core_line(db, order: SalesOrder, product: Product, *, required_date: date) -> SalesOrderLine:
    row = SalesOrderLine(
        id=_uid(),
        sales_order_id=order.id,
        product_id=product.id,
        qty_ordered=Decimal("10"),
        qty_delivered=Decimal("0"),
        required_date=required_date,
    )
    if order.company_id is not None:
        row.company_id = order.company_id
    db.add(row)
    db.flush()
    return row


def _project_order(
    db,
    project,
    *,
    autocount_doc_no: str | None = None,
    so_id: str | None = None,
    area_group: str = "TOWER",
) -> ProjectSalesOrder:
    row = ProjectSalesOrder(
        id=_uid(),
        company_id=project.company_id,
        project_id=project.id,
        area_group=area_group,
        provisional_ref=f"ZZT-PSO-{_uid()[:8]}",
        autocount_doc_no=autocount_doc_no,
        so_id=so_id,
        status=SO_STATUS_PUBLISHED,
        published_at=datetime.utcnow(),
        grouping_origin="area",
    )
    db.add(row)
    db.flush()
    return row


def _project_line(
    db, order: ProjectSalesOrder, product: Product, *, line_no: int, delivery_date: date
) -> ProjectSalesOrderLine:
    row = ProjectSalesOrderLine(
        id=_uid(),
        company_id=order.company_id,
        project_sales_order_id=order.id,
        line_no=line_no,
        product_id=product.id,
        description=f"{MARKER} line {line_no}",
        qty=Decimal("10"),
        uom="UNIT",
        unit_price=Decimal("10.00"),
        amount=Decimal("100.00"),
        delivery_date=delivery_date,
    )
    db.add(row)
    db.flush()
    return row


def _linked_scenario(db, project):
    """A Project SO whose header AND single line resolve cleanly: needs_cs_review."""
    product = _product(db)
    core_order = _core_order(db, so_number=f"ZZT-SO-{_uid()[:8]}")
    _core_line(db, core_order, product, required_date=D1)
    order = _project_order(
        db, project, autocount_doc_no=core_order.so_number, so_id=core_order.id
    )
    _project_line(db, order, product, line_no=1, delivery_date=D1)
    return order


def _awaiting_scenario(db, project):
    """A Project SO with no document uploaded yet: awaiting_reconciliation."""
    product = _product(db)
    order = _project_order(db, project, autocount_doc_no=None, so_id=None)
    _project_line(db, order, product, line_no=1, delivery_date=D1)
    return order


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
    UserPermissionService.check_user_has_permission = (
        lambda self, uid, slug: slug in granted
    )
    UserPermissionService.get_user_permission_slugs = lambda self, uid: list(granted)
    return TestClient(app), originals


def _restore(originals) -> None:
    from app.main import app
    from app.services.user_service import UserPermissionService

    UserPermissionService.check_user_has_permission = originals[0]
    UserPermissionService.get_user_permission_slugs = originals[1]
    app.dependency_overrides.clear()


def _api(permissions):
    from app.models.base import company_scope

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Eling")
        project = _project(db, company_id, owner)
        linked = _linked_scenario(db, project)
        awaiting = _awaiting_scenario(db, project)
        db.commit()
        client, originals = _client(db, owner, permissions)
        try:
            with company_scope(db, frozenset({company_id})):
                yield client, db, project, linked, awaiting, owner
        finally:
            _restore(originals)


@pytest.fixture()
def api():
    yield from _api([VIEW, EDIT])


@pytest.fixture()
def reader_api():
    yield from _api([VIEW])


@pytest.fixture()
def no_perms_api():
    yield from _api([])


# --------------------------------------------------------------------------- #
# GET /fulfilment-planning                                                    #
# --------------------------------------------------------------------------- #


def test_fulfilment_planning_list_serves_one_row_per_published_so(api):
    client, _db, project, linked, awaiting, _owner = api

    response = client.get(f"{BASE}/fulfilment-planning")

    assert response.status_code == 200, response.text
    body = response.json()
    rows = {row["id"]: row for row in body["data"]}
    assert linked.id in rows
    assert awaiting.id in rows

    linked_row = rows[linked.id]
    assert linked_row["review_state"] == "needs_cs_review"
    assert linked_row["project_id"] == project.id
    assert linked_row["provisional_ref"] == linked.provisional_ref
    assert linked_row["autocount_doc_no"] == linked.autocount_doc_no
    assert linked_row["line_count"] == 1
    assert linked_row["lines_linked"] == 1
    assert linked_row["exception_count"] == 0

    assert rows[awaiting.id]["review_state"] == "awaiting_reconciliation"


def test_fulfilment_planning_list_filters_by_review_state(api):
    client, _db, _project, linked, awaiting, _owner = api

    response = client.get(
        f"{BASE}/fulfilment-planning", params={"review_state": "needs_cs_review"}
    )

    assert response.status_code == 200, response.text
    ids = {row["id"] for row in response.json()["data"]}
    assert linked.id in ids
    assert awaiting.id not in ids


def test_fulfilment_planning_list_refuses_without_view_permission(no_perms_api):
    client, *_rest = no_perms_api

    response = client.get(f"{BASE}/fulfilment-planning")

    assert response.status_code == 403, response.text


# --------------------------------------------------------------------------- #
# GET /sales-orders/{pso_id}/reconciliation                                   #
# --------------------------------------------------------------------------- #


def test_reconciliation_route_serves_the_summary_shape(api):
    client, _db, project, linked, _awaiting, _owner = api

    response = client.get(f"{BASE}/sales-orders/{linked.id}/reconciliation")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["project_sales_order_id"] == linked.id
    assert body["provisional_ref"] == linked.provisional_ref
    assert body["autocount_doc_no"] == linked.autocount_doc_no
    assert body["project_id"] == project.id
    assert body["review_state"] == "needs_cs_review"
    assert body["header"]["outcome"] == "linked"
    assert body["header"]["core_so_number"]
    assert isinstance(body["lines"], list) and len(body["lines"]) == 1
    assert body["lines"][0]["link"] == "linked"
    assert body["exceptions"] == []
    assert body["lines_total"] == body["lines_linked"] == 1


def test_reconciliation_route_404s_on_an_unknown_sales_order(api):
    client, *_rest = api

    response = client.get(f"{BASE}/sales-orders/{uuid.uuid4()}/reconciliation")

    assert response.status_code == 404, response.text


def test_reconciliation_route_refuses_without_view_permission(no_perms_api):
    client, _db, _project, linked, _awaiting, _owner = no_perms_api

    response = client.get(f"{BASE}/sales-orders/{linked.id}/reconciliation")

    assert response.status_code == 403, response.text


def test_no_exception_message_in_the_reconciliation_route_names_a_uuid(api):
    client, _db, _project, _linked, awaiting, _owner = api

    response = client.get(f"{BASE}/sales-orders/{awaiting.id}/reconciliation")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["exceptions"], "expected at least one exception to check"
    for exc in body["exceptions"]:
        assert not _UUID_RE.search(exc["message"])


# --------------------------------------------------------------------------- #
# POST /sales-orders/{pso_id}/reconcile                                       #
# --------------------------------------------------------------------------- #


def test_reconcile_route_persists_the_link_and_reruns_idempotently(api):
    client, db, _project, linked, _awaiting, _owner = api

    first = client.post(f"{BASE}/sales-orders/{linked.id}/reconcile")

    assert first.status_code == 200, first.text
    body1 = first.json()
    assert body1["review_state"] == "needs_cs_review"
    assert body1["lines_linked"] == 1

    persisted_line = (
        db.query(ProjectSalesOrderLine)
        .filter(ProjectSalesOrderLine.project_sales_order_id == linked.id)
        .one()
    )
    assert persisted_line.core_sales_order_line_id is not None

    second = client.post(f"{BASE}/sales-orders/{linked.id}/reconcile")

    assert second.status_code == 200, second.text
    body2 = second.json()
    assert body2["lines_linked"] == body1["lines_linked"] == 1
    assert body2["review_state"] == body1["review_state"] == "needs_cs_review"
    assert body2["exceptions"] == body1["exceptions"] == []


def test_reconcile_route_404s_on_an_unknown_sales_order(api):
    client, *_rest = api

    response = client.post(f"{BASE}/sales-orders/{uuid.uuid4()}/reconcile")

    assert response.status_code == 404, response.text


def test_reconcile_route_refuses_a_viewer_without_edit_permission(reader_api):
    client, _db, _project, linked, _awaiting, _owner = reader_api

    response = client.post(f"{BASE}/sales-orders/{linked.id}/reconcile")

    assert response.status_code == 403, response.text


# --------------------------------------------------------------------------- #
# review_state / exception_count on the existing SO list + detail             #
# --------------------------------------------------------------------------- #


def test_the_project_so_list_row_carries_review_state_and_exception_count(api):
    client, _db, project, linked, awaiting, _owner = api

    response = client.get(f"{BASE}/projects/{project.id}/sales-orders")

    assert response.status_code == 200, response.text
    rows = {row["id"]: row for row in response.json()["data"]}
    assert rows[linked.id]["review_state"] == "needs_cs_review"
    assert rows[linked.id]["exception_count"] == 0
    assert rows[awaiting.id]["review_state"] == "awaiting_reconciliation"


def test_the_project_so_detail_carries_review_state_and_exception_count(api):
    client, _db, _project, linked, _awaiting, _owner = api

    response = client.get(f"{BASE}/sales-orders/{linked.id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["review_state"] == "needs_cs_review"
    assert body["exception_count"] == 0


# --------------------------------------------------------------------------- #
# No credentials at all                                                       #
# --------------------------------------------------------------------------- #


def test_the_reconciliation_route_refuses_a_caller_with_no_credentials():
    """Built WITHOUT the `with TestClient(app)` context manager on purpose -- see
    the identical note in `test_project_so_worksheet.py`: entering it runs the
    app's startup event and registers global audit listeners for the rest of the
    session, which a later test's history assertions would then see."""
    from fastapi.testclient import TestClient

    from app.main import app

    assert not app.dependency_overrides, "a sibling test left its overrides behind"
    response = TestClient(app).get(f"{BASE}/sales-orders/{uuid.uuid4()}/reconciliation")

    assert response.status_code in (401, 403), response.text
