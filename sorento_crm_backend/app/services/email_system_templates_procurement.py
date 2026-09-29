"""System email documents: procurement mails (#1349). Registered by email_system_templates.py.

Each entry follows the same shape as the auth/users/SLA entries there: brand header,
heading, intro, facts, one button, footer. Producers call
`EmailTemplateService(db).render_code(code, context)` and pass context only.
"""
from __future__ import annotations

from typing import Any, Optional

from app.services.email_system_templates_base import SystemTemplate

_SAMPLE_BASE = "https://crm.example.com"


def _h() -> dict[str, Any]:
    return {"type": "brand_header"}


def _f(note: Optional[str] = None) -> dict[str, Any]:
    return {"type": "footer", "note": note} if note else {"type": "footer"}


TEMPLATES: list[SystemTemplate] = []

# --------------------------------------------------------------------------- #
# Stock inquiry team notice                                                    #
# --------------------------------------------------------------------------- #

TEMPLATES.append(
    SystemTemplate(
        code="stock_inquiry_created",
        name="Stock inquiry team notice",
        description="Sent to a team (e.g. purchasing) one email to all when a stock inquiry needs its review.",
        subject="{{ heading }}",
        preheader="{{ intro | truncate(140, true, '...', 0) }}",
        blocks=[
            _h(),
            {"type": "heading", "text": "{{ heading }}"},
            {"type": "intro", "text": "{{ intro }}"},
            {"type": "button", "label": "Open stock inquiry", "url": "{{ view_url }}"},
            _f("This is a system-generated email. Please do not reply."),
        ],
        variables=[
            {"key": "heading", "label": "Heading / Subject", "sample": "Stock Inquiry pending purchasing review"},
            {
                "key": "intro",
                "label": "Intro Text",
                "sample": "Dear Purchasing Team,\n\nA stock inquiry has been approved and is now pending purchasing review.",
            },
            {"key": "view_url", "label": "Stock Inquiry Link", "sample": f"{_SAMPLE_BASE}/procurement-management/stock-inquiries/sample"},
        ],
        sample={
            "heading": "Stock Inquiry pending purchasing review",
            "intro": "Dear Purchasing Team,\n\nA stock inquiry has been approved and is now pending purchasing review.",
            "view_url": f"{_SAMPLE_BASE}/procurement-management/stock-inquiries/sample",
        },
    )
)

# --------------------------------------------------------------------------- #
# Purchase request / sponsorship form submitted (team notice)                  #
# --------------------------------------------------------------------------- #

TEMPLATES.append(
    SystemTemplate(
        code="purchase_request_submitted",
        name="Purchase request / sponsorship form submitted",
        description="Sent to the Project Sales team, one email to all, when a purchase request or sponsorship form is created or updated by an external integration.",
        subject="{{ heading }}",
        preheader="{{ intro | truncate(140, true, '...', 0) }}",
        blocks=[
            _h(),
            {"type": "heading", "text": "{{ heading }}"},
            {"type": "intro", "text": "Dear Project Sales Team,\n\n{{ intro }}"},
            {
                "type": "facts",
                "rows": [
                    {"label": "Reference", "value": "{{ purchase_request.request_number }}"},
                    {"label": "Project", "value": "{{ purchase_request.project_title }}"},
                ],
            },
            {"type": "button", "label": "Open request", "url": "{{ view_url }}"},
            _f("This is a system-generated email. Please do not reply."),
        ],
        variables=[
            {"key": "heading", "label": "Heading / Subject", "sample": "New purchase request created"},
            {"key": "intro", "label": "Intro Sentence", "sample": "A new purchase request has been created and requires your review."},
            {"key": "purchase_request.request_number", "label": "Request Number", "sample": "PR26-0319"},
            {"key": "purchase_request.project_title", "label": "Project Title", "sample": "HQ Renovation"},
            {"key": "view_url", "label": "Request Link", "sample": f"{_SAMPLE_BASE}/procurement-management/purchase-requests/sample"},
        ],
        sample={
            "heading": "New purchase request created",
            "intro": "A new purchase request has been created and requires your review.",
            "purchase_request": {"request_number": "PR26-0319", "project_title": "HQ Renovation"},
            "view_url": f"{_SAMPLE_BASE}/procurement-management/purchase-requests/sample",
        },
    )
)

# --------------------------------------------------------------------------- #
# Requester notified: approved / rejected                                     #
# --------------------------------------------------------------------------- #

TEMPLATES.append(
    SystemTemplate(
        code="purchase_request_requester_approved",
        name="Purchase request / sponsorship form approved (requester)",
        description="Sent to the user who requested approval when the purchase request or sponsorship form is approved.",
        subject="{{ purchase_request.type_label }} approved",
        preheader="{{ purchase_request.type_label }} {{ purchase_request.request_number }} has been approved.",
        blocks=[
            _h(),
            {"type": "heading", "text": "{{ purchase_request.type_label }} approved"},
            {"type": "intro", "text": "Your {{ purchase_request.type_label|lower }} has been approved."},
            {
                "type": "facts",
                "rows": [
                    {"label": "Reference", "value": "{{ purchase_request.request_number }}"},
                    {"label": "Project", "value": "{{ purchase_request.project_title }}"},
                ],
            },
            {"type": "button", "label": "View form", "url": "{{ view_url }}"},
            {"type": "link", "label": "Or paste this link into your browser:", "url": "{{ view_url }}"},
            _f(),
        ],
        variables=[
            {"key": "purchase_request.type_label", "label": "PR/Sponsorship Type Label", "sample": "Purchase Request"},
            {"key": "purchase_request.request_number", "label": "Request Number", "sample": "PR26-0319"},
            {"key": "purchase_request.project_title", "label": "Project Title", "sample": "HQ Renovation"},
            {"key": "view_url", "label": "View Form Link", "sample": f"{_SAMPLE_BASE}/view/request?token=sample"},
        ],
        sample={
            "purchase_request": {"type_label": "Purchase Request", "request_number": "PR26-0319", "project_title": "HQ Renovation"},
            "view_url": f"{_SAMPLE_BASE}/view/request?token=sample",
        },
    )
)

TEMPLATES.append(
    SystemTemplate(
        code="purchase_request_requester_rejected",
        name="Purchase request / sponsorship form rejected (requester)",
        description="Sent to the user who requested approval when the purchase request or sponsorship form is rejected.",
        subject="{{ purchase_request.type_label }} rejected",
        preheader="{{ purchase_request.type_label }} {{ purchase_request.request_number }} has been rejected.",
        blocks=[
            _h(),
            {"type": "heading", "text": "{{ purchase_request.type_label }} rejected"},
            {"type": "intro", "text": "Your {{ purchase_request.type_label|lower }} has been rejected."},
            {
                "type": "facts",
                "rows": [
                    {"label": "Reference", "value": "{{ purchase_request.request_number }}"},
                    {"label": "Project", "value": "{{ purchase_request.project_title }}"},
                ],
            },
            {"type": "button", "label": "View form", "url": "{{ view_url }}"},
            {"type": "link", "label": "Or paste this link into your browser:", "url": "{{ view_url }}"},
            _f(),
        ],
        variables=[
            {"key": "purchase_request.type_label", "label": "PR/Sponsorship Type Label", "sample": "Purchase Request"},
            {"key": "purchase_request.request_number", "label": "Request Number", "sample": "PR26-0319"},
            {"key": "purchase_request.project_title", "label": "Project Title", "sample": "HQ Renovation"},
            {"key": "view_url", "label": "View Form Link", "sample": f"{_SAMPLE_BASE}/view/request?token=sample"},
        ],
        sample={
            "purchase_request": {"type_label": "Purchase Request", "request_number": "PR26-0319", "project_title": "HQ Renovation"},
            "view_url": f"{_SAMPLE_BASE}/view/request?token=sample",
        },
    )
)

# --------------------------------------------------------------------------- #
# Approval link                                                                #
# --------------------------------------------------------------------------- #

TEMPLATES.append(
    SystemTemplate(
        code="purchase_request_approval_link",
        name="Purchase request / sponsorship form approval link",
        description="Sent to an approver with a one-time link to review and approve or reject a purchase request or sponsorship form.",
        subject="{{ purchase_request.type_label }} - Approval link",
        preheader="Review and approve {{ purchase_request.request_number }}.",
        blocks=[
            _h(),
            {"type": "heading", "text": "Review and approve"},
            {
                "type": "intro",
                "text": "You have been sent a one-time approval link for a {{ purchase_request.type_label|lower }}. Open the button below to approve or reject it (the link expires after use or after the expiry time).",
            },
            {
                "type": "facts",
                "rows": [
                    {"label": "Reference", "value": "{{ purchase_request.request_number }}"},
                    {"label": "Project", "value": "{{ purchase_request.project_title }}"},
                ],
            },
            {"type": "button", "label": "Review and approve", "url": "{{ approval_url }}"},
            {"type": "link", "label": "Or paste this link into your browser:", "url": "{{ approval_url }}"},
            _f(),
        ],
        variables=[
            {"key": "purchase_request.type_label", "label": "PR/Sponsorship Type Label", "sample": "Purchase Request"},
            {"key": "purchase_request.request_number", "label": "Request Number", "sample": "PR26-0319"},
            {"key": "purchase_request.project_title", "label": "Project Title", "sample": "HQ Renovation"},
            {"key": "approval_url", "label": "Approval Link", "sample": f"{_SAMPLE_BASE}/approval?token=sample"},
        ],
        sample={
            "purchase_request": {"type_label": "Purchase Request", "request_number": "PR26-0319", "project_title": "HQ Renovation"},
            "approval_url": f"{_SAMPLE_BASE}/approval?token=sample",
        },
    )
)
