"""A planning run's scope must not widen, and must not cross a company boundary.

Two defects of the same family, both in `create_run`'s code-to-id resolution, both of
which make a run plan MORE than was asked for while looking like it planned exactly that.

**1. An unresolved warehouse code planned every warehouse.** `_resolve_warehouse_ids`
returns `[]` when codes were given and none matched, and `_planning_rows` read a falsy
list as "no warehouse filter". So a mistyped location silently became the whole network.
This is the same shape as the product-scope defect in
`test_reorder_run_product_scope.py`, and it has to be fixed with the same three-state
convention or the two scopes disagree about what empty means: `None` is no scope asked
for, a list is that scope, and `[]` is a scope asked for that resolved to nothing.

**2. Code resolution crossed companies.** Both resolvers used raw SQL, and the
multi-company isolation filter runs on ORM execution ONLY - a `SELECT ... FROM products
WHERE product_code = ANY(...)` sees EVERY company. Not theoretical: each company carries
its own copy of the catalogue, so 11,390 product codes exist twice in the real database,
and narrowing a Sorento plan to one code put another company's product in the run's
persisted scope. Today that extra id is inert because only one company owns warehouses,
so `net_position_v` yields nothing for it - which is exactly why it needs a test rather
than a note. The trap arms itself the day the second company gets a warehouse.

The properties under test are about resolution, not source text: what ids the run row
actually carries, and what a scope resolves to under a given company scope. Reverting
either resolver to raw SQL fails these.

Postgres, marker-prefixed seeding of its own chain, inside `pg_session`'s rolled-back
transaction. Nothing borrowed with `LIMIT 1`: CI's database has no products at all.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.base import set_company_scope
from app.models.company import Company
from app.models.inventory import Stock, Warehouse
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import ReorderRun
from app.services.scm import reorder_run_service as svc
from tests._pg_fixture import pg_session, unique_code

MARKER = "ZZTRSI"


def _u() -> str:
    return str(uuid.uuid4())


def _code(stem: str) -> str:
    return f"{MARKER}-{stem}-{uuid.uuid4().hex[:8]}".upper()


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def two_companies(db):
    """Company A and B, each holding a product under the SAME code.

    The duplicate is the production shape. B is inserted second so a raw lookup keyed by
    code resolves to B's row, which makes the cross-company failure deterministic rather
    than dependent on row order.
    """
    a = Company(id=_u(), code=_code("CA")[:20], name=f"{MARKER} company A")
    b = Company(id=_u(), code=_code("CB")[:20], name=f"{MARKER} company B")
    db.add_all([a, b])
    db.flush()

    # Reference data is seeded unscoped so both companies' products can point at it.
    set_company_scope(db, None)
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
        warehouse_name="A's warehouse", is_active=True,
    )
    db.add(wh_a)
    db.flush()
    wh_b = Warehouse(
        id=_u(), company_id=b.id, warehouse_code=_code("WHB")[:30],
        warehouse_name="B's warehouse", is_active=True,
    )
    db.add(wh_b)
    db.flush()
    db.add(Stock(id=_u(), product_id=p_a.id, warehouse_id=wh_a.id, quantity_on_hand=5))
    db.flush()
    return {
        "a": a, "b": b, "code": shared_code,
        "p_a": p_a, "p_b": p_b, "wh_a": wh_a, "wh_b": wh_b,
    }


# --------------------------------------------------------------------------- #
# 1. an unresolved scope must plan nothing, never everything
# --------------------------------------------------------------------------- #


def test_an_unknown_warehouse_code_does_not_widen_the_plan_to_every_warehouse(db):
    """A mistyped location must plan nothing, not the whole network.

    Asserted through `_planning_rows`, because that is where the widening happened: the
    resolver's own `[]` was correct and the consumer read it as "no filter".
    """
    out = svc.create_run(db, [_code("NOSUCH")], enqueue=False)

    run = db.get(ReorderRun, out["run_id"])
    assert run.warehouse_ids == [], (
        "a warehouse scope that resolved to nothing was recorded as absent"
    )
    assert svc._planning_rows(db, []) == [], (
        "an unresolved warehouse scope widened the plan to every warehouse"
    )


def test_no_warehouse_scope_still_plans_every_warehouse(db):
    """The daily run's default, pinned so the fix cannot narrow it to nothing.

    Distinguishing `[]` from "absent" is only safe if absent keeps meaning all. A fix that
    read both as "plan nothing" would silently stop the scheduled plan, which is a worse
    failure than the one being fixed because nobody gets an empty screen to complain about.
    """
    wh = Warehouse(
        id=_u(), warehouse_code=_code("WH")[:30], warehouse_name="wh", is_active=True
    )
    db.add(wh)
    db.flush()

    out = svc.create_run(db, None, enqueue=False)
    run = db.get(ReorderRun, out["run_id"])
    assert run.warehouse_ids, "an unscoped run must carry the full warehouse list"
    assert str(wh.id) in [str(x) for x in run.warehouse_ids]


# --------------------------------------------------------------------------- #
# 2. resolution must not cross a company boundary
# --------------------------------------------------------------------------- #


def test_a_product_code_resolves_only_within_the_active_company(db, two_companies):
    """Under company A, the duplicated code is A's product and only A's.

    B's row is inserted second, so a raw lookup returns both ids (and a dict keyed by code
    would keep B's). Either way the run's persisted scope names a product company A does
    not own.
    """
    f = two_companies
    set_company_scope(db, frozenset({str(f["a"].id)}))

    resolved = svc._resolve_product_ids(db, [f["code"]])

    assert resolved == [str(f["p_a"].id)], (
        f"product-code resolution crossed a company boundary: {resolved}"
    )


def test_a_product_code_owned_only_by_another_company_resolves_to_nothing(db, two_companies):
    """A code company A does not hold must fail to resolve, never borrow B's row.

    This half is deterministic regardless of row order, so it fails on a raw lookup every
    time. Resolving to `[]` also has the right downstream meaning: a scope was asked for
    and nothing matched, so the run plans nothing.
    """
    f = two_companies
    b_only = _code("BONLY")
    set_company_scope(db, None)
    db.add(Product(
        id=_u(), company_id=f["b"].id, product_code=b_only, product_name="B only",
        category_id=f["p_b"].category_id, base_uom_id=f["p_b"].base_uom_id,
        list_price=0, is_active=True, is_discontinued=False,
    ))
    db.flush()
    set_company_scope(db, frozenset({str(f["a"].id)}))

    assert svc._resolve_product_ids(db, [b_only]) == [], (
        "resolution borrowed another company's product"
    )


def test_a_warehouse_code_resolves_only_within_the_active_company(db, two_companies):
    """The same property for the location scope.

    Warehouse codes are not duplicated across companies in the real data today, so the
    evidence here is the other-company-only shape: under A, B's code must not resolve.
    """
    f = two_companies
    set_company_scope(db, frozenset({str(f["a"].id)}))

    assert svc._resolve_warehouse_ids(db, [f["wh_b"].warehouse_code]) == [], (
        "warehouse-code resolution borrowed another company's warehouse"
    )
    assert svc._resolve_warehouse_ids(db, [f["wh_a"].warehouse_code]) == [
        str(f["wh_a"].id)
    ]


def test_an_unscoped_run_plans_only_the_active_company_warehouses(db, two_companies):
    """The daily run must not sweep another company's network into this company's plan.

    This is the one that bites the day the second company gets a warehouse: with no codes
    given, the resolver lists every active warehouse, and an unfiltered list is a plan for
    somebody else's stock.
    """
    f = two_companies
    set_company_scope(db, frozenset({str(f["a"].id)}))

    ids = [str(x) for x in svc._resolve_warehouse_ids(db, None)]

    assert str(f["wh_a"].id) in ids
    assert str(f["wh_b"].id) not in ids, (
        "an unscoped run listed another company's warehouse"
    )
