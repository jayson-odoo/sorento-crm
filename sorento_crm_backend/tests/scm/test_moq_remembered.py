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

from app.models.base import set_company_scope
from app.models.company import Company
from app.models.scm import PlanRowDecision
from app.services.scm import plan_edits_service as pe_svc
from app.services.scm import reorder_engine as eng
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


def _force_pool_netting_policy(db) -> None:
    """A global `reorder_point` + `pool_netting=true` policy, regardless of what a REAL
    row already says (the shared dev DB carries one from 2026-07-17 stamped
    `policy_type='reorder_level'`) or an empty CI table says (no row at all) - a row is
    guaranteed first (idempotent), then forced to the shape these pooled/network tests
    need, inside the test's own rolled-back transaction only."""
    eng.ensure_reorder_policy_defaults(db)
    db.execute(text(
        "UPDATE scm.reorder_policy SET policy_type = 'reorder_point', pool_netting = true "
        "WHERE scope_type = 'global'"
    ))


def _seed_category_uom_bait(db) -> None:
    """`test_m3_run.py`'s `m3_mk_product` borrows an existing product's category/uom via
    a bare `SELECT ... LIMIT 1` - never None on the shared dev DB (never empty), but None
    on CI's clean bootstrap DB (CLAUDE.md: never LIMIT 1 off an existing table; seed your
    own chain). Seeds one directly so the borrow always finds something, on either DB."""
    cat, uom = category_and_uom(db)
    product(db, cat, uom)


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


# =============================================================================
# Review fix round 2 (9 Sep): company scope, grouped fan-out, moq 0, supplier_code
# =============================================================================

def test_a_remembered_link_carries_the_products_own_company_id_never_the_db_default(db):
    """Finding 2: `product_suppliers.company_id` carries a DB DEFAULT (the legacy
    single-tenant company) - a link created for any OTHER company must not silently
    inherit it. A second company proves the write reads `products.company_id` rather
    than falling through to that default."""
    set_company_scope(db, None)
    company_b = Company(
        id=str(uuid.uuid4()), code=f"ZZTMOQR-CB-{uuid.uuid4().hex[:8]}",
        name="ZZTMOQR company B",
    )
    db.add(company_b)
    db.flush()
    set_company_scope(db, frozenset({str(company_b.id)}))

    cat, uom = category_and_uom(db)
    prod = product(db, cat, uom)
    plan = run(db)
    last_purchase_sup = supplier(db, "ZZTMOQR company-scoped supplier")
    rec = recommendation(
        db, plan, prod, None, sup=None,
        inputs={"moq": None, "order_multiple": None,
                "last_purchase": {"supplier_id": str(last_purchase_sup.id)}},
    )

    pe_svc.save_plan_edits(db, plan.id, [{"rec_id": rec.id, "moq": 100}], actor=ACTOR)

    row = db.execute(text(
        "SELECT company_id FROM product_suppliers WHERE product_id = :p AND supplier_id = :s"
    ), {"p": prod.id, "s": last_purchase_sup.id}).mappings().first()
    assert row is not None
    assert str(row["company_id"]) == str(company_b.id)


def test_remember_moq_upserts_even_when_the_existing_link_is_stamped_to_another_company(db):
    """Finding 2: the upsert keys purely on the (product, supplier) pair - a pre-existing
    link stamped to a DIFFERENT company must not 500 the save, and must end with ITS OWN
    moq updated (never a duplicate row for the same pair, and never silently re-stamped
    to whichever company happened to save last)."""
    set_company_scope(db, None)
    other_company = Company(
        id=str(uuid.uuid4()), code=f"ZZTMOQR-OC-{uuid.uuid4().hex[:8]}",
        name="ZZTMOQR other company",
    )
    db.add(other_company)
    db.flush()

    cat, uom = category_and_uom(db)
    prod = product(db, cat, uom)
    plan = run(db)
    sup = supplier(db, "ZZTMOQR cross-company link")
    # A pre-existing link, stamped by hand to the OTHER company - `product_suppliers`
    # carries no FK-level enforcement against the session's own scope, so this is a
    # legitimate (if stale) row a real tenant migration could easily leave behind.
    link_id = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO product_suppliers "
        "(id, product_id, supplier_id, standard_lead_time_days, moq, "
        " is_primary_supplier, company_id, created_at) "
        "VALUES (:id, :p, :s, 30, 5, false, :co, now())"
    ), {"id": link_id, "p": prod.id, "s": sup.id, "co": str(other_company.id)})

    rec = recommendation(
        db, plan, prod, None, sup=None,
        inputs={"moq": None, "order_multiple": None,
                "last_purchase": {"supplier_id": str(sup.id)}},
    )

    out = pe_svc.save_plan_edits(db, plan.id, [{"rec_id": rec.id, "moq": 120}], actor=ACTOR)
    assert out["saved_rows"] == 1, "the save must not 500 on a cross-company existing link"
    _assert_link_moq(db, prod.id, sup.id, 120.0)
    assert _product_supplier_link_count(db, prod.id, sup.id) == 1
    row = db.execute(text(
        "SELECT id, company_id FROM product_suppliers WHERE product_id = :p AND supplier_id = :s"
    ), {"p": prod.id, "s": sup.id}).mappings().first()
    assert str(row["id"]) == link_id, "the SAME row was updated, not a new one inserted"
    assert str(row["company_id"]) == str(other_company.id), "company_id is untouched on UPDATE"

    # Two saves in a row still hold ONE row.
    pe_svc.save_plan_edits(db, plan.id, [{"rec_id": rec.id, "moq": 130}], actor=ACTOR)
    _assert_link_moq(db, prod.id, sup.id, 130.0)
    assert _product_supplier_link_count(db, prod.id, sup.id) == 1


def test_a_grouped_products_two_members_resolve_one_link_on_the_most_recent_purchase(db):
    """AC-S13.1, finding 3: a product-grain row's MoQ edit fans out to every member
    recommendation - two locations of ONE product bought from two DIFFERENT suppliers
    historically - and only ONE product_suppliers link must be written, on whichever
    purchase is more recent, never one link per member overwriting the last."""
    cat, uom = category_and_uom(db)
    prod = product(db, cat, uom)
    plan = run(db)
    older_sup = supplier(db, "ZZTMOQR older last purchase")
    newer_sup = supplier(db, "ZZTMOQR newer last purchase")
    rec_a = recommendation(
        db, plan, prod, None, sup=None,
        inputs={"moq": None, "order_multiple": None,
                "last_purchase": {"supplier_id": str(older_sup.id), "at": "2025-01-01"}},
    )
    rec_b = recommendation(
        db, plan, prod, None, sup=None,
        inputs={"moq": None, "order_multiple": None,
                "last_purchase": {"supplier_id": str(newer_sup.id), "at": "2026-06-01"}},
    )

    out = pe_svc.save_plan_edits(
        db, plan.id,
        [{"rec_id": rec_a.id, "moq": 150}, {"rec_id": rec_b.id, "moq": 150}],
        actor=ACTOR,
    )
    assert out["saved_rows"] == 2

    _assert_link_moq(db, prod.id, newer_sup.id, 150.0)
    _assert_no_link(db, prod.id, older_sup.id)
    assert _product_supplier_link_count(db, prod.id, newer_sup.id) == 1


def test_moq_zero_clears_only_the_rows_own_override_the_link_survives_bulk_path(db):
    """Finding 5 + review fix round 3 ruling (finding 3): 0 means "no MoQ" for the ROW,
    not a literal figure to remember - but it never touches the remembered link. A buyer
    who clears a row and later types a fresh number must not find the link already
    disagrees with it."""
    cat, uom = category_and_uom(db)
    prod = product(db, cat, uom)
    plan = run(db)
    sup = supplier(db, "ZZTMOQR clear via bulk")
    rec = recommendation(
        db, plan, prod, None, sup=None,
        inputs={"moq": None, "order_multiple": None,
                "last_purchase": {"supplier_id": str(sup.id)}},
    )
    pe_svc.save_plan_edits(db, plan.id, [{"rec_id": rec.id, "moq": 100}], actor=ACTOR)
    _assert_link_moq(db, prod.id, sup.id, 100.0)

    pe_svc.save_plan_edits(db, plan.id, [{"rec_id": rec.id, "moq": 0}], actor=ACTOR)

    db.refresh(rec)
    assert rec.moq_override is None, "0 clears the row's own override, not a literal 0"
    _assert_link_moq(db, prod.id, sup.id, 100.0)


def test_moq_zero_never_creates_a_link_where_none_existed_single_route(db):
    """Finding 5, the single `PUT /recommendations/{id}/moq` route: a clear on a row
    with nothing remembered yet leaves the (product, supplier) pair with NO link at
    all, never a link freshly created just to hold a NULL."""
    cat, uom = category_and_uom(db)
    prod = product(db, cat, uom)
    plan = run(db)
    sup = supplier(db, "ZZTMOQR clear with nothing to clear")
    rec = recommendation(
        db, plan, prod, None, sup=sup,
        inputs={"moq": None, "order_multiple": None},
    )
    _assert_no_link(db, prod.id, sup.id)

    result = svc.set_moq_override(db, rec.id, 0)

    assert result["moq"] is None
    assert result["moq_is_override"] is False
    _assert_no_link(db, prod.id, sup.id)


def test_a_full_run_freezes_the_last_purchase_supplier_code(db):
    """Finding 6: the panel's supplier prefill reads a human CODE
    (`last_purchase_supplier_code`), never the raw id - a live run has to freeze that
    code onto `inputs.last_purchase`, not only the id `test_purchase_history_to_pool.py`
    already pins at the `_last_purchase_cost_map` level."""
    from datetime import date, datetime

    from app.models.procurement import PurchaseOrder, PurchaseOrderLine

    _seed_category_uom_bait(db)
    wid = m3_mk_warehouse(db, "LPC-W")
    pid = m3_mk_product(db, "LPC-P")
    sid = m3_mk_supplier(db, "LPC supplier")
    m3_link(db, pid, sid, lead=30, moq=None, mult=None, cost=60, primary=True)
    _mk_stock(db, pid, wid, 5)
    _mk_demand(db, pid, wid, 2.0)
    _mk_committed(db, pid, wid)

    po = PurchaseOrder(
        id=str(uuid.uuid4()), po_number=f"ZZTMOQR-LPC-{uuid.uuid4().hex[:8]}",
        supplier_id=sid, status="active", issue_date=date(2026, 5, 20),
        currency="MYR", created_at=datetime.utcnow(),
    )
    db.add(po)
    db.flush()
    db.add(PurchaseOrderLine(
        # `line_status="closed"` (fully received) - a HISTORICAL purchase for the price
        # freeze to read, not an open PO line, which `scm.po_ordered_v` would otherwise
        # count as incoming stock and net the shortage away entirely (rec_type
        # 'covered', not 'buy').
        id=str(uuid.uuid4()), purchase_order_id=po.id, product_id=pid,
        warehouse_id=wid, qty_ordered=10, qty_received=10, unit_cost=44.0,
        currency="MYR", line_status="closed",
    ))
    db.flush()

    result = svc.create_run(db, ["LPC-W"], "warehouse", enqueue=False)
    svc.run_reorder(result["run_id"], db=db)
    rec = db.execute(text(
        "SELECT inputs FROM scm.reorder_recommendation "
        "WHERE run_id = :r AND product_id = :p AND rec_type = 'buy'"
    ), {"r": result["run_id"], "p": pid}).mappings().first()
    assert rec is not None, "the product must plan a buy"
    lp = (rec["inputs"] or {}).get("last_purchase") or {}
    assert lp.get("supplier_code"), "the frozen last_purchase must carry a human code"


# =============================================================================
# G7 / AC-S13.6 (review fix round 2, 9 Sep) - the engine PLANS against the last
# purchase supplier, not merely remembers its MOQ for next time
# =============================================================================

def test_ac_s13_6_last_purchase_supplier_wins_price_moq_and_rounding(db):
    """Browser round 4 measured SRTSS8710 planning against its stale DEFAULT link (MYR
    121.80) while the row's own last purchase, and the just-saved MOQ 100, both named a
    DIFFERENT supplier - so the plan priced in the wrong currency and rounded to the
    wrong MOQ. A product with a PRIMARY link (A, MYR 121.80, no MOQ) and a recent last
    purchase from B (CNY 48, whose OWN link already remembers MOQ 100) must plan
    against B outright: price, currency, MOQ and the rounded buy qty all follow it."""
    from datetime import date, datetime

    from app.models.procurement import PurchaseOrder, PurchaseOrderLine

    _seed_category_uom_bait(db)
    wid = m3_mk_warehouse(db, "S136-W")
    pid = m3_mk_product(db, "S136-P")
    sup_a = m3_mk_supplier(db, "S136 primary A")
    sup_b = m3_mk_supplier(db, "S136 last purchase B")
    m3_link(db, pid, sup_a, lead=30, moq=None, mult=None, cost=121.80, primary=True)
    m3_link(db, pid, sup_b, lead=30, moq=100, mult=None, cost=None, primary=False)

    po = PurchaseOrder(
        id=str(uuid.uuid4()), po_number=f"ZZTS136-{uuid.uuid4().hex[:8]}",
        supplier_id=sup_b, status="closed", issue_date=date(2026, 6, 1),
        currency="CNY", created_at=datetime.utcnow(),
    )
    db.add(po)
    db.flush()
    db.add(PurchaseOrderLine(
        id=str(uuid.uuid4()), purchase_order_id=po.id, product_id=pid,
        warehouse_id=wid, qty_ordered=10, qty_received=10, unit_cost=48.0,
        currency="CNY", line_status="closed",
    ))
    db.flush()

    _mk_stock(db, pid, wid, 5)
    _mk_demand(db, pid, wid, 0.2)
    _mk_committed(db, pid, wid)

    result = svc.create_run(db, ["S136-W"], "warehouse", enqueue=False)
    svc.run_reorder(result["run_id"], db=db)
    rec = db.execute(text(
        "SELECT inputs, currency, unit_cost, rounded_qty, supplier_id "
        "FROM scm.reorder_recommendation "
        "WHERE run_id = :r AND product_id = :p AND rec_type = 'buy'"
    ), {"r": result["run_id"], "p": pid}).mappings().first()
    assert rec is not None, "the product must plan a buy"
    assert str(rec["supplier_id"]) == str(sup_b), "the frozen row must name B, not A"
    assert rec["currency"] == "CNY"
    assert float(rec["unit_cost"]) == 48.0
    # MOQ is a FLOOR, not a multiple to round up to (`reorder_engine.round_order_qty`,
    # review fix round 3, finding 1) - a need already above 100 would trivially satisfy
    # "respects the MOQ" without the floor doing anything; this fixture's true need is
    # BELOW 100, so landing on exactly 100 proves the floor actually fired.
    assert float(rec["rounded_qty"]) == 100.0, "the floor lifted the small raw need up to the MOQ"

    inputs = rec["inputs"] or {}
    assert inputs.get("selection") == "last_purchase"
    assert inputs["supplier"]["supplier_name"] == "S136 last purchase B"
    assert inputs["moq"] == 100.0


def test_ac_s13_6_no_last_purchase_falls_back_to_the_primary_link(db):
    """The other half of AC-S13.6: a product with no purchase history at all plans
    against the primary link exactly as before - the preference above only overrides
    when there IS a last purchase on file to prefer."""
    _seed_category_uom_bait(db)
    wid = m3_mk_warehouse(db, "S136B-W")
    pid = m3_mk_product(db, "S136B-P")
    sup_a = m3_mk_supplier(db, "S136B primary A")
    m3_link(db, pid, sup_a, lead=30, moq=None, mult=None, cost=121.80, primary=True)

    _mk_stock(db, pid, wid, 5)
    _mk_demand(db, pid, wid, 20.0)
    _mk_committed(db, pid, wid)

    result = svc.create_run(db, ["S136B-W"], "warehouse", enqueue=False)
    svc.run_reorder(result["run_id"], db=db)
    rec = db.execute(text(
        "SELECT inputs, supplier_id FROM scm.reorder_recommendation "
        "WHERE run_id = :r AND product_id = :p AND rec_type = 'buy'"
    ), {"r": result["run_id"], "p": pid}).mappings().first()
    assert rec is not None
    assert str(rec["supplier_id"]) == str(sup_a)
    assert (rec["inputs"] or {}).get("selection") != "last_purchase"



def test_ac_s13_6_wins_on_a_two_warehouse_pooled_run(db):
    """G7 / AC-S13.6, review fix round 3 finding 1: the SAME preference, on a pooled
    run - two warehouses in one site pool, per-warehouse grain, `_emit_pool`'s own
    supplier pick. Primary A at MYR 121.80 loses to the last-purchase supplier B (CNY
    48, whose OWN link already remembers MOQ 100)."""
    from datetime import date, datetime

    from app.models.procurement import PurchaseOrder, PurchaseOrderLine

    _seed_category_uom_bait(db)
    _force_pool_netting_policy(db)
    anchor = m3_mk_warehouse(db, "S136PW-A")
    member = m3_mk_warehouse(db, "S136PW-B", pool_warehouse_id=anchor)
    pid = m3_mk_product(db, "S136PW-P")
    sup_a = m3_mk_supplier(db, "S136PW primary A")
    sup_b = m3_mk_supplier(db, "S136PW last purchase B")
    m3_link(db, pid, sup_a, lead=30, moq=None, mult=None, cost=121.80, primary=True)
    m3_link(db, pid, sup_b, lead=30, moq=100, mult=None, cost=None, primary=False)

    po = PurchaseOrder(
        id=str(uuid.uuid4()), po_number=f"ZZTS136PW-{uuid.uuid4().hex[:8]}",
        supplier_id=sup_b, status="closed", issue_date=date(2026, 6, 1),
        currency="CNY", created_at=datetime.utcnow(),
    )
    db.add(po)
    db.flush()
    db.add(PurchaseOrderLine(
        id=str(uuid.uuid4()), purchase_order_id=po.id, product_id=pid,
        warehouse_id=anchor, qty_ordered=10, qty_received=10, unit_cost=48.0,
        currency="CNY", line_status="closed",
    ))
    db.flush()

    _mk_stock(db, pid, anchor, 5)
    _mk_demand(db, pid, anchor, 0.2)
    _mk_committed(db, pid, anchor)
    # B contributes NO demand/stock of its own - a genuine second pool member with
    # nothing to add, so the pool's total need matches the single-location case this
    # scenario otherwise mirrors (AC-S13.6's own primary test), and `round_order_qty`'s
    # floor-at-MOQ actually has something to floor: MOQ is a MINIMUM, not a multiple to
    # round up to (`reorder_engine.round_order_qty`), so a demand already well above 100
    # would trivially satisfy "respects the MOQ" without proving anything.

    result = svc.create_run(db, ["S136PW-A", "S136PW-B"], "warehouse", enqueue=False)
    svc.run_reorder(result["run_id"], db=db)
    recs = db.execute(text(
        "SELECT inputs, currency, unit_cost, rounded_qty, supplier_id, warehouse_id "
        "FROM scm.reorder_recommendation "
        "WHERE run_id = :r AND product_id = :p AND rec_type = 'buy'"
    ), {"r": result["run_id"], "p": pid}).mappings().all()
    # ONE buy for the pool, emitted against the pool's own anchor location (`_emit_pool`
    # never emits a second row for a member the split gave nothing to - AC-R8).
    assert len(recs) == 1, "the pool must plan exactly one buy, not one per member"
    rec = recs[0]
    assert str(rec["warehouse_id"]) == anchor
    assert str(rec["supplier_id"]) == str(sup_b)
    assert rec["currency"] == "CNY"
    assert float(rec["unit_cost"]) == 48.0
    # MOQ is a FLOOR, not a multiple to round up to (`reorder_engine.round_order_qty`,
    # review fix round 3, finding 1) - a need already above 100 would trivially satisfy
    # "respects the MOQ" without the floor doing anything; this fixture's true need is
    # BELOW 100, so landing on exactly 100 proves the floor actually fired.
    assert float(rec["rounded_qty"]) == 100.0
    inputs = rec["inputs"] or {}
    assert inputs.get("selection") == "last_purchase"
    assert inputs["moq"] == 100.0


def test_ac_s13_6_wins_on_a_network_scope_run(db):
    """G7 / AC-S13.6, review fix round 3 finding 1: the SAME preference, on a
    NETWORK-scope run - the aggregate buy names no single location, `_plan_network`'s
    own supplier pick. Primary A at MYR 121.80 loses to the last-purchase supplier B
    (CNY 48, whose OWN link already remembers MOQ 100)."""
    from datetime import date, datetime

    from app.models.procurement import PurchaseOrder, PurchaseOrderLine

    _seed_category_uom_bait(db)
    wid = m3_mk_warehouse(db, "S136NW-W")
    pid = m3_mk_product(db, "S136NW-P")
    sup_a = m3_mk_supplier(db, "S136NW primary A")
    sup_b = m3_mk_supplier(db, "S136NW last purchase B")
    m3_link(db, pid, sup_a, lead=30, moq=None, mult=None, cost=121.80, primary=True)
    m3_link(db, pid, sup_b, lead=30, moq=100, mult=None, cost=None, primary=False)

    po = PurchaseOrder(
        id=str(uuid.uuid4()), po_number=f"ZZTS136NW-{uuid.uuid4().hex[:8]}",
        supplier_id=sup_b, status="closed", issue_date=date(2026, 6, 1),
        currency="CNY", created_at=datetime.utcnow(),
    )
    db.add(po)
    db.flush()
    db.add(PurchaseOrderLine(
        id=str(uuid.uuid4()), purchase_order_id=po.id, product_id=pid,
        warehouse_id=wid, qty_ordered=10, qty_received=10, unit_cost=48.0,
        currency="CNY", line_status="closed",
    ))
    db.flush()

    _mk_stock(db, pid, wid, 5)
    _mk_demand(db, pid, wid, 0.2)
    _mk_committed(db, pid, wid)

    result = svc.create_run(db, ["S136NW-W"], "network", enqueue=False)
    svc.run_reorder(result["run_id"], db=db)
    rec = db.execute(text(
        "SELECT inputs, currency, unit_cost, rounded_qty, supplier_id "
        "FROM scm.reorder_recommendation "
        "WHERE run_id = :r AND product_id = :p AND rec_type = 'buy'"
    ), {"r": result["run_id"], "p": pid}).mappings().first()
    assert rec is not None, "the network row must plan a buy"
    assert str(rec["supplier_id"]) == str(sup_b)
    assert rec["currency"] == "CNY"
    assert float(rec["unit_cost"]) == 48.0
    # MOQ is a FLOOR, not a multiple to round up to (`reorder_engine.round_order_qty`,
    # review fix round 3, finding 1) - a need already above 100 would trivially satisfy
    # "respects the MOQ" without the floor doing anything; this fixture's true need is
    # BELOW 100, so landing on exactly 100 proves the floor actually fired.
    assert float(rec["rounded_qty"]) == 100.0
    inputs = rec["inputs"] or {}
    assert inputs.get("selection") == "last_purchase"
    assert inputs["moq"] == 100.0

