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
from ..test_so_supply_confirmation import _stock, _warehouse
from .test_project_supply_service_ladder import (
    REQUIRED_DATE,
    _group_sites,
    _seed_line,
    _world,
)


def _two_orders(db, *, on_hand: int, delivered: int = 0, sibling_on_hand: int = 0):
    """SO-A due 20 days before SO-B, both 36 at the same own bin, `on_hand` there.
    `delivered` of SO-B's line already delivered; `sibling_on_hand` at another bin of the
    same ownership group."""
    company_id, eling, project, product = _world(db)
    _group, sites = _group_sites(db)
    own, _pool = sites["BRW"]
    sibling, _sibling_pool = sites["MWH"]
    _stock(db, product, own, on_hand=on_hand)
    if sibling_on_hand:
        _stock(db, product, sibling, on_hand=sibling_on_hand)
    _seed_line(
        db, company_id, project, product, own, qty_ordered="36", line_no=1,
        required_date=REQUIRED_DATE - timedelta(days=20),
    )
    order_b, line_b, _cso, core_b = _seed_line(
        db, company_id, project, product, own, qty_ordered="36", line_no=1,
    )
    if delivered:
        core_b.qty_delivered = Decimal(delivered)
        db.commit()
    return {
        "eling": eling, "own": own, "sibling": sibling, "order": order_b, "line": line_b,
    }


def _confirm(db, world, *, reserve="0", buy="0", amend_reason=None, sibling=None):
    line = ConfirmLine(
        project_line_id=world["line"].id,
        reserve=(
            [{"warehouse_id": str(world["own"].id), "qty": reserve}]
            if Decimal(reserve) > 0
            else []
        )
        + ([{"warehouse_id": str(world["sibling"].id), "qty": sibling}] if sibling else []),
        buy_qty=Decimal(buy),
        **({"amend_reason": amend_reason} if amend_reason else {}),
    )
    body = ProjectSupplyService(db).confirm(
        world["order"], ConfirmSupplyBody(lines=[line]), actor_user_id=world["eling"]
    )
    db.commit()
    return body


def _active_rows(db, world, *, by_bin=False):
    """(source_type, qty) of the line's allocation rows under its ACTIVE revision; with
    `by_bin`, (warehouse_id, qty) instead."""
    active = ProjectSupplyService(db).active_decision(str(world["order"].id))
    rows = (
        db.query(SOLineAllocation)
        .filter(
            SOLineAllocation.so_line_id == world["line"].id,
            SOLineAllocation.decision_id == active.id,
        )
        .all()
    )
    return sorted(
        (str(row.warehouse_id) if by_bin else row.source_type, Decimal(row.qty).normalize())
        for row in rows
    )


def _shorts(body):
    return sorted(notice["reason"] for notice in body["stock_short_notices"] or [])


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


def test_a_partly_delivered_line_pressed_again_never_grows_its_hold():
    """Review B1: 10 of SO-B's 36 already delivered. The delivered credit and the carried
    credit froze the same units, so a repeat press must not credit them twice: every press
    holds what press 1 held (nothing at 36 on hand, 14 at 50 on hand)."""
    for on_hand, rows, short in ((36, [], "26 short"), (50, [("own", Decimal("14"))], "12 short")):
        with blank_session() as db:
            world = _two_orders(db, on_hand=on_hand, delivered=10)
            for press in (1, 2, 3, 4):
                body = _confirm(db, world, reserve="36")
                assert _active_rows(db, world) == rows, (on_hand, press)
                notices = _shorts(body)
                assert len(notices) == 1 and short in notices[0], (on_hand, press, notices)


def test_a_short_at_one_bin_and_a_hold_at_another_repeat_unchanged():
    """Reserve 18 at the own bin (empty) and 18 at a sibling bin of the same group (54 on
    hand, SO-A ahead for 36): press 1 holds the sibling's 18 and records the own bin's 18
    short; every repeat press says exactly the same."""
    with blank_session() as db:
        world = _two_orders(db, on_hand=0, sibling_on_hand=54)
        for press in (1, 2, 3):
            body = _confirm(db, world, reserve="18", sibling="18")
            assert _active_rows(db, world, by_bin=True) == [
                (str(world["sibling"].id), Decimal("18"))
            ], press
            notices = _shorts(body)
            assert len(notices) == 1 and "18 short" in notices[0], (press, notices)
            # The shortfall is frozen against its own component (the id the next press's
            # carried credit is matched on), not only the location code.
            assert _frozen_short(db, world)[0]["warehouse_id"] == str(world["own"].id)


def _frozen_short(db, world):
    active = ProjectSupplyService(db).active_decision(str(world["order"].id))
    return active.line_snapshots[0].get("stock_short") or []


def test_a_partly_delivered_borrow_pressed_again_never_grows_its_hold():
    """Review B2: Borrow 36 at a sibling bin with 20 free, 10 of the line delivered. Every
    press holds the 20 and records 6 short; the delivered units are credited once."""
    with blank_session() as db:
        world = _two_orders(db, on_hand=0, delivered=10, sibling_on_hand=20)
        for press in (1, 2, 3, 4):
            line = ConfirmLine(
                project_line_id=world["line"].id,
                borrow=[{
                    "source": "other_location",
                    "warehouse_id": str(world["sibling"].id),
                    "qty": "36",
                    "reason": "Units at the sibling bin.",
                }],
                buy_qty=Decimal("0"),
            )
            body = ProjectSupplyService(db).confirm(
                world["order"], ConfirmSupplyBody(lines=[line]), actor_user_id=world["eling"]
            )
            db.commit()
            assert _active_rows(db, world, by_bin=True) == [
                (str(world["sibling"].id), Decimal("20"))
            ], press
            notices = _shorts(body)
            assert len(notices) == 1 and "6 short" in notices[0], (press, notices)
            assert _frozen_short(db, world)[0]["warehouse_id"] == str(world["sibling"].id)


def _held(components, shorts):
    return {"x": {"components": components, "stock_short": shorts}}


def test_the_carried_credit_nets_only_its_own_components_short():
    """`_carried_component_qty` unit: a shortfall is credited back to the component it was
    recorded against (warehouse, and donor for a Borrow), never to a neighbour; a shortfall
    frozen before it carried those keys falls back to the location code."""
    credit = ProjectSupplyService._carried_component_qty
    reserve_a = {"kind": "reserve", "qty": "18", "source_warehouse_id": "A", "source_location": "LA"}
    reserve_b = {"kind": "reserve", "qty": "18", "source_warehouse_id": "B", "source_location": "LB"}
    short_a = {"kind": "reserve", "location": "LA", "warehouse_id": "A", "short": "18"}
    held = _held([reserve_a, reserve_b], [short_a])
    assert credit(None, held, "x", "reserve", "A") == Decimal("0")
    assert credit(None, held, "x", "reserve", "B") == Decimal("18")
    # A Borrow shortfall never touches a Reserve's credit at the same bin.
    borrow_short = {**short_a, "kind": "borrow"}
    assert credit(None, _held([reserve_a], [borrow_short]), "x", "reserve", "A") == Decimal("18")
    # Two donors at one bin: only the short donor's credit drops.
    p1 = {"kind": "borrow", "qty": "10", "source_warehouse_id": "A", "source_location": "LA",
          "donor_project_id": "P1"}
    p2 = {**p1, "donor_project_id": "P2"}
    p2_short = {"kind": "borrow", "location": "LA", "warehouse_id": "A",
                "donor_project_id": "P2", "short": "10"}
    donors = _held([p1, p2], [p2_short])
    assert credit(None, donors, "x", "borrow", "A", donor_project_id="P1") == Decimal("10")
    assert credit(None, donors, "x", "borrow", "A", donor_project_id="P2") == Decimal("0")
    # Legacy shortfall (no keys): matched on the location code.
    legacy = {"kind": "reserve", "location": "LB", "short": "6"}
    assert credit(None, _held([reserve_a, reserve_b], [legacy]), "x", "reserve", "B") == Decimal("12")
    assert credit(None, _held([reserve_a, reserve_b], [legacy]), "x", "reserve", "A") == Decimal("18")
    # Never below zero.
    big = {**short_a, "short": "40"}
    assert credit(None, _held([reserve_a], [big]), "x", "reserve", "A") == Decimal("0")


def test_a_shortfall_only_the_on_hand_floor_finds_is_frozen_against_its_component():
    """A Reserve with a reason at its own bin skips the capacity recheck (the 8 Sep lift),
    so only R14's on-hand floor records it short: 10 on hand, Reserve 36. That shortfall is
    keyed to the bin too, and a repeat press holds the same 10."""
    with blank_session() as db:
        world = _two_orders(db, on_hand=10)
        for press in (1, 2):
            body = _confirm(db, world, reserve="36", amend_reason="From the floor.")
            assert _active_rows(db, world) == [("own", Decimal("10"))], press
            notices = _shorts(body)
            assert len(notices) == 1 and "26 short" in notices[0], (press, notices)
            assert _frozen_short(db, world)[0]["warehouse_id"] == str(world["own"].id)


def test_a_cross_group_reserve_with_a_reason_pressed_again_stays_short():
    """The board's own path: an amended line always carries a reason, which lifts the
    capacity recheck only at the line's OWN group's bins. A Reserve from another group's bin
    that an earlier order of that group needs is short 36 on press 1, and on main press 2
    wrote it in full (`brw 36`). Every press is the same."""
    with blank_session() as db:
        company_id, eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        other = _warehouse(db, f"ZZTMWH-IR{own.warehouse_code[-3:]}")
        _stock(db, product, other, on_hand=36)
        _seed_line(
            db, company_id, project, product, other, qty_ordered="36", line_no=1,
            required_date=REQUIRED_DATE - timedelta(days=20),
        )
        order, line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="36", line_no=1,
        )
        world = {"order": order, "line": line}
        for press in (1, 2, 3):
            entry = ConfirmLine(
                project_line_id=line.id,
                reserve=[{"warehouse_id": str(other.id), "qty": "36"}],
                buy_qty=Decimal("0"),
                amend_reason="From the other group.",
            )
            body = ProjectSupplyService(db).confirm(
                order, ConfirmSupplyBody(lines=[entry]), actor_user_id=eling
            )
            db.commit()
            assert _active_rows(db, world) == [], press
            notices = _shorts(body)
            assert len(notices) == 1 and "36 short" in notices[0], (press, notices)
