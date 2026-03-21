"""Remove PIC / assigned respond user from access_agents.

Revision ID: 100_drop_agent_pic
Revises: 099_module_bundles
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa


revision = "100_drop_agent_pic"
down_revision = "099_module_bundles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("access_agents", "pic_respond_user_id")


def downgrade() -> None:
    op.add_column(
        "access_agents",
        sa.Column("pic_respond_user_id", sa.Text(), nullable=True),
    )
