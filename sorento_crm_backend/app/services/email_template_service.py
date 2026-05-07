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
    {"key": "promotion.code", "label": "Promotion Code", "sample": "PROMO-001"},
    {"key": "promotion.name", "label": "Promotion Name", "sample": "Year-End Sale"},
    {"key": "promotion.start_date", "label": "Promotion Start Date", "sample": "2026-05-01"},
    {"key": "promotion.end_date", "label": "Promotion End Date", "sample": "2026-05-15"},
    {"key": "promotion.link", "label": "Promotion Link", "sample": "https://crm.example.com/marketing/promotions/{id}"},
    {"key": "promotion.days_until_end", "label": "Days Until Promotion Ends", "sample": "7"},
    {"key": "complaint.complaint_number", "label": "Complaint Number", "sample": "CMP-2026-0001"},
    {"key": "complaint.delivery_order_number", "label": "Complaint DO Number", "sample": "DO-12345"},
    {"key": "complaint.customer_name", "label": "Complaint Customer", "sample": "ACME Sdn Bhd"},
    {"key": "complaint.salesperson", "label": "Complaint Salesperson", "sample": "Jane"},
    {"key": "complaint.product_code", "label": "Complaint Product Code", "sample": "PRD-001"},
    {"key": "complaint.complaint_type", "label": "Complaint Type", "sample": "Damaged"},
    {"key": "complaint.status", "label": "Complaint Status", "sample": "approved"},
    {"key": "complaint.root_cause", "label": "Complaint Root Cause", "sample": "Manufacturing defect"},
    {"key": "complaint.resolution", "label": "Complaint Resolution", "sample": "Replacement issued"},
    {"key": "complaint.link", "label": "Complaint Link", "sample": "https://crm.example.com/complaint-management/complaints/{id}"},
    {"key": "today", "label": "Today (ISO date)", "sample": "2026-05-07"},
    {"key": "recipient.name", "label": "Recipient Name", "sample": "John Doe"},
    {"key": "recipient.email", "label": "Recipient Email", "sample": "john@example.com"},
]


def sample_context() -> dict[str, Any]:
    today = date.today()
    return {
        "promotion": {
            "code": "PROMO-001",
            "name": "Year-End Sale",
            "start_date": today.isoformat(),
            "end_date": today.isoformat(),
            "link": "https://crm.example.com/marketing/promotions/sample",
            "days_until_end": 7,
        },
        "complaint": {
            "id": "sample",
            "complaint_number": "CMP-2026-0001",
            "delivery_order_number": "DO-12345",
            "customer_name": "ACME Sdn Bhd",
            "salesperson": "Jane",
            "product_code": "PRD-001",
            "complaint_type": "Damaged",
            "status": "approved",
            "root_cause": "Manufacturing defect",
            "resolution": "Replacement issued",
            "link": "https://crm.example.com/complaint-management/complaints/sample",
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
