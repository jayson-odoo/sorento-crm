"""TAG-TEMPLATE-DUPLICATE item 6: `dealer_kit.tag_template.sort_order`.

The Tag Templates list's shared manual order (drag-and-drop), the list's default order. Additive and
nullable: existing rows are numbered by created date within their company, and a row without a
number sorts last.

Revision ID: ttord_0001_tag_template_sort
Revises: ttdc_0001_tag_template_archived
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "ttord_0001_tag_template_sort"
down_revision = "ttdc_0001_tag_template_archived"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("ALTER TABLE dealer_kit.tag_template ADD COLUMN IF NOT EXISTS sort_order INTEGER")
    )
    bind.execute(
        sa.text(
            """
            UPDATE dealer_kit.tag_template t
               SET sort_order = n.rn
              FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY company_id ORDER BY created_at, id
                           ) AS rn
                      FROM dealer_kit.tag_template
                   ) n
             WHERE n.id = t.id
               AND t.sort_order IS NULL
            """
        )
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("ALTER TABLE dealer_kit.tag_template DROP COLUMN IF EXISTS sort_order")
    )
