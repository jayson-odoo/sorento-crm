""""This might be a system problem, flag it for investigation"
(`PLAN-scm-planning-inline-decisions.md` section 3.D5, ruling R10).

A SECOND answer beside the verdict rather than instead of it. A planner who amends a line
because the availability printed next to it reads wrong is telling us two different things,
and a decision that recorded only the amendment lost the one worth chasing. So the flag:

* travels on `ConfirmLine`, beside `amend_reason`, with whichever verdict was given;
* is FROZEN on the decision line, so the warning is still on the pill after a reload - a
  flag that lived only in the session's draft would say the doubt had been answered the
  moment the page was refreshed;
* is counted in `ConfirmResult.suspected_issues`, and stamped on the revision itself
  (`so_supply_decisions.suspected_system_issue`, migration 439) so a revision with a doubt
  on it can be found without walking a JSONB array.

Every assertion that matters is made on the WIRE: `response_model` silently drops what it
does not declare, so a field asserted only on the service's dict can be missing from the
JSON the board reads.

Postgres, blank scratch schema, every FK target seeded here (PRINCIPLES).
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.base import company_scope
from app.models.project_so import SOSupplyDecision
from app.services import project_seed_service

from ._pg_fixture import blank_session
from .test_so_supply_confirmation import (
    _client,
    _core_line,
    _core_so,
    _line_payload,
    _product,
    _project_line,
    _project_so,
    _restore,
    _sorento,
    _stock,
    _suffix,
    _user,
    _warehouse,
)

MARKER = "zzt-suspect"
BASE = "/api/v1/project-sales"


def _uid() -> str:
    return str(uuid.uuid4())


class _World:
    def __init__(self, db, company_id, actor, project, product, own_wh, pool_wh):
        self.db = db
        self.company_id = company_id
        self.actor = actor
        self.project = project
        self.product = product
        self.own_wh = own_wh
        self.pool_wh = pool_wh


@pytest.fixture()
def api():
    from app.services.project_service import register_project

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        actor = _user(db, f"{MARKER} Eling")
        project = register_project(
            db,
            company_id=company_id,
            actor_user_id=actor,
            developer_party_id=None,
            title=f"{MARKER} Tuju Residences",
        )
        product = _product(db)
        stem = _suffix()
        own_wh = _warehouse(db, f"ZZT{stem}A-BB", segment="project")
        pool_wh = _warehouse(db, f"ZZT{stem}P", segment="dealer")
        own_wh.pool_warehouse_id = pool_wh.id
        db.flush()
        db.commit()
        client, originals = _client(db, actor)
        world = _World(db, company_id, actor, project, product, own_wh, pool_wh)
        try:
            with company_scope(db, frozenset({company_id})):
                yield client, world
        finally:
            _restore(originals)


def _one_line_order(world, *, qty="10"):
    """A published project SO mirroring a real core order, one line, at its own location.

    The mirror names the core order (`so_id`): the board only offers a line it can address
    a confirmation to, and an unlinked mirror is invisible to it.
    """
    db = world.db
    core_so = _core_so(db, world.company_id)
    order = _project_so(db, world.project, so_id=core_so.id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered=qty)
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()
    return order, core_so, core_line, line


def _reserve(world, line, qty="10", **extra):
    """The shared payload helper, plus the two fields this lane adds to `ConfirmLine`."""
    body = _line_payload(
        line.id, reserve=[{"warehouse_id": world.own_wh.id, "qty": qty}]
    )
    body.update(extra)
    return body


def _decision(db, order):
    return (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id)
        .order_by(SOSupplyDecision.revision_no.desc())
        .first()
    )


def test_the_flag_is_frozen_on_the_line_and_counted_in_the_result(api):
    client, world = api
    db = world.db
    _stock(db, world.product, world.own_wh, on_hand=100)
    order, _core_so, _core_line, line = _one_line_order(world)

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _reserve(
                    world,
                    line,
                    amend_reason="BRW-AM says 9 available and the sheet says -15.",
                    suspected_system_issue=True,
                )
            ]
        },
    )

    assert response.status_code == 200, response.text
    # On the WIRE: `response_model` drops what it does not declare.
    assert response.json()["suspected_issues"] == 1

    decision = _decision(db, order)
    snapshot = decision.line_snapshots[0]
    assert snapshot["suspected_system_issue"] is True
    assert snapshot["amend_reason"] == "BRW-AM says 9 available and the sheet says -15."
    # The revision itself carries the answer to "was anything on it flagged" (migration 439).
    assert decision.suspected_system_issue is True


def test_a_confirmation_nobody_flagged_says_so_rather_than_saying_nothing(api):
    client, world = api
    db = world.db
    _stock(db, world.product, world.own_wh, on_hand=100)
    order, _core_so, _core_line, line = _one_line_order(world)

    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_reserve(world, line)]},
    )

    assert response.status_code == 200, response.text
    assert response.json()["suspected_issues"] == 0
    decision = _decision(db, order)
    assert decision.line_snapshots[0]["suspected_system_issue"] is False
    assert decision.suspected_system_issue is False


def test_the_flag_reaches_the_board_so_the_pill_still_warns_after_a_reload(api):
    """AC-C10. The board reads the FROZEN decision, so the warning survives the refresh."""
    from app.services.project_fulfilment_board_service import FulfilmentBoardService

    client, world = api
    db = world.db
    _stock(db, world.product, world.own_wh, on_hand=100)
    order, core_so, _core_line, line = _one_line_order(world)

    assert (
        client.post(
            f"{BASE}/sales-orders/{order.id}/confirm",
            json={
                "lines": [
                    _reserve(
                        world, line, amend_reason="The numbers look wrong.",
                        suspected_system_issue=True,
                    )
                ]
            },
        ).status_code
        == 200
    )

    board = FulfilmentBoardService(db).build(
        [core_so.so_number], granularity="week", as_of=date(2026, 1, 1)
    )
    contributions = [c for cell in board["cells"] for c in cell["contributions"]]
    decided = [c for c in contributions if c["decision"]]
    assert decided, "the confirmed line must come back covered, with its decision"
    assert decided[0]["decision"]["suspected_system_issue"] is True


def test_the_flag_reaches_the_board_over_the_wire(api):
    """`response_model` drops undeclared fields, so the echo is asserted on the JSON."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.own_wh, on_hand=100)
    order, core_so, _core_line, line = _one_line_order(world)

    assert (
        client.post(
            f"{BASE}/sales-orders/{order.id}/confirm",
            json={
                "lines": [
                    _reserve(
                        world, line, amend_reason="The numbers look wrong.",
                        suspected_system_issue=True,
                    )
                ]
            },
        ).status_code
        == 200
    )

    response = client.get(
        f"{BASE}/fulfilment-planning/board",
        params={"orders": core_so.so_number, "granularity": "week"},
    )

    assert response.status_code == 200, response.text
    decisions = [
        contribution["decision"]
        for cell in response.json()["cells"]
        for contribution in cell["contributions"]
        if contribution["decision"]
    ]
    assert decisions, "the confirmed line must come back covered"
    assert decisions[0]["suspected_system_issue"] is True


def test_confirm_all_reports_the_transfers_each_order_raised(api):
    """D5's other half: the board's toast reads "N lines confirmed - T transfers proposed",
    and the batch reply is where T comes from. The FE type already expects the two fields,
    so the schema has to declare them or `response_model` drops them."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=100)
    order, _core_so, _core_line, line = _one_line_order(world)

    response = client.post(
        f"{BASE}/fulfilment-planning/confirm-all",
        json={
            "orders": [
                {
                    "pso_id": str(order.id),
                    "lines": [
                        _line_payload(
                            line.id,
                            reserve=[{"warehouse_id": world.pool_wh.id, "qty": "10"}],
                        )
                    ],
                }
            ]
        },
    )

    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["ok"] is True
    # One component drawn from the pool rather than the line's own location: one movement.
    assert result["transfers_written"] == 1
    assert result["transfers_failed"] == 0
