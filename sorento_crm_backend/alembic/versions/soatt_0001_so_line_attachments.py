"""Sales-order-line attachments on the OI handover email (#1312,
PLAN-oi-line-attachments-27sep.md, AC-E7).

Two independent, idempotent edits:

1. Seeds the "Sales Order Line Attachment" attachment type (code
   ``so_line_attachment``, jpg/jpeg/png/webp/gif/pdf/xlsx/xls, 10 MB) - same
   idempotent INSERT-WHERE-NOT-EXISTS shape ``485_shipment_line_photo_type`` uses for
   its own seeded types.
2. Edits the handover template (``email_templates.code = 'order_inquiry_handover_
   default'``) IN PLACE, anchored on the remark cell's own Jinja token
   (``{{ line.remark | default("", true) }}``, present once in ``body_html`` inside a
   ``<td>`` and once in ``body_text`` at the end of the line's row) rather than
   swapping the whole body the way ``oihr_0001``/``oihr_0003`` do - this migration
   only ever ADDS a fragment after that token, so a byte-for-byte "restore the
   previous body" constant would have nothing to restore FROM once a later migration
   changes the surrounding body again. Detected via `_MARKER` (unique to this
   fragment, so a re-run is a no-op); a template whose anchor is gone (an admin
   reshaped it) is left alone and logged, never guessed at.

Downgrade strips exactly the inserted fragment (a plain string removal, the exact
literal this migration inserted) and deletes the seeded type row only when nothing
uses it. No `alembic_version` touch, no edit of any migration main already carries.

Revision ID: soatt_0001_so_line_attachments
Revises: merge_28sep_esc_fin
Create Date: 2026-09-27
"""
from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = "soatt_0001_so_line_attachments"
down_revision = "merge_28sep_esc_fin"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

TEMPLATE_CODE = "order_inquiry_handover_default"
TYPE_CODE = "so_line_attachment"
TYPE_NAME = "Sales Order Line Attachment"
TYPE_EXTENSIONS = "jpg,jpeg,png,webp,gif,pdf,xlsx,xls"
TYPE_MAX_MB = 10

#: The remark cell's own Jinja token - present once in each body today
#: (`oihr_0003_location_column`'s own `_BODY_HTML`/`_BODY_TEXT`).
_ANCHOR = '{{ line.remark | default("", true) }}'

#: Unique to this fragment - its presence in a body is the idempotency check, and its
#: absence in a body that HAS `_ANCHOR` is what upgrade inserts.
_MARKER = "{% if line.attachments %}"

_HTML_FRAGMENT = (
    "{% if line.attachments %}<br>Attachments: "
    "{% for a in line.attachments %}{% if not loop.first %}, {% endif %}"
    "{% if a.attached %}{{ a.name }}{% else %}"
    '<a href="{{ a.url }}">{{ a.name }}</a> (not attached, too large for email)'
    "{% endif %}{% endfor %}{% endif %}"
)

_TEXT_FRAGMENT = (
    "{% if line.attachments %} / Attachments: "
    "{% for a in line.attachments %}{% if not loop.first %}, {% endif %}"
    "{% if a.attached %}{{ a.name }}{% else %}"
    "{{ a.name }} ({{ a.url }}) (not attached, too large for email)"
    "{% endif %}{% endfor %}{% endif %}"
)


def _insert_fragment(body: str, fragment: str) -> tuple[str, bool]:
    """`(new_body, changed)`. Idempotent (the marker already present is a no-op);
    logs and leaves the body untouched when the anchor itself is gone."""
    if not body:
        return body, False
    if _MARKER in body:
        return body, False
    if _ANCHOR not in body:
        logger.warning(
            "soatt_0001_so_line_attachments: the handover template's remark-cell "
            "anchor is gone (reshaped since oihr_0003) - leaving it alone."
        )
        return body, False
    return body.replace(_ANCHOR, _ANCHOR + fragment, 1), True


def upgrade() -> None:
    bind = op.get_bind()

    row = bind.execute(
        sa.text("SELECT body_html, body_text FROM email_templates WHERE code = :code"),
        {"code": TEMPLATE_CODE},
    ).first()
    if row is not None:
        new_html, html_changed = _insert_fragment(row[0] or "", _HTML_FRAGMENT)
        new_text, text_changed = _insert_fragment(row[1] or "", _TEXT_FRAGMENT)
        if html_changed or text_changed:
            bind.execute(
                sa.text(
                    "UPDATE email_templates SET body_html = :h, body_text = :t "
                    "WHERE code = :code"
                ),
                {"h": new_html, "t": new_text, "code": TEMPLATE_CODE},
            )

    bind.execute(
        sa.text(
            "INSERT INTO attachment_types "
            "(id, code, type_name, allowed_extensions, max_file_size_mb, "
            "triggers_n8n_webhook, created_at) "
            "SELECT gen_random_uuid(), :code, :name, :extensions, :max_mb, false, now() "
            "WHERE NOT EXISTS (SELECT 1 FROM attachment_types WHERE code = :code)"
        ).bindparams(code=TYPE_CODE, name=TYPE_NAME, extensions=TYPE_EXTENSIONS, max_mb=TYPE_MAX_MB)
    )


def downgrade() -> None:
    bind = op.get_bind()

    row = bind.execute(
        sa.text("SELECT body_html, body_text FROM email_templates WHERE code = :code"),
        {"code": TEMPLATE_CODE},
    ).first()
    if row is not None:
        body_html, body_text = row[0] or "", row[1] or ""
        new_html = body_html.replace(_HTML_FRAGMENT, "", 1)
        new_text = body_text.replace(_TEXT_FRAGMENT, "", 1)
        if new_html != body_html or new_text != body_text:
            bind.execute(
                sa.text(
                    "UPDATE email_templates SET body_html = :h, body_text = :t "
                    "WHERE code = :code"
                ),
                {"h": new_html, "t": new_text, "code": TEMPLATE_CODE},
            )

    # Only when nothing uses it (module docstring) - a downgrade must not orphan a
    # real upload's own `attachment_type_id`.
    bind.execute(
        sa.text(
            "DELETE FROM attachment_types WHERE code = :code AND NOT EXISTS "
            "(SELECT 1 FROM attachments WHERE attachment_type_id = attachment_types.id)"
        ).bindparams(code=TYPE_CODE)
    )
