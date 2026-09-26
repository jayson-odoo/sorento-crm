"""Sales module, S2: `sales.opportunities`, `sales.opportunity_lines`, RBAC, numbering.

Plan: documentation/plans/sales/PLAN-sales-targets-opportunities-26sep.md, 3.4, 3.7, section 16.

1. `sales.opportunities` (header) and `sales.opportunity_lines` (products, cascade from the
   header). Columns exactly as plan 3.4: `expected_close_date`, no `product_note` or
   `product_category_id` (round 4 replaced both with product lines, N11).
2. Check constraints: a header names a customer or a prospect (never neither);
   `outcome` and `source` are closed vocabularies; a line's `qty` is positive.
3. `sales.opportunities.{view,add,edit,delete}`, created when absent and granted to admin
   and superadmin (the grant sweep, same shape as `sales_0001_teams`).
4. The `OPP-` numbering rule (`doc_type = 'sales_opportunity'`, 6 digits), inserted when
   absent - same shape `seed_lead_numbering_rule` uses for `LEAD-`.

Downgrade drops both tables. It leaves the permission rows (`sync_permissions` recreates
them from the registry on boot anyway, and a grant an admin made by hand must not vanish
with a rollback) and the numbering rule (a running number sequence is not undone by a
schema rollback - the next upgrade would otherwise mint duplicates).

Revision ID: sales_0003_opportunities
Revises: sales_0002_team_leader
Create Date: 2026-09-26
"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "sales_0003_opportunities"
down_revision = "sales_0002_team_leader"
branch_labels = None
depends_on = None

_PERMS = (
    ("sales.opportunities.view", "View Sales Opportunities", "Permission to view Sales Opportunities."),
    ("sales.opportunities.add", "Add Sales Opportunities", "Permission to add Sales Opportunities."),
    ("sales.opportunities.edit", "Edit Sales Opportunities", "Permission to edit Sales Opportunities."),
    ("sales.opportunities.delete", "Delete Sales Opportunities", "Permission to delete Sales Opportunities."),
)


def upgrade() -> None:
    op.create_table(
        "opportunities",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=False
        ),
        sa.Column("opportunity_no", sa.String(length=20), nullable=False),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("customers.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("prospect_name", sa.String(length=200), nullable=True),
        sa.Column(
            "sales_agent_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("sales_agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "status_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("statuses.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("outcome", sa.String(length=8), nullable=False, server_default="open"),
        sa.Column("expected_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("expected_close_date", sa.Date(), nullable=False),
        sa.Column("lost_reason", sa.String(length=150), nullable=True),
        sa.Column(
            "sales_order_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("sales_orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column(
            "created_by_contact_id",
            sa.Text(),
            sa.ForeignKey("respond_contacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_by_user_id", sa.String(length=64), nullable=True),
        sa.Column("stage_changed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "customer_id IS NOT NULL OR prospect_name IS NOT NULL",
            name="ck_sales_opportunities_customer_or_prospect",
        ),
        sa.CheckConstraint(
            "outcome IN ('open', 'won', 'lost')", name="ck_sales_opportunities_outcome"
        ),
        sa.CheckConstraint("source IN ('portal', 'crm')", name="ck_sales_opportunities_source"),
        schema="sales",
    )
    op.create_index(
        "ix_sales_opportunities_company_id", "opportunities", ["company_id"], schema="sales"
    )
    op.create_index(
        "uq_sales_opportunities_company_no",
        "opportunities",
        ["company_id", "opportunity_no"],
        unique=True,
        schema="sales",
    )
    op.create_index(
        "ix_sales_opportunities_customer_id", "opportunities", ["customer_id"], schema="sales"
    )
    op.create_index(
        "ix_sales_opportunities_sales_agent_id", "opportunities", ["sales_agent_id"], schema="sales"
    )
    op.create_index(
        "ix_sales_opportunities_status_id", "opportunities", ["status_id"], schema="sales"
    )
    op.create_index(
        "ix_sales_opportunities_expected_close_date",
        "opportunities",
        ["expected_close_date"],
        schema="sales",
    )

    op.create_table(
        "opportunity_lines",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=False
        ),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("sales.opportunities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("qty", sa.Numeric(12, 2), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.CheckConstraint("qty > 0", name="ck_sales_opportunity_lines_qty_positive"),
        schema="sales",
    )
    op.create_index(
        "ix_sales_opportunity_lines_company_id", "opportunity_lines", ["company_id"], schema="sales"
    )
    op.create_index(
        "ix_sales_opportunity_lines_opportunity_id",
        "opportunity_lines",
        ["opportunity_id"],
        schema="sales",
    )
    op.create_index(
        "ix_sales_opportunity_lines_product_id", "opportunity_lines", ["product_id"], schema="sales"
    )

    bind = op.get_bind()
    for slug, name, description in _PERMS:
        bind.execute(
            sa.text(
                """
                INSERT INTO user_permissions (id, slug, name, description, created_at)
                SELECT gen_random_uuid()::text, :slug, :name, :descr, now()
                WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :slug)
                """
            ),
            {"slug": slug, "name": name, "descr": description},
        )
    bind.execute(
        sa.text(
            """
            INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
            SELECT gen_random_uuid()::text, r.id, p.id, now()
            FROM user_roles r
            CROSS JOIN user_permissions p
            WHERE r.slug IN ('admin', 'superadmin') AND p.slug = ANY(:slugs)
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        ),
        {"slugs": [slug for slug, _, _ in _PERMS]},
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO document_numbering_rules
                (id, company_id, doc_type, enabled, prefix_template, number_digits,
                 next_value, start_value, reset_policy)
            SELECT :id, NULL, 'sales_opportunity', true, 'OPP-', 6, 1, 1, 'none'
            WHERE NOT EXISTS (
                SELECT 1 FROM document_numbering_rules WHERE doc_type = 'sales_opportunity'
            )
            """
        ),
        {"id": str(uuid.uuid4())},
    )


def downgrade() -> None:
    op.drop_table("opportunity_lines", schema="sales")
    op.drop_table("opportunities", schema="sales")
