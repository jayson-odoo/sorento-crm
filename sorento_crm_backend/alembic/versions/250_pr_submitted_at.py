"""purchase_requests.submitted_at — auto-stamped submit date (top document "Date").

Revision ID: 250_pr_submitted_at
Revises: 249_agent_team_notify_ext
Create Date: 2026-06-30

The PR/SF document has three dates: submitted (top, auto), request (footer-left,
user-entered = request_date), approved (footer-right = approved_at). submitted_at is
re-stamped on every submit (incl. resubmit-after-rejection) in portal submit_draft.
Backfill existing non-draft rows from created_at so the top date isn't blank.
See docs/plans/PLAN-pr-sf-three-dates.md.
"""
from alembic import op
import sqlalchemy as sa


revision = "250_pr_submitted_at"
down_revision = "249_agent_team_notify_ext"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "purchase_requests",
        sa.Column("submitted_at", sa.DateTime(timezone=False), nullable=True),
    )
    # Backfill: existing submitted/approved/rejected/processed rows get their
    # original creation time as the submitted date. Drafts stay NULL.
    op.execute(
        "UPDATE purchase_requests "
        "SET submitted_at = created_at "
        "WHERE submitted_at IS NULL AND status <> 'draft'"
    )


def downgrade() -> None:
    op.drop_column("purchase_requests", "submitted_at")
