"""SCM M3 reorder engine — RESOLVER layer (reads the live M1/M2 tables).

The pure maths are golden-tested in ``test_m3_engine.py``; this file proves the thin
resolver reads ``scm.reorder_policy`` / ``scm.item_classification`` /
``scm.supplier_performance`` / ``product_suppliers`` / ``scm.net_position_v`` correctly
and feeds them into the pure functions. Everything is written inside the rolled-back
SAVEPOINT the ``scm_app`` fixture provides, so no synthetic row escapes to the shared DB.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.services.scm import reorder_engine as eng
from app.services.scm.reorder_policy import global_policy_row
from tests.scm.conftest import requires_pg

pytestmark = requires_pg


def _product(db):
    return db.execute(text("SELECT id FROM products LIMIT 1")).scalar()


def _warehouse(db):
    return db.execute(text("SELECT id FROM warehouses LIMIT 1")).scalar()


def _mk_supplier(db, name):
    sid = str(uuid.uuid4())
    db.execute(text(
        "INSERT INTO suppliers (id, supplier_code, supplier_name, is_active, created_at, updated_at) "
        "VALUES (:id, :code, :name, true, now(), now())"
    ), {"id": sid, "code": f"M3T-{sid[:8]}", "name": name})
    return sid


def _link(db, product_id, supplier_id, *, lead=None, moq=None, mult=None, cost=None,
          primary=False, var=None):
    db.execute(text(
        "INSERT INTO product_suppliers (id, product_id, supplier_id, standard_lead_time_days, "
        "moq, order_multiple, unit_cost, currency, is_primary_supplier, "
        "lead_time_variability_days, created_at) "
        "VALUES (:id, :pid, :sid, :lead, :moq, :mult, :cost, 'MYR', :prim, :var, now())"
    ), {"id": str(uuid.uuid4()), "pid": product_id, "sid": supplier_id, "lead": lead,
        "moq": moq, "mult": mult, "cost": cost, "prim": primary, "var": var})


def _perf(db, supplier_id, product_id, *, lead, var, score, sample, conf):
    db.execute(text(
        "INSERT INTO scm.supplier_performance (id, supplier_id, product_id, avg_lead_time_days, "
        "lead_time_variance, composite_score, sample_size, confidence, source_system, "
        "source_ref, created_at) "
        "VALUES (:id, :sid, :pid, :lead, :var, :score, :sample, :conf, 'm3test', 't', now())"
    ), {"id": str(uuid.uuid4()), "sid": supplier_id, "pid": product_id, "lead": lead,
        "var": var, "score": score, "sample": sample, "conf": conf})


def _reset_policies(db):
    """Isolate policy resolution from ambient seeded rows (rolled back at teardown)."""
    db.execute(text("DELETE FROM scm.reorder_policy"))


# --- ensure_reorder_policy_defaults (idempotent global seed) ---------------

def test_ensure_reorder_policy_defaults_idempotent(scm_app):
    _, db, _, _ = scm_app
    _reset_policies(db)
    assert global_policy_row(db) is None
    eng.ensure_reorder_policy_defaults(db)
    row = db.execute(text(
        "SELECT policy_type, safety_stock_method, safety_days, service_level, "
        "review_period_days, factor_toggles, scope_type FROM scm.reorder_policy "
        "WHERE scope_type = 'global'"
    )).mappings().all()
    assert len(row) == 1
    r = row[0]
    assert r["policy_type"] == "reorder_point"
    assert r["safety_stock_method"] == "fixed_days"
    assert float(r["safety_days"]) == 7
    assert float(r["service_level"]) == pytest.approx(0.95)
    assert int(r["review_period_days"]) == 30
    # Cost leads: the same item is bought from more than one supplier on 5,995 products,
    # and the rule is to take the cheapest. `is_primary` stays in the sort key as the
    # tiebreak, so a nominated supplier still wins a tie - it no longer wins on nomination.
    assert r["factor_toggles"]["supplier_selection"] == "lowest_cost"
    assert int(r["factor_toggles"]["lead_time_default_days"]) == 30
    # second call inserts nothing
    eng.ensure_reorder_policy_defaults(db)
    assert db.execute(text(
        "SELECT count(*) FROM scm.reorder_policy WHERE scope_type = 'global'"
    )).scalar() == 1


# --- resolve_policy_for_sku (classification cell -> class -> global) --------

def test_resolve_policy_for_sku_picks_abc_xyz_cell(scm_app):
    _, db, _, _ = scm_app
    pid = _product(db)
    wid = _warehouse(db)
    _reset_policies(db)
    # classify the SKU as A / X in this warehouse
    db.execute(text("DELETE FROM scm.item_classification WHERE product_id = :p AND warehouse_id = :w"),
               {"p": pid, "w": wid})
    db.execute(text(
        "INSERT INTO scm.item_classification (id, product_id, warehouse_id, abc_class, xyz_class, "
        "source_system, source_ref, created_at) VALUES (:id, :p, :w, 'A', 'X', 'm3test', 't', now())"
    ), {"id": str(uuid.uuid4()), "p": pid, "w": wid})
    # a global + a matching abc_xyz cell policy
    for st, ref, prio, pol in (("global", None, 0, "g"), ("abc_xyz_cell", "A-X", 15, "cell")):
        db.execute(text(
            "INSERT INTO scm.reorder_policy (id, scope_type, scope_ref, policy_type, safety_days, "
            "is_active, priority, source_system, source_ref, created_at, updated_at) "
            "VALUES (:id, :st, :ref, 'reorder_point', 7, true, :prio, 'm3test', :pol, now(), now())"
        ), {"id": str(uuid.uuid4()), "st": st, "ref": ref, "prio": prio, "pol": pol})
    db.flush()
    policy = eng.resolve_policy_for_sku(db, pid, wid)
    assert policy is not None and policy["scope_type"] == "abc_xyz_cell"
    assert policy["scope_ref"] == "A-X"


def test_resolve_policy_for_sku_falls_back_to_global(scm_app):
    _, db, _, _ = scm_app
    pid = _product(db)
    _reset_policies(db)
    eng.ensure_reorder_policy_defaults(db)
    db.flush()
    policy = eng.resolve_policy_for_sku(db, pid, None)
    assert policy is not None and policy["scope_type"] == "global"
    # engine toggles read through factor_toggles with locked defaults
    toggles = eng.policy_toggles(policy)
    assert toggles["supplier_selection"] == "lowest_cost"
    assert int(toggles["lead_time_default_days"]) == 30


# --- resolve_supplier_for_sku (precedence + measured lead + no-supplier) ----

def test_resolve_supplier_primary_and_measured_lead(scm_app):
    _, db, _, _ = scm_app
    pid = _product(db)
    db.execute(text("DELETE FROM product_suppliers WHERE product_id = :p"), {"p": pid})
    primary = _mk_supplier(db, "M3 Primary")
    cheaper = _mk_supplier(db, "M3 Cheaper Overseas")
    _link(db, pid, primary, lead=30, moq=50, mult=12, cost=100, primary=True, var=4)
    _link(db, pid, cheaper, lead=45, moq=100, mult=12, cost=80, primary=False, var=9)
    # measured lead for the primary supplier×product (overrides its declared 30)
    _perf(db, primary, pid, lead=18.0, var=3.0, score=0.7, sample=5, conf="high")
    _perf(db, cheaper, pid, lead=40.0, var=9.0, score=0.9, sample=4, conf="high")
    db.flush()

    res = eng.resolve_supplier_for_sku(db, pid, selection="primary")
    assert res["exception"] is None
    chosen = res["chosen"]
    assert chosen["is_primary"] is True
    assert chosen["lead_time_days"] == pytest.approx(18.0)     # measured beat declared 30
    assert chosen["lead_time_source"] == "measured"
    assert chosen["lead_time_variance"] == pytest.approx(3.0)
    # the cheaper/best-score supplier is attached as a ranked alternative
    assert [str(a["supplier_id"]) for a in res["alternatives"]] == [cheaper]

    # best_score toggle flips the choice to the higher-composite overseas supplier
    res2 = eng.resolve_supplier_for_sku(db, pid, selection="best_score")
    assert str(res2["chosen"]["supplier_id"]) == cheaper


def test_resolve_supplier_declared_lead_when_unmeasured(scm_app):
    _, db, _, _ = scm_app
    pid = _product(db)
    db.execute(text("DELETE FROM product_suppliers WHERE product_id = :p"), {"p": pid})
    db.execute(text("DELETE FROM scm.supplier_performance WHERE product_id = :p"), {"p": pid})
    sup = _mk_supplier(db, "M3 Unmeasured")
    _link(db, pid, sup, lead=21, moq=50, mult=6, cost=42, primary=True, var=None)
    db.flush()
    res = eng.resolve_supplier_for_sku(db, pid)
    assert res["chosen"]["lead_time_days"] == pytest.approx(21)   # declared
    assert res["chosen"]["lead_time_source"] == "declared"


def test_resolve_supplier_no_link_flags_exception(scm_app):
    _, db, _, _ = scm_app
    # a real product with no product_suppliers row (AC-M3.6)
    pid = db.execute(text(
        "SELECT p.id FROM products p WHERE NOT EXISTS "
        "(SELECT 1 FROM product_suppliers ps WHERE ps.product_id = p.id) LIMIT 1"
    )).scalar()
    if pid is None:
        pytest.skip("no unlinked product available")
    res = eng.resolve_supplier_for_sku(db, pid)
    assert res["chosen"] is None and res["exception"] == "no_supplier"


# --- load_net_position (reads the M1 view) ---------------------------------

def test_load_net_position_reads_view(scm_app):
    _, db, _, _ = scm_app
    row = db.execute(text(
        "SELECT product_id, warehouse_id, net_position FROM scm.net_position_v LIMIT 1"
    )).mappings().first()
    if row is None:
        pytest.skip("net_position_v empty (unseeded DB)")
    loaded = eng.load_net_position(db, row["product_id"], row["warehouse_id"])
    assert loaded and loaded[0]["warehouse_id"] == row["warehouse_id"]
    assert float(loaded[0]["net_position"]) == pytest.approx(float(row["net_position"]))
