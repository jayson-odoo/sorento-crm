"""Finance module, S0: schema `finance`, billing documents and their lines, RBAC, catalog row.

Plan: documentation/plans/finance/PLAN-finance-billing-documents-27sep.md, 3.1, 3.2 and 3.5
(#1309).

1. `CREATE SCHEMA IF NOT EXISTS finance` (the owner's ask; the ADR-0011 precedent `sales`
   followed): the schema is the module key, so the tables carry no `finance_` prefix inside it.
2. `finance.billing_documents`: one typed table for AutoCount's invoice, cash sale, credit note
   and debit note (a CHECK on `document_type`, ADR 0013), `status` posted or cancelled, money as
   AutoCount sends it, unique `(company_id, document_type, source_ref)`. No date floor on
   `doc_date` (ruling Q2: the shared service owns the start date).
3. `finance.billing_document_lines`, cascading with their header, unique
   `(document_id, source_ref)`.
4. `finance.billing_documents.{view,export,edit,delete}`, created when absent and granted to
   admin and superadmin (ruling Q9, the `sales_0001_teams` precedent; everyone else through the
   role editor). `edit` and `delete` gate only the ingest and deletions doors.
5. Q16 (a), a separate statement: `view`, `edit` and `delete` also go to every role holding
   `scm.sales_orders.edit` (the AutoCount feed's role), so the feed can push on deploy.
6. The `finance` row in `app_modules_catalog`, with no `tenant_modules` row: installable but
   dormant, exactly as `sales` shipped. It is switched on in System > App Store.

Downgrade drops the two tables and the catalog row. It leaves the schema (a namespace, never
dropped, ADR-0011) and the permission rows (`sync_permissions` recreates them from the
registry on boot anyway, and a grant an admin made by hand must not vanish with a rollback).

Revision ID: fin_0001_billing_documents
Revises: identity_0001_s0_model
Create Date: 2026-09-27
"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "fin_0001_billing_documents"
down_revision = "identity_0001_s0_model"
branch_labels = None
depends_on = None

_PERMS = (
    (
        "finance.billing_documents.view",
        "View Billing Documents",
        "Permission to view billing documents (invoices, cash sales, credit and debit notes).",
    ),
    (
        "finance.billing_documents.export",
        "Export Billing Documents",
        "Permission to export the billing documents list.",
    ),
    (
        "finance.billing_documents.edit",
        "Ingest Billing Documents",
        "Permission to push billing documents through the AutoCount ingest.",
    ),
    (
        "finance.billing_documents.delete",
        "Delete Billing Documents",
        "Permission to delete billing documents through the AutoCount ingest.",
    ),
)
# Q16 (a): the three slugs the ingest doors check, never `export`.
_FEED_SLUGS = (
    "finance.billing_documents.view",
    "finance.billing_documents.edit",
    "finance.billing_documents.delete",
)

_UUID = postgresql.UUID(as_uuid=False)


def seed_permissions(bind) -> None:
    """Create the slugs when absent and grant them. Idempotent: running it again adds no row."""
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
    # Q16 (open, built to recommendation (a)): the AutoCount feed's role is whichever role
    # holds `scm.sales_orders.edit` (the `472_ingest_v2_permissions` sweep shape). Answer (b)
    # deletes this one statement and its assertion in the migration test.
    bind.execute(
        sa.text(
            """
            INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
            SELECT gen_random_uuid()::text, held.role_id, p.id, now()
            FROM user_role_permissions held
            JOIN user_permissions so_edit
              ON so_edit.id = held.permission_id AND so_edit.slug = 'scm.sales_orders.edit'
            CROSS JOIN user_permissions p
            WHERE p.slug = ANY(:slugs)
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        ),
        {"slugs": list(_FEED_SLUGS)},
    )


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS finance")

    op.create_table(
        "billing_documents",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("company_id", _UUID, sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("document_type", sa.String(length=20), nullable=False),
        sa.Column("doc_no", sa.String(length=50), nullable=False),
        sa.Column("doc_date", sa.Date(), nullable=False),
        sa.Column(
            "customer_id", _UUID, sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("debtor_code", sa.String(length=64), nullable=True),
        sa.Column("customer_name", sa.String(length=255), nullable=True),
        sa.Column(
            "sales_agent_id",
            _UUID,
            sa.ForeignKey("sales_agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("agent_code", sa.String(length=100), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=False, server_default="MYR"),
        sa.Column(
            "currency_rate", sa.Numeric(18, 8), nullable=False, server_default=sa.text("1")
        ),
        sa.Column("net_total", sa.Numeric(15, 2), nullable=True),
        sa.Column("tax_total", sa.Numeric(15, 2), nullable=True),
        sa.Column("total", sa.Numeric(15, 2), nullable=True),
        sa.Column("local_net_total", sa.Numeric(15, 2), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="posted"),
        sa.Column(
            "against_document_id",
            _UUID,
            sa.ForeignKey("finance.billing_documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("against_doc_no", sa.String(length=50), nullable=True),
        sa.Column("ref", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_system", sa.String(length=50), nullable=False, server_default="autocount"),
        sa.Column("source_ref", sa.String(length=255), nullable=False),
        sa.Column("source_modified_at", sa.DateTime(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "document_type IN ('invoice', 'cash_sale', 'credit_note', 'debit_note')",
            name="ck_finance_billing_documents_type",
        ),
        sa.CheckConstraint(
            "status IN ('posted', 'cancelled')", name="ck_finance_billing_documents_status"
        ),
        schema="finance",
    )
    for name, columns, unique in (
        ("ix_finance_billing_documents_company_id", ["company_id"], False),
        (
            "uq_finance_billing_documents_company_type_ref",
            ["company_id", "document_type", "source_ref"],
            True,
        ),
        (
            "ix_finance_billing_documents_company_type_doc_no",
            ["company_id", "document_type", "doc_no"],
            False,
        ),
        ("ix_finance_billing_documents_company_date", ["company_id", "doc_date"], False),
        (
            "ix_finance_billing_documents_company_agent_date",
            ["company_id", "sales_agent_id", "doc_date"],
            False,
        ),
        ("ix_finance_billing_documents_company_customer", ["company_id", "customer_id"], False),
        ("ix_finance_billing_documents_against", ["against_document_id"], False),
    ):
        op.create_index(name, "billing_documents", columns, unique=unique, schema="finance")

    op.create_table(
        "billing_document_lines",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("company_id", _UUID, sa.ForeignKey("companies.id"), nullable=False),
        sa.Column(
            "document_id",
            _UUID,
            sa.ForeignKey("finance.billing_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_no", sa.Integer(), nullable=True),
        sa.Column(
            "product_id", _UUID, sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("item_code", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("uom", sa.String(length=20), nullable=True),
        sa.Column("quantity", sa.Numeric(15, 4), nullable=True),
        sa.Column("unit_price", sa.Numeric(15, 4), nullable=True),
        sa.Column("discount_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("net_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("tax_code", sa.String(length=20), nullable=True),
        sa.Column("tax_rate", sa.Numeric(7, 4), nullable=True),
        sa.Column("tax_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("line_total", sa.Numeric(15, 2), nullable=True),
        sa.Column(
            "sales_order_line_id",
            _UUID,
            sa.ForeignKey("sales_order_lines.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("from_doc_type", sa.String(length=10), nullable=True),
        sa.Column("from_doc_no", sa.String(length=50), nullable=True),
        sa.Column("from_line_ref", sa.String(length=255), nullable=True),
        sa.Column("source_ref", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        schema="finance",
    )
    for name, columns, unique in (
        ("ix_finance_billing_document_lines_company_id", ["company_id"], False),
        (
            "uq_finance_billing_document_lines_document_ref",
            ["document_id", "source_ref"],
            True,
        ),
        (
            "ix_finance_billing_document_lines_sales_order_line",
            ["sales_order_line_id"],
            False,
        ),
        ("ix_finance_billing_document_lines_product", ["product_id"], False),
    ):
        op.create_index(name, "billing_document_lines", columns, unique=unique, schema="finance")

    bind = op.get_bind()
    seed_permissions(bind)

    bind.execute(
        sa.text(
            """
            INSERT INTO app_modules_catalog
                (id, module_key, display_name, description, sort_order, is_core, dependencies)
            VALUES (:id, 'finance', 'Finance', :desc, :sort, false, CAST(:deps AS jsonb))
            ON CONFLICT (module_key) DO NOTHING
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "desc": (
                "Billing documents from AutoCount: invoices, cash sales, credit notes and "
                "debit notes."
            ),
            "sort": "970",
            "deps": '["base", "order"]',
        },
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM tenant_modules WHERE module_key = 'finance'"))
    bind.execute(sa.text("DELETE FROM app_modules_catalog WHERE module_key = 'finance'"))
    op.drop_table("billing_document_lines", schema="finance")
    op.drop_table("billing_documents", schema="finance")
