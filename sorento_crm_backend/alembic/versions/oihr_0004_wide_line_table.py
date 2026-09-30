"""Order inquiry handover email on the WIDE shell, with a line table whose dates and
quantities never wrap (EMAIL-HANDOVER-QTY, PR #1392,
`PLAN-oi-handover-qty-change-30sep.md` S3, AC-11 to AC-13).

Owner (30 Sep): "i think this email template is too narrow already, the words are
cramped". The nine-column line table shared about 520px inside the 600px card
(`base.html`) with 40px gutters (`layout.html`); `EmailDocument.width = "wide"`
(`app/services/email_layout.py`) now renders a 900px card with 24px gutters, and this
migration puts the handover template on it.

Updates ``email_templates`` (``code`` = ``TEMPLATE_CODE`` below) IN PLACE, but only
while its ``layout_json`` is still the document `eml_0002_seed_layouts` seeded (that
migration's own guard): the template has been admin-editable in the block editor since
#1349, and a document an admin arranged - or a row eml_0002 left NULL because its body
had been edited - is theirs and is left alone. On the seeded row ``layout_json`` becomes
`eml_0002_seed_layouts`' handover document with ``width: "wide"`` and the custom text's
line table carrying per-column widths, ``white-space:nowrap`` on every cell but REMARK,
and 6px 8px cell padding (an authored ``style`` wins over ``email_layout.inline_defaults``,
so the shell's own 8px 10px default steps aside); ``body_html`` becomes the mirror of
the custom text blocks (#1349 D3, what `EmailTemplateService.update` keeps it equal
to); ``body_text``, the hand-tuned pipe table, is untouched. The subject is untouched.
A database with no row yet gets one inserted in this shape, with the text part as
`oihr_0003` + `soatt_0001` left it. Idempotent: the same row both times.

Downgrade restores ``layout_json`` and ``body_html`` byte for byte to what the chain
`oihr_0003` -> `soatt_0001` -> `eml_0002` leaves them (frozen copies below, read off a
replay of that chain, never re-derived) - so a rollback returns exactly the strings a
database on that revision shows.

Revision ID: oihr_0004_wide_line_table
Revises: sdn_0001_so_debtor_name
Create Date: 2026-09-30
"""
from __future__ import annotations

import json
import logging

import sqlalchemy as sa
from alembic import op


logger = logging.getLogger("alembic.runtime.migration")

revision = "oihr_0004_wide_line_table"
down_revision = "sdn_0001_so_debtor_name"
branch_labels = None
depends_on = None


# Split, not a literal (same reasoning `oihr_0001_handover_r2_layout` gives): several OI
# tests find THEIR seed migration by scanning alembic/versions for the full code as one
# contiguous token, and this file must not be a second match.
TEMPLATE_CODE = "order_inquiry_handover" + "_default"

_SUBJECT = "OI: {{ handover.subject_scope }}"


def _mirror(layout: dict) -> str:
    """`email_template_service._mirror_body_html`, restated here so a migration never
    imports app code that keeps changing."""
    return "\n".join(
        b["html"] for b in layout["blocks"] if b["type"] == "custom_text" and b.get("html")
    )


# --------------------------------------------------------------------------- #
# The WIDE document: eml_0002's handover document, width "wide", line table   #
# with column widths + nowrap. What upgrade writes.                            #
# --------------------------------------------------------------------------- #

_WIDE_LAYOUT = json.loads(r'''{
 "blocks": [
  {
   "type": "brand_header"
  },
  {
   "text": "{{ handover.headline }}",
   "type": "heading"
  },
  {
   "html": "<table width=\"100%\">\n  <thead>\n    <tr><th style=\"padding:6px 8px;\">S/O NO</th><th style=\"padding:6px 8px;\">CUSTOMER</th><th style=\"padding:6px 8px;\">PROJECT</th></tr>\n  </thead>\n  <tbody>\n    {% for order in handover.orders %}\n    <tr>\n      <td style=\"padding:6px 8px;\">{{ order.so_number | default(\"\", true) }}</td>\n      <td style=\"padding:6px 8px;\">{{ order.customer | default(\"\", true) }}</td>\n      <td style=\"padding:6px 8px;\">{{ order.project | default(\"\", true) }}</td>\n    </tr>\n    {% endfor %}\n  </tbody>\n</table>\n{%- set cols = namespace(qty=false, delivery_date=false) -%}{%- for line in handover.lines -%}{%- if line.was and line.was.qty %}{% set cols.qty = true %}{% endif -%}{%- if line.was and line.was.delivery_date %}{% set cols.delivery_date = true %}{% endif -%}{%- endfor -%}<table width=\"100%\">\n  <thead>\n    <tr>\n      <th style=\"width:86px;padding:6px 8px;\">SO DATE</th><th style=\"width:82px;padding:6px 8px;\">S/O NO</th><th style=\"width:92px;padding:6px 8px;\">LOCATION</th><th style=\"width:140px;padding:6px 8px;\">ITEM CODE</th>\n      <th style=\"width:56px;padding:6px 8px;\">QTY</th>{% if cols.qty %}<th style=\"width:72px;padding:6px 8px;\">QTY CHANGE TO</th>{% endif %}\n      <th style=\"width:92px;padding:6px 8px;\">DELIVERY DATE</th>{% if cols.delivery_date %}<th style=\"width:92px;padding:6px 8px;\">DELIVERY DATE CHANGE TO</th>{% endif %}\n      <th style=\"padding:6px 8px;\">REMARK</th>\n    </tr>\n  </thead>\n  <tbody>\n    {% for line in handover.lines %}\n    <tr>\n      <td style=\"white-space:nowrap;padding:6px 8px;\">{{ line.so_date | default(\"\", true) }}</td>\n      <td style=\"white-space:nowrap;padding:6px 8px;\">{{ line.so_number | default(\"\", true) }}</td>\n      <td style=\"white-space:nowrap;padding:6px 8px;\">{{ line.location | default(\"\", true) }}</td>\n      <td style=\"white-space:nowrap;padding:6px 8px;\">{{ line.item_code | default(\"\", true) }}</td>\n      <td style=\"white-space:nowrap;padding:6px 8px;\">{% if line.was and line.was.qty %}{{ line.was.qty }}{% else %}{{ line.qty | default(\"\", true) }}{% endif %}</td>\n      {% if cols.qty %}<td style=\"white-space:nowrap;padding:6px 8px;\">{% if line.was and line.was.qty %}{{ line.qty | default(\"\", true) }}{% endif %}</td>{% endif %}\n      <td style=\"white-space:nowrap;padding:6px 8px;\">{% if line.was and line.was.delivery_date %}{{ line.was.delivery_date }}{% else %}{{ line.delivery_date | default(\"\", true) }}{% endif %}</td>\n      {% if cols.delivery_date %}<td style=\"white-space:nowrap;padding:6px 8px;\">{% if line.was and line.was.delivery_date %}{{ line.delivery_date | default(\"\", true) }}{% endif %}</td>{% endif %}\n      <td style=\"padding:6px 8px;\">{{ line.remark | default(\"\", true) }}{% if line.attachments %}<br>Attachments: {% for a in line.attachments %}{% if not loop.first %}, {% endif %}{% if a.attached %}{{ a.name }}{% else %}<a href=\"{{ a.url }}\">{{ a.name }}</a> (not attached, too large for email){% endif %}{% endfor %}{% endif %}</td>\n    </tr>\n    {% endfor %}\n  </tbody>\n</table>\n<p>Raised by {{ actor.name if actor else '-' }}{% if actor %} ({{ actor.email }}){% endif %} on {{ today }}.</p>",
   "type": "custom_text"
  },
  {
   "url": "{{ handover.link }}",
   "type": "button",
   "label": "Open in Order Inquiries"
  },
  {
   "type": "footer"
  }
 ],
 "version": 1,
 "width": "wide"
}''')

_WIDE_BODY_HTML = _mirror(_WIDE_LAYOUT)


# --------------------------------------------------------------------------- #
# Frozen copies of the PRE-migration row, byte for byte - what downgrade      #
# restores and what the insert path uses for the text part. Never edit these  #
# to "fix" them; a fix has nothing left to ship it against once this revision #
# is live.                                                                     #
# --------------------------------------------------------------------------- #

#: `eml_0002_seed_layouts`' handover document (no width key: the standard shell).
_PRIOR_LAYOUT = json.loads(r'''{
 "blocks": [
  {
   "type": "brand_header"
  },
  {
   "text": "{{ handover.headline }}",
   "type": "heading"
  },
  {
   "html": "<table width=\"100%\">\n  <thead>\n    <tr><th>S/O NO</th><th>CUSTOMER</th><th>PROJECT</th></tr>\n  </thead>\n  <tbody>\n    {% for order in handover.orders %}\n    <tr>\n      <td>{{ order.so_number | default(\"\", true) }}</td>\n      <td>{{ order.customer | default(\"\", true) }}</td>\n      <td>{{ order.project | default(\"\", true) }}</td>\n    </tr>\n    {% endfor %}\n  </tbody>\n</table>\n{%- set cols = namespace(qty=false, delivery_date=false) -%}{%- for line in handover.lines -%}{%- if line.was and line.was.qty %}{% set cols.qty = true %}{% endif -%}{%- if line.was and line.was.delivery_date %}{% set cols.delivery_date = true %}{% endif -%}{%- endfor -%}<table width=\"100%\">\n  <thead>\n    <tr>\n      <th>SO DATE</th><th>S/O NO</th><th>LOCATION</th><th>ITEM CODE</th>\n      <th>QTY</th>{% if cols.qty %}<th>QTY CHANGE TO</th>{% endif %}\n      <th>DELIVERY DATE</th>{% if cols.delivery_date %}<th>DELIVERY DATE CHANGE TO</th>{% endif %}\n      <th>REMARK</th>\n    </tr>\n  </thead>\n  <tbody>\n    {% for line in handover.lines %}\n    <tr>\n      <td>{{ line.so_date | default(\"\", true) }}</td>\n      <td>{{ line.so_number | default(\"\", true) }}</td>\n      <td>{{ line.location | default(\"\", true) }}</td>\n      <td>{{ line.item_code | default(\"\", true) }}</td>\n      <td>{% if line.was and line.was.qty %}{{ line.was.qty }}{% else %}{{ line.qty | default(\"\", true) }}{% endif %}</td>\n      {% if cols.qty %}<td>{% if line.was and line.was.qty %}{{ line.qty | default(\"\", true) }}{% endif %}</td>{% endif %}\n      <td>{% if line.was and line.was.delivery_date %}{{ line.was.delivery_date }}{% else %}{{ line.delivery_date | default(\"\", true) }}{% endif %}</td>\n      {% if cols.delivery_date %}<td>{% if line.was and line.was.delivery_date %}{{ line.delivery_date | default(\"\", true) }}{% endif %}</td>{% endif %}\n      <td>{{ line.remark | default(\"\", true) }}{% if line.attachments %}<br>Attachments: {% for a in line.attachments %}{% if not loop.first %}, {% endif %}{% if a.attached %}{{ a.name }}{% else %}<a href=\"{{ a.url }}\">{{ a.name }}</a> (not attached, too large for email){% endif %}{% endfor %}{% endif %}</td>\n    </tr>\n    {% endfor %}\n  </tbody>\n</table>\n<p>Raised by {{ actor.name if actor else '-' }}{% if actor %} ({{ actor.email }}){% endif %} on {{ today }}.</p>",
   "type": "custom_text"
  },
  {
   "url": "{{ handover.link }}",
   "type": "button",
   "label": "Open in Order Inquiries"
  },
  {
   "type": "footer"
  }
 ],
 "version": 1
}''')

#: `oihr_0003_location_column`'s body with `soatt_0001`'s attachment fragment.
_PRIOR_BODY_HTML = '<p style="color:#b91c1c;font-weight:bold;">{{ handover.headline }}</p>\n<table style="border-collapse:collapse;font-family:Arial, sans-serif;font-size:13px;">\n  <thead>\n    <tr><th style="border:1px solid #d0d0d5;padding:4px 8px;background:#f2f2f5;text-align:left;">S/O NO</th><th style="border:1px solid #d0d0d5;padding:4px 8px;background:#f2f2f5;text-align:left;">CUSTOMER</th><th style="border:1px solid #d0d0d5;padding:4px 8px;background:#f2f2f5;text-align:left;">PROJECT</th></tr>\n  </thead>\n  <tbody>\n    {% for order in handover.orders %}\n    <tr>\n      <td style="border:1px solid #d0d0d5;padding:4px 8px;">{{ order.so_number | default("", true) }}</td>\n      <td style="border:1px solid #d0d0d5;padding:4px 8px;">{{ order.customer | default("", true) }}</td>\n      <td style="border:1px solid #d0d0d5;padding:4px 8px;">{{ order.project | default("", true) }}</td>\n    </tr>\n    {% endfor %}\n  </tbody>\n</table>\n{%- set cols = namespace(qty=false, delivery_date=false) -%}{%- for line in handover.lines -%}{%- if line.was and line.was.qty %}{% set cols.qty = true %}{% endif -%}{%- if line.was and line.was.delivery_date %}{% set cols.delivery_date = true %}{% endif -%}{%- endfor -%}<table style="border-collapse:collapse;font-family:Arial, sans-serif;font-size:13px;margin-top:12px;">\n  <thead>\n    <tr>\n      <th style="border:1px solid #d0d0d5;padding:4px 8px;background:#f2f2f5;text-align:left;">SO DATE</th><th style="border:1px solid #d0d0d5;padding:4px 8px;background:#f2f2f5;text-align:left;">S/O NO</th><th style="border:1px solid #d0d0d5;padding:4px 8px;background:#f2f2f5;text-align:left;">LOCATION</th><th style="border:1px solid #d0d0d5;padding:4px 8px;background:#f2f2f5;text-align:left;">ITEM CODE</th>\n      <th style="border:1px solid #d0d0d5;padding:4px 8px;background:#f2f2f5;text-align:left;">QTY</th>{% if cols.qty %}<th style="border:1px solid #d0d0d5;padding:4px 8px;background:#f2f2f5;text-align:left;">QTY CHANGE TO</th>{% endif %}\n      <th style="border:1px solid #d0d0d5;padding:4px 8px;background:#f2f2f5;text-align:left;">DELIVERY DATE</th>{% if cols.delivery_date %}<th style="border:1px solid #d0d0d5;padding:4px 8px;background:#f2f2f5;text-align:left;">DELIVERY DATE CHANGE TO</th>{% endif %}\n      <th style="border:1px solid #d0d0d5;padding:4px 8px;background:#f2f2f5;text-align:left;">REMARK</th>\n    </tr>\n  </thead>\n  <tbody>\n    {% for line in handover.lines %}\n    <tr>\n      <td style="border:1px solid #d0d0d5;padding:4px 8px;">{{ line.so_date | default("", true) }}</td>\n      <td style="border:1px solid #d0d0d5;padding:4px 8px;">{{ line.so_number | default("", true) }}</td>\n      <td style="border:1px solid #d0d0d5;padding:4px 8px;">{{ line.location | default("", true) }}</td>\n      <td style="border:1px solid #d0d0d5;padding:4px 8px;">{{ line.item_code | default("", true) }}</td>\n      <td style="border:1px solid #d0d0d5;padding:4px 8px;">{% if line.was and line.was.qty %}{{ line.was.qty }}{% else %}{{ line.qty | default("", true) }}{% endif %}</td>\n      {% if cols.qty %}<td style="border:1px solid #d0d0d5;padding:4px 8px;">{% if line.was and line.was.qty %}{{ line.qty | default("", true) }}{% endif %}</td>{% endif %}\n      <td style="border:1px solid #d0d0d5;padding:4px 8px;">{% if line.was and line.was.delivery_date %}{{ line.was.delivery_date }}{% else %}{{ line.delivery_date | default("", true) }}{% endif %}</td>\n      {% if cols.delivery_date %}<td style="border:1px solid #d0d0d5;padding:4px 8px;">{% if line.was and line.was.delivery_date %}{{ line.delivery_date | default("", true) }}{% endif %}</td>{% endif %}\n      <td style="border:1px solid #d0d0d5;padding:4px 8px;">{{ line.remark | default("", true) }}{% if line.attachments %}<br>Attachments: {% for a in line.attachments %}{% if not loop.first %}, {% endif %}{% if a.attached %}{{ a.name }}{% else %}<a href="{{ a.url }}">{{ a.name }}</a> (not attached, too large for email){% endif %}{% endfor %}{% endif %}</td>\n    </tr>\n    {% endfor %}\n  </tbody>\n</table>\n<p>Raised by {{ actor.name if actor else \'-\' }}{% if actor %} ({{ actor.email }}){% endif %} on {{ today }}.</p>\n<p><a href="{{ handover.link }}">Open in Order Inquiries</a></p>\n'

#: The hand-tuned plain-text part, same two migrations - untouched by upgrade.
_BODY_TEXT = '{%- set cols = namespace(qty=false, delivery_date=false) -%}{%- for line in handover.lines -%}{%- if line.was and line.was.qty %}{% set cols.qty = true %}{% endif -%}{%- if line.was and line.was.delivery_date %}{% set cols.delivery_date = true %}{% endif -%}{%- endfor -%}{{ handover.headline }}\n\n{% for order in handover.orders %}{{ order.so_number | default("", true) }}{% if order.customer %} - {{ order.customer }}{% endif %}{% if order.project %} - {{ order.project }}{% endif %}\n{% endfor %}\nSO DATE | S/O NO | LOCATION | ITEM CODE | QTY |{% if cols.qty %} QTY CHANGE TO |{% endif %} DELIVERY DATE |{% if cols.delivery_date %} DELIVERY DATE CHANGE TO |{% endif %} REMARK\n{% for line in handover.lines %}{{ line.so_date | default("", true) }} | {{ line.so_number | default("", true) }} | {{ line.location | default("", true) }} | {{ line.item_code | default("", true) }} | {% if line.was and line.was.qty %}{{ line.was.qty }}{% else %}{{ line.qty | default("", true) }}{% endif %} |{% if cols.qty %} {% if line.was and line.was.qty %}{{ line.qty | default("", true) }}{% endif %} |{% endif %} {% if line.was and line.was.delivery_date %}{{ line.was.delivery_date }}{% else %}{{ line.delivery_date | default("", true) }}{% endif %} |{% if cols.delivery_date %} {% if line.was and line.was.delivery_date %}{{ line.delivery_date | default("", true) }}{% endif %} |{% endif %} {{ line.remark | default("", true) }}{% if line.attachments %} / Attachments: {% for a in line.attachments %}{% if not loop.first %}, {% endif %}{% if a.attached %}{{ a.name }}{% else %}{{ a.name }} ({{ a.url }}) (not attached, too large for email){% endif %}{% endfor %}{% endif %}\n{% endfor %}\nRaised by {{ actor.name if actor else \'-\' }} on {{ today }}.\nOpen: {{ handover.link }}\n'


def _set(bind, *, layout: dict, body_html: str, only_when: list, direction: str) -> None:
    """Update the row only while its document is still one of `only_when` (the eml_0002
    guard, `eml_0002_seed_layouts._convert`'s own rule): a document an admin has since
    arranged in the block editor, or a row eml_0002 left with NULL `layout_json` because
    its body had been edited, is theirs and is left alone - and the skip is LOGGED (review
    round 1), so a release can see the row was not converted. Insert when no row exists."""
    existing = bind.execute(
        sa.text("SELECT id, layout_json FROM email_templates WHERE code = :code"),
        {"code": TEMPLATE_CODE},
    ).first()
    if existing:
        touched = 0
        for candidate in only_when:
            touched += bind.execute(
                sa.text(
                    """
                    UPDATE email_templates
                    SET layout_json = CAST(:layout AS jsonb), body_html = :body_html
                    WHERE code = :code AND layout_json = CAST(:only_when AS jsonb)
                    """
                ),
                {
                    "code": TEMPLATE_CODE,
                    "layout": json.dumps(layout),
                    "body_html": body_html,
                    "only_when": json.dumps(candidate),
                },
            ).rowcount
            if touched:
                break
        if not touched:
            logger.warning(
                "oihr_0004 %s: email_templates row %s carries a document this migration "
                "did not write (admin-edited, or eml_0002 left it NULL); left untouched.",
                direction,
                TEMPLATE_CODE,
            )
        return
    bind.execute(
        sa.text(
            """
            INSERT INTO email_templates
                (id, code, name, description, subject, body_html, body_text, layout_json, is_active)
            VALUES
                (gen_random_uuid(), :code, :name, :description, :subject, :body_html,
                 :body_text, CAST(:layout AS jsonb), true)
            """
        ),
        {
            "code": TEMPLATE_CODE,
            "name": "Order Inquiry Handover to Purchasing (default)",
            "description": (
                "Shaped like the manual handover mail CS sends purchasing: SO table, "
                "line table (with the stock location per line), QTY/DELIVERY DATE and "
                "their own CHANGE TO columns, on the wide email shell."
            ),
            "subject": _SUBJECT,
            "body_html": body_html,
            "body_text": _BODY_TEXT,
            "layout": json.dumps(layout),
        },
    )


def upgrade() -> None:
    # The seeded document as eml_0002 wrote it, and the SAME document as the block
    # editor re-saves it once `EmailDocument.width` exists (`model_dump` adds
    # `"width": "standard"` to an unchanged arrangement) - both are still ours.
    _set(
        op.get_bind(),
        layout=_WIDE_LAYOUT,
        body_html=_WIDE_BODY_HTML,
        only_when=[_PRIOR_LAYOUT, {**_PRIOR_LAYOUT, "width": "standard"}],
        direction="upgrade",
    )


def downgrade() -> None:
    _set(
        op.get_bind(),
        layout=_PRIOR_LAYOUT,
        body_html=_PRIOR_BODY_HTML,
        only_when=[_WIDE_LAYOUT],
        direction="downgrade",
    )
