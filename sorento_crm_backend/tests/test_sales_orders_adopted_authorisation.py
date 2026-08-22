"""Save, delete and bulk-delete on an order that has no project.

An order adopted from the AutoCount book carries `project_id = NULL` by design (migration
383). The three write routes in `sales_orders.py` used to pass that null to
`get_project_or_404` and answer 404 "Project not found", which took the routes off the
screen for exactly the records the fulfilment journey is about. The gate is now the same
shape as `fulfilment_planning._assert_can_act_on`: the module permission on the route is
the whole authorisation when there is no project, and the per-project check is kept for
records that have one.

Postgres via `tests/_pg_fixture.py::blank_session`, seeding its own chain. The adopted
record is written by the REAL adoption service, so what is under test is the row Start
planning writes.
"""
from __future__ import annotations

import uuid

from app.models.project_so import ProjectSalesOrder
from app.services.project_so_adoption_service import ProjectSOAdoptionService
from app.services.user_service import UserPermissionService

from .test_so_supply_confirmation import (  # noqa: F401  (api is a fixture)
    BASE,
    _core_line,
    _core_so,
    api,
)

DELETE = "projects.projects.delete"
EDIT = "projects.projects.edit"


def _adopted(world) -> ProjectSalesOrder:
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_so.demand_origin = "scm_order_inquiry"
    _core_line(db, core_so, world.product, world.own_wh, qty_ordered="50")
    db.flush()
    result = ProjectSOAdoptionService(db).adopt(str(core_so.id), actor_user_id=world.eling)
    db.commit()
    order = (
        db.query(ProjectSalesOrder)
        .filter(ProjectSalesOrder.id == result["project_sales_order_id"])
        .first()
    )
    assert order.project_id is None
    return order


def _projectless_draft(world) -> ProjectSalesOrder:
    """A draft with no project and no AutoCount link: the one project-less shape the
    delete rule lets through, so the route's gate is observable on its own."""
    order = ProjectSalesOrder(
        id=str(uuid.uuid4()),
        company_id=world.company_id,
        project_id=None,
        provisional_ref=f"ZZT-NOPRJ-{uuid.uuid4().hex[:8]}",
        status="draft",
    )
    world.db.add(order)
    world.db.commit()
    return order


class _without:
    """Take ONE permission away from the harness's allow-everything actor."""

    def __init__(self, slug: str):
        self.slug = slug

    def __enter__(self):
        self.original = UserPermissionService.check_user_has_permission
        slug = self.slug
        UserPermissionService.check_user_has_permission = (
            lambda self, uid, s: s != slug
        )

    def __exit__(self, *_exc):
        UserPermissionService.check_user_has_permission = self.original


def test_an_adopted_order_is_saved_with_the_module_permission_alone(api):
    client, world = api
    order = _adopted(world)

    response = client.put(f"{BASE}/sales-orders/{order.id}", json={"area_group": "TOWER B"})

    assert response.status_code == 200, response.text
    assert response.json()["area_group"] == "TOWER B"
    assert response.json()["project_id"] is None

    detail = client.get(f"{BASE}/sales-orders/{order.id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["area_group"] == "TOWER B"


def test_saving_an_adopted_order_is_denied_without_the_edit_permission(api):
    client, world = api
    order = _adopted(world)

    with _without(EDIT):
        response = client.put(
            f"{BASE}/sales-orders/{order.id}", json={"area_group": "TOWER B"}
        )

    assert response.status_code == 403, response.text


def test_deleting_an_adopted_order_reaches_the_service_rule_not_a_missing_project(api):
    """The record is linked to a live AutoCount document, so the SERVICE refuses it - which
    is the answer the reviewer should read, not "Project not found"."""
    client, world = api
    order = _adopted(world)

    response = client.delete(f"{BASE}/sales-orders/{order.id}")

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "so_autocount_linked"


def test_a_project_less_draft_is_deleted_with_the_module_permission_alone(api):
    client, world = api
    order_id = _projectless_draft(world).id

    response = client.delete(f"{BASE}/sales-orders/{order_id}")

    assert response.status_code == 200, response.text
    assert response.json()["success"] is True
    assert (
        world.db.query(ProjectSalesOrder).filter(ProjectSalesOrder.id == order_id).first()
        is None
    )


def test_deleting_a_project_less_order_is_denied_without_the_delete_permission(api):
    client, world = api
    order = _projectless_draft(world)

    with _without(DELETE):
        response = client.delete(f"{BASE}/sales-orders/{order.id}")

    assert response.status_code == 403, response.text


def test_bulk_delete_of_project_less_drafts_needs_only_the_module_permission(api):
    client, world = api
    ids = [_projectless_draft(world).id, _projectless_draft(world).id]

    response = client.post(f"{BASE}/sales-orders/bulk-delete", json={"ids": ids})

    assert response.status_code == 200, response.text
    assert response.json()["deleted_count"] == 2


def test_bulk_delete_of_an_adopted_order_reaches_the_service_refusal(api):
    client, world = api
    order = _adopted(world)

    response = client.post(f"{BASE}/sales-orders/bulk-delete", json={"ids": [order.id]})

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == "so_bulk_not_deletable"
    assert [row["code"] for row in body["refused"]] == ["so_autocount_linked"]


def test_bulk_delete_of_project_less_orders_is_denied_without_the_delete_permission(api):
    client, world = api
    order = _projectless_draft(world)

    with _without(DELETE):
        response = client.post(
            f"{BASE}/sales-orders/bulk-delete", json={"ids": [order.id]}
        )

    assert response.status_code == 403, response.text
