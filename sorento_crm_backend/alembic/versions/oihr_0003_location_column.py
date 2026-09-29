"""Order inquiry handover email: print the stock LOCATION per line, right after
S/O NO (`PLAN-oi-handover-email-location-and-line-order-24sep.md`, AC-1, issue #1166).

`_record_handover` (`project_order_inquiry_service.py`) has carried `row.stock_location`
onto the per-line dispatch context (`line.location`, blank when the row carries none)
since this lane, but the r2 SEEDED template (`oihr_0001_handover_r2_layout`) never
printed it - only the SUBJECT's one-distinct-location reduction read it. The owner:
the location per line is "very, very important" to purchasing, who cannot act on a
handover naming six lines and one warehouse without knowing which line is which.

Updates ``email_templates`` (same ``code`` as ``TEMPLATE_CODE`` below) IN PLACE, same
reasoning `oihr_0002_undone_headline` gives for its own update: the r2 line table's own
columns become ``SO DATE | S/O NO | LOCATION | ITEM CODE | QTY | QTY CHANGE TO |
DELIVERY DATE | DELIVERY DATE CHANGE TO | REMARK`` - LOCATION inserted right after S/O
NO, everything else (including AC-R2-18's per-email CHANGE TO column visibility)
unchanged. The SO summary table above the line table, and the subject line, are both
untouched - AC-4, the subject's one-distinct-location rule already lives in
`_build_handover_context`, not the template.

An UPDATE, not a skip-if-exists insert: the row already exists on every DB that ran
`oihr_0001`, and the point of this migration is to deliver a fix to its body. A DB with
no row yet (a fresh schema, or one stamped past `oihe_0001` without ever running it)
gets one inserted directly in the r2+location shape - AC-R2-18's `_COLUMNS_IN_USE`
preamble is copied byte for byte from `oihr_0001_handover_r2_layout`, LOCATION is not
conditional on anything. Idempotent: running twice sets the same subject/body_html/
body_text both times. The automation row and its recipients are untouched.

Downgrade restores the r2 body verbatim (copied from `oihr_0001_handover_r2_layout.py`
byte for byte, not re-derived), so a rollback returns the exact string a DB on that
revision would show.

Revision ID: oihr_0003_location_column
Revises: oirs_0004_reserve_event_zero
Create Date: 2026-09-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "oihr_0003_location_column"
down_revision = "oirs_0004_reserve_event_zero"
branch_labels = None
depends_on = None


# Split, not a literal (same reasoning `oihr_0001_handover_r2_layout` gives for its own
# `TEMPLATE_CODE`): a naive `"order_inquiry_handover_default"` literal in THIS file's
# source would make `tests/test_order_inquiry_handover_automation.py::_find_seed_
# migration_path`'s content-sniff (which matches on the template code as one
# contiguous token) ambiguous between the r1 seed migration and this one.
TEMPLATE_CODE = "order_inquiry_handover" + "_default"

_SUBJECT = "OI: {{ handover.subject_scope }}"

# Copied byte for byte from `oihr_0001_handover_r2_layout` - AC-R2-18's own preamble is
# unaffected by LOCATION, which carries no CHANGE TO column of its own.
_COLUMNS_IN_USE = (
    "{%- set cols = namespace(qty=false, delivery_date=false) -%}"
    "{%- for line in handover.lines -%}"
    "{%- if line.was and line.was.qty %}{% set cols.qty = true %}{% endif -%}"
    "{%- if line.was and line.was.delivery_date %}{% set cols.delivery_date = true %}{% endif -%}"
    "{%- endfor -%}"
)

_TH_STYLE = "border:1px solid #d0d0d5;padding:4px 8px;background:#f2f2f5;text-align:left;"
_TD_STYLE = "border:1px solid #d0d0d5;padding:4px 8px;"
_TABLE_STYLE = "border-collapse:collapse;font-family:Arial, sans-serif;font-size:13px;"

_BODY_HTML = """\
<p style="color:#b91c1c;font-weight:bold;">{{ handover.headline }}</p>
<table style="__TABLE_STYLE__">
  <thead>
    <tr><th style="__TH_STYLE__">S/O NO</th><th style="__TH_STYLE__">CUSTOMER</th><th style="__TH_STYLE__">PROJECT</th></tr>
  </thead>
  <tbody>
    {% for order in handover.orders %}
    <tr>
      <td style="__TD_STYLE__">{{ order.so_number | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ order.customer | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ order.project | default("", true) }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
__COLUMNS_IN_USE__<table style="__TABLE_STYLE__margin-top:12px;">
  <thead>
    <tr>
      <th style="__TH_STYLE__">SO DATE</th><th style="__TH_STYLE__">S/O NO</th><th style="__TH_STYLE__">LOCATION</th><th style="__TH_STYLE__">ITEM CODE</th>
      <th style="__TH_STYLE__">QTY</th>{% if cols.qty %}<th style="__TH_STYLE__">QTY CHANGE TO</th>{% endif %}
      <th style="__TH_STYLE__">DELIVERY DATE</th>{% if cols.delivery_date %}<th style="__TH_STYLE__">DELIVERY DATE CHANGE TO</th>{% endif %}
      <th style="__TH_STYLE__">REMARK</th>
    </tr>
  </thead>
  <tbody>
    {% for line in handover.lines %}
    <tr>
      <td style="__TD_STYLE__">{{ line.so_date | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ line.so_number | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ line.location | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ line.item_code | default("", true) }}</td>
      <td style="__TD_STYLE__">{% if line.was and line.was.qty %}{{ line.was.qty }}{% else %}{{ line.qty | default("", true) }}{% endif %}</td>
      {% if cols.qty %}<td style="__TD_STYLE__">{% if line.was and line.was.qty %}{{ line.qty | default("", true) }}{% endif %}</td>{% endif %}
      <td style="__TD_STYLE__">{% if line.was and line.was.delivery_date %}{{ line.was.delivery_date }}{% else %}{{ line.delivery_date | default("", true) }}{% endif %}</td>
      {% if cols.delivery_date %}<td style="__TD_STYLE__">{% if line.was and line.was.delivery_date %}{{ line.delivery_date | default("", true) }}{% endif %}</td>{% endif %}
      <td style="__TD_STYLE__">{{ line.remark | default("", true) }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
<p>Raised by {{ actor.name if actor else '-' }}{% if actor %} ({{ actor.email }}){% endif %} on {{ today }}.</p>
<p><a href="{{ handover.link }}">Open in Order Inquiries</a></p>
""".replace("__TABLE_STYLE__", _TABLE_STYLE).replace("__TH_STYLE__", _TH_STYLE).replace(
    "__TD_STYLE__", _TD_STYLE
).replace("__COLUMNS_IN_USE__", _COLUMNS_IN_USE)

_BODY_TEXT = """\
__COLUMNS_IN_USE__{{ handover.headline }}

{% for order in handover.orders %}{{ order.so_number | default("", true) }}{% if order.customer %} - {{ order.customer }}{% endif %}{% if order.project %} - {{ order.project }}{% endif %}
{% endfor %}
SO DATE | S/O NO | LOCATION | ITEM CODE | QTY |{% if cols.qty %} QTY CHANGE TO |{% endif %} DELIVERY DATE |{% if cols.delivery_date %} DELIVERY DATE CHANGE TO |{% endif %} REMARK
{% for line in handover.lines %}{{ line.so_date | default("", true) }} | {{ line.so_number | default("", true) }} | {{ line.location | default("", true) }} | {{ line.item_code | default("", true) }} | {% if line.was and line.was.qty %}{{ line.was.qty }}{% else %}{{ line.qty | default("", true) }}{% endif %} |{% if cols.qty %} {% if line.was and line.was.qty %}{{ line.qty | default("", true) }}{% endif %} |{% endif %} {% if line.was and line.was.delivery_date %}{{ line.was.delivery_date }}{% else %}{{ line.delivery_date | default("", true) }}{% endif %} |{% if cols.delivery_date %} {% if line.was and line.was.delivery_date %}{{ line.delivery_date | default("", true) }}{% endif %} |{% endif %} {{ line.remark | default("", true) }}
{% endfor %}
Raised by {{ actor.name if actor else '-' }} on {{ today }}.
Open: {{ handover.link }}
""".replace("__COLUMNS_IN_USE__", _COLUMNS_IN_USE)


# --------------------------------------------------------------------------- #
# r2 body, copied byte for byte from oihr_0001_handover_r2_layout.py -        #
# what downgrade restores. Never edit this to "fix" it; a fix to the r2 body  #
# has nothing left to ship it against once this revision is live.            #
# --------------------------------------------------------------------------- #

_R2_BODY_HTML = """\
<p style="color:#b91c1c;font-weight:bold;">{{ handover.headline }}</p>
<table style="__TABLE_STYLE__">
  <thead>
    <tr><th style="__TH_STYLE__">S/O NO</th><th style="__TH_STYLE__">CUSTOMER</th><th style="__TH_STYLE__">PROJECT</th></tr>
  </thead>
  <tbody>
    {% for order in handover.orders %}
    <tr>
      <td style="__TD_STYLE__">{{ order.so_number | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ order.customer | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ order.project | default("", true) }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
__COLUMNS_IN_USE__<table style="__TABLE_STYLE__margin-top:12px;">
  <thead>
    <tr>
      <th style="__TH_STYLE__">SO DATE</th><th style="__TH_STYLE__">S/O NO</th><th style="__TH_STYLE__">ITEM CODE</th>
      <th style="__TH_STYLE__">QTY</th>{% if cols.qty %}<th style="__TH_STYLE__">QTY CHANGE TO</th>{% endif %}
      <th style="__TH_STYLE__">DELIVERY DATE</th>{% if cols.delivery_date %}<th style="__TH_STYLE__">DELIVERY DATE CHANGE TO</th>{% endif %}
      <th style="__TH_STYLE__">REMARK</th>
    </tr>
  </thead>
  <tbody>
    {% for line in handover.lines %}
    <tr>
      <td style="__TD_STYLE__">{{ line.so_date | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ line.so_number | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ line.item_code | default("", true) }}</td>
      <td style="__TD_STYLE__">{% if line.was and line.was.qty %}{{ line.was.qty }}{% else %}{{ line.qty | default("", true) }}{% endif %}</td>
      {% if cols.qty %}<td style="__TD_STYLE__">{% if line.was and line.was.qty %}{{ line.qty | default("", true) }}{% endif %}</td>{% endif %}
      <td style="__TD_STYLE__">{% if line.was and line.was.delivery_date %}{{ line.was.delivery_date }}{% else %}{{ line.delivery_date | default("", true) }}{% endif %}</td>
      {% if cols.delivery_date %}<td style="__TD_STYLE__">{% if line.was and line.was.delivery_date %}{{ line.delivery_date | default("", true) }}{% endif %}</td>{% endif %}
      <td style="__TD_STYLE__">{{ line.remark | default("", true) }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
<p>Raised by {{ actor.name if actor else '-' }}{% if actor %} ({{ actor.email }}){% endif %} on {{ today }}.</p>
<p><a href="{{ handover.link }}">Open in Order Inquiries</a></p>
""".replace("__TABLE_STYLE__", _TABLE_STYLE).replace("__TH_STYLE__", _TH_STYLE).replace(
    "__TD_STYLE__", _TD_STYLE
).replace("__COLUMNS_IN_USE__", _COLUMNS_IN_USE)

_R2_BODY_TEXT = """\
__COLUMNS_IN_USE__{{ handover.headline }}

{% for order in handover.orders %}{{ order.so_number | default("", true) }}{% if order.customer %} - {{ order.customer }}{% endif %}{% if order.project %} - {{ order.project }}{% endif %}
{% endfor %}
SO DATE | S/O NO | ITEM CODE | QTY |{% if cols.qty %} QTY CHANGE TO |{% endif %} DELIVERY DATE |{% if cols.delivery_date %} DELIVERY DATE CHANGE TO |{% endif %} REMARK
{% for line in handover.lines %}{{ line.so_date | default("", true) }} | {{ line.so_number | default("", true) }} | {{ line.item_code | default("", true) }} | {% if line.was and line.was.qty %}{{ line.was.qty }}{% else %}{{ line.qty | default("", true) }}{% endif %} |{% if cols.qty %} {% if line.was and line.was.qty %}{{ line.qty | default("", true) }}{% endif %} |{% endif %} {% if line.was and line.was.delivery_date %}{{ line.was.delivery_date }}{% else %}{{ line.delivery_date | default("", true) }}{% endif %} |{% if cols.delivery_date %} {% if line.was and line.was.delivery_date %}{{ line.delivery_date | default("", true) }}{% endif %} |{% endif %} {{ line.remark | default("", true) }}
{% endfor %}
Raised by {{ actor.name if actor else '-' }} on {{ today }}.
Open: {{ handover.link }}
""".replace("__COLUMNS_IN_USE__", _COLUMNS_IN_USE)


def _set_template(bind, *, subject: str, body_html: str, body_text: str) -> None:
    existing = bind.execute(
        sa.text("SELECT id FROM email_templates WHERE code = :code"),
        {"code": TEMPLATE_CODE},
    ).first()
    if existing:
        bind.execute(
            sa.text(
                """
                UPDATE email_templates
                SET subject = :subject, body_html = :body_html, body_text = :body_text
                WHERE code = :code
                """
            ),
            {
                "code": TEMPLATE_CODE,
                "subject": subject,
                "body_html": body_html,
                "body_text": body_text,
            },
        )
        return
    bind.execute(
        sa.text(
            """
            INSERT INTO email_templates (id, code, name, description, subject, body_html, body_text, is_active)
            VALUES (gen_random_uuid(), :code, :name, :description, :subject, :body_html, :body_text, true)
            """
        ),
        {
            "code": TEMPLATE_CODE,
            "name": "Order Inquiry Handover to Purchasing (default)",
            "description": (
                "Shaped like the manual handover mail CS sends purchasing: SO table, "
                "line table (with the stock location per line), QTY/DELIVERY DATE and "
                "their own CHANGE TO columns."
            ),
            "subject": subject,
            "body_html": body_html,
            "body_text": body_text,
        },
    )


def upgrade() -> None:
    bind = op.get_bind()
    _set_template(bind, subject=_SUBJECT, body_html=_BODY_HTML, body_text=_BODY_TEXT)


def downgrade() -> None:
    bind = op.get_bind()
    _set_template(bind, subject=_SUBJECT, body_html=_R2_BODY_HTML, body_text=_R2_BODY_TEXT)
