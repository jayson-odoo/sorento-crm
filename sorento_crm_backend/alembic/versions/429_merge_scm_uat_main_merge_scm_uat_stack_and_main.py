"""merge scm-uat stack and main

Revision ID: 429_merge_scm_uat_main
Revises: 422_report_views_and_perms, 428_order_inquiry_ack_state
Create Date: 2026-08-27 05:50:29.764146

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '429_merge_scm_uat_main'
down_revision = ('422_report_views_and_perms', '428_order_inquiry_ack_state')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
