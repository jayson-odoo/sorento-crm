"""Seed default email templates + automations for the new PR / sponsorship approved triggers.

Creates two ``email_templates`` rows and two ``automations`` rows wired to the
new ``purchase_request_approved`` and ``sponsorship_form_approved`` trigger
types. Automations are seeded **disabled with empty recipient_config** so they
do not fire blank emails on first deploy — the admin opens System Management →
Automation, picks recipients, then flips the enable switch.

Idempotent: skips rows that already exist by ``email_templates.code`` and by
``(trigger_type, name)`` for automations.

Revision ID: 212_seed_pr_sponsorship_approved_automation
Revises: 211_portal_attachments_accept_video
Create Date: 2026-05-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "212_seed_pr_sponsorship_approved_automation"
down_revision = "211_portal_attachments_accept_video"
branch_labels = None
depends_on = None


_PR_TEMPLATE_CODE = "purchase_request_approved_default"
_SF_TEMPLATE_CODE = "sponsorship_form_approved_default"
_PR_AUTOMATION_NAME = "Purchase request approved notification"
_SF_AUTOMATION_NAME = "Sponsorship form approved notification"


_PR_SUBJECT = "[Approved] Purchase Request {{ purchase_request.request_number }}"
_SF_SUBJECT = "[Approved] Sponsorship Form {{ purchase_request.request_number }}"


_PR_BODY_HTML = """\
<p>Hi {{ recipient.name }},</p>
<p>
  <strong>{{ purchase_request.type_label }} {{ purchase_request.request_number }}</strong>
  has been <strong>approved</strong>.
</p>
<ul>
  <li><strong>Customer:</strong> {{ purchase_request.customer_name or '—' }}</li>
  <li><strong>Project:</strong> {{ purchase_request.project_title or '—' }}</li>
  <li><strong>Purpose:</strong> {{ purchase_request.purpose or '—' }}</li>
  <li><strong>Requested by:</strong> {{ purchase_request.requested_by or '—' }}</li>
  <li><strong>Approved by:</strong> {{ purchase_request.approved_by or '—' }}</li>
  <li><strong>Approved at:</strong> {{ purchase_request.approved_at or '—' }}</li>
  <li><strong>Expected delivery:</strong> {{ purchase_request.expected_delivery_date or '—' }}</li>
  <li><strong>Expected PO date:</strong> {{ purchase_request.expected_po_date or purchase_request.expected_po_date_text or '—' }}</li>
</ul>
{% if purchase_request.approval_comments %}
<p><strong>Approval comments:</strong> {{ purchase_request.approval_comments }}</p>
{% endif %}
<p><a href="{{ purchase_request.link }}">Open purchase request</a></p>
"""

_SF_BODY_HTML = """\
<p>Hi {{ recipient.name }},</p>
<p>
  <strong>{{ purchase_request.type_label }} {{ purchase_request.request_number }}</strong>
  has been <strong>approved</strong>.
</p>
<ul>
  <li><strong>Customer:</strong> {{ purchase_request.customer_name or '—' }}</li>
  <li><strong>Project:</strong> {{ purchase_request.project_title or '—' }}</li>
  <li><strong>Purpose:</strong> {{ purchase_request.purpose or '—' }}</li>
  <li><strong>Total project value:</strong>
    {{ purchase_request.total_project_value_text
       or purchase_request.total_project_value
       or '—' }}
  </li>
  <li><strong>Requested by:</strong> {{ purchase_request.requested_by or '—' }}</li>
  <li><strong>Approved by:</strong> {{ purchase_request.approved_by or '—' }}</li>
  <li><strong>Approved at:</strong> {{ purchase_request.approved_at or '—' }}</li>
</ul>
{% if purchase_request.approval_comments %}
<p><strong>Approval comments:</strong> {{ purchase_request.approval_comments }}</p>
{% endif %}
<p><a href="{{ purchase_request.link }}">Open sponsorship form</a></p>
"""


_PR_BODY_TEXT = """\
Hi {{ recipient.name }},

{{ purchase_request.type_label }} {{ purchase_request.request_number }} has been approved.

Customer: {{ purchase_request.customer_name or '-' }}
Project:  {{ purchase_request.project_title or '-' }}
Purpose:  {{ purchase_request.purpose or '-' }}
Requested by: {{ purchase_request.requested_by or '-' }}
Approved by:  {{ purchase_request.approved_by or '-' }}
Approved at:  {{ purchase_request.approved_at or '-' }}
Expected delivery: {{ purchase_request.expected_delivery_date or '-' }}
Expected PO date:  {{ purchase_request.expected_po_date or purchase_request.expected_po_date_text or '-' }}
{% if purchase_request.approval_comments %}
Approval comments: {{ purchase_request.approval_comments }}
{% endif %}
Open: {{ purchase_request.link }}
"""

_SF_BODY_TEXT = """\
Hi {{ recipient.name }},

{{ purchase_request.type_label }} {{ purchase_request.request_number }} has been approved.

Customer: {{ purchase_request.customer_name or '-' }}
Project:  {{ purchase_request.project_title or '-' }}
Purpose:  {{ purchase_request.purpose or '-' }}
Total project value: {{ purchase_request.total_project_value_text or purchase_request.total_project_value or '-' }}
Requested by: {{ purchase_request.requested_by or '-' }}
Approved by:  {{ purchase_request.approved_by or '-' }}
Approved at:  {{ purchase_request.approved_at or '-' }}
{% if purchase_request.approval_comments %}
Approval comments: {{ purchase_request.approval_comments }}
{% endif %}
Open: {{ purchase_request.link }}
"""


def _upsert_template(bind, *, code: str, name: str, description: str, subject: str, body_html: str, body_text: str) -> None:
    existing = bind.execute(
        sa.text("SELECT id FROM email_templates WHERE code = :code"),
        {"code": code},
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
            "code": code,
            "name": name,
            "description": description,
            "subject": subject,
            "body_html": body_html,
            "body_text": body_text,
        },
    )


def _seed_automation(
    bind,
    *,
    name: str,
    description: str,
    trigger_type: str,
    template_code: str,
) -> None:
    existing = bind.execute(
        sa.text(
            "SELECT id FROM automations WHERE trigger_type = :tt AND name = :name"
        ),
        {"tt": trigger_type, "name": name},
    ).first()
    if existing:
        return

    template_row = bind.execute(
        sa.text("SELECT id FROM email_templates WHERE code = :code"),
        {"code": template_code},
    ).first()
    if template_row is None:
        # Should not happen — _upsert_template runs first in upgrade().
        return
    template_id = template_row[0]

    bind.execute(
        sa.text(
            """
            INSERT INTO automations (
                id, name, description, enabled,
                trigger_type, trigger_config,
                action_type, email_template_id,
                recipient_config,
                schedule_type, timezone
            )
            VALUES (
                gen_random_uuid(), :name, :description, false,
                :trigger_type, '{}'::jsonb,
                'send_email', :template_id,
                '{"user_ids": [], "role_ids": [], "extra_emails": [], "include_promotion_owner": false}'::jsonb,
                'manual', 'Asia/Kuala_Lumpur'
            )
            """
        ),
        {
            "name": name,
            "description": description,
            "trigger_type": trigger_type,
            "template_id": template_id,
        },
    )


def upgrade() -> None:
    bind = op.get_bind()

    _upsert_template(
        bind,
        code=_PR_TEMPLATE_CODE,
        name="Purchase Request Approved (default)",
        description="Default body sent to configured recipients when a purchase request is approved.",
        subject=_PR_SUBJECT,
        body_html=_PR_BODY_HTML,
        body_text=_PR_BODY_TEXT,
    )
    _upsert_template(
        bind,
        code=_SF_TEMPLATE_CODE,
        name="Sponsorship Form Approved (default)",
        description="Default body sent to configured recipients when a sponsorship form is approved.",
        subject=_SF_SUBJECT,
        body_html=_SF_BODY_HTML,
        body_text=_SF_BODY_TEXT,
    )

    _seed_automation(
        bind,
        name=_PR_AUTOMATION_NAME,
        description=(
            "Sends the default approval email to configured recipients whenever a "
            "purchase request transitions to approved. Seeded disabled — add "
            "recipients in System Management → Automation, then enable."
        ),
        trigger_type="purchase_request_approved",
        template_code=_PR_TEMPLATE_CODE,
    )
    _seed_automation(
        bind,
        name=_SF_AUTOMATION_NAME,
        description=(
            "Sends the default approval email to configured recipients whenever a "
            "sponsorship form transitions to approved. Seeded disabled — add "
            "recipients in System Management → Automation, then enable."
        ),
        trigger_type="sponsorship_form_approved",
        template_code=_SF_TEMPLATE_CODE,
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM automations WHERE trigger_type IN "
            "('purchase_request_approved', 'sponsorship_form_approved') "
            "AND name IN (:pr, :sf)"
        ),
        {"pr": _PR_AUTOMATION_NAME, "sf": _SF_AUTOMATION_NAME},
    )
    bind.execute(
        sa.text(
            "DELETE FROM email_templates WHERE code IN (:pr, :sf)"
        ),
        {"pr": _PR_TEMPLATE_CODE, "sf": _SF_TEMPLATE_CODE},
    )
