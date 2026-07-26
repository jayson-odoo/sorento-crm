"""AutoCount ingest Slice 2: sales_agents + payment_methods + tax_entities.

Read-only mirror masters. Explicit, idempotent op.create_table (legacy
create_all DBs never run migration bodies). Chains on Slice 1 (302).

Revision ID: 303_autocount_slice2_masters
Revises: 302_autocount_credit_terms_tax_codes
"""
from alembic import op
import sqlalchemy as sa


revision = "303_autocount_slice2_masters"
down_revision = "302_autocount_credit_terms_tax_codes"
branch_labels = None
depends_on = None

_UUID = sa.dialects.postgresql.UUID
_TS = dict(server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())

    if "sales_agents" not in tables:
        op.create_table(
            "sales_agents",
            sa.Column("id", _UUID(as_uuid=False), primary_key=True),
            sa.Column("sales_agent", sa.String(100), nullable=False),
            sa.Column("description", sa.String(255), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("internal_note", sa.Text(), nullable=True),
            sa.Column("follow_up", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=False), **_TS),
            sa.Column("updated_at", sa.DateTime(timezone=False), **_TS),
        )
        op.create_unique_constraint("uq_sales_agents_sales_agent", "sales_agents", ["sales_agent"])

    if "payment_methods" not in tables:
        op.create_table(
            "payment_methods",
            sa.Column("id", _UUID(as_uuid=False), primary_key=True),
            sa.Column("payment_method", sa.String(100), nullable=False),
            sa.Column("description", sa.String(255), nullable=True),
            sa.Column("bank_account", sa.String(100), nullable=True),
            sa.Column("journal_type", sa.String(100), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("internal_note", sa.Text(), nullable=True),
            sa.Column("follow_up", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=False), **_TS),
            sa.Column("updated_at", sa.DateTime(timezone=False), **_TS),
        )
        op.create_unique_constraint("uq_payment_methods_payment_method", "payment_methods", ["payment_method"])

    if "tax_entities" not in tables:
        op.create_table(
            "tax_entities",
            sa.Column("id", _UUID(as_uuid=False), primary_key=True),
            sa.Column("tax_entity_id", sa.String(100), nullable=False),
            sa.Column("name", sa.String(255), nullable=True),
            sa.Column("tin", sa.String(100), nullable=True),
            sa.Column("identity_no", sa.String(100), nullable=True),
            sa.Column("tax_branch_id", sa.String(100), nullable=True),
            sa.Column("tax_classification", sa.Integer(), nullable=True),
            sa.Column("gst_register_no", sa.String(100), nullable=True),
            sa.Column("sst_register_no", sa.String(100), nullable=True),
            sa.Column("tourism_tax_register_no", sa.String(100), nullable=True),
            sa.Column("trade_name", sa.String(255), nullable=True),
            sa.Column("business_activity_desc", sa.String(255), nullable=True),
            sa.Column("msic_code", sa.String(40), nullable=True),
            sa.Column("address", sa.String(255), nullable=True),
            sa.Column("post_code", sa.String(40), nullable=True),
            sa.Column("city", sa.String(100), nullable=True),
            sa.Column("state_code", sa.String(40), nullable=True),
            sa.Column("country_code", sa.String(40), nullable=True),
            sa.Column("phone", sa.String(100), nullable=True),
            sa.Column("email_address", sa.String(255), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("internal_note", sa.Text(), nullable=True),
            sa.Column("follow_up", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=False), **_TS),
            sa.Column("updated_at", sa.DateTime(timezone=False), **_TS),
        )
        op.create_unique_constraint("uq_tax_entities_tax_entity_id", "tax_entities", ["tax_entity_id"])


def downgrade() -> None:
    op.drop_table("tax_entities")
    op.drop_table("payment_methods")
    op.drop_table("sales_agents")
