"""merge overdue_grace + draft_proposed_desc heads

464_overdue_grace (#618, main) and 467_merge_draft_proposed_desc (#594, main) both
forked from 463_draft_proposed: 467 merged 463 and 466_shipment_line_description but
never picked up 464, leaving two alembic heads and breaking `alembic upgrade head` on
deploy. This no-op merge unifies them into one head.

Revision ID: 468_merge_overdue_grace_desc
Revises: 464_overdue_grace, 467_merge_draft_proposed_desc
Create Date: 2026-09-04

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "468_merge_overdue_grace_desc"
down_revision = ("464_overdue_grace", "467_merge_draft_proposed_desc")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
