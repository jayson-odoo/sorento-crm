"""Let an admin choose which companies the discontinued-product check reports on.

`product_discontinued_check` reads `products` with the scheduler's company scope set
to all companies, so it is company-blind by nature. That was harmless while Sorento
was the only catalogue. The moment a second company's products are loaded, its entire
discontinued history lands in one notification aimed at staff who do not handle it.

Blank means "Sorento only" (resolved in code, not stored), so this column stays NULL
on every existing install and nothing changes until someone opts a company in.

Revision ID: 312_discontinued_notify_company_ids
Revises: 311_split_pr_approve_permission
"""
import sqlalchemy as sa
from alembic import op

revision = "312_discontinued_notify_company_ids"
down_revision = "311_split_pr_approve_permission"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "system_settings",
        sa.Column("product_discontinued_notify_company_ids", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("system_settings", "product_discontinued_notify_company_ids")
