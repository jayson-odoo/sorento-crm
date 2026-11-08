"""Accessory colours: an ordered list of their own, independent of the pictures.

PRICETAG-ACCESSORY-DESIGNER S7 (plan documentation/plans/dealer-kit/PLAN-pricetag-accessory-designer-07nov.md
"S7 Pictures and colours are independent"): table `accessory_colours` (id, accessory_id FK CASCADE, name
VARCHAR(40) NULL, hex VARCHAR(7) NOT NULL, sort_order, created_at; unique per accessory on lower(hex)).
`copy_picture_colours` copies each accessory's picture colours (distinct hex, in picture order, name kept)
into it, skipping any already there. `accessory_images.colour_name` / `colour_hex` stay, unread.
Idempotent (`IF NOT EXISTS`, `ON CONFLICT DO NOTHING`), additive only.

Revision ID: ptag_0019_acc_colours
Revises: ptag_0018_acc_box_style
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "ptag_0019_acc_colours"
down_revision = "ptag_0018_acc_box_style"
branch_labels = None
depends_on = None

DDL = [
    """
    CREATE TABLE IF NOT EXISTS accessory_colours (
        id UUID PRIMARY KEY,
        accessory_id UUID NOT NULL REFERENCES accessories(id) ON DELETE CASCADE,
        name VARCHAR(40),
        hex VARCHAR(7) NOT NULL,
        sort_order INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP NOT NULL DEFAULT now(),
        CONSTRAINT ck_accessory_colours_hex CHECK (hex ~ '^#[0-9a-fA-F]{6}$')
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_accessory_colours_accessory_hex "
    "ON accessory_colours (accessory_id, lower(hex))",
    "CREATE INDEX IF NOT EXISTS ix_accessory_colours_accessory_id ON accessory_colours (accessory_id)",
]

#: One row per distinct hex per accessory, in picture order (first picture wins the name), appended after
#: whatever the accessory already lists; a hex already there (any case) is skipped.
COPY_SQL = """
WITH firsts AS (
    SELECT DISTINCT ON (i.accessory_id, lower(i.colour_hex))
           i.accessory_id,
           -- the first non-empty name any picture gave this hex
           (SELECT i2.colour_name FROM accessory_images i2
             WHERE i2.accessory_id = i.accessory_id AND lower(i2.colour_hex) = lower(i.colour_hex)
               AND nullif(btrim(i2.colour_name), '') IS NOT NULL
             ORDER BY i2.sort_order, i2.created_at, i2.id LIMIT 1) AS colour_name,
           lower(i.colour_hex) AS hex, i.sort_order, i.created_at, i.id
    FROM accessory_images i
    WHERE i.colour_hex IS NOT NULL AND i.colour_hex ~ '^#[0-9a-fA-F]{6}$'
    ORDER BY i.accessory_id, lower(i.colour_hex), i.sort_order, i.created_at, i.id
), fresh AS (
    SELECT f.*, row_number() OVER (PARTITION BY f.accessory_id ORDER BY f.sort_order, f.created_at, f.id) AS n
    FROM firsts f
    WHERE NOT EXISTS (
        SELECT 1 FROM accessory_colours c WHERE c.accessory_id = f.accessory_id AND lower(c.hex) = f.hex
    )
)
INSERT INTO accessory_colours (id, accessory_id, name, hex, sort_order)
SELECT gen_random_uuid(), fresh.accessory_id, fresh.colour_name, fresh.hex,
       coalesce((SELECT max(c.sort_order) + 1 FROM accessory_colours c WHERE c.accessory_id = fresh.accessory_id), 0)
       + fresh.n - 1
FROM fresh
ON CONFLICT DO NOTHING
"""


def create_schema(bind) -> None:
    for statement in DDL:
        bind.execute(sa.text(statement))


def copy_picture_colours(bind) -> None:
    bind.execute(sa.text(COPY_SQL))


def upgrade() -> None:
    bind = op.get_bind()
    create_schema(bind)
    copy_picture_colours(bind)


def downgrade() -> None:
    op.get_bind().execute(sa.text("DROP TABLE IF EXISTS accessory_colours"))
