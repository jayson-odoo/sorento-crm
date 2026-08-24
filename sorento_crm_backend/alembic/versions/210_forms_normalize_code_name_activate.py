"""Normalize Form.code / Form.name and activate all forms.

Three transforms applied to every row in `forms`:

  1. Strip a trailing file extension (.pdf / .xlsx / .xls / .docx / .doc /
     .png / .jpg / .jpeg) from both `code` and `name`. Form rows seeded from
     uploaded filenames carry the extension verbatim, which leaks into the
     Edit Form UI and the MCP search surface.
  2. In `code` only - replace spaces with underscores, drop characters that
     are not alphanumeric / dash / underscore (so parens, dots, etc. are
     removed), and collapse repeated underscores. Matches the FE validator
     `^[A-Za-z0-9_-]+$` so existing rows can be saved through the Edit Form
     screen without rewriting the code by hand.
  3. Activate every row (`is_active = TRUE`). Forms were left inactive after
     seeding; product decision is to enable the full set.

Idempotent - only writes where the derived value differs from the current
value (per `feedback_backfill_idempotent`).

Revision ID: 210_forms_normalize_code_name_activate
Revises: 209_portal_tokens_revoke_lookalike_and_remint
Create Date: 2026-05-21
"""
from __future__ import annotations

from alembic import op


revision = "210_forms_normalize_code_name_activate"
down_revision = "209_portal_tokens_revoke_lookalike_and_remint"
branch_labels = None
depends_on = None


_EXT_PATTERN = r"\.(pdf|xlsx|xls|docx|doc|png|jpg|jpeg)$"


def upgrade() -> None:
    # Strip trailing extension from name. Idempotent - no-op when name has
    # no extension or already matches the stripped form.
    op.execute(
        f"""
        UPDATE forms
        SET name = regexp_replace(name, '{_EXT_PATTERN}', '', 'i')
        WHERE name ~* '{_EXT_PATTERN}';
        """
    )

    # Normalize code: strip extension → spaces to underscores → drop chars
    # outside [A-Za-z0-9_-] → collapse repeated underscores → trim leading /
    # trailing underscores. All four passes inline so the WHERE clause can
    # compare against the final derived value.
    op.execute(
        f"""
        UPDATE forms
        SET code = trim(both '_' from regexp_replace(
            regexp_replace(
                replace(
                    regexp_replace(code, '{_EXT_PATTERN}', '', 'i'),
                    ' ',
                    '_'
                ),
                '[^A-Za-z0-9_-]',
                '',
                'g'
            ),
            '_+',
            '_',
            'g'
        ))
        WHERE code IS DISTINCT FROM trim(both '_' from regexp_replace(
            regexp_replace(
                replace(
                    regexp_replace(code, '{_EXT_PATTERN}', '', 'i'),
                    ' ',
                    '_'
                ),
                '[^A-Za-z0-9_-]',
                '',
                'g'
            ),
            '_+',
            '_',
            'g'
        ));
        """
    )

    op.execute(
        """
        UPDATE forms
        SET is_active = TRUE
        WHERE is_active = FALSE;
        """
    )


def downgrade() -> None:
    # Non-reversible: the original codes/names with extensions are not
    # preserved anywhere, and reactivation has no semantic inverse. Leave the
    # normalized values in place - operators can re-author manually.
    pass
