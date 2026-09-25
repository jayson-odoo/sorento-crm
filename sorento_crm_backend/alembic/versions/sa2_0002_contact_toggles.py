"""Chatbot stock ask v2 S2 (PLAN-chatbot-stock-ask-v2-24sep.md) - per-contact toggles.

`respond_contacts.notify_salesman` and `respond_contacts.packing_list_allowed` (R7
names, R7 defaults - both OFF, unlike the existing `chatbot_stock_allowed` column
which defaults true). `ADD COLUMN IF NOT EXISTS` (500_product_exclude_planning's
idiom) keeps this re-runnable against a schema where `Base.metadata.create_all`
already created the ORM-mapped columns.

Revision ID: sa2_0002_contact_toggles
Revises: sa2_0001_xy_columns
Create Date: 2026-09-24
"""
from alembic import op
import sqlalchemy as sa

revision = "sa2_0002_contact_toggles"
down_revision = "sa2_0001_xy_columns"
branch_labels = None
depends_on = None

_COLUMNS = ("notify_salesman", "packing_list_allowed")


def upgrade() -> None:
    bind = op.get_bind()
    for column in _COLUMNS:
        bind.execute(
            sa.text(
                f"ALTER TABLE respond_contacts ADD COLUMN IF NOT EXISTS {column} "
                "BOOLEAN NOT NULL DEFAULT false"
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    for column in reversed(_COLUMNS):
        bind.execute(sa.text(f"ALTER TABLE respond_contacts DROP COLUMN IF EXISTS {column}"))
