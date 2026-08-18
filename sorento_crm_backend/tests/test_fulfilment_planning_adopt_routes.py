"""The adoption path's routes (plan section 6).

Contract: `documentation/plans/scm/PLAN-fulfilment-planning-from-autocount-so.md` section
6, which the frontend's mock was built against
(`app/(protected)/project-sales/_shared/services/fulfilmentPlanningService.ts`):

    GET  /project-sales/fulfilment-planning?...&review_state&sales_order_id
         review_state is a CLOSED set of FOUR, the first of them new:
           not_started | awaiting_reconciliation | needs_cs_review | confirmed
         An unknown value is a 422, never an empty 200.

    POST /project-sales/fulfilment-planning/adopt   body { sales_order_id }
         -> { project_sales_order_id, so_number, review_state, already_adopted }
         404 out of company scope, 409 on the two named refusals, 422 on a missing body.

No new permission (AC-FP26): reads take `projects.projects.view`, the write takes
`projects.projects.edit`, both of which every role that can already reach this screen holds.

TEST-FIRST. Written before the `adopt` route existed and before `not_started` was in the
route's `Literal`, so the red state was `404 Not Found` on every POST and `422` on the
`not_started` GET - the routes' absence, not an import or a fixture problem.

Postgres, blank scratch schema via `tests/_pg_fixture.py::blank_session`, rolled back at
teardown. The TestClient harness (`_client` / `_restore`) is imported from
`tests/test_project_so_reconciliation_routes.py` rather than copied.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.models.base import company_scope
from app.models.company import Company
from app.models.project_so import ProjectSalesOrder
from app.services import project_seed_service

from ._pg_fixture import blank_session
from .test_project_so_adoption import (
    MARKER,
    _core_line,
    _core_order,
    _product,
    _sorento,
    _uid,
    _warehouse,
)
from .test_project_so_reconciliation_routes import BASE, EDIT, VIEW, _client, _restore

D_MID = date(2026, 6, 9)


def _world(permissions):
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        from app.models.user import User

        owner = _uid()
        db.add(User(id=owner, email=f"{owner}@zzt.test", name=f"{MARKER} Eling"))
        db.flush()

        with company_scope(db, frozenset({company_id})):
            product = _product(db)
            warehouse = _warehouse(db, company_id)
            core = _core_order(db, company_id)
            _core_line(db, core, product, warehouse=warehouse, required_date=D_MID)
        db.commit()

        client, originals = _client(db, owner, permissions)
        try:
            with company_scope(db, frozenset({company_id})):
                yield client, db, company_id, core
        finally:
            _restore(originals)


@pytest.fixture()
def api():
    yield from _world([VIEW, EDIT])


@pytest.fixture()
def reader_api():
    yield from _world([VIEW])


# --------------------------------------------------------------------------- #
# GET /fulfilment-planning: the new state, and the closed set                  #
# --------------------------------------------------------------------------- #


def test_the_worklist_serves_the_outstanding_core_order_as_not_started(api):
    client, _db, _company_id, core = api

    response = client.get(f"{BASE}/fulfilment-planning")

    assert response.status_code == 200, response.text
    rows = {row["so_number"]: row for row in response.json()["data"]}
    assert core.so_number in rows
    row = rows[core.so_number]
    assert row["review_state"] == "not_started"
    assert row["row_kind"] == "sales_order"
    assert row["id"] is None
    assert row["sales_order_id"] == str(core.id)


def test_the_not_started_filter_is_part_of_the_closed_set(api):
    client, _db, _company_id, core = api

    response = client.get(
        f"{BASE}/fulfilment-planning", params={"review_state": "not_started"}
    )

    assert response.status_code == 200, response.text
    assert core.so_number in {row["so_number"] for row in response.json()["data"]}


def test_an_unknown_review_state_is_a_422_not_an_empty_200(api):
    client, *_rest = api

    response = client.get(
        f"{BASE}/fulfilment-planning", params={"review_state": "not_startd"}
    )

    assert response.status_code == 422, response.text


def test_the_worklist_can_be_narrowed_to_one_sales_order(api):
    client, db, company_id, core = api
    with company_scope(db, frozenset({company_id})):
        product = _product(db)
        warehouse = _warehouse(db, company_id)
        other = _core_order(db, company_id)
        _core_line(db, other, product, warehouse=warehouse, required_date=D_MID)
        db.commit()

    response = client.get(
        f"{BASE}/fulfilment-planning", params={"sales_order_id": str(core.id)}
    )

    assert response.status_code == 200, response.text
    assert {row["so_number"] for row in response.json()["data"]} == {core.so_number}


# --------------------------------------------------------------------------- #
# POST /fulfilment-planning/adopt                                             #
# --------------------------------------------------------------------------- #


def test_start_planning_adopts_the_core_order_and_says_which_record_it_is(api):
    client, db, _company_id, core = api

    response = client.post(
        f"{BASE}/fulfilment-planning/adopt", json={"sales_order_id": str(core.id)}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["already_adopted"] is False
    assert body["so_number"] == core.so_number
    assert body["review_state"] == "needs_cs_review"
    assert (
        db.query(ProjectSalesOrder)
        .filter(ProjectSalesOrder.id == body["project_sales_order_id"])
        .count()
        == 1
    )

    # The row it came from now reads Needs CS review and carries the record, once.
    listed = client.get(f"{BASE}/fulfilment-planning")
    rows = [r for r in listed.json()["data"] if r["so_number"] == core.so_number]
    assert len(rows) == 1
    assert rows[0]["review_state"] == "needs_cs_review"
    assert rows[0]["id"] == body["project_sales_order_id"]


def test_pressing_start_planning_twice_answers_with_the_same_record(api):
    client, _db, _company_id, core = api

    first = client.post(
        f"{BASE}/fulfilment-planning/adopt", json={"sales_order_id": str(core.id)}
    )
    second = client.post(
        f"{BASE}/fulfilment-planning/adopt", json={"sales_order_id": str(core.id)}
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert (
        second.json()["project_sales_order_id"]
        == first.json()["project_sales_order_id"]
    )
    assert second.json()["already_adopted"] is True


def test_start_planning_refuses_a_reader(reader_api):
    client, _db, _company_id, core = reader_api

    response = client.post(
        f"{BASE}/fulfilment-planning/adopt", json={"sales_order_id": str(core.id)}
    )

    assert response.status_code == 403, response.text


def test_start_planning_on_an_unknown_sales_order_is_a_404(api):
    client, *_rest = api

    response = client.post(
        f"{BASE}/fulfilment-planning/adopt", json={"sales_order_id": _uid()}
    )

    assert response.status_code == 404, response.text


def test_start_planning_without_a_sales_order_is_a_422(api):
    client, *_rest = api

    response = client.post(f"{BASE}/fulfilment-planning/adopt", json={})

    assert response.status_code == 422, response.text


def test_start_planning_across_a_company_is_a_404_and_names_nothing(api):
    client, db, _company_id, _core = api
    other_company_id = _uid()
    db.add(Company(id=other_company_id, name=f"{MARKER} other", code=f"ZZT{_uid()[:6]}"))
    db.flush()
    with company_scope(db, frozenset({other_company_id})):
        product = _product(db)
        warehouse = _warehouse(db, other_company_id)
        foreign = _core_order(db, other_company_id)
        _core_line(db, foreign, product, warehouse=warehouse, required_date=D_MID)
        db.commit()

    response = client.post(
        f"{BASE}/fulfilment-planning/adopt", json={"sales_order_id": str(foreign.id)}
    )

    assert response.status_code == 404, response.text
    assert foreign.so_number not in response.text
    assert (
        db.query(ProjectSalesOrder)
        .filter(ProjectSalesOrder.so_id == foreign.id)
        .count()
        == 0
    )


def test_start_planning_on_a_retail_order_is_a_named_409(api):
    client, db, company_id, _core = api
    with company_scope(db, frozenset({company_id})):
        product = _product(db)
        warehouse = _warehouse(db, company_id)
        retail = _core_order(db, company_id, demand_class="retail")
        _core_line(db, retail, product, warehouse=warehouse, required_date=D_MID)
        db.commit()

    response = client.post(
        f"{BASE}/fulfilment-planning/adopt", json={"sales_order_id": str(retail.id)}
    )

    assert response.status_code == 409, response.text
    body = response.json()
    assert body.get("code") == "sales_order_not_project_class"
    assert retail.so_number in body.get("message", "")
