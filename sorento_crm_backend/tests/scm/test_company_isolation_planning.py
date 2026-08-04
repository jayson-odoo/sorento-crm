"""A plan for one company must not see another company's warehouses, products or stock.

The multi-company isolation filter runs on **ORM execution only**, and the SCM planning path is
raw SQL over views: no `scm.*` table carries a `company_id` at all. So a run enumerates every
company's positions. It is inert today only because Mocha owns 0 warehouses, which means
`scm.net_position_v` yields Sorento rows alone - a property of the current data, not of the code.

**The leak that matters adds COVER, not rows.** An extra warehouse on the plan is visible: a
planner sees a location they do not recognise. Another company's stock counted into the same
product's availability is invisible: the net position simply reads higher, the reorder point is
not breached, and the purchase that should have been raised is never proposed. Nothing on any
screen admits it. So the assertions here are on quantities and on the recommendations a run
actually produces, never only on which rows come back.

Every test seeds TWO companies, each with a warehouse, and the SAME product code in both - the
production shape, where 11,390 codes exist twice. Marker-prefixed, inside `pg_session`'s
rolled-back transaction, nothing borrowed with `LIMIT 1`.

TEST-FIRST: these are expected to be red on the current behaviour.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest

from app.models.base import set_company_scope
from app.models.company import Company
from app.models.inventory import Stock, Warehouse
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import ReorderRecommendation, ReorderRun
from app.services.scm import reorder_run_service as svc
from app.services.scm.coverage_service import CoverageService
from app.services.sla_service import MALAYSIA_TZ, to_naive_datetime
from tests._pg_fixture import pg_session

MARKER = "ZZTCOISO"


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


def _today() -> date:
    return to_naive_datetime(datetime.now(MALAYSIA_TZ)).date()


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def two_companies(db):
    """Company A and B, each owning a warehouse, each holding the SAME product code.

    B is given MORE stock than A, so a leak shows up as extra cover rather than as a missing
    row: if B's 5,000 units are counted into A's position, A's shortfall disappears.
    """
    set_company_scope(db, None)
    a = Company(id=_u(), code=_code("CA")[:20], name=f"{MARKER} company A")
    b = Company(id=_u(), code=_code("CB")[:20], name=f"{MARKER} company B")
    db.add_all([a, b])
    db.flush()

    cat = ProductCategory(
        id=_u(), category_code=_code("CAT")[:40], category_name=_code("cat")
    )
    uom = UnitOfMeasure(id=_u(), uom_name=_code("uom"), uom_code=_code("U")[:20])
    db.add_all([cat, uom])
    db.flush()

    shared_code = _code("DUP")
    p_a = Product(
        id=_u(), company_id=a.id, product_code=shared_code, product_name="A's copy",
        category_id=cat.id, base_uom_id=uom.id, list_price=0,
        is_active=True, is_discontinued=False,
    )
    db.add(p_a)
    db.flush()
    p_b = Product(
        id=_u(), company_id=b.id, product_code=shared_code, product_name="B's copy",
        category_id=cat.id, base_uom_id=uom.id, list_price=0,
        is_active=True, is_discontinued=False,
    )
    db.add(p_b)
    db.flush()

    wh_a = Warehouse(
        id=_u(), company_id=a.id, warehouse_code=_code("WHA")[:30],
        warehouse_name="A's warehouse", is_active=True, counts_as_available=True,
    )
    db.add(wh_a)
    db.flush()
    wh_b = Warehouse(
        id=_u(), company_id=b.id, warehouse_code=_code("WHB")[:30],
        warehouse_name="B's warehouse", is_active=True, counts_as_available=True,
    )
    db.add(wh_b)
    db.flush()
    wh_a.pool_warehouse_id = wh_a.id
    wh_b.pool_warehouse_id = wh_b.id
    db.flush()

    # A is short: 10 on hand against 100 committed. B is long: 5,000 on hand.
    # `company_id` is set EXPLICITLY. `stock` carries the column and is company-scoped, and
    # the auto-stamp takes the session's active scope - which is None while this fixture
    # seeds both companies, so an unstamped row would be NULL and belong to neither.
    db.add(Stock(id=_u(), company_id=a.id, product_id=p_a.id, warehouse_id=wh_a.id,
                 quantity_on_hand=10))
    db.add(Stock(id=_u(), company_id=b.id, product_id=p_b.id, warehouse_id=wh_b.id,
                 quantity_on_hand=5000))
    db.flush()

    cust = Customer(id=_u(), company_id=a.id, customer_code=_code("C")[:30],
                    customer_name=f"{MARKER} dealer")
    db.add(cust)
    db.flush()
    so = SalesOrder(
        id=_u(), company_id=a.id, so_number=_code("SO")[:50], customer_id=cust.id,
        status="open", order_type="dealer", order_date=_today() - timedelta(days=3),
    )
    db.add(so)
    db.flush()
    db.add(SalesOrderLine(
        id=_u(), company_id=a.id, sales_order_id=so.id, product_id=p_a.id,
        warehouse_id=wh_a.id, qty_ordered=100, qty_delivered=0,
        required_date=_today() + timedelta(days=10), line_status="open",
    ))
    db.flush()
    return {
        "a": a, "b": b, "code": shared_code,
        "p_a": p_a, "p_b": p_b, "wh_a": wh_a, "wh_b": wh_b,
    }


def _as_a(db, f):
    set_company_scope(db, frozenset({str(f["a"].id)}))


# --------------------------------------------------------------------------- #
# the warehouse set: the one place the scope is applied
# --------------------------------------------------------------------------- #


def test_an_unscoped_run_lists_only_this_companys_warehouses(db, two_companies):
    """The daily run takes no codes, so it enumerates warehouses - for ONE company."""
    f = two_companies
    _as_a(db, f)

    ids = [str(x) for x in svc._resolve_warehouse_ids(db, None)]

    assert str(f["wh_a"].id) in ids
    assert str(f["wh_b"].id) not in ids


def test_the_availability_network_is_this_companys_locations_only(db, two_companies):
    """`network_positions` nets over every counting location, and "every" means this company's.

    Netting B's warehouse into A's network is precisely the invisible failure: it adds cover.
    """
    f = two_companies
    _as_a(db, f)

    ids = CoverageService(db).availability_warehouse_ids()

    assert str(f["wh_a"].id) in ids
    assert str(f["wh_b"].id) not in ids


# --------------------------------------------------------------------------- #
# positions: the leak that adds cover
# --------------------------------------------------------------------------- #


def test_another_companys_stock_does_not_cover_this_companys_demand(db, two_companies):
    """THE test. A holds 10 against 100 committed; B holds 5,000 of the same code.

    If B's stock reaches A's position, A's dated shortfall of 90 becomes zero and the buy is
    silently suppressed. Asserted on the quantity, because the row count would look right
    either way: one product, one position, wrong number.
    """
    f = two_companies
    _as_a(db, f)

    pos = CoverageService(db).network_positions([str(f["p_a"].id)])[str(f["p_a"].id)]

    assert pos.on_hand == 10, "another company's stock was counted as on hand"
    assert pos.shortfall == 90, "another company's stock covered this company's demand"


def test_the_planning_rows_of_a_run_name_only_this_companys_locations(db, two_companies):
    """`_planning_rows` is raw SQL over `scm.net_position_v`, so the ORM filter never sees it."""
    f = two_companies
    _as_a(db, f)

    rows = svc._planning_rows(db, None)
    marker_rows = [r for r in rows if str(r["product_id"]) in
                   (str(f["p_a"].id), str(f["p_b"].id))]

    assert marker_rows, "the seeded product produced no planning row at all"
    codes = {r["warehouse_code"] for r in marker_rows}
    assert f["wh_a"].warehouse_code in codes
    assert f["wh_b"].warehouse_code not in codes, (
        "a plan for company A enumerated company B's warehouse"
    )


def test_a_product_scoped_run_plans_only_this_companys_copy_of_the_code(db, two_companies):
    """The duplicate-code case, end to end through a real run.

    Both companies hold the code, so a narrowed run must resolve to A's product and plan A's
    location. The recommendation is what is asserted: it is what a buyer acts on.
    """
    f = two_companies
    _as_a(db, f)

    out = svc.create_run(
        db, [f["wh_a"].warehouse_code], product_codes=[f["code"]], enqueue=False
    )
    svc.run_reorder(out["run_id"], db=db)

    recs = (
        db.query(ReorderRecommendation)
        .filter(ReorderRecommendation.run_id == out["run_id"])
        .all()
    )
    assert recs, "the run produced no recommendation for a product that is 90 short"
    assert {str(r.product_id) for r in recs} == {str(f["p_a"].id)}
    assert str(f["p_b"].id) not in {str(r.product_id) for r in recs}
    for r in recs:
        assert r.warehouse_id in (None, f["wh_a"].id)


# --------------------------------------------------------------------------- #
# the run is a company's plan
# --------------------------------------------------------------------------- #


def test_a_run_records_the_company_it_planned_for(db, two_companies):
    """The RQ work-horse receives ONLY a run id.

    There is no request and therefore no company scope, and UNSET fails CLOSED - so a worker
    that relied on ambient scope would read nothing and the daily plan would silently produce
    zero recommendations. The scope has to be a property of the run.
    """
    f = two_companies
    _as_a(db, f)

    out = svc.create_run(db, [f["wh_a"].warehouse_code], enqueue=False)
    run = db.get(ReorderRun, out["run_id"])

    assert str(run.company_id) == str(f["a"].id)


def test_a_run_belonging_to_another_company_is_not_visible(db, two_companies):
    """A run list under A must not show B's plans: they are a different company's decisions."""
    f = two_companies
    set_company_scope(db, frozenset({str(f["b"].id)}))
    b_run = svc.create_run(db, [f["wh_b"].warehouse_code], enqueue=False)

    _as_a(db, f)
    visible = {
        str(r.id)
        for r in db.query(ReorderRun).filter(ReorderRun.source_ref == "run").all()
    }

    assert b_run["run_id"] not in visible


def test_the_page_opens_on_this_companys_run_not_the_most_recent_one(db, two_companies):
    """`today_or_latest_run` is raw SQL, so the ORM filter never sees it.

    Without a predicate the reorder page opens on whichever company ran most recently, which
    is another company's plan wearing this company's chrome - and every figure on it is about
    stock this company does not hold.
    """
    f = two_companies
    _as_a(db, f)
    a_run = svc.create_run(db, [f["wh_a"].warehouse_code], enqueue=False)
    svc.run_reorder(a_run["run_id"], db=db)
    _as_a(db, f)

    # B runs LAST, so an unscoped "latest" picks B.
    set_company_scope(db, frozenset({str(f["b"].id)}))
    b_run = svc.create_run(db, [f["wh_b"].warehouse_code], enqueue=False)
    svc.run_reorder(b_run["run_id"], db=db)

    _as_a(db, f)
    picked = svc.today_or_latest_run(db)

    assert picked is not None, "company A has a completed run of its own"
    assert str(picked["row"]["id"]) == a_run["run_id"], (
        "the page opened on another company's plan"
    )


def test_the_low_stock_signal_reads_this_companys_run(db, two_companies):
    """The dashboard's ROP source is the latest completed run, picked in raw SQL too.

    Another company's frozen reorder points would produce a low-stock warning list about
    stock this company does not hold.
    """
    from app.services.scm.dashboard_service import ScmDashboardService

    f = two_companies
    _as_a(db, f)
    a_run = svc.create_run(db, [f["wh_a"].warehouse_code], enqueue=False)
    svc.run_reorder(a_run["run_id"], db=db)

    set_company_scope(db, frozenset({str(f["b"].id)}))
    b_run = svc.create_run(db, [f["wh_b"].warehouse_code], enqueue=False)
    svc.run_reorder(b_run["run_id"], db=db)

    _as_a(db, f)
    picked = ScmDashboardService(db)._latest_completed_run_id()

    assert str(picked) == a_run["run_id"]


def test_the_worker_plans_the_runs_own_company_with_no_ambient_scope(db, two_companies):
    """The RQ work-horse has NO scope, and UNSET fails closed.

    So a worker that relied on ambient scope would read no warehouses and no positions, and
    the daily plan would complete with zero recommendations - which reads as a quiet week
    rather than as a broken job. Simulated by clearing the scope before the run, exactly as
    the work-horse starts.
    """
    from app.models.base import UNSET, set_company_scope as _set

    f = two_companies
    _as_a(db, f)
    out = svc.create_run(db, [f["wh_a"].warehouse_code], enqueue=False)

    _set(db, UNSET)  # the worker's starting state
    svc.run_reorder(out["run_id"], db=db)

    _as_a(db, f)
    recs = (
        db.query(ReorderRecommendation)
        .filter(ReorderRecommendation.run_id == out["run_id"])
        .all()
    )
    assert recs, "the worker planned nothing because it never adopted the run's company"
    assert {str(r.product_id) for r in recs} == {str(f["p_a"].id)}
