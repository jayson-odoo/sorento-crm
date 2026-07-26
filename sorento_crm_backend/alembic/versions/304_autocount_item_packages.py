"""AutoCount ingest Slice 3: item_packages + item_package_lines.

Parent+lines mirror. Explicit idempotent create_table (legacy create_all DBs
skip migration bodies). Chains on Slice 2 (303).

Revision ID: 304_autocount_item_packages
Revises: 303_autocount_slice2_masters
"""
from alembic import op
import sqlalchemy as sa


revision = "304_autocount_item_packages"
down_revision = "303_autocount_slice2_masters"
branch_labels = None
depends_on = None

_UUID = sa.dialects.postgresql.UUID
_TS = dict(server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())

    if "item_packages" not in tables:
        op.create_table(
            "item_packages",
            sa.Column("id", _UUID(as_uuid=False), primary_key=True),
            sa.Column("package_code", sa.String(100), nullable=False),
            sa.Column("description", sa.String(255), nullable=True),
            sa.Column("expiry_date", sa.Date(), nullable=True),
            sa.Column("limited_qty", sa.Numeric(15, 4), nullable=True),
            sa.Column("opening_qty", sa.Numeric(15, 4), nullable=True),
            sa.Column("user_uom", sa.String(100), nullable=True),
            sa.Column("bar_code", sa.String(100), nullable=True),
            sa.Column("further_description", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("internal_note", sa.Text(), nullable=True),
            sa.Column("follow_up", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=False), **_TS),
            sa.Column("updated_at", sa.DateTime(timezone=False), **_TS),
        )
        op.create_unique_constraint("uq_item_packages_package_code", "item_packages", ["package_code"])

    if "item_package_lines" not in tables:
        op.create_table(
            "item_package_lines",
            sa.Column("id", _UUID(as_uuid=False), primary_key=True),
            sa.Column("item_package_id", _UUID(as_uuid=False),
                      sa.ForeignKey("item_packages.id", ondelete="CASCADE"), nullable=False),
            sa.Column("product_id", _UUID(as_uuid=False),
                      sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("line_sequence", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("uom", sa.String(100), nullable=True),
            sa.Column("qty", sa.Numeric(15, 4), nullable=True),
            sa.Column("unit_price", sa.Numeric(15, 2), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=False), **_TS),
            sa.Column("updated_at", sa.DateTime(timezone=False), **_TS),
        )
        op.create_index("ix_item_package_lines_package", "item_package_lines", ["item_package_id"])


def downgrade() -> None:
    op.drop_table("item_package_lines")
    op.drop_table("item_packages")
