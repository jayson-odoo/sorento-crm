"""SALES-UNIFIED (#1916): AutoCount debtor type on customers, whose agent a sale is per company,
set-apart customers, and the slug that edits them.

Plan: documentation/plans/sales/PLAN-sales-unified-27oct.md (2.2 to 2.4).

Additive only:
1. ``customers.autocount_debtor_type`` (raw ``Debtor.DebtorType``; the CRM's own
   ``customers.debtor_type`` is a different concept and is not touched).
2. ``companies.sales_agent_source`` (``document`` | ``customer``), default ``document``.
3. ``sales.set_apart_customers`` (customer, from month, to month).
4. ``sales.set_apart.edit``, granted to admin and superadmin (PRINCIPLES DoD 3). Reading the
   list is ``sales.reports.view``, which already exists.

Revision ID: sales_unified_0001
Revises: akc_0001_removed_unreferenced
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "sales_unified_0001"
down_revision = "akc_0001_removed_unreferenced"
branch_labels = None
depends_on = None

_UUID = UUID(as_uuid=False)

SLUG = "sales.set_apart.edit"
SLUG_NAME = "Edit set-apart customers"
SLUG_DESC = "Add, change and remove the customers the sales reports set apart, by month."
GRANT_ROLES = ("superadmin", "admin")


def seed_slug(bind) -> None:
    """Shared with ``scripts.bootstrap_env`` (a create_all database never runs this body)."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    bind.execute(
        sa.text(
            "INSERT INTO user_permissions (id, slug, name, description, created_at) "
            "VALUES (:id, :slug, :name, :desc, :now) ON CONFLICT (slug) DO NOTHING"
        ),
        {"id": str(uuid.uuid4()), "slug": SLUG, "name": SLUG_NAME, "desc": SLUG_DESC, "now": now},
    )
    bind.execute(
        sa.text(
            "INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at) "
            "SELECT gen_random_uuid()::text, r.id, p.id, :now "
            "  FROM user_roles r CROSS JOIN user_permissions p "
            " WHERE r.slug = ANY(:roles) AND p.slug = :slug "
            "ON CONFLICT (role_id, permission_id) DO NOTHING"
        ),
        {"roles": list(GRANT_ROLES), "slug": SLUG, "now": now},
    )


def upgrade() -> None:
    op.execute(
        "ALTER TABLE customers ADD COLUMN IF NOT EXISTS autocount_debtor_type VARCHAR(50)"
    )
    op.execute(
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS sales_agent_source VARCHAR(10) "
        "NOT NULL DEFAULT 'document'"
    )
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_companies_sales_agent_source') THEN "
        "ALTER TABLE companies ADD CONSTRAINT ck_companies_sales_agent_source "
        "CHECK (sales_agent_source IN ('document', 'customer')); "
        "END IF; END $$"
    )
    op.execute("CREATE SCHEMA IF NOT EXISTS sales")
    op.create_table(
        "set_apart_customers",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("company_id", _UUID, sa.ForeignKey("companies.id"), nullable=True),
        sa.Column(
            "customer_id", _UUID, sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("from_month", sa.Date(), nullable=False),
        sa.Column("to_month", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "to_month IS NULL OR to_month >= from_month",
            name="ck_sales_set_apart_customers_months",
        ),
        schema="sales",
        if_not_exists=True,
    )
    op.create_index(
        "ix_sales_set_apart_customers_company_id", "set_apart_customers", ["company_id"],
        schema="sales", if_not_exists=True,
    )
    op.create_index(
        "ix_sales_set_apart_customers_customer_id", "set_apart_customers", ["customer_id"],
        schema="sales", if_not_exists=True,
    )
    op.create_index(
        "ix_sales_set_apart_customers_company_customer", "set_apart_customers",
        ["company_id", "customer_id"], schema="sales", if_not_exists=True,
    )
    seed_slug(op.get_bind())


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM user_role_permissions WHERE permission_id IN "
            "(SELECT id FROM user_permissions WHERE slug = :slug)"
        ),
        {"slug": SLUG},
    )
    bind.execute(sa.text("DELETE FROM user_permissions WHERE slug = :slug"), {"slug": SLUG})
    op.drop_table("set_apart_customers", schema="sales", if_exists=True)
    op.execute("ALTER TABLE companies DROP CONSTRAINT IF EXISTS ck_companies_sales_agent_source")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS sales_agent_source")
    op.execute("ALTER TABLE customers DROP COLUMN IF EXISTS autocount_debtor_type")
