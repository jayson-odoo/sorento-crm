"""SCM M3 reorder RUN JOB - drives the deterministic engine over a background run.

The pure maths + resolver live in ``reorder_engine`` (golden-tested). This module is
the ORCHESTRATION layer: it enumerates the planning SKUs in the selected warehouses,
calls the engine per SKU×warehouse (or aggregated when ``buy_scope='network'``), and
PERSISTS one ``scm.reorder_recommendation`` per emitted rec with its FROZEN inputs
(AC-M3.11 - reproducible without stat versioning), plus a ``scm.reorder_run`` log with
status transitions + counts.

Flow:
  * ``create_run`` inserts a ``running`` run (scope snapshot, started_at) and enqueues
    the RQ ``run_reorder(run_id)`` task on the ``imports`` queue (drained by the worker).
  * ``run_reorder`` (the worker task body) loads the run, evaluates all planning SKUs,
    writes the recommendations, and flips the run to ``completed`` (+ run-log counts) or
    ``failed`` (+ error_text) - it NEVER crashes the worker.
  * A re-run always creates a NEW run_id - runs are immutable history.

Two recommendation types (M3-D5):
  * ``buy`` - a triggered reorder (per policy trigger); ``disposition`` - dead/overstock.
  * A no-supplier SKU that WOULD trigger a buy emits an ``exception`` rec (never silently
    skipped - AC-M3.6).
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.product import Product
from app.models.scm import ReorderRecommendation, ReorderRun
from app.services.company_scope_sql import company_sql_predicate
from app.services.error_handler import AppException
from app.services.scm import cash_ranking
from app.services.scm import demand
from app.services.scm import reorder_engine as eng
from app.services.scm import reorder_level_service as rl_service
from app.services.scm.money import (
    BASE_CURRENCY,
    Rate,
    load_rates,
    normalize_currency,
    to_base,
)
from app.services.scm import plan_grain
from app.services.scm.reorder_policy import (
    DEFAULT_DEAD_STOCK_DAYS,
    DEFAULT_OVERSTOCK_DAYS,
)

log = logging.getLogger(__name__)

_SEED = "run"
_STAGES = ("resolving_policies", "computing_reorder_points",
           "selecting_suppliers", "writing_recommendations")


# ===========================================================================
# create_run - insert the run + enqueue the job
# ===========================================================================

def create_run(db: Session, warehouse_codes: Optional[list[str]],
               buy_scope: str = "warehouse",
               budget_id: Optional[str] = None, actor: Optional[str] = None,
               enqueue: bool = True, include_market: bool = False,
               product_codes: Optional[list[str]] = None,
               plan_horizon_date: Optional[date] = None) -> dict:
    """Insert a ``running`` ``scm.reorder_run`` (scope snapshot + started_at) and
    enqueue the RQ ``run_reorder`` task. Returns ``{run_id, status, buy_scope, stage}``.

    ``product_codes`` empty/None => plan every product; a narrowed run stores the resolved
    ids so the RQ worker, which receives only a run id, can honour the scope. A scope that
    was asked for but resolved to nothing is stored as an EMPTY list rather than NULL, so a
    mistyped code plans nothing instead of quietly widening to the whole catalogue.

    ``warehouse_codes`` empty/None => plan every active warehouse. A re-run always
    creates a NEW run_id (runs are immutable). ``enqueue=False`` skips the RQ enqueue
    (tests call ``run_reorder`` synchronously).

    ``buy_scope`` is no longer a manual-plan input (M8-D5) - it defaults to
    ``warehouse`` (per-warehouse planning; each buy is tied to a real warehouse, not
    an aggregated ``Network`` row). The HTTP request schema dropped it. Direct service
    callers may still pass ``network`` explicitly.

    ``plan_horizon_date`` (captain, 20 Aug) is the optional "Plan until" cutoff: ``None``
    (the default) plans against every open SO line regardless of when it is needed, exactly
    as before. When set, it is stamped on the run and read back by ``_execute_run_scoped`` -
    a per-RUN choice, never a live policy, so a past run's plan cannot move under a later
    edit of it (there is no live setting to edit; each run states its own).

    The run STAMPS the admin plan-grain policy (front-planning plan 5.1) and the contract
    version here, at creation, and never again: the grain a screen shows for a run is its
    stamp rather than the live setting, so changing the policy affects only later runs and
    an existing run's decisions stay valid where they were made.
    """
    buy_scope = buy_scope if buy_scope in ("network", "warehouse") else "warehouse"
    warehouse_ids = _resolve_warehouse_ids(db, warehouse_codes)
    product_ids = _resolve_product_ids(db, product_codes)
    run_id = str(uuid.uuid4())
    now = datetime.utcnow()
    db.add(ReorderRun(
        id=run_id,
        created_by=actor,
        status="running",
        warehouse_ids=warehouse_ids,
        product_ids=product_ids,
        buy_scope=buy_scope,
        budget_id=budget_id or None,
        include_market=bool(include_market),
        plan_horizon_date=plan_horizon_date,
        policy_snapshot_ref=f"policies@{now.isoformat()}",
        started_at=now,
        run_log={"stage": _STAGES[0]},
        source_system="scm",
        source_ref=_SEED,
        decision_grain=plan_grain.resolve_plan_grain(db),
        front_planning_contract_version=plan_grain.FRONT_PLANNING_CONTRACT_VERSION,
    ))
    db.commit()

    if enqueue:
        try:
            from app.services.queue_service import enqueue_job
            from app.tasks.reorder_tasks import run_reorder_job
            enqueue_job(run_reorder_job, run_id, queue_name="imports")
        except Exception:  # noqa: BLE001 - the run row exists; a broken broker must
            # not 500 the request. The run can be driven manually / by the next tick.
            log.exception("create_run: failed to enqueue run_reorder for %s", run_id)

    return {"run_id": run_id, "status": "running", "buy_scope": buy_scope,
            "stage": _STAGES[0]}


def _resolve_product_ids(
    db: Session, product_codes: Optional[list[str]]
) -> Optional[list[str]]:
    """Human product codes to ids, or None when no scope was asked for.

    Returns None for "no scope" and a list for "this scope", INCLUDING the empty list when
    nothing resolved. Collapsing those two would make a typo indistinguishable from an
    unnarrowed run, and the unnarrowed reading is the dangerous one: it plans everything and
    looks intentional.
    """
    if not product_codes:
        return None
    # ORM, not raw SQL: the multi-company isolation filter runs on ORM execution only, and
    # each company carries its own copy of the catalogue - 11,390 product codes exist twice
    # in the real database. A raw `SELECT ... FROM products WHERE product_code = ANY(...)`
    # therefore puts ANOTHER company's product into this run's scope. It is inert only for
    # as long as one company owns every warehouse, which is not a property to depend on.
    rows = (
        db.query(Product.id)
        .filter(Product.product_code.in_([str(c) for c in product_codes]))
        .all()
    )
    return [str(r[0]) for r in rows]


def _resolve_warehouse_ids(db: Session, warehouse_codes: Optional[list[str]]) -> list[str]:
    """Location codes to ids, or every active warehouse when no scope was asked for.

    Returns an EMPTY list when codes were given and none resolved - a mistyped location
    must plan nothing rather than the whole network (see ``_planning_rows``).

    ORM for the same isolation reason as the product resolver: an unscoped run must list
    THIS company's warehouses, not every company's.
    """
    if warehouse_codes:
        rows = (
            db.query(Warehouse.id)
            .filter(Warehouse.warehouse_code.in_([str(c) for c in warehouse_codes]))
            .all()
        )
        return [str(r[0]) for r in rows]
    rows = db.query(Warehouse.id).filter(Warehouse.is_active.is_(True)).all()
    return [str(r[0]) for r in rows]


# ===========================================================================
# today's plan - the run the reorder page opens to (M8-D3/D4)
# ===========================================================================

_KL_TZ = ZoneInfo("Asia/Kuala_Lumpur")


def _run_in_progress(db: Session, today: date) -> bool:
    """True when a run started today is still queued or running.

    Separate from the run being shown so the page can say "a plan is being built" WHILE it
    keeps showing the last one. The two facts are independent: the newest completed run and
    whether a newer one is on its way.
    """
    co, co_params = company_sql_predicate(db, "company_id", param_prefix="cip")
    co_clause = f"AND {co}" if co else ""
    row = db.execute(text(f"""
        SELECT 1
        FROM scm.reorder_run
        WHERE status IN ('queued', 'running')
          AND ((started_at AT TIME ZONE 'utc') AT TIME ZONE 'Asia/Kuala_Lumpur')::date = :today
          {co_clause}
        LIMIT 1
    """), {"today": today, **co_params}).first()
    return row is not None


def today_or_latest_run(db: Session, today: Optional[date] = None) -> Optional[dict]:
    """Pick the run the reorder page opens to WITHOUT knowing an id (M8-D3/D4).

    Returns ``{"row": <run mapping>, "is_today": bool}`` where the row is the
    most-recent NON-FAILED run STARTED today (Malaysia wall-clock) - the day's
    scheduled snapshot; else the most-recent COMPLETED run overall - the last
    available snapshot fallback when today's run has not fired (or failed). Returns
    ``None`` only when no run exists at all (fresh install → FE shows the empty page +
    Manual plan). ``today`` overrides the KL calendar date (tests only).

    ``started_at`` is stored naive-UTC; its KL calendar date is derived in SQL so the
    06:00-KL scheduled run counts as "today" even though its UTC date is the prior day.
    """
    if today is None:
        today = datetime.now(_KL_TZ).date()
    cols = ("id, status, buy_scope, warehouse_ids, started_at, finished_at, run_log, "
            "decision_grain, front_planning_contract_version, plan_horizon_date")
    # Company-scoped by hand: raw SQL, so the ORM isolation filter never sees it. Without the
    # predicate the reorder page opens on whichever company ran most recently, which is
    # another company's plan wearing this company's chrome.
    co, co_params = company_sql_predicate(db, "company_id", param_prefix="ctr")
    co_clause = f"AND {co}" if co else ""
    # COMPLETED, not merely "not failed". A run that is still going has no recommendations, so
    # opening the page on it renders an empty plan and the words "No plan yet" while a perfectly
    # good snapshot sits behind it. That is what a queued job with no worker looks like from the
    # planner's chair: they press Plan now, the page empties, and yesterday's plan is gone.
    row = db.execute(text(f"""
        SELECT {cols}
        FROM scm.reorder_run
        WHERE status = 'completed'
          AND ((started_at AT TIME ZONE 'utc') AT TIME ZONE 'Asia/Kuala_Lumpur')::date = :today
          {co_clause}
        ORDER BY started_at DESC NULLS LAST, created_at DESC
        LIMIT 1
    """), {"today": today, **co_params}).mappings().first()
    if row is not None:
        return {"row": dict(row), "is_today": True, "in_progress": _run_in_progress(db, today)}
    # Same ordering key as dashboard_service._latest_completed_run_id so both surfaces
    # reference the SAME latest-completed run (the dashboard's ROP source and this page).
    row = db.execute(text(f"""
        SELECT {cols}
        FROM scm.reorder_run
        WHERE status = 'completed'
          {co_clause}
        ORDER BY COALESCE(finished_at, created_at) DESC, created_at DESC
        LIMIT 1
    """), co_params).mappings().first()
    if row is None:
        # Nothing has ever completed. If a first plan is being built RIGHT NOW, that is a
        # better answer than "No plan yet", which reads as "nothing is happening" and invites
        # the user to start a second one. Only reached when there is no completed run to
        # prefer, so an unfinished run still never hides a usable snapshot.
        row = db.execute(text(f"""
            SELECT {cols}
            FROM scm.reorder_run
            WHERE status IN ('queued', 'running')
              AND ((started_at AT TIME ZONE 'utc') AT TIME ZONE 'Asia/Kuala_Lumpur')::date = :today
              {co_clause}
            ORDER BY started_at DESC NULLS LAST, created_at DESC
            LIMIT 1
        """), {"today": today, **co_params}).mappings().first()
        if row is None:
            return None
        return {"row": dict(row), "is_today": True, "in_progress": True}
    started = row["started_at"]
    is_today = bool(
        started is not None
        and started.replace(tzinfo=ZoneInfo("UTC")).astimezone(_KL_TZ).date() == today
    )
    return {"row": dict(row), "is_today": is_today, "in_progress": _run_in_progress(db, today)}


def assert_run_visible(db: Session, run_id: str) -> None:
    """404 unless ``run_id`` names a run the caller's company owns.

    THE gate for every route that takes a run id from the caller. Downstream reads of a
    run's children (recommendations, overrides, order-summary rows, the explainer's
    aggregates) are keyed by that run id and are raw SQL, so none of them are reached by
    the ORM isolation filter. Rather than repeat a predicate across ~30 of those reads,
    the id is validated ONCE at the entry point and the children inherit the decision.

    404 rather than 403: a run belonging to another company should not be distinguishable
    from one that does not exist.
    """
    co, co_params = company_sql_predicate(db, "company_id", param_prefix="crv")
    found = db.execute(
        text(f"SELECT 1 FROM scm.reorder_run WHERE id = :id AND {co or 'true'}"),
        {"id": run_id, **co_params},
    ).first()
    if not found:
        raise AppException(404, "Run not found")


# ===========================================================================
# run_reorder - the worker task body
# ===========================================================================

def run_reorder(run_id: str, db: Optional[Session] = None) -> dict:
    """Worker entry: evaluate all planning SKUs for ``run_id`` and persist the
    recommendations. Creates its own session when called from the worker; tests pass
    ``db`` to run inside their rolled-back savepoint. Never raises - a failure is
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


def _adopt_run_company_scope(db: Session, run: ReorderRun) -> None:
    """Re-establish the company scope from the run row before reading anything.

    The RQ work-horse receives a run id and NOTHING else: no request, no bearer token, and
    therefore no company scope. An UNSET scope FAILS CLOSED, so a worker that relied on the
    ambient scope would read no warehouses, no products and no positions, and the daily plan
    would silently complete with zero recommendations - the worst failure shape available,
    because an empty plan looks like a quiet week.

    So the scope is a property of the RUN, adopted here. That also makes it auditable and makes
    a past run reproducible under the company it was actually planned for.

    A run with no company (a legacy row from before the column existed) is left alone rather
    than defaulted: forcing a scope onto it would assert an ownership the row does not record.
    Its reads then run under whatever scope the session already has, which for the worker is
    UNSET and yields nothing - visibly empty rather than wrong.
    """
    from app.models.base import set_company_scope

    company_id = getattr(run, "company_id", None)
    if company_id:
        set_company_scope(db, frozenset({str(company_id)}))
    else:
        log.warning(
            "run_reorder %s has no company; planning under the ambient scope", run.id
        )


def _execute_run(db: Session, run_id: str) -> dict:
    # Read the run under NO scope: the worker has none, and the run row is the thing that
    # tells us which company to adopt, so it cannot itself sit behind that filter.
    from app.models.base import get_company_scope, set_company_scope

    caller_scope = get_company_scope(db)
    set_company_scope(db, None)
    run = db.get(ReorderRun, run_id)
    if run is None:
        set_company_scope(db, caller_scope)
        raise ValueError(f"reorder_run {run_id} not found")
    _adopt_run_company_scope(db, run)
    try:
        return _execute_run_scoped(db, run, caller_scope)
    finally:
        # Restore what the caller had. A synchronous caller (a test, a script) did not ask to
        # have its scope changed underneath it, and leaving the run's company behind would
        # silently re-scope everything it does next.
        set_company_scope(db, caller_scope)


def _execute_run_scoped(db: Session, run: ReorderRun, _caller_scope) -> dict:
    run_id = str(run.id)
    started = run.started_at or datetime.utcnow()

    # The heavy evaluation runs inside a SAVEPOINT: on failure we roll back ONLY the
    # planning work (partial recommendations, seeded policy) and keep the already-
    # committed run row so we can still stamp it 'failed' + error_text. The worker
    # never sees an exception - a broken run is recorded, not crashed.
    sp = db.begin_nested()
    try:
        eng.ensure_reorder_policy_defaults(db)
        policies = eng.load_policies(db)
        today = date.today()

        rows = _planning_rows(db, run.warehouse_ids, run.product_ids,
                             horizon=run.plan_horizon_date)
        # Confirmed Reserve / Borrow leaves the Retail free-supply pool before anything is
        # netted against it (AC-F07); stamped on the row so every planning path sees it.
        # Horizoned on the SAME rule as the demand it offsets (AC-F-horizon): a reserve
        # claimed against a project line beyond "Plan until" must leave the pool together
        # with that line's own demand, or it keeps subtracting cover nobody asked for.
        _apply_project_supply_reduction(db, rows, horizon=run.plan_horizon_date)
        last_move = _last_movement_map(db, [r["product_id"] for r in rows], run.warehouse_ids)
        # L5 - how long the stock sitting there has been sitting. Only ever consulted for a
        # SKU that has never moved, where until now there was no evidence at all.
        last_buy = _last_purchase_map(db, [r["product_id"] for r in rows])
        # S10: the levels the buyer owns. Read once for the whole run; a policy that does
        # not select the reorder_level basis simply never consults them.
        levels = rl_service.get_levels(
            db, sorted({r["product_id"] for r in rows}), run.warehouse_ids)
        # What we last paid, split by segment where the destination is known.
        last_cost = _last_purchase_cost_map(db, [r["product_id"] for r in rows])
        wh_meta = {str(r["warehouse_id"]): (r["warehouse_code"], r["warehouse_name"]) for r in rows}

        # One read for the whole run. Every supplier price is restated in the base
        # currency against THIS map, so a rate edited mid-run cannot make two SKUs in the
        # same plan disagree about what a dollar is worth.
        rates = load_rates(db)

        if run.buy_scope == "network":
            recs = _plan_network(db, run_id, rows, policies, today, last_move, wh_meta,
                                 last_buy=last_buy, rates=rates, levels=levels,
                                 last_cost=last_cost)
        else:
            recs = _plan_per_warehouse(db, run_id, rows, policies, today, last_move,
                                       wh_meta, last_buy=last_buy, rates=rates,
                                       levels=levels, last_cost=last_cost,
                                       horizon=run.plan_horizon_date)

        # M4 cash stage - compute + FREEZE each buy's rank_score / rank / rank_factors
        # (funded/deferred is computed live at view-time against a budget, not here).
        # M7: opt-in market-trend priority factor (per-run flag).
        _apply_cash_stage(db, recs, include_market=bool(run.include_market))

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

        # Freeze the Summary Order Report for this run (S3b, AC-C2.9). AFTER the commit and
        # BEST-EFFORT: the plan itself is complete and durable at this point, and a failure
        # here must not flip a finished run to `failed` - the retry would re-plan work that
        # already succeeded. The report writer is idempotent, so it can be re-run for the
        # same run id to fill the gap.
        try:
            from app.services.scm import summary_order_service
            frozen = summary_order_service.write_rows(db, run_id)
            log.info("run_reorder %s: froze %s order-summary rows", run_id, frozen)
        except Exception:  # noqa: BLE001
            log.exception("run_reorder %s: failed to freeze the order summary", run_id)

        # S13f, same rules as the summary: AFTER the commit and BEST-EFFORT. Writes only
        # `suggested_level` + `suggestion_basis` for the pairs this run planned; the stored
        # `level` belongs to the buyer and is never touched here. Idempotent, so a missed
        # refresh is filled by the next run rather than failing this one.
        try:
            from app.services.scm import level_suggestion_service
            n = level_suggestion_service.refresh_for_run(db, run_id)
            log.info("run_reorder %s: refreshed %s level suggestions", run_id, n)
        except Exception:  # noqa: BLE001
            log.exception("run_reorder %s: failed to refresh level suggestions", run_id)

        return {"run_id": run_id, "status": "completed", **counts}
    except Exception as exc:  # noqa: BLE001 - record, never crash the worker
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

def _planning_rows(db: Session, warehouse_ids: Optional[list[str]],
                   product_ids: Optional[list[str]] = None,
                   horizon: Optional[date] = None) -> list[dict]:
    """Active + ongoing SKU×warehouse rows with a net position / demand in the selected
    warehouses (reuses the dashboard focus predicate).

    BOTH scopes use the same three-state convention, and the two must not drift or empty
    means one thing for products and the opposite for locations. ``None`` => no scope was
    asked for, so plan everything (the daily run). A LIST narrows to it. An EMPTY list
    narrows to NOTHING: a scope was asked for and none of it resolved, so the honest answer
    is an empty plan the operator can see rather than the whole catalogue dressed up as
    their request. Reading `[]` as "no filter" is what turned one mistyped location code
    into an 11,585-row plan of every warehouse.

    ``committed`` comes from ``demand.horizon_committed_select_sql`` on EVERY run, not
    from ``np.committed`` off ``scm.net_position_v``. That branch is gone (the handshake,
    `PLAN-scm-oi-handshake.md` section 3): a plan may only buy against an order-inquiry
    row purchasing has ACKNOWLEDGED, and the view goes on counting an awaiting one because
    it is still owed to the customer. One SELECT holds both halves of the rule, rather
    than a branch here that could answer differently on two runs of one plan.

    ``horizon`` is the run's own "Plan until" date (captain, 20 Aug) and rides into that
    same SELECT: when set, demand with a stated required/delivery date AFTER it is
    excluded from ``committed`` (the horizon SIDE of the equation; unscheduled demand
    carrying no date is always still counted). ``None`` - the daily run, and any manual
    run that leaves the field empty - binds NULL, and every date comparison in the SELECT
    short-circuits true, so an unhorizoned run nets exactly as it did except for the
    acknowledgement rule. On-order is never touched either way; only which demand rows
    qualify.

    ``quantity_on_hand`` (and therefore ``net_position``, built from it below) is NOT the
    view's own figure any more: it is recomputed to DEALER-only on every row, horizon or
    not (captain, 20 Aug - "the on hand need to consider pool quantity only ... project on
    hand quantity is not really an actual usable quantity"). See the comment beside
    ``on_hand_expr`` below for the test and the coupling with ``net_position``.

    **Company-scoped by hand**, because this is raw SQL and the isolation filter runs on ORM
    execution ONLY. The predicate goes on the JOINED `warehouses` and `products` rather than on
    a denormalised column: company is a property of the location, and a second copy of that
    fact on the view row would be free to disagree with it. Both sides are filtered - the
    location because another company's stock counted here would ADD COVER and silently suppress
    a purchase, and the product because 11,390 codes exist in both companies, so the same code
    resolves to two rows.
    """
    where = ["p.is_active = true", "p.is_discontinued = false"]
    params: dict[str, Any] = {}
    wh_scope, wh_params = company_sql_predicate(db, "w.company_id", param_prefix="cw")
    if wh_scope:
        where.append(wh_scope)
        params.update(wh_params)
    prod_scope, prod_params = company_sql_predicate(db, "p.company_id", param_prefix="cp")
    if prod_scope:
        where.append(prod_scope)
        params.update(prod_params)
    if product_ids is not None:
        if not product_ids:
            return []
        where.append("np.product_id::text = ANY(:pids)")
        params["pids"] = [str(p) for p in product_ids]
    if warehouse_ids is not None:
        if not warehouse_ids:
            return []
        where.append("np.warehouse_id::text = ANY(:wids)")
        params["wids"] = [str(w) for w in warehouse_ids]

    # The PLAN's own committed figure, on every run (`PLAN-scm-oi-handshake.md` section 3).
    # It used to be read straight off `scm.committed_v` unless a horizon was asked for; the
    # acknowledgement rule made that untrue, because a plan may only buy against an
    # instruction purchasing has ACKNOWLEDGED, while the view goes on counting an awaiting
    # one - it is still owed to the customer. `demand.horizon_committed_select_sql` is that
    # narrower reading, with `:horizon` NULL on an unhorizoned run (every date comparison
    # short-circuits true), so the two rules live in one SELECT rather than in a branch
    # here that could answer differently.
    cv_join = (f"LEFT JOIN ({demand.horizon_committed_select_sql()}) cv "
               "ON cv.product_id = np.product_id AND cv.warehouse_id = np.warehouse_id")
    committed_col = "COALESCE(cv.committed, 0) AS committed"
    committed_expr = "COALESCE(cv.committed, 0)"
    params["horizon"] = horizon

    # Captain, 20 Aug: "the on hand need to consider pool quantity only ... project on
    # hand quantity is not really an actual usable quantity." `w.segment` is the test
    # ('dealer' on a pool root - BRW, MWH, DC1, RSW, WH3 - 'project' on the `-BB`/`-IB`/
    # `-IR`/`-NTC`/`-SMC` bins it feeds today) - never the CODE's naming convention
    # (`ProjectSupplyService._site_pool_warehouses` warns the hyphen suffix is not
    # authoritative). NOT `pool_warehouse_id`: that FK also drives the UNRELATED
    # fulfilment-pool netting opt-in (`_pool_map`/`pool_netting`), whose members can be
    # any warehouses a policy groups together regardless of segment - reusing it here
    # zeroed real stock inside an ordinary fulfilment pool that carries no project/dealer
    # split at all (`tests/scm/test_pool_netting_parity.py`,
    # `test_a_pool_member_the_split_gave_nothing_to_still_reaches_the_product_row`). A
    # location with no segment set counts (a site nobody has classified is not assumed to
    # be a project bin). `quantity_on_hand` counted here is the ONLY figure the engine
    # ever reads for netting/trigger, so moving it also moves `net_position` in the SAME
    # expression (never two readings of one fact that could drift apart) - the coupling
    # the diagnosis flagged. Stock sitting in a project bin is not silently dropped:
    # `project_on_hand` carries it, visible, on every row.
    is_dealer_expr = "(COALESCE(w.segment, 'dealer') <> 'project')"
    on_hand_expr = f"(CASE WHEN {is_dealer_expr} THEN np.quantity_on_hand ELSE 0 END)"
    project_on_hand_expr = f"(CASE WHEN {is_dealer_expr} THEN 0 ELSE np.quantity_on_hand END)"
    net_position_col = f"({on_hand_expr} + np.on_order - {committed_expr}) AS net_position"

    sql = text(f"""
        SELECT np.product_id, np.warehouse_id,
               p.product_code, p.product_name, pc.category_code, p.list_price,
               -- Master-data reorder settings. Shown beside what the plan computed so the
               -- buyer can see where the two disagree; the engine does not read them.
               p.reorder_level AS master_reorder_level,
               p.reorder_quantity AS master_reorder_quantity,
               w.warehouse_code, w.warehouse_name, w.segment,
               {on_hand_expr} AS quantity_on_hand,
               {project_on_hand_expr} AS project_on_hand,
               np.on_order, {committed_col}, {net_position_col},
               -- Front planning 5.3: the SAME committed figure, split by demand channel.
               -- Read off `committed_v` (or, under a horizon, its run-scoped override)
               -- rather than `net_position_v` so the netting view keeps exactly the
               -- columns and cardinality every other consumer already reads (AC-F07). The
               -- TWO sum to the `committed` column above - there is no third channel since
               -- P4, and `committed_v`'s `unclassified_committed` is a constant 0 kept
               -- only so the view could be replaced in place.
               COALESCE(cv.project_committed, 0) AS project_committed,
               COALESCE(cv.retail_committed, 0) AS retail_committed,
               -- Project demand is the Order Inquiry alone since P3 (migration 424), so
               -- this is EQUAL to `project_committed` on every row rather than a subset
               -- of it. Read as its own column all the same: the engine bypasses the
               -- reorder trigger for confirmed Buy (AC-E04, AC-E05), and that bypass must
               -- name the figure it means rather than inherit whatever the display column
               -- happens to hold.
               COALESCE(cv.project_confirmed_committed, 0) AS project_confirmed_committed,
               -- S10 - the buyer checks outstanding PO and incoming SPO by hand every week.
               -- `np.on_order` is SPO (supplier POs on the water); `po_ordered_v` is the
               -- ordered-not-received PO book. Two different questions, two columns.
               COALESCE(po.ordered, 0) AS po_ordered,
               ds.avg_daily_demand, ds.demand_cv, ds.sample_days, ds.window_days,
               ic.abc_class, ic.xyz_class
        FROM scm.net_position_v np
        JOIN products p ON p.id = np.product_id
        JOIN warehouses w ON w.id = np.warehouse_id
        {cv_join}
        LEFT JOIN scm.po_ordered_v po
          ON po.product_id = np.product_id AND po.warehouse_id = np.warehouse_id
        LEFT JOIN product_categories pc ON pc.id = p.category_id
        LEFT JOIN scm.demand_stat ds
          ON ds.product_id = np.product_id AND ds.warehouse_id = np.warehouse_id
        LEFT JOIN scm.item_classification ic
          ON ic.product_id = np.product_id AND ic.warehouse_id = np.warehouse_id
        WHERE {' AND '.join(where)}
        ORDER BY p.product_code, w.warehouse_code
    """)
    return [dict(r) for r in db.execute(sql, params).mappings().all()]


def awaiting_acknowledgement_rows(db: Session) -> int:
    """How many order inquiry rows are waiting for purchasing to take them on.

    The plan page's chip (`PLAN-scm-oi-handshake.md` section 4, AC-H10): the plan counts
    acknowledged rows only, so the awaiting ones would otherwise be invisible on the very
    screen that decides what to buy - a buyer would read a Project figure of nothing and
    conclude there is nothing to do.

    A COUNT of rows, live, not a figure frozen into the run log: it drops as the buyer
    acknowledges, and a chip that still claimed six after they had cleared them would send
    them looking for two that do not exist. Scoped to the rows that could ever BE demand -
    a buy verb, still owed - so a cancelled instruction is not counted as work.
    """
    from app.models.project_so import (
        ACK_AWAITING,
        INQUIRY_PARTLY_LINKED,
        INQUIRY_RAISED,
        IV_ORDER,
        IV_ORDER_BACK,
        OrderInquiryRow,
    )

    return int(
        db.query(func.count(OrderInquiryRow.id))
        .filter(
            OrderInquiryRow.ack_state == ACK_AWAITING,
            OrderInquiryRow.verb.in_((IV_ORDER, IV_ORDER_BACK)),
            OrderInquiryRow.state.in_((INQUIRY_RAISED, INQUIRY_PARTLY_LINKED)),
        )
        .scalar()
        or 0
    )


def _project_supply_reduction_map(db: Session, rows: list[dict],
                                  horizon: Optional[date] = None) -> dict[tuple, float]:
    """``{(product_id, warehouse_id): qty}`` of stock an ACTIVE Project decision has
    already claimed, at the location it was claimed FROM.

    > "every confirmed non-Buy component of an active Project decision (Reserve, Borrow,
    >  and timely SPO cover) is removed from Retail planning supply at its recorded source
    >  location"   (front planning 1.3, 5.3, AC-F07)

    Confirmed cover that stays free in the next Retail calculation is the double count the
    whole read model exists to prevent: CS promised those units to a project, so Retail
    must not net against them a second time. Every non-Buy `so_line_allocations` row of a
    decided SO counts, at `warehouse_id` when it names one (BRW-pool Reserve names the
    pool, Borrow names the donor) and at the core line's fulfilment location otherwise
    (own-location Reserve). `source_type = 'order'` is the Buy leg and is NOT a claim on
    stock - it is the residual the plan is being asked to buy.

    Timely SPO cover carries no allocation row today (it is dated location supply, not a
    persisted SO-line link), so it enters here only once Stage 1C writes it as a component.

    ``horizon`` filters on the CORE line's own ``required_date`` - the same demand this
    claim reduces `project_need` against (`project_confirmed_committed`, already horizoned
    through `demand.horizon_committed_select_sql`) - so a reserve and the demand it offsets
    leave the plan together. Undated demand stays in, same rule as every other horizon
    predicate in this module.
    """
    pids = list({str(r["product_id"]) for r in rows})
    if not pids:
        return {}
    found = db.execute(text("""
        SELECT sol.product_id::text AS pid,
               COALESCE(a.warehouse_id, sol.warehouse_id)::text AS wid,
               SUM(a.qty) AS qty
        FROM projects.so_line_allocations a
        JOIN projects.sales_order_lines psl ON psl.id = a.so_line_id
        JOIN sales_order_lines sol ON sol.id = psl.core_sales_order_line_id
        JOIN projects.so_supply_decisions d
          ON d.project_sales_order_id = psl.project_sales_order_id
         AND d.state = 'active'
        WHERE a.source_type <> 'order'
          AND sol.product_id::text = ANY(:pids)
          AND (CAST(:horizon AS date) IS NULL OR sol.required_date IS NULL
               OR sol.required_date <= CAST(:horizon AS date))
        GROUP BY 1, 2
    """), {"pids": pids, "horizon": horizon}).fetchall()
    return {(str(r[0]), str(r[1])): float(r[2] or 0.0)
            for r in found if r[1] is not None and float(r[2] or 0.0) > 0}


def _apply_project_supply_reduction(db: Session, rows: list[dict],
                                    horizon: Optional[date] = None) -> None:
    """Stamp each planning row with the confirmed Project claim on its own stock.

    Mutated onto the row rather than passed down, exactly like `_apply_unlocated_demand`,
    so every path that computes a cell sees it without a new parameter on four signatures.
    """
    claims = _project_supply_reduction_map(db, rows, horizon=horizon)
    if not claims:
        return
    for r in rows:
        qty = claims.get((str(r["product_id"]), str(r["warehouse_id"])))
        if qty:
            r["project_supply_reduction"] = qty


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
    # Company-scoped through the joined location, for the same reason as `_planning_rows`:
    # this is raw SQL over a view, so the ORM isolation filter never sees it. A last-movement
    # date read from another company's consumption would make a dead line here look alive.
    co, co_params = company_sql_predicate(db, "w.company_id", param_prefix="clm")
    params.update(co_params)
    rows = db.execute(text(f"""
        SELECT cv.product_id, cv.warehouse_id, MAX(cv.day) AS last_day
        FROM scm.consumption_v cv
        JOIN warehouses w ON w.id = cv.warehouse_id
        WHERE cv.product_id::text = ANY(:pids) {wh}
          {("AND " + co) if co else ""}
        GROUP BY cv.product_id, cv.warehouse_id
    """), params).fetchall()
    return {(str(r[0]), str(r[1])): r[2] for r in rows}


def _last_purchase_map(db: Session, product_ids: list[str]) -> dict[str, date]:
    """``{product_id: last purchase date}``, including the imported history.

    Keyed by PRODUCT, not by (product, warehouse). The purchase-history export names no
    location at all, so a per-warehouse key would silently drop every historical order and
    leave the ageing signal reading "never bought" for exactly the stock it exists to judge.
    Buying is a product-level act here in any case: one order lands and is put away wherever
    there is room.

    Company-scoped through the joined order, for the same reason as `_last_movement_map`:
    this is raw SQL, so the ORM isolation filter never sees it.
    """
    pids = list({str(p) for p in product_ids})
    if not pids:
        return {}
    co, co_params = company_sql_predicate(db, "po.company_id", param_prefix="clp")
    rows = db.execute(text(f"""
        SELECT pol.product_id, MAX(po.issue_date) AS last_day
        FROM purchase_order_lines pol
        JOIN purchase_orders po ON po.id = pol.purchase_order_id
        WHERE pol.product_id::text = ANY(:pids)
          AND po.issue_date IS NOT NULL
          {("AND " + co) if co else ""}
        GROUP BY pol.product_id
    """), {"pids": pids, **co_params}).fetchall()
    return {str(r[0]): r[1] for r in rows}


def _last_purchase_cost_map(db: Session, product_ids: list[str]) -> dict[str, dict]:
    """What we last PAID, per product, split by segment where the destination is known.

    > "last purchase only consider BRW ... last purchase for project is depending on the
    >  BRW-BB, IB those location"

    The split is the right question and the data cannot answer it for most rows: 12,928 of
    the 12,940 purchase-order lines on the customer's book name no destination, because the
    purchase-history export does not carry one. So this returns THREE things and the row
    says which it is showing:

      dealer / project - a purchase whose destination is known to be that segment
      any            - the most recent purchase regardless, used only when the segment
                         has none of its own

    A price with no destination is NOT relabelled as dealer. Calling an unattributed cost
    "the dealer cost" would be inventing the very attribution the buyer asked for, and they
    would price a project order off it. Once purchases arrive carrying a destination (an
    SPO allocation already does), the same query starts answering per segment with no
    further change here.
    """
    pids = list({str(p) for p in product_ids})
    if not pids:
        return {}
    co, co_params = company_sql_predicate(db, "po.company_id", param_prefix="clc")
    rows = db.execute(text(f"""
        SELECT DISTINCT ON (pol.product_id, COALESCE(w.segment, 'unattributed'))
               pol.product_id::text AS product_id,
               COALESCE(w.segment, 'unattributed') AS segment,
               pol.unit_cost, COALESCE(pol.currency, po.currency) AS currency,
               po.po_number, po.issue_date
          FROM purchase_order_lines pol
          JOIN purchase_orders po ON po.id = pol.purchase_order_id
          LEFT JOIN warehouses w ON w.id = pol.warehouse_id
         WHERE pol.product_id::text = ANY(:pids)
           AND pol.unit_cost IS NOT NULL
           {("AND " + co) if co else ""}
         ORDER BY pol.product_id, COALESCE(w.segment, 'unattributed'),
                  po.issue_date DESC NULLS LAST, pol.created_at DESC
    """), {"pids": pids, **co_params}).mappings().all()

    out: dict[str, dict] = {}
    for r in rows:
        entry = {
            "cost": _fnum(r["unit_cost"]),
            "currency": r["currency"],
            "ref": r["po_number"],
            "at": r["issue_date"].isoformat() if r["issue_date"] else None,
        }
        bucket = out.setdefault(r["product_id"], {})
        bucket[r["segment"]] = entry
        # "any" is the newest across every segment. The rows arrive newest-first within a
        # segment but not across them, so it is chosen rather than assumed.
        cur = bucket.get("any")
        if cur is None or (entry["at"] or "") > (cur["at"] or ""):
            bucket["any"] = entry
    return out


def _last_purchase_for(costs: dict, product_id: str,
                       segment: Optional[str]) -> tuple[Optional[dict], str]:
    """The purchase to show on a row, and how it was attributed.

    `own_segment` - a purchase that landed in this segment. `other_segment` is never
    returned: a dealer price does not price a project order.
    """
    bucket = (costs or {}).get(product_id) or {}
    if segment and bucket.get(segment):
        return bucket[segment], "own_segment"
    if bucket.get("unattributed"):
        return bucket["unattributed"], "unattributed"
    if bucket.get("any"):
        return bucket["any"], "unattributed"
    return None, "never_purchased"


# ===========================================================================
# per-warehouse planning (buy_scope=warehouse)
# ===========================================================================

def _pool_netting_enabled(policies: list[dict], db: Session, product_id: str) -> bool:
    """Whether this product's policy lets a sibling bin's surplus cover another bin.

    OFF by default. Pooled netting assumes a transfer that this phase does not propose:
    stock moves between bins on CS's say-so, decided before purchasing ever sees the
    requirement. Buying less on the strength of a move nobody has agreed to under-buys, and
    an under-buy is invisible until the stock runs out.
    """
    policy = eng.resolve_policy_for_sku(db, product_id, None, policies) or {}
    return bool(policy.get("pool_netting"))


def _pool_map(db: Session, rows: list[dict]) -> dict[str, str]:
    """``{warehouse_id: pool_id}`` for the planned locations.

    A location with no ``pool_warehouse_id`` is its own pool, which is what makes this
    change safe: over singleton pools, grouping by pool IS grouping by warehouse. See
    ADR-0011's pool-scope amendment.
    """
    wids = list({str(r["warehouse_id"]) for r in rows})
    if not wids:
        return {}
    found = db.execute(text(
        "SELECT id, COALESCE(pool_warehouse_id, id) AS pool_id "
        "FROM warehouses WHERE id::text = ANY(:wids)"
    ), {"wids": wids}).fetchall()
    out = {str(r[0]): str(r[1]) for r in found}
    # Anything the lookup missed still gets a pool: itself. Falling back to "no pool" would
    # silently drop the location from planning.
    for wid in wids:
        out.setdefault(wid, wid)
    return out


def _plan_per_warehouse(db: Session, run_id: str, rows: list[dict], policies: list[dict],
                        today: date, last_move: dict,
                        wh_meta: Optional[dict] = None,
                        last_buy: Optional[dict] = None,
                        rates: Optional[dict] = None,
                        levels: Optional[dict] = None,
                        last_cost: Optional[dict] = None,
                        horizon: Optional[date] = None) -> list[ReorderRecommendation]:
    """Plan each SKU against each fulfilment POOL, not each warehouse.

    A shortage in one bin is covered from the shared pool its site draws on before it is
    ever a purchase; netting strictly per location recommended buying 67 units of an item
    holding 4,397 (ADR-0011). A location with no pool pointer is its own pool, so a tenant
    that has configured no pooling gets byte-identical output to before - pinned by
    ``tests/scm/test_pool_netting_parity.py``.

    Disposition and transfer flags stay per LOCATION: "this stock has not moved in a year"
    and "this bin is overstocked while that one is short" are statements about a place, and
    aggregating them away would hide the very thing they exist to surface.
    """
    recs: list[ReorderRecommendation] = []
    # Read once for the whole plan, never once per SKU.
    rates = load_rates(db) if rates is None else rates
    wh_meta = wh_meta or {str(r["warehouse_id"]): (r["warehouse_code"], r["warehouse_name"])
                          for r in rows}
    pool_of = _pool_map(db, rows)

    # group by product so transfer flags can see all warehouses of a SKU
    by_product: dict[str, list[dict]] = {}
    for r in rows:
        by_product.setdefault(str(r["product_id"]), []).append(r)

    _apply_unlocated_demand(db, by_product, horizon=horizon)

    for pid, prows in by_product.items():
        # Each location is its own pool unless the policy says siblings may cover for one
        # another. Grouping is per product because the toggle resolves per product.
        pooled = _pool_netting_enabled(policies, db, pid)
        cands = eng.load_supplier_candidates(db, pid, rates=rates)
        computed: list[dict] = []
        for r in prows:
            c = _compute_cell(db, r, policies, cands, today, last_move, last_buy,
                              levels=levels, last_cost=last_cost)
            computed.append(c)
        flags = _transfer_flags_for(prows, computed)

        by_pool: dict[str, list[tuple[dict, dict]]] = {}
        for r, c in zip(prows, computed):
            wid = str(r["warehouse_id"])
            by_pool.setdefault(pool_of[wid] if pooled else wid, []).append((r, c))

        for pool_id, members in by_pool.items():
            if len(members) == 1:
                # The degenerate case, and the common one. Unchanged arithmetic.
                r, c = members[0]
                recs.extend(_emit_cell(run_id, r, c, flags.get(str(r["warehouse_id"]))))
            else:
                recs.extend(_emit_pool(db, run_id, pool_id, members, policies, cands,
                                       flags, wh_meta))
    return recs


def _unlocated_demand_map(
    db: Session, product_ids: list[str], horizon: Optional[date] = None,
) -> dict[str, float]:
    """``{product_id: qty}`` of open RETAIL demand whose sales-order line names no
    warehouse.

    97% of the customer's open lines are like this. Grouped away by ``scm.committed_v``
    under a NULL key that ``scm.net_position_v`` then fails to join to itself (``NULL =
    NULL`` is not true), so this demand was netted against nothing, anywhere, and the
    products carrying it simply never appeared in a plan.

    ``horizon`` mirrors ``demand.horizon_committed_select_sql``'s own rule exactly (the
    two must not drift, or a located line beyond the cutoff is excluded while an
    unlocated line for the same product is not): a stated ``required_date`` after the
    cutoff is excluded, a NULL date is always in. ``None`` reproduces the unhorizoned
    query's total byte-for-byte (this only adds a ``GROUP BY`` dimension to it, never a
    new filter).

    ONE channel, because the book leg of ``scm.committed_v`` is one channel now (P3,
    migration 424): a project-class line is not demand as a book line at all - it becomes
    demand when CS raises an Order Inquiry row for it - and a NULL class reads as retail.
    Same classification a LOCATED line gets there; this is the only place an unlocated one
    is read, so it has to make the same call by hand rather than via the view.

    An Order Inquiry row that states no stock location is unlocated too, and is NOT landed
    here: it comes out of the view under a NULL warehouse, which every reader's
    ``(product, warehouse)`` join matches nowhere. Counted at no location rather than
    invented at one, which is the form leg's own rule.
    """
    if not product_ids:
        return {}
    co, co_params = company_sql_predicate(db, "so.company_id", param_prefix="uld")
    rows = db.execute(text(f"""
        SELECT sol.product_id::text AS pid,
               SUM(GREATEST(COALESCE(sol.qty_required, sol.qty_ordered)
                          - COALESCE(sol.qty_delivered, 0), 0)) AS qty
        FROM sales_order_lines sol
        JOIN sales_orders so ON so.id = sol.sales_order_id
        WHERE sol.warehouse_id IS NULL
          AND so.status = 'open' AND sol.line_status = 'open'
          AND sol.purchasing_status <> 'covered'
          AND so.demand_class IS DISTINCT FROM 'project'
          AND sol.product_id::text = ANY(:pids)
          {("AND " + co) if co else ""}
          AND (CAST(:horizon AS date) IS NULL OR sol.required_date IS NULL
               OR sol.required_date <= CAST(:horizon AS date))
        GROUP BY sol.product_id
    """), {"pids": [str(p) for p in product_ids], "horizon": horizon, **co_params}).fetchall()
    out: dict[str, float] = {}
    for pid, qty in rows:
        qty = float(qty or 0.0)
        if qty > 0:
            out[str(pid)] = out.get(str(pid), 0.0) + qty
    return out


def _apply_unlocated_demand(db: Session, by_product: dict[str, list[dict]],
                            horizon: Optional[date] = None) -> None:
    """Land each product's unlocated demand on the location that would actually ship it.

    > "all SO line should have warehouse one, no warehouse we can just put it under net"

    Netting it nowhere is what made 1,130,402 units invisible. Netting it everywhere would
    double-count it against every pool. So it lands on ONE row per product: the location
    holding the most of that item, which is where the goods would come from, and which is
    the row a planner recognises. Ties break on warehouse code so a re-run cannot move the
    demand around, and a product with stock nowhere still gets a row rather than being
    dropped for a second reason.

    The rows are mutated in place, so everything downstream - netting, trigger, order size,
    the covered-by-stock suggestion - sees it as ordinary demand at that location. The
    quantity is stamped on the row so the plan can say where it came from.

    The SAME landing also raises ``committed`` without raising its channel split
    (``project_committed`` / ``retail_committed``) - which breaks the invariant every
    located row keeps (the two sum to ``committed``) and, on the FE, makes the row
    invisible to the expand panel's member filter, which keys on those figures. The whole
    unlocated total is RETAIL (see ``_unlocated_demand_map``), so it is added to that
    column here and the row lands classified exactly as a located line would have
    (AC-F07's invariant, held for a row this landing created rather than one the view
    already carried).

    ``horizon`` is the run's own "Plan until" cutoff, threaded straight through to
    ``_unlocated_demand_map`` - this path alone carries ~97% of the book, so leaving it
    unhorizoned defeated the horizon for nearly the whole plan.
    """
    unlocated = _unlocated_demand_map(db, list(by_product.keys()), horizon=horizon)
    if not unlocated:
        return
    for pid, qty in unlocated.items():
        prows = by_product.get(pid)
        if not prows:
            continue
        if qty <= 0:
            continue
        target = max(prows, key=lambda r: (float(r["quantity_on_hand"] or 0.0),
                                           str(r["warehouse_code"] or "")))
        target["committed"] = float(target["committed"] or 0.0) + qty
        target["net_position"] = float(target["net_position"] or 0.0) - qty
        target["unlocated_added"] = qty
        target["retail_committed"] = float(target.get("retail_committed") or 0.0) + qty


def _covered_rec(run_id: str, pool_id: str, prows: list[dict], anchor: dict, agg_cell: dict,
                 *, moq: Optional[float] = None,
                 order_multiple: Optional[float] = None,
                 plan_basis: Optional[dict] = None) -> Optional[ReorderRecommendation]:
    """A demand line the pool's own stock covers is a SUGGESTION, never a silent omission.

    An order-inquiry line reaching the plan has already been through CS: they decided this
    quantity needs buying, having looked at what the branch holds. The engine finding stock
    in the pool is worth SAYING - "you have 5 at BRW-BB, consider using those" - but it is
    not the engine's decision to make. Dropping the row means the system quietly chose "use
    stock" on the planner's behalf, and a CS oversight then has nowhere to surface.

    So: no trigger, but committed demand exists -> a ``covered`` row carrying the quantity
    that WOULD be bought (the outstanding commitment, rounded to the supplier's terms) plus
    what the pool holds. The planner picks: use stock, or buy anyway.

    ``None`` when the pool has no committed demand at all - that is genuinely nothing to
    say, not a decision withheld.

    It carries its sizing group's ``plan_basis`` like every other row, because the demand
    the group holds is true whether or not the group ended up buying: a product whose
    location A buys and location B is covered would otherwise lose B's unclassified and
    project-sheet readings, and every member location of B, from the product row.
    """
    committed = sum(float(r["committed"] or 0.0) for r in prows)
    if committed <= 0:
        return None
    # Same leg as `_compute_cell`'s `net` (captain, 20 Aug): outstanding PO is incoming
    # supply here too, or a pool sitting on a PO for the exact committed quantity still
    # reads as "buy this anyway" instead of "you already have this on order".
    available = sum(float(r["quantity_on_hand"] or 0.0) + float(r["on_order"] or 0.0)
                    + float(r["po_ordered"] or 0.0) for r in prows)
    rounded = eng.round_order_qty(committed, moq, order_multiple)
    cell = dict(agg_cell)
    # The row's own facts, so the grid states the trade-off without re-deriving it from
    # figures that may have moved since the run froze.
    cell["covered_committed"] = committed
    cell["covered_available"] = available
    return _build_rec(
        run_id, "covered", anchor, cell, warehouse_id=pool_id,
        order_qty=committed, rounded=rounded,
        reason_label=(f"{_qty_label(available)} available in this pool covers "
                      f"{_qty_label(committed)} committed"),
        plan_basis=plan_basis,
    )


def _qty_label(value: float) -> str:
    """Whole numbers read as whole numbers; a fractional quantity keeps its fraction."""
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _emit_pool(db: Session, run_id: str, pool_id: str,
               members: list[tuple[dict, dict]], policies: list[dict], cands: list[dict],
               flags: dict, wh_meta: dict) -> list[ReorderRecommendation]:
    """One buy decision for a multi-location pool, apportioned back to its locations.

    Reuses ``aggregate_network`` and ``allocate`` rather than growing a second netting
    implementation: "add up demand and net across these locations, size one buy, split it
    by deficit" is the same operation whether the set of locations is a network or a pool.
    Both are already covered by the M3 golden set.

    Unlike the network scope this buy is tied to a REAL warehouse - the pool itself - so no
    recommendation is emitted against a synthetic aggregate row (M8-D5).
    """
    recs: list[ReorderRecommendation] = []
    prows = [r for r, _ in members]
    cells = [c for _, c in members]

    # Policy is resolved for the pool, so one pool cannot be planned under two policies.
    policy = eng.resolve_policy_for_sku(db, str(prows[0]["product_id"]), pool_id,
                                        policies) or {}
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

    # The pool nets its RETAIL position (`_compute_cell` has already added the other two
    # channels back and removed confirmed Project claims); firm Project Buy is added to
    # the sized order below rather than netted (AC-E05).
    wh_inputs = [{"warehouse_id": str(r["warehouse_id"]),
                  "demand_rate": float(r["avg_daily_demand"] or 0.0),
                  "net": float(c.get("retail_net", r["net_position"]) or 0.0)}
                 for r, c in zip(prows, cells)]
    project_by_wid = {str(r["warehouse_id"]): float(c.get("project_need") or 0.0)
                      for r, c in zip(prows, cells)}
    pool_project_need = sum(project_by_wid.values())

    policy_type = policy.get("policy_type") or "reorder_point"
    # S10 - on the reorder_level basis the pool is sized against the SUM of its members'
    # levels rather than against a forecast. Each member is measured against its own level,
    # so a bin nobody has set up contributes nothing and receives nothing.
    pool_levels = None
    unset = []
    if policy_type == "reorder_level":
        pool_levels = {}
        for r, c in zip(prows, cells):
            wid = str(r["warehouse_id"])
            pool_levels[wid] = c.get("reorder_level")
            if c.get("reorder_level") is None:
                unset.append((r, c))

    # A pool where NOBODY has set a level has no target at all. Summing the levels that
    # exist gives 0, and 0 is a real target that any deficit trips - so the pool bought its
    # whole shortage on a number nobody chose, which is the exact failure the needs_level
    # row exists to prevent. None means "do not plan this pool"; the members are still each
    # named below, so the work is visible rather than silent.
    pool_unplannable = (pool_levels is not None
                        and all(v is None for v in pool_levels.values()))
    if pool_unplannable:
        pool_levels = None

    agg = eng.aggregate_network(wh_inputs, lead_time_days=lead, safety_days=safety_days,
                                review_days=review_days, moq=moq,
                                order_multiple=order_multiple, levels=pool_levels)

    min_override = _fnum(policy.get("min_override"))
    max_override = _fnum(policy.get("max_override"))
    agg_net = float(agg["agg_net"])
    if policy_type == "min_max" and max_override is not None:
        target_oup = float(max_override)
    else:
        target_oup = float(agg["order_up_to"])
    if pool_unplannable:
        # Nothing to plan against, and the forecast figures computed above must NOT be
        # allowed to stand in for the missing level: falling through to them would silently
        # restore the basis the buyer replaced.
        triggered, reason_label = False, None
    else:
        triggered, reason_label = eng.trigger(
            policy_type, net=agg_net, rop=float(agg["reorder_point"]),
            min_level=min_override, oup=target_oup, on_cadence=True,
            reorder_level=(float(agg["reorder_point"]) if pool_levels is not None else None))
    # Unrounded, so the supplier's terms apply ONCE to the pool's whole need.
    retail_recommended, _unrounded = eng.order_qty(
        triggered, net=agg_net, oup=target_oup, moq=None, order_multiple=None)
    recommended = retail_recommended + pool_project_need
    if pool_project_need > 0 and not triggered:
        triggered = True
        reason_label = (f"project buy: {_qty_label(pool_project_need)} confirmed unplaced "
                        f"Buy in this pool")
    rounded = (eng.round_order_qty(recommended, moq, order_multiple)
               if triggered and recommended > 0 else 0.0)
    if not triggered:
        recommended = 0.0
    # A location short only of firm Project Buy has no Retail deficit, so without this it
    # would receive nothing from the split it is the whole reason for.
    for w in agg["warehouses"]:
        w["deficit"] = float(w.get("deficit") or 0.0) + project_by_wid.get(
            str(w["warehouse_id"]), 0.0)

    # Emit the buy against the pool's own row when it is one of the planned locations, so
    # the recommendation names a place a buyer recognises.
    anchor = next((r for r in prows if str(r["warehouse_id"]) == pool_id), prows[0])
    agg_cell = _network_agg_cell(policy, tog, chosen, alt_choices, agg, lead, moq,
                                 order_multiple, prows,
                                 supplier_reason=sel.get("reason"),
                                 policy_type=policy_type,
                                 min_override=min_override, max_override=max_override,
                                 target_oup=target_oup, triggered=triggered,
                                 reason_label=reason_label, recommended=recommended,
                                 rounded=rounded, cells=cells)
    # ONE basis for the whole pool, carried identically by every row the pool emits -
    # including the rows that buy nothing. A member the split gave nothing to emits no row
    # at all, and a group that was covered or could not be sourced emits no buy at all, so
    # without this their channel needs never reach the product's readings. A demand
    # statement does not stop being true because the allocator sent the goods to a sibling,
    # or because the pool had enough already.
    split = eng.allocate(rounded, agg["warehouses"]) if triggered and rounded > 0 else {}
    pool_basis = _plan_basis(pool_id, "pool", prows, cells, split,
                             retail_need=retail_recommended,
                             recommended=recommended, rounded=rounded)

    # Named one row per bin, not once for the pool: the buyer has to set each one, and a
    # single pool-level "somebody needs a level" would not say which. Emitted here rather
    # than where `unset` was collected, so each row can carry the pool's basis; they still
    # come first in the pool's rows, exactly as before.
    for r, c in unset:
        recs.append(_build_rec(run_id, "needs_level", r, c,
                               warehouse_id=str(r["warehouse_id"]),
                               order_qty=None, rounded=None,
                               reason_enum="needs_level",
                               reason_label=_needs_level_label(c),
                               plan_basis=pool_basis))
    if triggered and rounded > 0:
        allocation = _allocation_lines(split, wh_meta)
        if chosen:
            # ONE ROW PER LOCATION THAT ASKED, never one row on the pool root.
            #
            # > "if the demand is at BRW-IB, then it should be bought to BRW-IB, the pooling
            # >  is only relevant if we want to borrow stock from other location"
            #
            # The pool decides WHETHER a purchase is needed - a sibling's surplus covers the
            # shortage first - and never where it lands. Emitting on the root put stock into
            # a location nobody ordered for, and left the planner asking why BRW was buying
            # for a BRW-IB order.
            by_id = {str(r["warehouse_id"]): r for r in prows}
            cell_by_id = {str(r["warehouse_id"]): c for r, c in zip(prows, cells)}
            share = _r(rounded) or 0
            placed = [(wid, qty) for wid, qty in split.items()
                      if qty and qty > 0 and wid in by_id]
            for wid, qty in sorted(placed, key=lambda kv: -kv[1]):
                # `recommended` is the pre-rounding pool figure; each location carries its
                # OWN share of it so the row's numbers describe the row's own purchase.
                portion = (float(recommended) * float(qty) / float(share)) if share else None
                # Sizing is the POOL's (one decision, borrowing included), but the position
                # columns must describe THIS location. Showing the pool's net on every row
                # made three rows read as three identical -37s, which is a figure that
                # belongs to none of them.
                member = cell_by_id.get(wid) or {}
                row_cell = dict(agg_cell)
                # Sizing is the POOL's; every figure that DESCRIBES a place belongs to the
                # place. The aggregate cell has no on-hand, no level and no last price, so
                # a pooled row that kept them all from `agg_cell` showed the buyer a blank
                # checklist on exactly the rows a pool produces - which is most of them.
                # `ss` travels with `rop` and `demand_rate` or the row's own explanation
                # stops adding up: the drill renders "ROP = safety stock + demand x lead",
                # and pairing the POOL's safety stock with the LOCATION's reorder point
                # printed 27 + 1.0/day x 14d = 22, which is not arithmetic anybody can
                # follow. Sizing stays the pool's; every figure that describes this bin
                # comes from this bin.
                for k in ("net", "rop", "demand_rate", "doc",
                          "project_need", "retail_need",
                          "project_supply_reduction", "retail_net",
                          "ss", "ss_used", "ss_fallback",
                          "demand_window_days",
                          "on_hand", "project_on_hand", "on_order", "po_ordered", "segment",
                          "master_reorder_level", "master_reorder_quantity",
                          "committed", "list_price",
                          "reorder_level", "reorder_level_source", "suggested_level",
                          "suggestion_basis", "last_purchase", "last_purchase_basis"):
                    if k in member:
                        row_cell[k] = member[k]
                recs.append(_build_rec(
                    run_id, "buy", by_id[wid], row_cell,
                    warehouse_id=wid, order_qty=portion, rounded=float(qty),
                    # The split stays on every row: it is how a reader sees that this buy
                    # was sized against the whole pool, not against this bin alone.
                    allocation=allocation, plan_basis=pool_basis))
            if not placed:
                # The allocator gave the whole buy to a location outside the planned set,
                # which should not happen. Emitting nothing would drop a triggered buy in
                # silence, so it lands on the anchor and says so.
                recs.append(_build_rec(
                    run_id, "buy", anchor, agg_cell, warehouse_id=pool_id,
                    order_qty=recommended, rounded=rounded, allocation=allocation,
                    plan_basis=pool_basis))
        else:
            recs.append(_build_rec(
                run_id, "exception", anchor, agg_cell, warehouse_id=pool_id,
                order_qty=None, rounded=None,
                reason_label="no linked supplier - cannot source this pool reorder",
                plan_basis=pool_basis))
    else:
        covered = _covered_rec(run_id, pool_id, prows, anchor, agg_cell,
                               moq=moq, order_multiple=order_multiple,
                               plan_basis=pool_basis)
        if covered is not None:
            recs.append(covered)

    # Disposition stays per location: idle stock is a fact about one bin.
    for r, cell in zip(prows, cells):
        disp = cell["disposition"]
        if disp:
            action = "discontinue" if disp["type"] == "dead" else "hold"
            recs.append(_build_rec(run_id, "disposition", r, cell,
                                   warehouse_id=str(r["warehouse_id"]),
                                   order_qty=None, rounded=None,
                                   reason_enum=disp["type"],
                                   reason_label=_disposition_label(
                                       disp["type"], cell, disp.get("basis")),
                                   disposition_action=action,
                                   transfer_flag=flags.get(str(r["warehouse_id"]))))
    return recs


def _compute_cell(db: Session, row: dict, policies: list[dict], cands: list[dict],
                  today: date, last_move: dict, last_buy: Optional[dict] = None,
                  levels: Optional[dict] = None,
                  last_cost: Optional[dict] = None) -> dict:
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
    # Captain, 20 Aug (live test): "for reorder plan need to deduct both SPO and PO to
    # determine the suggested quantity." `net_position` (on_hand + on_order/SPO -
    # committed, `scm.net_position_v`) has never carried the PO book - `po_ordered` sits
    # on the row (S10, `scm.po_ordered_v`) DISPLAY-ONLY, so a row could read "Net -1,141"
    # while its own PO column read 3,642 outstanding for the exact same shortage, and the
    # plan would recommend buying it again.
    #
    # No double count: the only thing `committed` ever excludes is a LINE CS marked
    # `purchasing_status='covered'` - "no purchase needed", a distinct ruling made by a
    # person, NOT "a PO exists for it" (`models/order.py::SalesOrderLine.purchasing_status`;
    # `committed_v`/`_unlocated_demand_map` filter on the same column). A line with a PO
    # raised against it keeps `purchasing_status='ordered'` and stays fully committed, so
    # its PO quantity was real, uncounted supply until now - adding it here nets it exactly
    # once, against the demand it was raised to cover.
    net = float(row["net_position"] or 0.0) + float(row.get("po_ordered") or 0.0)
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
        # The rate the candidate was priced with, carried through so the cash figure and
        # the frozen row use the SAME rate the ranking used.
        rate_to_base = _fnum(chosen.get("rate_to_base"))
        rate_as_of = chosen.get("rate_as_of")
    else:
        lead = float(tog["lead_time_default_days"])
        lead_src = "default"
        moq = order_multiple = var_lt = unit_cost = currency = None
        rate_to_base = rate_as_of = None

    ss, ss_used, ss_fallback = eng.safety_stock(
        ss_method, demand_rate=demand_rate, safety_days=safety_days,
        service_level=service_level, cv_d=cv, var_lt=var_lt, lead_time_days=lead,
        manual_value=_fnum(tog.get("safety_stock_manual")))
    rop = eng.reorder_point(demand_rate, lead, ss)
    if policy_type == "min_max" and max_override is not None:
        oup = float(max_override)
    else:
        oup = eng.order_up_to(rop, demand_rate, review_days)

    # S10 - the buyer's own level, when the resolved policy selects that basis. The forecast
    # ROP/OUP above are still computed and still frozen onto the row, because the buyer wants
    # to SEE what the industry-standard basis would have said; they simply no longer decide.
    lp, lp_basis = _last_purchase_for(last_cost or {}, pid, row.get("segment"))
    level_row = rl_service.resolve_level(levels or {}, pid, wid) or {}
    reorder_level = _fnum(level_row.get("level"))
    # A level nobody has set is not a level of zero. The row is emitted as `needs_level` so
    # the item is neither bought on a guess nor quietly dropped off the plan.
    needs_level = policy_type == "reorder_level" and reorder_level is None

    # --- the channel split of this location's need (front planning 5.3, AC-F07) -------
    #
    # Project need is FIRM, and firm means CONFIRMED: plan 5.3 defines it as "confirmed
    # unplaced Buy for Project-class lines fulfilled from w" and AC-E05 bypasses the
    # reorder trigger for "confirmed unplaced Project Buy". So the figure that skips the
    # netting is `project_confirmed_committed` - the un-linked remainder of raised Order
    # Inquiry rows - and nothing else.
    #
    # Since P3 (migration 424) that is the WHOLE Project column: the sheet leg is retired,
    # so `project_committed` and `project_confirmed_committed` are equal and there is no
    # unconfirmed project remainder left to net alongside Retail. A sheet-origin project
    # order nobody has decided is awaiting CS, and `demand_source_service` reports it.
    #
    # Retail need is therefore the ordinary calculation against a net position with the
    # firm channel taken back out of it and confirmed Project claims on stock removed -
    # otherwise Retail nets its own demand against stock a project has been promised.
    #
    # With no project demand and no project claim `retail_net` IS `net`, so a location
    # with only Retail demand plans byte for byte as it did before.
    project_committed = float(row.get("project_committed") or 0.0)
    project_need = float(row.get("project_confirmed_committed") or 0.0)
    project_supply_reduction = float(row.get("project_supply_reduction") or 0.0)
    retail_net = net + project_need - project_supply_reduction

    # on_cadence=True: in M3 every run counts as a review cadence (periodic_review always
    # gets to fire when below order-up-to). Real cadence scheduling (only fire on the SKU's
    # due review date) is future work.
    triggered, reason_label = eng.trigger(
        policy_type, net=retail_net, rop=rop, min_level=min_override, oup=oup,
        on_cadence=True, reorder_level=reorder_level)
    # On this basis the level IS the order-up-to: order the difference, nothing more.
    target = reorder_level if policy_type == "reorder_level" else oup
    # Unrounded on purpose: MOQ and the order multiple are applied ONCE, to the whole
    # need, below. Rounding the Retail half and then adding the Project half would apply
    # the supplier's terms to one channel and not the other.
    retail_need, _unrounded = eng.order_qty(
        triggered, net=retail_net, oup=target, moq=None, order_multiple=None)
    recommended = retail_need + project_need
    if project_need > 0 and not triggered:
        # Firm demand the netting never sees. Without this the location holds enough for
        # Retail, nothing triggers, and a confirmed customer commitment is never bought.
        triggered = True
        reason_label = (f"project buy: {_qty_label(project_need)} confirmed unplaced Buy "
                        f"at this location")
    rounded = (eng.round_order_qty(recommended, moq, order_multiple)
               if triggered and recommended > 0 else 0.0)
    if not triggered:
        recommended = 0.0
    doc = eng.days_of_cover(net, demand_rate)

    lm = last_move.get((pid, wid))
    lm_days = (today - lm).days if lm else None
    # Product-keyed: the purchase-history export names no location, so a per-warehouse
    # lookup would read "never bought" for exactly the stock this signal exists to judge.
    lb = (last_buy or {}).get(pid)
    lb_days = (today - lb).days if lb else None
    disp = eng.disposition(
        on_hand=on_hand, last_movement_days=lm_days, dead_stock_days=dead_days,
        days_of_cover_val=doc, overstock_days=overstock_days,
        last_purchase_days=lb_days)

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
        "rate_to_base": rate_to_base, "rate_as_of": rate_as_of,
        "ss": ss, "ss_used": ss_used, "ss_fallback": ss_fallback,
        # The channel breakdown of this location's need, frozen with everything else so
        # the product row can sum it and the drill can explain it (AC-F05, AC-F07).
        "project_need": project_need,
        "retail_need": retail_need,
        "project_supply_reduction": project_supply_reduction,
        "retail_net": retail_net,
        # front-planning follow-up (19-20 Aug): the RAW `committed_v` split, i.e. this
        # location's OPEN demand by channel. The product view sums these across locations
        # for its channel columns, and the two sum to `outstanding_sales` (== `committed`)
        # the same way `committed_v` guarantees.
        "project_committed": project_committed,
        "retail_committed": float(row.get("retail_committed") or 0.0),
        "rop": rop, "oup": oup, "triggered": triggered, "reason_label": reason_label,
        "recommended": recommended, "rounded": rounded, "doc": doc,
        "disposition": disp, "confidence": conf, "sample_size": sample_size,
        # Carried so the reason can quote the actual age rather than assert one.
        "last_purchase_days": lb_days,
        "supplier_reason": sel.get("reason"),
        "selection": tog["supplier_selection"],
        "overstock": bool(disp and disp["type"] == "overstock"),
        # "Short" means short of whatever the ACTIVE basis plans against, so the shortage
        # count on the page agrees with the buys beneath it.
        "short": net < (reorder_level if policy_type == "reorder_level"
                        and reorder_level is not None else rop),
        # S10 - carried onto the frozen row so the buyer sees their number, our suggestion,
        # and where the number came from, without a second query.
        "reorder_level": reorder_level,
        "reorder_level_source": level_row.get("source"),
        "suggested_level": _fnum(level_row.get("suggested_level")),
        "suggestion_basis": level_row.get("suggestion_basis"),
        "needs_level": needs_level,
        # M4 cash-ranking factor inputs (list_price read-only from products; committed
        # from the net-position view) - frozen into `inputs` for the cash stage.
        "list_price": _fnum(row.get("list_price")),
        "committed": _fnum(row.get("committed")),
        # S10 - the figures the buyer looks up by hand before deciding. Carried on the cell
        # so the row answers "should I order this" without a second screen.
        # Where the daily rate came from: N units delivered over the window. Without it the
        # rate is a number the reader has to take on faith.
        "demand_window_days": _fnum(row.get("window_days")),
        "on_hand": _fnum(row.get("quantity_on_hand")),
        # Stock physically sitting at a bin this location's pool feeds - NOT counted in
        # `on_hand` (captain, 20 Aug), but never dropped from the screen either: the buyer
        # can still see where it sits. 0.0 at a pool root, the bin's own quantity at a bin.
        "project_on_hand": _fnum(row.get("project_on_hand")),
        "on_order": _fnum(row.get("on_order")),
        "po_ordered": _fnum(row.get("po_ordered")),
        "segment": row.get("segment"),
        "master_reorder_level": _fnum(row.get("master_reorder_level")),
        "master_reorder_quantity": _fnum(row.get("master_reorder_quantity")),
        # The last price, and HOW it was attributed. The second half is the honest part:
        # most purchase history names no destination, so a dealer row is usually shown an
        # unattributed price and has to be told so.
        "last_purchase": lp,
        "last_purchase_basis": lp_basis,
    }


def _emit_cell(run_id: str, row: dict, c: dict,
               transfer_flag: Optional[str]) -> list[ReorderRecommendation]:
    """Turn one computed SKU×warehouse cell into 0..2 persisted recommendations."""
    out: list[ReorderRecommendation] = []
    chosen = c["chosen"]
    disp = c["disposition"]
    wid = str(row["warehouse_id"])

    def _basis(shares: Optional[dict] = None, *, recommended=None, rounded=None) -> dict:
        """This cell's sizing group, in the ONE shape the product freeze reads.

        Per-warehouse scope makes every cell its own group: one location, sized on itself.
        A cell that sized no purchase (needs_level / exception / covered) still states its
        group, because its channel needs are a demand statement - the product row has to
        show them and the drill has to name the location - and it simply took no share of
        a buy, which is what the empty ``shares`` says.
        """
        return _plan_basis(wid, "location", [row], [c], shares or {},
                           retail_need=float(c.get("retail_need") or 0.0),
                           recommended=recommended, rounded=rounded)

    # #8: a cell classified for disposition (dead OR overstock) must NOT also emit a buy
    # - buying more of dead/overstocked stock is contradictory. The disposition rec
    # below is the single action for that cell.
    # A triggered cell whose order qty rounds to 0 (net already at/above order-up-to
    # once MOQ/multiple are applied) is NOT an actionable buy - "buy 0" is noise, so
    # emit nothing. Mirrors the network path's `rounded > 0` gate (line ~516).
    rounded = c["rounded"] or 0
    if not disp and c.get("needs_level"):
        # S10 - the plan runs on a level nobody has set for this item. Proposing a quantity
        # would be a guess and omitting the row would read as "nothing to do here", so it is
        # emitted as its own kind, carrying the suggestion and the months behind it. One
        # click on that row turns it into a plannable item next run.
        out.append(_build_rec(run_id, "needs_level", row, c,
                              warehouse_id=wid,
                              order_qty=None, rounded=None,
                              reason_enum="needs_level",
                              reason_label=_needs_level_label(c),
                              plan_basis=_basis()))
    elif not disp and c["triggered"] and rounded > 0:
        if chosen:
            out.append(_build_rec(run_id, "buy", row, c, warehouse_id=wid,
                                  order_qty=c["recommended"], rounded=c["rounded"],
                                  # The degenerate group: one location, sized on itself,
                                  # taking its whole buy. Stated in the SAME shape a pool
                                  # or a network buy states, so the product freeze has
                                  # one thing to read rather than three.
                                  plan_basis=_basis({wid: rounded},
                                                    recommended=c["recommended"],
                                                    rounded=c["rounded"])))
        else:
            # The sharpest case for carrying a basis on a row that buys nothing: a
            # location holding CONFIRMED unplaced Project Buy with no linked supplier
            # triggers and then cannot be sourced, so without this its firm demand
            # reaches no product row at all (AC-E04, AC-E06).
            out.append(_build_rec(run_id, "exception", row, c,
                                  warehouse_id=wid,
                                  order_qty=None, rounded=None,
                                  reason_label="no linked supplier - cannot source this reorder",
                                  plan_basis=_basis()))
    elif not disp:
        # Same rule as the pool path: stock covering the demand is a SUGGESTION, and
        # writing nothing here would silently decide "use stock" for the single-location
        # case, which is most of the catalogue. A cell already destined for disposition is
        # excluded - "buy more of this dead stock" is the contradiction the gate above
        # exists to prevent, and offering it as a choice is the same contradiction.
        covered = _covered_rec(run_id, wid, [row], row, c,
                               moq=_fnum(c.get("moq")),
                               order_multiple=_fnum(c.get("order_multiple")),
                               plan_basis=_basis())
        if covered is not None:
            out.append(covered)

    # disposition (dead / overstock)
    if disp:
        action = "discontinue" if disp["type"] == "dead" else "hold"
        label = _disposition_label(disp["type"], c, disp.get("basis"))
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
                  today: date, last_move: dict, wh_meta: dict,
                  last_buy: Optional[dict] = None,
                  rates: Optional[dict] = None,
                  levels: Optional[dict] = None,
                  last_cost: Optional[dict] = None) -> list[ReorderRecommendation]:
    recs: list[ReorderRecommendation] = []
    rates = load_rates(db) if rates is None else rates
    by_product: dict[str, list[dict]] = {}
    for r in rows:
        by_product.setdefault(str(r["product_id"]), []).append(r)

    for pid, prows in by_product.items():
        cands = eng.load_supplier_candidates(db, pid, rates=rates)
        # per-warehouse cells (drive disposition + transfer flags + allocation demand)
        computed = [_compute_cell(db, r, policies, cands, today, last_move, last_buy,
                                  levels=levels, last_cost=last_cost)
                    for r in prows]
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
                      "net": float(c.get("retail_net", r["net_position"]) or 0.0)}
                     for r, c in zip(prows, computed)]
        project_by_wid = {str(r["warehouse_id"]): float(c.get("project_need") or 0.0)
                          for r, c in zip(prows, computed)}
        network_project_need = sum(project_by_wid.values())
        policy_type = policy.get("policy_type") or "reorder_point"
        # S10 - same rule as the pool path: the network target is the sum of the levels the
        # buyer owns, and a location with no level is named rather than guessed at.
        net_levels = None
        # Collected here, emitted after the network has been sized, so each row can carry
        # the network's own basis; they still come first in this product's rows.
        unset_levels: list[tuple[dict, dict]] = []
        if policy_type == "reorder_level":
            net_levels = {str(r["warehouse_id"]): c.get("reorder_level")
                          for r, c in zip(prows, computed)}
            unset_levels = [(r, c) for r, c in zip(prows, computed)
                            if c.get("reorder_level") is None]

        agg = eng.aggregate_network(wh_inputs, lead_time_days=lead, safety_days=safety_days,
                                    review_days=review_days, moq=moq,
                                    order_multiple=order_multiple, levels=net_levels)

        # Gate the network buy on the SAME policy trigger as per-warehouse, computed on
        # the AGGREGATE (net vs agg-ROP / agg-min / agg-OUP). Sizing the buy is NOT a
        # trigger: a cell above ROP but below OUP under a reorder_point policy must NOT
        # buy (matches per-warehouse), and min_max/periodic get their own gate + honest
        # label instead of a hardcoded "net ≤ ROP".
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
            min_level=min_override, oup=target_oup, on_cadence=True,
            reorder_level=(float(agg["reorder_point"]) if net_levels is not None else None))
        retail_recommended, _unrounded = eng.order_qty(
            triggered, net=agg_net, oup=target_oup, moq=None, order_multiple=None)
        recommended = retail_recommended + network_project_need
        if network_project_need > 0 and not triggered:
            triggered = True
            reason_label = (f"project buy: {_qty_label(network_project_need)} confirmed "
                            f"unplaced Buy on the network")
        rounded = (eng.round_order_qty(recommended, moq, order_multiple)
                   if triggered and recommended > 0 else 0.0)
        if not triggered:
            recommended = 0.0
        for w in agg["warehouses"]:
            w["deficit"] = float(w.get("deficit") or 0.0) + project_by_wid.get(
                str(w["warehouse_id"]), 0.0)

        first = prows[0]
        agg_cell = _network_agg_cell(policy, tog, chosen, alt_choices, agg, lead, moq,
                                     order_multiple, prows,
                                     supplier_reason=sel.get("reason"),
                                     policy_type=policy_type,
                                     min_override=min_override, max_override=max_override,
                                     target_oup=target_oup, triggered=triggered,
                                     reason_label=reason_label, recommended=recommended,
                                     rounded=rounded, cells=computed)
        # The network buy names NO warehouse, so without this the product row's only
        # location evidence is one nameless entry with every shared fact null, and its
        # netted replenishment reads as the sum of member cells that individually never
        # triggered (AC-F08). Built for the unsourceable and the un-levelled network too:
        # those rows carry the same demand, and only the purchase is missing.
        allocation_map = (eng.allocate(rounded, agg["warehouses"])
                          if triggered and rounded > 0 else {})
        network_basis = _plan_basis("network", "network", prows, computed, allocation_map,
                                    retail_need=retail_recommended,
                                    recommended=recommended, rounded=rounded)
        for r, c in unset_levels:
            recs.append(_build_rec(run_id, "needs_level", r, c,
                                   warehouse_id=str(r["warehouse_id"]),
                                   order_qty=None, rounded=None,
                                   reason_enum="needs_level",
                                   reason_label=_needs_level_label(c),
                                   plan_basis=network_basis))
        if triggered and rounded > 0 and chosen:
            allocation = _allocation_lines(allocation_map, wh_meta)
            recs.append(_build_rec(run_id, "buy", first, agg_cell, warehouse_id=None,
                                   order_qty=recommended, rounded=rounded,
                                   allocation=allocation,
                                   plan_basis=network_basis))
        elif triggered and rounded > 0 and not chosen:
            recs.append(_build_rec(
                run_id, "exception", first, agg_cell, warehouse_id=None,
                order_qty=None, rounded=None,
                reason_label="no linked supplier - cannot source this network reorder",
                plan_basis=network_basis))

        # --- per-warehouse disposition recs (dead/overstock) ---
        for r, cell in zip(prows, computed):
            disp = cell["disposition"]
            if disp:
                action = "discontinue" if disp["type"] == "dead" else "hold"
                label = _disposition_label(disp["type"], cell, disp.get("basis"))
                recs.append(_build_rec(run_id, "disposition", r, cell,
                                       warehouse_id=str(r["warehouse_id"]),
                                       order_qty=None, rounded=None,
                                       reason_enum=disp["type"], reason_label=label,
                                       disposition_action=action,
                                       transfer_flag=flags.get(str(r["warehouse_id"]))))
    return recs


def _network_agg_cell(policy, tog, chosen, alt_choices, agg, lead, moq, order_multiple,
                      prows, *, supplier_reason: Optional[dict] = None,
                      policy_type: str, min_override: Optional[float],
                      max_override: Optional[float], target_oup: float, triggered: bool,
                      reason_label: Optional[str], recommended: float,
                      rounded: float, cells: Optional[list[dict]] = None) -> dict:
    """Assemble the frozen-cell dict for a network aggregate buy (fixed_days SS).

    The trigger / order-up-to target / qty are computed by the caller on the aggregate
    against the RESOLVED policy_type, so ``reason_label`` and ``policy_type`` here are
    honest (no hardcoded "net ≤ ROP").
    """
    agg_demand = agg["agg_demand"]
    # #9: match the per-warehouse supplier-adequacy definition - a chosen supplier only
    # counts as adequate when its measured confidence is high|medium.
    supplier_adequate = bool(chosen) and (chosen.get("supplier_confidence") in ("high", "medium"))
    return {
        "policy": policy, "chosen": chosen, "alt_choices": alt_choices,
        "supplier_reason": supplier_reason,
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
        "rate_to_base": _fnum(chosen.get("rate_to_base")) if chosen else None,
        "rate_as_of": chosen.get("rate_as_of") if chosen else None,
        "ss": agg["safety_stock"], "ss_used": "fixed_days", "ss_fallback": None,
        # Summed across the aggregated locations: channel is a breakdown of the demand,
        # never a second supply row, so the shared facts above are still counted once.
        "project_need": sum(float(c.get("project_need") or 0.0) for c in (cells or [])),
        "retail_need": sum(float(c.get("retail_need") or 0.0) for c in (cells or [])),
        "project_supply_reduction": sum(
            float(c.get("project_supply_reduction") or 0.0) for c in (cells or [])),
        "retail_net": agg["agg_net"],
        # Same additivity as the need columns above: the raw committed split sums across
        # the aggregated locations.
        "project_committed": sum(
            float(c.get("project_committed") or 0.0) for c in (cells or [])),
        "retail_committed": sum(
            float(c.get("retail_committed") or 0.0) for c in (cells or [])),
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
# the sizing group's own basis (front planning 5.3, AC-F03, AC-F07, AC-F08)
# ===========================================================================

def _plan_basis(group: str, scope: str, prows: list[dict], cells: list[dict],
                shares: dict, *, retail_need: float,
                recommended: Optional[float], rounded: Optional[float]) -> dict:
    """What ONE sizing group was sized on, and the locations it read.

    A buy is sized against a GROUP of locations - one on its own, the members of a
    fulfilment pool, or the whole network - and the product row has to be able to state
    that group's figures without re-deriving them from the recommendation rows the group
    happened to emit. Two things went wrong when it tried:

    * a network buy emits ONE row with no warehouse at all, so the product's location
      evidence had a single nameless entry and the drill rendered a row with no identity
      (AC-F08);
    * a pool or network buy is netted on the AGGREGATE, so summing the member cells' own
      `retail_need` answers a different question - each member was measured against its own
      trigger and can be 0 while the group is short 213 (AC-F03: one calculation, two
      presentations).

    So the group states itself: its own netted replenishment (`retail_need`, the figure
    the aggregate was actually sized on), its firm Project Buy, and every member location
    it covered - INCLUDING the
    ones the split gave nothing to, because a location's channel needs are a demand
    statement and not an allocation statement.

    ``group`` is the dedupe key: the sibling rows of one pooled buy all carry the same
    basis, and the product freeze must count it once. ``shares`` is the engine's own split
    of its once-rounded buy, ``{warehouse_id: qty}``.
    """
    locations = []
    for r, c in zip(prows, cells):
        wid = str(r["warehouse_id"])
        locations.append({
            # Kept for the allocator replay, which needs a location it can address; the
            # read endpoint copies code and name only, so no UUID reaches a screen.
            "warehouse_id": wid,
            "warehouse_code": r.get("warehouse_code"),
            "warehouse_name": r.get("warehouse_name"),
            "project_need": _r(c.get("project_need")) or 0.0,
            "retail_need": _r(c.get("retail_need")) or 0.0,
            # Shared facts of the product-location, carrying no channel dimension.
            "on_hand": _fnum(c.get("on_hand")),
            # Visible-but-not-counted: stock at a project-held bin (captain, 20 Aug).
            "project_on_hand": _fnum(c.get("project_on_hand")),
            "incoming_spo": _fnum(c.get("on_order")),
            "on_order_po": _fnum(c.get("po_ordered")),
            "reorder_level": _fnum(c.get("reorder_level")),
            "avg_daily_demand": _r(c.get("demand_rate")),
            # This location's share of the group's once-rounded buy. 0 is a real answer:
            # the location asked for nothing, not that it was left out.
            "location_suggested_qty": float(shares.get(wid) or 0.0),
        })
    locations.sort(key=lambda x: (x["warehouse_code"] or ""))
    return {
        "group": group,
        "scope": scope,
        # Project is additive across locations, so the group's figure IS the sum of its
        # members'. Retail is not: it is netted once, on the aggregate, and only the
        # aggregate knows what it sized.
        "project_need": _r(sum(l["project_need"] for l in locations)),
        "retail_need": _r(retail_need) or 0.0,
        "recommended": _r(recommended),
        "rounded": _r(rounded),
        "locations": locations,
    }


# ===========================================================================
# recommendation builder (freezes inputs)
# ===========================================================================

def _build_rec(run_id: str, rec_type: str, row: dict, c: dict, *,
               warehouse_id: Optional[str], order_qty: Optional[float],
               rounded: Optional[float], allocation: Optional[list] = None,
               reason_enum: Optional[str] = None, reason_label: Optional[str] = None,
               disposition_action: Optional[str] = None,
               transfer_flag: Optional[str] = None,
               plan_basis: Optional[dict] = None) -> ReorderRecommendation:
    chosen = c["chosen"]
    reason = reason_enum or _reason_enum(c["policy_type"])
    label = reason_label if reason_label is not None else c.get("reason_label")
    unit_cost = c.get("unit_cost")
    rate = c.get("rate_to_base")
    rate_as_of = c.get("rate_as_of")
    # A ``covered`` row is priced too, because "buy anyway" needs a figure to weigh against
    # using the stock. It is NOT a purchase, so it never reaches the run's cash total or the
    # Buy count - both of those select rec_type='buy' explicitly.
    cash_impact = (_cash_impact_in_base(rounded, unit_cost, c.get("currency"),
                                        rate, rate_as_of)
                   if rec_type in ("buy", "covered") else None)

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
        # S10 - the buyer's number, our suggestion, and the arithmetic behind it. Frozen so
        # the row still explains itself after the level is edited next week.
        "reorder_level": c.get("reorder_level"),
        "reorder_level_source": c.get("reorder_level_source"),
        "suggested_level": c.get("suggested_level"),
        "suggestion_basis": c.get("suggestion_basis"),
        # The weekly checklist, frozen with the row so it still reads true next month.
        "demand_window_days": c.get("demand_window_days"),
        "on_hand": c.get("on_hand"),
        # Visible-but-not-counted (captain, 20 Aug): stock at a project-held bin, kept
        # beside `on_hand` so a pool-only figure never reads as stock going missing.
        "project_on_hand": c.get("project_on_hand"),
        "on_order": c.get("on_order"),
        "po_ordered": c.get("po_ordered"),
        "segment": c.get("segment"),
        "master_reorder_level": c.get("master_reorder_level"),
        "master_reorder_quantity": c.get("master_reorder_quantity"),
        "last_purchase": c.get("last_purchase"),
        "last_purchase_basis": c.get("last_purchase_basis"),
        "cv_d": c.get("cv"),
        "var_lt": c.get("var_lt"),
        "demand_rate": _r(c.get("demand_rate")),
        "net": _r(c.get("net")),
        # Front planning 5.3 / AC-F07: the SAME location row states its Project and Retail
        # need separately while stock, incoming and the reorder level above stay single
        # shared facts of the product-location. The order this row proposes is
        # `project_need + retail_need` rounded once at the supplier's terms; `retail_net`
        # is the position the Retail half was netted against, so the whole derivation is
        # reproducible from the snapshot (AC-M3.11) rather than only the half of it that
        # predates channels. `project_need` is the un-linked remainder of raised Order
        # Inquiry rows, which since P3 is the entire Project reading.
        "project_need": _r(c.get("project_need")),
        "retail_need": _r(c.get("retail_need")),
        "project_supply_reduction": _r(c.get("project_supply_reduction")),
        "retail_net": _r(c.get("retail_net")),
        # front-planning follow-up (19-20 Aug): the raw `committed_v` split - this row's
        # OPEN demand by channel. The product view's channel columns sum these across
        # locations and the two always sum to `committed` above.
        "project_committed": _r(c.get("project_committed")),
        "retail_committed": _r(c.get("retail_committed")),
        # The SIZING GROUP this buy belongs to, and the locations it was sized over
        # (`_plan_basis`). The four channel figures above describe THIS row's place; the
        # basis describes the decision, which for a pool or a network buy spans more
        # places than the row names - including ones the split gave nothing to. The
        # product freeze reads this and nothing else, so Product and Location can only
        # ever be two presentations of one calculation (AC-F03, AC-F07, AC-F08).
        "plan_basis": plan_basis,
        # M4 cash-ranking factor inputs (frozen for the cash stage + explainability).
        "list_price": c.get("list_price"),
        "committed": c.get("committed"),
        "on_cadence": True,
        "selection": c.get("selection"),
        "sample_size": c.get("sample_size"),
        "supplier": _supplier_choice(chosen) if chosen else None,
        "alternatives": c.get("alt_choices") or [],
        # Why this supplier and not the runner-up, frozen at run time so the popup states
        # the reason rather than re-deriving it from figures that may since have moved.
        "supplier_reason": c.get("supplier_reason"),
        "disposition_action": disposition_action,
        "transfer_flag": transfer_flag,
        "is_exception": rec_type == "exception",
        # Only on a ``covered`` row: the two numbers the choice turns on.
        "covered_committed": _r(c.get("covered_committed")),
        "covered_available": _r(c.get("covered_available")),
        # How much of this row's demand arrived with no stated location. A planner looking
        # at a buy against BRW deserves to know part of it is demand nobody located, since
        # that is the part most likely to be wrong.
        "unlocated_demand": _r(row.get("unlocated_added")),
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
        # Frozen so a plan printed today still explains its own figures after somebody
        # updates the rate tomorrow.
        rate_to_base=rate,
        rate_as_of=rate_as_of,
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
        # Where the figure came from, so a buyer can tell a quote from a receipt:
        # `last_po` (what we paid, with the order number and date beside it), `contract`
        # (a typed figure on product_suppliers), or absent when nobody knows.
        "unit_cost_source": cand.get("unit_cost_source"),
        "unit_cost_ref": cand.get("unit_cost_ref"),
        "unit_cost_at": (
            cand["unit_cost_at"].isoformat() if cand.get("unit_cost_at") else None
        ),
        "currency": cand.get("currency"),
        # The same price restated in the base currency, which is the figure the ranking
        # actually used. Both travel so the popup can show what we pay AND what it costs
        # us to compare, and so a missing rate is visible rather than inferred from a gap.
        "unit_cost_base": _fnum(cand.get("unit_cost_base")),
        "base_currency": cand.get("base_currency") or BASE_CURRENCY,
        "rate_to_base": _fnum(cand.get("rate_to_base")),
        "rate_as_of": (cand["rate_as_of"].isoformat() if cand.get("rate_as_of") else None),
        "missing_rate_currency": cand.get("missing_rate_currency"),
        "lead_time_days": _fnum(cand.get("lead_time_days")),
        "composite_score": _fnum(cand.get("composite_score")),
        "is_primary": bool(cand.get("is_primary")),
        # M5-prep - scorecard detail for the "why this supplier" popover (all already
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


def _disposition_label(kind: str, c: dict, basis: Optional[str] = None) -> str:
    if kind == "dead":
        if basis == "ageing":
            days = c.get("last_purchase_days")
            # The age is quoted rather than asserted: "bought 1,876 days ago and has never
            # moved" is a fact somebody can check, and it is the whole argument for the call.
            return (f"dead stock: bought {int(days):,} days ago and has never moved"
                    if days is not None
                    else "dead stock: bought before the dead-stock window and has never moved")
        return "dead stock: no movement in the dead-stock window"
    doc = c.get("doc")
    return f"overstock: runway of {doc:g} days exceeds the ceiling" if doc is not None \
        else "overstock: runway exceeds the ceiling"


def _reason_enum(policy_type: Optional[str]) -> str:
    if policy_type in ("reorder_point", "periodic_review", "min_max", "reorder_level"):
        return policy_type
    return "reorder_point"


def _needs_level_label(c: dict) -> str:
    """Why this row is asking rather than proposing, with the suggestion in the sentence."""
    suggested = c.get("suggested_level")
    basis = c.get("suggestion_basis") or {}
    if suggested is None:
        return "no reorder level set, and there is no movement history to suggest one from"
    if basis.get("no_movement"):
        return (f"no reorder level set. Nothing moved in the last "
                f"{basis.get('months_studied', 3)} months, so the suggestion is 0")
    avg = basis.get("avg_monthly")
    cover = basis.get("cover_months")
    if avg is not None and cover is not None:
        return (f"no reorder level set. {avg:g} a month over "
                f"{basis.get('months_studied', 3)} months x {cover:g} months cover "
                f"suggests {suggested:g}")
    return f"no reorder level set. The suggestion is {suggested:g}"


def _cash_impact_in_base(rounded, unit_cost, currency, rate, rate_as_of) -> Optional[float]:
    """What this buy draws from the budget, in the BASE currency, or nothing.

    The budget is a single pot of ringgit. A USD buy counted at its face value consumes a
    quarter of what it really costs, so the plan funds more than the money on hand. When the
    price cannot be converted the honest answer is no figure at all: that lands the buy in
    the same needs-attention bucket an unpriced buy already lands in, where a human looks at
    it, rather than in "funded" at a made-up price.

    A recorded zero is a cost OF zero and funds at zero - it is not unknown.
    """
    if rounded is None or unit_cost is None:
        return None
    code = normalize_currency(currency)
    rates = ({} if rate is None
             else {code: Rate(currency=code, rate_to_base=float(rate), as_of=rate_as_of)})
    conv = to_base(float(unit_cost), code, rates)
    if conv.amount is None:
        return None
    return round(float(rounded) * conv.amount, 2)


# ===========================================================================
# M4 cash stage - freeze rank_score + rank on the buy recommendations
# ===========================================================================

def load_cash_weights(db: Session) -> dict:
    """Weights from the single active ``scm.cash_ranking_policy`` row; falls back to
    the seeded defaults when none is present (fresh install pre-migration seed)."""
    row = db.execute(text(
        "SELECT weight_urgency, weight_margin, weight_abc, weight_priority, "
        "       weight_committed, weight_market "
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
        "market": _wf(row["weight_market"], "market"),
    }


def _wf(v, key: str) -> float:
    return float(v) if v is not None else float(cash_ranking.DEFAULT_WEIGHTS[key])


def _market_values_for_recs(
    db: Session, buys: list[ReorderRecommendation]
) -> dict[str, tuple[Optional[float], Optional[str]]]:
    """Per BUY product, the normalized market-trend priority + the signal summary (M7).
    Matches the latest ``scm.market_signal`` on the product's category **id OR code**
    (the same both-ways match the advisory uses). Returns product_id → (market_value,
    summary); market_value is ``None`` when no signal matches (factor then dropped)."""
    product_ids = list({str(r.product_id) for r in buys if r.product_id})
    if not product_ids:
        return {}
    rows = db.execute(
        text(
            "SELECT p.id::text AS pid, p.category_id::text AS cat_id, pc.category_code AS code "
            "FROM products p LEFT JOIN product_categories pc ON pc.id = p.category_id "
            "WHERE p.id::text = ANY(:ids)"
        ),
        {"ids": product_ids},
    ).mappings().all()
    refs: set[str] = set()
    for x in rows:
        if x["cat_id"]:
            refs.add(x["cat_id"])
        if x["code"]:
            refs.add(x["code"])
    if not refs:
        return {}
    sig_rows = db.execute(
        text(
            "SELECT DISTINCT ON (category_ref) category_ref, trend, summary "
            "FROM scm.market_signal WHERE category_ref = ANY(:refs) "
            "ORDER BY category_ref, captured_at DESC NULLS LAST, created_at DESC"
        ),
        {"refs": list(refs)},
    ).mappings().all()
    by_ref = {s["category_ref"]: (s["trend"], s["summary"]) for s in sig_rows}
    out: dict[str, tuple[Optional[float], Optional[str]]] = {}
    for x in rows:
        hit = by_ref.get(x["cat_id"]) or by_ref.get(x["code"])
        if hit:
            trend, summary = hit
            out[x["pid"]] = (cash_ranking.market_value(trend), summary)
        else:
            out[x["pid"]] = (None, None)
    return out


def _apply_cash_stage(
    db: Session, recs: list[ReorderRecommendation], include_market: bool = False
) -> None:
    """Compute + FREEZE the cash-ranking fields on the run's BUY recs (M4-D1/D14):
    each buy's graceful-degrade ``rank_score`` + its factor vector + days-to-stockout
    (into ``inputs``), then a dense ``rank`` by rank_score desc (tiebreak cash_impact
    then product_code). Non-buy recs are untouched. Funded/deferred is NOT decided
    here - it is applied live at view-time against a budget (M4-D2/D3).

    ``include_market`` (M7): when true, each buy's category is matched to the latest
    market signal and a bounded market-trend factor joins the rank score (order qty is
    untouched - only the funding order shifts). When false, no market factor is added
    and the score is byte-identical to pre-M7."""
    weights = load_cash_weights(db)
    buys = [r for r in recs if r.rec_type == "buy"]
    market = _market_values_for_recs(db, buys) if include_market else {}
    for r in buys:
        inp = dict(r.inputs or {})
        mv, msummary = market.get(str(r.product_id), (None, None))
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
            market_signal_value=mv,
        )
        r.rank_score = round(cash_ranking.rank_score(factors), 6)
        inp["rank_factors"] = [f.as_dict() for f in factors]
        if mv is not None:
            # Freeze the signal that moved this rank so "why this rank" can name it.
            inp["market_factor"] = {"value": mv, "summary": msummary}
        inp["days_to_stockout"] = cash_ranking.days_to_stockout(
            _fnum(r.net_position), _fnum(r.forecast_daily_demand), _fnum(r.days_of_cover))
        r.inputs = inp

    ordered = sorted(buys, key=lambda r: cash_ranking.rank_sort_key(
        float(r.rank_score or 0.0), _fnum(r.cash_impact), (r.inputs or {}).get("sku")))
    for i, r in enumerate(ordered, start=1):
        r.rank = i


# ===========================================================================
# M4 funding allocation - greedy-by-rank over a run's buys (view-time + persist)
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


def _decision_split(db: Session, run_id: str) -> tuple[set[str], set[str]]:
    """The run's buy recs partitioned by decision-overlay status (M8-C3): pinned =
    accepted/adjusted (force-funded), rejected = dismissed (excluded). Proposed recs are
    in neither set (they reshuffle with the budget)."""
    rows = db.execute(text(
        "SELECT id, status FROM scm.reorder_recommendation "
        "WHERE run_id = :rid AND rec_type = 'buy'"
    ), {"rid": run_id}).mappings().all()
    pinned = {str(r["id"]) for r in rows if r["status"] in ("accepted", "adjusted")}
    rejected = {str(r["id"]) for r in rows if r["status"] == "dismissed"}
    return pinned, rejected


def allocate_run_budget(db: Session, run_id: str,
                        budget: Optional[float]) -> cash_ranking.AllocationResult:
    """Greedy funding over the run's buys for ``budget`` - VIEW-TIME, no persistence.
    Applies the decision overlay (pins win, rejects excluded) so the live view matches
    the persisted split (M8-C3)."""
    pinned, rejected = _decision_split(db, run_id)
    return cash_ranking.allocate_funding(
        _load_run_buys(db, run_id), budget,
        pinned_ids=pinned, rejected_ids=rejected)


def apply_run_budget(db: Session, run_id: str, budget: Optional[float],
                     *, full: bool = False) -> dict:
    """PERSIST the funding split for ``budget``: stamps ``funding_status`` on every buy
    rec + ``budget_amount`` on the run (so a shared run shows one funded set). Derives
    pins (accepted/adjusted) + rejects (dismissed) from the decision overlay so the
    PERSISTED split matches the live FE split (M8-C3). ``full`` (or ``budget`` None) funds
    every costed buy within/regardless of budget (the daily-cron path). Rejected recs are
    excluded from the split and have their ``funding_status`` cleared. Returns the roll-up
    counts + funded/deferred cash."""
    pinned, rejected = _decision_split(db, run_id)
    result = cash_ranking.allocate_funding(
        _load_run_buys(db, run_id), budget,
        pinned_ids=pinned, rejected_ids=rejected, full=full)
    for rec_id, status in result.status_by_id.items():
        db.execute(text(
            "UPDATE scm.reorder_recommendation SET funding_status = :s WHERE id = :id"
        ), {"s": status, "id": rec_id})
    # Rejected buys are out of the plan - clear any stale funding_status so a later read
    # never shows a dismissed rec as funded/deferred (it reads the decision overlay).
    if rejected:
        db.execute(text(
            "UPDATE scm.reorder_recommendation SET funding_status = NULL "
            "WHERE id::text = ANY(:ids)"
        ), {"ids": list(rejected)})
    budget_amount = None if (full or budget is None) else float(budget)
    db.execute(text(
        "UPDATE scm.reorder_run SET budget_amount = :b WHERE id = :rid"
    ), {"b": budget_amount, "rid": run_id})
    db.commit()
    return {
        "run_id": run_id,
        "budget": budget_amount,
        "funded_count": result.funded_count,
        "deferred_count": result.deferred_count,
        "needs_cost_count": result.needs_cost_count,
        "funded_cash": result.funded_cash,
        "deferred_cash": result.deferred_cash,
    }


def explain_net(db: Session, rec_id: str) -> dict:
    """M8-A1 net-breakdown drill for a recommendation.

    Returns the five position components (on_hand / on_order / po_ordered / committed /
    net) for the rec's product×warehouse plus the OPEN sales-order lines behind
    ``committed`` - each navigable (SO number, customer, qty, order date) rather than a
    pre-aggregated total.

    Positions come from ``scm.net_position_v`` (the SAME source the run froze
    ``net_position`` from) plus ``scm.po_ordered_v`` for the ``po_ordered`` leg (21 Aug
    fix - the sizing engine has netted this leg into the recommendation's own ``net``
    since ``_compute_cell`` started adding it; the drill now matches); the committed
    lines come from the base ``sales_order_lines`` tables. All apply the identical filter
    (``status='open' AND qty_ordered > qty_delivered``) so the listed line qtys sum to
    ``committed``, and ``on_hand + on_order + po_ordered - committed == net`` holds.
    Read-only; no numeric write anywhere.
    """
    # Raw SQL, so company-scoped by hand: a recommendation id from another company's plan
    # must read as absent, not as a net breakdown of stock this caller cannot see.
    co, co_params = company_sql_predicate(db, "company_id", param_prefix="cnb")
    rec = db.execute(text(
        "SELECT product_id, warehouse_id FROM scm.reorder_recommendation "
        f"WHERE id = :id AND {co or 'true'}"
    ), {"id": rec_id, **co_params}).mappings().first()
    if not rec:
        raise AppException(status_code=404, message="Recommendation not found.")
    return net_breakdown(
        db,
        str(rec["product_id"]),
        str(rec["warehouse_id"]) if rec["warehouse_id"] is not None else None,
    )


def net_breakdown(db: Session, product_id: str,
                  warehouse_id: Optional[str]) -> dict:
    """Net components + open-SO-line contributors for a product (+ optional warehouse).

    ``po_ordered`` (captain, 20-21 Aug: "for reorder plan need to deduct both SPO and PO
    to determine the suggested quantity") is a leg the sizing engine (``_compute_cell``)
    has netted into the frozen figure it actually decided the recommendation against
    since that fix landed - ``net = net_position + po_ordered``. This drill used to stop
    at ``on_hand + on_order - committed``, which is a DIFFERENT, smaller number than the
    one the recommendation was sized off, so the popup could read "Net -1,141" beside a
    PO leg of 3,642 for the exact same shortage and the two would not explain each other.
    ``net`` here is now recomputed the SAME way the engine computes it (``on_hand +
    on_order + po_ordered - committed``), with ``po_ordered`` surfaced as its own key so
    the arithmetic is honest and re-derivable rather than asserted. The other three keys
    are unchanged (contract note: a caller pinned to the old 4-key shape now sees a 5th
    key; the old three legs and their meanings do not change).

    When ``warehouse_id`` is None (a network rec) positions are summed across all of the
    product's warehouse cells and the committed SO lines are listed network-wide."""
    wh_pos = "AND warehouse_id = :wid" if warehouse_id else ""
    params: dict[str, Any] = {"pid": product_id}
    if warehouse_id:
        params["wid"] = warehouse_id
    pos = db.execute(text(f"""
        SELECT COALESCE(SUM(quantity_on_hand), 0) AS on_hand,
               COALESCE(SUM(on_order), 0)         AS on_order,
               COALESCE(SUM(committed), 0)        AS committed
        FROM scm.net_position_v
        WHERE product_id = :pid {wh_pos}
    """), params).mappings().first()

    # Same view `_planning_rows` reads for the S10 checklist column - "still to come" on
    # an open, not-fully-received PO line. Summed the same way (product, optional
    # warehouse) as the three legs above so all four are read off the identical scope.
    wh_po = "AND warehouse_id = :wid" if warehouse_id else ""
    po_ordered = db.execute(text(f"""
        SELECT COALESCE(SUM(ordered), 0) AS po_ordered
        FROM scm.po_ordered_v
        WHERE product_id = :pid {wh_po}
    """), params).scalar() or 0

    wh_sol = "AND sol.warehouse_id = :wid" if warehouse_id else ""
    sos = db.execute(text(f"""
        SELECT so.so_number,
               c.customer_name,
               so.order_date,
               (sol.qty_ordered - sol.qty_delivered) AS qty
        FROM sales_order_lines sol
        JOIN sales_orders so ON so.id = sol.sales_order_id
        LEFT JOIN customers c ON c.id = so.customer_id
        WHERE sol.product_id = :pid
          AND so.status = 'open'
          AND sol.qty_ordered > sol.qty_delivered
          {wh_sol}
        ORDER BY so.order_date DESC NULLS LAST, so.so_number
    """), params).mappings().all()

    on_hand = _fnum(pos["on_hand"]) or 0.0
    on_order = _fnum(pos["on_order"]) or 0.0
    committed = _fnum(pos["committed"]) or 0.0
    po_ordered_val = _fnum(po_ordered) or 0.0
    return {
        "on_hand": on_hand,
        "on_order": on_order,
        "po_ordered": po_ordered_val,
        "committed": committed,
        "net": on_hand + on_order + po_ordered_val - committed,
        "committed_sos": [{
            "so_number": r["so_number"],
            "qty": _fnum(r["qty"]),
            "customer_name": r["customer_name"],
            "order_date": r["order_date"].isoformat() if r["order_date"] else None,
        } for r in sos],
    }


# ===========================================================================
# MoQ override (20 Aug live test) - the buyer's own figure, recalculated live
# ===========================================================================

def effective_moq(inputs: Optional[dict], moq_override: Optional[float]) -> tuple[
        Optional[float], bool]:
    """(moq, is_override) - the buyer's own figure when set, else the frozen master
    value the engine rounded against at run time (``inputs.moq``)."""
    if moq_override is not None:
        return float(moq_override), True
    master = (inputs or {}).get("moq")
    return (float(master) if master is not None else None), False


def recalc_rounded_qty(recommended_qty, moq: Optional[float],
                       order_multiple) -> Optional[float]:
    """Re-derive ``rounded_qty`` off the row's FROZEN ``recommended_qty`` (need is
    unchanged - only the rounding rung moves) through the SAME helper the engine used,
    so an override can never drift from a fresh run's arithmetic."""
    if recommended_qty is None:
        return None
    return eng.round_order_qty(float(recommended_qty), moq, order_multiple)


def set_moq_override(db: Session, rec_id: str, moq: Optional[float]) -> dict:
    """Persist (or clear, on ``None``) the buyer's own MoQ for one recommendation row,
    and recalculate + PERSIST ``rounded_qty`` / ``cash_impact`` off it so the plan grid
    updates the row WITHOUT a full re-run - captain's 20 Aug live-test ask ("MoQ is
    varying ... let them input it, and when they change it, recalculate").

    ``rounded_qty`` / ``cash_impact`` ARE rewritten (unlike the frozen ``inputs`` blob,
    which never moves - AC-M3.11's freeze is about reproducing a fresh run's arithmetic
    byte-for-byte, not about pinning a derived column the buyer just told us is wrong).
    Every reader of those two columns - the draft-PO line at confirm, the budget
    allocator, the grid's server-side sort, the M8 explainer/market/simulation views -
    is a straight column read with no override-awareness of its own, so an override that
    only lived in the live recompute here (the previous shape) was invisible to all of
    them. Making the column itself correct fixes every reader at once instead of teaching
    each one about ``moq_override``.

    NOT grain-guarded (captain, live test, 21 Aug: "This plan is decided at Product grain,
    so a Location decision cannot be recorded on it - I got this when setting the MoQ
    manually"). A prior version of this guard treated a MoQ override like Accept/Adjust
    /Reject (AC-F09), which was wrong: those are DECISIONS about a location's recommended
    quantity, made only where the run's decision grain says that location may decide.
    An MoQ override is not a decision at all - it is an INPUT the buyer is correcting
    before the suggestion is even acted on ("the supplier's MoQ drifted, my number is
    right") - and a product-grain run is exactly where that correction is made, since the
    location-level rows are what a product-grain plan is built FROM. So this stays refused
    only on a legacy run (AC-F10 - the run predates the contract and is read only outright)
    and once the row has already been decided - an accepted/adjusted rec may already sit
    in a draft PO line keyed off the qty this would silently move out from under it."""
    co, co_params = company_sql_predicate(db, "company_id", param_prefix="mvo")
    rec = db.execute(text(
        "SELECT id, run_id, rec_type, status, recommended_qty, unit_cost, currency, "
        "       rate_to_base, rate_as_of, inputs FROM scm.reorder_recommendation "
        f"WHERE id = :id AND {co or 'true'}"
    ), {"id": rec_id, **co_params}).mappings().first()
    if not rec:
        raise AppException(status_code=404, message="Recommendation not found.")
    if rec["rec_type"] not in ("buy", "covered"):
        raise AppException(
            status_code=422,
            message="Only a buy or covered-by-stock row carries a MoQ to override.")
    if moq is not None and float(moq) < 0:
        raise AppException(status_code=422, message="MoQ cannot be negative.")

    run = db.query(ReorderRun).filter(ReorderRun.id == rec["run_id"]).first()
    if run is None:
        raise AppException(status_code=404, message="Reorder run not found.")
    plan_grain.assert_not_legacy(run)
    if rec["status"] != "proposed":
        raise AppException(
            status_code=409,
            message="This row has already been decided, so its MoQ can no longer be "
                    "changed. Reset the decision first.",
            code="recommendation_already_decided",
        )

    moq_value = float(moq) if moq is not None else None
    inp = rec["inputs"] or {}
    effective, is_override = effective_moq(inp, moq_value)
    rounded = recalc_rounded_qty(rec["recommended_qty"], effective, inp.get("order_multiple"))
    cash_impact = _cash_impact_in_base(
        rounded, rec["unit_cost"], rec["currency"], rec["rate_to_base"], rec["rate_as_of"])
    db.execute(text(
        "UPDATE scm.reorder_recommendation "
        "SET moq_override = :m, rounded_qty = :rq, cash_impact = :ci WHERE id = :id"
    ), {"m": moq_value, "rq": rounded, "ci": cash_impact, "id": rec_id})
    db.commit()

    return {
        "recommendation_id": rec_id,
        "moq": effective,
        "moq_is_override": is_override,
        "master_moq": _fnum(inp.get("moq")),
        "order_qty": _fnum(rounded),
        "recommended_qty": _fnum(rec["recommended_qty"]),
        "cash_impact": cash_impact,
    }


def _summarise(recs: list[ReorderRecommendation]) -> dict:
    # Buy count = ORDERABLE buys only (a supplier cost exists). Uncosted buys can't be
    # bought - they're the "N products skipped, no supplier cost" banner, not part of
    # the plan - so they must not inflate the Buy tile (mirrors the FE needs-cost split).
    buy = sum(1 for r in recs if r.rec_type == "buy" and r.unit_cost is not None)
    disposition = sum(1 for r in recs if r.rec_type == "disposition")
    exceptions = sum(1 for r in recs if r.rec_type == "exception")
    total_cash = float(sum(float(r.cash_impact or 0.0) for r in recs if r.rec_type == "buy"))
    # Demand the pool's stock covers. Counted separately and never folded into `buy`: it is
    # a decision the planner has not taken yet, and adding it to the Buy tile would report
    # money as committed that nobody has agreed to spend.
    covered = sum(1 for r in recs if r.rec_type == "covered")
    # Items the plan could not size because nobody has set a level. Counted, never folded
    # into anything else: a plan that quietly omits them reports "nothing to do" for stock
    # that has simply never been set up.
    needs_level = sum(1 for r in recs if r.rec_type == "needs_level")
    return {
        "buy": buy,
        "covered": covered,
        "needs_level": needs_level,
        "disposition": disposition,
        "exceptions": exceptions,
        "total_cash_impact": round(total_cash, 2),
        "recommendation_count": len(recs),
    }


def _fnum(v) -> Optional[float]:
    return float(v) if v is not None else None


def _r(v) -> Optional[float]:
    return round(float(v), 6) if v is not None else None
