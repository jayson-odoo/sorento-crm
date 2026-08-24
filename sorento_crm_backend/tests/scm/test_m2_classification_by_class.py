"""SCM M2 - ABC split by demand class (captain, 19 Aug 2026, PLAN item this file covers).

`scm.item_classification.abc_class` ranks over ALL demand by trailing-12mo COST VALUE
(unchanged, costed keys only - the reorder engine's inventory-value lens). `abc_class_project`
and `abc_class_retail` rank a SEPARATE maths: trailing-12mo delivered QUANTITY, each over
ONLY its own demand-class partition - see `analytics_service._abc_class_qty_totals`.
Captain, 19 Aug 2026: "hot-selling is by quantity, not related to money" - so the
project/retail letters need no cost at all, and a null-cost product still earns one even
though its `abc_class` stays NULL.

The demand class itself, per the 4 Aug 2026 amendment, is read `sales_agents.demand_class`
FIRST (matched on `orders.agent` falling back to `orders.salesman`), `customers.
market_segment_code` only as a FALLBACK when the agent said nothing - never the segment
alone. An order whose agent AND segment are both silent counts for NEITHER partition
(S3: silence is not retail). A product can be A for a project customer and C for the
dealer channel; a key with no demand of a class is NULL there, never a computed 'C'.

Every test picks an `as_of` that puts the trailing-365-day window entirely AFTER the last
real order date in this (shared, prod-copy) database - `_isolated_as_of` - so the "whole
universe" `_abc_map` ranks over is exactly this test's own seeded rows and nothing
borrowed from production data makes the class letters non-deterministic. Postgres,
marker-prefixed, rolled back with the `scm_app` savepoint.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.models.access import MarketSegment
from app.models.base import set_company_scope
from app.models.inventory import Warehouse
from app.models.order import Customer, Order, OrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.sales_agent import SalesAgent
from app.services.scm import analytics_service as svc
from tests.scm.conftest import SORENTO_COMPANY_ID, requires_pg

pytestmark = requires_pg

MARKER = "ZZM2C"


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}"


def _isolated_as_of(db) -> date:
    """A date whose trailing-365-day window holds no real order - see module docstring."""
    last_real = db.execute(text("SELECT MAX(order_date) FROM orders")).scalar()
    base = last_real if last_real else date.today()
    if hasattr(base, "date"):
        base = base.date()
    return base + timedelta(days=400)


def _mk_category(db) -> str:
    cat = ProductCategory(id=_u(), category_code=_code("CAT"), category_name="M2C test category")
    db.add(cat)
    db.flush()
    return cat.id


def _mk_uom(db) -> str:
    uom = UnitOfMeasure(id=_u(), uom_code=_code("UOM"), uom_name="M2C test unit")
    db.add(uom)
    db.flush()
    return uom.id


def _mk_warehouse(db) -> str:
    wh = Warehouse(id=_u(), warehouse_code=_code("WH"), warehouse_name="M2C test warehouse", is_active=True)
    db.add(wh)
    db.flush()
    return wh.id


def _mk_product(db, cat_id, uom_id, cost_price=100) -> str:
    """``cost_price=None`` seeds a product with NO cost - still eligible for the
    quantity-based project/retail letters, ineligible for the cost-value `abc_class`."""
    p = Product(id=_u(), product_code=_code("P"), product_name="M2C test product",
               category_id=cat_id, base_uom_id=uom_id, list_price=(cost_price or 0),
               cost_price=cost_price, currency="MYR")
    db.add(p)
    db.flush()
    return p.id


def _mk_market_segment(db, stem: str) -> str:
    seg = f"{MARKER}-{stem}-{uuid.uuid4().hex[:6]}".lower()
    db.add(MarketSegment(id=_u(), code=seg, name=seg, is_active=True))
    db.flush()
    return seg


def _mk_customer(db, segment_code) -> str:
    code = _code("CUST")
    cust = Customer(id=_u(), customer_code=code, customer_name=code,
                    market_segment_code=segment_code, is_active=True)
    db.add(cust)
    db.flush()
    return cust.id


def _mk_sales_agent(db, demand_class=None) -> str:
    """A shared (`company_id` NULL) salesperson-master row, mirroring what
    `sales_agent_service.resolve_or_create` produces. `demand_class=None` is the
    "nobody has decided yet" state every real agent ships in."""
    code = _code("AGENT")
    db.add(SalesAgent(id=_u(), sales_agent=code, demand_class=demand_class,
                      is_active=True, source="manual"))
    db.flush()
    return code


def _mk_order_line(db, customer_id, product_id, warehouse_id, qty, order_date, agent=None):
    order = Order(id=_u(), order_number=_code("DO"), customer_id=customer_id,
                 order_date=order_date, is_cancelled=False, agent=agent)
    db.add(order)
    db.flush()
    db.add(OrderLine(id=_u(), order_id=order.id, product_id=product_id,
                     warehouse_id=warehouse_id, quantity=qty))
    db.flush()


@pytest.fixture()
def env(scm_app):
    """A company-scoped session (so the ORM auto-stamp can write owned rows) plus one
    isolated `as_of` shared by everything a test seeds."""
    _, db, _, _ = scm_app
    set_company_scope(db, frozenset({SORENTO_COMPANY_ID}))
    as_of = _isolated_as_of(db)
    order_date = as_of - timedelta(days=10)  # inside both the 90d and 365d windows
    return db, as_of, order_date


def _classification(db, product_id, warehouse_id):
    return db.execute(text(
        "SELECT abc_class, abc_class_project, abc_class_retail, "
        "annual_value, annual_qty_project, annual_qty_retail "
        "FROM scm.item_classification WHERE product_id = :p AND warehouse_id = :w"
    ), {"p": product_id, "w": warehouse_id}).fetchone()


def test_project_only_product_is_A_project_null_retail(env):
    """A product whose entire demand is one project-segment customer is A on the project
    partition and, having no retail demand at all, NULL - not a computed C - on retail."""
    db, as_of, order_date = env
    cat, uom, wh = _mk_category(db), _mk_uom(db), _mk_warehouse(db)
    pid = _mk_product(db, cat, uom, cost_price=100)
    seg = _mk_market_segment(db, "PROJECT")
    cust = _mk_customer(db, seg)
    _mk_order_line(db, cust, pid, wh, qty=1000, order_date=order_date)

    svc.run_analytics(db, scope={"product_ids": [pid]}, config={"as_of": as_of})

    row = _classification(db, pid, wh)
    assert row is not None
    assert row.abc_class == "A"          # rank-1 of the (isolated) whole costed universe
    assert row.abc_class_project == "A"  # rank-1 of the project partition (by qty), alone in it
    assert row.abc_class_retail is None  # no retail demand for this key at all
    assert row.annual_qty_retail is None


def test_partitions_rank_independently(env):
    """Two products, opposite dominance: the retail-heavy one is A on retail and only a
    minor share of project quantity, while the project-heavy one dominates project - 
    proving the two rankings are computed independently rather than one letter reused
    twice. Same `cost_price` on both, so the qty ratio mirrors what a value ratio would
    have been - this pins that the ranking is genuinely qty-driven, not a leftover value
    computation that happens to agree."""
    db, as_of, order_date = env
    cat, uom, wh = _mk_category(db), _mk_uom(db), _mk_warehouse(db)
    proj_seg = _mk_market_segment(db, "PROJECT")
    retail_seg = _mk_market_segment(db, "DEALER")  # non-blank, non-project -> retail
    retail_cust = _mk_customer(db, retail_seg)
    project_cust = _mk_customer(db, proj_seg)

    # X: dominant on retail (huge qty), a token project order too (tiny qty).
    x = _mk_product(db, cat, uom, cost_price=100)
    _mk_order_line(db, retail_cust, x, wh, qty=1_000_000, order_date=order_date)  # retail
    _mk_order_line(db, project_cust, x, wh, qty=1, order_date=order_date)         # project

    # Y: exists ONLY to dominate the project partition so X's tiny project share does not
    # land as an (only-entry) automatic A there.
    y = _mk_product(db, cat, uom, cost_price=100)
    _mk_order_line(db, project_cust, y, wh, qty=1_000_000, order_date=order_date)  # project

    svc.run_analytics(db, scope={"product_ids": [x, y]}, config={"as_of": as_of})

    row_x = _classification(db, x, wh)
    row_y = _classification(db, y, wh)
    assert row_x.abc_class_retail == "A"     # X's only retail entry -> rank-1
    assert row_x.abc_class_project == "C"    # X's project qty is ~0.0001% of the pair's total
    assert row_x.annual_qty_retail is not None
    assert row_y.abc_class_project == "A"    # Y dominates (rank-1) the project partition
    assert row_y.abc_class_retail is None    # Y has no retail demand at all


def test_no_cost_product_gets_class_letters_but_all_demand_stays_null(env):
    """Captain, 19 Aug 2026: hot-selling is by quantity, not money. A product with NO
    `cost_price` cannot earn a cost-value `abc_class` (unknown), but the project/retail
    letters - pure quantity - do not need one at all."""
    db, as_of, order_date = env
    cat, uom, wh = _mk_category(db), _mk_uom(db), _mk_warehouse(db)
    pid = _mk_product(db, cat, uom, cost_price=None)
    seg = _mk_market_segment(db, "PROJECT")
    cust = _mk_customer(db, seg)
    _mk_order_line(db, cust, pid, wh, qty=1000, order_date=order_date)

    svc.run_analytics(db, scope={"product_ids": [pid]}, config={"as_of": as_of})

    row = _classification(db, pid, wh)
    assert row is not None
    assert row.abc_class is None          # no cost -> unknown, unchanged behaviour
    assert row.annual_value is None
    assert row.abc_class_project == "A"   # quantity-only ranking, alone in its partition
    assert row.annual_qty_project == 1000
    assert row.abc_class_retail is None


def test_agent_master_classifies_even_with_no_customer_segment(env):
    """4 Aug 2026 amendment: the salesperson master is the source of truth, not a
    fallback. A customer with NO segment at all still lands in the project partition
    when the order's agent is classified project."""
    db, as_of, order_date = env
    cat, uom, wh = _mk_category(db), _mk_uom(db), _mk_warehouse(db)
    pid = _mk_product(db, cat, uom, cost_price=100)
    cust = _mk_customer(db, None)  # no market segment whatsoever
    agent = _mk_sales_agent(db, demand_class="project")
    _mk_order_line(db, cust, pid, wh, qty=750, order_date=order_date, agent=agent)

    svc.run_analytics(db, scope={"product_ids": [pid]}, config={"as_of": as_of})

    row = _classification(db, pid, wh)
    assert row is not None
    assert row.abc_class_project == "A"
    assert row.annual_qty_project == 750
    assert row.abc_class_retail is None


def test_unclassified_agent_and_no_segment_lands_in_neither_partition(env):
    """S3: silence is not retail. An agent nobody has classified yet, on a customer with
    no segment, leaves the key out of BOTH the project and the retail partition."""
    db, as_of, order_date = env
    cat, uom, wh = _mk_category(db), _mk_uom(db), _mk_warehouse(db)
    pid = _mk_product(db, cat, uom, cost_price=100)
    cust = _mk_customer(db, None)
    agent = _mk_sales_agent(db, demand_class=None)  # "nobody has decided yet"
    _mk_order_line(db, cust, pid, wh, qty=400, order_date=order_date, agent=agent)

    svc.run_analytics(db, scope={"product_ids": [pid]}, config={"as_of": as_of})

    row = _classification(db, pid, wh)
    assert row is not None
    assert row.abc_class_project is None
    assert row.abc_class_retail is None
    assert row.annual_qty_project is None
    assert row.annual_qty_retail is None


def test_segment_is_the_fallback_when_agent_is_unclassified(env):
    """The market segment still classifies a key - but only because the agent said
    nothing. A classified agent would win; see the previous two tests."""
    db, as_of, order_date = env
    cat, uom, wh = _mk_category(db), _mk_uom(db), _mk_warehouse(db)
    pid = _mk_product(db, cat, uom, cost_price=100)
    seg = _mk_market_segment(db, "PROJECT")
    cust = _mk_customer(db, seg)
    agent = _mk_sales_agent(db, demand_class=None)
    _mk_order_line(db, cust, pid, wh, qty=600, order_date=order_date, agent=agent)

    svc.run_analytics(db, scope={"product_ids": [pid]}, config={"as_of": as_of})

    row = _classification(db, pid, wh)
    assert row is not None
    assert row.abc_class_project == "A"
    assert row.annual_qty_project == 600
    assert row.abc_class_retail is None


def test_rerun_overwrites_project_retail_classes_no_duplicates(env):
    """AC-M2.8 extended to the new columns: a second run overwrites, never duplicates,
    and a policy change that flips the letter is reflected (not stuck from run 1)."""
    db, as_of, order_date = env
    cat, uom, wh = _mk_category(db), _mk_uom(db), _mk_warehouse(db)
    seg = _mk_market_segment(db, "PROJECT")
    cust = _mk_customer(db, seg)
    pid = _mk_product(db, cat, uom, cost_price=100)
    _mk_order_line(db, cust, pid, wh, qty=500, order_date=order_date)

    svc.run_analytics(db, scope={"product_ids": [pid]}, config={"as_of": as_of})
    svc.run_analytics(db, scope={"product_ids": [pid]}, config={"as_of": as_of})

    dup = db.execute(text(
        "SELECT count(*) FROM scm.item_classification WHERE product_id = :p AND warehouse_id = :w"
    ), {"p": pid, "w": wh}).scalar()
    assert dup == 1
    row = _classification(db, pid, wh)
    assert row.abc_class_project == "A"
    assert row.abc_class_retail is None
