"""Seed the order inquiry handover email to purchasing (PLAN-scm-oi-handover-email.md,
AC-H13/AC-H14).

The parallel run starts at go-live (17 Sep): CS keeps sending the manual mail while
purchasing also gets one shaped like it, from an Automation row an admin can switch off
(untick Enabled) the moment the manual mail retires. Seeded ENABLED, unlike the
purchase-request/sponsorship-approved automations before it (R9, owner ruling 16 Sep) -
this one has to run from day one for the comparison to mean anything.

Idempotent by ``email_templates.code`` and ``(trigger_type, name)``, same shape as
``212_seed_pr_sponsorship_approved_automation``. ``role_ids`` seeds every role whose slug
starts with ``purchasing`` - empty on a database with none (CI's blank schema).

Revision ID: oihe_0001_seed_handover
Revises: ptag_0011_line_promo
Create Date: 2026-09-16
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op


revision = "oihe_0001_seed_handover"
down_revision = "ptag_0011_line_promo"
branch_labels = None
depends_on = None


TEMPLATE_CODE = "order_inquiry_handover_default"
AUTOMATION_NAME = "Order inquiry to purchasing"
TRIGGER_TYPE = "order_inquiry_handover"

_SUBJECT = "OI: {{ handover.subject_scope }}"

_BODY_HTML = """\
<p style="color:#b91c1c;font-weight:bold;">{{ handover.headline }}</p>
<table border="1" cellspacing="0" cellpadding="4" style="border-collapse:collapse;">
  <thead>
    <tr><th>S/O NO</th><th>CUSTOMER</th><th>PROJECT</th></tr>
  </thead>
  <tbody>
    {% for order in handover.orders %}
    <tr>
      <td>{{ order.so_number }}</td>
      <td>{{ order.customer }}</td>
      <td>{{ order.project }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
<table border="1" cellspacing="0" cellpadding="4" style="border-collapse:collapse;margin-top:12px;">
  <thead>
    <tr>
      <th>SO DATE</th><th>S/O NO</th><th>CUSTOMER</th><th>PROJECT</th>
      <th>ITEM CODE</th><th>QTY</th><th>DELIVERY DATE</th><th>REMARK</th>
    </tr>
  </thead>
  <tbody>
    {% for line in handover.lines %}
    <tr>
      <td>{{ line.so_date }}</td>
      <td>{{ line.so_number }}</td>
      <td>{{ line.customer }}</td>
      <td>{{ line.project }}</td>
      <td>{{ line.item_code }}</td>
      <td>{% if line.was and line.was.qty %}<s>{{ line.was.qty }}</s> {% endif %}{{ line.qty }}</td>
      <td>{% if line.was and line.was.delivery_date %}<s>{{ line.was.delivery_date }}</s> {% endif %}{{ line.delivery_date }}</td>
      <td>{{ line.remark }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
<p>Raised by {{ actor.name if actor else '-' }}{% if actor %} ({{ actor.email }}){% endif %} on {{ today }}.</p>
<p><a href="{{ handover.link }}">Open in Order Inquiries</a></p>
"""

_BODY_TEXT = """\
{{ handover.headline }}

{% for order in handover.orders %}{{ order.so_number }} - {{ order.customer }} - {{ order.project }}
{% endfor %}
SO DATE | S/O NO | CUSTOMER | PROJECT | ITEM CODE | QTY | DELIVERY DATE | REMARK
{% for line in handover.lines %}{{ line.so_date }} | {{ line.so_number }} | {{ line.customer }} | {{ line.project }} | {{ line.item_code }} | {% if line.was and line.was.qty %}{{ line.qty }} (was {{ line.was.qty }}){% else %}{{ line.qty }}{% endif %} | {% if line.was and line.was.delivery_date %}{{ line.delivery_date }} (was {{ line.was.delivery_date }}){% else %}{{ line.delivery_date }}{% endif %} | {{ line.remark }}
{% endfor %}
Raised by {{ actor.name if actor else '-' }} on {{ today }}.
Open: {{ handover.link }}
"""


def _seed_template(bind) -> None:
    existing = bind.execute(
        sa.text("SELECT id FROM email_templates WHERE code = :code"),
        {"code": TEMPLATE_CODE},
    ).first()
    if existing:
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
                "line table, changes struck through in the cell."
            ),
            "subject": _SUBJECT,
            "body_html": _BODY_HTML,
            "body_text": _BODY_TEXT,
        },
    )


def _seed_automation(bind) -> None:
    existing = bind.execute(
        sa.text(
            "SELECT id FROM automations WHERE trigger_type = :tt AND name = :name"
        ),
        {"tt": TRIGGER_TYPE, "name": AUTOMATION_NAME},
    ).first()
    if existing:
        return

    template_row = bind.execute(
        sa.text("SELECT id FROM email_templates WHERE code = :code"),
        {"code": TEMPLATE_CODE},
    ).first()
    if template_row is None:
        # Should not happen - _seed_template runs first in upgrade().
        return
    template_id = template_row[0]

    role_ids = [
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT id FROM user_roles WHERE slug LIKE 'purchasing%' "
                "AND is_trashed = false"
            )
        ).fetchall()
    ]
    recipient_config = json.dumps(
        {
            "user_ids": [],
            "role_ids": [str(r) for r in role_ids],
            "extra_emails": [],
            "include_actor": True,
        }
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO automations (
                id, name, description, enabled,
                trigger_type, trigger_config,
                action_type, email_template_id,
                recipient_config, group_matches,
                schedule_type, timezone
            )
            VALUES (
                gen_random_uuid(), :name, :description, true,
                :trigger_type, '{}'::jsonb,
                'send_email', :template_id,
                CAST(:recipient_config AS jsonb), false,
                'manual', 'Asia/Kuala_Lumpur'
            )
            """
        ),
        {
            "name": AUTOMATION_NAME,
            "description": (
                "Parallel run (go-live 17 Sep): mails purchasing whenever CS raises, "
                "settles or cancels order inquiry rows in one write, shaped like the "
                "manual mail it is being compared against. Untick Enabled to retire "
                "the comparison."
            ),
            "trigger_type": TRIGGER_TYPE,
            "template_id": template_id,
            "recipient_config": recipient_config,
        },
    )


def upgrade() -> None:
    bind = op.get_bind()
    _seed_template(bind)
    _seed_automation(bind)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM automations WHERE trigger_type = :tt AND name = :name"
        ),
        {"tt": TRIGGER_TYPE, "name": AUTOMATION_NAME},
    )
    bind.execute(
        sa.text("DELETE FROM email_templates WHERE code = :code"),
        {"code": TEMPLATE_CODE},
    )
