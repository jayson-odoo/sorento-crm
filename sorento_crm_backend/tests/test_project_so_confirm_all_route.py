"""POST /project-sales/fulfilment-planning/confirm-all (PLAN-demo-followups-19aug-ladder-v2
workstream D3).

Contract in `app/services/project_supply_service.py::confirm_many` and
`app/api/v1/projects/fulfilment_planning.py::confirm_all`: "Confirm all approved" posts the
SAME per-order write `POST .../sales-orders/{pso_id}/confirm` already does, once per order
named in the body, each in its OWN transaction. One order's own refusal must never take the
orders around it down - every order named in the body gets a result, in the same order,
and nothing from a failing order is ever persisted.

Postgres via `tests/_pg_fixture.py::blank_session`, never sqlite. Reuses the fixture chain
from `tests/test_so_supply_confirmation.py` (company, project, product, warehouses, the
TestClient harness) rather than re-declaring it, and seeds its own two sales orders on top.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.project_so import SOSupplyDecision

from .test_so_supply_confirmation import (  # noqa: F401 - `api` is a fixture
    BASE,
    EDIT,
    VIEW,
    _client,
    _core_line,
    _core_so,
    _line_payload,
    _project_line,
    _project_so,
    _restore,
    _stock,
    api,
)

MARKER = "zzt-confirm-all"


def _uid() -> str:
    return str(uuid.uuid4())


# --------------------------------------------------------------------------- happy path


def test_confirm_all_commits_the_good_order_and_reports_the_bad_one_without_writing_it(api):
    """One order confirms cleanly; the other names a line that belongs to the FIRST order,
    which is not on the second order's own book - a failing line, refused whole, nothing
    written for it - while the first order's own commit stands untouched.

    Ladder v2 (section E rule 7): the own location is never a Reserve source any more, so
    the good order's line reserves from the shared POOL (`world.pool_wh`, wired to
    `world.own_wh` by the `api` fixture) rather than its own warehouse."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=100)

    order_1 = _project_so(db, world.project)
    core_1 = _core_so(db, world.company_id)
    core_line_1 = _core_line(db, core_1, world.product, world.own_wh, qty_ordered="50")
    line_1 = _project_line(db, order_1, line_no=10, product=world.product, core_line=core_line_1)

    order_2 = _project_so(db, world.project)
    core_2 = _core_so(db, world.company_id)
    core_line_2 = _core_line(db, core_2, world.product, world.own_wh, qty_ordered="30")
    line_2 = _project_line(db, order_2, line_no=10, product=world.product, core_line=core_line_2)
    db.commit()

    payload = {
        "orders": [
            {
                "pso_id": order_1.id,
                "lines": [
                    _line_payload(
                        line_1.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "50"}]
                    )
                ],
            },
            {
                "pso_id": order_2.id,
                # line_1 belongs to order_1, not order_2: "not on this sales order any more".
                "lines": [_line_payload(line_1.id, buy_qty="30")],
            },
        ]
    }
    response = client.post(f"{BASE}/fulfilment-planning/confirm-all", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    results = {row["pso_id"]: row for row in body["results"]}
    assert len(body["results"]) == 2
    # Same order as the request, so an index-matching caller never has to search.
    assert [row["pso_id"] for row in body["results"]] == [order_1.id, order_2.id]

    first = results[order_1.id]
    assert first["ok"] is True, first
    assert first["decision_revision"] == 1
    assert first["lines_decided"] == 1
    assert first["lines_undecided"] == 0
    assert first.get("error") is None
    # The board's toast counts the movements PER ORDER, so both figures have to survive the
    # response model - one it does not declare is dropped in silence (R16).
    assert first["transfers_written"] == 1
    assert first["transfers_kept"] == 0

    second = results[order_2.id]
    assert second["ok"] is False, second
    assert second.get("error")
    failing_line_nos = {
        row.get("line_no") for row in (second.get("failing_lines") or [])
    }
    # The refused line addresses by line number where it can; here the id resolves to no
    # line on THIS order, so the service names it with a null line number and a reason.
    assert any(
        "not on this sales order" in (row.get("reason") or "")
        for row in (second.get("failing_lines") or [])
    ), second

    assert (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order_1.id)
        .count()
        == 1
    ), "the good order's commit must stand"
    assert (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order_2.id)
        .count()
        == 0
    ), "nothing from the failing order may be written"


# --------------------------------------------------------------------------- malformed id


def test_confirm_all_names_a_malformed_pso_id_plainly_instead_of_a_database_error(api):
    """A `pso_id` that is not a UUID at all must never reach `get_order`'s query: Postgres
    would raise its own message for it, and that message would surface verbatim as this
    entry's `error` - a database internal leaking to the planner. Caught before the query,
    same guard the single-order route applies via `validate_uuid_path`, and reported as a
    plain per-entry refusal rather than aborting the whole batch.

    Ladder v2 (section E rule 7): the own location is never a Reserve source any more, so
    the good order's line reserves from the shared POOL (`world.pool_wh`) instead."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=50)

    order = _project_so(db, world.project)
    core = _core_so(db, world.company_id)
    core_line = _core_line(db, core, world.product, world.own_wh, qty_ordered="50")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    payload = {
        "orders": [
            {"pso_id": "not-a-uuid", "lines": []},
            {
                "pso_id": order.id,
                "lines": [
                    _line_payload(
                        line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "50"}]
                    )
                ],
            },
        ]
    }
    response = client.post(f"{BASE}/fulfilment-planning/confirm-all", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    results = {row["pso_id"]: row for row in body["results"]}
    assert len(body["results"]) == 2

    bad = results["not-a-uuid"]
    assert bad["ok"] is False, bad
    assert bad["error"] == "Not a valid sales order id."
    assert bad.get("failing_lines") is None

    # The malformed entry never touches the good one alongside it.
    good = results[order.id]
    assert good["ok"] is True, good
    assert (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id)
        .count()
        == 1
    )


# --------------------------------------------------------------------------- empty body


def test_confirm_all_with_no_orders_answers_with_an_empty_result(api):
    client, _world = api

    response = client.post(f"{BASE}/fulfilment-planning/confirm-all", json={"orders": []})

    assert response.status_code == 200, response.text
    assert response.json() == {"results": []}


def test_confirm_all_with_no_body_field_answers_with_an_empty_result(api):
    """`orders` defaults to `[]` on the schema, so an entirely empty body is the same as
    an explicit empty list - never a 422 for a board with nothing approved yet."""
    client, _world = api

    response = client.post(f"{BASE}/fulfilment-planning/confirm-all", json={})

    assert response.status_code == 200, response.text
    assert response.json() == {"results": []}


# --------------------------------------------------------------------------- auth denial


def test_confirm_all_is_denied_without_the_edit_permission(api):
    client, world = api
    db = world.db
    _stock(db, world.product, world.own_wh, on_hand=50)
    order = _project_so(db, world.project)
    core = _core_so(db, world.company_id)
    core_line = _core_line(db, core, world.product, world.own_wh, qty_ordered="50")
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    from app.services.user_service import UserPermissionService

    original = UserPermissionService.check_user_has_permission
    try:
        UserPermissionService.check_user_has_permission = lambda self, uid, slug: slug != EDIT
        response = client.post(
            f"{BASE}/fulfilment-planning/confirm-all",
            json={
                "orders": [
                    {
                        "pso_id": order.id,
                        "lines": [
                            _line_payload(
                                line.id,
                                reserve=[{"warehouse_id": world.own_wh.id, "qty": "50"}],
                            )
                        ],
                    }
                ]
            },
        )
        assert response.status_code == 403, response.text
    finally:
        UserPermissionService.check_user_has_permission = original

    assert (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id)
        .count()
        == 0
    )


def test_confirm_all_401s_without_a_principal(api):
    """`require_permission` (unlike the API-key variant the reads use) resolves the
    principal through `get_current_user` alone, so denying that dependency is the 401."""
    from app.dependencies import get_current_user
    from app.main import app
    from fastapi import HTTPException

    client, _world = api

    def _deny():
        raise HTTPException(status_code=401, detail="Not authenticated")

    original = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = _deny
    try:
        response = client.post(
            f"{BASE}/fulfilment-planning/confirm-all", json={"orders": []}
        )
    finally:
        if original is not None:
            app.dependency_overrides[get_current_user] = original

    assert response.status_code == 401, response.text
