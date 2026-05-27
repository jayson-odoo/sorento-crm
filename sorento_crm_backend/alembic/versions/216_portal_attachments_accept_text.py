"""Extend portal_submission attachment type to accept pasted text (.txt).

The portal attachment dropzone now lets contacts paste plain text, which the
frontend saves as a `.txt` file flowing through the normal upload path (mirrors
the AI-extract text-paste feature). The backend whitelist must include `txt`
or `_check_quota` rejects it.

Also re-seeds the `portal_submission` attachment type when missing so installs
that never received the original seed (e.g. partial DB migrations) converge.

Idempotent: derives the new CSV from whatever the row currently stores.

Revision ID: 216_portal_attachments_accept_text
Revises: 215_backfill_pr_status_from_approval
Create Date: 2026-05-27
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "216_portal_attachments_accept_text"
down_revision = "215_backfill_pr_status_from_approval"
branch_labels = None
depends_on = None


_TEXT_EXTS = ("txt",)


def upgrade() -> None:
    bind = op.get_bind()

    # Re-seed the row if a partial migration left it absent.
    bind.execute(
        sa.text(
            """
            INSERT INTO attachment_types
                (id, code, type_name, description, allowed_extensions, max_file_size_mb, max_count_per_entity)
            VALUES (
                gen_random_uuid(),
                'portal_submission',
                'Portal Submission',
                'Attachments uploaded by external contacts via the user submission portal.',
                'jpg,jpeg,png,heic,webp,pdf,mp4,mov,webm,m4v,3gp,txt',
                100,
                10
            )
            ON CONFLICT (code) DO NOTHING
            """
        )
    )

    row = bind.execute(
        sa.text(
            "SELECT allowed_extensions FROM attachment_types "
            "WHERE code = 'portal_submission'"
        )
    ).first()
    if row is None:
        return

    current_exts = {
        e.strip().lower().lstrip(".")
        for e in (row[0] or "").split(",")
        if e.strip()
    }
    new_csv = ",".join(sorted(current_exts | set(_TEXT_EXTS)))

    bind.execute(
        sa.text(
            "UPDATE attachment_types "
            "SET allowed_extensions = :exts "
            "WHERE code = 'portal_submission' "
            "AND allowed_extensions IS DISTINCT FROM :exts"
        ),
        {"exts": new_csv},
    )


def downgrade() -> None:
    bind = op.get_bind()
    row = bind.execute(
        sa.text(
            "SELECT allowed_extensions FROM attachment_types "
            "WHERE code = 'portal_submission'"
        )
    ).first()
    if row is None:
        return

    remaining = sorted(
        {
            e.strip().lower().lstrip(".")
            for e in (row[0] or "").split(",")
            if e.strip() and e.strip().lower().lstrip(".") not in _TEXT_EXTS
        }
    )
    bind.execute(
        sa.text(
            "UPDATE attachment_types "
            "SET allowed_extensions = :exts "
            "WHERE code = 'portal_submission'"
        ),
        {"exts": ",".join(remaining)},
    )
