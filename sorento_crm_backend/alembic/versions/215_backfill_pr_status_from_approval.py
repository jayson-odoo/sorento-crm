"""Backfill purchase_requests.status from approval_status for pre-decision rows.

Revision ID: 215_backfill_pr_status_from_approval
Revises: 214_sla_tracking_source_entity_index
Create Date: 2026-05-27

Commit 26a0f64c advanced the lifecycle status to approved/rejected on the public
approval link and pre-approval reject paths, but only going forward. Rows decided
BEFORE that fix still sit at status='submitted' with approval_status approved/rejected,
so the portal renders "Submitted" while the system list shows Approved/Rejected.
This backfills those rows to align status with the recorded decision.

Only 'submitted' rows are touched. 'draft' rows are left alone (distinct lifecycle
state), and 'submitted'+'pending' is already correct.
"""
from alembic import op


revision = "215_backfill_pr_status_from_approval"
down_revision = "214_sla_tracking_source_entity_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE purchase_requests SET status = 'approved' "
        "WHERE status = 'submitted' AND approval_status = 'approved'"
    )
    op.execute(
        "UPDATE purchase_requests SET status = 'rejected' "
        "WHERE status = 'submitted' AND approval_status = 'rejected'"
    )


def downgrade() -> None:
    # Data backfill — not reversible (cannot distinguish backfilled rows from
    # ones that legitimately reached approved/rejected after the fix).
    pass
