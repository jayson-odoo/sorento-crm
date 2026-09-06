"""`customers` gains `region` (AutoCount `Debtor.AreaCode`, D16), and a new
`order_inquiry_conflicts` table records an ESB warehouse overwrite for the
Order Inquiry worklist to render (D22, S2).

Revision ID: 476_customers_region
Revises: 475_products_remark
"""
import sqlalchemy as sa
from alembic import op

revision = "476_customers_region"
down_revision = "475_products_remark"
branch_labels = None
depends_on = None


def apply(bind) -> None:
    bind.execute(sa.text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS region VARCHAR(80)"))
    bind.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS order_inquiry_conflicts (
                id UUID PRIMARY KEY,
                company_id UUID NOT NULL REFERENCES companies(id),
                sales_order_id UUID NOT NULL REFERENCES sales_orders(id) ON DELETE CASCADE,
                sales_order_line_id UUID NOT NULL REFERENCES sales_order_lines(id) ON DELETE CASCADE,
                previous_warehouse_id UUID REFERENCES warehouses(id) ON DELETE SET NULL,
                new_warehouse_id UUID REFERENCES warehouses(id) ON DELETE SET NULL,
                source VARCHAR(32) NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT now()
            )
            """
        )
    )
    bind.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_order_inquiry_conflicts_company_id "
            "ON order_inquiry_conflicts (company_id)"
        )
    )
    bind.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_order_inquiry_conflicts_sales_order_id "
            "ON order_inquiry_conflicts (sales_order_id)"
        )
    )


def revert(bind) -> None:
    bind.execute(sa.text("DROP TABLE IF EXISTS order_inquiry_conflicts"))
    bind.execute(sa.text("ALTER TABLE customers DROP COLUMN IF EXISTS region"))


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    revert(op.get_bind())
