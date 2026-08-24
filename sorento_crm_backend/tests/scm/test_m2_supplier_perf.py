"""SCM M2 - supplier performance (AC-M2.8/2.9/2.10/2.11).

Supplier metrics run off PO -> GR pairs. To keep the golden numbers deterministic and
independent of whatever demo seed is (or isn't) loaded, each test builds a small
synthetic PO/GR fixture inside the rolled-back savepoint and hand-computes the expected
scorecard. Fixture (issue d0, expected d0+10, grace 2, weights 0.5/0.5, min_sample 3):

  Supplier S1:
    P1: 3 completed lines -> lead 10/13/11, on_time y/n/y, rej 0/10/0, all qty 100.
        direct (sample 3) -> on_time 2/3, avg_lead 11.333, var 1.5556, reject 10/300,
        fill 1.0, composite 0.81667, confidence high.
    P2: 1 line ordered 200 received via 2 GRs (120 @ d0+8 partial, 80 @ d0+15 COMPLETING)
        -> lead 15 (completing receipt), late; sample 1 < 3 -> fall back to S1 aggregate
        (confidence medium).
    S1 aggregate (4 samples): on_time 2/4=0.5, avg_lead 12.25, var 3.6875, reject 10/500=0.02,
        fill 1.0, composite 0.74 -> denormalised to suppliers.current_performance_score.
  Supplier S2:
    P3: 1 line, lead 20 late; sample 1 and supplier total 1 < 3 -> confidence low.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.services.scm import analytics_service as svc
from tests.scm.conftest import requires_pg

pytestmark = requires_pg

D0 = date(2026, 1, 10)
AS_OF = date(2026, 3, 1)


def _mk_supplier(db, name):
    sid = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO suppliers (id, supplier_code, supplier_name, is_active, created_at, updated_at) "
        "VALUES (:id, :code, :name, true, now(), now())"
    ), {"id": sid, "code": f"M2T-{sid[:8]}", "name": name})
    return sid


def _products(db, n):
    return [r[0] for r in db.execute(text("SELECT id FROM products LIMIT :n"), {"n": n}).fetchall()]


def _warehouse(db):
    return db.execute(text("SELECT id FROM warehouses LIMIT 1")).scalar()


def _mk_po_line(db, supplier_id, product_id, wid, ordered, issue, expected, status="received"):
    po_id, pol_id = str(uuid.uuid4()), str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO purchase_orders (id, po_number, supplier_id, issue_date, expected_date, "
        "status, currency, source_system, source_ref, created_at, updated_at) "
        "VALUES (:id, :num, :sid, :iss, :exp, :st, 'MYR', 'm2test', 't', now(), now())"
    ), {"id": po_id, "num": f"POT-{po_id[:8]}", "sid": supplier_id, "iss": issue,
        "exp": expected, "st": status})
    db.execute(text(
        "INSERT INTO purchase_order_lines (id, purchase_order_id, product_id, warehouse_id, "
        "qty_ordered, qty_received, unit_cost, currency, expected_date, line_status, "
        "source_system, source_ref, created_at, updated_at) "
        "VALUES (:id, :po, :prod, :wid, :qo, :qo, 10, 'MYR', :exp, 'received', 'm2test', 't', now(), now())"
    ), {"id": pol_id, "po": po_id, "prod": product_id, "wid": wid, "qo": ordered, "exp": expected})
    return pol_id


def _mk_gr(db, pol_id, product_id, wid, picking_date, picked, accepted, rejected):
    gh_id, gl_id = str(uuid.uuid4()), str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO picking_headers (id, picking_number, picking_type, source_entity_type, "
        "picking_date, inspection_status, picking_status, created_at, updated_at) "
        "VALUES (:id, :num, 'goods_received', 'purchase_order', :pd, 'passed', 'posted', now(), now())"
    ), {"id": gh_id, "num": f"GRT-{gh_id[:8]}", "pd": picking_date})
    db.execute(text(
        "INSERT INTO picking_lines (id, picking_header_id, po_line_id, product_id, "
        "quantity_expected, quantity_picked, qty_accepted, qty_rejected, unit_cost, "
        "destination_warehouse_id, created_at, updated_at) "
        "VALUES (:id, :gh, :pol, :prod, :qp, :qp, :acc, :rej, 10, :wid, now(), now())"
    ), {"id": gl_id, "gh": gh_id, "pol": pol_id, "prod": product_id, "qp": picked,
        "acc": accepted, "rej": rejected, "wid": wid})


def _set_scoring_policy(db, dw=0.5, qw=0.5, grace=2, min_sample=3):
    """Pin the supplier scoring policy to the locked golden config (the ambient seed
    row may carry different weights) so the blessed numbers are deterministic."""
    db.execute(text("UPDATE scm.supplier_scoring_policy SET is_active = false"))
    db.execute(text(
        "INSERT INTO scm.supplier_scoring_policy (id, delivery_weight, quality_weight, "
        "grace_days, min_sample_size, is_active, source_system, source_ref, created_at, updated_at) "
        "VALUES (:id, :dw, :qw, :g, :m, true, 'test', 'pin', now(), now())"
    ), {"id": str(uuid.uuid4()), "dw": dw, "qw": qw, "g": grace, "m": min_sample})
    db.flush()


def _build_fixture(db):
    wid = _warehouse(db)
    p1, p2, p3 = _products(db, 3)
    s1, s2 = _mk_supplier(db, "M2 Supplier One"), _mk_supplier(db, "M2 Supplier Two")
    exp = D0 + timedelta(days=10)

    # S1 x P1 - three completed single-GR lines
    for lead, rej in ((10, 0), (13, 10), (11, 0)):
        pol = _mk_po_line(db, s1, p1, wid, 100, D0, exp)
        _mk_gr(db, pol, p1, wid, D0 + timedelta(days=lead), 100, 100 - rej, rej)

    # S1 x P2 - one line received over two GRs; completing GR at d0+15
    pol2 = _mk_po_line(db, s1, p2, wid, 200, D0, exp)
    _mk_gr(db, pol2, p2, wid, D0 + timedelta(days=8), 120, 120, 0)   # partial
    _mk_gr(db, pol2, p2, wid, D0 + timedelta(days=15), 80, 80, 0)    # completing

    # S2 x P3 - single thin line
    pol3 = _mk_po_line(db, s2, p3, wid, 50, D0, exp)
    _mk_gr(db, pol3, p3, wid, D0 + timedelta(days=20), 50, 50, 0)
    db.flush()
    return {"s1": s1, "s2": s2, "p1": p1, "p2": p2, "p3": p3}


def _row(db, supplier_id, product_id):
    clause = "product_id = :p" if product_id else "product_id IS NULL"
    params = {"s": supplier_id}
    if product_id:
        params["p"] = product_id
    return db.execute(text(
        f"SELECT on_time_rate, avg_lead_time_days, lead_time_variance, reject_rate, fill_rate, "
        f"composite_score, sample_size, confidence FROM scm.supplier_performance "
        f"WHERE supplier_id = :s AND {clause}"
    ), params).fetchone()


def test_supplier_product_direct_metrics(scm_app):
    """AC-M2.8: sample>=min -> direct product-level scorecard = hand-computed golden."""
    _, db, _, _ = scm_app
    f = _build_fixture(db)
    _set_scoring_policy(db)
    svc.run_analytics(db, scope={"supplier_ids": [f["s1"], f["s2"]]}, config={"as_of": AS_OF})
    r = _row(db, f["s1"], f["p1"])
    assert r is not None
    assert float(r.on_time_rate) == pytest.approx(2 / 3, abs=1e-4)
    assert float(r.avg_lead_time_days) == pytest.approx(11.333333, abs=1e-4)
    assert float(r.lead_time_variance) == pytest.approx(1.555556, abs=1e-4)
    assert float(r.reject_rate) == pytest.approx(10 / 300, abs=1e-4)
    assert float(r.fill_rate) == pytest.approx(1.0, abs=1e-4)
    assert float(r.composite_score) == pytest.approx(0.816667, abs=1e-4)
    assert r.sample_size == 3
    assert r.confidence == "high"


def test_completing_receipt_used_for_lead_time(scm_app):
    """AC-M2.9: multi-GR line -> lead time uses the COMPLETING receipt (d0+15), not d0+8."""
    _, db, _, _ = scm_app
    f = _build_fixture(db)
    svc.run_analytics(db, scope={"supplier_ids": [f["s1"]]}, config={"as_of": AS_OF})
    # supplier-level aggregate includes the P2 completing sample (lead 15)
    agg = _row(db, f["s1"], None)
    assert float(agg.avg_lead_time_days) == pytest.approx(12.25, abs=1e-4)  # mean(10,13,11,15)
    assert float(agg.lead_time_variance) == pytest.approx(3.6875, abs=1e-4)
    assert agg.sample_size == 4


def test_min_sample_fallback_to_supplier_level(scm_app):
    """AC-M2.10: thin supplier x product falls back to supplier-level; below fallback
    -> confidence low, never fabricated."""
    _, db, _, _ = scm_app
    f = _build_fixture(db)
    _set_scoring_policy(db)
    svc.run_analytics(db, scope={"supplier_ids": [f["s1"], f["s2"]]}, config={"as_of": AS_OF})

    # S1 x P2 (sample 1) falls back to S1 aggregate metrics, confidence medium
    p2 = _row(db, f["s1"], f["p2"])
    assert p2.sample_size == 1
    assert p2.confidence == "medium"
    assert float(p2.on_time_rate) == pytest.approx(0.5, abs=1e-4)      # S1 aggregate
    assert float(p2.composite_score) == pytest.approx(0.74, abs=1e-4)

    # S2 x P3 (sample 1, supplier also thin) -> confidence low
    p3 = _row(db, f["s2"], f["p3"])
    assert p3.sample_size == 1
    assert p3.confidence == "low"


def test_supplier_composite_denormalised(scm_app):
    _, db, _, _ = scm_app
    f = _build_fixture(db)
    _set_scoring_policy(db)
    svc.run_analytics(db, scope={"supplier_ids": [f["s1"], f["s2"]]}, config={"as_of": AS_OF})
    s1_score = db.execute(text(
        "SELECT current_performance_score FROM suppliers WHERE id = :id"
    ), {"id": f["s1"]}).scalar()
    assert float(s1_score) == pytest.approx(0.74, abs=1e-4)


def test_grace_and_weights_are_configurable(scm_app):
    """AC-M2.8: changing grace_days / weights changes output with no code change."""
    _, db, _, _ = scm_app
    f = _build_fixture(db)
    # tighten grace to 0 (P1's d0+11 line now late) and shift all weight onto delivery
    db.execute(text("UPDATE scm.supplier_scoring_policy SET is_active = false"))
    db.execute(text(
        "INSERT INTO scm.supplier_scoring_policy (id, delivery_weight, quality_weight, "
        "grace_days, min_sample_size, is_active, source_system, source_ref, created_at, updated_at) "
        "VALUES (:id, 1.0, 0.0, 0, 3, true, 'test', 'cfg', now(), now())"
    ), {"id": str(uuid.uuid4())})
    db.flush()
    svc.run_analytics(db, scope={"supplier_ids": [f["s1"]]}, config={"as_of": AS_OF})
    r = _row(db, f["s1"], f["p1"])
    # grace 0 -> only the d0+10 line on-time -> 1/3; composite = 1.0*on_time + 0*quality
    assert float(r.on_time_rate) == pytest.approx(1 / 3, abs=1e-4)
    assert float(r.composite_score) == pytest.approx(1 / 3, abs=1e-4)


def test_null_issue_date_group_does_not_crash(scm_app):
    """B2: a supplier group whose completing receipts ALL have a null PO issue_date must
    still compute (period_start / lead null) without raising ValueError from min()/max()
    on an empty date sequence - a null issue_date row can never fail the whole run."""
    _, db, _, _ = scm_app
    wid = _warehouse(db)
    (p1,) = _products(db, 1)
    s = _mk_supplier(db, "M2 Null-IssueDate Supplier")
    exp = D0 + timedelta(days=10)
    # PO line with a NULL issue_date, fully received in one GR (a completing receipt)
    pol = _mk_po_line(db, s, p1, wid, 100, None, exp)
    _mk_gr(db, pol, p1, wid, D0 + timedelta(days=9), 100, 100, 0)
    db.flush()

    # must not raise, and the run completes
    res = svc.run_analytics(
        db, scope={"supplier_ids": [s], "product_ids": [p1]}, config={"as_of": AS_OF})
    assert res["status"] == "completed"

    row = db.execute(text(
        "SELECT period_start, avg_lead_time_days, on_time_rate FROM scm.supplier_performance "
        "WHERE supplier_id = :s AND product_id = :p"
    ), {"s": s, "p": p1}).fetchone()
    assert row is not None
    assert row.period_start is None        # no issue date to bound the period
    assert row.avg_lead_time_days is None  # lead measured off a null issue_date is null
    # on-time still resolves off expected_date vs the receipt (independent of issue_date)
    assert float(row.on_time_rate) == pytest.approx(1.0, abs=1e-4)


def test_on_gr_hook_scoped_to_one_pair(scm_app):
    """AC-M2.11: the on-GR refresh recomputes only the given supplier x product,
    not the whole catalog."""
    _, db, _, _ = scm_app
    f = _build_fixture(db)
    # nothing computed yet for S2
    assert _row(db, f["s2"], f["p3"]) is None
    written = svc.refresh_supplier_performance(db, f["s2"], f["p3"], config={"as_of": AS_OF})
    assert written >= 1
    assert _row(db, f["s2"], f["p3"]) is not None
    # S1 was NOT touched by the scoped refresh
    assert _row(db, f["s1"], f["p1"]) is None
