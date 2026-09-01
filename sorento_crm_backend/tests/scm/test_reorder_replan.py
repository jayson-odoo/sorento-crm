"""S5 - Plan detail Header/Lines tabs + Re-plan supersede (PLAN-scm-reorder-oi-feedback-1sep.md,
G8; UAC AC-5.2/AC-5.3).

A Re-plan creates a NEW run with edited Plan-until / scope values, supersedes the OLD one
with a two-way link, and carries plan_row_decisions across for a product/location whose
suggestion did not change - dropping a decision when the product left scope, and flagging
the arriving (undecided) row `needs_recheck` when the suggestion changed. Runs stay
immutable: the old run's own recommendations/decisions are never touched.

Postgres via `scm_app`'s rolled-back savepoint, reusing `test_m3_run.py`'s controlled
fixture builders so a `buy` rec type is reliably produced (G1's committed-demand gate).
`run_reorder` runs SYNCHRONOUSLY (no live worker required) so the post-commit carry step
that lives at the end of `_execute_run_scoped` runs inline, inside the test.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.order import SalesOrder, SalesOrderLine
from app.models.scm import ReorderRun
from app.services.error_handler import AppException
from app.services.scm import decision_service
from app.services.scm import reorder_run_service as svc
from tests.scm.conftest import requires_pg
from tests.scm.test_m3_run import (
    _link,
    _mk_committed,
    _mk_demand,
    _mk_product,
    _mk_stock,
    _mk_supplier,
    _mk_warehouse,
)

pytestmark = requires_pg


def _buy_rec_id(db, run_id: str, sku: str) -> str:
    row = db.execute(text(
        "SELECT rr.id, rr.rounded_qty FROM scm.reorder_recommendation rr "
        "JOIN products p ON p.id = rr.product_id "
        "WHERE rr.run_id = :r AND rr.rec_type = 'buy' AND p.product_code = :sku"
    ), {"r": run_id, "sku": sku}).first()
    assert row, f"no buy rec for {sku} on run {run_id}"
    return str(row[0])


def _decisions_for(db, rec_id: str) -> list:
    return db.execute(text(
        "SELECT kind, buy_qty FROM scm.plan_row_decision WHERE recommendation_id = :r"
    ), {"r": rec_id}).mappings().all()


def _needs_recheck(db, rec_id: str) -> bool:
    inputs = db.execute(text(
        "SELECT inputs FROM scm.reorder_recommendation WHERE id = :r"
    ), {"r": rec_id}).scalar()
    return bool((inputs or {}).get("needs_recheck"))


def _rec_exists(db, run_id: str, sku: str) -> bool:
    row = db.execute(text(
        "SELECT 1 FROM scm.reorder_recommendation rr JOIN products p ON p.id = rr.product_id "
        "WHERE rr.run_id = :r AND p.product_code = :sku"
    ), {"r": run_id, "sku": sku}).first()
    return row is not None


def _seed_buy_scenario(db, code: str):
    """One product/warehouse with a real buy trigger (low stock + demand) plus the G1
    committed-demand line that admits it to the run."""
    wid = _mk_warehouse(db, f"RPW-{code}")
    pid = _mk_product(db, f"RPP-{code}")
    _mk_stock(db, pid, wid, 10)
    _mk_demand(db, pid, wid, 10.0)
    _mk_committed(db, pid, wid, qty=1)
    _link(db, pid, _mk_supplier(db, f"Replan Supplier {code}"))
    db.flush()
    return {"warehouse_id": wid, "warehouse_code": f"RPW-{code}",
            "product_id": pid, "product_code": f"RPP-{code}"}


def test_replan_creates_new_run_supersedes_old_two_way(scm_app):
    """AC-5.2: the new run points back at the old one (`supersedes_run_id`, stamped at
    creation) and the old run points forward to the new one (`superseded_by_run_id`,
    stamped once the new run completes) - readable from either side."""
    _, db, _, _ = scm_app
    p = _seed_buy_scenario(db, "A1")

    old = svc.create_run(db, [p["warehouse_code"]], enqueue=False)
    svc.run_reorder(old["run_id"], db=db)

    new = svc.replan_run(
        db, old["run_id"],
        warehouse_codes=[p["warehouse_code"]], product_codes=[], plan_horizon_date=None,
        actor="tester",
    )
    assert new["run_id"] != old["run_id"]
    new_row = db.get(ReorderRun, new["run_id"])
    assert str(new_row.supersedes_run_id) == old["run_id"], (
        "the new run must be stamped with what it supersedes BEFORE its own job runs"
    )
    # Not superseded yet - the new run has not completed.
    old_row = db.get(ReorderRun, old["run_id"])
    assert old_row.superseded_by_run_id is None

    svc.run_reorder(new["run_id"], db=db)
    db.refresh(old_row)
    assert str(old_row.superseded_by_run_id) == new["run_id"], (
        "the OLD run must point forward once its replacement actually completed"
    )


def test_replan_carries_decision_for_unchanged_suggestion(scm_app):
    """AC-5.3: a product/location present in both runs with an UNCHANGED suggestion keeps
    its decision - copied onto the new run's matching recommendation, never mutating the
    old (immutable) one."""
    _, db, _, _ = scm_app
    p = _seed_buy_scenario(db, "B1")

    old = svc.create_run(db, [p["warehouse_code"]], enqueue=False)
    svc.run_reorder(old["run_id"], db=db)
    old_rec_id = _buy_rec_id(db, old["run_id"], p["product_code"])
    decision_service.record_plan_row_decision(
        db, old_rec_id, kind="buy", buy_qty=25, stock_takes=None, po_qty=None,
        po_refs=None, reason_text=None, actor="tester",
    )
    db.flush()

    new = svc.replan_run(
        db, old["run_id"],
        warehouse_codes=[p["warehouse_code"]], product_codes=[], plan_horizon_date=None,
        actor="tester",
    )
    svc.run_reorder(new["run_id"], db=db)

    new_rec_id = _buy_rec_id(db, new["run_id"], p["product_code"])
    assert new_rec_id != old_rec_id, "runs stay immutable - a re-plan writes NEW rec rows"
    new_decisions = _decisions_for(db, new_rec_id)
    assert len(new_decisions) == 1, "the decision was not carried to the matching new row"
    assert float(new_decisions[0]["buy_qty"]) == 25.0

    # The OLD row's own decision is untouched.
    old_decisions = _decisions_for(db, old_rec_id)
    assert len(old_decisions) == 1 and float(old_decisions[0]["buy_qty"]) == 25.0
    assert not _needs_recheck(db, new_rec_id)


def test_replan_flags_recheck_when_suggestion_changed(scm_app):
    """AC-5.3: a product/location present in both runs whose suggestion CHANGED arrives
    undecided, flagged `needs_recheck` - the buyer decides again rather than trusting a
    carried figure that no longer matches what the engine is now proposing."""
    _, db, _, _ = scm_app
    p = _seed_buy_scenario(db, "C1")

    old = svc.create_run(db, [p["warehouse_code"]], enqueue=False)
    svc.run_reorder(old["run_id"], db=db)
    old_rec_id = _buy_rec_id(db, old["run_id"], p["product_code"])
    decision_service.record_plan_row_decision(
        db, old_rec_id, kind="buy", buy_qty=10, stock_takes=None, po_qty=None,
        po_refs=None, reason_text=None, actor="tester",
    )
    db.flush()

    # Raise committed demand so the net position drops and the engine proposes a BIGGER
    # buy on the next run - the suggestion genuinely changed, not a re-run artifact.
    so = SalesOrder(id=str(uuid.uuid4()), so_number=f"RPTESTSO-{uuid.uuid4().hex[:8]}",
                    status="open", demand_class="retail")
    db.add(so)
    db.flush()
    db.add(SalesOrderLine(
        id=str(uuid.uuid4()), sales_order_id=so.id, product_id=p["product_id"],
        warehouse_id=p["warehouse_id"], qty_ordered=500, qty_delivered=0,
        line_status="open",
    ))
    db.flush()

    new = svc.replan_run(
        db, old["run_id"],
        warehouse_codes=[p["warehouse_code"]], product_codes=[], plan_horizon_date=None,
        actor="tester",
    )
    svc.run_reorder(new["run_id"], db=db)

    new_rec_id = _buy_rec_id(db, new["run_id"], p["product_code"])
    old_qty = db.execute(text(
        "SELECT rounded_qty FROM scm.reorder_recommendation WHERE id = :r"
    ), {"r": old_rec_id}).scalar()
    new_qty = db.execute(text(
        "SELECT rounded_qty FROM scm.reorder_recommendation WHERE id = :r"
    ), {"r": new_rec_id}).scalar()
    assert float(new_qty) != float(old_qty), "fixture failed to move the suggestion"

    assert _decisions_for(db, new_rec_id) == [], "a changed suggestion must arrive undecided"
    assert _needs_recheck(db, new_rec_id), "a changed suggestion must be flagged for re-check"


def test_replan_drops_decision_for_a_product_that_left_scope(scm_app):
    """AC-5.3: a product outside the re-plan's narrowed scope produces no row at all on
    the new run, so its old decision is not carried anywhere - a silent drop, not an
    error."""
    _, db, _, _ = scm_app
    kept = _seed_buy_scenario(db, "D1")
    dropped = _seed_buy_scenario(db, "D2")

    old = svc.create_run(
        db, [kept["warehouse_code"], dropped["warehouse_code"]], enqueue=False,
    )
    svc.run_reorder(old["run_id"], db=db)
    kept_rec = _buy_rec_id(db, old["run_id"], kept["product_code"])
    dropped_rec = _buy_rec_id(db, old["run_id"], dropped["product_code"])
    for rec_id in (kept_rec, dropped_rec):
        decision_service.record_plan_row_decision(
            db, rec_id, kind="buy", buy_qty=5, stock_takes=None, po_qty=None,
            po_refs=None, reason_text=None, actor="tester",
        )
    db.flush()

    # Narrow the re-plan to ONE product only.
    new = svc.replan_run(
        db, old["run_id"],
        warehouse_codes=[kept["warehouse_code"], dropped["warehouse_code"]],
        product_codes=[kept["product_code"]], plan_horizon_date=None, actor="tester",
    )
    svc.run_reorder(new["run_id"], db=db)

    assert _rec_exists(db, new["run_id"], kept["product_code"])
    assert not _rec_exists(db, new["run_id"], dropped["product_code"]), (
        "a product outside the narrowed scope must not appear on the new run"
    )
    new_kept_rec = _buy_rec_id(db, new["run_id"], kept["product_code"])
    assert len(_decisions_for(db, new_kept_rec)) == 1


def test_replan_refuses_a_run_that_is_not_completed(scm_app):
    """AC-5.2 guard: nothing to supersede on a run that never finished."""
    _, db, _, _ = scm_app
    p = _seed_buy_scenario(db, "E1")
    running = svc.create_run(db, [p["warehouse_code"]], enqueue=False)  # never run_reorder'd

    with pytest.raises(AppException) as exc:
        svc.replan_run(
            db, running["run_id"],
            warehouse_codes=[p["warehouse_code"]], product_codes=[], plan_horizon_date=None,
            actor="tester",
        )
    assert exc.value.status_code == 422


def test_replan_refuses_a_run_already_replanned(scm_app):
    """One re-plan per run keeps the lineage a simple chain - re-plan the NEWEST run
    instead of forking an old one a second time."""
    _, db, _, _ = scm_app
    p = _seed_buy_scenario(db, "F1")
    old = svc.create_run(db, [p["warehouse_code"]], enqueue=False)
    svc.run_reorder(old["run_id"], db=db)

    first = svc.replan_run(
        db, old["run_id"],
        warehouse_codes=[p["warehouse_code"]], product_codes=[], plan_horizon_date=None,
        actor="tester",
    )
    svc.run_reorder(first["run_id"], db=db)

    with pytest.raises(AppException) as exc:
        svc.replan_run(
            db, old["run_id"],
            warehouse_codes=[p["warehouse_code"]], product_codes=[], plan_horizon_date=None,
            actor="tester",
        )
    assert exc.value.status_code == 422
