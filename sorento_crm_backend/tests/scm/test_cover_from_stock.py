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

from app.services.scm.cover_service import CoverSource, propose_cover, sources_in_scope

MARKER = "ZZTCOV"


def src(code: str, qty: float, segment: str | None = None, wid: str | None = None) -> CoverSource:
    """A site-pool source unless a test says otherwise: a location nobody has classified
    counts as pool, the same call `reorder_run_service._planning_rows` makes."""
    return CoverSource(
        warehouse_id=wid or f"wh-{code}",
        warehouse_code=code,
        segment=segment,
        qty=qty,
    )


# --------------------------------------------------------------------------- #
# the split
# --------------------------------------------------------------------------- #

def test_a_shortage_smaller_than_the_free_stock_is_covered_outright():
    p = propose_cover(1, "wh-BRW-IB", [src("BRW-BB", 5), src("PJ-SR", 1)])

    assert p.cover_qty == 1
    assert p.buy_qty == 0
    assert [(s.warehouse_code, s.qty) for s in p.sources] == [("BRW-BB", 1)]
    assert p.is_split is False


def test_a_shortage_larger_than_the_free_stock_becomes_a_split():
    """The live DC1-BB case: 6 units exist anywhere else, so cover 6 and buy the other 182."""
    p = propose_cover(188, "wh-DC1-BB", [src("BRW-BB", 5), src("PJ-SR", 1)])

    assert p.cover_qty == 6
    assert p.buy_qty == 182
    assert p.is_split is True
    assert [(s.warehouse_code, s.qty) for s in p.sources] == [("BRW-BB", 5), ("PJ-SR", 1)]


def test_nothing_free_anywhere_is_a_plain_buy():
    p = propose_cover(188, "wh-DC1-BB", [])

    assert p.cover_qty == 0
    assert p.buy_qty == 188
    assert p.sources == []


def test_a_line_that_is_not_short_proposes_nothing():
    assert propose_cover(0, "wh-A", [src("B", 50)]).sources == []


# --------------------------------------------------------------------------- #
# a location never covers itself
# --------------------------------------------------------------------------- #

def test_the_lines_own_location_is_never_offered_as_a_source():
    """Its stock is already inside the net. Offering it back would count it twice and is what
    made the old button read as "use the 1 on hand here", which was never a decision."""
    p = propose_cover(10, "wh-BRW-BB", [src("BRW-BB", 5), src("PJ-SR", 1)])

    assert [s.warehouse_code for s in p.sources] == ["PJ-SR"]
    assert p.cover_qty == 1
    assert p.buy_qty == 9


# --------------------------------------------------------------------------- #
# the same unit is never promised twice
# --------------------------------------------------------------------------- #

def test_stock_already_taken_by_an_earlier_decision_is_not_offered_again():
    free = [src("BRW-BB", 5)]

    first = propose_cover(3, "wh-A", free)
    assert first.cover_qty == 3

    second = propose_cover(
        3, "wh-B", free, already_taken={"wh-BRW-BB": first.cover_qty}
    )
    assert second.cover_qty == 2
    assert second.buy_qty == 1


def test_a_fully_consumed_source_disappears_rather_than_offering_zero():
    p = propose_cover(5, "wh-A", [src("BRW-BB", 5)], already_taken={"wh-BRW-BB": 5})

    assert p.sources == []
    assert p.buy_qty == 5


# --------------------------------------------------------------------------- #
# a project bin is never a source
# --------------------------------------------------------------------------- #
#
# R18 (captain, 28 Aug): "From stock" offers POOL locations only. Project stock is already
# claimed by an Order Inquiry, so offering it to a reorder promises the same units twice -
# and the cross-segment idea (offer it, but flag it) went with the ruling.

def test_a_project_bin_is_never_offered_however_much_it_holds():
    p = propose_cover(4, "wh-A", [src("BRW-IB", 100, segment="project")])

    assert p.sources == []
    assert p.cover_qty == 0
    assert p.buy_qty == 4


def test_a_pool_source_beside_a_project_bin_is_the_only_one_offered():
    p = propose_cover(
        10,
        "wh-A",
        [src("BRW-IB", 100, segment="project"), src("DC1", 3, segment="dealer")],
    )

    assert [(s.warehouse_code, s.qty) for s in p.sources] == [("DC1", 3)]
    assert p.buy_qty == 7


def test_an_unclassified_location_still_counts_as_pool():
    # A site nobody has tagged is not assumed to be a project bin - the same call the
    # engine's own on-hand makes (COALESCE(segment, 'dealer')).
    p = propose_cover(2, "wh-A", [src("X", 10, segment=None)])
    assert p.cover_qty == 2


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


def test_a_project_bin_holding_the_lot_offers_nothing_and_the_gap_is_bought():
    """The live shape R18 was written for: 34 units sit in BRW-IB (a project bin) and the
    BRW pool holds none. The plan offered "Stock 34" off the bin, which is stock an Order
    Inquiry has already claimed - so the row promised units it could not move.

    Now the bin is not a source, the pool has nothing to give, and the whole gap is a buy.
    """
    from app.services.scm.cover_service import free_stock_by_product, propose_cover
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    from sqlalchemy import text as _t
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

        run_id = _u()
        db.execute(_t(
            "INSERT INTO scm.reorder_run (id, status, include_market, created_at) "
            "VALUES (:id, 'complete', false, now())"), {"id": run_id})

        pool_id, bin_id = _u(), _u()
        pool_code, bin_code = f"{MARKER}-BRW", f"{MARKER}-BRW-IB"
        for wid, code, segment in ((pool_id, pool_code, "dealer"),
                                   (bin_id, bin_code, "project")):
            db.execute(_t(
                "INSERT INTO warehouses (id, warehouse_code, warehouse_name, is_active, "
                "counts_as_available, segment, pool_warehouse_id) "
                "VALUES (:id, :c, :c, true, true, :s, :pool)"),
                {"id": wid, "c": code, "s": segment,
                 "pool": pool_id if segment == "project" else None})
        # 34 free in the bin, nothing in the pool.
        db.execute(_t(
            "INSERT INTO stock (id, product_id, warehouse_id, quantity_on_hand, "
            "synced_to_excel) VALUES (:id, :p, :w, 34, false)"),
            {"id": _u(), "p": product.id, "w": bin_id})
        db.flush()

        free = free_stock_by_product(db, run_id, [str(product.id)]).get(str(product.id), [])

        assert free == [], "a project bin is not free stock for a reorder"
        p = propose_cover(100, pool_id, free,
                          cover_scope="own_pool", line_pool_warehouse_id=pool_id)
        assert p.cover_qty == 0
        assert p.buy_qty == 100


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
            "INSERT INTO scm.reorder_run (id, status, include_market, created_at) "
            "VALUES (:id, 'complete', false, now())"), {"id": run_id})

        wh_ids = {}
        # Site pools, not project bins: after R18 a project bin is never a source at all,
        # and these two rows are here to pin the free = on_hand - own demand rule.
        for code, on_hand, demand in (
            (f"{MARKER}-SHORT", 231, 419),   # holds stock, short of its own demand
            (f"{MARKER}-SPARE", 5, 0),       # holds stock, no demand, no plan row
        ):
            wid = _u()
            wh_ids[code] = wid
            db.execute(_t(
                "INSERT INTO warehouses (id, warehouse_code, warehouse_name, "
                "is_active, counts_as_available, segment) "
                "VALUES (:id, :c, :c, true, true, 'dealer')"),
                {"id": wid, "c": code})
            db.execute(_t(
                "INSERT INTO stock (id, product_id, warehouse_id, quantity_on_hand, "
                "synced_to_excel) VALUES (:id, :p, :w, :q, false)"),
                {"id": _u(), "p": product.id, "w": wid, "q": on_hand})
            if demand:
                db.execute(_t(
                    "INSERT INTO scm.reorder_recommendation "
                    "(id, run_id, product_id, warehouse_id, rec_type, rounded_qty, status, "
                    "inputs) "
                    "VALUES (:id, :run, :p, :w, 'buy', 0, 'proposed', CAST(:inputs AS jsonb))"),
                    {"id": _u(), "run": run_id, "p": product.id, "w": wid,
                     "inputs": f'{{"committed": {demand}, "on_hand": {on_hand}}}'})
        db.flush()

        free = free_stock_by_product(db, run_id, [str(product.id)]).get(str(product.id), [])
        yield {"free": free, "product": product, "wh_ids": wh_ids}


# --------------------------------------------------------------------------- #
# cover scope: the row's own site, or anywhere
# --------------------------------------------------------------------------- #
#
# > "why am I allowed to use stock from other locations? It is either I use stock from BRW,
# >  or buy."
#
# Three warehouses: A and B share pool A (one site), C is its own site. A row sitting at A
# may take from B under `own_pool`, and from B or C under `all_locations`.

def scoped(code: str, qty: float, pool: str, segment: str | None = None) -> CoverSource:
    return CoverSource(
        warehouse_id=f"wh-{code}",
        warehouse_code=code,
        segment=segment,
        qty=qty,
        pool_warehouse_id=pool,
    )


def test_own_pool_offers_only_the_rows_own_site():
    free = [scoped("B", 5, "wh-A"), scoped("C", 50, "wh-C")]

    p = propose_cover(60, "wh-A", free,
                      cover_scope="own_pool", line_pool_warehouse_id="wh-A")

    assert [s.warehouse_code for s in p.sources] == ["B"]
    assert p.cover_qty == 5
    assert p.buy_qty == 55


def test_all_locations_offers_every_site():
    free = [scoped("B", 5, "wh-A"), scoped("C", 50, "wh-C")]

    p = propose_cover(60, "wh-A", free,
                      cover_scope="all_locations", line_pool_warehouse_id="wh-A")

    assert [s.warehouse_code for s in p.sources] == ["C", "B"]
    assert p.cover_qty == 55
    assert p.buy_qty == 5


def test_a_source_with_no_pool_of_its_own_is_its_own_pool():
    loose = CoverSource(warehouse_id="wh-D", warehouse_code="D", segment=None, qty=9)

    assert propose_cover(9, "wh-A", [loose],
                         cover_scope="own_pool",
                         line_pool_warehouse_id="wh-A").sources == []
    assert propose_cover(9, "wh-A", [loose],
                         cover_scope="own_pool",
                         line_pool_warehouse_id="wh-D").cover_qty == 9


def test_a_row_with_no_pool_is_not_scoped_to_nothing():
    """A network row carries no warehouse, so there is no pool to compare against. Filtering
    it to nothing would silently withdraw every option rather than narrow them."""
    free = [scoped("B", 5, "wh-A"), scoped("C", 50, "wh-C")]

    p = propose_cover(60, None, free,
                      cover_scope="own_pool", line_pool_warehouse_id=None)

    assert [s.warehouse_code for s in p.sources] == ["C", "B"]


def test_an_absent_scope_falls_closed_to_the_rows_own_pool():
    """The policy default is `own_pool`, so an absent value has to mean own_pool here too.

    Reading it as `all_locations` failed OPEN: a caller that forgot the argument (or a payload
    that predates the column) silently offered the whole network, which is the one answer the
    captain ruled out ("either I use stock from BRW, or buy").
    """
    free = [scoped("B", 5, "wh-A"), scoped("C", 50, "wh-C")]

    p = propose_cover(60, "wh-A", free, line_pool_warehouse_id="wh-A")

    assert [s.warehouse_code for s in p.sources] == ["B"]
    assert p.cover_qty == 5
    assert p.buy_qty == 55


def test_sources_in_scope_falls_closed_on_an_absent_scope():
    free = [scoped("B", 5, "wh-A"), scoped("C", 50, "wh-C")]

    assert [s.warehouse_code for s in sources_in_scope(free, None, "wh-A")] == ["B"]
    assert [s.warehouse_code for s in sources_in_scope(free, "", "wh-A")] == ["B"]


def test_own_pool_still_excludes_the_lines_own_warehouse():
    """Scope narrows the offer; it never re-admits the row's own stock, which is already
    inside the net."""
    free = [scoped("A", 100, "wh-A"), scoped("B", 5, "wh-A")]

    p = propose_cover(60, "wh-A", free,
                      cover_scope="own_pool", line_pool_warehouse_id="wh-A")

    assert [s.warehouse_code for s in p.sources] == ["B"]


def test_free_stock_carries_the_pool_each_location_belongs_to(db_pooled_world):
    """The endpoint is keyed by PRODUCT (the pool is shared), so each source has to say which
    pool it sits in or a per-row scope filter is impossible."""
    by_code = {s.warehouse_code: s for s in db_pooled_world["free"]}
    ids = db_pooled_world["wh_ids"]

    # B shares A's pool; C is its own.
    assert by_code[f"{MARKER}-B"].pool_warehouse_id == ids[f"{MARKER}-A"]
    assert by_code[f"{MARKER}-C"].pool_warehouse_id == ids[f"{MARKER}-C"]


@pytest.fixture()
def db_pooled_world():
    """A product with free stock at two locations: one in the row's pool, one outside it."""
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
            "INSERT INTO scm.reorder_run (id, status, include_market, created_at) "
            "VALUES (:id, 'complete', false, now())"), {"id": run_id})

        wh_ids: dict[str, str] = {}
        # A is the pool root; B points at it; C is its own site. All three are site pools:
        # after R18 a project bin is never offered, so scoping it would prove nothing.
        for code in (f"{MARKER}-A", f"{MARKER}-B", f"{MARKER}-C"):
            wid = _u()
            wh_ids[code] = wid
            db.execute(_t(
                "INSERT INTO warehouses (id, warehouse_code, warehouse_name, "
                "is_active, counts_as_available, segment) "
                "VALUES (:id, :c, :c, true, true, 'dealer')"),
                {"id": wid, "c": code})
        db.execute(_t("UPDATE warehouses SET pool_warehouse_id = :root WHERE id = :id"),
                   {"root": wh_ids[f"{MARKER}-A"], "id": wh_ids[f"{MARKER}-B"]})
        for code, on_hand in ((f"{MARKER}-B", 5), (f"{MARKER}-C", 50)):
            db.execute(_t(
                "INSERT INTO stock (id, product_id, warehouse_id, quantity_on_hand, "
                "synced_to_excel) VALUES (:id, :p, :w, :q, false)"),
                {"id": _u(), "p": product.id, "w": wh_ids[code], "q": on_hand})
        db.flush()

        free = free_stock_by_product(db, run_id, [str(product.id)]).get(str(product.id), [])
        yield {"free": free, "product": product, "wh_ids": wh_ids, "run_id": run_id}
