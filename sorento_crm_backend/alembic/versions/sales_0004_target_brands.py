"""Sales module, S1 fix round 2: a target can apply to one or more brands.

The owner's hand test of 27 Sep (PR #1297, "this one need 1 more choice is 'Brand'"): Applies
to gains a fourth choice beside All products, Categories and Products.

1. `sales.target_scope.brand_id`, FK `brands` ON DELETE CASCADE (a deleted brand leaves the
   target, like a deleted category or product), indexed. The one-of check now covers three
   columns.
2. `sales.targets.product_scope` accepts `brands`.

Downgrade deletes the brand scope rows, turns a brand target back into All products (the old
check would refuse `brands`), and drops the column.

Revision ID: sales_0004_target_brands
Revises: sales_0003_targets
Create Date: 2026-09-27
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.models.sales import translated_schema

revision = "sales_0004_target_brands"
down_revision = "sales_0003_targets"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=False)


def upgrade() -> None:
    # `sales`, or the migration test's scratch copy of it: alembic's ALTER TABLE ignores
    # `schema_translate_map`, so the schema is named explicitly (the sales_0002 precedent).
    schema = translated_schema(op.get_bind())
    op.add_column("target_scope", sa.Column("brand_id", _UUID, nullable=True), schema=schema)
    op.create_foreign_key(
        "fk_sales_target_scope_brand_id",
        "target_scope",
        "brands",
        ["brand_id"],
        ["id"],
        source_schema=schema,
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_sales_target_scope_brand_id", "target_scope", ["brand_id"], schema=schema
    )
    op.drop_constraint("ck_sales_target_scope_one", "target_scope", schema=schema, type_="check")
    op.create_check_constraint(
        "ck_sales_target_scope_one",
        "target_scope",
        "num_nonnulls(product_category_id, product_id, brand_id) = 1",
        schema=schema,
    )
    op.drop_constraint("ck_sales_targets_product_scope", "targets", schema=schema, type_="check")
    op.create_check_constraint(
        "ck_sales_targets_product_scope",
        "targets",
        "product_scope IN ('all', 'categories', 'products', 'brands')",
        schema=schema,
    )


def downgrade() -> None:
    schema = translated_schema(op.get_bind())
    scope = sa.table("target_scope", sa.column("brand_id"), schema=schema)
    targets = sa.table("targets", sa.column("product_scope"), schema=schema)
    op.execute(scope.delete().where(scope.c.brand_id.isnot(None)))
    op.execute(
        targets.update().where(targets.c.product_scope == "brands").values(product_scope="all")
    )
    op.drop_constraint("ck_sales_targets_product_scope", "targets", schema=schema, type_="check")
    op.create_check_constraint(
        "ck_sales_targets_product_scope",
        "targets",
        "product_scope IN ('all', 'categories', 'products')",
        schema=schema,
    )
    op.drop_constraint("ck_sales_target_scope_one", "target_scope", schema=schema, type_="check")
    op.create_check_constraint(
        "ck_sales_target_scope_one",
        "target_scope",
        "num_nonnulls(product_category_id, product_id) = 1",
        schema=schema,
    )
    op.drop_index("ix_sales_target_scope_brand_id", "target_scope", schema=schema)
    op.drop_constraint(
        "fk_sales_target_scope_brand_id", "target_scope", schema=schema, type_="foreignkey"
    )
    op.drop_column("target_scope", "brand_id", schema=schema)
