"""Extract every run output the plan cares about into one normalized, JSON-safe dict.

Two of the read-time services (``level_suggestion_service``, ``summary_order_service``)
have a post-commit hook inside ``run_reorder`` that calls them WITHOUT ``as_of`` - they
then default to ``date.today()``, the real wall clock, not the pinned ``AS_OF``. This module
re-invokes them itself with ``as_of=AS_OF`` before reading anything back, so the snapshot
is pinned even though the run's own best-effort hook was not.

``summary_order_service`` additionally depends on ``coverage_service``, which reads
``datetime.now(MALAYSIA_TZ)`` inline with no ``as_of`` parameter at all (see README) - its
non-timestamp figures (on_hand, project_demand, dealer_outstanding, qty_on_order,
qty_in_transit, suggested_qty) are stable regardless, but ``shortfall`` /
``max_days_outstanding`` are dated projections from "now" and are EXCLUDED below rather
than pinned. Everything else here is fully deterministic under a frozen ``AS_OF``.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import text

from scripts.scm_sim.world import AS_OF, SUPPLIERS, WH_DEALER, WH_PROJECT

#: Qualified with ``rr.`` throughout - ``products`` also carries a ``currency`` column,
#: and an unqualified ``currency`` is ambiguous the moment this is joined to it.
_REC_COLUMNS = (
    "rr.rec_type, rr.net_position, rr.reorder_point, rr.forecast_daily_demand, "
    "rr.days_of_cover, rr.recommended_qty, rr.rounded_qty, rr.unit_cost, "
    "rr.cash_impact, rr.currency, rr.rate_to_base, rr.rate_as_of, rr.urgency_score, "
    "rr.priority_score, rr.rank_score, rr.rank, rr.confidence_band, "
    "rr.triggered_reason, rr.allocation, rr.inputs, rr.funding_status, rr.status"
)

#: order_summary_row fields whose VALUE is a dated projection off `coverage_service`'s
#: unpinnable internal clock, not off `AS_OF`. Excluded so a same-day rerun cannot show a
#: spurious CHANGED against yesterday's baseline for a reason that has nothing to do with
#: the engine.
_ORDER_SUMMARY_UNPINNED_FIELDS = ("shortfall", "max_days_outstanding")


#: Reserved top-level snapshot key for run-level facts that are NOT a scenario (S2).
#: ``compare.py`` special-cases this key so a mode flip shows as its own META line
#: instead of being walked as a 39th "scenario".
META_KEY = "_meta"


def build_snapshot(db, run_id: str, scenarios: list) -> dict:
    _repin_post_commit_hooks(db, run_id)

    from app.services.scm import (
        level_suggestion_service,
        po_book_service,
        price_history_service,
        summary_order_service,
        trajectory_service,
    )
    from app.services.scm.reorder_policy import resolve_global_planning_mode

    suggestions = level_suggestion_service.suggestions_for_run(db, run_id)["suggestions"]
    price_hist = {
        key: _price_advice_to_dict(advice)
        for key, advice in price_history_service.price_history_for_run(
            db, run_id, as_of=AS_OF
        ).items()
    }
    trajectory = trajectory_service.trajectory_for_run(db, run_id, as_of=AS_OF)["series"]
    po_book = po_book_service.po_book_for_run(db, run_id)["po_book"]
    summary_rows = _summary_rows_by_code(db, run_id)

    codes = [s.code for s in scenarios]
    product_ids = _lookup_ids(db, "products", "product_code", codes)
    warehouse_ids = _lookup_ids(db, "warehouses", "warehouse_code", [WH_DEALER, WH_PROJECT])
    recs_by_code = _recommendations_by_code(db, run_id, codes)
    net_by_code = _net_position_by_code(db, codes)
    level_by_code = _reorder_level_by_code(db, codes)

    out: dict[str, Any] = {}
    for spec in scenarios:
        pid = product_ids.get(spec.code)
        wh_code = WH_DEALER if spec.segment == "dealer" else WH_PROJECT
        wid = warehouse_ids.get(wh_code)
        supplier_code = SUPPLIERS[spec.supplier][0]

        entry = {
            "title": spec.title,
            "expected_note": spec.expected_note,
            "segment": spec.segment,
            "policy": spec.policy,
            "recommendations": recs_by_code.get(spec.code, []),
            "net_position": net_by_code.get(spec.code),
            "reorder_level": level_by_code.get(spec.code),
            "level_suggestion": _strip_level_suggestion_volatiles(
                suggestions.get(f"{pid}:{wid or ''}")
            ),
            "trajectory": trajectory.get(f"{pid}:{spec.segment}"),
            "po_book": po_book.get(f"{pid}:{wid or ''}"),
            "price_history": price_hist.get(f"{pid}:{supplier_code}"),
            "order_summary_row": _strip_unpinned(summary_rows.get(spec.code)),
        }
        out[spec.code] = entry

    # Run-level fact, not a scenario: which global planning mode this run actually
    # executed under (S2, UAC C2). Read AFTER the run so a mid-run flip (there isn't
    # one in the harness, but the read stays honest) would show the mode that governed
    # the recommendations above.
    out[META_KEY] = {"planning_mode": resolve_global_planning_mode(db)}
    return _normalize(out)


def _repin_post_commit_hooks(db, run_id: str) -> None:
    """Recompute the two ``as_of``-accepting post-commit writers with the pinned clock,
    overwriting whatever ``run_reorder``'s own (unpinned) best-effort call produced.

    Each is wrapped independently and ROLLED BACK on failure - a raised exception leaves
    the session's transaction "aborted" in Postgres (every subsequent statement raises
    ``InFailedSqlTransaction`` until a rollback), so swallowing the exception without
    rolling back would silently break every read that follows, including the
    recommendation/net-position reads this same snapshot still needs to do.
    """
    from app.services.scm import level_suggestion_service, summary_order_service

    try:
        level_suggestion_service.refresh_for_run(db, run_id, as_of=AS_OF)
    except Exception as exc:  # noqa: BLE001 - snapshot must not die on a soft-fail hook
        db.rollback()
        print(f"[scm_sim] WARNING: level_suggestion_service.refresh_for_run failed "
              f"(level_suggestion excluded for this run): {exc}")
    try:
        summary_order_service.write_rows(db, run_id, as_of=AS_OF)
        db.commit()
    except Exception as exc:  # noqa: BLE001 - coverage_service's inline clock is the
        # documented reason this can resist pinning (see README); the run itself already
        # completed and must not be reported as failed over this.
        db.rollback()
        print(f"[scm_sim] WARNING: summary_order_service.write_rows failed "
              f"(order_summary_row excluded for affected products): {exc}")


def _summary_rows_by_code(db, run_id: str) -> dict[str, dict]:
    from app.services.error_handler import AppException
    from app.services.scm import summary_order_service

    try:
        report = summary_order_service.report(db, run_id=run_id)
    except AppException:
        return {}
    return {row["product_code"]: row for row in report.get("rows", [])}


def _strip_level_suggestion_volatiles(row: Optional[dict]) -> Optional[dict]:
    """The level-suggestion payload carries raw ids (fresh UUIDs every reseed) and a
    wall-clock ``suggested_at`` - all volatile, none of them the suggestion. The scenario
    key already names the product/warehouse."""
    if not row:
        return row
    return {k: v for k, v in row.items()
            if k not in ("product_id", "warehouse_id", "suggested_at")}


def _strip_unpinned(row: Optional[dict]) -> Optional[dict]:
    if row is None:
        return None
    return {k: v for k, v in row.items() if k not in _ORDER_SUMMARY_UNPINNED_FIELDS}


def _price_advice_to_dict(advice) -> dict:
    d = advice._asdict()
    d["last"] = advice.last._asdict() if advice.last else None
    d["previous"] = advice.previous._asdict() if advice.previous else None
    return d


def _lookup_ids(db, table: str, code_column: str, codes: list[str]) -> dict[str, str]:
    if not codes:
        return {}
    rows = db.execute(
        text(f"SELECT id, {code_column} AS code FROM {table} WHERE {code_column} = ANY(:codes)"),
        {"codes": codes},
    ).mappings().all()
    return {r["code"]: str(r["id"]) for r in rows}


def _recommendations_by_code(db, run_id: str, codes: list[str]) -> dict[str, list[dict]]:
    if not codes:
        return {}
    rows = db.execute(text(f"""
        SELECT p.product_code, {_REC_COLUMNS}
        FROM scm.reorder_recommendation rr
        JOIN products p ON p.id = rr.product_id
        WHERE rr.run_id = :run_id AND p.product_code = ANY(:codes)
        ORDER BY p.product_code, rr.rec_type
    """), {"run_id": run_id, "codes": codes}).mappings().all()
    out: dict[str, list[dict]] = {}
    for r in rows:
        d = dict(r)
        code = d.pop("product_code")
        _strip_policy_ref(d)
        out.setdefault(code, []).append(d)
    return out


def _strip_policy_ref(rec: dict) -> None:
    """``inputs.policy_ref`` is the raw ``scm.reorder_policy.id`` - a bare UUID with no
    human code to map back to (the table has no ``code`` column), and NOT a stable one
    besides: `scm.reorder_policy` is truncated and reseeded on every ``run``, so even the
    fixed global-defaults row the engine auto-creates
    (``reorder_engine.ensure_reorder_policy_defaults``) gets a fresh random id each time.
    Every OTHER fact about the resolved policy (policy_type, service_level, safety_days,
    ...) is already inlined beside it in ``inputs``, so dropping the id loses nothing a
    diff could act on."""
    inputs = rec.get("inputs")
    if isinstance(inputs, dict):
        inputs.pop("policy_ref", None)


def _net_position_by_code(db, codes: list[str]) -> dict[str, dict]:
    if not codes:
        return {}
    rows = db.execute(text("""
        SELECT p.product_code, np.quantity_on_hand, np.on_order, np.committed,
               np.net_position
        FROM scm.net_position_v np
        JOIN products p ON p.id = np.product_id
        WHERE p.product_code = ANY(:codes)
    """), {"codes": codes}).mappings().all()
    return {r["product_code"]: {k: v for k, v in r.items() if k != "product_code"}
            for r in rows}


def _reorder_level_by_code(db, codes: list[str]) -> dict[str, dict]:
    if not codes:
        return {}
    rows = db.execute(text("""
        SELECT p.product_code, rl.level, rl.reorder_qty, rl.source, rl.suggested_level,
               rl.suggestion_basis, rl.amended_level
        FROM scm.reorder_level rl
        JOIN products p ON p.id = rl.product_id
        WHERE p.product_code = ANY(:codes)
    """), {"codes": codes}).mappings().all()
    return {r["product_code"]: {k: v for k, v in r.items() if k != "product_code"}
            for r in rows}


def _normalize(obj: Any) -> Any:
    """Decimal -> float, date/datetime -> isoformat, UUID -> str, recursively."""
    if isinstance(obj, dict):
        return {k: _normalize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_normalize(v) for v in obj]
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, _uuid.UUID):
        return str(obj)
    return obj
