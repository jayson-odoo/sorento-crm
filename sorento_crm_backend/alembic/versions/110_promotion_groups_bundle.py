"""Promotion groups (FOC bundles) and dealer pricing on promotion_products.

Revision ID: 110_promotion_groups_bundle
Revises: 109_promotions_list_query
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "110_promotion_groups_bundle"
down_revision = "109_promotions_list_query"
branch_labels = None
depends_on = None

_PAIR_COLS = {"promotion_id", "product_id"}


def _drop_old_promotion_product_pair_uniqueness() -> None:
    """
    Old DBs may have (promotion_id, product_id) uniqueness as either:
    - a UNIQUE CONSTRAINT (drop with ALTER TABLE ... DROP CONSTRAINT), or
    - a UNIQUE INDEX only (drop with DROP INDEX), or
    - a different name than uq_promotion_products_promotion_id_product_id.

    Inspect the live schema and drop whichever exists.
    """
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "promotion_products" not in insp.get_table_names():
        return

    for uc in insp.get_unique_constraints("promotion_products"):
        if set(uc.get("column_names") or []) == _PAIR_COLS:
            op.drop_constraint(uc["name"], "promotion_products", type_="unique")
            return

    for idx in insp.get_indexes("promotion_products"):
        if idx.get("unique") and set(idx.get("column_names") or []) == _PAIR_COLS:
            op.drop_index(idx["name"], table_name="promotion_products")
            return

    # Fallback: known Alembic / hand-rolled names (PostgreSQL)
    op.execute(
        sa.text(
            "ALTER TABLE promotion_products DROP CONSTRAINT IF EXISTS uq_promotion_products_promotion_id_product_id"
        )
    )
    op.execute(sa.text("DROP INDEX IF EXISTS uq_promotion_products_promotion_id_product_id"))


def upgrade() -> None:
    op.create_table(
        "promotion_groups",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "promotion_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("promotions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("group_name", sa.String(255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("purchase_quantity_for_foc", sa.Integer(), nullable=True),
        sa.Column("foc_quantity", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_promotion_groups_promotion_id", "promotion_groups", ["promotion_id"])

    op.add_column(
        "promotion_products",
        sa.Column("promotion_group_id", postgresql.UUID(as_uuid=False), nullable=True),
    )
    op.add_column(
        "promotion_products",
        sa.Column("dealer_discount_percent", sa.Numeric(8, 6), nullable=True),
    )
    op.add_column("promotion_products", sa.Column("dealer_cost", sa.Numeric(12, 2), nullable=True))
    op.add_column(
        "promotion_products",
        sa.Column("list_to_dealer_margin_amount", sa.Numeric(12, 2), nullable=True),
    )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            INSERT INTO promotion_groups (id, promotion_id, group_name, sort_order, purchase_quantity_for_foc, foc_quantity, created_at, updated_at)
            SELECT gen_random_uuid(), p.id, 'Default', 0, NULL, NULL, NOW(), NOW()
            FROM promotions p
            WHERE EXISTS (SELECT 1 FROM promotion_products pp WHERE pp.promotion_id = p.id)
            """
        )
    )

    bind.execute(
        sa.text(
            """
            UPDATE promotion_products pp
            SET promotion_group_id = pg.id
            FROM promotion_groups pg
            WHERE pg.promotion_id = pp.promotion_id AND pg.group_name = 'Default'
            """
        )
    )

    _drop_old_promotion_product_pair_uniqueness()

    op.alter_column("promotion_products", "promotion_group_id", nullable=False)

    op.create_foreign_key(
        "fk_promotion_products_promotion_group_id",
        "promotion_products",
        "promotion_groups",
        ["promotion_group_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_promotion_products_promotion_group_id", "promotion_products", ["promotion_group_id"])

    op.execute(
        """
        CREATE UNIQUE INDEX uq_promotion_products_group_product
        ON promotion_products (promotion_group_id, product_id)
        """
    )


def downgrade() -> None:
    op.drop_index("uq_promotion_products_group_product", table_name="promotion_products")
    op.drop_index("ix_promotion_products_promotion_group_id", table_name="promotion_products")
    op.drop_constraint("fk_promotion_products_promotion_group_id", "promotion_products", type_="foreignkey")

    op.drop_column("promotion_products", "list_to_dealer_margin_amount")
    op.drop_column("promotion_products", "dealer_cost")
    op.drop_column("promotion_products", "dealer_discount_percent")
    op.drop_column("promotion_products", "promotion_group_id")

    op.drop_index("ix_promotion_groups_promotion_id", table_name="promotion_groups")
    op.drop_table("promotion_groups")

    op.create_unique_constraint(
        "uq_promotion_products_promotion_id_product_id",
        "promotion_products",
        ["promotion_id", "product_id"],
    )
