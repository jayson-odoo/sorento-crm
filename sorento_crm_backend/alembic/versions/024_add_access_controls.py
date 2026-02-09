"""Add access control fields for respond contacts, promotions, and product attachments.

Revision ID: 024_add_access_controls
Revises: 023_create_purchase_requests
Create Date: 2026-02-03 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "024_add_access_controls"
down_revision = "023_create_purchase_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    # respond_contacts.user_type
    if "respond_contacts" in inspector.get_table_names():
        columns = [col["name"] for col in inspector.get_columns("respond_contacts")]
        if "user_type" not in columns:
            op.add_column("respond_contacts", sa.Column("user_type", sa.Text(), nullable=True))
        indexes = inspector.get_indexes("respond_contacts")
        if not any(idx["name"] == "ix_respond_contacts_user_type" for idx in indexes):
            op.create_index("ix_respond_contacts_user_type", "respond_contacts", ["user_type"])

    # promotions.access_levels (JSONB array)
    if "promotions" in inspector.get_table_names():
        columns = [col["name"] for col in inspector.get_columns("promotions")]
        if "access_levels" not in columns:
            op.add_column(
                "promotions",
                sa.Column(
                    "access_levels",
                    postgresql.JSONB(),
                    nullable=False,
                    server_default=sa.text("'[\"dealer\",\"end_user\"]'::jsonb"),
                ),
            )
        # Backfill existing rows to default access
        op.execute(
            sa.text(
                "UPDATE promotions SET access_levels = '[\"dealer\",\"end_user\"]'::jsonb "
                "WHERE access_levels IS NULL"
            )
        )
        indexes = inspector.get_indexes("promotions")
        if not any(idx["name"] == "ix_promotions_access_levels" for idx in indexes):
            op.create_index(
                "ix_promotions_access_levels",
                "promotions",
                ["access_levels"],
                postgresql_using="gin",
            )

    # product_attachments.access_levels (JSONB array)
    if "product_attachments" in inspector.get_table_names():
        columns = [col["name"] for col in inspector.get_columns("product_attachments")]
        if "access_levels" not in columns:
            op.add_column(
                "product_attachments",
                sa.Column(
                    "access_levels",
                    postgresql.JSONB(),
                    nullable=False,
                    server_default=sa.text("'[\"dealer\",\"end_user\"]'::jsonb"),
                ),
            )
        # Backfill existing rows to default access
        op.execute(
            sa.text(
                "UPDATE product_attachments SET access_levels = '[\"dealer\",\"end_user\"]'::jsonb "
                "WHERE access_levels IS NULL"
            )
        )
        indexes = inspector.get_indexes("product_attachments")
        if not any(idx["name"] == "ix_product_attachments_access_levels" for idx in indexes):
            op.create_index(
                "ix_product_attachments_access_levels",
                "product_attachments",
                ["access_levels"],
                postgresql_using="gin",
            )


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    if "product_attachments" in inspector.get_table_names():
        columns = [col["name"] for col in inspector.get_columns("product_attachments")]
        indexes = inspector.get_indexes("product_attachments")
        if any(idx["name"] == "ix_product_attachments_access_levels" for idx in indexes):
            op.drop_index("ix_product_attachments_access_levels", table_name="product_attachments")
        if "access_levels" in columns:
            op.drop_column("product_attachments", "access_levels")

    if "promotions" in inspector.get_table_names():
        columns = [col["name"] for col in inspector.get_columns("promotions")]
        indexes = inspector.get_indexes("promotions")
        if any(idx["name"] == "ix_promotions_access_levels" for idx in indexes):
            op.drop_index("ix_promotions_access_levels", table_name="promotions")
        if "access_levels" in columns:
            op.drop_column("promotions", "access_levels")

    if "respond_contacts" in inspector.get_table_names():
        columns = [col["name"] for col in inspector.get_columns("respond_contacts")]
        indexes = inspector.get_indexes("respond_contacts")
        if any(idx["name"] == "ix_respond_contacts_user_type" for idx in indexes):
            op.drop_index("ix_respond_contacts_user_type", table_name="respond_contacts")
        if "user_type" in columns:
            op.drop_column("respond_contacts", "user_type")
