"""Seed the "order inquiry undone" email to purchasing
(PLAN-board-undo-last-confirm.md, "The email", AC-UC-34/AC-UC-35).

Same method as `oihe_0001_seed_handover_automation`, copied not adapted: an admin can
switch it off (untick Enabled) independently of the handover mail it compensates for.
Seeded ENABLED for the same reason the handover one is - the moment a planner undoes a
confirm, purchasing needs telling what changed back.

Idempotent by `email_templates.code` and `(trigger_type, name)`, same shape as
`oihe_0001`: a re-run of this revision SKIPS both rows when they already exist. An
UPDATE there could only ever overwrite an admin's own hand edit, never deliver a fix (a
body/config fix ships as its own migration).

`recipient_config` is copied from the existing `order_inquiry_handover` automation row
when one exists (same audience: purchasing hears about the undo the same way it heard
about the handover) - falling back to `oihe_0001`'s own default-building query
(purchasing roles, `include_actor`, `one_email`) when no handover row exists yet, so a
database that migrates this revision before `oihe_0001` (or never ran it) still gets a
sane default rather than an empty one.

Revision ID: undo_0002_seed_undone
Revises: undo_0001_undo_journal
Create Date: 2026-09-17
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op


revision = "undo_0002_seed_undone"
down_revision = "undo_0001_undo_journal"
branch_labels = None
depends_on = None


TEMPLATE_CODE = "order_inquiry_undone_default"
AUTOMATION_NAME = "Order inquiry undone"
TRIGGER_TYPE = "order_inquiry_undone"
HANDOVER_TRIGGER_TYPE = "order_inquiry_handover"

_SUBJECT = "OI undone: {{ undo.so_number }} rev {{ undo.revision_no }}"

# Inline, like `oihe_0001`'s own body - a mail client carries no stylesheet.
_TH_STYLE = "border:1px solid #d0d0d5;padding:4px 8px;background:#f2f2f5;text-align:left;"
_TD_STYLE = "border:1px solid #d0d0d5;padding:4px 8px;"
_TABLE_STYLE = "border-collapse:collapse;font-family:Arial, sans-serif;font-size:13px;"

_BODY_HTML = """\
<p style="color:#b91c1c;font-weight:bold;">Undone: {{ undo.so_number | default("", true) }} rev {{ undo.revision_no }}</p>
<p>{{ undo.customer | default("", true) }}{% if undo.customer and undo.project %} / {% endif %}{{ undo.project | default("", true) }}</p>
<table style="__TABLE_STYLE__">
  <thead>
    <tr><th style="__TH_STYLE__">ITEM CODE</th><th style="__TH_STYLE__">QTY</th><th style="__TH_STYLE__">DELIVERY DATE</th><th style="__TH_STYLE__">OUTCOME</th></tr>
  </thead>
  <tbody>
    {% for line in undo.lines %}
    <tr>
      <td style="__TD_STYLE__">{{ line.item_code | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ line.qty | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ line.delivery_date | default("", true) }}</td>
      <td style="__TD_STYLE__">{{ line.outcome | default("", true) }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
<p>Undone by {{ actor.name if actor else '-' }}{% if actor %} ({{ actor.email }}){% endif %} on {{ today }}.</p>
<p><a href="{{ undo.link }}">Open in Order Inquiries</a></p>
""".replace("__TABLE_STYLE__", _TABLE_STYLE).replace("__TH_STYLE__", _TH_STYLE).replace(
    "__TD_STYLE__", _TD_STYLE
)

_BODY_TEXT = """\
Undone: {{ undo.so_number | default("", true) }} rev {{ undo.revision_no }}
{{ undo.customer | default("", true) }}{% if undo.customer and undo.project %} / {% endif %}{{ undo.project | default("", true) }}

ITEM CODE | QTY | DELIVERY DATE | OUTCOME
{% for line in undo.lines %}{{ line.item_code | default("", true) }} | {{ line.qty | default("", true) }} | {{ line.delivery_date | default("", true) }} | {{ line.outcome | default("", true) }}
{% endfor %}
Undone by {{ actor.name if actor else '-' }} on {{ today }}.
Open: {{ undo.link }}
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
            "name": "Order Inquiry Undone (default)",
            "description": (
                "Tells purchasing a board Confirm was undone: which lines went back "
                "to their earlier quantity or date, and which freshly-raised lines "
                "disappeared."
            ),
            "subject": _SUBJECT,
            "body_html": _BODY_HTML,
            "body_text": _BODY_TEXT,
        },
    )


def _default_recipient_config(bind) -> str:
    """`oihe_0001`'s own default-building query, copied not adapted - used only when
    no `order_inquiry_handover` automation row exists yet to copy from."""
    role_ids = [
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT id FROM user_roles WHERE slug LIKE 'purchasing%' "
                "AND is_trashed = false"
            )
        ).fetchall()
    ]
    return json.dumps(
        {
            "user_ids": [],
            "role_ids": [str(r) for r in role_ids],
            "extra_emails": [],
            "include_actor": True,
            "one_email": True,
        }
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

    handover_row = bind.execute(
        sa.text(
            "SELECT recipient_config FROM automations WHERE trigger_type = :tt LIMIT 1"
        ),
        {"tt": HANDOVER_TRIGGER_TYPE},
    ).first()
    if handover_row is not None and handover_row[0] is not None:
        raw = handover_row[0]
        recipient_config = raw if isinstance(raw, str) else json.dumps(raw)
    else:
        recipient_config = _default_recipient_config(bind)

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
                "Mails purchasing whenever a planner undoes a board Confirm, so the "
                "handover it may have already read is compensated for."
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
    # Only when nothing else references it (same rule `oihe_0001` downgrade uses):
    # `automations.email_template_id` is `ON DELETE RESTRICT`, and an admin may have
    # pointed a second, unrelated automation at this same default template.
    bind.execute(
        sa.text(
            """
            DELETE FROM email_templates
            WHERE code = :code
              AND NOT EXISTS (
                  SELECT 1 FROM automations
                  WHERE automations.email_template_id = email_templates.id
              )
            """
        ),
        {"code": TEMPLATE_CODE},
    )
