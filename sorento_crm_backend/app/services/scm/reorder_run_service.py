"""SCM M3 reorder RUN JOB — drives the deterministic engine over a background run.

The pure maths + resolver live in ``reorder_engine`` (golden-tested). This module is
the ORCHESTRATION layer: it enumerates the planning SKUs in the selected warehouses,
calls the engine per SKU×warehouse (or aggregated when ``buy_scope='network'``), and
PERSISTS one ``scm.reorder_recommendation`` per emitted rec with its FROZEN inputs
(AC-M3.11 — reproducible without stat versioning), plus a ``scm.reorder_run`` log with
status transitions + counts.

Flow:
  * ``create_run`` inserts a ``running`` run (scope snapshot, started_at) and enqueues
    the RQ ``run_reorder(run_id)`` task on the ``imports`` queue (drained by the worker).
  * ``run_reorder`` (the worker task body) loads the run, evaluates all planning SKUs,
    writes the recommendations, and flips the run to ``completed`` (+ run-log counts) or
    ``failed`` (+ error_text) — it NEVER crashes the worker.
  * A re-run always creates a NEW run_id — runs are immutable history.

Two recommendation types (M3-D5):
  * ``buy`` — a triggered reorder (per policy trigger); ``disposition`` — dead/overstock.
  * A no-supplier SKU that WOULD trigger a buy emits an ``exception`` rec (never silently
    skipped — AC-M3.6).
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.scm import ReorderRecommendation, ReorderRun
from app.services.scm import cash_ranking
from app.services.scm import reorder_engine as eng
from app.services.scm.reorder_policy import (
    DEFAULT_DEAD_STOCK_DAYS,
    DEFAULT_OVERSTOCK_DAYS,
)

log = logging.getLogger(__name__)

_SEED = "run"
_STAGES = ("resolving_policies", "computing_reorder_points",
           "selecting_suppliers", "writing_recommendations")


# ===========================================================================
# create_run — insert the run + enqueue the job
# ===========================================================================

def create_run(db: Session, warehouse_codes: Optional[list[str]], buy_scope: str,
               budget_id: Optional[str] = None, actor: Optional[str] = None,
               enqueue: bool = True) -> dict:
    """Insert a ``running`` ``scm.reorder_run`` (scope snapshot + started_at) and
    enqueue the RQ ``run_reorder`` task. Returns ``{run_id, status, buy_scope, stage}``.

    ``warehouse_codes`` empty/None => plan every active warehouse. A re-run always
    creates a NEW run_id (runs are immutable). ``enqueue=False`` skips the RQ enqueue
    (tests call ``run_reorder`` synchronously).
    """
    buy_scope = buy_scope if buy_scope in ("network", "warehouse") else "network"
    warehouse_ids = _resolve_warehouse_ids(db, warehouse_codes)
    run_id = str(uuid.uuid4())
    now = datetime.utcnow()
    db.add(ReorderRun(
        id=run_id,
        created_by=actor,
        status="running",
        warehouse_ids=warehouse_ids,
        buy_scope=buy_scope,
        budget_id=budget_id or None,
        policy_snapshot_ref=f"policies@{now.isoformat()}",
        started_at=now,
        run_log={"stage": _STAGES[0]},
        source_system="scm",
        source_ref=_SEED,
    ))
    db.commit()

    if enqueue:
        try:
            from app.services.queue_service import enqueue_job
            from app.tasks.reorder_tasks import run_reorder_job
            enqueue_job(run_reorder_job, run_id, queue_name="imports")
        except Exception:  # noqa: BLE001 — the run row exists; a broken broker must
            # not 500 the request. The run can be driven manually / by the next tick.
            log.exception("create_run: failed to enqueue run_reorder for %s", run_id)

    return {"run_id": run_id, "status": "running", "buy_scope": buy_scope,
            "stage": _STAGES[0]}


def _resolve_warehouse_ids(db: Session, warehouse_codes: Optional[list[str]]) -> list[str]:
    if warehouse_codes:
        rows = db.execute(text(
            "SELECT id FROM warehouses WHERE warehouse_code = ANY(:codes)"
        ), {"codes": [str(c) for c in warehouse_codes]}).fetchall()
        return [str(r[0]) for r in rows]
    rows = db.execute(text(
        "SELECT id FROM warehouses WHERE is_active = true"
    )).fetchall()
    return [str(r[0]) for r in rows]


# ===========================================================================
# run_reorder — the worker task body
# ===========================================================================

def run_reorder(run_id: str, db: Optional[Session] = None) -> dict:
    """Worker entry: evaluate all planning SKUs for ``run_id`` and persist the
    recommendations. Creates its own session when called from the worker; tests pass
    ``db`` to run inside their rolled-back savepoint. Never raises — a failure is
    recorded on the run (status='failed' + error_text) so the worker survives."""
    own = db is None
    if own:
        from app.database import SessionLocal
        db = SessionLocal()
    try:
        return _execute_run(db, run_id)
    finally:
        if own:
            db.close()


def _execute_run(db: Session, run_id: str) -> dict:
    run = db.get(ReorderRun, run_id)
    if run is None:
        raise ValueError(f"reorder_run {run_id} not found")
    started = run.started_at or datetime.utcnow()

    # The heavy evaluation runs inside a SAVEPOINT: on failure we roll back ONLY the
    # planning work (partial recommendations, seeded policy) and keep the already-
    # committed run row so we can still stamp it 'failed' + error_text. The worker
    # never sees an exception — a broken run is recorded, not crashed.
    sp = db.begin_nested()
    try:
        eng.ensure_reorder_policy_defaults(db)
        policies = eng.load_policies(db)
        today = date.today()

        rows = _planning_rows(db, run.warehouse_ids)
        last_move = _last_movement_map(db, [r["product_id"] for r in rows], run.warehouse_ids)
        wh_meta = {str(r["warehouse_id"]): (r["warehouse_code"], r["warehouse_name"]) for r in rows}

        if run.buy_scope == "network":
            recs = _plan_network(db, run_id, rows, policies, today, last_move, wh_meta)
        else:
            recs = _plan_per_warehouse(db, run_id, rows, policies, today, last_move)

        # M4 cash stage — compute + FREEZE each buy's rank_score / rank / rank_factors
        # (funded/deferred is computed live at view-time against a budget, not here).
        _apply_cash_stage(db, recs)

        for r in recs:
            db.add(r)
        db.flush()
        sp.commit()

        counts = _summarise(recs)
        counts["duration_ms"] = int((datetime.utcnow() - started).total_seconds() * 1000)
        run.status = "completed"
        run.finished_at = datetime.utcnow()
        run.run_log = {"stage": _STAGES[3], **counts}
        db.add(run)
        db.commit()
        return {"run_id": run_id, "status": "completed", **counts}
    except Exception as exc:  # noqa: BLE001 — record, never crash the worker
        log.exception("run_reorder %s failed", run_id)
        try:
            sp.rollback()
        except Exception:
            pass
        try:
            run.status = "failed"
            run.finished_at = datetime.utcnow()
            run.error_text = str(exc)[:2000]
            run.run_log = {**(run.run_log or {}), "stage": (run.run_log or {}).get("stage")}
            db.add(run)
            db.commit()
        except Exception:
            log.exception("run_reorder %s: failed to record failure", run_id)
        return {"run_id": run_id, "status": "failed", "error": str(exc)[:2000]}


# ===========================================================================
# planning-SKU enumeration (M2 lifecycle/focus predicate: active + ongoing)
# ===========================================================================

def _planning_rows(db: Session, warehouse_ids: Optional[list[str]]) -> list[dict]:
    """Active + ongoing SKU×warehouse rows with a net position / demand in the selected
    warehouses (reuses the dashboard focus predicate). Empty ``warehouse_ids`` => all."""
    where = ["p.is_active = true", "p.is_discontinued = false"]
    params: dict[str, Any] = {}
    if warehouse_ids:
        where.append("np.warehouse_id::text = ANY(:wids)")
        params["wids"] = [str(w) for w in warehouse_ids]
    sql = text(f"""
        SELECT np.product_id, np.warehouse_id,
               p.product_code, p.product_name, pc.category_code, p.list_price,
               w.warehouse_code, w.warehouse_name,
               np.quantity_on_hand, np.on_order, np.committed, np.net_position,
               ds.avg_daily_demand, ds.demand_cv, ds.sample_days,
               ic.abc_class, ic.xyz_class
        FROM scm.net_position_v np
        JOIN products p ON p.id = np.product_id
        JOIN warehouses w ON w.id = np.warehouse_id
        LEFT JOIN product_categories pc ON pc.id = p.category_id
        LEFT JOIN scm.demand_stat ds
          ON ds.product_id = np.product_id AND ds.warehouse_id = np.warehouse_id
        LEFT JOIN scm.item_classification ic
          ON ic.product_id = np.product_id AND ic.warehouse_id = np.warehouse_id
        WHERE {' AND '.join(where)}
        ORDER BY p.product_code, w.warehouse_code
    """)
    return [dict(r) for r in db.execute(sql, params).mappings().all()]


def _last_movement_map(db: Session, product_ids: list[str],
                       warehouse_ids: Optional[list[str]]) -> dict[tuple, date]:
    pids = list({str(p) for p in product_ids})
    if not pids:
        return {}
    params: dict[str, Any] = {"pids": pids}
    wh = ""
    if warehouse_ids:
        wh = "AND cv.warehouse_id::text = ANY(:wids)"
        params["wids"] = [str(w) for w in warehouse_ids]
    rows = db.execute(text(f"""
        SELECT cv.product_id, cv.warehouse_id, MAX(cv.day) AS last_day
        FROM scm.consumption_v cv
        WHERE cv.product_id::text = ANY(:pids) {wh}
        GROUP BY cv.product_id, cv.warehouse_id
    """), params).fetchall()
    return {(str(r[0]), str(r[1])): r[2] for r in rows}


# ===========================================================================
# per-warehouse planning (buy_scope=warehouse)
# ===========================================================================

def _plan_per_warehouse(db: Session, run_id: str, rows: list[dict], policies: list[dict],
                        today: date, last_move: dict) -> list[ReorderRecommendation]:
    recs: list[ReorderRecommendation] = []
    # group by product so transfer flags can see all warehouses of a SKU
    by_product: dict[str, list[dict]] = {}
    for r in rows:
        by_product.setdefault(str(r["product_id"]), []).append(r)

    for pid, prows in by_product.items():
        cands = eng.load_supplier_candidates(db, pid)
        computed: list[dict] = []
        for r in prows:
            c = _compute_cell(db, r, policies, cands, today, last_move)
            computed.append(c)
        flags = _transfer_flags_for(prows, computed)
        for r, c in zip(prows, computed):
            recs.extend(_emit_cell(run_id, r, c, flags.get(str(r["warehouse_id"]))))
    return recs


def _compute_cell(db: Session, row: dict, policies: list[dict], cands: list[dict],
                  today: date, last_move: dict) -> dict:
    """Run the engine for one SKU×warehouse; returns the frozen decision values."""
    pid = str(row["product_id"])
    wid = str(row["warehouse_id"])
    policy = eng.resolve_policy_for_sku(db, pid, wid, policies) or {}
    tog = eng.policy_toggles(policy)

    sel = eng.select_supplier(cands, selection=tog["supplier_selection"])
    chosen = sel["chosen"]
    by_id = {c["supplier_id"]: c for c in cands}
    alt_choices = [_supplier_choice(by_id[a["supplier_id"]]) for a in sel["alternatives"]
                   if a["supplier_id"] in by_id]

    demand_rate = float(row["avg_daily_demand"] or 0.0)
    net = float(row["net_position"] or 0.0)
    on_hand = float(row["quantity_on_hand"] or 0.0)
    cv = float(row["demand_cv"]) if row["demand_cv"] is not None else None

    policy_type = policy.get("policy_type") or "reorder_point"
    service_level = float(policy.get("service_level") or eng.DEFAULT_SERVICE_LEVEL)
    ss_method = policy.get("safety_stock_method")
    safety_days = float(policy.get("safety_days") or eng.DEFAULT_SAFETY_DAYS)
    review_days = float(policy.get("review_period_days") or eng.DEFAULT_REVIEW_PERIOD_DAYS)
    min_override = _fnum(policy.get("min_override"))
    max_override = _fnum(policy.get("max_override"))
    dead_days = float(policy.get("dead_stock_days") or DEFAULT_DEAD_STOCK_DAYS)
    overstock_days = float(policy.get("overstock_days") or DEFAULT_OVERSTOCK_DAYS)

    if chosen:
        lead = float(chosen["lead_time_days"])
        lead_src = chosen["lead_time_source"]
        moq = _fnum(chosen.get("moq"))
        order_multiple = _fnum(chosen.get("order_multiple"))
        var_lt = _fnum(chosen.get("lead_time_variance"))
        unit_cost = _fnum(chosen.get("unit_cost"))
        currency = chosen.get("currency")
    else:
        lead = float(tog["lead_time_default_days"])
        lead_src = "default"
        moq = order_multiple = var_lt = unit_cost = currency = None

    ss, ss_used, ss_fallback = eng.safety_stock(
        ss_method, demand_rate=demand_rate, safety_days=safety_days,
        service_level=service_level, cv_d=cv, var_lt=var_lt, lead_time_days=lead,
        manual_value=_fnum(tog.get("safety_stock_manual")))
    rop = eng.reorder_point(demand_rate, lead, ss)
    if policy_type == "min_max" and max_override is not None:
        oup = float(max_override)
    else:
        oup = eng.order_up_to(rop, demand_rate, review_days)
    # on_cadence=True: in M3 every run counts as a review cadence (periodic_review always
    # gets to fire when below order-up-to). Real cadence scheduling (only fire on the SKU's
    # due review date) is future work.
    triggered, reason_label = eng.trigger(
        policy_type, net=net, rop=rop, min_level=min_override, oup=oup, on_cadence=True)
    recommended, rounded = eng.order_qty(
        triggered, net=net, oup=oup, moq=moq, order_multiple=order_multiple)
    doc = eng.days_of_cover(net, demand_rate)

    lm = last_move.get((pid, wid))
    lm_days = (today - lm).days if lm else None
    disp = eng.disposition(
        on_hand=on_hand, last_movement_days=lm_days, dead_stock_days=dead_days,
        days_of_cover_val=doc, overstock_days=overstock_days)

    demand_adequate = demand_rate > 0 and cv is not None
    supplier_adequate = bool(chosen) and (chosen.get("supplier_confidence") in ("high", "medium"))
    conf = eng.confidence(row["xyz_class"], demand_adequate=demand_adequate,
                          supplier_adequate=supplier_adequate)
    sample_size = int(chosen.get("supplier_sample_size") or 0) if chosen else \
        int(row["sample_days"] or 0)

    return {
        "policy": policy, "chosen": chosen, "alt_choices": alt_choices,
        "demand_rate": demand_rate, "net": net, "on_hand": on_hand, "cv": cv,
        "policy_type": policy_type, "service_level": service_level,
        "safety_days": safety_days, "review_days": review_days,
        "min_override": min_override, "max_override": max_override,
        "lead": lead, "lead_src": lead_src, "moq": moq,
        "order_multiple": order_multiple, "var_lt": var_lt,
        "unit_cost": unit_cost, "currency": currency,
        "ss": ss, "ss_used": ss_used, "ss_fallback": ss_fallback,
        "rop": rop, "oup": oup, "triggered": triggered, "reason_label": reason_label,
        "recommended": recommended, "rounded": rounded, "doc": doc,
        "disposition": disp, "confidence": conf, "sample_size": sample_size,
        "selection": tog["supplier_selection"],
        "overstock": bool(disp and disp["type"] == "overstock"),
        "short": net < rop,
        # M4 cash-ranking factor inputs (list_price read-only from products; committed
        # from the net-position view) — frozen into `inputs` for the cash stage.
        "list_price": _fnum(row.get("list_price")),
        "committed": _fnum(row.get("committed")),
    }


def _emit_cell(run_id: str, row: dict, c: dict,
               transfer_flag: Optional[str]) -> list[ReorderRecommendation]:
    """Turn one computed SKU×warehouse cell into 0..2 persisted recommendations."""
    out: list[ReorderRecommendation] = []
    chosen = c["chosen"]
    disp = c["disposition"]

    # #8: a cell classified for disposition (dead OR overstock) must NOT also emit a buy
    # — buying more of dead/overstocked stock is contradictory. The disposition rec
    # below is the single action for that cell.
    if not disp and c["triggered"] and chosen:
        out.append(_build_rec(run_id, "buy", row, c, warehouse_id=str(row["warehouse_id"]),
                              order_qty=c["recommended"], rounded=c["rounded"]))
    elif not disp and c["triggered"] and not chosen:
        out.append(_build_rec(run_id, "exception", row, c,
                              warehouse_id=str(row["warehouse_id"]),
                              order_qty=None, rounded=None,
                              reason_label="no linked supplier — cannot source this reorder"))

    # disposition (dead / overstock)
    if disp:
        action = "discontinue" if disp["type"] == "dead" else "hold"
        label = _disposition_label(disp["type"], c)
        out.append(_build_rec(run_id, "disposition", row, c,
                              warehouse_id=str(row["warehouse_id"]),
                              order_qty=None, rounded=None,
                              reason_enum=disp["type"], reason_label=label,
                              disposition_action=action, transfer_flag=transfer_flag))
    return out


# ===========================================================================
# network planning (buy_scope=network)
# ===========================================================================

def _plan_network(db: Session, run_id: str, rows: list[dict], policies: list[dict],
                  today: date, last_move: dict, wh_meta: dict) -> list[ReorderRecommendation]:
    recs: list[ReorderRecommendation] = []
    by_product: dict[str, list[dict]] = {}
    for r in rows:
        by_product.setdefault(str(r["product_id"]), []).append(r)

    for pid, prows in by_product.items():
        cands = eng.load_supplier_candidates(db, pid)
        # per-warehouse cells (drive disposition + transfer flags + allocation demand)
        computed = [_compute_cell(db, r, policies, cands, today, last_move) for r in prows]
        flags = _transfer_flags_for(prows, computed)

        # --- aggregate buy on the network ---
        policy = eng.resolve_policy_for_sku(db, pid, None, policies) or {}
        tog = eng.policy_toggles(policy)
        sel = eng.select_supplier(cands, selection=tog["supplier_selection"])
        chosen = sel["chosen"]
        by_id = {c["supplier_id"]: c for c in cands}
        alt_choices = [_supplier_choice(by_id[a["supplier_id"]]) for a in sel["alternatives"]
                       if a["supplier_id"] in by_id]
        lead = float(chosen["lead_time_days"]) if chosen else float(tog["lead_time_default_days"])
        moq = _fnum(chosen.get("moq")) if chosen else None
        order_multiple = _fnum(chosen.get("order_multiple")) if chosen else None
        safety_days = float(policy.get("safety_days") or eng.DEFAULT_SAFETY_DAYS)
        review_days = float(policy.get("review_period_days") or eng.DEFAULT_REVIEW_PERIOD_DAYS)

        wh_inputs = [{"warehouse_id": str(r["warehouse_id"]),
                      "demand_rate": float(r["avg_daily_demand"] or 0.0),
                      "net": float(r["net_position"] or 0.0)} for r in prows]
        agg = eng.aggregate_network(wh_inputs, lead_time_days=lead, safety_days=safety_days,
                                    review_days=review_days, moq=moq,
                                    order_multiple=order_multiple)

        # Gate the network buy on the SAME policy trigger as per-warehouse, computed on
        # the AGGREGATE (net vs agg-ROP / agg-min / agg-OUP). Sizing the buy is NOT a
        # trigger: a cell above ROP but below OUP under a reorder_point policy must NOT
        # buy (matches per-warehouse), and min_max/periodic get their own gate + honest
        # label instead of a hardcoded "net ≤ ROP".
        policy_type = policy.get("policy_type") or "reorder_point"
        min_override = _fnum(policy.get("min_override"))
        max_override = _fnum(policy.get("max_override"))
        agg_net = float(agg["agg_net"])
        if policy_type == "min_max" and max_override is not None:
            target_oup = float(max_override)             # order up to max on the aggregate
        else:
            target_oup = float(agg["order_up_to"])
        # on_cadence=True: every run is a review cadence in M3 (see per-warehouse note).
        triggered, reason_label = eng.trigger(
            policy_type, net=agg_net, rop=float(agg["reorder_point"]),
            min_level=min_override, oup=target_oup, on_cadence=True)
        recommended, rounded = eng.order_qty(
            triggered, net=agg_net, oup=target_oup, moq=moq, order_multiple=order_multiple)

        first = prows[0]
        agg_cell = _network_agg_cell(policy, tog, chosen, alt_choices, agg, lead, moq,
                                     order_multiple, prows, policy_type=policy_type,
                                     min_override=min_override, max_override=max_override,
                                     target_oup=target_oup, triggered=triggered,
                                     reason_label=reason_label, recommended=recommended,
                                     rounded=rounded)
        if triggered and rounded > 0 and chosen:
            allocation_map = eng.allocate(rounded, agg["warehouses"])
            allocation = _allocation_lines(allocation_map, wh_meta)
            recs.append(_build_rec(run_id, "buy", first, agg_cell, warehouse_id=None,
                                   order_qty=recommended, rounded=rounded,
                                   allocation=allocation))
        elif triggered and rounded > 0 and not chosen:
            recs.append(_build_rec(run_id, "exception", first, agg_cell, warehouse_id=None,
                                   order_qty=None, rounded=None,
                                   reason_label="no linked supplier — cannot source this network reorder"))

        # --- per-warehouse disposition recs (dead/overstock) ---
        for r, cell in zip(prows, computed):
            disp = cell["disposition"]
            if disp:
                action = "discontinue" if disp["type"] == "dead" else "hold"
                label = _disposition_label(disp["type"], cell)
                recs.append(_build_rec(run_id, "disposition", r, cell,
                                       warehouse_id=str(r["warehouse_id"]),
                                       order_qty=None, rounded=None,
                                       reason_enum=disp["type"], reason_label=label,
                                       disposition_action=action,
                                       transfer_flag=flags.get(str(r["warehouse_id"]))))
    return recs


def _network_agg_cell(policy, tog, chosen, alt_choices, agg, lead, moq, order_multiple,
                      prows, *, policy_type: str, min_override: Optional[float],
                      max_override: Optional[float], target_oup: float, triggered: bool,
                      reason_label: Optional[str], recommended: float,
                      rounded: float) -> dict:
    """Assemble the frozen-cell dict for a network aggregate buy (fixed_days SS).

    The trigger / order-up-to target / qty are computed by the caller on the aggregate
    against the RESOLVED policy_type, so ``reason_label`` and ``policy_type`` here are
    honest (no hardcoded "net ≤ ROP").
    """
    agg_demand = agg["agg_demand"]
    # #9: match the per-warehouse supplier-adequacy definition — a chosen supplier only
    # counts as adequate when its measured confidence is high|medium.
    supplier_adequate = bool(chosen) and (chosen.get("supplier_confidence") in ("high", "medium"))
    return {
        "policy": policy, "chosen": chosen, "alt_choices": alt_choices,
        "demand_rate": agg_demand, "net": agg["agg_net"], "on_hand": None, "cv": None,
        "policy_type": policy_type,
        "service_level": float(policy.get("service_level") or eng.DEFAULT_SERVICE_LEVEL),
        "safety_days": float(policy.get("safety_days") or eng.DEFAULT_SAFETY_DAYS),
        "review_days": float(policy.get("review_period_days") or eng.DEFAULT_REVIEW_PERIOD_DAYS),
        "min_override": min_override, "max_override": max_override,
        "lead": lead, "lead_src": chosen["lead_time_source"] if chosen else "default",
        "moq": moq, "order_multiple": order_multiple, "var_lt": None,
        "unit_cost": _fnum(chosen.get("unit_cost")) if chosen else None,
        "currency": chosen.get("currency") if chosen else None,
        "ss": agg["safety_stock"], "ss_used": "fixed_days", "ss_fallback": None,
        "rop": agg["reorder_point"], "oup": target_oup, "triggered": triggered,
        "reason_label": reason_label,
        "recommended": recommended, "rounded": rounded,
        "doc": eng.days_of_cover(agg["agg_net"], agg_demand),
        "disposition": None,
        "confidence": eng.confidence(prows[0]["xyz_class"], demand_adequate=agg_demand > 0,
                                     supplier_adequate=supplier_adequate),
        "sample_size": int(chosen.get("supplier_sample_size") or 0) if chosen else 0,
        "selection": tog["supplier_selection"],
        # M4 cash-ranking factor inputs on the aggregate: list_price is per-product
        # (same across warehouses); committed is summed across the network's cells.
        "list_price": _fnum(prows[0].get("list_price")),
        "committed": _fnum(sum(float(r.get("committed") or 0.0) for r in prows)),
    }


def _allocation_lines(allocation: dict, wh_meta: dict) -> list[dict]:
    """Freeze the engine's {warehouse_id: qty} split as [{warehouse_id, code, name, qty}]
    so the read endpoint never re-resolves (and never leaks a bare UUID)."""
    out = []
    for wid, qty in allocation.items():
        code, name = wh_meta.get(wid, (None, None))
        out.append({"warehouse_id": wid, "warehouse_code": code,
                    "warehouse_name": name, "qty": qty})
    return out


# ===========================================================================
# recommendation builder (freezes inputs)
# ===========================================================================

def _build_rec(run_id: str, rec_type: str, row: dict, c: dict, *,
               warehouse_id: Optional[str], order_qty: Optional[float],
               rounded: Optional[float], allocation: Optional[list] = None,
               reason_enum: Optional[str] = None, reason_label: Optional[str] = None,
               disposition_action: Optional[str] = None,
               transfer_flag: Optional[str] = None) -> ReorderRecommendation:
    chosen = c["chosen"]
    reason = reason_enum or _reason_enum(c["policy_type"])
    label = reason_label if reason_label is not None else c.get("reason_label")
    unit_cost = c.get("unit_cost")
    cash_impact = None
    if rec_type == "buy" and rounded is not None and unit_cost is not None:
        cash_impact = float(rounded) * float(unit_cost)

    inputs = {
        "reason": reason,
        "reason_label": label,
        "min_qty": c.get("min_override"),
        "max_qty": c.get("max_override"),
        "order_up_to": _r(c.get("oup")),
        "safety_stock": _r(c.get("ss")),
        "safety_stock_method": c.get("ss_used"),
        "safety_stock_fallback": c.get("ss_fallback"),
        "lead_time_days": _r(c.get("lead")),
        "lead_time_source": c.get("lead_src"),
        "policy_ref": (str((c.get("policy") or {}).get("id"))
                       if (c.get("policy") or {}).get("id") is not None else None),
        "policy_type": c.get("policy_type"),
        "service_level": c.get("service_level"),
        "safety_days": c.get("safety_days"),
        "review_days": c.get("review_days"),
        "moq": c.get("moq"),
        "order_multiple": c.get("order_multiple"),
        "cv_d": c.get("cv"),
        "var_lt": c.get("var_lt"),
        "demand_rate": _r(c.get("demand_rate")),
        "net": _r(c.get("net")),
        # M4 cash-ranking factor inputs (frozen for the cash stage + explainability).
        "list_price": c.get("list_price"),
        "committed": c.get("committed"),
        "on_cadence": True,
        "selection": c.get("selection"),
        "sample_size": c.get("sample_size"),
        "supplier": _supplier_choice(chosen) if chosen else None,
        "alternatives": c.get("alt_choices") or [],
        "disposition_action": disposition_action,
        "transfer_flag": transfer_flag,
        "is_exception": rec_type == "exception",
        # frozen display fields (no re-resolution / UUID leak at read time)
        "sku": row["product_code"],
        "product_name": row["product_name"],
        "warehouse_code": row["warehouse_code"] if warehouse_id else None,
        "warehouse_name": row["warehouse_name"] if warehouse_id else None,
        "abc_class": row["abc_class"],
        "xyz_class": row["xyz_class"],
        "category_code": row.get("category_code"),
    }
    return ReorderRecommendation(
        id=str(uuid.uuid4()),
        run_id=run_id,
        rec_type=rec_type,
        product_id=str(row["product_id"]),
        warehouse_id=warehouse_id,
        supplier_id=(chosen["supplier_id"] if chosen else None),
        net_position=_r(c.get("net")),
        reorder_point=_r(c.get("rop")),
        forecast_daily_demand=_r(c.get("demand_rate")),
        days_of_cover=_r(c.get("doc")),
        recommended_qty=_r(order_qty),
        rounded_qty=_r(rounded),
        unit_cost=unit_cost,
        cash_impact=cash_impact,
        currency=c.get("currency"),
        confidence_band=c.get("confidence"),
        triggered_reason=(label[:100] if label else None),
        allocation=allocation,
        inputs=inputs,
        status="proposed",
        source_system="scm",
        source_ref=_SEED,
    )


# ===========================================================================
# helpers
# ===========================================================================

def _supplier_choice(cand: Optional[dict]) -> Optional[dict]:
    if not cand:
        return None
    return {
        "supplier_code": cand.get("supplier_code"),
        "supplier_name": cand.get("supplier_name"),
        "unit_cost": _fnum(cand.get("unit_cost")),
        "lead_time_days": _fnum(cand.get("lead_time_days")),
        "composite_score": _fnum(cand.get("composite_score")),
        "is_primary": bool(cand.get("is_primary")),
        # M5-prep — scorecard detail for the "why this supplier" popover (all already
        # on the candidate from the M2 supplier_performance join). Frozen at run time.
        "sample_size": (int(cand["supplier_sample_size"])
                        if cand.get("supplier_sample_size") is not None else None),
        "confidence": cand.get("supplier_confidence"),
        "lead_time_source": cand.get("lead_time_source"),
        "lead_time_variance": _fnum(cand.get("lead_time_variance")),
        "moq": _fnum(cand.get("moq")),
        "order_multiple": _fnum(cand.get("order_multiple")),
    }


def _transfer_flags_for(prows: list[dict], computed: list[dict]) -> dict[str, str]:
    """Advisory transfer flags per SKU across its warehouses (overstock-here +
    short-there). Returns {warehouse_id: message} keyed to the OVERSTOCK warehouse."""
    sku = prows[0]["product_code"]
    whs = [{"warehouse_id": str(r["warehouse_id"]),
            "warehouse_code": r["warehouse_code"],
            "overstock": computed[i]["overstock"],
            "short": computed[i]["short"]} for i, r in enumerate(prows)]
    flags = eng.transfer_flags(sku, whs)
    out: dict[str, str] = {}
    for f, w in [(f, w) for f in flags for w in whs
                 if w["warehouse_code"] == f["from_warehouse"]]:
        out[w["warehouse_id"]] = f["message"]
    return out


def _disposition_label(kind: str, c: dict) -> str:
    if kind == "dead":
        return "dead stock: no movement in the dead-stock window"
    doc = c.get("doc")
    return f"overstock: {doc:g} days of cover exceeds the ceiling" if doc is not None \
        else "overstock: days of cover exceeds the ceiling"


def _reason_enum(policy_type: Optional[str]) -> str:
    if policy_type in ("reorder_point", "periodic_review", "min_max"):
        return policy_type
    return "reorder_point"


# ===========================================================================
# M4 cash stage — freeze rank_score + rank on the buy recommendations
# ===========================================================================

def load_cash_weights(db: Session) -> dict:
    """Weights from the single active ``scm.cash_ranking_policy`` row; falls back to
    the seeded defaults when none is present (fresh install pre-migration seed)."""
    row = db.execute(text(
        "SELECT weight_urgency, weight_margin, weight_abc, weight_priority, "
        "       weight_committed "
        "FROM scm.cash_ranking_policy WHERE is_active = true "
        "ORDER BY updated_at DESC NULLS LAST, created_at DESC LIMIT 1"
    )).mappings().first()
    if not row:
        return dict(cash_ranking.DEFAULT_WEIGHTS)
    return {
        "urgency": _wf(row["weight_urgency"], "urgency"),
        "margin": _wf(row["weight_margin"], "margin"),
        "abc": _wf(row["weight_abc"], "abc"),
        "priority": _wf(row["weight_priority"], "priority"),
        "committed": _wf(row["weight_committed"], "committed"),
    }


def _wf(v, key: str) -> float:
    return float(v) if v is not None else float(cash_ranking.DEFAULT_WEIGHTS[key])


def _apply_cash_stage(db: Session, recs: list[ReorderRecommendation]) -> None:
    """Compute + FREEZE the cash-ranking fields on the run's BUY recs (M4-D1/D14):
    each buy's graceful-degrade ``rank_score`` + its factor vector + days-to-stockout
    (into ``inputs``), then a dense ``rank`` by rank_score desc (tiebreak cash_impact
    then product_code). Non-buy recs are untouched. Funded/deferred is NOT decided
    here — it is applied live at view-time against a budget (M4-D2/D3)."""
    weights = load_cash_weights(db)
    buys = [r for r in recs if r.rec_type == "buy"]
    for r in buys:
        inp = dict(r.inputs or {})
        factors = cash_ranking.build_factors(
            weights,
            days_of_cover=_fnum(r.days_of_cover),
            net_position=_fnum(r.net_position),
            list_price=inp.get("list_price"),
            unit_cost=_fnum(r.unit_cost),
            abc_class=inp.get("abc_class"),
            committed=inp.get("committed"),
            forecast_daily_demand=_fnum(r.forecast_daily_demand),
            lead_time_days=inp.get("lead_time_days"),
        )
        r.rank_score = round(cash_ranking.rank_score(factors), 6)
        inp["rank_factors"] = [f.as_dict() for f in factors]
        inp["days_to_stockout"] = cash_ranking.days_to_stockout(
            _fnum(r.net_position), _fnum(r.forecast_daily_demand), _fnum(r.days_of_cover))
        r.inputs = inp

    ordered = sorted(buys, key=lambda r: cash_ranking.rank_sort_key(
        float(r.rank_score or 0.0), _fnum(r.cash_impact), (r.inputs or {}).get("sku")))
    for i, r in enumerate(ordered, start=1):
        r.rank = i


# ===========================================================================
# M4 funding allocation — greedy-by-rank over a run's buys (view-time + persist)
# ===========================================================================

def _load_run_buys(db: Session, run_id: str) -> list[cash_ranking.Buy]:
    """The run's BUY recs as allocator inputs (id, frozen rank, cash_impact)."""
    rows = db.execute(text(
        "SELECT id, rank, cash_impact FROM scm.reorder_recommendation "
        "WHERE run_id = :rid AND rec_type = 'buy'"
    ), {"rid": run_id}).mappings().all()
    return [cash_ranking.Buy(
        id=str(r["id"]),
        rank=int(r["rank"]) if r["rank"] is not None else None,
        cash_impact=float(r["cash_impact"]) if r["cash_impact"] is not None else None,
    ) for r in rows]


def allocate_run_budget(db: Session, run_id: str,
                        budget: Optional[float]) -> cash_ranking.AllocationResult:
    """Greedy funding over the run's buys for ``budget`` — VIEW-TIME, no persistence."""
    return cash_ranking.allocate_funding(_load_run_buys(db, run_id), budget)


def apply_run_budget(db: Session, run_id: str, budget: float) -> dict:
    """PERSIST the funding split for ``budget``: stamps ``funding_status`` on every buy
    rec + ``budget_amount`` on the run (so a shared run shows one funded set). Returns
    the roll-up counts + funded/deferred cash."""
    result = cash_ranking.allocate_funding(_load_run_buys(db, run_id), budget)
    for rec_id, status in result.status_by_id.items():
        db.execute(text(
            "UPDATE scm.reorder_recommendation SET funding_status = :s WHERE id = :id"
        ), {"s": status, "id": rec_id})
    db.execute(text(
        "UPDATE scm.reorder_run SET budget_amount = :b WHERE id = :rid"
    ), {"b": budget, "rid": run_id})
    db.commit()
    return {
        "run_id": run_id,
        "budget": float(budget),
        "funded_count": result.funded_count,
        "deferred_count": result.deferred_count,
        "needs_cost_count": result.needs_cost_count,
        "funded_cash": result.funded_cash,
        "deferred_cash": result.deferred_cash,
    }


def _summarise(recs: list[ReorderRecommendation]) -> dict:
    buy = sum(1 for r in recs if r.rec_type == "buy")
    disposition = sum(1 for r in recs if r.rec_type == "disposition")
    exceptions = sum(1 for r in recs if r.rec_type == "exception")
    total_cash = float(sum(float(r.cash_impact or 0.0) for r in recs if r.rec_type == "buy"))
    return {
        "buy": buy,
        "disposition": disposition,
        "exceptions": exceptions,
        "total_cash_impact": round(total_cash, 2),
        "recommendation_count": len(recs),
    }


def _fnum(v) -> Optional[float]:
    return float(v) if v is not None else None


def _r(v) -> Optional[float]:
    return round(float(v), 6) if v is not None else None
