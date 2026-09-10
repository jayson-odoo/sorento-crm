"""Two empty lookup sets for attribute-first asks: certificate_scheme, attachment_type_alias

Revision ID: 511_attribute_first_lookup_sets
Revises: 510_strip_rtf_so_notes
Create Date: 2026-09-10

D3, PLAN-attribute-first-asks.md. NO options here by owner decision (10 Sep 2026:
"don't need to seed for scheme, I will enter") - the owner adds options and
keywords afterwards on System > Lookup Sets. Until then a scheme or alias word
resolves through neither set, which `product_predicate_service.py`'s legs read as
unrecognized, never a 500 (AC-1314).

Idempotent: re-running upgrade() leaves the same two rows, not duplicates.
Downgrade drops both sets; any options an owner has since entered cascade with
them (`lookup_options.set_id` is `ondelete=CASCADE`).
"""
from alembic import op
import sqlalchemy as sa


revision = "511_attribute_first_lookup_sets"
down_revision = "510_strip_rtf_so_notes"
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


def upgrade() -> None:
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
    for set_key, _name, _description in SETS:
        # Cascades to any owner-entered options + keywords via FK ondelete=CASCADE.
        op.execute(
            sa.text(
                "DELETE FROM lookup_sets WHERE tenant_id IS NULL AND set_key = :set_key"
            ).bindparams(set_key=set_key)
        )
