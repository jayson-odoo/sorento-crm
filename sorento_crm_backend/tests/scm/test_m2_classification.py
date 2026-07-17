"""SCM M2 — ABC/XYZ classification (AC-M2.5/2.6/2.7).

ABC classes are blessed in ``fixtures/golden_m2.json`` (ranked over the full costed
universe by trailing-12mo value); XYZ derives from the same demand CV as the demand
golden. Config cut points drive the maths — changing them reclassifies with no code
change. Null-cost keys classify as unknown (NULL). Savepoint-rolled-back.
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.services.scm import analytics_service as svc
from tests.scm.conftest import requires_pg

pytestmark = requires_pg

_GOLDEN = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "golden_m2.json")))
_AS_OF = date.fromisoformat(_GOLDEN["as_of"])


# ---------------------------------------------------------------------------
# ABC ranking — pure maths (B1: boundary-crossing item to higher class; rank-1 = A)
# ---------------------------------------------------------------------------

def test_abc_classify_dominant_single_sku_is_A():
    """B1: a rank-1 SKU that ALONE exceeds the 80% A cut is still A — the class is
    decided on the cumulative share BEFORE the item is added (prev_cum=0 for rank-1)."""
    # one SKU = 85% of annual value, two small tails
    assert svc.abc_classify([85.0, 10.0, 5.0], 80, 95) == ["A", "B", "B"]
    # a single SKU = 100% of the universe → A (prev_cum 0), not B/C
    assert svc.abc_classify([100.0], 80, 95) == ["A"]
    # and the degenerate empty / all-zero cases don't blow up
    assert svc.abc_classify([], 80, 95) == []
    assert svc.abc_classify([0.0, 0.0], 80, 95) == ["A", "A"]


def test_abc_classify_boundary_item_goes_to_higher_class():
    """The item that straddles a cut belongs to the HIGHER class, and mid-list B/C
    boundaries still land where cumulative-before-add crosses the cut."""
    # cum-before-add: 0, 50, 80, 95 → A, A, A(<=80), B(<=95)
    assert svc.abc_classify([50.0, 30.0, 15.0, 5.0], 80, 95) == ["A", "A", "A", "B"]
    # a long even tail eventually crosses into B then C
    vals = [40.0, 40.0, 10.0, 5.0, 3.0, 2.0]  # cum-before: 0,40,80,90,95,98
    assert svc.abc_classify(vals, 80, 95) == ["A", "A", "A", "B", "B", "C"]


def _pid(db, code):
    return db.execute(text("SELECT id FROM products WHERE product_code = :c"), {"c": code}).scalar()


def _wid(db, code):
    return db.execute(text("SELECT id FROM warehouses WHERE warehouse_code = :c"), {"c": code}).scalar()


def _run(db):
    pids = [_pid(db, x["product_code"]) for x in _GOLDEN["demand"]]
    svc.run_analytics(db, scope={"product_ids": pids}, config={"as_of": _AS_OF})


@pytest.mark.parametrize("g", _GOLDEN["demand"], ids=[f"{g['product_code']}@{g['warehouse_code']}" for g in _GOLDEN["demand"]])
def test_abc_xyz_matches_golden(scm_app, g):
    _, db, _, _ = scm_app
    _run(db)
    pid, wid = _pid(db, g["product_code"]), _wid(db, g["warehouse_code"])
    row = db.execute(text(
        "SELECT abc_class, xyz_class, computed_at FROM scm.item_classification "
        "WHERE product_id = :p AND warehouse_id = :w"
    ), {"p": pid, "w": wid}).fetchone()
    assert row is not None, "item_classification not written (AC-M2.7 SKUxwarehouse)"
    assert row.abc_class == g["abc_class"]
    assert row.xyz_class == g["xyz_class"]
    assert row.computed_at is not None


def test_null_cost_sku_classifies_unknown(scm_app):
    """AC-M2.6: a SKU with no cost_price cannot have an annual value -> abc_class NULL
    (unknown), not zeroed. XYZ still computes from demand CV."""
    _, db, _, _ = scm_app
    key = db.execute(text("""
        SELECT np.product_id, np.warehouse_id FROM scm.net_position_v np
        JOIN products p ON p.id = np.product_id
        JOIN scm.consumption_v c ON c.product_id = np.product_id AND c.warehouse_id = np.warehouse_id
        WHERE (p.cost_price IS NULL OR p.cost_price = 0)
          AND c.day >= :lo AND c.day < :as_of
        LIMIT 1
    """), {"lo": _AS_OF - timedelta(days=90), "as_of": _AS_OF}).fetchone()
    if key is None:
        pytest.skip("no null-cost SKU with outflow found")
    svc.run_analytics(db, scope={"product_ids": [key.product_id]}, config={"as_of": _AS_OF})
    row = db.execute(text(
        "SELECT abc_class, xyz_class, annual_value FROM scm.item_classification "
        "WHERE product_id = :p AND warehouse_id = :w"
    ), {"p": key.product_id, "w": key.warehouse_id}).fetchone()
    assert row is not None
    assert row.abc_class is None
    assert row.annual_value is None
    assert row.xyz_class in ("X", "Y", "Z")


def test_abc_cut_points_are_configurable(scm_app):
    """AC-M2.5: shrinking abc_a_pct reclassifies A-items with no code change."""
    _, db, _, _ = scm_app
    # force a tiny A band so the top costed key alone can't be 'A' cumulatively
    import uuid as _uuid
    # tiny cumulative cut points (5% A / 10% B, canonical 0..100 scale) — well above 1
    # so they are read literally, not as legacy fractions.
    db.execute(text("UPDATE scm.abc_xyz_policy SET is_active = false"))
    db.execute(text(
        "INSERT INTO scm.abc_xyz_policy (id, abc_a_pct, abc_b_pct, xyz_x_max, xyz_y_max, "
        "is_active, source_system, source_ref, created_at, updated_at) "
        "VALUES (:id, 5, 10, 0.5, 1.0, true, 'test', 'cut', now(), now())"
    ), {"id": str(_uuid.uuid4())})
    db.flush()
    g = _GOLDEN["demand"][1]  # B2155-NL-BLUE@BRW-IB — 'A' under default 80/95
    pid, wid = _pid(db, g["product_code"]), _wid(db, g["warehouse_code"])
    svc.run_analytics(db, scope={"product_ids": [_pid(db, x["product_code"]) for x in _GOLDEN["demand"]]},
                      config={"as_of": _AS_OF})
    abc = db.execute(text(
        "SELECT abc_class FROM scm.item_classification WHERE product_id = :p AND warehouse_id = :w"
    ), {"p": pid, "w": wid}).scalar()
    # with a 5%/10% band this mid-value key is no longer 'A'
    assert abc != "A"


def test_ensure_policy_defaults_idempotent(scm_app):
    _, db, _, _ = scm_app
    db.execute(text("DELETE FROM scm.abc_xyz_policy"))
    db.execute(text("DELETE FROM scm.supplier_scoring_policy"))
    db.flush()
    svc.ensure_policy_defaults(db)
    svc.ensure_policy_defaults(db)  # second call must not duplicate
    assert db.execute(text("SELECT count(*) FROM scm.abc_xyz_policy WHERE is_active")).scalar() == 1
    assert db.execute(text("SELECT count(*) FROM scm.supplier_scoring_policy WHERE is_active")).scalar() == 1
