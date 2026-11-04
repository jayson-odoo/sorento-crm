"""Price tag LP/SP per line, default tag template, combo tag templates (PRICETAG-LPSP).

documentation/plans/dealer-kit/PLAN-pricetag-lpsp-04nov.md, slice S1.

1. ``price_tag_request_lines.price_type`` VARCHAR(16) NULL, CHECK in ('list','selling'),
   backfilled from the request's ``price_mode`` so every existing line keeps what it printed.
2. ``dealer_kit.product_tag_template.is_default`` plus a partial unique index: one default
   link per product.
3. ``dealer_kit.combo_tag_template``: the combo's own tag templates, same shape as the product
   links (CASCADE on both FKs, unique (combo_id, template_id), one default per combo).

4. A new version of the ``ai_extract_portal_price_tag_request`` prompt carrying rule (10)
   (LP/SP price types, typed prices, "+" sets), moved onto the ``production`` label only when
   that label still holds the pre-LPSP text byte for byte (an owner-edited prompt is left
   alone; no stored prompt = nothing to do). Same mechanism as ``ptag_0013_r10`` (S2). The
   texts are literals here, never imported from the application. Not reversed on downgrade:
   a prompt version is data, and the older one stays on file.

Idempotent (IF NOT EXISTS everywhere): a database built by ``create_all`` already holds all of
it. Downgrade drops everything added.

Revision ID: ptag_0014_lpsp
Revises: tinv_0001_target_invoiced_basis
Create Date: 2026-11-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "ptag_0014_lpsp"
down_revision = "tinv_0001_target_invoiced_basis"
branch_labels = None
depends_on = None


PROMPT_NAME = "ai_extract_portal_price_tag_request"

# Production's text before this lane: `ptag_0013_r10`'s version 2, frozen here.
_PRE_LPSP_TEXT = (
    "You are an information-extraction assistant. The user uploads documents "
    "(delivery orders, photos, message screenshots, PDFs). Read every "
    "attachment and return a single JSON object whose top-level keys are the "
    "form field names below. Rules: (1) Omit any field you cannot find or are "
    "not confident about - do not guess. (2) For fields with a `lookup`, "
    "return ONLY one of the listed option `value` strings, exactly. (3) For "
    "`do_number` fields with `multi: true`, return an array of strings. (4) "
    "For `date` fields, use ISO-8601 (YYYY-MM-DD). (5) For `fk_product`, "
    "return the closest-matching product_code from the supplied examples; if "
    "nothing matches, return the raw code as printed in the document. If "
    "multiple distinct product codes apply, return them as a single "
    'comma-separated string (e.g. "TPE-9201, TPE-9203") - never as a JSON '
    "array. (6) For `text`, `textarea`, and `fk_customer` fields, if the "
    "document shows multiple distinct values for the same field, return them "
    "as a single comma-separated string. (7) Never invent values. Never "
    "include explanations or prose. (8) When the form has line items, "
    "`products` is REQUIRED whenever the document shows any product code: "
    "every product code line is one entry, even when no quantity, price or "
    "name is shown. Return an empty `products` array only when no product "
    "code appears anywhere. (9) `quantity` is how many tags the salesperson "
    "wants, which the document never says. Omit `quantity` from every entry; "
    "never copy a quantity, pack size or order quantity from the document."
)

# Matches `_ai_extract_price_tag_fallback()` as this lane leaves it.
_LPSP_TEXT = _PRE_LPSP_TEXT + (
    ' (10) Prices and sets. An entry may carry `price_type` ("list" or '
    '"selling"), `typed_list_price`, `typed_sell_price` (plain numbers, '
    "no currency symbol) and `set_codes`. A line under a section header "
    '"LP" (list price) or "SP" (selling price), or carrying "LP rm.." '
    'or "SP rm.." itself, takes that `price_type`; a price written on the '
    "line wins over the header. Put an LP figure in `typed_list_price` and "
    "an SP figure in `typed_sell_price`. When product codes are joined by "
    '"+", the first is `product_code` and the others, in the order '
    "written, are `set_codes` (an array of strings). When one line shows a "
    "second price of the same kind, keep the first in the typed field and "
    "put the other in `notes`. Omit `price_type` and any price the "
    "document does not state; never guess either."
)


def _publish_prompt() -> None:
    conn = op.get_bind()
    production_text = conn.execute(
        sa.text(
            "SELECT v.template FROM ai_prompt_labels l "
            "JOIN ai_prompt_versions v ON v.id = l.version_id "
            "WHERE l.name = :n AND l.label = 'production'"
        ),
        {"n": PROMPT_NAME},
    ).scalar()
    if production_text is None or production_text != _PRE_LPSP_TEXT:
        return
    next_version = conn.execute(
        sa.text(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM ai_prompt_versions WHERE name = :n"
        ),
        {"n": PROMPT_NAME},
    ).scalar()
    new_id = conn.execute(
        sa.text(
            "INSERT INTO ai_prompt_versions (id, name, version, type, template, variables) "
            "VALUES (gen_random_uuid(), :n, :v, 'text', :t, '[]'::jsonb) RETURNING id"
        ),
        {"n": PROMPT_NAME, "v": next_version, "t": _LPSP_TEXT},
    ).scalar()
    conn.execute(
        sa.text(
            "UPDATE ai_prompt_labels SET version_id = :v WHERE name = :n AND label = 'production'"
        ),
        {"n": PROMPT_NAME, "v": new_id},
    )


def _dk() -> str:
    """The dealer_kit schema prefix, read from where ``tag_template`` lives on this
    connection's search_path (see ``ptpt_0001_product_tag_templates._dk``)."""
    schema = op.get_bind().execute(
        sa.text(
            "SELECT n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.oid = to_regclass('tag_template')"
        )
    ).scalar()
    return f'"{schema or "dealer_kit"}".'


def upgrade() -> None:
    dk = _dk()
    op.execute(
        "ALTER TABLE price_tag_request_lines ADD COLUMN IF NOT EXISTS price_type VARCHAR(16) NULL"
    )
    # conrelid, not just conname: the name repeats in every schema holding the table.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_price_tag_request_lines_price_type'
                  AND conrelid = 'price_tag_request_lines'::regclass
            ) THEN
                ALTER TABLE price_tag_request_lines
                    ADD CONSTRAINT ck_price_tag_request_lines_price_type
                    CHECK (price_type IN ('list','selling'));
            END IF;
        END $$;
        """
    )
    op.execute(
        "UPDATE price_tag_request_lines l SET price_type = r.price_mode "
        "FROM price_tag_requests r "
        "WHERE r.id = l.request_id AND l.price_type IS NULL "
        "AND r.price_mode IN ('list','selling')"
    )

    op.execute(
        f"ALTER TABLE {dk}product_tag_template "
        "ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_dealer_kit_product_tag_template_default "
        f"ON {dk}product_tag_template (product_id) WHERE is_default"
    )

    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {dk}combo_tag_template (
            id UUID PRIMARY KEY,
            combo_id UUID NOT NULL REFERENCES product_combos(id) ON DELETE CASCADE,
            template_id UUID NOT NULL REFERENCES {dk}tag_template(id) ON DELETE CASCADE,
            is_default BOOLEAN NOT NULL DEFAULT false,
            created_by VARCHAR NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
            CONSTRAINT uq_dealer_kit_combo_tag_template UNIQUE (combo_id, template_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_dealer_kit_combo_tag_template_template_id "
        f"ON {dk}combo_tag_template (template_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_dealer_kit_combo_tag_template_default "
        f"ON {dk}combo_tag_template (combo_id) WHERE is_default"
    )
    _publish_prompt()


def downgrade() -> None:
    dk = _dk()
    op.execute(f"DROP TABLE IF EXISTS {dk}combo_tag_template")
    op.execute(f"ALTER TABLE {dk}product_tag_template DROP COLUMN IF EXISTS is_default")
    op.execute("ALTER TABLE price_tag_request_lines DROP COLUMN IF EXISTS price_type")
