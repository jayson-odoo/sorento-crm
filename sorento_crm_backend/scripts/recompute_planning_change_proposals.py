"""One-off: recompute `proposal_json` for every PENDING `replan` row of every unapplied
planning-change batch (19 August 2026 fix, `app/services/planning_change_service.py`'s
`_proposal_for`).

Before the fix, a `replan` row's proposal was built by a plain `FulfilmentBoardService.build()`
call. When the line's ACTIVE decision still covers it (true for `advanced`/`qty_up`/`delayed`-
turned-`release` rows - Apply is what excludes the line, and Apply has not run yet on a PENDING
row), the board found it `covered` and handed back the FROZEN composition instead of running
the ladder: one source, `trail: []`, no `rank_factors`. Existing pending rows built before the
fix carry that slimmed-down proposal in the database and need a one-time recompute; every row
built from here on gets the full contribution at build time.

Run with the target DATABASE_URL inline (never bare - see `sorento_crm_backend/CLAUDE.md`):
    DATABASE_URL=... venv/bin/python scripts/recompute_planning_change_proposals.py
"""
from __future__ import annotations

from app.database import SessionLocal
from app.models.base import set_company_scope
from app.services.company_scope import register_company_scope_listeners
from app.models.planning_change import (
    PLANNING_CHANGE_STATE_PENDING,
    PlanningChangeBatch,
    PlanningChangeRow,
)
from app.models.project_so import ProjectSalesOrder
from app.services.planning_change_service import _json_safe, _proposal_for, _so_number


def main() -> None:
    register_company_scope_listeners()
    db = SessionLocal()
    # A maintenance script has no request-scoped JWT/API-key to resolve a company from - the
    # scope defaults to `UNSET` (fail-closed, 0 rows) otherwise. `None` = every company, the
    # same scope an unscoped X-API-Key caller reads with.
    set_company_scope(db, None)
    try:
        batches = (
            db.query(PlanningChangeBatch)
            .filter(PlanningChangeBatch.applied_at.is_(None))
            .all()
        )
        board_cache: dict = {}
        touched = 0
        unchanged = 0
        skipped_no_line = 0
        for batch in batches:
            rows = (
                db.query(PlanningChangeRow)
                .filter(
                    PlanningChangeRow.batch_id == batch.id,
                    PlanningChangeRow.applied_state == PLANNING_CHANGE_STATE_PENDING,
                    PlanningChangeRow.suggested == "replan",
                )
                .all()
            )
            for row in rows:
                if not row.project_line_id or not row.core_line_id:
                    skipped_no_line += 1
                    continue
                order = (
                    db.query(ProjectSalesOrder)
                    .filter(ProjectSalesOrder.id == row.project_sales_order_id)
                    .one_or_none()
                )
                if order is None:
                    skipped_no_line += 1
                    continue
                so_number = _so_number(order)
                proposal = _proposal_for(
                    db, board_cache, so_number, str(row.core_line_id), str(row.project_line_id)
                )
                new_proposal = _json_safe(proposal)
                if new_proposal != row.proposal_json:
                    row.proposal_json = new_proposal
                    touched += 1
                else:
                    unchanged += 1
        db.commit()
        print(
            f"batches examined: {len(batches)}, rows recomputed (changed): {touched}, "
            f"rows unchanged: {unchanged}, rows skipped (no line): {skipped_no_line}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
