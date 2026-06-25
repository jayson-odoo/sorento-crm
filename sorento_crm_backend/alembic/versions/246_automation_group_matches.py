"""Automation group_matches: combine multi-match runs into one email per recipient.

Revision ID: 246_automation_group_matches
Revises: 245_coverage_redirect_assignments
Create Date: 2026-06-25

Adds ``automations.group_matches``. When true (default), a scheduled run of the
``days_before_promotion_end`` trigger that matches multiple promotions sends ONE
combined email per recipient (listing every expiring promotion) instead of one
email per promotion. Existing rows default to true (the desired digest behavior).

Idempotent and reversible.
"""
from alembic import op
import sqlalchemy as sa


revision = "246_automation_group_matches"
down_revision = "245_coverage_redirect_assignments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "automations",
        sa.Column(
            "group_matches",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("automations", "group_matches")
