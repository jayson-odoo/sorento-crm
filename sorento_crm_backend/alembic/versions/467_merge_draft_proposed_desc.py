"""merge draft_proposed + shipment_line_description heads

463_draft_proposed (PR #575, main) and 466_shipment_line_description (this lane) both
forked from 464_merge_plan_stmt_fulfil, creating two alembic heads and breaking
`alembic upgrade head` on deploy. This no-op merge unifies them into one head.

Revision ID: 467_merge_draft_proposed_desc
Revises: 463_draft_proposed, 466_shipment_line_description
Create Date: 2026-09-03

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "467_merge_draft_proposed_desc"
down_revision = ("463_draft_proposed", "466_shipment_line_description")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
