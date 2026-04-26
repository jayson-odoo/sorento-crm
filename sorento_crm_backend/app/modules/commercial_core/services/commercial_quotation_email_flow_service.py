"""Preview and send quotation customer emails (terminal stage only) with PDF attachment."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.notification import Notification, NotificationDelivery
from app.models.user import SystemSetting
from app.modules.commercial_core.services.commercial_quotation_document_service import CommercialQuotationDocumentService
from app.services.notification_email import _smtp_config_from_settings, send_mime_email
from app.modules.commercial_core.services.quotation_email_template_service import QuotationEmailTemplateService
from app.utils.template_tokens import render_token_template


def _html_to_plain(html: str) -> str:
    if not html:
        return ""
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"[ \t\r\f\v]+", " ", text).strip()


class CommercialQuotationEmailFlowService:
    def __init__(self, db: Session):
        self.db = db
        self._doc = CommercialQuotationDocumentService(db)
        self._tpl = QuotationEmailTemplateService(db)

    def preview(
        self,
        revision_id: str,
        *,
        user_id: str,
        template_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        mq, rev = self._doc.get_revision_with_master(revision_id)
        self._doc.ensure_terminal_and_project_access(mq, user_id)
        ctx = self._doc.build_token_context(mq, rev)
        default_to = self._doc.default_customer_email(mq)
        filename = CommercialQuotationDocumentService.suggested_pdf_filename(mq, rev)

        subject = ""
        body_html = ""
        if template_id and str(template_id).strip():
            tpl = self._tpl.get(str(template_id).strip())
            if not tpl.is_active:
                d = self._tpl.get_default()
                tpl = d or tpl
            subject = render_token_template(tpl.subject_template, ctx)
            body_html = render_token_template(tpl.body_html_template, ctx)
        else:
            d = self._tpl.get_default()
            if d:
                subject = render_token_template(d.subject_template, ctx)
                body_html = render_token_template(d.body_html_template, ctx)

        token_keys = sorted(ctx.keys())
        return {
            "default_to": default_to,
            "subject": subject,
            "body_html": body_html,
            "pdf_attachment_filename": filename,
            "token_keys": token_keys,
        }

    def send(
        self,
        revision_id: str,
        *,
        user_id: str,
        to_list: List[str],
        cc_list: List[str],
        bcc_list: List[str],
        subject: str,
        body_html: str,
    ) -> Tuple[bool, Optional[str]]:
        mq, rev = self._doc.get_revision_with_master(revision_id)
        self._doc.ensure_terminal_and_project_access(mq, user_id)
        pdf, filename = self._doc.generate_quotation_pdf(revision_id, user_id=user_id)

        to_clean = [x.strip() for x in to_list if x and str(x).strip()]
        if not to_clean:
            return False, "At least one recipient is required"

        settings = self.db.query(SystemSetting).first()
        smtp_config = _smtp_config_from_settings(settings) if settings else None
        plain = _html_to_plain(body_html)

        err = send_mime_email(
            to_list=to_clean,
            cc_list=[x.strip() for x in cc_list if x and str(x).strip()],
            bcc_list=[x.strip() for x in bcc_list if x and str(x).strip()],
            subject=subject.strip() or "Quotation",
            body_text=plain or subject,
            body_html=body_html or None,
            attachments=[(filename, "application/pdf", pdf)],
            smtp_config=smtp_config,
        )
        if err:
            return False, err

        n = Notification(
            user_id=user_id,
            type="quotation_email",
            title=(subject.strip() or "Quotation")[:512],
            body=(plain[:20000] if plain else None),
            data={
                "recipient_emails": to_clean,
                "cc_emails": [x.strip() for x in cc_list if x and str(x).strip()],
                "bcc_emails": [x.strip() for x in bcc_list if x and str(x).strip()],
                "body_html": body_html,
                "master_quotation_id": str(mq.id),
                "quotation_revision_id": str(revision_id),
            },
            source_entity_type="commercial_quotation_revision",
            source_entity_id=str(revision_id),
            event_type=None,
        )
        self.db.add(n)
        self.db.flush()
        self.db.add(
            NotificationDelivery(
                notification_id=n.id,
                channel="email",
                status="sent",
                sent_at=datetime.utcnow(),
            )
        )
        self.db.flush()
        return True, None
