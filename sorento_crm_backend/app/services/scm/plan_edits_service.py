"""Save every drafted edit on a plan in ONE request (PLAN-scm-reorder-revamp.md 4.5/5.1).

The revamp's expanded row holds the whole decision - cover mixture, MOQ, the AutoCount
level and its reorder quantity, keep-or-discontinue - and none of it reaches the backend
until the buyer presses Save. Before this, each control wrote on its own: a pencil Record,
a MOQ blur, a level Save, a health click. One row could be four requests, and a
half-finished thought was already persisted.

**This module decides nothing.** Every field is handed straight to the service function
that already owned it, so the bulk save and the per-row endpoints (which stay, and are
what the older screens still call) can never disagree:

    decision     -> decision_service.record_plan_row_decision
    moq          -> reorder_run_service.set_moq_override
    level        -> level_suggestion_service.amend_suggestion
    reorder_qty  -> reorder_level_service.set_reorder_qty
    lifecycle    -> product_economics_service.record_lifecycle_decision

What it does own is the TRANSACTION. Save is one button over many rows, so a failure on
row seven must leave nothing of rows one to six behind - a partial save would leave the
screen's pills reading Saved for edits that never landed. Each of those services commits
by default (they are called one per request everywhere else); here they are all called
with `commit=False` and the route commits once at the end. An `AppException` from any row
propagates with the session still dirty, and the request's session is discarded (rolled
back) without ever committing.

A grouped product row is fanned out by the CALLER, one entry per member recommendation,
exactly the way `usePlanLines.decide` and `.updateMoq` already fan their per-row writes -
so this never has to know about the grouping. What it does report back is the count of
distinct PRODUCTS those rows belong to (R14), which is the figure Save (N) showed.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.base import get_company_scope
from app.models.scm import ReorderRecommendation, ReorderRun
from app.services.company_scope import resolve_write_company_id
from app.services.error_handler import AppException
from app.services.scm import decision_service
from app.services.scm import level_suggestion_service
from app.services.scm import plan_grain
from app.services.scm import product_economics_service
from app.services.scm import reorder_level_service
from app.services.scm import reorder_run_service


def save_plan_edits(
    db: Session, run_id: str, rows: list[dict[str, Any]], actor: Optional[str]
) -> dict[str, int]:
    """Apply every drafted row edit on `run_id`. Returns `{saved_rows, saved_products}`.

    404 when the run is unknown or a row names a recommendation that is not on it (a rec
    id from another plan is not a permission question, it is a row that does not exist
    HERE). 409 on a legacy run, the same refusal every other write to one gives.
    """
    run = db.query(ReorderRun).filter(ReorderRun.id == run_id).first()
    if run is None:
        raise AppException(status_code=404, message="Reorder run not found.")
    plan_grain.assert_not_legacy(run)

    if not rows:
        return {"saved_rows": 0, "saved_products": 0}

    recs = _recs_on_run(db, run_id, [str(r.get("rec_id") or "") for r in rows])
    # Resolved ONLY when a reorder quantity is actually being written: `scm.reorder_level`
    # is an owned table reached by raw SQL, so its insert has to stamp the company the ORM
    # hook would - and that resolution refuses an unnamed company, which must not fail a
    # save that never touches the table (`reorder_levels._company_id` does the same, per
    # request).
    company_id = (
        resolve_write_company_id(get_company_scope(db))
        if any("reorder_qty" in row for row in rows) else None
    )

    products: set[str] = set()
    for row in rows:
        rec = recs[str(row["rec_id"])]
        products.add(str(rec.product_id))
        _apply_row(db, rec, row, actor=actor, company_id=company_id)

    return {"saved_rows": len(rows), "saved_products": len(products)}


def _recs_on_run(
    db: Session, run_id: str, rec_ids: list[str]
) -> dict[str, ReorderRecommendation]:
    """Every named recommendation, checked to be ON this run BEFORE anything is written.

    Resolved up front rather than row by row so a batch naming one foreign rec is refused
    without having written the rows before it - the rollback would undo them anyway, but
    a guard that runs first is the one a reader can reason about.
    """
    wanted = [rid for rid in rec_ids if rid]
    if len(wanted) != len(rec_ids):
        raise AppException(status_code=422, message="Every edited row needs a row id.")
    found = {
        str(rec.id): rec
        for rec in db.query(ReorderRecommendation)
        .filter(
            ReorderRecommendation.run_id == run_id,
            ReorderRecommendation.id.in_(set(wanted)),
        )
        .all()
    }
    missing = [rid for rid in wanted if rid not in found]
    if missing:
        raise AppException(
            status_code=404, message="A row in this save is not part of this plan."
        )
    return found


def _apply_row(
    db: Session,
    rec: ReorderRecommendation,
    row: dict[str, Any],
    *,
    actor: Optional[str],
    company_id: Optional[str],
) -> None:
    """One drafted row, field by field, in the order the panel reads top to bottom."""
    decision = row.get("decision")
    if decision:
        decision_service.record_plan_row_decision(
            db,
            str(rec.id),
            decision.get("kind"),
            decision.get("buy_qty"),
            decision.get("stock_takes") or [],
            decision.get("po_qty"),
            decision.get("po_refs") or [],
            decision.get("reason_text"),
            actor,
            price_mode=decision.get("price_mode"),
            supplier_code=decision.get("supplier_code"),
            unit_cost=decision.get("unit_cost"),
        )

    if "moq" in row:
        reorder_run_service.set_moq_override(
            db, str(rec.id), row["moq"], commit=False
        )

    # Both write to the row the PANEL is reading. `scm.reorder_level` is keyed
    # (product, warehouse) and the suggestion the panel amends was stored under the
    # recommendation's OWN pair (`level_suggestion_service._plan_pairs`): a product-grain
    # rec carries `warehouse_id = NULL`, a location-grain one carries its warehouse. So
    # the key travels off the rec rather than being forced to NULL - forcing it looked up
    # the product-wide row, which on a location-grain run holds no suggestion and made
    # every Level edit a 422 ("There is no suggestion to amend for this item"). A
    # fanned-out grouped row still writes the same product row several times with the same
    # value, which is idempotent by construction.
    if "level" in row:
        level_suggestion_service.amend_suggestion(
            db,
            product_id=str(rec.product_id),
            warehouse_id=(str(rec.warehouse_id) if rec.warehouse_id is not None else None),
            amended_level=(None if row["level"] is None else float(row["level"])),
            amended_by=actor,
            commit=False,
        )

    if "reorder_qty" in row:
        reorder_level_service.set_reorder_qty(
            db,
            product_id=str(rec.product_id),
            warehouse_id=(str(rec.warehouse_id) if rec.warehouse_id is not None else None),
            reorder_qty=(None if row["reorder_qty"] is None else float(row["reorder_qty"])),
            company_id=company_id,
            commit=False,
        )

    if "lifecycle" in row:
        product_economics_service.record_lifecycle_decision(
            db,
            product_id=str(rec.product_id),
            decision=row["lifecycle"],
            decided_by=actor,
            commit=False,
        )
