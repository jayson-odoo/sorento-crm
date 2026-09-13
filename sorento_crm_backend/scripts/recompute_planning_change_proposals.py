"""Bring PENDING planning-change rows up to the composed suggestion (Slice C).

`documentation/plans/scm/PLAN-scm-change-management-one-engine.md`, Slice C: a row used to
carry a reaction VERB (`suggested`/`why`) and, for some kinds, a proposal. It now carries
`suggestion_json` - the ladder re-run at the line's new state, diffed against what the line
holds, one sentence per component - and `composition_json`, pre-filled so Confirm posts it
unchanged.

A row raised BEFORE that deploy has neither, so the board shows its Was / Now table with no
suggestion under it and Confirm has nothing to post. This recomputes both, plus the re-run
they are derived from, for every row that can still be acted on: an unapplied batch, a
`pending` row, no decision taken yet (a row somebody already confirmed or amended keeps the
composition they decided - recomputing it would quietly replace a person's answer).

Idempotent: it writes only where the recomputed value differs, so a second run reports
everything unchanged. It reads TODAY's state - stock, placements, the ladder - which is
what the board would show if the batch were raised now.

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
from app.models.product import Product
from app.models.project_so import ProjectSalesOrder
from app.services.planning_change_service import (
    _as_date,
    _hot_selling_evidence,
    _inquiry_rows_and_buy_actioned,
    _is_immediate,
    _placed_links,
    _so_number,
    compose_row_state,
)


def _facts_for(db, row: PlanningChangeRow, product_id: str | None) -> dict:
    """The row's own stored facts, refreshed with everything the diff reads today.

    The hot-selling verdict and what is on a document are re-measured rather than trusted:
    a row raised weeks ago may have been placed on a purchase order since, and that is
    exactly what decides whether its suggestion reallocates or releases.
    """
    facts = dict(row.facts_json or {})
    from_json = row.from_json or {}
    to_json = row.to_json or {}
    new_date = _as_date(to_json.get("required_date")) or _as_date(
        from_json.get("required_date")
    )
    dealer_where, project_where = _hot_selling_evidence(
        db, {product_id} if product_id else set()
    )
    _inquiry_rows, buy_actioned = _inquiry_rows_and_buy_actioned(
        db, str(row.project_line_id) if row.project_line_id else None
    )
    facts["dealer_hot_selling"] = {
        "value": bool(product_id and product_id in dealer_where),
        "where": dealer_where.get(product_id, []) if product_id else [],
    }
    facts["project_hot_selling"] = {
        "value": bool(product_id and product_id in project_where),
        "where": project_where.get(product_id, []) if product_id else [],
    }
    facts["buy_actioned"] = buy_actioned
    facts["placed"] = _placed_links(
        db, str(row.project_line_id) if row.project_line_id else None
    )
    facts["new_date"] = new_date.isoformat() if new_date else None
    old_date = _as_date(from_json.get("required_date"))
    facts["old_date"] = old_date.isoformat() if old_date else None
    facts["immediate"] = _is_immediate(new_date)
    return facts


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
        skipped = 0
        for batch in batches:
            rows = (
                db.query(PlanningChangeRow)
                .filter(
                    PlanningChangeRow.batch_id == batch.id,
                    PlanningChangeRow.applied_state == PLANNING_CHANGE_STATE_PENDING,
                    PlanningChangeRow.decision.is_(None),
                )
                .all()
            )
            for row in rows:
                order = (
                    db.query(ProjectSalesOrder)
                    .filter(ProjectSalesOrder.id == row.project_sales_order_id)
                    .one_or_none()
                )
                if order is None:
                    skipped += 1
                    continue
                product_id = None
                if row.item_code:
                    product_id = (
                        db.query(Product.id)
                        .filter(Product.product_code == row.item_code)
                        .scalar()
                    )
                facts = _facts_for(db, row, str(product_id) if product_id else None)
                proposal, suggestion, composition = compose_row_state(
                    db,
                    kind=row.kind,
                    held=row.held_json,
                    facts=facts,
                    from_json=row.from_json or {},
                    to_json=row.to_json or {},
                    item_code=row.item_code,
                    product_id=str(product_id) if product_id else None,
                    project_line_id=str(row.project_line_id) if row.project_line_id else None,
                    core_line_id=str(row.core_line_id) if row.core_line_id else None,
                    so_number=_so_number(order),
                    board_cache=board_cache,
                )
                if (
                    proposal == row.proposal_json
                    and suggestion == row.suggestion_json
                    and composition == row.composition_json
                ):
                    unchanged += 1
                    continue
                row.facts_json = facts
                row.proposal_json = proposal
                row.suggestion_json = suggestion
                row.composition_json = composition
                touched += 1
        db.commit()
        print(
            f"batches examined: {len(batches)}, rows recomposed: {touched}, "
            f"rows unchanged: {unchanged}, rows skipped (no order): {skipped}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
