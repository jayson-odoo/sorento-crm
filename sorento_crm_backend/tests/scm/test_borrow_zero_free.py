"""BORROW-ZERO-FREE (`documentation/plans/scm/PLAN-borrow-zero-free-22oct.md`).

Owner, 22 Oct 2026 (SO401624 line 224, BRW-BB 0 available): "not available also can borrow".
Borrow lists every location that carries a stock row for the item, even with 0 free, on every
fulfilment planning screen. Quantities are never capped by CRM stock: what is not free there is
recorded short at Confirm, as the own location (BORROW-OWN-LOC) already is.

Postgres via `blank_session`; every chain seeded here. Board fixtures from
`tests/test_fulfilment_board.py`, confirm fixtures from the ladder suite, with the
justification that earned them there.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.project_so import DECISION_ACTIVE, SOLineAllocation, SOSupplyDecision
from app.services.project_supply_service import ProjectSupplyService

from .._pg_fixture import blank_session
from ..test_fulfilment_board import (
    TODAY,
    _cell,
    _line,
    _order,
    _product,
    _service,
    _stock as _board_stock,
    _uid,
    _warehouse as _board_warehouse,
)
from ..test_so_supply_confirmation import _stock
from .test_borrow_location_only import _set_borrow_order
from .test_borrow_own_location import _confirm, _held_at, _own_world
from .test_project_supply_service_ladder import (
    _group_sites,
    _lead_time,
    _seed_line,
    _warehouse,
    _world,
)

REQUIRED = date(2026, 9, 3)
BUCKET = "2026-08-31"


def _rows_at(contribution, warehouse):
    return [
        c
        for c in contribution["borrow_candidates"]
        if c.get("warehouse_id") == str(warehouse.id)
    ]


@pytest.mark.parametrize("enabled", [False, True])
def test_a_location_with_a_stock_row_and_nothing_free_is_still_a_borrow_choice(enabled):
    """The owner's ask: a location holding nothing free is listed under Borrow (0 free), in
    both switch states, behind the location that has stock, with the own location last."""
    with blank_session() as db:
        _set_borrow_order(db, enabled)
        sfx = _uid()[:6]
        product = _product(db, f"ZZT-{sfx}")
        own = _board_warehouse(db, f"ZZTO{sfx}")
        empty = _board_warehouse(db, f"ZZTZ{sfx}")
        stocked = _board_warehouse(db, f"ZZTS{sfx}")
        _board_stock(db, product, own, on_hand=0)
        _board_stock(db, product, empty, on_hand=0)
        _board_stock(db, product, stocked, on_hand=25)
        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        _line(db, order, product, qty="10", required_date=REQUIRED, warehouse=own)

        board = _service(db).build([order.so_number], granularity="week", as_of=TODAY)

        contribution = _cell(board, product.product_code, BUCKET)["contributions"][0]
        codes = [c["warehouse_code"] for c in contribution["borrow_candidates"]]
        assert codes == [
            stocked.warehouse_code,
            empty.warehouse_code,
            own.warehouse_code,
        ], codes
        rows = _rows_at(contribution, empty)
        assert len(rows) == 1, contribution["borrow_candidates"]
        row = rows[0]
        assert row["source"] == "other_location"
        assert Decimal(row["free_qty"]) == 0
        assert not row.get("donor_project_id") and not row.get("donor_so_number")
        assert not row.get("recommended")
        # The dialog's location table reads this; without it the row is dropped there.
        assert row["location"]["warehouse_id"] == str(empty.id)
        # Exactly one recommended head, and it is the location with stock.
        heads = [c for c in contribution["borrow_candidates"] if c.get("recommended")]
        assert [c["warehouse_code"] for c in heads] == [stocked.warehouse_code]
        # Nothing free there adds nothing borrowable.
        assert contribution["qty_borrow_available"] == "25"
        # AC-6: the Buy's note never names a place with nothing free.
        offered = contribution["sources"][-1]["reason"].split("Borrowing is possible from")[1]
        assert empty.warehouse_code not in offered, offered


def test_a_location_with_nothing_free_never_takes_the_head_from_one_with_stock():
    """Availability nets what the book owes, not what is reserved or held, so a location whose
    whole stock is spoken for can read MORE available than one with 7 free. The 0-free row is
    listed, but behind every row with stock: picking it would be recorded short in full."""
    with blank_session() as db:
        sfx = _uid()[:6]
        product = _product(db, f"ZZT-{sfx}")
        own = _board_warehouse(db, f"ZZTO{sfx}")
        spoken = _board_warehouse(db, f"ZZTA{sfx}")
        spare = _board_warehouse(db, f"ZZTS{sfx}")
        _board_stock(db, product, own, on_hand=0)
        # 30 on hand, all 30 reserved: 0 free, 30 available.
        _board_stock(db, product, spoken, on_hand=30, reserved=30)
        _board_stock(db, product, spare, on_hand=7)
        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        _line(db, order, product, qty="10", required_date=REQUIRED, warehouse=own)

        board = _service(db).build([order.so_number], granularity="week", as_of=TODAY)

        contribution = _cell(board, product.product_code, BUCKET)["contributions"][0]
        candidates = contribution["borrow_candidates"]
        assert [c["warehouse_code"] for c in candidates] == [
            spare.warehouse_code,
            spoken.warehouse_code,
            own.warehouse_code,
        ], [(c["warehouse_code"], c["free_qty"], c["available_qty"]) for c in candidates]
        assert [c["warehouse_code"] for c in candidates if c.get("recommended")] == [
            spare.warehouse_code
        ]


def test_an_oversold_location_is_listed_with_its_signed_availability():
    """The owner's screenshot shape: nothing on hand and owed elsewhere. Listed too, and says
    how far short it is: the signed `available_qty`, never floored to 0 (13.11)."""
    with blank_session() as db:
        sfx = _uid()[:6]
        product = _product(db, f"ZZT-{sfx}")
        own = _board_warehouse(db, f"ZZTO{sfx}")
        oversold = _board_warehouse(db, f"ZZTV{sfx}")
        _board_stock(db, product, own, on_hand=0)
        _board_stock(db, product, oversold, on_hand=0)
        # Another order owes 40 at the oversold location: 0 on hand - 40 owed = -40.
        other = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 1))
        _line(db, other, product, qty="40", required_date=REQUIRED, warehouse=oversold)
        order = _order(db, so_number=f"ZZT-SO-{_uid()[:8]}", order_date=date(2026, 1, 2))
        _line(db, order, product, qty="10", required_date=REQUIRED, warehouse=own)

        board = _service(db).build([order.so_number], granularity="week", as_of=TODAY)

        contribution = _cell(board, product.product_code, BUCKET)["contributions"][0]
        rows = _rows_at(contribution, oversold)
        assert len(rows) == 1, contribution["borrow_candidates"]
        assert Decimal(rows[0]["free_qty"]) == 0
        assert Decimal(rows[0]["available_qty"]) == Decimal("-40"), rows[0]


def test_confirm_a_borrow_at_a_location_with_nothing_free_passes_short():
    """Picking a 0-free location is not refused: Confirm keeps the decision and records the
    whole quantity short, the way an own-location borrow beyond its free stock already is."""
    with blank_session() as db:
        world = _own_world(db, on_hand=0)
        # A location outside this line's Reserve pool, with a stock row and nothing free.
        elsewhere = _board_warehouse(db, f"ZZTE{_uid()[:6]}")
        _stock(db, world["product"], elsewhere, on_hand=0)
        db.commit()
        body = _confirm(
            db,
            world,
            borrow=[
                {
                    "source": "other_location",
                    "warehouse_id": str(elsewhere.id),
                    "qty": "10",
                    "reason": "Nothing free there yet, planning ahead.",
                }
            ],
        )
        notices = body["stock_short_notices"]
        assert len(notices) == 1 and "10 short" in notices[0]["reason"], notices
        assert _held_at(db, world, elsewhere) == Decimal("0")


# --------------------------------------------------------------------------- beyond the window


def test_confirm_accepts_a_hand_picked_borrow_on_a_line_beyond_the_reserve_window():
    """Owner ruling (b), 22 Oct 2026, on SO401624 line 224's shape (SRTWB242, BRW-BB, due
    2027-06-07, 90 days of lead time): beyond the reserve window the ladder still composes a
    Buy and walks no borrow rung, but the Borrow LIST is offered, and a donor a planner picks
    from it confirms. End to end: read off the sheet, picked, confirmed, recorded.

    BORROW-NO-HOLD (28 Oct 2026): a confirmed Borrow is a plan, not a hold, so it holds
    nothing; Confirm still writes its allocation row on the active decision."""
    with blank_session() as db:
        company_id, eling, project, product = _world(db)
        _group, sites = _group_sites(db)
        own, _pool = sites["BRW"]
        elsewhere = _warehouse(db, f"ZZTHP-{_uid()[:4]}")
        _stock(db, product, own, on_hand=0)
        _stock(db, product, elsewhere, on_hand=650)
        _lead_time(db, product, 90)
        order, line, _cso, _cline = _seed_line(
            db, company_id, project, product, own, qty_ordered="441",
            # 174 days out, against 90 of lead time plus the 14-day buffer: well beyond.
            required_date=date.today() + timedelta(days=174),
        )

        sheet_line = ProjectSupplyService(db).proposal_for(order)["lines"][0]
        # The auto-proposal is unchanged: a Buy of the whole line, by the rule.
        assert [c["kind"] for c in sheet_line["components"]] == ["buy"]
        assert "beyond the lead time window" in sheet_line["components"][0]["reason"]
        # The list is offered: the location with stock first, the own location last.
        codes = [c["warehouse_code"] for c in sheet_line["borrow_candidates"]]
        assert codes == [elsewhere.warehouse_code, own.warehouse_code], codes
        picked = sheet_line["borrow_candidates"][0]
        assert picked["source"] == "other_location", picked

        world = {"eling": eling, "product": product, "order": order, "line": line}
        body = _confirm(
            db,
            world,
            borrow=[
                {
                    "source": picked["source"],
                    "warehouse_id": picked["warehouse_id"],
                    "qty": "441",
                    "reason": "Stock is there now; the customer wants it early.",
                }
            ],
        )
        assert not body.get("stock_short_notices"), body.get("stock_short_notices")
        assert _held_at(db, world, elsewhere) == Decimal("0"), "a plan holds nothing"
        rows = (
            db.query(SOLineAllocation.source_type, SOLineAllocation.qty)
            .join(SOSupplyDecision, SOSupplyDecision.id == SOLineAllocation.decision_id)
            .filter(
                SOLineAllocation.so_line_id == line.id,
                SOLineAllocation.warehouse_id == str(elsewhere.id),
                SOLineAllocation.confirmed_at.isnot(None),
                SOSupplyDecision.state == DECISION_ACTIVE,
            )
            .all()
        )
        assert [(r.source_type, Decimal(r.qty)) for r in rows] == [
            (picked["source"], Decimal("441"))
        ], rows
