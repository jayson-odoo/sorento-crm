"""Seed the Shipment Line Photo attachment type (R25, section 12, purchasing
consolidation batch, lane C, slice C3, review round 1 item 3).

Photos on a shipment line file as this type - see
``app.services.scm.shipment_line_photos``'s module docstring for why the lookup
still tolerates an admin later renaming/re-coding the row, but no longer depends on
one existing at all: unlike ``packing_list_service``'s own "Packing List" type
(best-effort filing on an apply that succeeds either way), this endpoint has no
fallback - filing the photo IS the point of it, so a fresh deploy with nobody having
created the row first would 400 on the very first upload.

Idempotent update-or-insert by code, mirroring
``021_add_attachment_type_code_and_complaint_document.py`` /
``308_requestor_uploader_attr.py``'s own seed.

Revision ID: 485_shipment_line_photo_type
Revises: 484_translation_memory
"""
from alembic import op
from sqlalchemy import text

revision = "485_shipment_line_photo_type"
down_revision = "484_translation_memory"
branch_labels = None
depends_on = None

_CODE = "shipment_line_photo"
_NAME = "Shipment Line Photo"
_EXTENSIONS = "jpg,jpeg,png,webp,gif"
_MAX_FILE_SIZE_MB = 10


def upgrade() -> None:
    op.execute(
        text(
            "UPDATE attachment_types SET code = :code "
            "WHERE type_name = :name AND (code IS NULL OR code != :code)"
        ).bindparams(code=_CODE, name=_NAME)
    )
    op.execute(
        text(
            "INSERT INTO attachment_types "
            "(id, code, type_name, allowed_extensions, max_file_size_mb, "
            "triggers_n8n_webhook, created_at) "
            "SELECT gen_random_uuid(), :code, :name, :extensions, :max_mb, false, now() "
            "WHERE NOT EXISTS (SELECT 1 FROM attachment_types WHERE code = :code)"
        ).bindparams(
            code=_CODE, name=_NAME, extensions=_EXTENSIONS, max_mb=_MAX_FILE_SIZE_MB
        )
    )


def downgrade() -> None:
    op.execute(
        text("DELETE FROM attachment_types WHERE code = :code").bindparams(code=_CODE)
    )
