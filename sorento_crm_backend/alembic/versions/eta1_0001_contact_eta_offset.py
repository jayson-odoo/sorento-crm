"""Issue #1328 - per-contact switch for the chatbot ETA offset.

`respond_contacts.chatbot_eta_offset_applied` BOOLEAN NOT NULL DEFAULT true: whether the ETA
this contact is told carries the product-or-category `chatbot_eta_offset_days`
(`app/services/eta_policy.py`). Default true is the stock ask's behaviour before the switch
existed. `ADD COLUMN IF NOT EXISTS` (sa2_0002_contact_toggles' idiom) keeps this re-runnable
against a schema where `Base.metadata.create_all` already created the ORM-mapped column.

Also the MERGE point of main's two heads as of 28 Sep 2026 (`chatbot_esc_confirm_1323` and
`fin_0002_billing_demand_class`, both children of `fin_0001_billing_documents`), so the tree
has one head again. Neither parent's DDL touches `respond_contacts`, so the order is free.

Revision ID: eta1_0001_contact_eta_offset
Revises: chatbot_esc_confirm_1323, fin_0002_billing_demand_class
Create Date: 2026-09-28
"""
from alembic import op
import sqlalchemy as sa

revision = "eta1_0001_contact_eta_offset"
down_revision = ("chatbot_esc_confirm_1323", "fin_0002_billing_demand_class")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "ALTER TABLE respond_contacts ADD COLUMN IF NOT EXISTS chatbot_eta_offset_applied "
            "BOOLEAN NOT NULL DEFAULT true"
        )
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("ALTER TABLE respond_contacts DROP COLUMN IF EXISTS chatbot_eta_offset_applied")
    )
