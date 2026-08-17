"""What a series sells a product for, and how far it may be discounted (T1).

Two nullable columns on ``project_series_products``:

* ``selling_price``     - the price this SERIES sells the product at. The client's sheet calls
  it DEVELOPERS. It is not the product's list price and does not replace it: the same product
  can sit in two series at two prices, which is why this lives on the link row.
* ``max_discount_pct``  - how much further a distributor may come down from that price,
  stored as a PERCENT (``6`` means 6%). The sheet calls it DISTRIBUTORS and writes it two ways,
  ``6 % MAX`` in one tab and ``0.06`` in another; both normalise to ``6`` on the way in.

**Both are nullable, and a NULL is silence rather than zero.** Measured on the client's book of
151 codes: 95 carry a price, 56 carry a discount, and the whole ``shower`` tab carries neither.
A NULL discount therefore falls through to ``price_floor_rules`` rather than being read as "no
discount permitted" - that reading would put a hard floor under 56 products nobody set one for.

Precision: ``NUMERIC(12, 2)`` matches ``price_floor_rules.value`` and the money columns on
quotation lines. ``NUMERIC(5, 2)`` holds 0.00 to 999.99, so a percentage cannot silently
overflow and cannot carry more precision than a human would ever type.

**No backfill.** These numbers do not exist anywhere in the database yet - they are in a
spreadsheet - so there is nothing to copy in. They arrive when somebody loads the sheet.

Defensively re-runnable, because the dev database is a copy of production and this branch's
revisions have been applied there by hand (``Operations.context``), leaving ``alembic_version``
untouched. See documentation/plans/PLAN-series-catalogue-and-pricing-pages.md.

Revision ID: 333_series_product_pricing
Revises: 332_extraction_job_tracking
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision = "333_series_product_pricing"
down_revision = "332_extraction_job_tracking"
branch_labels = None
depends_on = None


_TABLE = "project_series_products"
_COLUMNS = (
    ("selling_price", sa.Numeric(12, 2)),
    ("max_discount_pct", sa.Numeric(5, 2)),
)


def _has_column(table: str, column: str) -> bool:
    return bool(
        op.get_bind()
        .execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": column},
        )
        .scalar()
    )


def upgrade() -> None:
    for name, type_ in _COLUMNS:
        if not _has_column(_TABLE, name):
            op.add_column(_TABLE, sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    for name, _type in _COLUMNS:
        if _has_column(_TABLE, name):
            op.drop_column(_TABLE, name)
