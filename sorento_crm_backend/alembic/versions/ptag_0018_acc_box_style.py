"""Accessory box style override per product and per combo.

PRICETAG-ACCESSORY-DESIGNER S6 (plan documentation/plans/dealer-kit/PLAN-pricetag-accessory-designer-07nov.md
"Box style override per product / per combo"): `products.accessory_box_preset_id` and
`product_combos.accessory_box_preset_id`, FK `dealer_kit.accessory_box_preset` ON DELETE SET NULL
(NULL = the tag template's own box). Idempotent (`IF NOT EXISTS`), additive only.

Revision ID: ptag_0018_acc_box_style
Revises: ptag_0017_acc_designer
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "ptag_0018_acc_box_style"
down_revision = "ptag_0017_acc_designer"
branch_labels = None
depends_on = None

DDL = [
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS accessory_box_preset_id UUID "
    "REFERENCES dealer_kit.accessory_box_preset(id) ON DELETE SET NULL",
    "ALTER TABLE product_combos ADD COLUMN IF NOT EXISTS accessory_box_preset_id UUID "
    "REFERENCES dealer_kit.accessory_box_preset(id) ON DELETE SET NULL",
    "CREATE INDEX IF NOT EXISTS ix_products_accessory_box_preset_id ON products (accessory_box_preset_id)",
    "CREATE INDEX IF NOT EXISTS ix_product_combos_accessory_box_preset_id "
    "ON product_combos (accessory_box_preset_id)",
]


def upgrade() -> None:
    bind = op.get_bind()
    for statement in DDL:
        bind.execute(sa.text(statement))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DROP INDEX IF EXISTS ix_product_combos_accessory_box_preset_id"))
    bind.execute(sa.text("DROP INDEX IF EXISTS ix_products_accessory_box_preset_id"))
    bind.execute(sa.text("ALTER TABLE product_combos DROP COLUMN IF EXISTS accessory_box_preset_id"))
    bind.execute(sa.text("ALTER TABLE products DROP COLUMN IF EXISTS accessory_box_preset_id"))
