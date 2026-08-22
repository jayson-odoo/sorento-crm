"""An adopted AutoCount order must reach the sheet, propose, and confirm - with no project.

This is the captain's approved journey, end to end: Fulfilment Planning -> Start planning on
an outstanding AutoCount sales order -> the supply sheet -> Confirm
(`PLAN-fulfilment-planning-from-autocount-so.md` section 0, steps 2 to 5). Adoption writes a
planning record with `project_id = NULL` on purpose (section 4: an adopted order has no
project registration and must not invent one), so every screen and every write on that
journey has to tolerate the absence rather than assume the authored path's project.

Two live breaks this file pins, both found by reading the adopted path after seam C:

* the sheet serialised `str(order.project_id)` into a NOT-NULL schema field, so the proposal
  answered the literal string `"None"` - a UUID-shaped hole in the one field the frontend
  uses to link to the project's Order Inquiry;
* Confirm and Re-sync both ran `get_project_or_404(db, order.project_id)`, which answers 404
  "Project not found" for `None`. The last step of the journey was unreachable.

Postgres via `tests/_pg_fixture.py::blank_session`, seeding its own chain, per PRINCIPLES.
The record is built by the REAL adoption service rather than by hand, so what is under test
is the row the captain's Start planning button actually writes.
"""
from __future__ import annotations

import json

from app.models.project_so import ProjectSalesOrder, SOSupplyDecision
from app.services.project_so_adoption_service import ProjectSOAdoptionService

from .test_so_supply_confirmation import (  # noqa: F401  (api is a fixture)
    BASE,
    _core_line,
    _core_so,
    _line_payload,
    _stock,
    api,
)


def _adopted(world, *, lines=("50", "30")):
    """A core AutoCount order, adopted the way Start planning adopts it."""
    db = world.db
    core_so = _core_so(db, world.company_id)
    core_so.demand_origin = "scm_order_inquiry"
    for qty in lines:
        _core_line(db, core_so, world.product, world.own_wh, qty_ordered=qty)
    db.flush()

    result = ProjectSOAdoptionService(db).adopt(str(core_so.id), actor_user_id=world.eling)
    db.commit()

    order = (
        db.query(ProjectSalesOrder)
        .filter(ProjectSalesOrder.id == result["project_sales_order_id"])
        .first()
    )
    assert order.project_id is None, "an adopted order carries no project, by design"
    return core_so, order


def test_the_supply_sheet_opens_for_an_adopted_order_with_no_project(api):
    """Step 3 of the journey. The project is absent, and says so as null."""
    client, world = api
    _stock(world.db, world.product, world.own_wh, on_hand=100)
    _core, order = _adopted(world)

    response = client.get(f"{BASE}/sales-orders/{order.id}/supply")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["project_id"] is None
    assert body["project_code"] is None
    assert body["project_name"] is None
    assert len(body["lines"]) == 2, "both mirror lines are proposed against"
    assert '"None"' not in json.dumps(body), (
        "a stringified null is worse than a null: it is a value the screen would render "
        "and the frontend would use as a project id"
    )


def test_an_adopted_order_confirms_without_a_project(api):
    """Step 5, the end of the journey: the confirmation that makes the promise."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.own_wh, on_hand=100)
    _core, order = _adopted(world)

    sheet = client.get(f"{BASE}/sales-orders/{order.id}/supply")
    assert sheet.status_code == 200, sheet.text
    lines = sheet.json()["lines"]

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(line["project_line_id"], buy_qty=line["open_qty"])
                for line in lines
            ]
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["revision_no"] == 1
    assert response.json()["lines_undecided"] == 0

    db.expire_all()
    decision = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id)
        .first()
    )
    assert decision is not None and decision.state == "active"

    # Step 6: purchasing can still trace the Buy. The PROJECT-scoped Order Inquiry screens
    # cannot show an order that has no project (reported, not fixed here); this per-sales
    # order surface is the one that reaches it, and it must not 500 on the missing project.
    inquiry = client.get(f"{BASE}/sales-orders/{order.id}/order-inquiry")
    assert inquiry.status_code == 200, inquiry.text
    assert len(inquiry.json()["rows"]) == 2


def test_an_adopted_order_confirms_one_line_and_leaves_the_rest_undecided(api):
    """The two halves of seam C meet: partial confirmation on the adopted path, which is
    the path the captain plans the AutoCount book from."""
    client, world = api
    _stock(world.db, world.product, world.own_wh, on_hand=100)
    _core, order = _adopted(world)

    lines = client.get(f"{BASE}/sales-orders/{order.id}/supply").json()["lines"]
    first = lines[0]

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(first["project_line_id"], buy_qty=first["open_qty"])]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["lines_decided"] == 1
    assert response.json()["lines_undecided"] == 1

    sheet = client.get(f"{BASE}/sales-orders/{order.id}/supply").json()
    assert sheet["lines_decided"] == 1
    assert sheet["lines_total"] == 2


def test_a_cross_project_borrow_on_an_adopted_order_is_refused_by_name(api):
    """The third place a missing project would have surfaced, and the nastiest.

    `AllocationClaim.from_project_id` is a NOT NULL uuid: a cross-project Borrow on an
    adopted order used to reach it as the TEXT "None" and take the whole confirmation down
    with a database error, after every recheck had passed. It is refused as a failing line
    instead, and the sheet does not offer the Borrow in the first place.
    """
    from app.models.projects import Project
    from app.services.project_service import register_project

    client, world = api
    db = world.db
    _stock(db, world.product, world.own_wh, on_hand=100)
    _core, order = _adopted(world, lines=("50",))

    donor = register_project(
        db, company_id=world.company_id, actor_user_id=world.eling,
        developer_party_id=None, title="ZZT donor of stock",
    )
    db.commit()
    assert db.query(Project).filter(Project.id == donor.id).first() is not None

    lines = client.get(f"{BASE}/sales-orders/{order.id}/supply").json()["lines"]
    line = lines[0]
    assert all(
        candidate["source"] != "other_project"
        for candidate in line["borrow_candidates"]
    ), "an order with no project is never offered another project's stock"

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(
                    line["project_line_id"],
                    borrow=[{
                        "source": "other_project",
                        "warehouse_id": world.own_wh.id,
                        "donor_project_id": donor.id,
                        "qty": "10",
                        "reason": "the donor can spare it",
                    }],
                    buy_qty="40",
                )
            ]
        },
    )
    assert response.status_code == 422, response.text
    reasons = " ".join(row["reason"] for row in response.json()["failing_lines"])
    assert "belongs to no project" in reasons


def test_re_sync_runs_on_an_adopted_order_with_no_project(api):
    """Journey step 7's button, on the same sheet. It reconciles a record that has no
    project to authorise against, so the module permission is the whole gate (section 2,
    "Authorisation with no project")."""
    client, world = api
    _stock(world.db, world.product, world.own_wh, on_hand=100)
    _core, order = _adopted(world)

    response = client.post(f"{BASE}/sales-orders/{order.id}/reconcile")
    assert response.status_code == 200, response.text
    assert response.json()["header"]["outcome"] == "adopted"
