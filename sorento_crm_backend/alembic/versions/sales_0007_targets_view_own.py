"""sales.targets.view_own: own-only sales targets (AI-TOOLS-WAVE2, owner ruling 5 Nov 2026).

Additive: one permission row, created when absent and granted to NO role (an admin grants it to the
salesperson role). Its holder, without `sales.targets.view`, sees only the agent targets of their own sales
agents, with their commission, on the Sales targets screen and in the assistant (`own_scope.sales_target_clause`).

Downgrade keeps the permission row (the sales_0003 precedent: a role may hold it by then).

Revision ID: sales_0007_targets_view_own
Revises: sfam_0001_supplier_ledger_family
Create Date: 2026-11-05
"""
import sqlalchemy as sa
from alembic import op

revision = "sales_0007_targets_view_own"
down_revision = "sfam_0001_supplier_ledger_family"
branch_labels = None
depends_on = None

_SLUG = "sales.targets.view_own"
_NAME = "View Own Sales Targets"
_DESCRIPTION = (
    "See only the agent targets of your own sales agents, with their commission. "
    "Ignored when View Sales Targets is also held."
)


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO user_permissions (id, slug, name, description, created_at)
            SELECT gen_random_uuid()::text, :slug, :name, :descr, now()
            WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :slug)
            """
        ),
        {"slug": _SLUG, "name": _NAME, "descr": _DESCRIPTION},
    )


def downgrade() -> None:
    pass
