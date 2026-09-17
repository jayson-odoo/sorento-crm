"""Saved decisions on the planning board (S4 of `PLAN-scm-fulfilment-feedback-2sep.md`, R-F).

TEST-FIRST for Phase 2. Every assertion below is written from the contract the Phase 1
frontend was already built against (`_shared/services/fulfilmentPlanningService.ts`
`putLineDraft` / `deleteLineDraft`, `_shared/types/fulfilmentPlanning.types.ts`
`BoardLineDraft`), before `projects.so_supply_decision_drafts`, the model, the service or
the two routes exist. The right reason to fail today is a 405 on the route and an
ImportError on the model.

  PUT    /project-sales/fulfilment-planning/lines/{contribution_key}/draft
         body {decision} -> 200 {decision, saved_by, saved_at, stale}
  DELETE /project-sales/fulfilment-planning/lines/{contribution_key}/draft -> 204

`contribution_key` is the board's own `contributions[].key`, read off a real board read
here rather than spelled out, because the key IS the contract between the two sides.

Postgres via `tests/_pg_fixture.py::blank_session`, never sqlite. The fixture chain
(company, project, product, own + pool warehouses, the TestClient harness) is reused from
`tests/test_so_supply_confirmation.py` rather than re-declared; this file seeds its own
core sales order, mirror and stock on top.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from .test_so_supply_confirmation import (  # noqa: F401 - `api` is a fixture
    BASE,
    EDIT,
    MARKER as CONFIRM_MARKER,
    _act_as,
    _core_line,
    _core_so,
    _line_payload,
    _product,
    _project_line,
    _project_so,
    _stock,
    _user,
    api,
)

MARKER = "zzt-line-draft"

#: The composition a planner saves on the row. Opaque to the server, which stores it and
#: hands it back: the confirmation reads the body the frontend posts, never this.
DECISION = {
    "verdict": "amended",
    "reserve_qty": "10",
    "reserve": [{"location": "ZZT-BRW", "qty": "10"}],
    "borrow": [],
    "buy_qty": "0",
    "reason": "Taking it from the pool.",
}


def _uid() -> str:
    return str(uuid.uuid4())


def _world(api, *, pool_on_hand=100, qty="10"):
    """One core sales order with one line, adopted, on a pool that can cover it whole.

    Ladder v8 (R-B) lets a project line take HALF the pool's free pile, so covering 10
    whole takes 20 in the pool; 100 keeps every case here comfortably inside that.
    """
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=pool_on_hand)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered=qty)
    order = _project_so(db, world.project, so_id=core_so.id)
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()
    return client, world, core_so, core_line, order, line


def _board(client, core_so):
    response = client.get(
        f"{BASE}/fulfilment-planning/board",
        params={"orders": core_so.so_number, "granularity": "week"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _contribution(board, so_number: str) -> dict:
    return next(
        row for row in board["contributions"] if row["so_number"] == so_number
    )


def _save(client, key: str, decision=None, proposed=None):
    body = {"decision": decision or DECISION}
    if proposed is not None:
        body["proposed"] = proposed
    return client.put(f"{BASE}/fulfilment-planning/lines/{key}/draft", json=body)


# --------------------------------------------------------------------------- save


def test_saving_a_line_decision_answers_with_the_saver_and_the_time(api):
    """AC-4.1: the row is saved on the SERVER, and says who saved it and when.

    `saved_by` is the person's NAME, never their id: the pill's popover renders it and no
    identifier a human has to resolve is ever shown (PRINCIPLES, no UUIDs in the UI).
    """
    client, world, core_so, _core_line, _order, _line = _world(api)
    board = _board(client, core_so)
    contribution = _contribution(board, core_so.so_number)

    response = _save(client, contribution["key"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision"]["verdict"] == "amended"
    assert body["decision"]["reserve"][0]["qty"] == "10"
    assert body["saved_by"] == f"{CONFIRM_MARKER} Eling"
    assert body["saved_at"]
    # Saved against the suggestion in front of the planner, so nothing has changed yet.
    assert body["stale"] is False


def test_a_second_planner_saving_the_same_line_replaces_the_first(api):
    """AC-4.5: drafts are SHARED, one row per contribution key, and the popover names the
    NEWER saver. A second row would show the board two answers for one line."""
    from app.models.project_so import SOSupplyDecisionDraft

    client, world, core_so, _core_line, _order, _line = _world(api)
    db = world.db
    board = _board(client, core_so)
    key = _contribution(board, core_so.so_number)["key"]
    assert _save(client, key).status_code == 200

    second = _user(db, f"{MARKER} Mei")
    db.commit()
    _act_as(client, second)
    response = _save(
        client, key, decision={**DECISION, "buy_qty": "4", "reason": "Buying the rest."}
    )

    assert response.status_code == 200, response.text
    assert response.json()["saved_by"] == f"{MARKER} Mei"
    assert response.json()["decision"]["buy_qty"] == "4"
    assert (
        db.query(SOSupplyDecisionDraft)
        .filter(SOSupplyDecisionDraft.sales_order_id == core_so.id)
        .count()
        == 1
    ), "a save REPLACES the saved decision; it never adds a second row for one line"


def test_a_view_only_planner_cannot_save_a_decision(api):
    """Saving is a write and takes the EDIT permission, the same one Confirm takes."""
    from app.services.user_service import UserPermissionService

    client, world, core_so, _core_line, _order, _line = _world(api)
    board = _board(client, core_so)
    key = _contribution(board, core_so.so_number)["key"]

    original = UserPermissionService.check_user_has_permission
    UserPermissionService.check_user_has_permission = (
        lambda self, uid, slug: slug != EDIT
    )
    try:
        response = _save(client, key)
        removal = client.delete(f"{BASE}/fulfilment-planning/lines/{key}/draft")
    finally:
        UserPermissionService.check_user_has_permission = original

    assert response.status_code == 403, response.text
    assert removal.status_code == 403, removal.text


@pytest.mark.parametrize(
    "key",
    [
        "not-a-key",
        # Three parts: a bucket is missing.
        "d24f5c1e-0000-0000-0000-000000000000|3|ZZT-ITEM",
        # A line number that is not a number.
        "d24f5c1e-0000-0000-0000-000000000000|three|ZZT-ITEM|2026-09-07",
        # A sales order id that is not an id.
        "SO391698|3|ZZT-ITEM|2026-09-07",
        # An item code longer than the column (`String(100)`).
        f"d24f5c1e-0000-0000-0000-000000000000|3|{'Z' * 101}|2026-09-07",
        # A bucket key longer than the column (`String(32)`).
        f"d24f5c1e-0000-0000-0000-000000000000|3|ZZT-ITEM|{'2' * 33}",
    ],
)
def test_a_malformed_contribution_key_is_refused(api, key):
    """The key is `${sales_order_id}|${line_no}|${item_code}|${bucket_key}` and nothing
    else. A key the server cannot read is a 422, never a row saved under a key no board
    will ever ask for again."""
    client, _w, _core_so, _core_line, _order, _line = _world(api)

    response = _save(client, key)

    assert response.status_code == 422, response.text


# ------------------------------------------------------- S3: a key naming no real line


def test_saving_against_an_order_outside_the_caller_s_company_scope_is_refused(api):
    """S3, captain ruling: an order this company cannot see is refused, not saved under a
    key nobody will ever ask for again."""
    client, world, _core_so, _core_line, _order, _line = _world(api)
    unknown_order = _uid()

    response = _save(client, f"{unknown_order}|1|ZZT-ITEM|2026-09-07")

    assert response.status_code == 422, response.text


# ------------------------------------------- S3 (fix round 5): an authored PSO on the wire

def test_an_authored_pso_reconciled_line_does_not_change_a_sibling_line_s_number(api):
    """S3 (fix round 5): `_resolve_core_line`'s own numbering read every
    `ProjectSalesOrderLine`, an AUTHORED PSO's included - `FulfilmentBoardService.
    _mirror_addressing` (which numbers the board's own contribution keys) is scoped to the
    record that HOLDS the core order (`ProjectSalesOrder.so_id.isnot(None)`), so an order
    with a sibling line reconciled to an unrelated AUTHORED PSO numbered its OWN lines
    differently on the two sides of the same save.

    `uq_projects_so_line_core_line` allows exactly one holder per core line, so the
    collision cannot be on the SAME line (`_resolve_core_line`'s own docstring already
    covers that: the identity is the core line id, not this numbering dict) - it is between
    TWO SIBLING lines of the SAME core order, one reconciled to the true mirror and one
    reconciled to an unrelated authored PSO.
    """
    client, world, core_so, core_line_a, _order, _mirror_line = _world(api)
    db = world.db
    # A second, LATER-due line on the same core order, reconciled to an unrelated AUTHORED
    # PSO (so_id is None: it does not hold THIS core order) under an arbitrary line_no.
    product_b = _product(db)
    core_line_b = _core_line(
        db, core_so, product_b, world.own_wh, qty_ordered="5",
        required_date=core_line_a.required_date + timedelta(days=5),
    )
    authored = _project_so(db, world.project, so_id=None)
    _project_line(db, authored, line_no=1, product=product_b, core_line=core_line_b)
    db.commit()

    board = _board(client, core_so)
    contribution_a = next(
        row
        for row in board["contributions"]
        if row["so_number"] == core_so.so_number and row["item_code"] == world.product.product_code
    )
    key = contribution_a["key"]

    response = _save(client, key)

    assert response.status_code == 200, response.text

    from app.models.project_so import SOSupplyDecisionDraft

    draft = (
        db.query(SOSupplyDecisionDraft)
        .filter(SOSupplyDecisionDraft.sales_order_id == core_so.id)
        .one()
    )
    # The SAME core line the board's own key named, whatever number the unrelated authored
    # line happens to carry.
    assert draft.core_line_id == core_line_a.id


def test_saving_against_another_company_s_real_order_is_refused_not_saved(api):
    """S3: a syntactically real order that belongs to ANOTHER company reads the same as one
    that never existed - fail-closed, the way every other owned row here is scoped."""
    from app.models.project_so import SOSupplyDecisionDraft
    from .test_so_supply_confirmation import _second_company

    client, world, core_so, _core_line, _order, _line = _world(api)
    db = world.db
    other_company = _second_company(db)
    other_so = _core_so(db, other_company)
    db.commit()

    response = _save(client, f"{other_so.id}|1|ZZT-ITEM|2026-09-07")

    assert response.status_code == 422, response.text
    assert (
        db.query(SOSupplyDecisionDraft)
        .filter(SOSupplyDecisionDraft.sales_order_id == other_so.id)
        .count()
        == 0
    )


def test_saving_a_real_order_with_a_bogus_line_number_is_refused(api):
    """S3: the order exists, but no line on it derives to this number."""
    client, world, core_so, _core_line, _order, _line = _world(api)

    response = _save(client, f"{core_so.id}|999|ZZT-ITEM|2026-09-07")

    assert response.status_code == 422, response.text


def test_saving_a_valid_uuid_that_names_no_sales_order_is_422_not_500(api):
    """S3: a syntactically valid UUID that names something OTHER than a sales order (a
    product, here) must read as "no such line", never as an unhandled server error."""
    client, world, _core_so, _core_line, _order, _line = _world(api)

    response = _save(client, f"{world.product.id}|1|ZZT-ITEM|2026-09-07")

    assert response.status_code == 422, response.text
    # Never raw DB/SQL text (S3): the 422 states its own fixed message.
    body = str(response.json()).lower()
    assert "select" not in body and "constraint" not in body


def test_saving_a_line_whose_order_also_carries_an_unplanned_line_resolves_correctly(api):
    """Found by hand on the real lane (SO391698), not by a unit test: `_resolve_core_line`
    used to number EVERY line of the order, while the board numbers only the lines its own
    predicate counts (`SalesOrder.status IN ('open','closed')`, `demand_class == "project"`,
    `is_undecided_demand()` on the line) - `_demand_rows` in
    `project_fulfilment_board_service.py`. An order carrying a line the board leaves out, beside
    lines it takes, got a DIFFERENT ordinal on each side: the board handed out "line 2" for the
    second line it counted, and the resolver, counting the excluded one too, read ordinal 2 as a
    different row - "That sales order line does not exist" for a line that plainly did, on a
    real board.

    THE EXCLUDED LINE IS NOW A CANCELLED ONE. It used to be a `closed` one, which under the
    14 September 2026 rule is ordinary board demand - a line the book closed by delivering it,
    that nobody decided a source for, is exactly what this lane puts on the board. Cancelled is
    what the board still leaves out, so it is what can still shift an ordinal. The subject of
    the test is unchanged: the board's ordinal and the resolver's ordinal must be the same one.

    Three core lines, DIFFERENT products (a same-product fixture would resolve to the WRONG
    line silently instead of 422ing, which is worse and would not have failed this test),
    the cancelled one sorted FIRST (earliest date) so it shifts every ordinal after it if it
    is wrongly counted."""
    client, world = api
    db = world.db
    product_b = _product(db)
    product_c = _product(db)
    _stock(db, world.product, world.pool_wh, on_hand=100)
    _stock(db, product_b, world.pool_wh, on_hand=100)
    _stock(db, product_c, world.pool_wh, on_hand=100)
    core_so = _core_so(db, world.company_id)
    cancelled = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="5",
                           required_date=date(2026, 1, 1))
    cancelled.line_status = "cancelled"
    _core_line(db, core_so, product_b, world.own_wh, qty_ordered="10",
              required_date=date(2026, 6, 1))
    _core_line(db, core_so, product_c, world.own_wh, qty_ordered="8",
              required_date=date(2026, 7, 1))
    db.commit()

    board = _board(client, core_so)
    contributions = board["contributions"]
    assert len(contributions) == 2, "the cancelled line must not appear on the board at all"
    target = next(row for row in contributions if row["line_no"] == 2)
    assert target["item_code"] == product_c.product_code, (
        "sanity: line 2 must be the LATER open line (product_c), never product_b shifted "
        "into its place by counting the closed line"
    )

    response = _save(client, target["key"])
    assert response.status_code == 200, response.text

    # And the SAVE landed on the right line: re-reading the board shows the draft on
    # product_c's contribution, never on product_b's (the wrong-line resolution this test
    # exists to catch would have silently saved against product_b's key instead).
    again = _board(client, core_so)
    saved_c = next(row for row in again["contributions"] if row["item_code"] == product_c.product_code)
    saved_b = next(row for row in again["contributions"] if row["item_code"] == product_b.product_code)
    assert saved_c["draft"] is not None
    assert saved_b["draft"] is None


# --------------------------------------------------------------------------- the board


def test_the_board_carries_a_saved_decision_back_on_the_next_read(api):
    """AC-4.2: reload the page, or open the board on another device, and the line is still
    saved. Asserted on the JSON rather than on the service, because a field the response
    model does not declare is dropped in silence."""
    client, world, core_so, _core_line, _order, _line = _world(api)
    board = _board(client, core_so)
    contribution = _contribution(board, core_so.so_number)
    assert contribution["draft"] is None, "nobody has saved this line yet"

    assert _save(client, contribution["key"]).status_code == 200

    again = _board(client, core_so)
    saved = _contribution(again, core_so.so_number)["draft"]
    assert saved is not None, "the board must carry the saved decision back"
    assert saved["decision"]["verdict"] == "amended"
    assert saved["saved_by"] == f"{CONFIRM_MARKER} Eling"
    assert saved["stale"] is False
    # And on the CELL's own copy of the contribution, which is what the grid renders.
    cell_row = again["cells"][0]["contributions"][0]
    assert cell_row["draft"]["decision"]["verdict"] == "amended"


def test_undo_removes_the_saved_decision_and_the_board_reads_null_again(api):
    """AC-4.3: Undo deletes the draft; the pill returns to Suggested."""
    client, world, core_so, _core_line, _order, _line = _world(api)
    board = _board(client, core_so)
    key = _contribution(board, core_so.so_number)["key"]
    assert _save(client, key).status_code == 200

    removal = client.delete(f"{BASE}/fulfilment-planning/lines/{key}/draft")

    assert removal.status_code == 204, removal.text
    assert _contribution(_board(client, core_so), core_so.so_number)["draft"] is None


def test_undo_on_a_line_nobody_saved_is_a_404(api):
    client, world, core_so, _core_line, _order, _line = _world(api)
    key = _contribution(_board(client, core_so), core_so.so_number)["key"]

    response = client.delete(f"{BASE}/fulfilment-planning/lines/{key}/draft")

    assert response.status_code == 404, response.text


def test_a_saved_line_whose_plan_qty_changes_reads_stale(api):
    """AC-4.4, second half, S1 (code review round 3, captain ruling): staleness is judged
    on the LINE's own facts - plan quantity and required date - never on the proposal.

    The proposal depends on which orders share the board, its granularity and its window,
    so comparing IT flipped `stale` falsely across views and silently dropped a saved line
    from Confirm the moment a planner opened a different one. The line's own facts do not
    move with the view - only with a real change, exactly like this one.

    AC-S2-17: STALE MEANS THE ASK CHANGED, AND THE ASK IS THE PLAN QUANTITY. The board asks
    for `coalesce(qty_required, qty_ordered)` now, so that is the figure a saved suggestion
    was made against and the figure staleness compares. The customer raising the order from
    10 to 14 is the change - the planner decided 10 units of supply and there are 14 to find."""
    client, world, core_so, core_line, _order, _line = _world(api)
    db = world.db
    board = _board(client, core_so)
    contribution = _contribution(board, core_so.so_number)
    assert contribution["qty"] == "10", "sanity: saved against the plan quantity"
    assert _save(client, contribution["key"]).status_code == 200

    # The book raises the ordered quantity: the ASK moves, the same fact an SO re-upload
    # changes, and the composition the planner saved no longer covers it.
    core_line.qty_ordered = Decimal("14")
    db.commit()

    after = _contribution(_board(client, core_so), core_so.so_number)
    assert after["draft"]["stale"] is True
    # Still SAVED, and still readable: staleness is a warning on the row, not a deletion.
    assert after["draft"]["decision"]["verdict"] == "amended"


def test_a_part_delivery_does_not_make_a_saved_line_stale(api):
    """AC-S2-17, the other side. A delivery is not a change to the ask.

    The planner saved a decision about where 10 units come from. Four of them shipping does
    not make that decision out of date - the board still asks for 10, because a delivered unit
    nobody sourced is a unit to put back, and the saved composition still answers the question
    it was saved against. Flagging it stale would send CS back to re-decide a line nothing had
    happened to, and drop it out of Confirm until they did.

    This is the assertion that pins the two sides together: the snapshot
    (`project_line_draft_service._line_snapshot`) and its reader
    (`sales_order_service._saved_is_stale`) must BOTH read the plan quantity. Either one left
    on the still-owed figure and this line reads stale.
    """
    client, world, core_so, core_line, _order, _line = _world(api)
    db = world.db
    contribution = _contribution(_board(client, core_so), core_so.so_number)
    assert _save(client, contribution["key"]).status_code == 200

    core_line.qty_delivered = Decimal("4")
    db.commit()

    after = _contribution(_board(client, core_so), core_so.so_number)
    assert after["qty"] == "10", "the board still asks for the whole 10"
    assert after["draft"]["stale"] is False, (
        "a delivery did not change what the planner was asked to decide"
    )


def test_a_draft_saved_on_a_delivered_line_is_not_stale_straight_away(api):
    """AC-S2-17, and the case where the two sides being out of step actually bites.

    The WRITER (`project_line_draft_service._line_snapshot`) still freezes `_open_of` - the
    still-owed figure - while the board's READER already compares `row.qty`, the plan quantity.
    On a line with nothing delivered the two agree and nothing shows. On SO421404's own shape -
    3 ordered, 3 delivered, the very line this lane exists to plan - the snapshot is written as
    0 and compared against 3, so a suggestion comes back flagged STALE the instant it is saved,
    before anybody has touched anything.

    That reads to CS as "somebody changed this line under me", and a stale draft is dropped
    from Confirm - so the delivered line they just decided cannot be confirmed at all. Both
    sides have to speak the plan quantity, which is what makes this a coupling rather than a
    preference about which figure is nicer.
    """
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=100)
    core_so = _core_so(db, world.company_id)
    core_so.status = "closed"
    core_line = _core_line(
        db, core_so, world.product, world.own_wh, qty_ordered="3", qty_delivered="3",
    )
    core_line.line_status = "closed"
    order = _project_so(db, world.project, so_id=core_so.id)
    _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()

    contribution = _contribution(_board(client, core_so), core_so.so_number)
    assert contribution["qty"] == "3", "sanity: the board plans the ordered quantity"
    assert _save(client, contribution["key"]).status_code == 200

    after = _contribution(_board(client, core_so), core_so.so_number)
    assert after["draft"] is not None
    assert after["draft"]["stale"] is False, (
        "nothing changed between the save and the read; the snapshot and the board have to "
        "be comparing the same figure"
    )


def test_a_saved_line_read_under_a_different_granularity_is_not_stale(api):
    """S1: the bug this rule replaces. Comparing the ENGINE's proposal (rather than the
    line's own facts) meant the same saved line, with nothing about it actually changed,
    could read `stale` on one view of the board and not another - here, week against day -
    because the proposal depends on the board's own granularity. Nothing about the LINE
    moved, so it must read the same either way."""
    client, world, core_so, _core_line, _order, _line = _world(api)
    board = _board(client, core_so)
    contribution = _contribution(board, core_so.so_number)
    assert _save(client, contribution["key"]).status_code == 200
    assert _contribution(board, core_so.so_number)["draft"] is None, (
        "the FIRST read predates the save; sanity on the fixture, not the assertion"
    )

    day = client.get(
        f"{BASE}/fulfilment-planning/board",
        params={"orders": core_so.so_number, "granularity": "day"},
    )
    assert day.status_code == 200, day.text
    after = _contribution(day.json(), core_so.so_number)
    assert after["draft"] is not None, "the save must still be found under a different view"
    assert after["draft"]["stale"] is False


def _pool_stock(db, world):
    from app.models.inventory import Stock

    return (
        db.query(Stock)
        .filter(
            Stock.product_id == world.product.id,
            Stock.warehouse_id == world.pool_wh.id,
        )
        .one()
    )


def test_a_draft_saved_in_another_company_is_invisible_here(api):
    """Company isolation, fail-closed like every other owned row: a draft belongs to the
    company it was saved in, and the board of another company never reads it."""
    from app.models.project_so import SOSupplyDecisionDraft
    from .test_so_supply_confirmation import _second_company

    client, world, core_so, core_line, _order, _line = _world(api)
    db = world.db
    contribution = _contribution(_board(client, core_so), core_so.so_number)
    other = _second_company(db)
    db.add(
        SOSupplyDecisionDraft(
            id=_uid(),
            company_id=other,
            sales_order_id=core_so.id,
            core_line_id=core_line.id,
            line_no=contribution["line_no"],
            item_code=contribution["item_code"],
            bucket_key=contribution["key"].split("|")[3],
            decision=DECISION,
            line_snapshot=None,
            saved_by=world.eling,
        )
    )
    db.commit()

    assert _contribution(_board(client, core_so), core_so.so_number)["draft"] is None


# --------------------------------------------------------------------------- confirm


def test_confirming_the_order_deletes_the_draft_it_promotes(api):
    """AC-4.4, first half: Confirm promotes the saved lines and the draft goes with the
    same write. A draft left behind would re-seed the panel on the next read and offer to
    confirm a decision that has already been confirmed."""
    from app.models.project_so import SOSupplyDecisionDraft

    client, world, core_so, _core_line, order, line = _world(api)
    db = world.db
    key = _contribution(_board(client, core_so), core_so.so_number)["key"]
    assert _save(client, key).status_code == 200

    response = client.post(
        f"{BASE}/fulfilment-planning/confirm-all",
        json={
            "orders": [
                {
                    "pso_id": order.id,
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
    assert response.json()["results"][0]["ok"] is True, response.text
    assert (
        db.query(SOSupplyDecisionDraft)
        .filter(SOSupplyDecisionDraft.sales_order_id == core_so.id)
        .count()
        == 0
    )
    after = _contribution(_board(client, core_so), core_so.so_number)
    assert after["covered"] is True
    assert after["draft"] is None


def test_a_confirmation_that_fails_leaves_the_saved_decision_in_place(api):
    """The delete rides the confirmation's own transaction, so an order that refuses keeps
    its drafts: the planner has lost nothing and can fix the line and press again."""
    from app.models.project_so import SOSupplyDecisionDraft

    client, world, core_so, _core_line, order, line = _world(api)
    db = world.db
    key = _contribution(_board(client, core_so), core_so.so_number)["key"]
    assert _save(client, key).status_code == 200

    response = client.post(
        f"{BASE}/fulfilment-planning/confirm-all",
        json={
            "orders": [
                {
                    "pso_id": order.id,
                    # A line id that is not on this order at all: refused whole.
                    "lines": [_line_payload(_uid(), buy_qty="10")],
                }
            ]
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["ok"] is False, response.text
    assert (
        db.query(SOSupplyDecisionDraft)
        .filter(SOSupplyDecisionDraft.sales_order_id == core_so.id)
        .count()
        == 1
    ), "a refused confirmation must not take the planner's saved decision with it"
    assert _contribution(_board(client, core_so), core_so.so_number)["draft"] is not None


# ------------------------------------------------- C2: the identity a draft is keyed by
#
# A board line number is POSITIONAL whenever the order's lines are not all mirrored
# (`FulfilmentBoardService._line_numbers`), so it moves - a re-upload that changes an
# earlier line's required date renumbers every line after it, and a mirror that numbers one
# line 10 while the board counts it 2 gives the same physical line two numbers at once. The
# draft's durable identity is therefore the CORE sales order line, and the number is only
# what it was saved under.


def _two_open_lines(api, *, mirror_second=False, mirror_line_no=10):
    """One core order with two OPEN lines of different products, at two dates.

    Different products, because the board numbers by (required date, item code, line id)
    and a same-product pair would resolve to the wrong line in silence rather than fail.
    `mirror_second` adopts the order and mirrors ONLY the later line, which is what makes
    `_line_numbers` fall back to the POSITIONAL index for the whole order.
    """
    client, world = api
    db = world.db
    first_product = _product(db)
    second_product = _product(db)
    _stock(db, first_product, world.pool_wh, on_hand=100)
    _stock(db, second_product, world.pool_wh, on_hand=100)
    core_so = _core_so(db, world.company_id)
    first = _core_line(
        db, core_so, first_product, world.own_wh, qty_ordered="7",
        required_date=date(2026, 6, 1),
    )
    second = _core_line(
        db, core_so, second_product, world.own_wh, qty_ordered="10",
        required_date=date(2026, 7, 1),
    )
    order = mirror = None
    if mirror_second:
        order = _project_so(db, world.project, so_id=core_so.id)
        mirror = _project_line(
            db, order, line_no=mirror_line_no, product=second_product, core_line=second,
        )
    db.commit()
    return client, world, core_so, first, second, order, mirror


def _by_item(board, product) -> dict:
    return next(
        row for row in board["contributions"]
        if row["item_code"] == product.product_code
    )


def test_confirming_deletes_the_draft_even_when_the_board_numbers_lines_positionally(api):
    """C2 (code review round 4). Only ONE of the order's two lines has a mirror, so
    `_line_numbers` gives the whole order POSITIONAL numbers - the saved line is board line
    2 while its mirror row calls itself line 10.

    `_write_decision` deleted the promoted drafts by the MIRROR's `line_no`, so nothing
    matched: the draft survived its own confirmation and re-attached beside the frozen
    decision, offering the planner a line that had already been confirmed.
    """
    from app.models.project_so import SOSupplyDecisionDraft

    client, world, core_so, _first, second, order, mirror = _two_open_lines(
        api, mirror_second=True
    )
    db = world.db
    contribution = _by_item(_board(client, core_so), second.product)
    assert contribution["line_no"] == 2, (
        "sanity: the board numbers positionally here, so the saved line is 2 and not the "
        "mirror's own 10 - which is the divergence this test is about"
    )
    assert mirror.line_no == 10
    assert _save(client, contribution["key"]).status_code == 200

    response = client.post(
        f"{BASE}/fulfilment-planning/confirm-all",
        json={
            "orders": [
                {
                    "pso_id": order.id,
                    "lines": [
                        _line_payload(
                            mirror.id,
                            reserve=[{"warehouse_id": world.pool_wh.id, "qty": "10"}],
                        )
                    ],
                }
            ]
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["ok"] is True, response.text
    assert (
        db.query(SOSupplyDecisionDraft)
        .filter(SOSupplyDecisionDraft.sales_order_id == core_so.id)
        .count()
        == 0
    ), "the confirmation must take the draft it promoted with it"
    after = _by_item(_board(client, core_so), second.product)
    assert after["covered"] is True
    assert after["draft"] is None


def test_a_saved_line_survives_the_board_renumbering_its_lines(api):
    """C2. A re-upload that moves an EARLIER line's required date renumbers every line
    after it, and the draft has to stay on the physical line it was saved against.

    Keyed by (order, line number, item code) it did not: the save was made under line 2 and
    the line became line 1, so the board read `draft: null` on a line somebody had saved and
    the planner's work was invisible until the date moved back.
    """
    client, world, core_so, first, second, _order, _mirror = _two_open_lines(api)
    db = world.db
    contribution = _by_item(_board(client, core_so), second.product)
    assert contribution["line_no"] == 2
    assert _save(client, contribution["key"]).status_code == 200

    # The re-upload: the FIRST line's required date moves past the second's, so the board's
    # positional numbering swaps them.
    first.required_date = date(2026, 8, 1)
    db.commit()

    board = _board(client, core_so)
    moved = _by_item(board, second.product)
    assert moved["line_no"] == 1, "sanity: the saved line has been renumbered"
    assert moved["draft"] is not None, (
        "the draft belongs to the LINE, not to the number it happened to carry"
    )
    assert moved["draft"]["decision"]["verdict"] == "amended"
    # Its OWN facts did not move - only the line before it did - so it is not stale (S1).
    assert moved["draft"]["stale"] is False
    # And it did not follow the number onto the other line.
    assert _by_item(board, first.product)["draft"] is None


def test_re_saving_the_same_line_under_a_new_line_number_updates_the_one_row(api):
    """C2. Same physical line, a new board number, one saved decision - never two rows,
    which is what a key of (order, line number, item code) produced the moment the board
    renumbered and the planner saved again."""
    from app.models.project_so import SOSupplyDecisionDraft

    client, world, core_so, first, second, _order, _mirror = _two_open_lines(api)
    db = world.db
    assert _save(
        client, _by_item(_board(client, core_so), second.product)["key"]
    ).status_code == 200

    first.required_date = date(2026, 8, 1)
    db.commit()
    renumbered = _by_item(_board(client, core_so), second.product)
    assert renumbered["line_no"] == 1
    assert _save(
        client, renumbered["key"], decision={**DECISION, "buy_qty": "3"}
    ).status_code == 200

    rows = (
        db.query(SOSupplyDecisionDraft)
        .filter(SOSupplyDecisionDraft.sales_order_id == core_so.id)
        .all()
    )
    assert len(rows) == 1, "one physical line, one saved decision"
    assert rows[0].line_no == 1, "and it records the number it was last saved under"
    assert rows[0].decision["buy_qty"] == "3"


def test_saving_with_a_proposal_round_trips_it_on_the_board(api):
    """D12 (#573, captain 3 Sep): the draft keeps the engine's suggestion at save time, in
    the board's own `BoardSource` shape - the caller's own `sources` for this contribution.

    Never read for staleness (S1 still holds, `test_a_saved_line_whose_outstanding_qty_
    changes_reads_stale` proves it separately) - this exists so the Sales Order page's
    Suggested column can read a saved-but-unconfirmed line the same way the board's list
    view already reads a live composition.
    """
    client, world, core_so, _core_line, _order, _line = _world(api)
    board = _board(client, core_so)
    contribution = _contribution(board, core_so.so_number)
    proposed = [
        {
            "kind": "reserve",
            "qty": "10",
            "location": "ZZT-BRW",
            "reason": "Reserve from BRW",
            "rung": "pool",
        }
    ]

    response = _save(client, contribution["key"], proposed=proposed)

    assert response.status_code == 200, response.text
    assert response.json()["proposed"][0]["location"] == "ZZT-BRW"

    saved = _contribution(_board(client, core_so), core_so.so_number)["draft"]
    assert saved["proposed"][0]["kind"] == "reserve"
    assert saved["proposed"][0]["location"] == "ZZT-BRW"
    assert saved["proposed"][0]["qty"] == "10"


def test_saving_with_no_proposal_still_saves_the_decision(api):
    """`proposed` is OPTIONAL and additive (D12): an older client that never sends it saves
    exactly as it always has."""
    client, world, core_so, _core_line, _order, _line = _world(api)
    board = _board(client, core_so)
    contribution = _contribution(board, core_so.so_number)

    response = _save(client, contribution["key"])

    assert response.status_code == 200, response.text
    assert response.json()["proposed"] is None

    saved = _contribution(_board(client, core_so), core_so.so_number)["draft"]
    assert saved["proposed"] is None


def test_a_re_save_with_no_proposal_keeps_the_one_already_stored(api):
    """A re-save the caller could not resolve a contribution for must not ERASE the
    suggestion the first save stored.

    `proposed` is optional (the test above), and "absent" has always meant "I am not
    telling you about it" - so the column keeps what it holds. The screen that reads it is
    the Sales Order page's Suggested column (D12, #573), and a second Save from a surface
    that has no board contribution to hand would otherwise blank it back to Decided "-".
    """
    client, world, core_so, _core_line, _order, _line = _world(api)
    key = _contribution(_board(client, core_so), core_so.so_number)["key"]
    proposed = [
        {
            "kind": "reserve",
            "qty": "10",
            "location": "ZZT-BRW",
            "reason": "Reserve from BRW",
            "rung": "pool",
        }
    ]
    assert _save(client, key, proposed=proposed).status_code == 200

    again = _save(client, key)

    assert again.status_code == 200, again.text
    assert again.json()["proposed"][0]["location"] == "ZZT-BRW"
    saved = _contribution(_board(client, core_so), core_so.so_number)["draft"]
    assert saved["proposed"][0]["qty"] == "10"


# --------------------------------------------------------------------------- #
# AC-S2-16: the draft resolver's line set is the BOARD's                       #
# (`PLAN-fulfilment-board-plans-delivered-lines.md`)                           #
#                                                                             #
# Found on the lane's own browser walk, 14 September 2026, not by a unit test - #
# the same way SO391698's ordinal bug above was. A Completed order with three   #
# delivered undecided lines opened the board and proposed Buy 1 on each, and    #
# then every one of the three `Save all suggested` PUTs came back 422: the      #
# board had been widened to `SalesOrder.status IN ('open','closed')` plus       #
# `is_undecided_demand()`, and `_resolve_core_line` was still on                #
# `status == 'open'` plus `is_open_demand()`.                                   #
#                                                                             #
# The resolver reads a key THE BOARD JUST HANDED OUT, so a set narrower than    #
# the board's refuses a line the planner is looking at, and there is nothing on #
# screen to explain it. That coupling is the criterion, not the two spellings:  #
# whatever the board admits, this must resolve.                                 #
# --------------------------------------------------------------------------- #


def _delivered_closed_order(api, *, qty="3"):
    """SO421404's own shape: Completed, one line ordered and delivered whole, undecided."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=100)
    core_so = _core_so(db, world.company_id)
    core_so.status = "closed"
    core_line = _core_line(
        db, core_so, world.product, world.own_wh, qty_ordered=qty, qty_delivered=qty,
    )
    core_line.line_status = "closed"
    order = _project_so(db, world.project, so_id=core_so.id)
    line = _project_line(db, order, line_no=10, product=world.product, core_line=core_line)
    db.commit()
    return client, world, core_so, core_line, order, line


def test_a_draft_saves_and_deletes_on_a_closed_orders_delivered_line(api):
    """AC-S2-16. The key comes off a real board read, as everywhere else in this file: it IS
    the contract between the two sides, and spelling it out by hand here would prove the
    resolver agrees with the test rather than with the board."""
    client, _world, core_so, _core_line, _order, _line = _delivered_closed_order(api)

    board = _board(client, core_so)
    contribution = _contribution(board, core_so.so_number)
    assert contribution["qty"] == "3", "sanity: the board plans the ordered quantity"
    assert contribution["qty_delivered"] == "3"

    saved = _save(client, contribution["key"])
    assert saved.status_code == 200, saved.text
    assert saved.json()["decision"]["verdict"] == "amended"

    # And it comes back on the next read, so the save landed on THIS line and not beside it.
    again = _contribution(_board(client, core_so), core_so.so_number)
    assert again["draft"] is not None

    removed = client.delete(
        f"{BASE}/fulfilment-planning/lines/{contribution['key']}/draft"
    )
    assert removed.status_code == 204, removed.text
    assert _contribution(_board(client, core_so), core_so.so_number)["draft"] is None


def test_a_draft_on_a_cancelled_line_is_still_refused(api):
    """The other half of AC-S2-16, and the reason it is a coupling rather than "resolve
    anything": the board never offers a cancelled line, so a key naming one did not come from
    a board and must not resolve. Widening the resolver past `is_undecided_demand()` would
    let a planner save a decision on demand nobody owes."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=100)
    core_so = _core_so(db, world.company_id)
    core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="9")
    core_line.line_status = "cancelled"
    core_line.qty_delivered = Decimal("4")
    db.commit()

    assert _board(client, core_so)["contributions"] == [], (
        "sanity: a cancelled line is not on the board, so no key for it was ever issued"
    )

    # Built by hand for exactly that reason - there is no board key to read.
    key = f"{core_so.id}|1|{world.product.product_code}|2026-08-31"
    response = _save(client, key)

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "board_contribution_line_not_found"


# --------------------------------------------------------------------------- #
# R1 (`PLAN-board-draft-on-confirmed-line.md`): a covered line refuses a plain #
# save. Covered means an ACTIVE `SOSupplyDecision` on the mirror order whose   #
# `line_snapshots[].core_line_id` names this core line - the only draft such a #
# line still accepts is an amendment. TEST-FIRST: `save_draft` carries no gate #
# yet, so every 409 below is a 200 today.                                     #
# --------------------------------------------------------------------------- #


def _confirm_full_qty(client, world, order, line, qty="10"):
    """Confirms `line` whole, off the pool, so an ACTIVE decision covers it (R1)."""
    response = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(
                    line.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": qty}]
                )
            ]
        },
    )
    assert response.status_code == 200, response.text
    return response


def _approval_body():
    return {
        "verdict": "approved",
        "reserve_qty": "10",
        "reserve": [{"location": "ZZT-BRW", "qty": "10"}],
        "borrow": [],
        "buy_qty": "0",
    }


def test_a_plain_approval_on_a_confirmed_line_is_refused(api):
    """AC-B1: an ACTIVE decision already covers the line, so a plain approve is refused with
    409 `board_line_already_confirmed`, and nothing is written."""
    from app.models.project_so import SOSupplyDecisionDraft

    client, world, core_so, core_line, order, line = _world(api)
    db = world.db
    key = _contribution(_board(client, core_so), core_so.so_number)["key"]
    _confirm_full_qty(client, world, order, line)

    response = _save(client, key, decision=_approval_body())

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "board_line_already_confirmed"
    assert (
        db.query(SOSupplyDecisionDraft)
        .filter(SOSupplyDecisionDraft.core_line_id == str(core_line.id))
        .count()
        == 0
    )


def test_a_plain_rejection_on_a_confirmed_line_is_refused(api):
    """AC-B2: the other verdict R1 refuses outright on a covered line."""
    from app.models.project_so import SOSupplyDecisionDraft

    client, world, core_so, core_line, order, line = _world(api)
    db = world.db
    key = _contribution(_board(client, core_so), core_so.so_number)["key"]
    _confirm_full_qty(client, world, order, line)

    response = _save(client, key, decision={"verdict": "rejected", "reason": "local"})

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "board_line_already_confirmed"
    assert (
        db.query(SOSupplyDecisionDraft)
        .filter(SOSupplyDecisionDraft.core_line_id == str(core_line.id))
        .count()
        == 0
    )


def test_an_amendment_on_a_confirmed_line_still_saves(api):
    """AC-B3: the amend path is untouched by R1 - it is the one verdict a covered line still
    takes."""
    from app.models.project_so import SOSupplyDecisionDraft

    client, world, core_so, core_line, order, line = _world(api)
    db = world.db
    key = _contribution(_board(client, core_so), core_so.so_number)["key"]
    _confirm_full_qty(client, world, order, line)

    response = _save(client, key, decision=DECISION)

    assert response.status_code == 200, response.text
    assert (
        db.query(SOSupplyDecisionDraft)
        .filter(SOSupplyDecisionDraft.core_line_id == str(core_line.id))
        .count()
        == 1
    )


def test_an_approval_on_an_uncovered_line_still_saves(api):
    """AC-B4: regression guard, NOT a red test - no confirm at all, so the line is not
    covered and the ordinary save keeps answering 200, exactly as it does today. This pins
    R1's gate as a NEW refusal on a COVERED line, never a change to the save every other test
    in this file already relies on."""
    client, world, core_so, core_line, order, line = _world(api)
    key = _contribution(_board(client, core_so), core_so.so_number)["key"]

    response = _save(client, key, decision=_approval_body())

    assert response.status_code == 200, response.text


def test_a_line_whose_only_decision_is_superseded_is_not_covered(api):
    """AC-B5: covered means an ACTIVE decision, never a superseded one. The ONLY decision on
    this line is downgraded to superseded directly (rather than reached by reconfirming, which
    is `test_reconfirming_supersedes_the_active_decision_and_increments_the_revision`'s own
    case), leaving the line with no active decision at all - exactly the case R1 must not
    catch."""
    from app.models.project_so import DECISION_SUPERSEDED, SOSupplyDecision

    client, world, core_so, core_line, order, line = _world(api)
    db = world.db
    key = _contribution(_board(client, core_so), core_so.so_number)["key"]
    _confirm_full_qty(client, world, order, line)

    decision = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id)
        .one()
    )
    decision.state = DECISION_SUPERSEDED
    db.commit()

    response = _save(client, key, decision=_approval_body())

    assert response.status_code == 200, response.text


def test_the_confirmed_line_refusal_states_the_exact_sentence(api):
    """AC-B6: the message a planner reads when R1 refuses their save."""
    client, world, core_so, core_line, order, line = _world(api)
    key = _contribution(_board(client, core_so), core_so.so_number)["key"]
    _confirm_full_qty(client, world, order, line)

    response = _save(client, key, decision=_approval_body())

    assert response.status_code == 409, response.text
    assert response.json()["message"] == (
        "This line is already confirmed. Amend it to change the decision, "
        "or undo the confirmation."
    )


# --------------------------------------------------------------------------- #
# Review round, 17 Sep 2026: two gaps R1's gate must not have.                 #
# --------------------------------------------------------------------------- #


def test_confirming_one_line_does_not_cover_a_sibling_line_of_the_same_order(api):
    """AC-B7: guards the `line_snapshots[].core_line_id == this line` MEMBERSHIP check in
    `_covered_by_active_decision` against a cheaper implementation that would pass every
    OTHER test in this file - `return bool(decisions)`, "an active decision exists on this
    order at all" - because every other test here confirms an order with exactly one line.
    Two core lines, two mirror lines, only line 1 confirmed: line 2 must still take a plain
    approval. PASSES TODAY - this is a guard against a regression, not a gap."""
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=100)
    core_so = _core_so(db, world.company_id)
    core_line_1 = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10")
    product_2 = _product(db)
    core_line_2 = _core_line(db, core_so, product_2, world.own_wh, qty_ordered="5")
    order = _project_so(db, world.project, so_id=core_so.id)
    line_1 = _project_line(db, order, line_no=10, product=world.product, core_line=core_line_1)
    _project_line(db, order, line_no=20, product=product_2, core_line=core_line_2)
    db.commit()

    confirm = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(
                    line_1.id, reserve=[{"warehouse_id": world.pool_wh.id, "qty": "10"}]
                )
            ]
        },
    )
    assert confirm.status_code == 200, confirm.text

    key_2 = next(
        row["key"]
        for row in _board(client, core_so)["contributions"]
        if row["item_code"] == product_2.product_code
    )

    response = _save(client, key_2, decision=_approval_body())

    assert response.status_code == 200, response.text


def _planning_change_row(db, *, order, line, core_line, product, applied_state):
    """One `PlanningChangeRow` on `line`, in its own fresh batch (the FK the row needs)."""
    from app.models.planning_change import PlanningChangeBatch, PlanningChangeRow

    batch = PlanningChangeBatch(id=str(uuid.uuid4()), source_kind="so_manual_edit")
    db.add(batch)
    db.flush()
    row = PlanningChangeRow(
        id=str(uuid.uuid4()),
        batch_id=batch.id,
        project_sales_order_id=order.id,
        project_line_id=line.id,
        core_line_id=core_line.id,
        line_no=line.line_no,
        item_code=product.product_code,
        kind="qty_up",
        facts_json={},
        applied_state=applied_state,
    )
    db.add(row)
    db.flush()
    return row


def test_a_pending_planning_change_on_a_confirmed_line_exempts_it_from_the_gate(api):
    """AC-B8: a line mid-replan - a re-uploaded book row not yet applied - is not the
    "confirmed, leave it alone" case R1 exists for; the planner is being asked to redecide it,
    so a plain Save must still land. TEST-FIRST: `_covered_by_active_decision` carries no
    planning-change awareness yet, so this is refused with 409 today."""
    from app.models.project_so import SOSupplyDecisionDraft
    from app.services.planning_change_service import PLANNING_CHANGE_STATE_PENDING

    client, world, core_so, core_line, order, line = _world(api)
    db = world.db
    key = _contribution(_board(client, core_so), core_so.so_number)["key"]
    _confirm_full_qty(client, world, order, line)
    _planning_change_row(
        db, order=order, line=line, core_line=core_line, product=world.product,
        applied_state=PLANNING_CHANGE_STATE_PENDING,
    )

    response = _save(client, key, decision=_approval_body())

    assert response.status_code == 200, response.text
    assert (
        db.query(SOSupplyDecisionDraft)
        .filter(SOSupplyDecisionDraft.core_line_id == str(core_line.id))
        .count()
        == 1
    )


def test_an_applied_planning_change_on_a_confirmed_line_does_not_exempt_it(api):
    """AC-B8, the other half: once the planning change has been APPLIED, the ordinary R1
    gate still holds - only a row genuinely still PENDING (a live redecide) exempts a line.
    PASSES TODAY: identical to the ordinary covered case for the gate as it stands."""
    from app.services.planning_change_service import PLANNING_CHANGE_STATE_APPLIED

    client, world, core_so, core_line, order, line = _world(api)
    db = world.db
    key = _contribution(_board(client, core_so), core_so.so_number)["key"]
    _confirm_full_qty(client, world, order, line)
    _planning_change_row(
        db, order=order, line=line, core_line=core_line, product=world.product,
        applied_state=PLANNING_CHANGE_STATE_APPLIED,
    )

    response = _save(client, key, decision=_approval_body())

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "board_line_already_confirmed"
