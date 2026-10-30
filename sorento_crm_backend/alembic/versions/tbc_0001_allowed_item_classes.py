"""TAG-BRAND-CLASS: `respond_contacts.allowed_item_class_codes`.

The item class codes a contact may see (upper-cased, `__NONE__` = products with no class); NULL
= every class (PLAN-tag-brand-class-30oct.md D1). NULL everywhere after the upgrade, so no
contact's access changes on deploy. `brand_class_ids` (item_class_0001) stays, unread and
unwritten; a later cleanup PR drops it. Additive and idempotent.

Revision ID: tbc_0001_allowed_item_classes
Revises: agp1_0001_agent_foundation
Create Date: 2026-10-30
"""
from alembic import op

revision = "tbc_0001_allowed_item_classes"
down_revision = "agp1_0001_agent_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE respond_contacts ADD COLUMN IF NOT EXISTS allowed_item_class_codes VARCHAR(50)[]"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE respond_contacts DROP COLUMN IF EXISTS allowed_item_class_codes")
