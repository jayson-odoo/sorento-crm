"""Add contact_number to users.

Revision ID: 118_user_contact_number
Revises: 117_user_list_column_configs
"""

from alembic import op
import sqlalchemy as sa


revision = "118_user_contact_number"
down_revision = "117_user_list_column_configs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("contact_number", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "contact_number")

