"""A series nominates PRODUCTS as well as categories (S18).

``project_series_categories`` could not express what the client means by "standard". Their
template is 151 product-code cells reaching 167 catalogue rows; those rows span 31
categories holding 15,048 products, so nominating the categories would call fifteen
thousand products standard in order to capture a hundred and sixty-seven - and would never
flag the sibling SKU the alert exists for.

So this ADDS a second, product-level nomination. Categories are untouched and stay: they
are the right tool for "everything under Basins is fair game". A product is in the series
if it is nominated here OR sits under a nominated category.

No backfill: the table starts empty by definition, and every existing series keeps
answering exactly as it did (empty product set, unchanged categories). The stale
``is_non_standard`` flags on existing lines are NOT rewritten here on purpose - the client
refused a bulk write and asked for a recompute button instead (S19), because master data
keeps moving and the correction has to be repeatable.

Revision ID: 331_project_series_products
Revises: dd96502280be
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision = "331_project_series_products"
down_revision = "dd96502280be"
branch_labels = None
depends_on = None

_TABLE = "project_series_products"


def _exists(name: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text("select to_regclass(:name) is not null"), {"name": f"public.{name}"}
        ).scalar()
    )


def upgrade() -> None:
    # Guarded because the dev database is a copy of production and this branch's revisions
    # have been applied to it by hand more than once.
    if _exists(_TABLE):
        return
    op.create_table(
        _TABLE,
        sa.Column(
            "series_id",
            UUID(as_uuid=False),
            sa.ForeignKey("project_series.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "product_id",
            UUID(as_uuid=False),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    # The composite primary key already answers "is this product in this series"; this one
    # answers the other direction - "which series list this product" - which is what a
    # product page and a future impact check both ask.
    op.create_index(
        "ix_project_series_products_product", _TABLE, ["product_id"], unique=False
    )


def downgrade() -> None:
    if not _exists(_TABLE):
        return
    op.drop_index("ix_project_series_products_product", table_name=_TABLE)
    op.drop_table(_TABLE)
