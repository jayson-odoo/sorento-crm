"""CRUD for quotation customer email templates (tokenized HTML)."""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.modules.commercial_core.models_quotation_email_template import QuotationEmailTemplate
from app.services.error_handler import handle_not_found, handle_validation_error


class QuotationEmailTemplateService:
    def __init__(self, db: Session):
        self.db = db

    def list_templates(self, *, active_only: bool = True) -> List[QuotationEmailTemplate]:
        q = self.db.query(QuotationEmailTemplate)
        if active_only:
            q = q.filter(QuotationEmailTemplate.is_active.is_(True))
        return q.order_by(QuotationEmailTemplate.sort_order.asc(), QuotationEmailTemplate.name.asc()).all()

    def get(self, template_id: str) -> QuotationEmailTemplate:
        row = self.db.query(QuotationEmailTemplate).filter(QuotationEmailTemplate.id == template_id).first()
        if not row:
            raise handle_not_found("Quotation email template", template_id)
        return row

    def get_default(self) -> Optional[QuotationEmailTemplate]:
        return (
            self.db.query(QuotationEmailTemplate)
            .filter(QuotationEmailTemplate.is_active.is_(True), QuotationEmailTemplate.is_default.is_(True))
            .order_by(QuotationEmailTemplate.sort_order.asc())
            .first()
        )

    def create(
        self,
        *,
        code: str,
        name: str,
        subject_template: str,
        body_html_template: str,
        is_active: bool = True,
        is_default: bool = False,
        sort_order: int = 0,
    ) -> QuotationEmailTemplate:
        c = (code or "").strip()
        if not c:
            raise handle_validation_error("code is required")
        exists = self.db.query(QuotationEmailTemplate).filter(QuotationEmailTemplate.code == c).first()
        if exists:
            raise handle_validation_error("Template code already exists")
        row = QuotationEmailTemplate(
            code=c,
            name=(name or "").strip() or c,
            subject_template=subject_template or "",
            body_html_template=body_html_template or "",
            is_active=bool(is_active),
            is_default=bool(is_default),
            sort_order=int(sort_order or 0),
        )
        self.db.add(row)
        self.db.flush()
        if row.is_default:
            self._clear_other_defaults(str(row.id))
            self.db.flush()
        self.db.refresh(row)
        return row

    def update(
        self,
        template_id: str,
        *,
        code: Optional[str] = None,
        name: Optional[str] = None,
        subject_template: Optional[str] = None,
        body_html_template: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_default: Optional[bool] = None,
        sort_order: Optional[int] = None,
    ) -> QuotationEmailTemplate:
        row = self.get(template_id)
        if code is not None:
            c = code.strip()
            if not c:
                raise handle_validation_error("code cannot be empty")
            clash = (
                self.db.query(QuotationEmailTemplate)
                .filter(QuotationEmailTemplate.code == c, QuotationEmailTemplate.id != template_id)
                .first()
            )
            if clash:
                raise handle_validation_error("Template code already exists")
            row.code = c
        if name is not None:
            row.name = name.strip() or row.code
        if subject_template is not None:
            row.subject_template = subject_template
        if body_html_template is not None:
            row.body_html_template = body_html_template
        if is_active is not None:
            row.is_active = bool(is_active)
        if sort_order is not None:
            row.sort_order = int(sort_order)
        if is_default is not None:
            row.is_default = bool(is_default)
        self.db.flush()
        if row.is_default:
            self._clear_other_defaults(str(row.id))
            self.db.flush()
        self.db.refresh(row)
        return row

    def _clear_other_defaults(self, keep_id: str) -> None:
        (
            self.db.query(QuotationEmailTemplate)
            .filter(QuotationEmailTemplate.id != keep_id, QuotationEmailTemplate.is_default.is_(True))
            .update({QuotationEmailTemplate.is_default: False}, synchronize_session=False)
        )

    def soft_delete(self, template_id: str) -> None:
        row = self.get(template_id)
        row.is_active = False
        row.is_default = False
        self.db.flush()
