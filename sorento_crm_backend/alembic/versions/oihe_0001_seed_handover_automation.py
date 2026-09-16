"""Seed the order inquiry handover email to purchasing (PLAN-scm-oi-handover-email.md,
AC-H13/AC-H14).

The parallel run starts at go-live (17 Sep): CS keeps sending the manual mail while
purchasing also gets one shaped like it, from an Automation row an admin can switch off
(untick Enabled) the moment the manual mail retires. Seeded ENABLED, unlike the
purchase-request/sponsorship-approved automations before it (R9, owner ruling 16 Sep) -
this one has to run from day one for the comparison to mean anything.

Idempotent by ``email_templates.code`` and ``(trigger_type, name)``, same shape as
``212_seed_pr_sponsorship_approved_automation`` - except the template body: a re-run
UPDATEs subject/body_html/body_text on the existing row rather than skipping, so a
database that already seeded an earlier revision of this body (the 0915 copy, prod after
deploy) picks up a fix on the next ``alembic upgrade head`` instead of keeping it stale
forever. ``role_ids`` seeds every role whose slug starts with ``purchasing`` - empty on a
database with none (CI's blank schema).

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

# Inline, because a mail client carries no stylesheet (production-copy render finding,
# 16 Sep: a body with only `border-collapse` on the `<table>` and nothing on any cell
# rendered as a squashed, borderless grid in both the recipient's client and the
# outbox preview).
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

_BODY_TEXT = """\
{{ handover.headline }}

{% for order in handover.orders %}{{ order.so_number | default("", true) }}{% if order.customer %} - {{ order.customer }}{% endif %}{% if order.project %} - {{ order.project }}{% endif %}
{% endfor %}
SO DATE | S/O NO | CUSTOMER | PROJECT | ITEM CODE | QTY | DELIVERY DATE | REMARK
{% for line in handover.lines %}{{ line.so_date | default("", true) }} | {{ line.so_number | default("", true) }} | {{ line.customer | default("", true) }} | {{ line.project | default("", true) }} | {{ line.item_code | default("", true) }} | {% if line.was and line.was.qty %}{{ line.qty }} (was {{ line.was.qty }}){% else %}{{ line.qty | default("", true) }}{% endif %} | {% if line.was and line.was.delivery_date %}{{ line.delivery_date }} (was {{ line.was.delivery_date }}){% else %}{{ line.delivery_date | default("", true) }}{% endif %} | {{ line.remark | default("", true) }}
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
        # Still idempotent - one row, same code - but not a no-op: the body has already
        # been revised once after a production-copy render caught real defects (blank
        # fields printing the word "None", tables with no inline cell borders), so a
        # database that seeded the FIRST version (the 0915 copy, prod after deploy) must
        # pick up the fix on the next `alembic upgrade head` rather than keep serving it.
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
                "subject": _SUBJECT,
                "body_html": _BODY_HTML,
                "body_text": _BODY_TEXT,
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
            "SELECT id, recipient_config FROM automations "
            "WHERE trigger_type = :tt AND name = :name"
        ),
        {"tt": TRIGGER_TYPE, "name": AUTOMATION_NAME},
    ).first()
    if existing:
        # Idempotent re-run must still pick up a config key added AFTER the row was
        # first written (AC-H26: `one_email` did not exist at first seed) - an
        # already-seeded database (the 0915 copy, prod after deploy) needs it added
        # once, without touching anything an admin has changed by hand since.
        automation_id, recipient_config = existing
        cfg = (
            recipient_config
            if isinstance(recipient_config, dict)
            else json.loads(recipient_config or "{}")
        )
        if "one_email" not in cfg:
            cfg["one_email"] = True
            bind.execute(
                sa.text(
                    "UPDATE automations SET recipient_config = CAST(:cfg AS jsonb) "
                    "WHERE id = :id"
                ),
                {"cfg": json.dumps(cfg), "id": automation_id},
            )
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
            # R5: the manual mail's shape - one email, purchasing plus the raiser on
            # one thread, not one copy per address (AC-H26).
            "one_email": True,
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
    # Only when nothing else references it (review round 1 nit): `automations.
    # email_template_id` is `ON DELETE RESTRICT`, and an admin may have pointed a second,
    # unrelated automation at this same default template after deploy - deleting it
    # unconditionally would fail the downgrade on that FK rather than leave the template
    # behind for whoever is still using it.
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
