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

The arithmetic is the S10b one (`avg monthly movement x cover months`, study/cover windows
from the planning policy). What S13f adds is the trajectory: a product whose orders are
rising rounds UP to the next whole unit, one whose orders died off rounds DOWN, so the
suggested level leans the way the demand is leaning (AC-S13f.1).
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.scm import reorder_level_service as rl
from app.services.scm import trajectory_service

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
               w.warehouse_code, w.warehouse_name
          FROM scm.reorder_recommendation rr
          JOIN products p ON p.id = rr.product_id
          LEFT JOIN warehouses w ON w.id = rr.warehouse_id
         WHERE rr.run_id = :run_id AND rr.rec_type = ANY(:kinds)
         ORDER BY rr.product_id, rr.warehouse_id
    """), {"run_id": run_id, "kinds": list(PLAN_REC_TYPES)}).mappings().all()]


def _level_windows(db: Session) -> dict[str, float]:
    """The study/cover months off the global planning policy. NULL = the code default."""
    row = db.execute(text(
        "SELECT level_study_months, level_cover_months "
        "FROM scm.reorder_policy WHERE scope_type = 'global' AND is_active = true "
        "ORDER BY priority DESC NULLS LAST LIMIT 1"
    )).first()
    return {
        "study_months": int(row[0]) if row and row[0] else rl.DEFAULT_STUDY_MONTHS,
        "cover_months": float(row[1]) if row and row[1] else rl.DEFAULT_COVER_MONTHS,
    }


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
    # The same verdicts the Trend popup shows, so the two never disagree about a product.
    trend = trajectory_service.trajectory_for_run(db, run_id, as_of=as_of)["series"]

    written = 0
    movement_by_wid: dict[Optional[str], dict[str, list]] = {}
    for pair in pairs:
        pid, wid = pair["product_id"], pair["warehouse_id"]
        if wid not in movement_by_wid:
            movement_by_wid[wid] = rl.monthly_movement(
                db, product_ids, [wid] if wid else None,
                months=windows["study_months"], as_of=as_of)
        segment = pair["segment"] or "project"
        verdict = (trend.get(f"{pid}:{segment}") or {}).get("verdict")
        c = constraints.get(pid, {})
        out = rl.suggest_level(
            movement_by_wid[wid].get(pid, []),
            cover_months=windows["cover_months"],
            moq=c.get("moq"), order_multiple=c.get("order_multiple"),
            trend=verdict)
        rl.store_suggestion(db, product_id=pid, warehouse_id=wid,
                            suggested_level=out["level"], basis=out["basis"],
                            company_id=pair["company_id"])
        written += 1
    db.commit()
    return written


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
            "suggested_at": (row["suggested_at"].isoformat()
                             if row.get("suggested_at") else None),
            "basis": row.get("suggestion_basis") or {},
        }
    return {"suggestions": out, "count": len(out)}
