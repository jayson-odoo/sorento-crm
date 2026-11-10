"""Seed `products.cost.view` and grant it to purchasing and management roles (SUPPLIER-COST-ACCESS).

Owner + management, 9 Nov 2026: cost price, supplier unit costs, last purchase / PO costs and the
product Suppliers / Purchase History tabs are for purchasing and management only. Plan:
`documentation/plans/products/PLAN-supplier-cost-access-10nov.md`.

Additive only: one permission row, granted BY SLUG to the roles crew read from the dev database
(10 Nov 2026): admin, director, purchasing_manager, purchasing, purchasing_executive.
superadmin passes every check by bypass. Deliberately NOT a sweep from an existing slug:
`procurement.cost_price_changes.view` and `procurement.product_suppliers.view` are both held by
sales-side roles today (project.customer.service, marketing_*), which are exactly the roles this
lane takes cost away from. Nothing is revoked; a role missing here is granted in the RBAC UI.

Revision ID: sca_0001_products_cost_view
Revises: town_0001_view_perm
Create Date: 2026-11-10
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "sca_0001_products_cost_view"
down_revision = "town_0001_view_perm"
branch_labels = None
depends_on = None

PERM_SLUG = "products.cost.view"
PERM_NAME = "View Product Cost"
PERM_DESCRIPTION = (
    "See cost price, supplier unit costs, last purchase / PO costs and the product Suppliers and "
    "Purchase History tabs; History shows cost values."
)
GRANT_ROLE_SLUGS = ("admin", "director", "purchasing_manager", "purchasing", "purchasing_executive")


def grant_cost_view(bind) -> None:
    """Create the permission if absent and grant it to `GRANT_ROLE_SLUGS`. Idempotent."""
    bind.execute(
        sa.text(
            """
            INSERT INTO user_permissions (id, slug, name, description, created_at)
            SELECT gen_random_uuid()::text, :slug, :name, :descr, now()
            WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :slug)
            """
        ),
        {"slug": PERM_SLUG, "name": PERM_NAME, "descr": PERM_DESCRIPTION},
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
            SELECT gen_random_uuid()::text, r.id, p.id, now()
            FROM user_roles r
            CROSS JOIN user_permissions p
            WHERE p.slug = :slug AND r.slug = ANY(:roles)
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        ),
        {"slug": PERM_SLUG, "roles": list(GRANT_ROLE_SLUGS)},
    )


def upgrade() -> None:
    grant_cost_view(op.get_bind())


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM user_role_permissions WHERE permission_id IN "
            "(SELECT id FROM user_permissions WHERE slug = :slug)"
        ),
        {"slug": PERM_SLUG},
    )
    bind.execute(sa.text("DELETE FROM user_permissions WHERE slug = :slug"), {"slug": PERM_SLUG})
