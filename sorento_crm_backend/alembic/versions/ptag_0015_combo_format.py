"""Template price type and one default LP + one default SP link (PRICETAG-COMBO-FORMAT).

documentation/plans/dealer-kit/pricetag-combo-format-contract.md, slices S5 and S6.

1. ``dealer_kit.tag_template.price_type`` VARCHAR(16) NULL, CHECK in ('list','selling','both').
   Existing rows stay NULL (unset: offered on LP and SP lines, exactly as before).
2. ``dealer_kit.product_tag_template`` and ``dealer_kit.combo_tag_template``: ``is_default`` is
   replaced by ``default_list`` and ``default_selling`` (BOOLEAN NOT NULL DEFAULT false), each
   with a partial unique index per owner. An ``is_default`` row gets both flags (today's default
   stays the default for LP and SP lines). The old column and its index are dropped.

Downgrade: ``is_default`` = ``default_selling``, or ``default_list`` where the owner has no
``default_selling`` row; the new columns and indexes go.

Idempotent: a database built by ``create_all`` already holds the new shape.

Revision ID: ptag_0015_combo_format
Revises: ttdc_0001_tag_template_archived
Create Date: 2026-11-05
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "ptag_0015_combo_format"
down_revision = "ttdc_0001_tag_template_archived"
branch_labels = None
depends_on = None

_LINKS = (
    ("product_tag_template", "product_id", "uq_dealer_kit_product_tag_template_default"),
    ("combo_tag_template", "combo_id", "uq_dealer_kit_combo_tag_template_default"),
)


def _dk() -> str:
    """The dealer_kit schema prefix, read from where ``tag_template`` lives on this
    connection's search_path (see ``ptag_0014_lpsp._dk``)."""
    schema = op.get_bind().execute(
        sa.text(
            "SELECT n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.oid = to_regclass('tag_template')"
        )
    ).scalar()
    return f'"{schema or "dealer_kit"}".'


def _has_column(dk: str, table: str, column: str) -> bool:
    return bool(
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM pg_attribute WHERE attrelid = to_regclass(:t) "
                "AND attname = :c AND attnum > 0 AND NOT attisdropped"
            ),
            {"t": f"{dk}{table}", "c": column},
        )
        .scalar()
    )


def upgrade() -> None:
    dk = _dk()
    op.execute(f"ALTER TABLE {dk}tag_template ADD COLUMN IF NOT EXISTS price_type VARCHAR(16) NULL")
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_dealer_kit_tag_template_price_type'
                  AND conrelid = '{dk}tag_template'::regclass
            ) THEN
                ALTER TABLE {dk}tag_template
                    ADD CONSTRAINT ck_dealer_kit_tag_template_price_type
                    CHECK (price_type IN ('list','selling','both'));
            END IF;
        END $$;
        """
    )

    for table, owner, old_index in _LINKS:
        op.execute(
            f"ALTER TABLE {dk}{table} ADD COLUMN IF NOT EXISTS default_list BOOLEAN NOT NULL DEFAULT false"
        )
        op.execute(
            f"ALTER TABLE {dk}{table} ADD COLUMN IF NOT EXISTS default_selling BOOLEAN NOT NULL DEFAULT false"
        )
        if _has_column(dk, table, "is_default"):
            op.execute(
                f"UPDATE {dk}{table} SET default_list = true, default_selling = true WHERE is_default"
            )
            op.execute(f"DROP INDEX IF EXISTS {dk}{old_index}")
            op.execute(f"ALTER TABLE {dk}{table} DROP COLUMN is_default")
        op.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {old_index}_list "
            f"ON {dk}{table} ({owner}) WHERE default_list"
        )
        op.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {old_index}_selling "
            f"ON {dk}{table} ({owner}) WHERE default_selling"
        )


def downgrade() -> None:
    dk = _dk()
    for table, owner, old_index in _LINKS:
        op.execute(
            f"ALTER TABLE {dk}{table} ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT false"
        )
        op.execute(
            f"""
            UPDATE {dk}{table} t SET is_default = true
            WHERE t.default_selling
               OR (t.default_list AND NOT EXISTS (
                    SELECT 1 FROM {dk}{table} s WHERE s.{owner} = t.{owner} AND s.default_selling))
            """
        )
        op.execute(f"DROP INDEX IF EXISTS {dk}{old_index}_list")
        op.execute(f"DROP INDEX IF EXISTS {dk}{old_index}_selling")
        op.execute(f"ALTER TABLE {dk}{table} DROP COLUMN IF EXISTS default_list")
        op.execute(f"ALTER TABLE {dk}{table} DROP COLUMN IF EXISTS default_selling")
        op.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {old_index} ON {dk}{table} ({owner}) WHERE is_default"
        )
    op.execute(f"ALTER TABLE {dk}tag_template DROP COLUMN IF EXISTS price_type")
