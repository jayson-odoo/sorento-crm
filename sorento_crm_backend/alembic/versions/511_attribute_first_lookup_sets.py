"""Two empty lookup sets for attribute-first asks: certificate_scheme, attachment_type_alias

Revision ID: 511_attribute_first_lookup_sets
Revises: sales_0002_team_leader
Create Date: 2026-09-10

D3, PLAN-attribute-first-asks.md. NO options here by owner decision (10 Sep 2026:
"don't need to seed for scheme, I will enter") - the owner adds options and
keywords afterwards on System > Lookup Sets. Until then a scheme or alias word
resolves through neither set, which `product_predicate_service.py`'s legs read as
unrecognized, never a 500 (AC-1314).

Idempotent: re-running upgrade() leaves the same two rows, not duplicates.
Downgrade drops both sets; any options an owner has since entered cascade with
them (`lookup_options.set_id` is `ondelete=CASCADE`).

Also (revive, 26 Sep 2026, owner: "which water tap got stock ... which water basin
got stock"): appends "water tap" to every Tap category's `search_synonyms` and
"water basin" to every Wash Basin one, the same words
`product_class_signal.CLASS_SYNONYMS` now carries so a later backfill keeps them.
Append-only: a word already there (staff's or the backfill's) is never touched,
and the word is never added twice. Downgrade removes only these two words, including
where staff had entered one of them before this migration (upgrade records no row list;
accepted and documented, reviewer N1 on PR #833).
"""
from alembic import op
import sqlalchemy as sa


revision = "511_attribute_first_lookup_sets"
down_revision = "sales_0002_team_leader"
branch_labels = None
depends_on = None


# (set_key, name, description)
SETS = (
    (
        "certificate_scheme",
        "Certificate Scheme",
        "Aliases for a certificate register scheme word (e.g. 'pps cert' -> PPS), "
        "so 'has cert' with a scheme narrows correctly.",
    ),
    (
        "attachment_type_alias",
        "Attachment Type Alias",
        "Aliases for an attachment type label (e.g. 'photo', 'gambar' -> Product "
        "Photos), so an attribute-first ask about a document class resolves.",
    ),
)


# (class_label, the word appended to that class's categories)
CLASS_WORDS = (("Tap", "water tap"), ("Wash Basin", "water basin"))


def upgrade() -> None:
    for class_label, word in CLASS_WORDS:
        op.execute(
            sa.text(
                """
                UPDATE product_categories
                SET search_synonyms = COALESCE(search_synonyms, '[]'::jsonb) || jsonb_build_array(CAST(:word AS text))
                WHERE class_label = :class_label
                  AND NOT (COALESCE(search_synonyms, '[]'::jsonb) @> jsonb_build_array(CAST(:word AS text)))
                """
            ).bindparams(class_label=class_label, word=word)
        )
    for set_key, name, description in SETS:
        op.execute(
            sa.text(
                """
                INSERT INTO lookup_sets (id, tenant_id, set_key, name, description, is_active)
                SELECT gen_random_uuid(), NULL, :set_key, :name, :description, TRUE
                WHERE NOT EXISTS (
                    SELECT 1 FROM lookup_sets
                    WHERE tenant_id IS NULL AND set_key = :set_key
                )
                """
            ).bindparams(set_key=set_key, name=name, description=description)
        )
        op.execute(
            sa.text(
                """
                UPDATE lookup_sets
                SET name = :name,
                    description = :description,
                    is_active = TRUE,
                    updated_at = now()
                WHERE tenant_id IS NULL AND set_key = :set_key
                """
            ).bindparams(set_key=set_key, name=name, description=description)
        )


def downgrade() -> None:
    for class_label, word in CLASS_WORDS:
        op.execute(
            sa.text(
                """
                UPDATE product_categories
                SET search_synonyms = search_synonyms - CAST(:word AS text)
                WHERE class_label = :class_label
                """
            ).bindparams(class_label=class_label, word=word)
        )
    for set_key, _name, _description in SETS:
        # Cascades to any owner-entered options + keywords via FK ondelete=CASCADE.
        op.execute(
            sa.text(
                "DELETE FROM lookup_sets WHERE tenant_id IS NULL AND set_key = :set_key"
            ).bindparams(set_key=set_key)
        )
