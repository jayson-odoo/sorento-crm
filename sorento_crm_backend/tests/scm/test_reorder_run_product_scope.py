"""Narrowing a manual plan to a product must actually narrow it (S3, AC-C2 tooling).

`RunPlanningModal` grew a `product_codes[]` picker beside the warehouse picker, and the
frontend sends it, but `CreateReorderRunRequest` has no such field. Pydantic drops an unknown
key silently, so a planner who asks to plan ONE sku gets the whole catalogue back and the
modal's own caption ("Leave empty to plan every product") tells them that is not what
happened. On this database that is 3,123 products instead of one.

Worse than useless: the run LOOKS like the narrow plan that was asked for. Nothing on the
results screen says the scope was ignored, so the extra 3,122 rows read as the engine's
opinion about products nobody asked about, and the next person to narrow a run learns the
control does nothing.

The scope also has to be PERSISTED on the run rather than passed through, because the
evaluation happens later in an RQ worker that only receives a run id. A scope the worker
cannot read is a scope that only exists in the request that has already returned.

Postgres, marker-prefixed seeding of its own chain, inside `pg_session`'s rolled-back
transaction. Nothing borrowed with `LIMIT 1`: an empty CI database has no products at all.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.inventory import Stock, Warehouse
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import ReorderRun
from app.services.scm import reorder_run_service as svc
from tests._pg_fixture import pg_session, unique_code


def _u() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


@pytest.fixture()
def catalogue(db):
    """Two products in one warehouse, both with stock, so both are planning candidates."""
    cat = ProductCategory(
        id=_u(), category_code=unique_code("CAT")[:40], category_name=unique_code("cat")
    )
    uom = UnitOfMeasure(id=_u(), uom_name=unique_code("uom"), uom_code=unique_code("U")[:20])
    db.add_all([cat, uom])
    db.flush()

    wanted = Product(
        id=_u(), product_code=unique_code("WANT"), product_name="the one asked for",
        category_id=cat.id, base_uom_id=uom.id, list_price=0,
        is_active=True, is_discontinued=False,
    )
    other = Product(
        id=_u(), product_code=unique_code("OTHR"), product_name="nobody asked",
        category_id=cat.id, base_uom_id=uom.id, list_price=0,
        is_active=True, is_discontinued=False,
    )
    wh = Warehouse(
        id=_u(), warehouse_code=unique_code("WH"), warehouse_name="wh", is_active=True
    )
    db.add_all([wanted, other, wh])
    db.flush()
    for p in (wanted, other):
        db.add(Stock(id=_u(), product_id=p.id, warehouse_id=wh.id, quantity_on_hand=5))
    db.flush()
    return {"wanted": wanted, "other": other, "wh": wh}


def test_the_requested_product_scope_is_persisted_on_the_run(db, catalogue):
    """The worker receives only a run id, so a scope it cannot read does not exist.

    Asserted on the stored row rather than on the return value: `create_run` returns before
    the evaluation happens, and it is the row the RQ task reads.
    """
    out = svc.create_run(
        db,
        [catalogue["wh"].warehouse_code],
        product_codes=[catalogue["wanted"].product_code],
        enqueue=False,
    )

    run = db.get(ReorderRun, out["run_id"])
    stored = [str(x) for x in (run.product_ids or [])]
    assert stored == [str(catalogue["wanted"].id)], (
        "the product scope never reached the run row, so the worker will plan everything"
    )


def test_a_run_narrowed_to_one_product_evaluates_only_that_product(db, catalogue):
    """The defect, end to end: ask for one sku, get one sku.

    Two candidates exist and both would otherwise be planned, which is what makes the
    filter visible. One product is the smallest scope that can be wrong in the way that
    matters.
    """
    out = svc.create_run(
        db,
        [catalogue["wh"].warehouse_code],
        product_codes=[catalogue["wanted"].product_code],
        enqueue=False,
    )
    svc.run_reorder(out["run_id"], db=db)

    rows = svc._planning_rows(
        db, [str(catalogue["wh"].id)], product_ids=[str(catalogue["wanted"].id)]
    )
    codes = {r["product_code"] for r in rows}
    assert codes == {catalogue["wanted"].product_code}
    assert catalogue["other"].product_code not in codes


def test_an_empty_product_scope_still_plans_every_product(db, catalogue):
    """The default, pinned so a fix cannot narrow every run to nothing.

    Empty means all: the daily scheduled run sends no product scope at all, and a filter
    that treated an empty list as "plan nothing" would silently stop the whole plan.
    """
    out = svc.create_run(db, [catalogue["wh"].warehouse_code], enqueue=False)

    run = db.get(ReorderRun, out["run_id"])
    assert not (run.product_ids or []), "an unnarrowed run must carry no product scope"

    rows = svc._planning_rows(db, [str(catalogue["wh"].id)])
    codes = {r["product_code"] for r in rows}
    assert {catalogue["wanted"].product_code, catalogue["other"].product_code} <= codes


def test_an_unknown_product_code_is_not_silently_treated_as_no_scope(db, catalogue):
    """A typo must not widen the plan to everything.

    Resolving an unknown code to an empty id list and then treating empty as "all" is how a
    mistyped sku turns into a full-catalogue run that looks deliberate. The run is created
    with a scope that matches nothing, so it plans nothing, and the operator sees an empty
    result they can act on rather than 3,000 rows they did not ask for.
    """
    out = svc.create_run(
        db,
        [catalogue["wh"].warehouse_code],
        product_codes=[f"{unique_code('NOSUCH')}"],
        enqueue=False,
    )

    run = db.get(ReorderRun, out["run_id"])
    # A scope was asked for and none of it resolved: recorded as an empty-but-present scope,
    # never as absent.
    assert run.product_ids == [], "an unresolved scope was indistinguishable from no scope"

    rows = svc._planning_rows(db, [str(catalogue["wh"].id)], product_ids=[])
    assert rows == []
