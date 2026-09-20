"""Board contribution key round trip - reviewer fix round (captain's brief, 21 Sep 2026).

Plan: `documentation/plans/scm/PLAN-so-lines-autocount-order.md` section 3.5.
UAC: `documentation/plans/scm/so-lines-autocount-order-acceptance-criteria.md`, S3.

The reviewer's blocker: `app/services/project_line_draft_service.py::_resolve_core_line`
(used by `save_draft` / `remove_draft`) still numbers a contribution key's line by the OLD
rule - `(required_date, item_code, id)` / mirror-wins - while
`FulfilmentBoardService._line_numbers` already hands out AutoCount's raw `line_no` once
every contributing core line of the order carries a distinct one. A key the board builds
from `line_no` therefore names a DIFFERENT line to the resolver, which still counts by
date/code: the same class of drift `test_fulfilment_line_draft_route.py`'s own
`test_saving_a_line_whose_order_also_carries_an_unplanned_line_resolves_correctly` (~line
318) already caught once, for a different cause (the resolver counting a line the board's
own predicate excludes). The coder is extracting ONE shared numbering function for the
board, the resolver and `ProjectSOAdoptionService._mirror` (covered separately in
`test_so_lines_autocount_order_planning.py`) so all three agree.

  AC-B1-1  an UNADOPTED AutoCount order (no mirror) whose two lines' `line_no` DISAGREES
           with date/code order: the board hands out a key naming line A's raw `line_no`;
           saving against that key resolves to line A, not whichever line the OLD derived
           rule would have put in that slot; Undo on the same key succeeds (not 404).
  AC-B1-2  the SAME order with one line's `line_no` NULL: board and resolver BOTH fall
           back to the derived rule (the "all or nothing" guard already proven for the
           board in `test_so_lines_autocount_order_planning.py` AC-S3-2, now asked of the
           resolver too) - the key still resolves and the save still works.
  AC-B1-3  a FULLY MIRRORED order: the board's key already carries the mirror's own
           `line_no` and the resolver already accepts it - existing behaviour, a guard
           against the fix accidentally weakening the one case that already worked.

MEASURED, not assumed: AC-B1-2 is ALREADY GREEN today, unlike AC-B1-1. The brief's own
"expect B1-1, B1-2 ... red" is a reasonable guess that this run disproves for B1-2 - with
only ONE line's `line_no` null, `_resolve_core_line` computes the plain
`(required_date, item_code, id)` derived ordinal UNCONDITIONALLY (it never reads `line_no`
at all today), which for a two-line order with no cancelled/closed sibling is ARITHMETICALLY
IDENTICAL to the board's own fallback formula - so the two sides coincide by construction
whenever not every line carries a distinct raw number, bug or no bug. It is kept as a named
regression guard: once the coder's shared function runs on both sides, this must keep
passing exactly as it does now.

Setup copied from `tests/test_fulfilment_line_draft_route.py` (the `api` fixture chain and
its record builders, imported from `tests.test_so_supply_confirmation`) per the tester
brief - no new substrate. Postgres via `blank_session` (inside the `api` fixture), never
sqlite.
"""
from __future__ import annotations

from datetime import date

from app.models.project_so import SOSupplyDecisionDraft

from tests.test_fulfilment_line_draft_route import _board
from tests.test_fulfilment_line_draft_route import _save
from tests.test_so_supply_confirmation import (
    BASE,
    _core_line,
    _core_so,
    _product,
    _project_line,
    _project_so,
    _stock,
    api,  # noqa: F401 - pytest fixture, imported for reuse
)

__all__ = ["api"]


def _row(board: dict, *, line_no: int | None = None, item_code: str | None = None) -> dict:
    for row in board["contributions"]:
        if line_no is not None and row["line_no"] != line_no:
            continue
        if item_code is not None and row["item_code"] != item_code:
            continue
        return row
    raise AssertionError(
        f"no contribution matched line_no={line_no} item_code={item_code}: "
        f"{board['contributions']}"
    )


def _draft_for(db, sales_order_id: str) -> SOSupplyDecisionDraft:
    return (
        db.query(SOSupplyDecisionDraft)
        .filter(SOSupplyDecisionDraft.sales_order_id == sales_order_id)
        .one()
    )


class TestBoardKeyRoundTripUnadopted:
    def test_ac_b1_1_the_board_key_resolves_to_the_line_its_own_line_no_names(self, api):
        """`line_no` DISAGREES with date/code order on purpose: line A carries `line_no=2`
        but is due earliest and sorts first on code too; line B carries `line_no=1` but is
        due later. A resolver still using the derived rule would swap which physical line
        each key names."""
        client, world = api
        db = world.db
        product_a = _product(db)
        product_b = _product(db)
        _stock(db, product_a, world.pool_wh, on_hand=100)
        _stock(db, product_b, world.pool_wh, on_hand=100)
        core_so = _core_so(db, world.company_id)
        line_a = _core_line(
            db, core_so, product_a, world.own_wh, qty_ordered="5",
            required_date=date(2026, 1, 1),
        )
        line_a.line_no = 2
        line_b = _core_line(
            db, core_so, product_b, world.own_wh, qty_ordered="5",
            required_date=date(2026, 2, 1),
        )
        line_b.line_no = 1
        db.commit()

        board = _board(client, core_so)
        row_a = _row(board, line_no=2)
        assert row_a["item_code"] == product_a.product_code, (
            "sanity: line_no=2 on the board must be line A's own AutoCount number, not a "
            "derived ordinal that happens to also read 2"
        )

        response = _save(client, row_a["key"])
        assert response.status_code == 200, response.text
        assert str(_draft_for(db, core_so.id).core_line_id) == str(line_a.id)

        removal = client.delete(f"{BASE}/fulfilment-planning/lines/{row_a['key']}/draft")
        assert removal.status_code == 204, removal.text
        assert (
            db.query(SOSupplyDecisionDraft)
            .filter(SOSupplyDecisionDraft.sales_order_id == core_so.id)
            .count()
            == 0
        )

    def test_ac_b1_2_one_null_line_no_falls_back_to_the_derived_rule_on_both_sides(self, api):
        """A partial `line_no` is not enough to trust (the board's own AC-S3-2 rule) -
        with one line NULL, BOTH the board's key and the resolver's lookup must fall back
        to (required_date, item_code, id) for every line of the order, not just the null
        one.

        ALREADY GREEN today (see the module docstring): the resolver never reads `line_no`
        at all yet, so it always computes this same derived ordinal, and for a plain
        two-line order that coincides with the board's own fallback whether or not the fix
        has landed. Kept as a regression guard.
        """
        client, world = api
        db = world.db
        product_a = _product(db)
        product_b = _product(db)
        _stock(db, product_a, world.pool_wh, on_hand=100)
        _stock(db, product_b, world.pool_wh, on_hand=100)
        core_so = _core_so(db, world.company_id)
        line_a = _core_line(
            db, core_so, product_a, world.own_wh, qty_ordered="5",
            required_date=date(2026, 1, 1),
        )
        line_a.line_no = 5
        line_b = _core_line(
            db, core_so, product_b, world.own_wh, qty_ordered="5",
            required_date=date(2026, 2, 1),
        )
        line_b.line_no = None
        db.commit()

        board = _board(client, core_so)
        # Derived, by required date ascending: line_a (D1) -> 1, line_b (D2) -> 2 - NOT the
        # raw `line_no` (5) line_a itself carries.
        row_b = _row(board, item_code=product_b.product_code)
        assert row_b["line_no"] == 2

        response = _save(client, row_b["key"])
        assert response.status_code == 200, response.text
        assert str(_draft_for(db, core_so.id).core_line_id) == str(line_b.id)


class TestBoardKeyRoundTripMirrored:
    def test_ac_b1_3_a_fully_mirrored_order_still_resolves_by_the_mirrors_numbers(self, api):
        """Existing behaviour, kept as a guard: once every contributing line is mirrored,
        the mirror's OWN `line_no` (42 here - deliberately not 1, so a resolver that fell
        back to a positional guess could never accidentally match it) wins on both the
        board's key and the resolver's lookup."""
        client, world = api
        db = world.db
        _stock(db, world.product, world.pool_wh, on_hand=100)
        core_so = _core_so(db, world.company_id)
        core_line = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10")
        order = _project_so(db, world.project, so_id=core_so.id)
        _project_line(db, order, line_no=42, product=world.product, core_line=core_line)
        db.commit()

        board = _board(client, core_so)
        row = _row(board, item_code=world.product.product_code)
        assert row["line_no"] == 42

        response = _save(client, row["key"])
        assert response.status_code == 200, response.text
        assert str(_draft_for(db, core_so.id).core_line_id) == str(core_line.id)
