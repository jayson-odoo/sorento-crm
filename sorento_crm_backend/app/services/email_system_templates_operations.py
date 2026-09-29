"""System email documents: operations mails (#1349). Registered by email_system_templates.py.

Each entry follows the same shape as the auth/users/SLA entries there: brand header,
heading, intro, facts, one button, footer. Producers call
`EmailTemplateService(db).render_code(code, context)` and pass context only.
"""
from __future__ import annotations

from typing import Any, Optional

from app.services.email_system_templates_base import SystemTemplate


def _h() -> dict[str, Any]:
    return {"type": "brand_header"}


def _f(note: Optional[str] = None) -> dict[str, Any]:
    return {"type": "footer", "note": note} if note else {"type": "footer"}


_SAMPLE_BASE = "https://crm.example.com"
_REPLY_NOTE = "This is a system-generated email. Please do not reply."


TEMPLATES: list[SystemTemplate] = [
    # ----------------------------------------------------------------- complaints
    SystemTemplate(
        code="complaint_created",
        name="Complaint created / resubmitted",
        description=(
            "Notifies the Complaint team when a new complaint is created externally, "
            "or a previously rejected one is resubmitted."
        ),
        subject="{{ title }}",
        # The route's old plain body, byte for byte - `notification.body` is read by
        # other channels too, so the text part cannot drift from it.
        body_text=(
            "Dear Complaint Team,\n\n{{ sentence }}\n\n{{ view_url }}\n\n" + _REPLY_NOTE
        ),
        blocks=[
            _h(),
            {"type": "heading", "text": "{{ title }}"},
            {"type": "intro", "text": "Dear Complaint Team,\n\n{{ sentence }}"},
            {"type": "button", "label": "Open complaint", "url": "{{ view_url }}"},
            _f(_REPLY_NOTE),
        ],
        variables=[
            {"key": "title", "label": "Title", "sample": "New Complaint created"},
            {
                "key": "sentence",
                "label": "Sentence",
                "sample": "A new complaint has been created and requires your review.",
            },
            {"key": "view_url", "label": "Complaint Link", "sample": f"{_SAMPLE_BASE}/view/complaint?token=sample"},
        ],
        sample={
            "title": "New Complaint created",
            "sentence": "A new complaint has been created and requires your review.",
            "view_url": f"{_SAMPLE_BASE}/view/complaint?token=sample",
        },
    ),
    SystemTemplate(
        code="complaint_do_delivered",
        name="Replacement delivery order delivered",
        description="Notifies the Complaint team (Tier 1 + 2) that a replacement DO has been delivered.",
        subject="{{ title }}",
        # Byte-identical to the old plain body: `notification.body` is pinned by
        # tests/test_complaint_do_notify.py ("\n- SKU-1 x 2\n- SKU-2 x 1", the
        # internal link, never the /view token link).
        body_text=(
            "Dear Complaint Team,\n\n{{ headline }}"
            "{% if items_block %}\n\n{{ items_block }}{% endif %}"
            "\n\n{{ view_url }}\n\n" + _REPLY_NOTE
        ),
        blocks=[
            _h(),
            {"type": "heading", "text": "{{ title }}"},
            {"type": "intro", "text": "Dear Complaint Team,\n\n{{ headline }}"},
            {
                "type": "custom_text",
                "html": (
                    "{% if item_lines %}<p>Items delivered:</p>"
                    "<ul>{% for l in item_lines %}<li>{{ l }}</li>{% endfor %}</ul>{% endif %}"
                ),
            },
            {"type": "button", "label": "Open complaint", "url": "{{ view_url }}"},
            _f(_REPLY_NOTE),
        ],
        variables=[
            {"key": "title", "label": "Title", "sample": "Replacement delivery order delivered"},
            {
                "key": "headline",
                "label": "Headline",
                "sample": "Replacement delivery order REPPS-0012 for complaint CMP-2026-0001 has been delivered.",
            },
            {"key": "item_lines", "label": "Delivered Items (loop of 'CODE x QTY')", "sample": "[ 'SKU-1 x 2', 'SKU-2 x 1' ]"},
            {"key": "view_url", "label": "Complaint Link (internal)", "sample": f"{_SAMPLE_BASE}/complaint-management/complaints/sample"},
        ],
        sample={
            "title": "Replacement delivery order delivered",
            "headline": "Replacement delivery order REPPS-0012 for complaint CMP-2026-0001 has been delivered.",
            "items_block": "Items delivered:\n- SKU-1 x 2\n- SKU-2 x 1",
            "item_lines": ["SKU-1 x 2", "SKU-2 x 1"],
            "view_url": f"{_SAMPLE_BASE}/complaint-management/complaints/sample",
        },
    ),
    # -------------------------------------------------------------- attachments
    SystemTemplate(
        code="attachment_linked",
        name="Attachment linked (external)",
        description=(
            "Notifies an uploader (or the explicit notify user) when an external API used "
            "their file(s) to create or link an entity - product photo, form, packing list. "
            "Multiple callbacks within the coalesce window re-render this with every "
            "attachment collected so far."
        ),
        subject="{{ title }}",
        blocks=[
            _h(),
            {"type": "heading", "text": "{{ title }}"},
            {"type": "custom_text", "html": "{{ summary_html }}"},
            {"type": "button", "label": "{{ entity_link_text }}", "url": "{{ entity_url }}"},
            {
                "type": "custom_text",
                "html": (
                    "{% if attachment_items %}<p>Your attachment(s):</p>"
                    '<ul>{% for a in attachment_items %}<li><a href="{{ a.url }}">{{ a.name }}</a></li>{% endfor %}</ul>{% endif %}'
                ),
            },
            _f(_REPLY_NOTE),
        ],
        variables=[
            {"key": "title", "label": "Title", "sample": "Product attachment linked: PRD-001"},
            {
                "key": "summary_html",
                "label": "Summary (HTML)",
                "sample": '<p>Your file was linked to product <strong>PRD-001</strong> in Sorento CRM.</p>',
            },
            {"key": "entity_url", "label": "Entity Link", "sample": f"{_SAMPLE_BASE}/master-data-management/products/sample"},
            {"key": "entity_link_text", "label": "Entity Link Label", "sample": "Open product in Sorento CRM"},
            {
                "key": "attachment_items",
                "label": "Attachment(s) (loop: name, url)",
                "sample": "[ { name, url }, ... ]",
            },
        ],
        sample={
            "title": "Product attachment linked: PRD-001",
            "summary_html": '<p>Your file was linked to product <strong>PRD-001</strong> in Sorento CRM.</p>',
            "entity_url": f"{_SAMPLE_BASE}/master-data-management/products/sample",
            "entity_link_text": "Open product in Sorento CRM",
            "attachment_items": [
                {"name": "product-photo.jpg", "url": f"{_SAMPLE_BASE}/resource-management/attachments/sample"},
            ],
        },
    ),
    SystemTemplate(
        code="promotion_created",
        name="Promotion created (external)",
        description="Notifies an uploader (or the explicit notify user) when an external API created a promotion using their file(s).",
        subject="{{ title }}",
        blocks=[
            _h(),
            {"type": "heading", "text": "{{ title }}"},
            {"type": "custom_text", "html": "{{ summary_html }}"},
            {"type": "button", "label": "{{ entity_link_text }}", "url": "{{ entity_url }}"},
            {
                "type": "custom_text",
                "html": (
                    "{% if attachment_items %}<p>Your attachment(s):</p>"
                    '<ul>{% for a in attachment_items %}<li><a href="{{ a.url }}">{{ a.name }}</a></li>{% endfor %}</ul>{% endif %}'
                ),
            },
            _f(_REPLY_NOTE),
        ],
        variables=[
            {"key": "title", "label": "Title", "sample": "Promotion created: Year-End Sale"},
            {
                "key": "summary_html",
                "label": "Summary (HTML)",
                "sample": '<p>A promotion <strong>Year-End Sale</strong> was created in Sorento CRM using your uploaded file(s).</p>',
            },
            {"key": "entity_url", "label": "Promotion Link", "sample": f"{_SAMPLE_BASE}/marketing-management/promotions/sample"},
            {"key": "entity_link_text", "label": "Entity Link Label", "sample": "Open promotion in Sorento CRM"},
            {
                "key": "attachment_items",
                "label": "Attachment(s) (loop: name, url)",
                "sample": "[ { name, url }, ... ]",
            },
        ],
        sample={
            "title": "Promotion created: Year-End Sale",
            "summary_html": '<p>A promotion <strong>Year-End Sale</strong> was created in Sorento CRM using your uploaded file(s).</p>',
            "entity_url": f"{_SAMPLE_BASE}/marketing-management/promotions/sample",
            "entity_link_text": "Open promotion in Sorento CRM",
            "attachment_items": [
                {"name": "promo-banner.png", "url": f"{_SAMPLE_BASE}/resource-management/attachments/sample"},
            ],
        },
    ),
    # -------------------------------------------------------------- onboarding
    SystemTemplate(
        code="onboarding_intake_link",
        name="Onboarding intake link",
        description="Sent to the requester with the link to submit their team for onboarding.",
        subject="Submit your team for onboarding: {{ request_title }}",
        blocks=[
            _h(),
            {"type": "heading", "text": "Submit your team for onboarding"},
            {
                "type": "intro",
                "text": (
                    "Hello {{ requester_name }},\n\n"
                    "Sorento asks you to submit your team for onboarding. Open the link below, "
                    "type the names in, and submit it once."
                ),
            },
            {"type": "button", "label": "Open onboarding intake", "url": "{{ intake_url }}"},
            {"type": "link", "label": "Or paste this link into your browser:", "url": "{{ intake_url }}"},
            {
                "type": "custom_text",
                "html": (
                    "<p>The link works until {{ expires_date }} and you can come back to it as "
                    "often as you like until you submit.</p>"
                ),
            },
            _f(_REPLY_NOTE),
        ],
        variables=[
            {"key": "requester_name", "label": "Requester Name", "sample": "Aina"},
            {"key": "request_title", "label": "Request Title", "sample": "ACME Sdn Bhd - Sales Team"},
            {"key": "intake_url", "label": "Intake Link", "sample": f"{_SAMPLE_BASE}/onboarding/intake?token=sample"},
            {"key": "expires_date", "label": "Expires Date", "sample": "31 Dec 2026"},
        ],
        sample={
            "requester_name": "Aina",
            "request_title": "ACME Sdn Bhd - Sales Team",
            "intake_url": f"{_SAMPLE_BASE}/onboarding/intake?token=sample",
            "expires_date": "31 Dec 2026",
        },
    ),
    SystemTemplate(
        code="onboarding_submitted",
        name="Onboarding submitted",
        description="Confirms to the requester that their onboarding batch was received.",
        subject="Received: {{ request_title }}",
        blocks=[
            _h(),
            {"type": "heading", "text": "We received your submission"},
            {
                "type": "intro",
                "text": (
                    "Hello {{ requester_name }},\n\n"
                    "We have received your onboarding submission '{{ request_title }}' with "
                    "{{ people_count }} {{ 'person' if people_count == 1 else 'people' }}.\n\n"
                    "Somebody will review it and you will get one more email when it is done. "
                    "Your original link now shows the status of each person."
                ),
            },
            _f(_REPLY_NOTE),
        ],
        variables=[
            {"key": "requester_name", "label": "Requester Name", "sample": "Aina"},
            {"key": "request_title", "label": "Request Title", "sample": "ACME Sdn Bhd - Sales Team"},
            {"key": "people_count", "label": "People Count", "sample": "5"},
        ],
        sample={
            "requester_name": "Aina",
            "request_title": "ACME Sdn Bhd - Sales Team",
            "people_count": 5,
        },
    ),
    SystemTemplate(
        code="onboarding_completed",
        name="Onboarding completed",
        description="Sent to the requester once every approved person in the batch has been processed.",
        subject="Onboarding complete: {{ request_title }}",
        blocks=[
            _h(),
            {"type": "heading", "text": "Onboarding complete"},
            {
                "type": "intro",
                "text": "Hello {{ requester_name }},\n\nYour onboarding submission '{{ request_title }}' has been processed.",
            },
            {
                "type": "facts",
                "hide_empty": False,
                "rows": [
                    {"label": "Accounts created", "value": "{{ created }}"},
                    {"label": "Already existed", "value": "{{ skipped }}"},
                ],
            },
            {
                "type": "facts",
                "rows": [
                    {"label": "Could not be created", "value": "{{ failed if failed else '' }}"},
                ],
            },
            {
                "type": "custom_text",
                "html": (
                    "{% if failed %}<p>Somebody from the team will be in touch about the ones that failed.</p>{% endif %}"
                    "<p>Anybody who received an account has been emailed a link to set their password.</p>"
                ),
            },
            _f(_REPLY_NOTE),
        ],
        variables=[
            {"key": "requester_name", "label": "Requester Name", "sample": "Aina"},
            {"key": "request_title", "label": "Request Title", "sample": "ACME Sdn Bhd - Sales Team"},
            {"key": "created", "label": "Accounts Created", "sample": "4"},
            {"key": "skipped", "label": "Already Existed", "sample": "1"},
            {"key": "failed", "label": "Could Not Be Created", "sample": "0"},
        ],
        sample={
            "requester_name": "Aina",
            "request_title": "ACME Sdn Bhd - Sales Team",
            "created": 4,
            "skipped": 1,
            "failed": 0,
        },
    ),
]
