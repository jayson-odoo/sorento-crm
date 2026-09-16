"""Planning change confirm balances against the plan quantity
(`documentation/plans/scm/PLAN-scm-planning-change-plan-qty.md`, UAC AC-PQ1 to AC-PQ6, issue
#971). RED before the coder's fix lands - `planning_change_service._row_open_qty` (:2441-2450)
still prefers `proposal_json["qty_outstanding"]` (what is OWED the customer) over
`proposal_json["qty"]` (the PLAN quantity), while `composition_from_proposal`'s own composed
total already reads the plan quantity through `qty_proposed_buy` - so a partly-delivered line's
own board-composed suggestion mismatches the validator's reading of what it is open for.

Every scenario seeds a core line with BOTH `qty_ordered` and `qty_delivered` (`_delivered_
world`, below): an active decision already covers the line's FULL plan quantity (the shape
`ProjectSupplyService.confirm` validates against since the 14 September plan-quantity ruling,
`project_supply_service.py:604-611`), then a book re-upload / manual edit changes the line
the way `test_planning_change_delta_seam.py::_change_and_batch` already does (mutate the core
line, then `build_batch` off one `Change`) - the real SO-book-diff replanning path, not a
stand-in.

Postgres only (`tests/_pg_fixture.py::blank_session`), every FK seeded here, never a borrowed
row - CI's database has no data.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.models.planning_change import PlanningChangeRow
from app.models.project_so import DECISION_ACTIVE, DECISION_SUPERSEDED, SOSupplyDecision
from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody
from app.services import planning_change_service
from app.services.project_supply_service import ProjectSupplyService

from tests._pg_fixture import blank_session
from tests.test_planning_changes import BASE, _client, _line_payload, _restore
from tests.test_so_supply_confirmation import (  # noqa: F401  (helpers, not fixtures)
    _core_so,
    _core_line,
    _project_line,
    _project_so,
)
from tests.scm.test_project_supply_service_ladder import _group_sites, _world
from tests.scm.test_planning_change_delta_seam import _active_decision, _change_and_batch, _only_row

MARKER = "zzt-planqty"

#: Well beyond RESERVE_WINDOW_DAYS (60) and DEFAULT_IMMEDIATE_WINDOW_DAYS (30), matching
#: `test_planning_change_delta_seam.py`'s own `NON_IMMEDIATE` - a plain Buy proposal, no
#: reserve-window mechanics in play.
REQUIRED_DATE = date.today() + timedelta(days=100)


def _delivered_world(db, *, qty_ordered, qty_delivered, required_date=REQUIRED_DATE):
    """A held Buy, at the line's FULL PLAN quantity, on a line already PARTLY delivered -
    PLAN section 1's own measured shape (SO289628: `qty_ordered 3210, qty_delivered 638`).

    The initial confirm buys the WHOLE `qty_ordered` regardless of `qty_delivered` - the
    same shape `test_planning_change_delta_seam.py::_held_buy_world` already confirms with
    no delivery in play, and the one `ProjectSupplyService.confirm` itself validates
    against since the 14 September plan-quantity ruling (`project_supply_service.py:
    604-611`, `:4781`): what a line asks for is the PLAN quantity, not what is left owed.
    """
    company_id, actor, project, product = _world(db)
    _group, sites = _group_sites(db)
    own, pool = sites["BRW"]
    core_so = _core_so(db, company_id)
    core_line = _core_line(
        db, core_so, product, own, qty_ordered=qty_ordered, qty_delivered=qty_delivered,
        required_date=required_date,
    )
    order = _project_so(db, project, so_id=core_so.id)
    order.autocount_doc_no = core_so.so_number
    line = _project_line(db, order, line_no=1, product=product, core_line=core_line)
    db.commit()
    ProjectSupplyService(db).confirm(
        order,
        ConfirmSupplyBody(lines=[ConfirmLine(
            project_line_id=line.id, buy_qty=str(qty_ordered),
            buy_reason="ZZT no stock anywhere",
        )]),
        actor_user_id=actor,
    )
    db.commit()
    return {
        "company_id": company_id, "actor": actor, "project": project, "product": product,
        "own": own, "pool": pool, "order": order, "line": line, "core_so": core_so,
        "core_line": core_line,
    }


# --------------------------------------------------------------------------- #
# AC-PQ1: confirming the raised row balances against the plan quantity
# --------------------------------------------------------------------------- #

def test_confirm_on_a_partly_delivered_line_balances_against_the_plan_quantity():
    """AC-PQ1: `qty_ordered 3210 -> 3200` with `qty_delivered 638` (owed 2562, plan 3200)
    and an active decision already covering the line. Confirming the raised row via
    `PUT .../rows/{row_id}` with `decision=confirm` must balance the composed Buy (3200,
    the whole new plan quantity - `composition_from_proposal` already reads it off
    `qty_proposed_buy`) against the PLAN quantity, not the owed one: 200,
    `composition["buy_qty"] == "3200"`."""
    with blank_session() as db:
        world = _delivered_world(db, qty_ordered="3210", qty_delivered="638")
        batch = _change_and_batch(db, world, new_qty="3200")
        row = _only_row(db, batch)

        client, originals = _client(db, world["actor"])
        try:
            response = client.put(
                f"{BASE}/planning-changes/{batch.id}/rows/{row.id}",
                json={"decision": "confirm"},
            )
        finally:
            _restore(originals)

        assert response.status_code == 200, response.text
        assert response.json()["composition"]["buy_qty"] == "3200", response.json()


# --------------------------------------------------------------------------- #
# AC-PQ2: a hand-composed amendment AT the plan quantity is accepted
# --------------------------------------------------------------------------- #

def test_amend_at_the_plan_quantity_is_accepted():
    """AC-PQ2: AC-PQ1's row, decided by hand (`amend`) with components summing to the PLAN
    quantity (3200) rather than the owed one (2562) - still accepted, 200."""
    with blank_session() as db:
        world = _delivered_world(db, qty_ordered="3210", qty_delivered="638")
        batch = _change_and_batch(db, world, new_qty="3200")
        row = _only_row(db, batch)

        client, originals = _client(db, world["actor"])
        try:
            response = client.put(
                f"{BASE}/planning-changes/{batch.id}/rows/{row.id}",
                json={
                    "decision": "amend",
                    "composition": {
                        "project_line_id": str(world["line"].id),
                        "buy_qty": "3200",
                        "buy_reason": "ZZT no stock anywhere",
                    },
                },
            )
        finally:
            _restore(originals)

        assert response.status_code == 200, response.text


# --------------------------------------------------------------------------- #
# AC-PQ3: an amendment short of the plan quantity is still refused
# --------------------------------------------------------------------------- #

def test_amend_short_of_the_plan_quantity_is_still_refused():
    """AC-PQ3: AC-PQ1's row, decided by hand with components summing to the OWED quantity
    (2562) rather than the PLAN one (3200) - refused, 422
    `planning_change_composition_mismatch`. The composition must still add up to the whole
    plan quantity, never stop at what is left to deliver."""
    with blank_session() as db:
        world = _delivered_world(db, qty_ordered="3210", qty_delivered="638")
        batch = _change_and_batch(db, world, new_qty="3200")
        row = _only_row(db, batch)

        client, originals = _client(db, world["actor"])
        try:
            response = client.put(
                f"{BASE}/planning-changes/{batch.id}/rows/{row.id}",
                json={
                    "decision": "amend",
                    "composition": {
                        "project_line_id": str(world["line"].id),
                        "buy_qty": "2562",
                        "buy_reason": "ZZT no stock anywhere",
                    },
                },
            )
        finally:
            _restore(originals)

        assert response.status_code == 422, response.text
        assert response.json().get("code") == "planning_change_composition_mismatch", (
            response.json()
        )


# --------------------------------------------------------------------------- #
# AC-PQ4: `_row_open_qty` reads the plan quantity over the owed one
# --------------------------------------------------------------------------- #

def test_row_open_qty_is_the_plan_quantity_on_a_delivered_line():
    """AC-PQ4 (unit, no DB): given a proposal carrying BOTH `qty` (plan, 3200) and
    `qty_outstanding` (owed, 2562), `_row_open_qty` returns the plan quantity. Given a
    proposal with neither key at all, it falls back to `to_json["qty"]` - unchanged by
    this fix, the fallback this file's `_row_open_qty` docstring calls "the last resort"."""
    both = PlanningChangeRow(proposal_json={"qty": "3200", "qty_outstanding": "2562"})
    assert planning_change_service._row_open_qty(both) == Decimal("3200")

    neither = PlanningChangeRow(proposal_json={}, to_json={"qty": "3200"})
    assert planning_change_service._row_open_qty(neither) == Decimal("3200")


# --------------------------------------------------------------------------- #
# AC-PQ5: the board's own Confirm writes a second revision on a delivered line
# --------------------------------------------------------------------------- #

def test_board_confirm_of_a_planning_change_on_a_delivered_line_writes_revision_2():
    """AC-PQ5: `POST /sales-orders/{pso_id}/confirm` with the batch id (the board's own
    Confirm, `_confirm_a_planning_change`) hits the SAME open-quantity check
    `set_row_decision` does. `so_supply_decisions` ends with a second revision for the
    order and the first is superseded."""
    with blank_session() as db:
        world = _delivered_world(db, qty_ordered="3210", qty_delivered="638")
        batch = _change_and_batch(db, world, new_qty="3200")
        original_decision = _active_decision(db, world["order"].id)

        client, originals = _client(db, world["actor"])
        try:
            response = client.post(
                f"{BASE}/sales-orders/{world['order'].id}/confirm",
                json={
                    "batch_id": str(batch.id),
                    "lines": [_line_payload(
                        str(world["line"].id), buy_qty="3200",
                        buy_reason="ZZT no stock anywhere",
                    )],
                },
            )
        finally:
            _restore(originals)

        assert response.status_code == 200, response.text

        decisions = (
            db.query(SOSupplyDecision)
            .filter(SOSupplyDecision.project_sales_order_id == world["order"].id)
            .order_by(SOSupplyDecision.revision_no.asc())
            .all()
        )
        assert len(decisions) == 2, [d.state for d in decisions]
        assert str(decisions[0].id) == str(original_decision.id)
        assert decisions[0].state == DECISION_SUPERSEDED
        assert decisions[1].state == DECISION_ACTIVE


# --------------------------------------------------------------------------- #
# AC-PQ6: the floor-at-zero edge - a fully delivered, closed line still confirms
# --------------------------------------------------------------------------- #

def test_fully_delivered_closed_line_confirms_its_change():
    """AC-PQ6: `qty_ordered 1, qty_delivered 1` (owed floored at 0, plan 1). A raised
    planning change on this line (its required date moves - the qty itself is unchanged)
    still confirms: the composition balances against the plan quantity (1), never a
    floored owed of 0. `_open_of`'s own floor (`project_supply_service.py:417-429`) must
    never leak into what a confirm is asked to add up to."""
    with blank_session() as db:
        world = _delivered_world(db, qty_ordered="1", qty_delivered="1")
        batch = _change_and_batch(
            db, world, new_required_date=REQUIRED_DATE + timedelta(days=14),
        )
        row = _only_row(db, batch)

        client, originals = _client(db, world["actor"])
        try:
            response = client.put(
                f"{BASE}/planning-changes/{batch.id}/rows/{row.id}",
                json={"decision": "confirm"},
            )
        finally:
            _restore(originals)

        assert response.status_code == 200, response.text
