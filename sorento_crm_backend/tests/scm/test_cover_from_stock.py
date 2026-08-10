"""Cover a shortage from stock somewhere else, or buy it, or both.

> "actually the use stock is use from BRW, not from BRW-IB"

The action was built on the wrong reading. A line's own on-hand is already inside its net
position - it is arithmetic that has happened, not a choice. "Use stock" means covering the
shortage from a DIFFERENT location, which needs a source and a quantity and is very often only
partial.

The live case these tests are modelled on, MWC7624-RL-S10:

    BRW-IB   needs 1     on hand 0    -> short 1    | free elsewhere: BRW-BB 5, PJ-SR 1
    DC1-BB   needs 419   on hand 231  -> short 188  | so: cover 6, buy 182

DC1-BB holds 231 units and can give NONE of them: it is short itself. That is the trap the
`free = on_hand - own demand` rule exists to close.
"""
from __future__ import annotations

import uuid

import pytest

from app.services.scm.cover_service import CoverSource, propose_cover

MARKER = "ZZTCOV"


def src(code: str, qty: float, segment: str = "project", wid: str | None = None) -> CoverSource:
    return CoverSource(
        warehouse_id=wid or f"wh-{code}",
        warehouse_code=code,
        segment=segment,
        qty=qty,
        cross_segment=False,
    )


# --------------------------------------------------------------------------- #
# the split
# --------------------------------------------------------------------------- #

def test_a_shortage_smaller_than_the_free_stock_is_covered_outright():
    p = propose_cover(1, "wh-BRW-IB", "project", [src("BRW-BB", 5), src("PJ-SR", 1)])

    assert p.cover_qty == 1
    assert p.buy_qty == 0
    assert [(s.warehouse_code, s.qty) for s in p.sources] == [("BRW-BB", 1)]
    assert p.is_split is False


def test_a_shortage_larger_than_the_free_stock_becomes_a_split():
    """The live DC1-BB case: 6 units exist anywhere else, so cover 6 and buy the other 182."""
    p = propose_cover(188, "wh-DC1-BB", "project", [src("BRW-BB", 5), src("PJ-SR", 1)])

    assert p.cover_qty == 6
    assert p.buy_qty == 182
    assert p.is_split is True
    assert [(s.warehouse_code, s.qty) for s in p.sources] == [("BRW-BB", 5), ("PJ-SR", 1)]


def test_nothing_free_anywhere_is_a_plain_buy():
    p = propose_cover(188, "wh-DC1-BB", "project", [])

    assert p.cover_qty == 0
    assert p.buy_qty == 188
    assert p.sources == []


def test_a_line_that_is_not_short_proposes_nothing():
    assert propose_cover(0, "wh-A", "project", [src("B", 50)]).sources == []


# --------------------------------------------------------------------------- #
# a location never covers itself
# --------------------------------------------------------------------------- #

def test_the_lines_own_location_is_never_offered_as_a_source():
    """Its stock is already inside the net. Offering it back would count it twice and is what
    made the old button read as "use the 1 on hand here", which was never a decision."""
    p = propose_cover(10, "wh-BRW-BB", "project", [src("BRW-BB", 5), src("PJ-SR", 1)])

    assert [s.warehouse_code for s in p.sources] == ["PJ-SR"]
    assert p.cover_qty == 1
    assert p.buy_qty == 9


# --------------------------------------------------------------------------- #
# the same unit is never promised twice
# --------------------------------------------------------------------------- #

def test_stock_already_taken_by_an_earlier_decision_is_not_offered_again():
    free = [src("BRW-BB", 5)]

    first = propose_cover(3, "wh-A", "project", free)
    assert first.cover_qty == 3

    second = propose_cover(
        3, "wh-B", "project", free, already_taken={"wh-BRW-BB": first.cover_qty}
    )
    assert second.cover_qty == 2
    assert second.buy_qty == 1


def test_a_fully_consumed_source_disappears_rather_than_offering_zero():
    p = propose_cover(5, "wh-A", "project", [src("BRW-BB", 5)], already_taken={"wh-BRW-BB": 5})

    assert p.sources == []
    assert p.buy_qty == 5


# --------------------------------------------------------------------------- #
# segments are crossed deliberately, never silently
# --------------------------------------------------------------------------- #

def test_same_segment_stock_is_preferred_over_a_bigger_cross_segment_pile():
    """A smaller same-segment source beats a larger one across the boundary: crossing is a
    decision the business tracks, so it is the fallback, not the first answer."""
    p = propose_cover(
        4,
        "wh-A",
        "project",
        [src("DEALER-BIG", 100, segment="dealer"), src("PROJ-SMALL", 3, segment="project")],
    )

    assert [s.warehouse_code for s in p.sources] == ["PROJ-SMALL", "DEALER-BIG"]
    assert p.sources[0].cross_segment is False
    assert p.sources[1].cross_segment is True


def test_a_cross_segment_source_is_flagged_so_it_is_never_mixed_in_silently():
    p = propose_cover(2, "wh-A", "dealer", [src("PROJ", 10, segment="project")])

    assert p.cover_qty == 2
    assert p.sources[0].cross_segment is True


def test_an_unknown_segment_is_not_treated_as_a_crossing():
    # Absent data is not evidence of a boundary being crossed, so it must not be flagged as one.
    p = propose_cover(2, "wh-A", None, [src("X", 10, segment=None)])
    assert p.sources[0].cross_segment is False


# --------------------------------------------------------------------------- #
# free stock read from a real run
# --------------------------------------------------------------------------- #

def test_free_stock_excludes_a_location_that_is_short_itself(db_free_world):
    """DC1-BB holds 231 and needs 419. It has nothing to give, and reading its raw on-hand
    would rob a location that is itself short."""
    free = db_free_world["free"]
    codes = {s.warehouse_code: s.qty for s in free}

    assert codes.get(f"{MARKER}-SHORT") is None
    assert codes[f"{MARKER}-SPARE"] == 5


def test_free_stock_includes_a_location_with_stock_and_no_plan_row(db_free_world):
    """A location with stock and no demand produces NO recommendation, so absence of a row has
    to read as zero demand rather than as absence of stock."""
    codes = {s.warehouse_code: s.qty for s in db_free_world["free"]}
    assert codes[f"{MARKER}-SPARE"] == 5


@pytest.fixture()
def db_free_world():
    """A product with stock in two places: one short of its own demand, one idle."""
    from app.models.procurement import Supplier
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    from app.services.scm.cover_service import free_stock_by_product
    from tests._pg_fixture import pg_session, unique_code

    def _u() -> str:
        return str(uuid.uuid4())

    with pg_session() as db:
        cat = ProductCategory(id=_u(), category_code=unique_code(MARKER),
                              category_name=f"{MARKER} cat")
        uom = UnitOfMeasure(id=_u(), uom_code=unique_code("U")[:20], uom_name=f"{MARKER} u")
        db.add_all([cat, uom])
        db.flush()
        product = Product(id=_u(), product_code=unique_code("P"), product_name=f"{MARKER} p",
                          category_id=cat.id, base_uom_id=uom.id, list_price=0,
                          is_active=True, is_discontinued=False)
        db.add(product)
        db.flush()

        from sqlalchemy import text as _t

        run_id = _u()
        db.execute(_t(
            "INSERT INTO scm.reorder_run (id, status, created_at) "
            "VALUES (:id, 'complete', now())"), {"id": run_id})

        wh_ids = {}
        for code, on_hand, demand in (
            (f"{MARKER}-SHORT", 231, 419),   # holds stock, short of its own demand
            (f"{MARKER}-SPARE", 5, 0),       # holds stock, no demand, no plan row
        ):
            wid = _u()
            wh_ids[code] = wid
            db.execute(_t(
                "INSERT INTO warehouses (id, warehouse_code, warehouse_name, "
                "counts_as_available, segment) VALUES (:id, :c, :c, true, 'project')"),
                {"id": wid, "c": code})
            db.execute(_t(
                "INSERT INTO stock (id, product_id, warehouse_id, quantity_on_hand) "
                "VALUES (:id, :p, :w, :q)"),
                {"id": _u(), "p": product.id, "w": wid, "q": on_hand})
            if demand:
                db.execute(_t(
                    "INSERT INTO scm.reorder_recommendation "
                    "(id, run_id, product_id, warehouse_id, rec_type, rounded_qty, inputs) "
                    "VALUES (:id, :run, :p, :w, 'buy', 0, CAST(:inputs AS jsonb))"),
                    {"id": _u(), "run": run_id, "p": product.id, "w": wid,
                     "inputs": f'{{"committed": {demand}, "on_hand": {on_hand}}}'})
        db.flush()

        free = free_stock_by_product(db, run_id, [str(product.id)]).get(str(product.id), [])
        yield {"free": free, "product": product, "wh_ids": wh_ids}
