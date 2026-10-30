"""SO-LINE-DESC: the AutoCount SO line description on `sales_order_lines`, and the per-product
tick that shows it in the OI email.

Adds `sales_order_lines.description` (TEXT NULL, filled by ingest from the line's
`product_name`) and `products.show_so_line_description` (BOOLEAN NOT NULL DEFAULT false), then
ticks every product coded RPACC (the generic spare-part code staff describe in the line text).

Revision ID: sld_0001_so_line_description
Revises: qca1_0001_amendment_requests
"""
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "sld_0001_so_line_description"
down_revision = "qca1_0001_amendment_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sales_order_lines ADD COLUMN IF NOT EXISTS description TEXT")
    op.execute(
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS show_so_line_description "
        "BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute("UPDATE products SET show_so_line_description = true WHERE product_code = 'RPACC'")


def downgrade() -> None:
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS show_so_line_description")
    op.execute("ALTER TABLE sales_order_lines DROP COLUMN IF EXISTS description")
