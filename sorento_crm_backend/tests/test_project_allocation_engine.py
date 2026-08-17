"""P9 allocation ranking: the pure engine behind AC-H1 and AC-H2.

No database. The engine is handed the live stock rows and the live project holds and
returns ranked candidates, which is the whole point of the slice: a stored snapshot of
another project's on-hand goes stale the moment they ship, and acting on a stale figure is
the failure this exists to prevent. Only the DECISION is persisted, never the figures.

The golden cases below are the five shapes the client's own allocation meetings produce:
nothing anywhere, enough at the master location, a split across two, a pile that is
physically present but spoken for by somebody else, and a quantity no combination reaches.
"""
from __future__ import annotations

from decimal import Decimal

from app.services.project_allocation_engine import (
    LineNeed,
    ProjectHold,
    StockRow,
    rank_sources,
)

BRW = "wh-brw"
OWN = "wh-own"
OTHER = "wh-other"
FREE = "wh-free"

THIS_PROJECT = "prj-this"
OTHER_PROJECT = "prj-other"


def _need(qty: str, project_id: str = THIS_PROJECT) -> LineNeed:
    return LineNeed(
        line_id="line-1", product_id="prod-1", project_id=project_id, qty=Decimal(qty)
    )


def _stock(warehouse_id: str, code: str, on_hand: str, reserved: str = "0") -> StockRow:
    return StockRow(
        warehouse_id=warehouse_id,
        warehouse_code=code,
        warehouse_name=code,
        on_hand=Decimal(on_hand),
        reserved=Decimal(reserved),
    )


def _hold(warehouse_id: str, project_id: str, qty: str, *, code: str, cs: str) -> ProjectHold:
    return ProjectHold(
        warehouse_id=warehouse_id,
        project_id=project_id,
        project_code=code,
        project_title=f"{code} Residences",
        cs_user_id=f"user-{cs}",
        cs_name=cs,
        qty=Decimal(qty),
    )


def _by_type(result, source_type: str):
    return [c for c in result.candidates if c.source_type == source_type]


# --------------------------------------------------------------- 1. nothing anywhere


def test_nothing_anywhere_offers_only_the_order_option():
    """No stock and no holds. The honest answer is "buy it", carrying no warehouse."""
    result = rank_sources(_need("135"), stock_rows=[], holds=[], brw_warehouse_id=BRW)

    assert [c.source_type for c in result.candidates] == ["order"]
    order = result.candidates[0]
    assert order.warehouse_id is None
    assert order.warehouse_code is None
    assert order.available == Decimal("0")
    assert order.allocatable == Decimal("135")
    assert result.covered is False
    assert result.shortfall == Decimal("135")
    assert result.plan == []


# ------------------------------------------------------------------ 2. enough at BRW


def test_enough_at_brw_is_ranked_first_and_covers_the_line():
    result = rank_sources(
        _need("135"),
        stock_rows=[_stock(BRW, "BRW-BB", "500")],
        holds=[],
        brw_warehouse_id=BRW,
    )

    assert [c.source_type for c in result.candidates] == ["brw", "order"]
    brw = result.candidates[0]
    assert brw.rank == 1
    assert brw.warehouse_code == "BRW-BB"
    assert brw.on_hand == Decimal("500")
    assert brw.committed == Decimal("0")
    assert brw.available == Decimal("500")
    assert brw.allocatable == Decimal("135")
    assert brw.requires_claim is False

    assert result.covered is True
    assert result.shortfall == Decimal("0")
    assert result.plan == [(BRW, Decimal("135"))]
    # The order option is still offered, at zero, because buying instead is always allowed.
    assert result.candidates[-1].allocatable == Decimal("0")


def test_brw_ranks_ahead_of_a_larger_pile_elsewhere():
    """Ranking is by SOURCE first, never by size: BRW-BB is the master location."""
    result = rank_sources(
        _need("50"),
        stock_rows=[_stock(BRW, "BRW-BB", "60"), _stock(FREE, "MWH", "900")],
        holds=[],
        brw_warehouse_id=BRW,
    )

    assert [c.warehouse_code for c in result.candidates] == ["BRW-BB", "MWH", None]
    assert result.plan == [(BRW, Decimal("50"))]


def test_the_projects_own_location_outranks_free_stock_elsewhere():
    result = rank_sources(
        _need("10"),
        stock_rows=[_stock(OWN, "WH3", "40"), _stock(FREE, "MWH", "900")],
        holds=[_hold(OWN, THIS_PROJECT, "40", code="PS26-0143", cs="Eling")],
        brw_warehouse_id=BRW,
    )

    codes = [c.warehouse_code for c in result.candidates]
    assert codes == ["WH3", "MWH", None]
    own = result.candidates[0]
    assert own.source_type == "own"
    assert own.is_project_location is True
    # Stock this project already holds is not committed AGAINST this project.
    assert own.available == Decimal("40")
    assert result.candidates[1].source_type == "own"
    assert result.candidates[1].is_project_location is False


# ------------------------------------------------------------- 3. split across sources


def test_a_line_no_single_source_covers_is_split_in_rank_order():
    result = rank_sources(
        _need("135"),
        stock_rows=[_stock(BRW, "BRW-BB", "80"), _stock(FREE, "MWH", "100")],
        holds=[],
        brw_warehouse_id=BRW,
    )

    assert result.covered is True
    assert result.shortfall == Decimal("0")
    assert result.plan == [(BRW, Decimal("80")), (FREE, Decimal("55"))]


def test_reserved_stock_is_committed_and_never_planned():
    """`quantity_reserved` is somebody's commitment already. Only the balance is offered."""
    result = rank_sources(
        _need("135"),
        stock_rows=[_stock(BRW, "BRW-BB", "200", reserved="150")],
        holds=[],
        brw_warehouse_id=BRW,
    )

    brw = result.candidates[0]
    assert brw.on_hand == Decimal("200")
    assert brw.reserved == Decimal("150")
    assert brw.committed == Decimal("150")
    assert brw.available == Decimal("50")
    assert result.plan == [(BRW, Decimal("50"))]
    assert result.shortfall == Decimal("85")
    assert result.covered is False


# ------------------------------------------------ 4. a pile held for another project


def test_a_pile_held_for_another_project_is_labelled_and_never_planned():
    """AC-H2 and AC-H4: it is visible, it names the holder and their CS, and it is asked for."""
    result = rank_sources(
        _need("135"),
        stock_rows=[_stock(OTHER, "MWH", "200")],
        holds=[_hold(OTHER, OTHER_PROJECT, "200", code="PS26-0201", cs="Farah")],
        brw_warehouse_id=BRW,
    )

    held = _by_type(result, "other_project")
    assert len(held) == 1
    candidate = held[0]
    assert candidate.warehouse_code == "MWH"
    assert candidate.on_hand == Decimal("200")
    assert candidate.held_for_other_projects == Decimal("200")
    assert candidate.committed == Decimal("200")
    assert candidate.available == Decimal("0")
    assert candidate.allocatable == Decimal("0")
    assert candidate.requires_claim is True
    assert candidate.claimable == Decimal("135")
    assert [(h.project_code, h.cs_name) for h in candidate.holders] == [("PS26-0201", "Farah")]

    # Nothing moves on silence: the proposal cannot quietly spend somebody else's stock.
    assert result.plan == []
    assert result.covered is False
    assert result.shortfall == Decimal("135")


def test_a_partly_held_pile_offers_only_the_free_balance():
    result = rank_sources(
        _need("135"),
        stock_rows=[_stock(OTHER, "MWH", "200")],
        holds=[_hold(OTHER, OTHER_PROJECT, "160", code="PS26-0201", cs="Farah")],
        brw_warehouse_id=BRW,
    )

    candidate = _by_type(result, "other_project")[0]
    assert candidate.available == Decimal("40")
    assert candidate.claimable == Decimal("135")
    assert result.plan == [(OTHER, Decimal("40"))]
    assert result.shortfall == Decimal("95")


def test_the_four_sources_rank_in_the_order_the_client_reads_them():
    result = rank_sources(
        _need("500"),
        stock_rows=[
            _stock(OTHER, "MWH", "200"),
            _stock(FREE, "DC1", "10"),
            _stock(OWN, "WH3", "30"),
            _stock(BRW, "BRW-BB", "20"),
        ],
        holds=[
            _hold(OTHER, OTHER_PROJECT, "200", code="PS26-0201", cs="Farah"),
            _hold(OWN, THIS_PROJECT, "30", code="PS26-0143", cs="Eling"),
        ],
        brw_warehouse_id=BRW,
    )

    assert [c.source_type for c in result.candidates] == [
        "brw",
        "own",
        "own",
        "other_project",
        "order",
    ]
    assert [c.warehouse_code for c in result.candidates] == [
        "BRW-BB",
        "WH3",
        "DC1",
        "MWH",
        None,
    ]
    assert [c.rank for c in result.candidates] == [1, 2, 3, 4, 5]


# --------------------------------------------- 5. a quantity no combination satisfies


def test_a_quantity_no_combination_satisfies_reports_the_shortfall_as_an_order():
    result = rank_sources(
        _need("927"),
        stock_rows=[
            _stock(BRW, "BRW-BB", "10"),
            _stock(OWN, "WH3", "5"),
            _stock(OTHER, "MWH", "200"),
        ],
        holds=[
            _hold(OWN, THIS_PROJECT, "5", code="PS26-0143", cs="Eling"),
            _hold(OTHER, OTHER_PROJECT, "200", code="PS26-0201", cs="Farah"),
        ],
        brw_warehouse_id=BRW,
    )

    assert result.covered is False
    assert result.shortfall == Decimal("912")
    assert result.plan == [(BRW, Decimal("10")), (OWN, Decimal("5"))]
    order = result.candidates[-1]
    assert order.source_type == "order"
    assert order.allocatable == Decimal("912")


# ------------------------------------------------------------------------- hygiene


def test_locations_holding_nothing_and_owing_nothing_are_not_offered():
    result = rank_sources(
        _need("10"),
        stock_rows=[_stock(BRW, "BRW-BB", "10"), _stock(FREE, "DC1", "0")],
        holds=[],
        brw_warehouse_id=BRW,
    )

    assert [c.warehouse_code for c in result.candidates] == ["BRW-BB", None]


def test_no_brw_warehouse_configured_still_ranks_the_rest():
    """A database with no BRW-BB row must not blank the screen."""
    result = rank_sources(
        _need("10"),
        stock_rows=[_stock(FREE, "MWH", "40")],
        holds=[],
        brw_warehouse_id=None,
    )

    assert [c.source_type for c in result.candidates] == ["own", "order"]
    assert result.plan == [(FREE, Decimal("10"))]


def test_a_line_needing_nothing_plans_nothing():
    result = rank_sources(
        _need("0"),
        stock_rows=[_stock(BRW, "BRW-BB", "10")],
        holds=[],
        brw_warehouse_id=BRW,
    )

    assert result.covered is True
    assert result.shortfall == Decimal("0")
    assert result.plan == []
