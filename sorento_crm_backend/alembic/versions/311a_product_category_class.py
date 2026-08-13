"""Decode the class and brand hiding in product_categories.category_code.

`category_name` is a verbatim copy of `category_code` on all 175 live rows, so the
class and brand encoded in `SRT-KS` / `CB-FT` / `BRT-WC` are invisible to any query.
Spec search needs them as real values: class has total coverage (every product has a
category) where `dimensions_length` reaches 14.6% of rows and `item_type` none at all,
which makes it the largest single boost in the ranker.

DDL is four additive columns, all nullable or defaulted, so no existing row changes
meaning and no existing read breaks.

The data half seeds the PILOT class only (kitchen sink: SRT-KS, CB-KS). Every other
category is deliberately left unclassified and counted, because a category nobody has
classified must be visible as such. Guessing a class is the most damaging thing that
can be done to the ranker, since class carries the largest weight.

Idempotent both halves: the columns are added only if absent, and the seed is
set-where-mismatch rather than update-where-null, so re-running repairs a prior bad
run instead of skipping it.

REVISION ID NOTE: chained on 310, the committed main head resolved via
ScriptDirectory.get_heads() rather than by picking the highest file number, which is
how a numbered-but-consumed node has broken a deploy here before. The `a` suffix
avoids a collision with the in-flight 311_certificate_register on another branch. If
both land, alembic will report two heads off 310 and needs an `alembic merge`.

Revision ID: 311a_product_category_class
Revises: 310_form_sla_skip_stage
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "311a_product_category_class"
down_revision = "320_company_aware_routing"
branch_labels = None
depends_on = None


TABLE = "product_categories"
NEW_COLUMNS = ("class_label", "brand_hint", "search_synonyms", "is_searchable")


def _has_column(bind, table: str, column: str) -> bool:
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": column},
        ).scalar()
    )


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_column(bind, TABLE, "class_label"):
        op.add_column(TABLE, sa.Column("class_label", sa.String(length=100), nullable=True))
    if not _has_column(bind, TABLE, "brand_hint"):
        op.add_column(TABLE, sa.Column("brand_hint", sa.String(length=100), nullable=True))
    if not _has_column(bind, TABLE, "search_synonyms"):
        op.add_column(
            TABLE,
            sa.Column(
                "search_synonyms",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
        )
    if not _has_column(bind, TABLE, "is_searchable"):
        op.add_column(
            TABLE,
            sa.Column(
                "is_searchable",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
        )

    # Seed the pilot class. Imported rather than duplicated as SQL so the migration and
    # the re-runnable job can never disagree about what a category code means.
    from sqlalchemy.orm import Session

    from app.services.product_class_signal import backfill_category_signals

    session = Session(bind=bind)
    try:
        result = backfill_category_signals(session)
        session.flush()
        print(
            f"[311a] category class signal: {result['updated']} classified, "
            f"{result['unmapped_count']} still unmapped (expected until T2 widens the map)"
        )
    finally:
        session.close()


def downgrade() -> None:
    bind = op.get_bind()
    for column in reversed(NEW_COLUMNS):
        if _has_column(bind, TABLE, column):
            op.drop_column(TABLE, column)
