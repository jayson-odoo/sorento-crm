"""Extend portal_submission attachment type to accept videos.

Phone galleries hide files whose MIME the `<input accept=...>` attribute
excludes, so users on mobile couldn't see their videos when picking
attachments. Frontend dropzones now advertise `image/*,video/*,.pdf`; this
migration brings the backend whitelist in line by adding common video
extensions to `attachment_types.allowed_extensions` for `portal_submission`
and bumping `max_file_size_mb` to 100 MB (phone clips routinely exceed 10 MB).

Idempotent: derives the new CSV from whatever the row currently stores so
re-runs and partially-applied installs converge.

Revision ID: 211_portal_attachments_accept_video
Revises: 210_forms_normalize_code_name_activate
Create Date: 2026-05-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "211_portal_attachments_accept_video"
down_revision = "210_forms_normalize_code_name_activate"
branch_labels = None
depends_on = None


_VIDEO_EXTS = ("mp4", "mov", "webm", "m4v", "3gp")
_TARGET_SIZE_MB = 100


def upgrade() -> None:
    bind = op.get_bind()
    row = bind.execute(
        sa.text(
            "SELECT allowed_extensions, max_file_size_mb "
            "FROM attachment_types WHERE code = 'portal_submission'"
        )
    ).first()
    if row is None:
        return

    current_exts = {
        e.strip().lower().lstrip(".")
        for e in (row[0] or "").split(",")
        if e.strip()
    }
    merged = sorted(current_exts | set(_VIDEO_EXTS))
    new_csv = ",".join(merged)
    new_size = max(int(row[1] or 0), _TARGET_SIZE_MB)

    bind.execute(
        sa.text(
            "UPDATE attachment_types "
            "SET allowed_extensions = :exts, max_file_size_mb = :sz "
            "WHERE code = 'portal_submission' "
            "AND (allowed_extensions IS DISTINCT FROM :exts "
            "     OR max_file_size_mb IS DISTINCT FROM :sz)"
        ),
        {"exts": new_csv, "sz": new_size},
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
            if e.strip() and e.strip().lower().lstrip(".") not in _VIDEO_EXTS
        }
    )
    bind.execute(
        sa.text(
            "UPDATE attachment_types "
            "SET allowed_extensions = :exts, max_file_size_mb = 10 "
            "WHERE code = 'portal_submission'"
        ),
        {"exts": ",".join(remaining)},
    )
