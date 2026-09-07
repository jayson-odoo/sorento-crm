"""Seed the Shipment Line Photo, Proforma Invoice and Packing List attachment types
(R25, section 12, purchasing consolidation batch, lane C, slice C3, review round 1
item 3; browser-test round finding 3 adds the latter two to this same, still
unreleased migration - see the plan's ``## Deviations (lane C)``).

Photos on a shipment line file as Shipment Line Photo - see
``app.services.scm.shipment_line_photos``'s module docstring for why the lookup
still tolerates an admin later renaming/re-coding the row, but no longer depends on
one existing at all: unlike ``packing_list_service``'s own "Packing List" type
(best-effort filing on an apply that succeeds either way), this endpoint has no
fallback - filing the photo IS the point of it, so a fresh deploy with nobody having
created the row first would 400 on the very first upload.

Proforma Invoice and Packing List did not exist at all before this round: a proforma
invoice uploaded through the supplier-documents dialog was never filed in Drive
because ``supplier_document_service``'s own lookup (``code = 'proforma_invoice' OR
lower(type_name) = 'proforma invoice'``) found nothing. Packing List is admin data
that already exists in the shared dev database (R4's own note), so its seed only
ever UPDATEs that row's `code` column - the INSERT branch is dead there and exists
for a genuinely empty database (CI, a fresh install).

Idempotent update-or-insert by code, per type, mirroring
``021_add_attachment_type_code_and_complaint_document.py`` /
``308_requestor_uploader_attr.py``'s own seed. `triggers_n8n_webhook` is left alone
on an UPDATE (an admin's own choice on a pre-existing row) and hardcoded `false` only
on an INSERT (this batch's own reader already produced whatever the file describes;
firing the webhook would create a second one through the external route, R3/R12).

Revision ID: 485_shipment_line_photo_type
Revises: 484_translation_memory
"""
from alembic import op
from sqlalchemy import text

revision = "485_shipment_line_photo_type"
down_revision = "484_translation_memory"
branch_labels = None
depends_on = None

#: (code, type_name, allowed_extensions, max_file_size_mb) - one row per type this
#: migration seeds. The order matches this docstring's own account of why each is here.
_TYPES = (
    ("shipment_line_photo", "Shipment Line Photo", "jpg,jpeg,png,webp,gif", 10),
    ("proforma_invoice", "Proforma Invoice", "xlsx,xls,pdf", 10),
    ("packing_list", "Packing List", "xlsx,xls,pdf", 10),
)


def upgrade() -> None:
    for code, name, extensions, max_mb in _TYPES:
        op.execute(
            text(
                "UPDATE attachment_types SET code = :code "
                "WHERE type_name = :name AND (code IS NULL OR code != :code)"
            ).bindparams(code=code, name=name)
        )
        op.execute(
            text(
                "INSERT INTO attachment_types "
                "(id, code, type_name, allowed_extensions, max_file_size_mb, "
                "triggers_n8n_webhook, created_at) "
                "SELECT gen_random_uuid(), :code, :name, :extensions, :max_mb, false, now() "
                "WHERE NOT EXISTS (SELECT 1 FROM attachment_types WHERE code = :code)"
            ).bindparams(code=code, name=name, extensions=extensions, max_mb=max_mb)
        )


def downgrade() -> None:
    # Shipment Line Photo and Proforma Invoice are rows THIS migration mints fresh in
    # any database that reaches head - safe to delete outright. Packing List is not:
    # the shared dev database already carries that row as real admin data (R4), and
    # this migration only ever sets its `code` column, so downgrading clears the code
    # rather than deleting a row this migration never created.
    op.execute(
        text(
            "DELETE FROM attachment_types WHERE code IN ('shipment_line_photo', 'proforma_invoice')"
        )
    )
    op.execute(
        text(
            "UPDATE attachment_types SET code = NULL "
            "WHERE code = 'packing_list' AND type_name = 'Packing List'"
        )
    )
