"""Commercial core consolidated tables (leads, projects, tenders, quotations, sales orders).

Revision ID: 151_commercial_core_consolidated
Revises: 150_base_workflow_respond_entity_conv

Folds ijm_icp_crm migrations 136, 137, 138 (×3), 143, 144, 159, 160, 178, 179, 183, 189
into a single CREATE pass driven directly off the SQLAlchemy model metadata.
Schema is sourced from `app.modules.commercial_core.models` so any future model
changes are reflected here as long as we re-run alembic against a clean DB.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "151_commercial_core_consolidated"
down_revision = "150_base_workflow_respond_entity_conv"
branch_labels = None
depends_on = None


# Tables owned by commercial_core (verified via `vars(<module>).items()` over
# models, models_process_config, models_quotation_email_template).
COMMERCIAL_CORE_TABLES = (
    "commercial_lead_notes",
    "commercial_lead_respond_contacts",
    "commercial_leads",
    "commercial_master_quotation_activities",
    "commercial_master_quotations",
    "commercial_process_settings",
    "commercial_project_customers",
    "commercial_project_leads",
    "commercial_projects",
    "commercial_quotation_revisions",
    "commercial_reminder_defaults",
    "commercial_sales_orders",
    "commercial_tasks",
    "commercial_tender_checkpoint_templates",
    "commercial_tender_milestones",
    "commercial_tenders",
    "quotation_email_templates",
)


def upgrade() -> None:
    # Import the module so its tables are registered on Base.metadata.
    import app.modules.commercial_core  # noqa: F401  - register models
    from app.database import Base

    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. Extend the base `customers` table with profile columns commercial code expects.
    # Idempotent: prior partial installs may already have some of these.
    existing_cols = {c["name"] for c in insp.get_columns("customers")}
    for col_name, col_def in [
        ("registered_name", sa.Column("registered_name", sa.String(255), nullable=True)),
        ("trading_name", sa.Column("trading_name", sa.String(255), nullable=True)),
        ("registration_number", sa.Column("registration_number", sa.String(100), nullable=True)),
        ("industry", sa.Column("industry", sa.String(120), nullable=True)),
        ("website", sa.Column("website", sa.String(500), nullable=True)),
        ("billing_address", sa.Column("billing_address", postgresql.JSONB, nullable=True)),
        ("country", sa.Column("country", sa.String(100), nullable=True)),
        ("tax_id", sa.Column("tax_id", sa.String(100), nullable=True)),
        ("notes", sa.Column("notes", sa.Text(), nullable=True)),
        (
            "account_owner_user_id",
            sa.Column(
                "account_owner_user_id",
                sa.String(100),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
        ),
        (
            "customer_type",
            sa.Column("customer_type", sa.String(20), nullable=False, server_default="company"),
        ),
        ("salutation", sa.Column("salutation", sa.String(32), nullable=True)),
        ("first_name", sa.Column("first_name", sa.String(120), nullable=True)),
        ("last_name", sa.Column("last_name", sa.String(120), nullable=True)),
        ("mobile_number", sa.Column("mobile_number", sa.String(50), nullable=True)),
    ]:
        if col_name not in existing_cols:
            op.add_column("customers", col_def)
    existing_indexes = {i["name"] for i in insp.get_indexes("customers")}
    if "ix_customers_account_owner_user_id" not in existing_indexes:
        op.create_index("ix_customers_account_owner_user_id", "customers", ["account_owner_user_id"])

    # 2. Create customer_contacts (general; not commercial-specific table but
    #    the relationship is what commercial code needs).
    if "customer_contacts" not in sa.inspect(bind).get_table_names():
        Base.metadata.tables["customer_contacts"].create(bind=bind, checkfirst=True)

    # 3. Create all commercial_core tables in one pass.
    tables = [Base.metadata.tables[name] for name in COMMERCIAL_CORE_TABLES]
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    import app.modules.commercial_core  # noqa: F401
    from app.database import Base

    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in COMMERCIAL_CORE_TABLES]
    Base.metadata.drop_all(bind=bind, tables=tables, checkfirst=True)
    Base.metadata.tables["customer_contacts"].drop(bind=bind, checkfirst=True)
    op.drop_index("ix_customers_account_owner_user_id", table_name="customers")
    for col in [
        "mobile_number",
        "last_name",
        "first_name",
        "salutation",
        "customer_type",
        "account_owner_user_id",
        "notes",
        "tax_id",
        "country",
        "billing_address",
        "website",
        "industry",
        "registration_number",
        "trading_name",
        "registered_name",
    ]:
        op.drop_column("customers", col)
