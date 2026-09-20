"""r10 schema (PLAN-price-tag-r10.md "Migration ptag_0013_r10").

Six additive pieces, none touching what already exists:

1. AC-S1-4: ``price_tag_requests.print_by`` NULL -> ``'self'`` (a request
   born before r9 D7 never answered the question; ``office`` rows are
   untouched).
2. AC-S2-5: a version-2 prompt for ``ai_extract_portal_price_tag_request``,
   inserted only when the STORED version 1 is byte-for-byte the pre-r10
   fallback (an owner-edited version 1 is left alone; a tenant with no
   stored version gets nothing, since there is nothing to compare against).
   The new text is a literal here, never imported from
   ``ai_prompt_registry`` - a migration must not depend on live application
   code drifting out from under it (LESSONS-LEARNT 340).
3. AC-S4-1: ``products.price_tag_description TEXT NULL``.
4. AC-S5-1: ``product_combos.image_attachment_id UUID NULL`` FK
   ``attachments(id) ON DELETE SET NULL``, plus the ``Combo Image``
   (``combo_image``) attachment type, seeded idempotently by code.
5. AC-S6-1: ``price_tag_request_tags.print_excluded BOOLEAN NOT NULL
   DEFAULT false``.
6. AC-S7-11: ``dealer_kit.tag_size_preset`` gains ``sheet_cols``,
   ``sheet_rows``, ``sheet_turn``.
7. AC-S8-1: ``price_tag_request_tags`` gains ``data_updated_at``,
   ``data_update_changes``, ``data_update_version``.

Downgrade drops every column added by 3/4/5/7 (the attachment TYPE row from
4 stays - an attachment may still reference it, same rule every other
attachment-type seed in this codebase follows) and leaves 1/2's DATA
untouched, the same as every other backfill migration in this codebase: a
downgrade restores SCHEMA, not a value a person may have acted on since.

Revision ID: ptag_0013_r10
Revises: 522_oi_cancelled_used_confirm
Create Date: 2026-09-21
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "ptag_0013_r10"
down_revision = "522_oi_cancelled_used_confirm"
branch_labels = None
depends_on = None

PROMPT_NAME = "ai_extract_portal_price_tag_request"

# The EXACT text `_ai_extract_price_tag_fallback()` returned before this
# migration's own S2 changed it (frozen 20 Sep 2026, one call) - compared
# against the STORED version 1 template, never against the live function
# (LESSONS-LEARNT 340: a migration must never import live application code,
# since that code keeps changing in this very lane).
_PRE_R10_FALLBACK = (
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
    "code appears anywhere."
)

# What version 2 becomes: the same text plus rule (9), matching
# `app.services.ai_prompt_registry._ai_extract_price_tag_fallback()` exactly
# as this lane's S2 slice leaves it.
_V2_TEXT = _PRE_R10_FALLBACK + (
    " (9) `quantity` is how many tags the salesperson wants, which the "
    "document never says. Omit `quantity` from every entry; never copy a "
    "quantity, pack size or order quantity from the document."
)


def _dealer_kit_schema(conn) -> str | None:
    """None when ``tag_size_preset`` is reachable UNQUALIFIED on this
    connection's own search_path (a test's scratch schema already lists its
    ``..._dealer_kit`` sibling there - `tests/_pg_fixture.py`), else the
    literal ``dealer_kit`` schema production actually uses.

    ``op.add_column``'s own ``schema=`` kwarg is not rewritten by
    ``schema_translate_map`` the way an ordinary compiled ORM/Core construct
    is (measured, same gotcha ``ptag_0011_line_promotion.py``'s own
    ``_dealer_kit_schema`` docstring names for a different construct) - a
    literal ``schema="dealer_kit"`` under test lands on the real, separately
    migrated ``dealer_kit`` schema that already exists in the CI database,
    not the scratch one this test session actually reads back from.
    """
    inspector = sa.inspect(conn)
    return None if inspector.has_table("tag_size_preset") else "dealer_kit"


def _seed_combo_image_type() -> None:
    """AC-S5-1: idempotent by ``code`` - a second run inserts nothing new."""
    op.execute(
        sa.text(
            "INSERT INTO attachment_types "
            "(id, code, type_name, allowed_extensions, max_file_size_mb, created_at) "
            "SELECT gen_random_uuid(), 'combo_image', 'Combo Image', "
            "'jpg,jpeg,png,webp', 10, now() AT TIME ZONE 'utc' "
            "WHERE NOT EXISTS (SELECT 1 FROM attachment_types WHERE code = 'combo_image')"
        )
    )


def upgrade() -> None:
    conn = op.get_bind()

    # --- AC-S1-4: print_by backfill -----------------------------------------
    conn.execute(
        sa.text(
            "UPDATE price_tag_requests SET print_by = 'self' WHERE print_by IS NULL"
        )
    )

    # --- AC-S2-5: v2 prompt, only over an untouched v1 ----------------------
    stored_v1 = conn.execute(
        sa.text(
            "SELECT template FROM ai_prompt_versions WHERE name = :n AND version = 1"
        ),
        {"n": PROMPT_NAME},
    ).scalar()
    if stored_v1 is not None and stored_v1 == _PRE_R10_FALLBACK:
        conn.execute(
            sa.text(
                "INSERT INTO ai_prompt_versions "
                "(id, name, version, type, template, variables) "
                "VALUES (gen_random_uuid(), :n, 2, 'text', :t, '[]'::jsonb)"
            ),
            {"n": PROMPT_NAME, "t": _V2_TEXT},
        )

    # --- AC-S4-1: products.price_tag_description ----------------------------
    op.add_column(
        "products", sa.Column("price_tag_description", sa.Text(), nullable=True)
    )

    # --- AC-S5-1: product_combos.image_attachment_id + Combo Image type -----
    op.add_column(
        "product_combos",
        sa.Column(
            "image_attachment_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("attachments.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    _seed_combo_image_type()

    # --- AC-S6-1: price_tag_request_tags.print_excluded ---------------------
    op.add_column(
        "price_tag_request_tags",
        sa.Column(
            "print_excluded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # --- AC-S7-11: dealer_kit.tag_size_preset grid columns -------------------
    dk_schema = _dealer_kit_schema(conn)
    op.add_column(
        "tag_size_preset",
        sa.Column("sheet_cols", sa.Integer(), nullable=True),
        schema=dk_schema,
    )
    op.add_column(
        "tag_size_preset",
        sa.Column("sheet_rows", sa.Integer(), nullable=True),
        schema=dk_schema,
    )
    op.add_column(
        "tag_size_preset",
        sa.Column(
            "sheet_turn", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        schema=dk_schema,
    )

    # --- AC-S8-1: the three data-update columns ------------------------------
    op.add_column(
        "price_tag_request_tags",
        sa.Column("data_updated_at", sa.DateTime(timezone=False), nullable=True),
    )
    op.add_column(
        "price_tag_request_tags",
        sa.Column("data_update_changes", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "price_tag_request_tags",
        sa.Column("data_update_version", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    conn = op.get_bind()

    op.drop_column("price_tag_request_tags", "data_update_version")
    op.drop_column("price_tag_request_tags", "data_update_changes")
    op.drop_column("price_tag_request_tags", "data_updated_at")

    dk_schema = _dealer_kit_schema(conn)
    op.drop_column("tag_size_preset", "sheet_turn", schema=dk_schema)
    op.drop_column("tag_size_preset", "sheet_rows", schema=dk_schema)
    op.drop_column("tag_size_preset", "sheet_cols", schema=dk_schema)

    op.drop_column("price_tag_request_tags", "print_excluded")

    # The `Combo Image` attachment TYPE row stays - an attachment may still
    # reference it, the same rule every other attachment-type seed follows.
    op.drop_column("product_combos", "image_attachment_id")

    op.drop_column("products", "price_tag_description")

    # print_by / the v2 prompt: data, not schema - left as they are, the same
    # way every other backfill migration in this codebase treats its downgrade.
