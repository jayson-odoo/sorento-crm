"""NEW-PRODUCT-APP v4: the paper layout (dimension, material, thickness, packing, lead time, feedback stamp).

Additive only and idempotent (`ADD COLUMN IF NOT EXISTS`) so the shared dev DB, which converges
through `create_all`, can take it in any order. Nothing is dropped: the columns the paper form
no longer asks for stay in the table, nullable.

Plan: documentation/plans/procurement/PLAN-new-product-application-17oct.md ("v4").

Revision ID: npa_0002_paper_layout
Revises: npa_0001_new_product_apps
"""
import sqlalchemy as sa
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "npa_0002_paper_layout"
down_revision = "npa_0001_new_product_apps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for statement in (
        "ALTER TABLE new_product_application_lines ADD COLUMN IF NOT EXISTS dimension TEXT",
        "ALTER TABLE new_product_application_lines ADD COLUMN IF NOT EXISTS material TEXT",
        "ALTER TABLE new_product_application_lines ADD COLUMN IF NOT EXISTS thickness TEXT",
        "ALTER TABLE new_product_application_lines ADD COLUMN IF NOT EXISTS packing TEXT",
        "ALTER TABLE new_product_applications ADD COLUMN IF NOT EXISTS lead_time TEXT",
        "ALTER TABLE new_product_applications ADD COLUMN IF NOT EXISTS feedback_by VARCHAR(100) "
        "REFERENCES users(id) ON DELETE SET NULL",
        "ALTER TABLE new_product_applications ADD COLUMN IF NOT EXISTS feedback_at TIMESTAMP",
    ):
        bind.execute(sa.text(statement))


def downgrade() -> None:
    bind = op.get_bind()
    for statement in (
        "ALTER TABLE new_product_applications DROP COLUMN IF EXISTS feedback_at",
        "ALTER TABLE new_product_applications DROP COLUMN IF EXISTS feedback_by",
        "ALTER TABLE new_product_applications DROP COLUMN IF EXISTS lead_time",
        "ALTER TABLE new_product_application_lines DROP COLUMN IF EXISTS packing",
        "ALTER TABLE new_product_application_lines DROP COLUMN IF EXISTS thickness",
        "ALTER TABLE new_product_application_lines DROP COLUMN IF EXISTS material",
        "ALTER TABLE new_product_application_lines DROP COLUMN IF EXISTS dimension",
    ):
        bind.execute(sa.text(statement))
