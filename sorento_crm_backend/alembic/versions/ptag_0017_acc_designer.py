"""Accessory card designer: several coloured pictures, rich spec + remark, per-row overrides, box presets.

PRICETAG-ACCESSORY-DESIGNER S1 (plan documentation/plans/dealer-kit/PLAN-pricetag-accessory-designer-07nov.md):

1. `accessory_images` (ordered pictures, optional colour name + hex). `copy_images` turns every
   `accessories.image_attachment_id` into image 1 (sort 0, no colour); idempotent, and the old
   column stays (unread).
2. `accessories.spec` widens to TEXT (rich HTML or plain); `accessories.remark` TEXT NULL.
3. `product_accessories` and `product_combo_accessories` gain `image_id` (FK accessory_images, SET
   NULL), `name_override`, `spec_override`, `remark_override`.
4. `dealer_kit.accessory_box_preset` (company scoped; unique per company on lower(name)).

Every statement is idempotent (`IF NOT EXISTS`), because the shared dev database converges through
`create_all` and may already hold these objects. Additive only.

Revision ID: ptag_0017_acc_designer
Revises: sales_0007_targets_view_own
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "ptag_0017_acc_designer"
down_revision = "sales_0007_targets_view_own"
branch_labels = None
depends_on = None

DDL = [
    """
    CREATE TABLE IF NOT EXISTS accessory_images (
        id UUID PRIMARY KEY,
        accessory_id UUID NOT NULL REFERENCES accessories(id) ON DELETE CASCADE,
        attachment_id UUID NOT NULL REFERENCES attachments(id) ON DELETE CASCADE,
        colour_name VARCHAR(40),
        colour_hex VARCHAR(7),
        sort_order INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP NOT NULL DEFAULT now(),
        CONSTRAINT ck_accessory_images_colour_hex
            CHECK (colour_hex IS NULL OR colour_hex ~ '^#[0-9a-fA-F]{6}$')
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_accessory_images_accessory_id ON accessory_images (accessory_id)",
    "ALTER TABLE accessories ALTER COLUMN spec TYPE TEXT",
    "ALTER TABLE accessories ADD COLUMN IF NOT EXISTS remark TEXT",
    "ALTER TABLE product_accessories ADD COLUMN IF NOT EXISTS image_id UUID "
    "REFERENCES accessory_images(id) ON DELETE SET NULL",
    "ALTER TABLE product_accessories ADD COLUMN IF NOT EXISTS name_override VARCHAR(200)",
    "ALTER TABLE product_accessories ADD COLUMN IF NOT EXISTS spec_override TEXT",
    "ALTER TABLE product_accessories ADD COLUMN IF NOT EXISTS remark_override TEXT",
    "ALTER TABLE product_combo_accessories ADD COLUMN IF NOT EXISTS image_id UUID "
    "REFERENCES accessory_images(id) ON DELETE SET NULL",
    "ALTER TABLE product_combo_accessories ADD COLUMN IF NOT EXISTS name_override VARCHAR(200)",
    "ALTER TABLE product_combo_accessories ADD COLUMN IF NOT EXISTS spec_override TEXT",
    "ALTER TABLE product_combo_accessories ADD COLUMN IF NOT EXISTS remark_override TEXT",
    """
    CREATE TABLE IF NOT EXISTS dealer_kit.accessory_box_preset (
        id UUID PRIMARY KEY,
        company_id UUID REFERENCES companies(id),
        name VARCHAR(100) NOT NULL,
        design JSONB NOT NULL,
        created_by VARCHAR,
        updated_by VARCHAR,
        created_at TIMESTAMP NOT NULL DEFAULT now(),
        updated_at TIMESTAMP NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_dealer_kit_accessory_box_preset_company_id "
    "ON dealer_kit.accessory_box_preset (company_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_dealer_kit_accessory_box_preset_company_name "
    "ON dealer_kit.accessory_box_preset (company_id, lower(name))",
]

COPY_IMAGES_SQL = """
INSERT INTO accessory_images (id, accessory_id, attachment_id, sort_order)
SELECT gen_random_uuid(), a.id, a.image_attachment_id, 0
FROM accessories a
WHERE a.image_attachment_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM accessory_images i
      WHERE i.accessory_id = a.id AND i.attachment_id = a.image_attachment_id
  )
"""


def create_schema(bind) -> None:
    for statement in DDL:
        bind.execute(sa.text(statement))


def copy_images(bind) -> None:
    bind.execute(sa.text(COPY_IMAGES_SQL))


def upgrade() -> None:
    bind = op.get_bind()
    create_schema(bind)
    copy_images(bind)


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("product_combo_accessories", "product_accessories"):
        for column in ("remark_override", "spec_override", "name_override", "image_id"):
            bind.execute(sa.text(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {column}"))
    bind.execute(sa.text("DROP TABLE IF EXISTS dealer_kit.accessory_box_preset"))
    bind.execute(sa.text("DROP TABLE IF EXISTS accessory_images"))
    bind.execute(sa.text("ALTER TABLE accessories DROP COLUMN IF EXISTS remark"))
    # `spec` stays TEXT: narrowing it back could truncate rich text.
