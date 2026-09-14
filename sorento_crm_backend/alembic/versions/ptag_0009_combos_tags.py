"""Price tag combos: packages on the product, parts under a line, tags under a line

PLAN-price-tag-combos.md D1/D2/D3. Built INCREMENTALLY across the lane's slices, in
one revision file, because they are one schema change: S1 lands step 1's DDL, S2 and
S3 add the rest to this same file before the lane opens its PR.

Step 1 (S1, here): the new tables and columns.

  * `product_combos` / `product_combo_parts` - the catalogue package on the host
    product (D1).
  * `price_tag_request_line_parts` - what the salesperson asked to come with a line,
    plus `lines.combo_id` and `lines.package_warning` (D2). The line columns land
    with the table they belong to rather than a slice later: the model declares them
    the moment `PriceTagRequestLinePart` exists, and a model column with no database
    column behind it breaks every read of the table.
  * `system_settings.price_tag_guarded_classes` - the classes the S2 guard warns
    about, seeded with the two the owner named. NOT NULL with a default rather than
    NULL, or the guard would warn about nothing on every existing tenant, which reads
    as the feature not working.

Steps 2 to 4 (S3) still to come in this file: one tag per existing line, the tag
sheet document re-key, the r9 pin remap, and dropping the retired line columns.

Revision ID: ptag_0009_combos_tags
Revises: 510_spec_visibility_policies
Create Date: 2026-09-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "ptag_0009_combos_tags"
down_revision = "510_spec_visibility_policies"
branch_labels = None
depends_on = None

GUARDED_CLASSES_DEFAULT = '["Bathroom Furniture", "Kitchen Sink"]'


def upgrade() -> None:
    # ---------------------------------------------------------------- D1 combos
    op.create_table(
        "product_combos",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "host_product_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("host_product_id", "name", name="uq_product_combos_host_name"),
    )
    op.create_index("ix_product_combos_host_product_id", "product_combos", ["host_product_id"])

    op.create_table(
        "product_combo_parts",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "combo_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("product_combos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "part_product_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("choice_group", sa.String(length=100), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("combo_id", "part_product_id", name="uq_product_combo_parts_product"),
    )
    op.create_index("ix_product_combo_parts_combo_id", "product_combo_parts", ["combo_id"])
    op.create_index(
        "ix_product_combo_parts_part_product_id", "product_combo_parts", ["part_product_id"]
    )

    # ------------------------------------------------------- D2 parts on a line
    op.add_column(
        "price_tag_request_lines",
        sa.Column(
            "combo_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("product_combos.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "price_tag_request_lines", sa.Column("package_warning", sa.Text(), nullable=True)
    )

    op.create_table(
        "price_tag_request_line_parts",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "line_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("price_tag_request_lines.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("role", sa.String(length=100), nullable=True),
        sa.Column(
            "candidates",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "(product_id IS NOT NULL AND candidates = '[]'::jsonb) "
            "OR (product_id IS NULL AND jsonb_array_length(candidates) > 0)",
            name="ck_ptag_line_parts_resolved_or_open",
        ),
    )
    op.create_index(
        "ix_price_tag_request_line_parts_line_id", "price_tag_request_line_parts", ["line_id"]
    )

    # ------------------------------------------------- D2 the guarded class list
    op.add_column(
        "system_settings",
        sa.Column(
            "price_tag_guarded_classes",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text(f"'{GUARDED_CLASSES_DEFAULT}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("system_settings", "price_tag_guarded_classes")
    op.drop_index(
        "ix_price_tag_request_line_parts_line_id", table_name="price_tag_request_line_parts"
    )
    op.drop_table("price_tag_request_line_parts")
    op.drop_column("price_tag_request_lines", "package_warning")
    op.drop_column("price_tag_request_lines", "combo_id")
    op.drop_index("ix_product_combo_parts_part_product_id", table_name="product_combo_parts")
    op.drop_index("ix_product_combo_parts_combo_id", table_name="product_combo_parts")
    op.drop_table("product_combo_parts")
    op.drop_index("ix_product_combos_host_product_id", table_name="product_combos")
    op.drop_table("product_combos")
