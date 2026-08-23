"""product sets: a flyer code that resolves to the SKUs it is made of

Explicit ``op.create_table`` rather than an autogenerate stub. New tables are
absent on a database built by ``create_all``, and a migration that only carries
an index or a constraint leaves the model with no table behind it, so every read
500s on ``UndefinedTable`` long after the branch looked green.

Revision ID: 411_product_sets
Revises: 410_trgm_norm_idx
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "411_product_sets"
down_revision = "410_trgm_norm_idx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_sets",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("set_code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("list_price_override", sa.Numeric(15, 2), nullable=True),
        sa.Column("override_set_by", UUID(as_uuid=False), nullable=True),
        sa.Column("override_set_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "company_id",
            UUID(as_uuid=False),
            sa.ForeignKey("companies.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", UUID(as_uuid=False), nullable=True),
        # Per company. Sorento and Mocha both carry the same product codes, so a
        # global unique index would make the two companies fight over one row.
        sa.UniqueConstraint("company_id", "set_code", name="uq_product_sets_company_code"),
    )
    op.create_index("ix_product_sets_set_code", "product_sets", ["set_code"])
    op.create_index("ix_product_sets_company_id", "product_sets", ["company_id"])

    op.create_table(
        "product_set_members",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "product_set_id",
            UUID(as_uuid=False),
            sa.ForeignKey("product_sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # RESTRICT: a set must never hold a dangling member. Deleting a product
        # that a set names is refused rather than silently making the
        # complete-sets figure wrong.
        sa.Column(
            "product_id",
            UUID(as_uuid=False),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        # NUMERIC, never Integer: an Integer quantity truncates fractional and
        # negative values with no error.
        sa.Column("quantity", sa.Numeric(15, 4), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "contributes_to_price",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("product_set_id", "product_id", name="uq_product_set_member"),
    )
    op.create_index("ix_product_set_members_set_id", "product_set_members", ["product_set_id"])
    op.create_index("ix_product_set_members_product_id", "product_set_members", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_product_set_members_product_id", table_name="product_set_members")
    op.drop_index("ix_product_set_members_set_id", table_name="product_set_members")
    op.drop_table("product_set_members")
    op.drop_index("ix_product_sets_company_id", table_name="product_sets")
    op.drop_index("ix_product_sets_set_code", table_name="product_sets")
    op.drop_table("product_sets")
