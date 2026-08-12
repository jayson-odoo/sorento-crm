"""Email template CRUD + render."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.email_template import EmailTemplate
from app.services.error_handler import AppException
from app.services.templating import html_to_text, render_html, render_text


# Static catalog of variables the editor can suggest. Real automation runs may
# extend the context, but these are the documented placeholders.
TEMPLATE_VARIABLE_CATALOG: list[dict[str, Any]] = [
    {"key": "promotion.description", "label": "Promotion Description", "sample": "Year-End Sale"},
    {"key": "promotion.start_date", "label": "Promotion Start Date", "sample": "2026-05-01"},
    {"key": "promotion.end_date", "label": "Promotion End Date", "sample": "2026-05-15"},
    {"key": "promotion.link", "label": "Promotion Link", "sample": "https://crm.example.com/marketing/promotions/{id}"},
    {"key": "promotion.days_until_end", "label": "Days Until Promotion Ends", "sample": "7"},
    {"key": "promotions", "label": "All Expiring Promotions (loop with {% for p in promotions %})", "sample": "[ { name, start_date, end_date, link, days_until_end }, ... ]"},
    {"key": "promotions_count", "label": "Number Of Expiring Promotions", "sample": "5"},
    {"key": "batch_link", "label": "Expiring Promotions Batch Link (View all)", "sample": "https://crm.example.com/marketing-management/promotions?expiry_notify_batch_id=00000000-0000-0000-0000-000000000000"},
    {"key": "expiry_notify_batch_id", "label": "Expiry Notify Batch Id", "sample": "00000000-0000-0000-0000-000000000000"},
    {"key": "certificate.scheme", "label": "Certificate Scheme", "sample": "PPS"},
    {"key": "certificate.certificate_number", "label": "Certificate Number", "sample": "04424FC"},
    {"key": "certificate.certifying_body", "label": "Certifying Body", "sample": "IKRAM"},
    {"key": "certificate.valid_until", "label": "Certificate Valid Until", "sample": "2026-12-23"},
    {"key": "certificate.days_until_expiry", "label": "Days Until Certificate Expires", "sample": "30"},
    {"key": "certificate.covered_product_count", "label": "Covered Products", "sample": "68"},
    {"key": "certificate.link", "label": "Certificate Link", "sample": "https://crm.example.com/master-data-management/certificates/{id}"},
    {"key": "certificates", "label": "All Expiring Certificates (loop with {% for c in certificates %})", "sample": "[ { scheme, certificate_number, certifying_body, valid_until, days_until_expiry, covered_product_count, link }, ... ]"},
    {"key": "certificates_count", "label": "Number Of Expiring Certificates", "sample": "4"},
    {"key": "complaint.complaint_number", "label": "Complaint Number", "sample": "CMP-2026-0001"},
    {"key": "complaint.delivery_order_number", "label": "Complaint DO Number", "sample": "DO-12345"},
    {"key": "complaint.customer_name", "label": "Complaint Customer", "sample": "ACME Sdn Bhd"},
    {"key": "complaint.salesperson", "label": "Complaint Salesperson", "sample": "Jane"},
    {"key": "complaint.product_code", "label": "Complaint Product Code", "sample": "PRD-001"},
    {"key": "complaint.complaint_type", "label": "Complaint Type", "sample": "Damaged"},
    {"key": "complaint.status", "label": "Complaint Status", "sample": "approved"},
    {"key": "complaint.technical_team_response", "label": "Complaint Technical Response", "sample": "We have inspected the unit and will issue a replacement."},
    {"key": "complaint.root_cause", "label": "Complaint Root Cause", "sample": "Manufacturing defect"},
    {"key": "complaint.resolution", "label": "Complaint Resolution", "sample": "Replacement issued"},
    {"key": "complaint.link", "label": "Complaint Link", "sample": "https://crm.example.com/complaint-management/complaints/{id}"},
    {"key": "purchase_request.type_label", "label": "PR/Sponsorship Type Label", "sample": "Purchase Request"},
    {"key": "purchase_request.request_number", "label": "PR/Sponsorship Number", "sample": "PR26-0319"},
    {"key": "purchase_request.request_date", "label": "PR/Sponsorship Request Date", "sample": "2026-05-22"},
    {"key": "purchase_request.customer_name", "label": "PR/Sponsorship Customer", "sample": "ACME Sdn Bhd"},
    {"key": "purchase_request.project_title", "label": "PR/Sponsorship Project Title", "sample": "HQ Renovation"},
    {"key": "purchase_request.purpose", "label": "PR/Sponsorship Purpose", "sample": "Office equipment refresh"},
    {"key": "purchase_request.requested_by", "label": "PR/Sponsorship Requested By", "sample": "Jane Doe"},
    {"key": "purchase_request.approved_by", "label": "PR/Sponsorship Approved By", "sample": "Director Lim"},
    {"key": "purchase_request.approved_at", "label": "PR/Sponsorship Approved At", "sample": "2026-05-22T10:15:00"},
    {"key": "purchase_request.approval_comments", "label": "PR/Sponsorship Approval Comments", "sample": "Approved with notes"},
    {"key": "purchase_request.total_project_value", "label": "PR/Sponsorship Total Project Value", "sample": "1600000.00"},
    {"key": "purchase_request.total_project_value_text", "label": "PR/Sponsorship Total Value (Text)", "sample": "BULK ORDER EST RM1.6MIL"},
    {"key": "purchase_request.expected_delivery_date", "label": "PR/Sponsorship Expected Delivery", "sample": "2026-06-15"},
    {"key": "purchase_request.expected_po_date", "label": "PR/Sponsorship Expected PO Date", "sample": "2026-05-30"},
    {"key": "purchase_request.status", "label": "PR/Sponsorship Status", "sample": "approved"},
    {"key": "purchase_request.link", "label": "PR/Sponsorship Link", "sample": "https://crm.example.com/procurement-management/purchase-requests/{id}"},
    {"key": "today", "label": "Today (ISO date)", "sample": "2026-05-07"},
    {"key": "recipient.name", "label": "Recipient Name", "sample": "John Doe"},
    {"key": "recipient.email", "label": "Recipient Email", "sample": "john@example.com"},
]


def sample_context() -> dict[str, Any]:
    today = date.today()
    sample_certificate = {
        "id": "sample",
        "scheme": "PPS",
        "certificate_number": "04424FC",
        "certifying_body": "IKRAM",
        "issuer": "IKRAM QA Services Sdn Bhd",
        "title": "Product certification",
        "valid_from": today.isoformat(),
        "valid_until": today.isoformat(),
        "days_until_expiry": 30,
        "covered_product_count": 68,
        "link": "https://crm.example.com/master-data-management/certificates/sample",
    }
    sample_promo = {
        "code": "PROMO-001",
        "name": "Year-End Sale",
        "start_date": today.isoformat(),
        "end_date": today.isoformat(),
        "link": "https://crm.example.com/marketing/promotions/sample",
        "days_until_end": 7,
    }
    return {
        "promotion": sample_promo,
        "promotions": [
            sample_promo,
            {
                "code": "PROMO-002",
                "name": "Clearance Bonanza",
                "start_date": today.isoformat(),
                "end_date": today.isoformat(),
                "link": "https://crm.example.com/marketing/promotions/sample-2",
                "days_until_end": 7,
            },
        ],
        "promotions_count": 2,
        "batch_link": "https://crm.example.com/marketing-management/promotions?expiry_notify_batch_id=00000000-0000-0000-0000-000000000000",
        "expiry_notify_batch_id": "00000000-0000-0000-0000-000000000000",
        "certificate": sample_certificate,
        "certificates": [
            sample_certificate,
            {
                **sample_certificate,
                "id": "sample-2",
                "certificate_number": "WCM PC 000321",
                "certifying_body": "JBC",
                "covered_product_count": 12,
                "link": "https://crm.example.com/master-data-management/certificates/sample-2",
            },
        ],
        "certificates_count": 2,
        "complaint": {
            "id": "sample",
            "complaint_number": "CMP-2026-0001",
            "delivery_order_number": "DO-12345",
            "customer_name": "ACME Sdn Bhd",
            "salesperson": "Jane",
            "product_code": "PRD-001",
            "complaint_type": "Damaged",
            "status": "approved",
            "technical_team_response": "We have inspected the unit and will issue a replacement.",
            "root_cause": "Manufacturing defect",
            "resolution": "Replacement issued",
            "link": "https://crm.example.com/complaint-management/complaints/sample",
        },
        "purchase_request": {
            "id": "sample",
            "type": "purchase_request",
            "type_label": "Purchase Request",
            "request_number": "PR26-0319",
            "request_date": today.isoformat(),
            "customer_name": "ACME Sdn Bhd",
            "project_title": "HQ Renovation",
            "purpose": "Office equipment refresh",
            "requested_by": "Jane Doe",
            "approved_by": "Director Lim",
            "approved_at": today.isoformat(),
            "approval_comments": "Approved with notes",
            "total_project_value": "1600000.00",
            "total_project_value_text": "BULK ORDER EST RM1.6MIL",
            "expected_delivery_date": today.isoformat(),
            "expected_po_date": today.isoformat(),
            "expected_po_date_text": None,
            "status": "approved",
            "link": "https://crm.example.com/procurement-management/purchase-requests/sample",
        },
        "today": today.isoformat(),
        "recipient": {"name": "Sample Recipient", "email": "sample@example.com"},
    }


class EmailTemplateService:
    def __init__(self, db: Session):
        self.db = db

    def list(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> tuple[list[EmailTemplate], int]:
        q = self.db.query(EmailTemplate)
        if query and query.strip():
            term = f"%{query.strip()}%"
            q = q.filter(
                (EmailTemplate.code.ilike(term))
                | (EmailTemplate.name.ilike(term))
                | (EmailTemplate.subject.ilike(term))
            )
        if is_active is not None:
            q = q.filter(EmailTemplate.is_active.is_(is_active))
        total = q.count()
        rows = (
            q.order_by(EmailTemplate.updated_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )
        return rows, total

    def get(self, template_id: str) -> Optional[EmailTemplate]:
        return (
            self.db.query(EmailTemplate)
            .filter(EmailTemplate.id == template_id)
            .first()
        )

    def get_by_code(self, code: str) -> Optional[EmailTemplate]:
        return (
            self.db.query(EmailTemplate)
            .filter(EmailTemplate.code == code)
            .first()
        )

    def create(self, payload: dict[str, Any], user_id: Optional[str]) -> EmailTemplate:
        if self.get_by_code(payload["code"]):
            raise AppException(status_code=409, message=f"Email template with code '{payload['code']}' already exists")
        body_text = payload.get("body_text") or html_to_text(payload.get("body_html") or "")
        row = EmailTemplate(
            code=payload["code"],
            name=payload["name"],
            description=payload.get("description"),
            subject=payload["subject"],
            body_html=payload.get("body_html") or "",
            body_text=body_text,
            is_active=payload.get("is_active", True),
            created_by_user_id=user_id,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update(self, template_id: str, payload: dict[str, Any]) -> EmailTemplate:
        row = self.get(template_id)
        if not row:
            raise AppException(status_code=404, message="Email template not found")
        if "code" in payload and payload["code"] and payload["code"] != row.code:
            existing = self.get_by_code(payload["code"])
            if existing and str(existing.id) != str(row.id):
                raise AppException(status_code=409, message=f"Email template with code '{payload['code']}' already exists")
        for field in ("code", "name", "description", "subject", "body_html", "is_active"):
            if field in payload and payload[field] is not None:
                setattr(row, field, payload[field])
        if "body_text" in payload and payload["body_text"] is not None:
            row.body_text = payload["body_text"]
        elif "body_html" in payload and payload["body_html"] is not None:
            row.body_text = html_to_text(payload["body_html"])
        row.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete(self, template_id: str) -> None:
        from app.models.automation import Automation

        row = self.get(template_id)
        if not row:
            raise AppException(status_code=404, message="Email template not found")
        active_automations = (
            self.db.query(Automation)
            .filter(
                Automation.email_template_id == template_id,
                Automation.enabled.is_(True),
            )
            .count()
        )
        if active_automations:
            raise AppException(
                status_code=409,
                message=f"Cannot delete: {active_automations} active automation(s) reference this template. Disable or update them first.",
            )
        self.db.delete(row)
        self.db.commit()

    def render(
        self,
        template: EmailTemplate,
        context: dict[str, Any],
    ) -> dict[str, str]:
        subject = render_text(str(template.subject or ""), context)
        body_html = render_html(str(template.body_html or ""), context)
        body_text_source = template.body_text if template.body_text else None
        if body_text_source:
            body_text = render_text(str(body_text_source), context)
        else:
            body_text = html_to_text(body_html)
        return {"subject": subject, "body_html": body_html, "body_text": body_text}

    def preview(
        self,
        template_id: str,
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, str]:
        template = self.get(template_id)
        if not template:
            raise AppException(status_code=404, message="Email template not found")
        ctx = context if context else sample_context()
        return self.render(template, ctx)
