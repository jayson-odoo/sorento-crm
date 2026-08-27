"""S13f: after a run, suggest the reorder level to set back in AutoCount.

> "important aspect is the reorder level and reorder quantity, which are set at autocount,
>  and they need to upload to our system ... the third suggestion is I should suggest the
>  reorder level"

The level lives in AutoCount and the buyer maintains it there; this system only ever
uploads it (S13c) and SUGGESTS a better one. So the engine writes `suggested_level` +
`suggestion_basis` onto `scm.reorder_level` and never touches `level` itself - accepting
is the buyer's click, applying it in AutoCount is the buyer's job.

Scope is the PLAN's rows only (user decision), not the whole catalogue: the suggestion is
part of reviewing this week's plan, and a catalogue-wide sweep would bury the forty levels
worth changing under thousands nobody is looking at.

The arithmetic is the industry one (captain, 27 Aug; AC-R11):

    ADU   = delivery-order quantity over the last 90 days / 90, every warehouse
    level = ADU x lead_time + ADU x 14, rounded up to a whole unit

`lead_time` is the product's own supplier lead time - the recommendation's frozen supplier
first (that is the supplier this plan intends to buy from), then `product_suppliers`, then
30 days when nobody knows one. It replaces the S10b `avg monthly movement x cover months`
suggestion and the S13f trajectory lean on top of it: a level sized against a lead time is
a number the buyer can argue with, and a rounding nudged by a trend verdict was not.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.company_scope_sql import company_sql_predicate
from app.services.error_handler import AppException
from app.services.scm import reorder_level_service as rl

log = logging.getLogger(__name__)

#: The rows a level suggestion is about. Dispositions move stock we already own and
#: exceptions have no supplier; neither is a row the buyer sets a level against.
PLAN_REC_TYPES = ("buy", "covered", "needs_level")


def _plan_pairs(db: Session, run_id: str) -> list[dict]:
    """DISTINCT (product, warehouse, segment) the run planned, with codes for the reader."""
    return [dict(r) for r in db.execute(text("""
        SELECT DISTINCT ON (rr.product_id, rr.warehouse_id)
               rr.product_id::text  AS product_id,
               rr.warehouse_id::text AS warehouse_id,
               COALESCE(w.segment, 'project') AS segment,
               rr.company_id::text  AS company_id,
               p.product_code, p.product_name,
               p.reorder_quantity AS master_reorder_quantity,
               -- The lead time the run FROZE for the supplier it chose. There is no
               -- column for it: `inputs.supplier` is where the run keeps the choice.
               (rr.inputs -> 'supplier' ->> 'lead_time_days') AS lead_time_days,
               w.warehouse_code, w.warehouse_name
          FROM scm.reorder_recommendation rr
          JOIN products p ON p.id = rr.product_id
          LEFT JOIN warehouses w ON w.id = rr.warehouse_id
         WHERE rr.run_id = :run_id AND rr.rec_type = ANY(:kinds)
         ORDER BY rr.product_id, rr.warehouse_id
    """), {"run_id": run_id, "kinds": list(PLAN_REC_TYPES)}).mappings().all()]


def _level_windows(db: Session) -> dict[str, float]:
    """The months the popover CHARTS off the global planning policy. NULL = the code
    default. The level's own arithmetic reads the 90-day ADU window, never these months -
    they are the evidence bars under the sentence."""
    row = db.execute(text(
        "SELECT level_study_months "
        "FROM scm.reorder_policy WHERE scope_type = 'global' AND is_active = true "
        "ORDER BY priority DESC NULLS LAST LIMIT 1"
    )).first()
    return {"study_months": int(row[0]) if row and row[0] else rl.DEFAULT_STUDY_MONTHS}


def refresh_for_run(db: Session, run_id: str, *, as_of: Optional[date] = None) -> int:
    """Recompute and store the trajectory-adjusted suggestion for every pair the run planned.

    Never touches a stored `level`. Returns how many suggestions were written.
    """
    pairs = _plan_pairs(db, run_id)
    if not pairs:
        return 0

    windows = _level_windows(db)
    product_ids = sorted({p["product_id"] for p in pairs})
    constraints = rl.supplier_constraints(db, product_ids)
    # ADU and the evidence bars are PRODUCT facts, read once across every warehouse - the
    # level does not care which bin the units left from (captain, 27 Aug).
    usage = rl.average_daily_usage(db, product_ids, as_of=as_of)
    movement = rl.monthly_movement(db, product_ids, None,
                                   months=windows["study_months"], as_of=as_of)

    written = 0
    for pair in pairs:
        pid, wid = pair["product_id"], pair["warehouse_id"]
        u = usage.get(pid, {})
        lead, source = _lead_time_for(pair, constraints.get(pid, {}))
        out = rl.suggest_level_from_usage(
            adu=u.get("adu", 0.0), lead_time_days=lead, lead_time_source=source,
            window_days=u.get("window_days", rl.LEVEL_WINDOW_DAYS),
            window_qty=u.get("window_qty"), months=movement.get(pid, []))
        rl.store_suggestion(db, product_id=pid, warehouse_id=wid,
                            suggested_level=out["level"], basis=out["basis"],
                            company_id=pair["company_id"])
        written += 1
    db.commit()
    return written


def _lead_time_for(pair: dict, constraint: dict) -> tuple[Optional[float], Optional[str]]:
    """The lead time the level is sized against, and where it came from.

    The recommendation's own frozen lead time wins: that is the supplier this plan intends
    to buy from, and a level sized against a different one would ask the buyer to hold
    stock for a lead time nobody is ordering on. `product_suppliers` is the fallback for a
    row the engine never costed (a `needs_level` row often has no supplier chosen).
    """
    rec_lead = pair.get("lead_time_days")
    if rec_lead:
        return float(rec_lead), "recommendation"
    ps_lead = constraint.get("lead_time_days")
    if ps_lead:
        return float(ps_lead), "supplier"
    return None, "default"


def amend_suggestion(db: Session, *, product_id: str, warehouse_id: Optional[str],
                     amended_level: Optional[float], amended_by: Optional[str]) -> dict:
    """Record the buyer's own figure BESIDE the engine's suggestion (S14).

    Never touches `suggested_level` (the engine's number stays arguable-with) and never
    touches `level` (that changes in AutoCount, then comes back on the next upload).
    `amended_level=None` withdraws the amendment. There must be a suggestion to amend:
    an amendment of nothing would be a hand-set level wearing the wrong column.
    """
    co, co_params = company_sql_predicate(db, "rl.company_id", param_prefix="rla",
                                          shared=True)
    row = db.execute(text(f"""
        SELECT rl.id::text AS id, rl.suggested_level
          FROM scm.reorder_level rl
         WHERE rl.product_id = CAST(:pid AS uuid)
           AND COALESCE(rl.warehouse_id::text, '') = COALESCE(CAST(:wid AS text), '')
           {("AND " + co) if co else ""}
    """), {"pid": product_id, "wid": warehouse_id, **co_params}).mappings().first()
    if row is None or row["suggested_level"] is None:
        raise AppException(status_code=422,
                           message="There is no suggestion to amend for this item.")

    if amended_level is not None and amended_level < 0:
        raise AppException(status_code=422,
                           message="A reorder level cannot be negative.")

    now = datetime.utcnow()
    db.execute(text("""
        UPDATE scm.reorder_level
           SET amended_level = :al,
               amended_at = CASE WHEN :al IS NULL THEN NULL ELSE :now END,
               amended_by = CASE WHEN :al IS NULL THEN NULL ELSE :by END,
               updated_at = :now
         WHERE id = :id
    """), {"id": row["id"], "al": amended_level, "by": amended_by, "now": now})
    db.commit()

    fresh = db.execute(text(
        "SELECT suggested_level, amended_level, amended_at, amended_by "
        "FROM scm.reorder_level WHERE id = :id"), {"id": row["id"]}).mappings().first()
    return {
        "product_id": product_id,
        "warehouse_id": warehouse_id,
        "suggested_level": float(fresh["suggested_level"]),
        "amended_level": (float(fresh["amended_level"])
                          if fresh["amended_level"] is not None else None),
        "amended_at": fresh["amended_at"].isoformat() if fresh["amended_at"] else None,
    }


def suggestions_for_run(db: Session, run_id: str) -> dict[str, Any]:
    """Every stored suggestion for the run's plan pairs, keyed `product_id:warehouse_id`.

    The current level travels beside the suggestion: "set it to 12" means nothing without
    "it is 20 today", and a row with no stored level says so rather than showing a zero.
    """
    pairs = _plan_pairs(db, run_id)
    if not pairs:
        return {"suggestions": {}, "count": 0}

    levels = rl.get_levels(db, sorted({p["product_id"] for p in pairs}),
                           sorted({p["warehouse_id"] for p in pairs if p["warehouse_id"]}) or None)

    out: dict[str, Any] = {}
    for pair in pairs:
        pid, wid = pair["product_id"], pair["warehouse_id"]
        row = rl.resolve_level(levels, pid, wid) or {}
        if row.get("suggested_level") is None:
            continue
        out[f"{pid}:{wid or ''}"] = {
            "product_id": pid,
            "warehouse_id": wid,
            "product_code": pair["product_code"],
            "product_name": pair["product_name"],
            "warehouse_code": pair["warehouse_code"],
            "warehouse_name": pair["warehouse_name"],
            "current_level": float(row["level"]) if row.get("level") is not None else None,
            "current_source": row.get("source"),
            "suggested_level": float(row["suggested_level"]),
            # The lot to order when stock hits the level. Lives in the stored basis
            # (no schema change); older suggestions computed before it exist read None,
            # never 0 - "not computed" and "order nothing" are different answers.
            "suggested_quantity": (
                float((row.get("suggestion_basis") or {})["suggested_quantity"])
                if (row.get("suggestion_basis") or {}).get("suggested_quantity") is not None
                else None),
            # AutoCount's reorder quantity as uploaded, beside the engine's: where they
            # disagree is where the master record needs updating.
            "master_reorder_quantity": (
                float(pair["master_reorder_quantity"])
                if pair.get("master_reorder_quantity") is not None else None),
            "suggested_at": (row["suggested_at"].isoformat()
                             if row.get("suggested_at") else None),
            # The buyer's own figure, beside the engine's - never instead of it (S14).
            "amended_level": (float(row["amended_level"])
                              if row.get("amended_level") is not None else None),
            "amended_at": (row["amended_at"].isoformat()
                           if row.get("amended_at") else None),
            "basis": row.get("suggestion_basis") or {},
        }
    return {"suggestions": out, "count": len(out)}
