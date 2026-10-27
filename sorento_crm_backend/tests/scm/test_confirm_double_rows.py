"""CONFIRM-DOUBLE-ROWS: pressing Confirm again on the same board decision is idempotent.

Found by BOARD-NO-HOLD (#1919) and identical on main: a fresh order SO-B, an earlier
undecided order SO-A at the same bin, three identical "Reserve own 36" confirms. Press 1
writes no allocation and records the Reserve short (SO-A's earlier date takes the pile). Press
2 then wrote `own 36`, and press 3 a SECOND `own 36`: the carry-forward exemption
(`_carried_component_qty`) credited the FROZEN component (36 asked) as already held, so the
repeat skipped the recheck and wrote the asked Reserve in full.

Rule (owner, 28 Oct 2026): confirming the same decision again never adds an allocation row for
what is already held; a changed decision replaces the previous one, it does not add to it.

Postgres via `blank_session`; every chain seeded here (ladder suite fixtures).
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from app.models.project_so import ALLOC_SOURCE_ORDER, SOLineAllocation, SOSupplyDecision
from app.schemas.project_supply import ConfirmLine, ConfirmSupplyBody
from app.services.project_supply_service import ProjectSupplyService

from .._pg_fixture import blank_session
from ..test_so_supply_confirmation import _stock
from .test_project_supply_service_ladder import (
    REQUIRED_DATE,
    _group_sites,
    _seed_line,
    _world,
)


def _two_orders(db, *, on_hand: int):
    """SO-A due 20 days before SO-B, both 36 at the same own bin, `on_hand` there."""
    company_id, eling, project, product = _world(db)
    _group, sites = _group_sites(db)
    own, _pool = sites["BRW"]
    _stock(db, product, own, on_hand=on_hand)
    _seed_line(
        db, company_id, project, product, own, qty_ordered="36", line_no=1,
        required_date=REQUIRED_DATE - timedelta(days=20),
    )
    order_b, line_b, _cso, _cline = _seed_line(
        db, company_id, project, product, own, qty_ordered="36", line_no=1,
    )
    return {"eling": eling, "own": own, "order": order_b, "line": line_b}


def _confirm(db, world, *, reserve="0", buy="0", amend_reason=None):
    line = ConfirmLine(
        project_line_id=world["line"].id,
        reserve=(
            [{"warehouse_id": str(world["own"].id), "qty": reserve}]
            if Decimal(reserve) > 0
            else []
        ),
        buy_qty=Decimal(buy),
        **({"amend_reason": amend_reason} if amend_reason else {}),
    )
    body = ProjectSupplyService(db).confirm(
        world["order"], ConfirmSupplyBody(lines=[line]), actor_user_id=world["eling"]
    )
    db.commit()
    return body


def _active_rows(db, world):
    """(source_type, qty) of the line's allocation rows under its ACTIVE revision."""
    active = ProjectSupplyService(db).active_decision(str(world["order"].id))
    rows = (
        db.query(SOLineAllocation)
        .filter(
            SOLineAllocation.so_line_id == world["line"].id,
            SOLineAllocation.decision_id == active.id,
        )
        .all()
    )
    return sorted((row.source_type, Decimal(row.qty).normalize()) for row in rows)


def _revisions(db, world):
    return (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == world["order"].id)
        .count()
    )


def test_three_identical_reserve_presses_behind_an_earlier_order_stay_short():
    """The #1919 diagnostic. Every press is the same decision, so every press leaves the
    same state as the first: no allocation row, the Reserve recorded short 36."""
    with blank_session() as db:
        world = _two_orders(db, on_hand=36)
        for press in (1, 2, 3):
            body = _confirm(db, world, reserve="36")
            assert _active_rows(db, world) == [], f"press {press}"
            notices = body["stock_short_notices"] or []
            assert len(notices) == 1 and "36 short" in notices[0]["reason"], (
                press, notices,
            )
        all_rows = (
            db.query(SOLineAllocation)
            .filter(SOLineAllocation.so_line_id == world["line"].id)
            .count()
        )
        assert all_rows == 0


def test_a_repeat_press_on_a_held_reserve_keeps_exactly_one_row():
    """Free stock (no earlier order): press 1 writes `own 36`; pressing again keeps the one
    `own 36` under the active revision, never two."""
    with blank_session() as db:
        world = _two_orders(db, on_hand=72)
        for press in (1, 2, 3):
            body = _confirm(db, world, reserve="36")
            assert _active_rows(db, world) == [("own", Decimal("36"))], f"press {press}"
            assert not body["stock_short_notices"], (press, body["stock_short_notices"])
        assert _revisions(db, world) == 3


def test_a_changed_decision_replaces_the_previous_allocation():
    """Reserve 36, then Buy 36, then Reserve 36 again: each press's active rows are that
    press's decision alone, never the previous one added to it."""
    with blank_session() as db:
        world = _two_orders(db, on_hand=72)
        _confirm(db, world, reserve="36")
        assert _active_rows(db, world) == [("own", Decimal("36"))]
        _confirm(db, world, buy="36")
        assert _active_rows(db, world) == [(ALLOC_SOURCE_ORDER, Decimal("36"))]
        _confirm(db, world, reserve="36")
        assert _active_rows(db, world) == [("own", Decimal("36"))]


def test_a_smaller_reserve_replaces_and_a_larger_one_is_rechecked():
    """Reserve 36 held, then a changed decision Reserve 20 + Buy 16 (with a reason): the
    active revision holds 20, not 36 + 20."""
    with blank_session() as db:
        world = _two_orders(db, on_hand=72)
        _confirm(db, world, reserve="36")
        _confirm(db, world, reserve="20", buy="16", amend_reason="Part from stock.")
        assert _active_rows(db, world) == [
            (ALLOC_SOURCE_ORDER, Decimal("16")), ("own", Decimal("20")),
        ]


def test_a_partly_short_reserve_pressed_again_holds_only_what_the_first_press_held():
    """50 on hand, SO-A (earlier) takes 36 by date, 14 are free for SO-B: press 1 holds 14
    and records 22 short; every repeat press says exactly the same."""
    with blank_session() as db:
        world = _two_orders(db, on_hand=50)
        for press in (1, 2, 3):
            body = _confirm(db, world, reserve="36")
            assert _active_rows(db, world) == [("own", Decimal("14"))], f"press {press}"
            notices = body["stock_short_notices"] or []
            assert len(notices) == 1 and "22 short" in notices[0]["reason"], (
                press, notices,
            )
