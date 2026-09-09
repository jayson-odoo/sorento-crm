"""AC-S13.1/AC-S13.3/AC-S13.4 (round 2, reorder-feedback-9sep, PLAN-reorder-feedback-9sep.md
section 4 "Round 2", S13).

Ruling (captain, screenshots 17-20): "MOQ edits land only as `set_moq_override` on the
recommendation (per run)" - a MOQ the buyer types is thrown away the moment the plan is
re-run. This lane makes `reorder_run_service.set_moq_override` (both callers - the bulk
`PUT .../plan-edits` moq field, and the single `PUT /recommendations/{id}/moq`) ALSO
remember the figure on the `product_suppliers` link, so the NEXT run picks it up the way
`reorder_engine.load_supplier_candidates` already reads `product_suppliers.moq` for
whichever supplier `select_supplier` chooses (`_supplier_choice` freezes it onto the
rec's own `inputs.supplier.moq`, alongside the top-level `inputs.moq` `effective_moq`
already reads).

Supplier resolution order for WHICH (product, supplier) link is remembered (plan 4, S13
design): the row's own CHOSEN supplier (`scm.plan_row_decision.supplier_id`, the buyer's
override) first, else the supplier the LAST PURCHASE actually named
(`inputs.last_purchase.supplier_id`, S11's own field), else the primary link (the
engine's frozen `rec.supplier_id`).

Postgres only, marker-prefixed, every test seeds its own chain - no `LIMIT 1` borrow off
the shared prod-copy database (CI's has none).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.scm import PlanRowDecision
from app.services.scm import plan_edits_service as pe_svc
from app.services.scm import reorder_run_service as svc
from tests._pg_fixture import pg_session
from tests.scm.conftest import requires_pg
from tests.scm.test_m3_run import (
    _link as m3_link,
    _mk_committed,
    _mk_demand,
    _mk_product as m3_mk_product,
    _mk_stock,
    _mk_supplier as m3_mk_supplier,
    _mk_warehouse as m3_mk_warehouse,
)
from tests.scm._revamp_fixtures import (
    category_and_uom,
    product,
    recommendation,
    run,
    supplier,
)

pytestmark = requires_pg

ACTOR = str(uuid.uuid4())


@pytest.fixture()
def db():
    with pg_session() as s:
        yield s


_NO_LINK = object()


def _product_supplier_moq(db, product_id, supplier_id):
    """The link's `moq`, or the `_NO_LINK` sentinel when no `product_suppliers` row for
    this (product, supplier) pair exists at all - distinct from a link whose `moq` is
    itself NULL."""
    row = db.execute(text(
        "SELECT moq FROM product_suppliers WHERE product_id = :p AND supplier_id = :s"
    ), {"p": product_id, "s": supplier_id}).mappings().first()
    return row["moq"] if row else _NO_LINK


def _assert_link_moq(db, product_id, supplier_id, expected):
    """A readable failure either way: no link at all, or a link with the wrong figure -
    rather than a bare `ValueError` out of `float(_NO_LINK)`."""
    got = _product_supplier_moq(db, product_id, supplier_id)
    assert got is not _NO_LINK, (
        f"expected a product_suppliers link (product={product_id}, supplier={supplier_id}) "
        f"with moq={expected}, but no such link exists at all"
    )
    assert float(got) == expected


def _assert_no_link(db, product_id, supplier_id):
    got = _product_supplier_moq(db, product_id, supplier_id)
    assert got is _NO_LINK, (
        f"expected NO product_suppliers link for (product={product_id}, "
        f"supplier={supplier_id}), but found one with moq={got}"
    )


def _product_supplier_link_count(db, product_id, supplier_id):
    return db.execute(text(
        "SELECT count(*) FROM product_suppliers WHERE product_id = :p AND supplier_id = :s"
    ), {"p": product_id, "s": supplier_id}).scalar()


# =============================================================================
# AC-S13.1/AC-S13.4 - plan-edits `moq` remembers onto the resolved supplier link
# =============================================================================

def test_remembers_moq_on_the_last_purchase_supplier_when_nothing_else_names_one(db):
    """No buyer supplier override on this row (no `plan_row_decision`), and the engine's
    OWN frozen supplier (`rec.supplier_id`) is a THIRD supplier - so the link written must
    be the LAST-PURCHASE one (`inputs.last_purchase.supplier_id`), not the engine's."""
    cat, uom = category_and_uom(db)
    prod = product(db, cat, uom)
    plan = run(db)
    engine_default_sup = supplier(db, "ZZTMOQR engine default")
    last_purchase_sup = supplier(db, "ZZTMOQR last purchase (KAIPING-like)")
    rec = recommendation(
        db, plan, prod, None, sup=engine_default_sup,
        inputs={
            "moq": None, "order_multiple": None,
            "last_purchase": {"supplier_id": str(last_purchase_sup.id)},
        },
    )
    _assert_no_link(db, prod.id, last_purchase_sup.id)

    out = pe_svc.save_plan_edits(db, plan.id, [{"rec_id": rec.id, "moq": 100}], actor=ACTOR)
    assert out["saved_rows"] == 1

    _assert_link_moq(db, prod.id, last_purchase_sup.id, 100.0)
    # Never the engine's own default link - that would silently correct the WRONG
    # supplier's terms.
    _assert_no_link(db, prod.id, engine_default_sup.id)

    db.refresh(rec)
    assert float(rec.moq_override) == 100.0


def test_a_second_save_updates_the_same_link_in_place(db):
    """Saving twice never creates a second `product_suppliers` row for the same pair."""
    cat, uom = category_and_uom(db)
    prod = product(db, cat, uom)
    plan = run(db)
    last_purchase_sup = supplier(db, "ZZTMOQR repeat save supplier")
    rec = recommendation(
        db, plan, prod, None, sup=None,
        inputs={"moq": None, "order_multiple": None,
                "last_purchase": {"supplier_id": str(last_purchase_sup.id)}},
    )

    pe_svc.save_plan_edits(db, plan.id, [{"rec_id": rec.id, "moq": 100}], actor=ACTOR)
    _assert_link_moq(db, prod.id, last_purchase_sup.id, 100.0)
    assert _product_supplier_link_count(db, prod.id, last_purchase_sup.id) == 1

    pe_svc.save_plan_edits(db, plan.id, [{"rec_id": rec.id, "moq": 120}], actor=ACTOR)
    _assert_link_moq(db, prod.id, last_purchase_sup.id, 120.0)
    assert _product_supplier_link_count(db, prod.id, last_purchase_sup.id) == 1, (
        "the second save must UPDATE the existing link, never insert a duplicate"
    )


def test_the_rows_own_chosen_supplier_wins_over_the_last_purchase_one(db):
    """A `plan_row_decision.supplier_id` (the buyer's own supplier pick on this row) is
    the FIRST tier - it wins even when the row's last purchase names someone else."""
    cat, uom = category_and_uom(db)
    prod = product(db, cat, uom)
    plan = run(db)
    chosen_sup = supplier(db, "ZZTMOQR chosen (buyer pick)")
    last_purchase_sup = supplier(db, "ZZTMOQR last purchase, overridden")
    rec = recommendation(
        db, plan, prod, None, sup=None,
        inputs={"moq": None, "order_multiple": None,
                "last_purchase": {"supplier_id": str(last_purchase_sup.id)}},
    )
    db.add(PlanRowDecision(
        id=str(uuid.uuid4()), recommendation_id=rec.id, kind="buy", buy_qty=10,
        supplier_id=chosen_sup.id,
    ))
    db.flush()

    pe_svc.save_plan_edits(db, plan.id, [{"rec_id": rec.id, "moq": 100}], actor=ACTOR)

    _assert_link_moq(db, prod.id, chosen_sup.id, 100.0)
    _assert_no_link(db, prod.id, last_purchase_sup.id)


def test_put_recommendations_moq_remembers_the_same_way(db):
    """`set_moq_override` is the ONE function both the bulk plan-edits row and the single
    `PUT /recommendations/{id}/moq` route call - proven directly here at the service
    layer (the route's own auth/shape is `test_moq_override.py`'s job)."""
    cat, uom = category_and_uom(db)
    prod = product(db, cat, uom)
    plan = run(db)
    primary_sup = supplier(db, "ZZTMOQR primary link fallback")
    # Neither a chosen supplier NOR a last purchase - falls all the way to the primary
    # link, which is the engine's own frozen `rec.supplier_id`.
    rec = recommendation(
        db, plan, prod, None, sup=primary_sup,
        inputs={"moq": None, "order_multiple": None},
    )

    result = svc.set_moq_override(db, rec.id, 80)

    assert result["moq"] == 80.0
    _assert_link_moq(db, prod.id, primary_sup.id, 80.0)


# =============================================================================
# AC-S13.3 - the NEXT run applies the remembered MoQ
# =============================================================================

def test_a_later_run_applies_the_remembered_moq(scm_app):
    """Full round trip through the real engine: remember MOQ 100 via `set_moq_override`
    on a product whose only supplier link started at a lower MOQ, then run the plan
    again and confirm the fresh recommendation both freezes `inputs.supplier.moq == 100`
    (`reorder_run_service._supplier_choice`) and rounds the buy qty to respect it -
    `reorder_engine.load_supplier_candidates` already reads `product_suppliers.moq`
    for whichever supplier `select_supplier` picks, so remembering the figure on that
    link is the whole fix; the engine itself needs no change."""
    _, db, _, _ = scm_app
    wid = m3_mk_warehouse(db, "MQR-W")
    pid = m3_mk_product(db, "MQR-P")
    sid = m3_mk_supplier(db, "MQR supplier")
    m3_link(db, pid, sid, lead=30, moq=20, mult=None, cost=60, primary=True)
    _mk_stock(db, pid, wid, 5)
    _mk_demand(db, pid, wid, 2.0)
    _mk_committed(db, pid, wid)
    db.flush()

    first = svc.create_run(db, ["MQR-W"], "warehouse", enqueue=False)
    svc.run_reorder(first["run_id"], db=db)
    first_rec = db.execute(text(
        "SELECT id FROM scm.reorder_recommendation "
        "WHERE run_id = :r AND product_id = :p AND rec_type = 'buy'"
    ), {"r": first["run_id"], "p": pid}).mappings().first()
    assert first_rec is not None, "the product must actually plan a buy on the first run"

    svc.set_moq_override(db, first_rec["id"], 100)
    _assert_link_moq(db, pid, sid, 100.0)

    second = svc.create_run(db, ["MQR-W"], "warehouse", enqueue=False)
    svc.run_reorder(second["run_id"], db=db)
    second_rec = db.execute(text(
        "SELECT inputs, rounded_qty FROM scm.reorder_recommendation "
        "WHERE run_id = :r AND product_id = :p AND rec_type = 'buy'"
    ), {"r": second["run_id"], "p": pid}).mappings().first()
    assert second_rec is not None, "the product must still plan a buy on the second run"

    inputs = second_rec["inputs"]
    assert inputs["moq"] == 100.0, "the top-level frozen master MoQ picks up the remembered figure"
    assert inputs["supplier"]["moq"] == 100.0, (
        "the row's own supplier block (what the panel reads) carries it too"
    )
    assert float(second_rec["rounded_qty"]) >= 100.0, (
        "the rounded buy qty must respect the remembered MoQ, not the old MoQ 20"
    )
