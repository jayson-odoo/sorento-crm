"""proforma_invoice_line / proforma_invoice_packing_line carry description_en (S2, text
glossary lane, R11 - PLAN-text-glossary.md).

Adds the cache column both tables read `description_en or description` from downstream
(shipment line, packing list line, container workbook, unplaced-rows note), and backfills
it from whatever `translation_memory` already knows (the upload preview's own AI fill, or
an earlier manual correction) - so PI-2609-001..008 on prod pick up an English word typed
once on any one of them, without a re-upload. Normalises `description` the same way
`translation_service.normalize_source_text` does (trim, collapse internal whitespace)
before matching it against the memory's own normalised `source_text`.

No seed rows (R6): a row with nothing in `translation_memory` for its description stays
NULL, same as before this migration ran.

Revision ID: 510_pi_description_en
Revises: 509_merge_508_summary_exclwh
Create Date: 2026-09-10
"""
import sqlalchemy as sa
from alembic import op

revision = "510_pi_description_en"
down_revision = "509_merge_508_summary_exclwh"
branch_labels = None
depends_on = None

_SCHEMA = "scm"
_LINE = "proforma_invoice_line"
_PACKING_LINE = "proforma_invoice_packing_line"
_MEMORY = "translation_memory"


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str, schema: str | None = None) -> bool:
    return _inspector().has_table(name, schema=schema)


def _has_column(table: str, column: str, schema: str | None = None) -> bool:
    if not _has_table(table, schema=schema):
        return False
    return column in {col["name"] for col in _inspector().get_columns(table, schema=schema)}


def _backfill(table: str) -> None:
    op.execute(
        sa.text(
            f"""
            UPDATE {_SCHEMA}.{table} r
            SET description_en = m.target_text
            FROM {_MEMORY} m
            WHERE m.source_lang = 'zh' AND m.target_lang = 'en'
              AND regexp_replace(btrim(r.description), '\\s+', ' ', 'g') = m.source_text
              AND r.description_en IS NULL
            """
        )
    )


def upgrade() -> None:
    if not _has_column(_LINE, "description_en", schema=_SCHEMA):
        op.add_column(_LINE, sa.Column("description_en", sa.Text(), nullable=True), schema=_SCHEMA)
    if not _has_column(_PACKING_LINE, "description_en", schema=_SCHEMA):
        op.add_column(
            _PACKING_LINE, sa.Column("description_en", sa.Text(), nullable=True), schema=_SCHEMA
        )

    if _has_table(_MEMORY):
        if _has_table(_LINE, schema=_SCHEMA):
            _backfill(_LINE)
        if _has_table(_PACKING_LINE, schema=_SCHEMA):
            _backfill(_PACKING_LINE)


def downgrade() -> None:
    if _has_column(_LINE, "description_en", schema=_SCHEMA):
        op.drop_column(_LINE, "description_en", schema=_SCHEMA)
    if _has_column(_PACKING_LINE, "description_en", schema=_SCHEMA):
        op.drop_column(_PACKING_LINE, "description_en", schema=_SCHEMA)
