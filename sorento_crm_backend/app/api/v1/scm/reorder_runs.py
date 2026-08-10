"""SCM M3 reorder-run endpoints — launch a background planning run, poll its status,
and page its recommendations.

Launching a run is a planning action (``scm.reorder.run``); reading status + the
read-only results grid is a dashboard view (``scm.dashboard.view``). Matches the
Phase-1 FE contract in ``services/reorderRunService.ts``. No UUIDs surface in display
fields — SKU/warehouse/supplier resolve to human codes/names.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Query, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission_with_api_key
from app.schemas.scm_reorder import (
    CreateReorderRunRequest,
    ReorderRunAccepted,
    ReorderRunListResponse,
    ReorderRunStatusResponse,
    ReorderRunTodayResponse,
    UnlocatedDemandResponse,
)
from app.services.company_scope_sql import company_sql_predicate
from app.services.scm import cover_service
from app.services.scm import price_history_service
from app.services.scm import level_suggestion_service, trajectory_service
from app.services.error_handler import AppException
from app.services.scm import reorder_run_service as svc
from app.services.scm import demand_source_service
from app.services.scm import unplanned_demand_service
from app.services.scm import demand_breakdown_service
from app.services.scm.money import BASE_CURRENCY

router = APIRouter()

_VIEW = require_permission_with_api_key("scm.dashboard.view")
_RUN = require_permission_with_api_key("scm.reorder.run")

# server-side sort allowlist → SQL expression (mirrors the FE grid's sortable columns)
_SORT = {
    "type": "rr.rec_type",
    "sku": "p.product_code",
    "warehouse_code": "w.warehouse_code",
    "order_qty": "rr.rounded_qty",
    "reorder_point": "rr.reorder_point",
    "net_position": "rr.net_position",
    "days_of_cover": "rr.days_of_cover",
    "confidence": "rr.confidence_band",
    "reason_label": "rr.triggered_reason",
    "min_qty": "(rr.inputs->>'min_qty')::numeric",
    "max_qty": "(rr.inputs->>'max_qty')::numeric",
    "order_up_to": "(rr.inputs->>'order_up_to')::numeric",
    "supplier": "su.supplier_name",
}


@router.post("/reorder-runs", response_model=ReorderRunAccepted, status_code=202)
def create_reorder_run(
    payload: CreateReorderRunRequest = Body(...),
    response: Response = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
    _user: dict = Depends(_RUN),
):
    """Launch a reorder planning run in the background (RQ). Returns 202 with the
    run_id — the UI then polls ``GET /reorder-runs/{run_id}`` until completed/failed."""
    result = svc.create_run(
        db,
        warehouse_codes=payload.warehouse_codes or [],
        # Passed through EMPTY-AS-NONE deliberately: an unnarrowed run must carry no product
        # scope at all, which is what the daily scheduled run sends.
        product_codes=payload.product_codes or None,
        budget_id=payload.budget_id,
        actor=(_user or {}).get("id"),
        include_market=payload.include_market,
    )
    if response is not None:
        response.status_code = 202
    return result


@router.get("/reorder-runs", response_model=ReorderRunListResponse)
def list_reorder_runs(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """Newest-first paginated run history. Each row carries its scope (warehouse
    codes + count), lifecycle timestamps, and — once completed — the roll-up
    summary counts read from the immutable ``run_log``. The FE loads a past run's
    detail by reusing ``GET /{id}`` (summary) + ``/{id}/recommendations`` (grid).
    No UUIDs surface — runs are identified by time + warehouses."""
    # Raw SQL, so the ORM isolation filter never sees it: this company's run history only.
    co, co_params = company_sql_predicate(db, "company_id", param_prefix="crl")
    where = f"WHERE {co}" if co else ""
    total = db.execute(
        text(f"SELECT count(*) FROM scm.reorder_run {where}"), co_params
    ).scalar() or 0
    rows = db.execute(text(f"""
        SELECT id, status, buy_scope, warehouse_ids, started_at, finished_at, run_log
        FROM scm.reorder_run
        {where}
        ORDER BY started_at DESC NULLS LAST, created_at DESC
        LIMIT :limit OFFSET :offset
    """), {"limit": limit, "offset": (page - 1) * limit, **co_params}).mappings().all()

    # Resolve every warehouse id across the page → human code in ONE query.
    all_ids: set[str] = set()
    for r in rows:
        for wid in (r["warehouse_ids"] or []):
            all_ids.add(str(wid))
    code_by_id: dict[str, str] = {}
    if all_ids:
        for wr in db.execute(text(
            "SELECT id::text AS id, warehouse_code FROM warehouses WHERE id::text = ANY(:ids)"
        ), {"ids": list(all_ids)}).mappings().all():
            code_by_id[wr["id"]] = wr["warehouse_code"]

    buy_counts = _costed_buy_counts(db, [str(r["id"]) for r in rows])
    data = [_list_item(r, code_by_id, buy_counts) for r in rows]
    total_pages = max(1, (int(total) + limit - 1) // limit)
    return {"data": data,
            "pagination": {"page": page, "limit": limit, "total": int(total),
                           "total_pages": total_pages}}


def _costed_buy_counts(db: Session, run_ids: list[str]) -> dict[str, int]:
    """Live count of ORDERABLE buys (unit_cost present) per run, from the frozen
    recommendations. Overrides the run_log's ``buy`` tally so runs generated before
    the uncosted-exclusion fix still report the orderable count, keeping the Buy tile
    consistent with the plan grid (which parks uncosted buys in the needs-cost banner)."""
    if not run_ids:
        return {}
    rows = db.execute(text(
        "SELECT run_id::text AS run_id, count(*) AS n FROM scm.reorder_recommendation "
        "WHERE run_id::text = ANY(:ids) AND rec_type = 'buy' AND unit_cost IS NOT NULL "
        "GROUP BY run_id"
    ), {"ids": run_ids}).mappings().all()
    return {r["run_id"]: int(r["n"]) for r in rows}


def _list_item(r, code_by_id: dict, buy_counts: dict[str, int] | None = None) -> dict:
    """One run-history row: scope resolved to warehouse codes + the completed
    summary counts frozen in ``run_log`` (buy_count overridden with the live
    orderable-buy count so uncosted buys never inflate it)."""
    wids = [str(w) for w in (r["warehouse_ids"] or [])]
    codes = [code_by_id[w] for w in wids if w in code_by_id]
    log_obj = r["run_log"] or {}
    summary = None
    if r["status"] == "completed":
        rid = str(r["id"])
        buy_count = (buy_counts or {}).get(rid)
        if buy_count is None:
            buy_count = int(log_obj.get("buy", 0))
        summary = {
            "buy_count": buy_count,
            "disposition_count": int(log_obj.get("disposition", 0)),
            "exception_count": int(log_obj.get("exceptions", 0)),
            "total_cash_impact": float(log_obj.get("total_cash_impact", 0.0)),
            "recommendation_count": int(log_obj.get("recommendation_count", 0)),
        }
    return {
        "run_id": str(r["id"]),
        "status": r["status"],
        "buy_scope": r["buy_scope"],
        "warehouse_codes": codes,
        "warehouse_count": len(wids),
        "started_at": _iso(r["started_at"]),
        "finished_at": _iso(r["finished_at"]),
        "summary": summary,
    }


def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt is not None else None


# NOTE: this static route MUST stay ABOVE ``/reorder-runs/{run_id}`` — declared after
# it, FastAPI would capture "today" as ``run_id`` (route-shadowing).
@router.get("/reorder-runs/today", response_model=Optional[ReorderRunTodayResponse])
def get_today_reorder_run(
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """M8-D3/D4 — the run the reorder page opens to without knowing an id: today's
    scheduled snapshot when present, else the most-recent completed run (last available
    snapshot). ``is_today`` distinguishes the two so the FE header shows "Today's plan"
    vs that run's date+time (M8-D11). ``null`` when no run exists yet (fresh install →
    FE shows the empty page + Manual plan). Same row shape as the history list."""
    picked = svc.today_or_latest_run(db)
    if picked is None:
        return None
    row = picked["row"]
    code_by_id: dict[str, str] = {}
    ids = [str(w) for w in (row["warehouse_ids"] or [])]
    if ids:
        for wr in db.execute(text(
            "SELECT id::text AS id, warehouse_code FROM warehouses WHERE id::text = ANY(:ids)"
        ), {"ids": ids}).mappings().all():
            code_by_id[wr["id"]] = wr["warehouse_code"]
    item = _list_item(row, code_by_id, _costed_buy_counts(db, [str(row["id"])]))
    item["is_today"] = picked["is_today"]
    item["in_progress"] = bool(picked.get("in_progress"))
    return item


# Also above ``/reorder-runs/{run_id}`` - a static segment declared after a path parameter
# is captured by it.
@router.get("/reorder-runs/unlocated-demand", response_model=UnlocatedDemandResponse)
def get_unlocated_demand(
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """Open demand carrying no stock location, so the plan cannot net it against anything.

    Answers "why is this product not in my planning" for the case the counts alone cannot:
    the demand is real and committed, and it is invisible because nobody said where it ships
    from."""
    return unplanned_demand_service.unlocated_demand(db)


# Above ``/reorder-runs/{run_id}`` for the same route-shadowing reason as its neighbour.
@router.get("/reorder-runs/set-aside-demand")
def get_set_aside_demand(
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """Project demand the plan did NOT count, because no Order Inquiry named it (S13b).

    The other half of the demand split: CS filters project sales orders into the Order
    Inquiry, so a project SO outside it is set aside - and this report is what keeps that
    from reading as demand silently going missing. Whole-book, like unlocated-demand: it
    describes the CURRENT book, not a frozen run."""
    return demand_source_service.set_aside_project_demand(db)


@router.get("/reorder-runs/{run_id}", response_model=ReorderRunStatusResponse)
def get_reorder_run(
    run_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """Poll a run's status. ``summary`` is populated once ``status='completed'``;
    ``error`` once ``status='failed'``."""
    co, co_params = company_sql_predicate(db, "company_id", param_prefix="crg")
    row = db.execute(text(
        "SELECT id, status, buy_scope, error_text, run_log FROM scm.reorder_run "
        f"WHERE id = :id AND {co or 'true'}"
    ), {"id": run_id, **co_params}).mappings().first()
    if not row:
        # 404 rather than 403 - another company's run must not be distinguishable
        # from one that does not exist.
        raise AppException(status_code=404, message="Reorder run not found.")
    log_obj = row["run_log"] or {}
    summary = None
    if row["status"] == "completed":
        buy_count = _costed_buy_counts(db, [str(row["id"])]).get(str(row["id"]))
        summary = {
            "buy_count": buy_count if buy_count is not None else int(log_obj.get("buy", 0)),
            "disposition_count": int(log_obj.get("disposition", 0)),
            "exception_count": int(log_obj.get("exceptions", 0)),
            "total_cash_impact": float(log_obj.get("total_cash_impact", 0.0)),
            "recommendation_count": int(log_obj.get("recommendation_count", 0)),
        }
    return {
        "run_id": str(row["id"]),
        "status": row["status"],
        "stage": log_obj.get("stage"),
        "buy_scope": row["buy_scope"],
        "error": row["error_text"],
        "summary": summary,
    }


@router.get("/reorder-runs/{run_id}/recommendations/{rec_id}/demand")
def recommendation_demand(
    run_id: str,
    rec_id: str,
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """The open order lines a planned quantity was built from.

    Answers "why is it bought into BRW when I ordered for BRW-IB, and why so many" from the
    row itself: pooled netting is the reason, and the orders are the evidence."""
    svc.assert_run_visible(db, run_id)
    return demand_breakdown_service.demand_for_recommendation(db, rec_id, limit)


@router.get("/reorder-runs/{run_id}/cover-sources")
def list_cover_sources(
    run_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """Stock held somewhere else that could cover a shortage instead of buying it.

    Keyed by product rather than folded onto each row, because the pool is SHARED: two lines
    for the same product draw on the same units, and duplicating it per row would let the
    screen promise the same stock twice. The caller holds one pool and spends it down as
    decisions are made.

    Free means surplus - a location's on-hand less its OWN demand - so a location that is
    short of its own requirement offers nothing, however much it is holding.
    """
    svc.assert_run_visible(db, run_id)
    product_ids = [
        r[0]
        for r in db.execute(
            text(
                "SELECT DISTINCT product_id::text FROM scm.reorder_recommendation "
                "WHERE run_id::text = :run AND rec_type IN ('buy', 'needs_level')"
            ),
            {"run": run_id},
        ).fetchall()
    ]
    free = cover_service.free_stock_by_product(db, run_id, product_ids)
    return {
        "sources": {
            pid: [
                {
                    "warehouse_id": s.warehouse_id,
                    "warehouse_code": s.warehouse_code,
                    "segment": s.segment,
                    "qty": s.qty,
                }
                for s in sources
            ]
            for pid, sources in free.items()
        }
    }


@router.get("/reorder-runs/{run_id}/price-history")
def list_price_history(
    run_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """What we last paid each supplier for each item in the plan, and how old that is.

    Keyed ``"{product_id}:{supplier_code}"`` because that pair is the question: a cheaper
    price from another supplier is a different negotiation and cannot stand in for it.

    Everything here comes out of our own purchase ledger. The ``advice`` code names which
    fact dominates (no history, unknown age, stale, moving, recent); it is never a claim
    about what the item is worth today, because nothing in this system can see that.
    """
    svc.assert_run_visible(db, run_id)
    history = price_history_service.price_history_for_run(db, run_id)
    # The applied thresholds ride on every entry (policy override or default), so the
    # header echoes the first entry rather than restating the module constants.
    first = next(iter(history.values()), None)

    def _purchase(p) -> Optional[dict]:
        if p is None:
            return None
        return {
            "po_number": p.po_number,
            "issue_date": p.issue_date.isoformat() if p.issue_date else None,
            "unit_cost": p.unit_cost,
            "currency": p.currency,
            "qty": p.qty,
        }

    return {
        "stale_after_days": (
            first.stale_after_days if first else price_history_service.STALE_AFTER_DAYS
        ),
        "movement_threshold_pct": (
            first.movement_threshold_pct if first else price_history_service.MOVEMENT_PCT
        ),
        "prices": {
            key: {
                "advice": a.advice,
                "last": _purchase(a.last),
                "previous": _purchase(a.previous),
                "age_days": a.age_days,
                "movement_pct": a.movement_pct,
                "currency_changed": a.currency_changed,
                "standing_cost": a.standing_cost,
                "standing_currency": a.standing_currency,
                "standing_gap_pct": a.standing_gap_pct,
                "free_of_charge_lines": a.free_of_charge_lines,
            }
            for key, a in history.items()
        },
    }


@router.get("/reorder-runs/{run_id}/trajectory")
def get_trajectory(
    run_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """Is each product's demand sustaining or dying off, per side (S13d).

    Keyed ``"{product_id}:{segment}"`` - project and retail are never merged into one
    figure. Everything comes out of our own order book: the verdict compares the configured
    recent window against the window before it AND the same window last year, side by side,
    with the monthly series behind it for the popup's line graph.
    """
    svc.assert_run_visible(db, run_id)
    return trajectory_service.trajectory_for_run(db, run_id)


@router.get("/reorder-runs/{run_id}/level-suggestions")
def list_level_suggestions(
    run_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """The AutoCount levels this run suggests changing (S13f).

    Keyed ``"{product_id}:{warehouse_id}"``. Each entry carries the current level beside
    the suggestion and the full arithmetic (`basis`), because "set it to 12" means nothing
    without "it is 20 today" and the sums that produced the 12. The stored `level` is never
    written by the engine - accepting a suggestion stays the buyer's click, and applying it
    in AutoCount stays the buyer's job.
    """
    svc.assert_run_visible(db, run_id)
    return level_suggestion_service.suggestions_for_run(db, run_id)


@router.get("/reorder-runs/{run_id}/recommendations")
def list_recommendations(
    run_id: str,
    page: int = Query(1, ge=1),
    # cap 1000: the M4 cash view fetches the whole buy set unpaginated (greedy funding
    # + funded/deferred/needs-cost sections run across the entire ranked list).
    limit: int = Query(50, ge=1, le=1000),
    sort: Optional[str] = Query(None),
    dir: str = Query("asc"),
    query: Optional[str] = Query(None),
    type: Optional[str] = Query(None),  # buy | covered | disposition | exception | needs_level
    budget: Optional[float] = Query(None, ge=0),  # M4 — live funding what-if
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """Paginated recommendations for a completed run (DataGrid). Server-side sort over
    the allowlisted rec columns; ``type`` filter (buy|covered|disposition|exception); ``query``
    on SKU/product name. Each row carries its frozen inputs (AC-M3.11).

    M4: when ``budget`` is supplied, buy rows carry a LIVE ``funding_status``
    (funded|deferred|needs_cost) from the greedy skip-overflow allocation over the
    run's FROZEN rank_score — no engine re-run, no persistence. Omitting ``budget``
    returns the last persisted funding_status (or null for costed buys never funded)."""
    svc.assert_run_visible(db, run_id)

    where = ["rr.run_id = :rid"]
    params: dict[str, Any] = {"rid": run_id}
    if type in ("buy", "covered", "disposition", "exception", "needs_level"):
        where.append("rr.rec_type = :type")
        params["type"] = type
    if query:
        where.append("(p.product_code ILIKE :q OR p.product_name ILIKE :q)")
        params["q"] = f"%{query}%"
    where_sql = " AND ".join(where)

    total = db.execute(text(
        f"SELECT count(*) FROM scm.reorder_recommendation rr "
        f"JOIN products p ON p.id = rr.product_id WHERE {where_sql}"
    ), params).scalar() or 0

    sort_expr = _SORT.get(sort or "", None)
    order_by = (f"{sort_expr} {'DESC' if dir.lower() == 'desc' else 'ASC'} NULLS LAST"
                if sort_expr else "rr.rec_type ASC, p.product_code ASC")
    params["limit"] = limit
    params["offset"] = (page - 1) * limit
    rows = db.execute(text(f"""
        SELECT rr.id, rr.rec_type, rr.product_id, rr.warehouse_id, rr.net_position, rr.reorder_point,
               rr.days_of_cover, rr.rounded_qty, rr.recommended_qty, rr.confidence_band,
               rr.allocation, rr.inputs,
               rr.rank, rr.rank_score, rr.unit_cost, rr.cash_impact, rr.funding_status,
               rr.currency, rr.rate_to_base, rr.rate_as_of, rr.status,
               p.product_code, p.product_name,
               w.warehouse_code, w.warehouse_name, w.segment,
               su.supplier_code, su.supplier_name
        FROM scm.reorder_recommendation rr
        JOIN products p ON p.id = rr.product_id
        LEFT JOIN warehouses w ON w.id = rr.warehouse_id
        LEFT JOIN suppliers su ON su.id = rr.supplier_id
        WHERE {where_sql}
        ORDER BY {order_by}
        LIMIT :limit OFFSET :offset
    """), params).mappings().all()

    # M4 live funding: when a budget is supplied, run the greedy allocator over the
    # run's WHOLE frozen buy set (not just this page) and annotate the buy rows.
    funding_by_id: Optional[dict[str, str]] = None
    if budget is not None:
        funding_by_id = svc.allocate_run_budget(db, run_id, budget).status_by_id

    data = [_row(r, funding_by_id) for r in rows]
    total_pages = max(1, (int(total) + limit - 1) // limit)
    return {"data": data,
            "pagination": {"page": page, "limit": limit, "total": int(total),
                           "total_pages": total_pages}}


@router.put("/reorder-runs/{run_id}/budget")
def apply_reorder_run_budget(
    run_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    _user: dict = Depends(_RUN),
):
    """Persist the chosen budget + funding split to the run ("Apply budget"). Runs the
    pin/reject-aware allocator over the run's frozen buys, stamps ``funding_status`` on
    each buy rec + ``budget_amount`` on the run so a shared run shows ONE funded set.
    Persisting funding + budget is a planning action (mutates run state) → ``scm.reorder.run``.

    Full-budget request (``full: true`` OR a null ``budget``) funds every costed buy — the
    daily-cron / 'fund all' path — and stamps a null ``budget_amount``."""
    svc.assert_run_visible(db, run_id)
    budget = payload.get("budget")
    if payload.get("full") or budget is None:
        return svc.apply_run_budget(db, run_id, None, full=True)
    if not isinstance(budget, (int, float)) or budget < 0:
        raise AppException(status_code=422, message="A non-negative budget is required.")
    return svc.apply_run_budget(db, run_id, float(budget))


@router.get("/recommendations/{rec_id}/explain-net")
def explain_recommendation_net(
    rec_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(_VIEW),
):
    """M8-A1 — net-breakdown drill: ``on_hand`` / ``on_order`` / ``committed`` / ``net``
    for the rec's product×warehouse plus the list of OPEN sales-order lines behind
    ``committed`` (each navigable — SO number, customer, qty, order date), summing to the
    committed figure. Read-only; no numeric write. IDs resolve to human-readable
    SO number + customer name (no UUIDs surface)."""
    return svc.explain_net(db, rec_id)


def _row(r, funding_by_id: Optional[dict[str, str]] = None) -> dict:
    """Build a read-only recommendation row from stored columns + frozen ``inputs``.

    ``funding_by_id`` (M4) carries the live budget allocation → a buy row's
    ``funding_status`` reflects the slid budget. When absent, buy rows fall back to
    their persisted ``funding_status`` (uncosted buys are always ``needs_cost``)."""
    inp = r["inputs"] or {}
    is_network = r["warehouse_id"] is None
    is_buy = r["rec_type"] == "buy"
    # A covered row is priced like a buy so "buy anyway" has a figure beside it.
    is_priced = r["rec_type"] in ("buy", "covered")
    allocation = None
    if r["allocation"]:
        allocation = [{"warehouse_code": a.get("warehouse_code"),
                       "warehouse_name": a.get("warehouse_name"),
                       "qty": a.get("qty")} for a in r["allocation"]]
    return {
        "id": r["id"],
        "type": r["rec_type"],
        "sku": r["product_code"],
        "product_name": r["product_name"],
        "abc_class": inp.get("abc_class"),
        "xyz_class": inp.get("xyz_class"),
        "warehouse_code": r["warehouse_code"],
        "warehouse_name": r["warehouse_name"],
        # Data-only ids (never rendered) so the FE demand drill can call
        # GET /analytics/explain/demand?product_id=&warehouse_id= (M8-A2). Mirrors
        # how the row already carries the opaque `id` for the explain / detail fetch.
        "product_id": str(r["product_id"]) if r["product_id"] is not None else None,
        "warehouse_id": str(r["warehouse_id"]) if r["warehouse_id"] is not None else None,
        "is_network": is_network,
        "allocation": allocation,
        # A ``covered`` row carries a quantity too: it is what buying anyway would cost
        # you, and without it the choice between stock and a purchase has one side missing.
        "order_qty": (_f(r["rounded_qty"])
                      if r["rec_type"] in ("buy", "covered") else None),
        # Pre-rounding order qty (order-up-to − net) so the derivation popup can show
        # the raw figure BEFORE MoQ / pack-multiple rounding lands on `order_qty`.
        "recommended_qty": (_f(r["recommended_qty"])
                            if r["rec_type"] in ("buy", "covered") else None),
        "reorder_point": _f(r["reorder_point"]),
        "min_qty": inp.get("min_qty"),
        "max_qty": inp.get("max_qty"),
        "order_up_to": inp.get("order_up_to"),
        "net_position": _f(r["net_position"]),
        "days_of_cover": _f(r["days_of_cover"]),
        "reason": inp.get("reason"),
        "reason_label": inp.get("reason_label"),
        "confidence": r["confidence_band"],
        "sample_size": int(inp.get("sample_size") or 0),
        "supplier": inp.get("supplier"),
        # Why this supplier and not the runner-up, frozen at run time. Without it the
        # "why this one" popup has nothing to render, which is how it first shipped.
        "supplier_reason": inp.get("supplier_reason"),
        "alternatives": inp.get("alternatives") or [],
        "is_exception": bool(inp.get("is_exception")),
        # --- covered rows: the two numbers the stock-or-buy choice turns on ---
        # The decision taken on this row, if any. A covered row KEEPS its place in the
        # list after a decision so it can be changed; without the state the list would
        # look untouched and the click would read as having done nothing.
        "decision_status": r["status"],
        "covered_committed": inp.get("covered_committed"),
        # Part of this row's demand arrived with no stated location, so the reader can
        # weigh it accordingly rather than assuming every unit was located by CS.
        "unlocated_demand": inp.get("unlocated_demand"),
        "covered_available": inp.get("covered_available"),
        "disposition_action": inp.get("disposition_action"),
        "transfer_flag": inp.get("transfer_flag"),
        # --- frozen derivation inputs (drive the plain-language explanation popup) ---
        # All already frozen at run time in `inputs` (AC-M3.11) — surfaced read-only,
        # never recomputed on the client.
        "forecast_daily_demand": inp.get("demand_rate"),
        "lead_time_days": inp.get("lead_time_days"),
        "lead_time_source": inp.get("lead_time_source"),
        "safety_stock": inp.get("safety_stock"),
        "safety_stock_method": inp.get("safety_stock_method"),
        "safety_stock_fallback": inp.get("safety_stock_fallback"),
        "service_level": inp.get("service_level"),
        "safety_days": inp.get("safety_days"),
        "review_days": inp.get("review_days"),
        "moq": inp.get("moq"),
        "order_multiple": inp.get("order_multiple"),
        # --- S10: the weekly checklist, so the row answers "should I order this" alone ---
        "segment": r["segment"],
        # The window the daily rate was averaged over, so the row can show "N units over
        # M days" instead of a bare rate.
        "demand_window_days": inp.get("demand_window_days"),
        "on_hand": inp.get("on_hand"),
        # SPO on the water vs the ordered-not-received PO book. Two different questions.
        "incoming_spo": inp.get("on_order"),
        "outstanding_po": inp.get("po_ordered"),
        "outstanding_sales": inp.get("committed"),
        # What master data says, beside what the plan computed. The buyer asked to see both:
        # where they disagree is where the master record needs updating.
        "master_reorder_level": inp.get("master_reorder_level"),
        "master_reorder_quantity": inp.get("master_reorder_quantity"),
        "reorder_level": inp.get("reorder_level"),
        "reorder_level_source": inp.get("reorder_level_source"),
        "suggested_level": inp.get("suggested_level"),
        "suggestion_basis": inp.get("suggestion_basis"),
        # What we last paid, and how it was attributed. `unattributed` is said out loud
        # because most purchase history names no destination: presenting it as the dealer
        # or project cost would invent the split the buyer asked us for.
        "last_purchase_cost": (inp.get("last_purchase") or {}).get("cost"),
        "last_purchase_currency": (inp.get("last_purchase") or {}).get("currency"),
        "last_purchase_date": (inp.get("last_purchase") or {}).get("at"),
        "last_purchase_ref": (inp.get("last_purchase") or {}).get("ref"),
        "last_purchase_basis": inp.get("last_purchase_basis"),
        "policy_type": inp.get("policy_type"),
        "supplier_selection": inp.get("selection"),
        # --- M4 cash co-pilot (buy rows only; non-buy leave these null) ---
        # `unit_cost` is what the SUPPLIER charges, in `currency`. `cash_impact` is what the
        # buy draws from the budget, always in `base_currency`. They are deliberately in
        # different money, so both are labelled: an unlabelled 45 beside an unlabelled 1980
        # reads as an arithmetic error.
        "unit_cost": _f(r["unit_cost"]) if is_priced else None,
        "currency": (r["currency"] if is_priced else None),
        "cash_impact": _f(r["cash_impact"]) if is_priced else None,
        "base_currency": BASE_CURRENCY if is_priced else None,
        "rate_to_base": _f(r["rate_to_base"]) if is_priced else None,
        "rate_as_of": (r["rate_as_of"].isoformat()
                       if is_priced and r["rate_as_of"] else None),
        # Why there is no cash figure, when there is none: `no_cost` (nobody has ever
        # priced it) and `no_rate` (priced, in money we cannot convert) send the buyer to
        # two different screens, so "needs cost" alone would send half of them to the
        # wrong one.
        "cost_status": _cost_status(r, inp, is_buy),
        "missing_rate_currencies": (
            list((inp.get("supplier_reason") or {}).get("missing_rates") or [])
            if is_buy else []
        ),
        "rank": int(r["rank"]) if (is_buy and r["rank"] is not None) else None,
        "rank_score": _f(r["rank_score"]) if is_buy else None,
        "funding_status": _funding_status(r, is_buy, funding_by_id),
        "days_to_stockout": inp.get("days_to_stockout") if is_buy else None,
        "rank_factors": (inp.get("rank_factors") or []) if is_buy else [],
        # M7 — the market signal that moved this rank (only when the run opted in and a
        # signal matched); a one-line summary for "why this rank". No UUID.
        "market_signal": (
            (inp.get("market_factor") or {}).get("summary") if is_buy else None
        ),
    }


def _cost_status(r, inp: dict, is_buy: bool) -> Optional[str]:
    """`ok`, `no_cost`, or `no_rate` - which of the two reasons a buy has no cash figure.

    Both currently land in the same `needs_cost` funding bucket, which is right (a human
    has to look at them either way), but the fix differs: one is "buy it once so we know
    what it costs", the other is "enter a rate for CNY". A single label would send half the
    rows to the wrong screen.
    """
    if not is_buy:
        return None
    if r["cash_impact"] is not None:
        return "ok"
    if r["unit_cost"] is None:
        return "no_cost"
    return "no_rate"


def _funding_status(r, is_buy: bool,
                    funding_by_id: Optional[dict[str, str]]) -> Optional[str]:
    """Live funding when a budget was supplied; else the persisted status. Non-buy
    rows never carry a funding status."""
    if not is_buy:
        return None
    if funding_by_id is not None:
        return funding_by_id.get(str(r["id"]))
    # No budget in the query — an uncosted buy is always needs_cost (M4-D16); a costed
    # buy shows its last persisted funding_status (null when never funded).
    if r["cash_impact"] is None:
        return "needs_cost"
    return r["funding_status"]


def _f(v) -> Optional[float]:
    return float(v) if v is not None else None
