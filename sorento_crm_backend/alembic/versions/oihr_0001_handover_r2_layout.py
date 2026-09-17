"""Order inquiry handover email r2 layout (PLAN-scm-oi-handover-r2-undo.md, S1,
AC-R2-01..05/08/09).

Updates ``email_templates`` (same ``code`` as ``TEMPLATE_CODE`` below) IN PLACE: the
line table's own columns become ``SO DATE | S/O NO | ITEM CODE | QTY | QTY CHANGE TO |
DELIVERY DATE | DELIVERY DATE CHANGE TO | REMARK`` - the layout of the manual mail CS
sent purchasing, `QTY`/`DELIVERY DATE` printing the OLD value and the `CHANGE TO` column
next to it printing the new one only when it moved, rather than the r1 layout's
strikethrough-old-value-then-new-value-in-one-cell. Reverses ruling R3 of the archived
``PLAN-scm-oi-handover-email.md``. ``CUSTOMER``/``PROJECT`` stay on the SO table above,
unchanged.

An UPDATE, not a skip-if-exists insert (unlike ``oihe_0001_seed_handover_automation``,
whose seed this revises): the row already exists on every DB that ran this lane's
down_revision, and the point of THIS migration is to deliver a fix to its body, so
skipping when it is present would ship nothing. A DB with no row yet (a fresh schema, or
one stamped past ``oihe_0001`` without ever running it) gets one inserted. Idempotent:
running twice sets the same subject/body_html/body_text both times. The automation row
and its recipients are untouched - an admin-typed extra email survives this migration.

Downgrade restores the r1 body verbatim (copied from ``oihe_0001_seed_handover_
automation.py`` byte for byte, not re-derived), so a rollback returns the exact string a
DB on that revision would show.

Revision ID: oihr_0001_handover_r2_layout
Revises: undo_0003_journal_sql_null
Create Date: 2026-09-18
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "oihr_0001_handover_r2_layout"
down_revision = "undo_0003_journal_sql_null"
branch_labels = None
depends_on = None


# Split, not a literal, on purpose: `test_order_inquiry_handover_automation.py`'s
# `_find_seed_migration_path()` (the OLDER r1 seed migration's own discovery helper,
# `PLAN-scm-oi-handover-email.md`) finds ITS file by scanning alembic/versions/*.py for
# any file whose raw text contains this template's code as one contiguous token - which
# this migration's own runtime value would otherwise also match, and `Path.glob` gives
# no ordering guarantee between the two, so the r1-only tests (`test_seed_migration_
# idempotent` etc, all pre-dating this lane) started loading THIS file instead and
# broke. The runtime string is byte-for-byte identical either way; only the SOURCE no
# longer carries the one contiguous token that helper's `in` check keys on.
TEMPLATE_CODE = "order_inquiry_handover" + "_default"

# Subject is unchanged from r1 - AC-R2-14/15's blank-location rule lives in the Python
# context builder (`_build_handover_context`), not the template.
_SUBJECT = "OI: {{ handover.subject_scope }}"

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
<table style="__TABLE_STYLE__margin-top:12px;">
  <thead>
    <tr>
      <th style="__TH_STYLE__">SO DATE</th><th style="__TH_STYLE__">S/O NO</th><th style="__TH_STYLE__">ITEM CODE</th>
      <th style="__TH_STYLE__">QTY</th><th style="__TH_STYLE__">QTY CHANGE TO</th>
      <th style="__TH_STYLE__">DELIVERY DATE</th><th style="__TH_STYLE__">DELIVERY DATE CHANGE TO</th>
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
      <td style="__TD_STYLE__">{% if line.was and line.was.qty %}{{ line.qty | default("", true) }}{% endif %}</td>
      <td style="__TD_STYLE__">{% if line.was and line.was.delivery_date %}{{ line.was.delivery_date }}{% else %}{{ line.delivery_date | default("", true) }}{% endif %}</td>
      <td style="__TD_STYLE__">{% if line.was and line.was.delivery_date %}{{ line.delivery_date | default("", true) }}{% endif %}</td>
      <td style="__TD_STYLE__">{{ line.remark | default("", true) }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
<p>Raised by {{ actor.name if actor else '-' }}{% if actor %} ({{ actor.email }}){% endif %} on {{ today }}.</p>
<p><a href="{{ handover.link }}">Open in Order Inquiries</a></p>
""".replace("__TABLE_STYLE__", _TABLE_STYLE).replace("__TH_STYLE__", _TH_STYLE).replace(
    "__TD_STYLE__", _TD_STYLE
)

_BODY_TEXT = """\
{{ handover.headline }}

{% for order in handover.orders %}{{ order.so_number | default("", true) }}{% if order.customer %} - {{ order.customer }}{% endif %}{% if order.project %} - {{ order.project }}{% endif %}
{% endfor %}
SO DATE | S/O NO | ITEM CODE | QTY | QTY CHANGE TO | DELIVERY DATE | DELIVERY DATE CHANGE TO | REMARK
{% for line in handover.lines %}{{ line.so_date | default("", true) }} | {{ line.so_number | default("", true) }} | {{ line.item_code | default("", true) }} | {% if line.was and line.was.qty %}{{ line.was.qty }}{% else %}{{ line.qty | default("", true) }}{% endif %} | {% if line.was and line.was.qty %}{{ line.qty | default("", true) }}{% endif %} | {% if line.was and line.was.delivery_date %}{{ line.was.delivery_date }}{% else %}{{ line.delivery_date | default("", true) }}{% endif %} | {% if line.was and line.was.delivery_date %}{{ line.delivery_date | default("", true) }}{% endif %} | {{ line.remark | default("", true) }}
{% endfor %}
Raised by {{ actor.name if actor else '-' }} on {{ today }}.
Open: {{ handover.link }}
"""


# --------------------------------------------------------------------------- #
# r1 body, copied byte for byte from oihe_0001_seed_handover_automation.py -  #
# what downgrade restores. Never edit this to "fix" it; a fix to the r1 body  #
# has nothing left to ship it against once r2 is live.                       #
# --------------------------------------------------------------------------- #

_R1_SUBJECT = "OI: {{ handover.subject_scope }}"

_R1_BODY_HTML = """\
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
<table style="__TABLE_STYLE__margin-top:12px;">
  <thead>
    <tr>
      <th style="__TH_STYLE__">SO DATE</th><th style="__TH_STYLE__">S/O NO</th><th style="__TH_STYLE__">CUSTOMER</th><th style="__TH_STYLE__">PROJECT</th>
      <th style="__TH_STYLE__">ITEM CODE</th><th style="__TH_STYLE__">QTY</th><th style="__TH_STYLE__">DELIVERY DATE</th><th style="__TH_STYLE__">REMARK</th>
    </tr>
  </thead>
  <tbody>
    {% for line in handover.lines %}
    <tr>
      <td style="__TD_STYLE__">{{ line.so_date | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ line.so_number | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ line.customer | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ line.project | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ line.item_code | default("", true) }}</td>
      <td style="__TD_STYLE__">{% if line.was and line.was.qty %}<s>{{ line.was.qty }}</s> {% endif %}{{ line.qty | default("", true) }}</td>
      <td style="__TD_STYLE__">{% if line.was and line.was.delivery_date %}<s>{{ line.was.delivery_date }}</s> {% endif %}{{ line.delivery_date | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ line.remark | default("", true) }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
<p>Raised by {{ actor.name if actor else '-' }}{% if actor %} ({{ actor.email }}){% endif %} on {{ today }}.</p>
<p><a href="{{ handover.link }}">Open in Order Inquiries</a></p>
""".replace("__TABLE_STYLE__", _TABLE_STYLE).replace("__TH_STYLE__", _TH_STYLE).replace(
    "__TD_STYLE__", _TD_STYLE
)

_R1_BODY_TEXT = """\
{{ handover.headline }}

{% for order in handover.orders %}{{ order.so_number | default("", true) }}{% if order.customer %} - {{ order.customer }}{% endif %}{% if order.project %} - {{ order.project }}{% endif %}
{% endfor %}
SO DATE | S/O NO | CUSTOMER | PROJECT | ITEM CODE | QTY | DELIVERY DATE | REMARK
{% for line in handover.lines %}{{ line.so_date | default("", true) }} | {{ line.so_number | default("", true) }} | {{ line.customer | default("", true) }} | {{ line.project | default("", true) }} | {{ line.item_code | default("", true) }} | {% if line.was and line.was.qty %}{{ line.qty }} (was {{ line.was.qty }}){% else %}{{ line.qty | default("", true) }}{% endif %} | {% if line.was and line.was.delivery_date %}{{ line.delivery_date }} (was {{ line.was.delivery_date }}){% else %}{{ line.delivery_date | default("", true) }}{% endif %} | {{ line.remark | default("", true) }}
{% endfor %}
Raised by {{ actor.name if actor else '-' }} on {{ today }}.
Open: {{ handover.link }}
"""


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
                "line table, QTY/DELIVERY DATE and their own CHANGE TO columns."
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
    _set_template(bind, subject=_R1_SUBJECT, body_html=_R1_BODY_HTML, body_text=_R1_BODY_TEXT)
