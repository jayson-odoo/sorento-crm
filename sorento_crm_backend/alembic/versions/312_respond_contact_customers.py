"""Link a WhatsApp contact to the customer account they belong to.

The dependency the dealer kit could not clear: a consumer arriving from a
catalogue link is a ``respond_contacts`` row, and turning their design into a
quote needs the account behind it. Nothing joined the two.

Deliberately a table, not ``respond_contacts.customer_id``. ``customers`` is
company-scoped and ``respond_contacts`` is not, so a single column cannot
express "customer X at Sorento, customer Y at Mocha", and a company-scoped value
sitting on an unscoped row is one join from crossing the partition. Each link
carries its own ``company_id``.

The partial unique index is the interesting constraint: a person may be the
contact for two accounts, but only one of them can be the primary, and only
within one company - so the same person can be primary for a Sorento account
AND a Mocha one without the index treating that as a conflict.

Revision ID: 312_respond_contact_customers
Revises: 311_dealer_kit_export_request
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "312_respond_contact_customers"
down_revision = "311_dealer_kit_export_request"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "respond_contact_customers",
        sa.Column("id", UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column(
            "contact_id",
            sa.Text(),
            sa.ForeignKey("respond_contacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            UUID(as_uuid=False),
            sa.ForeignKey("customers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("company_id", UUID(as_uuid=False), nullable=True),
        sa.Column(
            "is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("source", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("linked_by", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "contact_id", "customer_id", name="uq_respond_contact_customers_pair"
        ),
    )

    op.create_index(
        "ix_respond_contact_customers_contact_id",
        "respond_contact_customers",
        ["contact_id"],
    )
    op.create_index(
        "ix_respond_contact_customers_customer_id",
        "respond_contact_customers",
        ["customer_id"],
    )
    op.create_index(
        "uq_respond_contact_customers_one_primary",
        "respond_contact_customers",
        ["contact_id", "company_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_respond_contact_customers_one_primary",
        table_name="respond_contact_customers",
    )
    op.drop_index(
        "ix_respond_contact_customers_customer_id",
        table_name="respond_contact_customers",
    )
    op.drop_index(
        "ix_respond_contact_customers_contact_id",
        table_name="respond_contact_customers",
    )
    op.drop_table("respond_contact_customers")
