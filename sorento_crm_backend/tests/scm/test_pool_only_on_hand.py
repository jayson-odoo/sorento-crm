"""Captain, 20 Aug: "the on hand need to consider pool quantity only, meaning BRW, MWH,
all those; project on hand quantity is not really an actual usable quantity."

Verified live: SRT-H3005 read 309 on hand = 229 at BRW (pool, `segment='dealer'`) + 80 at
BRW-BB (project-held, `segment='project'`) - the project leg is not usable supply, so the
plan must not net it out of an incoming shortage or use it to avoid a buy trigger.

`_planning_rows` is exercised directly (same idiom `test_plan_horizon_review_fixes.py`
uses for the same function) rather than through a full `run_reorder`, because the fact
under test is what ONE SQL statement returns per row, not the engine's downstream
decisions - `test_pool_only_on_hand_reaches_a_frozen_recommendation` below still proves
it survives the freeze, through the real engine, end to end.

Postgres only, marker-prefixed, every test seeds its own chain.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.inventory import Stock, Warehouse
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.services.scm import reorder_run_service as svc
from tests._pg_fixture import pg_session
from tests.scm.conftest import requires_pg

pytestmark = requires_pg

MARKER = "ZZTPOOL"


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


def _product(db) -> Product:
    cat = ProductCategory(id=_u(), category_code=_code("CAT")[:40], category_name=_code("cat"))
    uom = UnitOfMeasure(id=_u(), uom_name=_code("uom"), uom_code=_code("U")[:20])
    db.add_all([cat, uom])
    db.flush()
    p = Product(
        id=_u(), product_code=_code("SKU"), product_name="Pool-only on-hand test product",
        category_id=cat.id, base_uom_id=uom.id, list_price=0,
        is_active=True, is_discontinued=False,
    )
    db.add(p)
    db.flush()
    return p


def _warehouse(db, *, segment: str | None, pool_warehouse_id: str | None = None) -> Warehouse:
    w = Warehouse(
        id=_u(), warehouse_code=_code("WH")[:50], warehouse_name="Pool-only test WH",
        segment=segment, pool_warehouse_id=pool_warehouse_id,
    )
    db.add(w)
    db.flush()
    return w


def _stock(db, product_id, warehouse_id, qty) -> None:
    db.add(Stock(id=_u(), product_id=product_id, warehouse_id=warehouse_id,
                 quantity_on_hand=qty, synced_to_excel=False))
    db.flush()


def test_a_dealer_location_counts_its_stock_in_full(db):
    p = _product(db)
    pool = _warehouse(db, segment="dealer")
    _stock(db, p.id, pool.id, 229)

    rows = svc._planning_rows(db, [str(pool.id)], [p.id])

    assert len(rows) == 1
    assert rows[0]["quantity_on_hand"] == 229
    assert rows[0]["project_on_hand"] == 0
    assert rows[0]["net_position"] == 229


def test_a_project_bin_counts_zero_but_states_its_own_stock_visibly(db):
    p = _product(db)
    pool = _warehouse(db, segment="dealer")
    project_supplier_bin = pool.id  # kept only to make the pool concrete for the reader
    bin_ = _warehouse(db, segment="project", pool_warehouse_id=project_supplier_bin)
    _stock(db, p.id, bin_.id, 80)

    rows = svc._planning_rows(db, [str(bin_.id)], [p.id])

    assert len(rows) == 1
    assert rows[0]["quantity_on_hand"] == 0, "project-held stock is not usable supply"
    assert rows[0]["project_on_hand"] == 80, "but it is never dropped from the screen"


def test_net_position_moves_with_the_pool_only_reading_never_the_view_own_figure(db):
    """The coupling the diagnosis flagged: `net_position` must use the SAME `on_hand` the
    row displays, or the screen and the buy trigger disagree about the same fact. 100
    committed against a project bin holding 80 reads as fully short (net -100), not as
    20 short the way `80 + 0 - 100` would."""
    p = _product(db)
    pool = _warehouse(db, segment="dealer")
    bin_ = _warehouse(db, segment="project", pool_warehouse_id=pool.id)
    _stock(db, p.id, bin_.id, 80)
    so = _mk_open_so(db)
    _mk_so_line(db, so, p.id, bin_.id, 100)

    rows = svc._planning_rows(db, [str(bin_.id)], [p.id])

    assert len(rows) == 1
    assert rows[0]["quantity_on_hand"] == 0
    assert rows[0]["project_on_hand"] == 80
    assert rows[0]["committed"] == 100
    assert rows[0]["net_position"] == -100, (
        "not -20 - the 80 sitting in the bin is not usable cover for its own demand either"
    )


def test_pool_only_on_hand_reaches_a_frozen_recommendation(scm_app):
    """End to end through the real engine and the freeze: the SRT-H3005 shape (229 at the
    pool, 80 at the project bin it feeds) survives `create_run` -> `run_reorder` with the
    same split on the frozen row, not only on the private helper's return value."""
    from tests.scm.test_m3_run import _link, _mk_supplier  # noqa: PLC0415

    _, db, _, _ = scm_app
    pool = Warehouse(id=_u(), warehouse_code=_code("POOL")[:50],
                     warehouse_name="Pool-only run WH", segment="dealer")
    db.add(pool)
    db.flush()
    bin_ = Warehouse(id=_u(), warehouse_code=_code("BIN")[:50],
                     warehouse_name="Pool-only run bin", segment="project",
                     pool_warehouse_id=pool.id)
    db.add(bin_)
    db.flush()
    p = Product(id=_u(), product_code=_code("SKU"), product_name="Pool-only run product",
                category_id=db.execute(
                    text("SELECT category_id FROM products WHERE category_id IS NOT NULL LIMIT 1")
                ).scalar(),
                base_uom_id=db.execute(
                    text("SELECT base_uom_id FROM products WHERE base_uom_id IS NOT NULL LIMIT 1")
                ).scalar(),
                list_price=0, is_active=True, is_discontinued=False)
    db.add(p)
    db.flush()
    _stock(db, p.id, pool.id, 229)
    _stock(db, p.id, bin_.id, 80)
    # Committed demand at BOTH locations, so both emit a row (a location with nothing
    # committed and nothing short emits none at all) - the pool's own 50 stays covered by
    # its 229; the bin's 100 is short against its counted (pool-only) on_hand of 0.
    so = _mk_open_so(db)
    _mk_so_line(db, so, p.id, pool.id, 50)
    _mk_so_line(db, so, p.id, bin_.id, 100)
    _link(db, p.id, _mk_supplier(db, "ZZT Pool-only Supplier"), moq=None, mult=None)
    db.flush()

    created = svc.create_run(db, [pool.warehouse_code, bin_.warehouse_code], enqueue=False)
    svc.run_reorder(created["run_id"], db=db)

    rows = db.execute(text(
        "SELECT warehouse_id, inputs FROM scm.reorder_recommendation "
        "WHERE run_id = :r AND product_id = :p"
    ), {"r": created["run_id"], "p": p.id}).mappings().all()
    by_wh = {str(r["warehouse_id"]): r["inputs"] for r in rows}
    assert float(by_wh[str(pool.id)]["on_hand"]) == 229.0
    assert float(by_wh[str(pool.id)]["project_on_hand"]) == 0.0
    assert float(by_wh[str(bin_.id)]["on_hand"]) == 0.0
    assert float(by_wh[str(bin_.id)]["project_on_hand"]) == 80.0


def _mk_open_so(db) -> str:
    soid = _u()
    db.execute(text(
        "INSERT INTO sales_orders (id, so_number, status, created_at, updated_at) "
        "VALUES (:id, :num, 'open', now(), now())"
    ), {"id": soid, "num": _code("SO")})
    return soid


def _mk_so_line(db, so_id, product_id, warehouse_id, qty) -> None:
    db.execute(text(
        "INSERT INTO sales_order_lines (id, sales_order_id, product_id, warehouse_id, "
        "qty_ordered, qty_required, qty_delivered, line_status, purchasing_status, "
        "created_at, updated_at) "
        "VALUES (:id, :so, :p, :w, :q, :q, 0, 'open', 'needs_purchase', now(), now())"
    ), {"id": _u(), "so": so_id, "p": product_id, "w": warehouse_id, "q": qty})
    db.flush()
