"""One header per SO: fold every planning_change_batch header onto the order's own
amendment_id IS NULL header (PLAN-oi-worklist-one-header.md, S3, AC-OH-34).

`derive_for_book_change` used to mint a synthetic `so_amendments` row
(`from_version_kind='planning_change_batch'`) and its own `order_inquiries` header for
every planning-change batch apply, on the theory that the DB-level singleton on
`amendment_id IS NULL` per sales order would otherwise collide with whatever `confirm()`
had just written in the same apply. It never did - `ensure_inquiry` returns the exact
header `confirm()` wrote earlier in the same apply - so that header was pure duplication:
one sales order carrying two order inquiry numbers (prod: OI-000477 and OI-000734 on
SO314593, the origin case this lane fixes). As of this revision `derive_for_book_change`
appends straight onto the order's own null-amendment header, so this migration is a
one-time cleanup of what the OLD code path already wrote.

Runs entirely through `project_order_inquiry_service.fold_planning_change_batch_headers`,
so the ORM's own row-move-and-cleanup logic is not duplicated here in raw SQL: for every
`order_inquiries` row whose amendment is `planning_change_batch`, its rows move onto the
order's own null header (minted when the order somehow has none, copying company_id,
project_sales_order_id, state, raised_by and raised_at off the oldest header being
folded), then the emptied header and its synthetic amendment are deleted. Row ids, links,
claims and handover records are all untouched - only `order_inquiry_rows.order_inquiry_id`
moves. Idempotent: a second run finds no `planning_change_batch` header left and does
nothing.

Downgrade is a no-op: recreating the synthetic per-apply headers this revision folds away
would mean inventing which rows belonged to which now-deleted batch header, which nothing
after this revision records - there is no way back that is not itself a guess.

Revision ID: oioh_0001_one_header_per_so
Revises: undo_0002_seed_undone
Create Date: 2026-09-17
"""
from __future__ import annotations

import logging

from alembic import op
from sqlalchemy.orm import Session

logger = logging.getLogger("alembic.oioh_0001")

revision = "oioh_0001_one_header_per_so"
down_revision = "undo_0002_seed_undone"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.services.project_order_inquiry_service import (
        fold_planning_change_batch_headers,
    )

    session = Session(bind=op.get_bind())
    try:
        folded = fold_planning_change_batch_headers(session)
        session.commit()
        logger.info("oioh_0001: folded %d planning_change_batch header(s)", folded)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def downgrade() -> None:
    # No-op by design - see the module docstring. The synthetic per-apply headers this
    # revision folds away are gone, and nothing records enough to reconstruct which rows
    # belonged to which one.
    pass
