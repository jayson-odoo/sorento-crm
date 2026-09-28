"""Email template CRUD + render."""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.email_template import EmailTemplate
from app.services.email_layout import (
    FONT_STACKS,
    EmailDocument,
    EmailTheme,
    ResolvedTheme,
    first_company_logo,
    implicit_document,
    load_theme,
    parse_document,
    render_document,
    resolve_theme,
    theme_defaults,
)
from app.services.email_system_templates import CREDENTIAL_CODES, SYSTEM_TEMPLATES, get_system_template
from app.services.error_handler import AppException
from app.services.templating import html_to_text

logger = logging.getLogger(__name__)


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
    {"key": "handover.headline", "label": "Handover Headline (verbs)", "sample": "ORDER, AMEND"},
    {"key": "handover.subject_scope", "label": "Handover Subject Scope", "sample": "KL WAREHOUSE @ SO-26-0412"},
    {"key": "handover.orders", "label": "Handover Orders (loop: so_number, customer, project)", "sample": "[ { so_number, customer, project }, ... ]"},
    {"key": "handover.lines", "label": "Handover Lines (loop: so_date, so_number, location, item_code, qty, delivery_date, remark, was, attachments)", "sample": "[ { so_date, so_number, location, item_code, qty, delivery_date, remark, was: { qty, delivery_date }, attachments }, ... ]"},
    {"key": "handover.link", "label": "Handover Link", "sample": "https://crm.example.com/scm/order-inquiries/{id}"},
    {"key": "undo.headline", "label": "Undo Headline", "sample": "UNDONE"},
    {"key": "undo.so_number", "label": "Undo S/O Number", "sample": "SO-26-0412"},
    {"key": "undo.revision_no", "label": "Undo Revision Number", "sample": "3"},
    {"key": "undo.customer", "label": "Undo Customer", "sample": "Lim Hardware Sdn Bhd"},
    {"key": "undo.project", "label": "Undo Project", "sample": "Taman Melati Phase 2"},
    {"key": "undo.lines", "label": "Undo Lines (loop: item_code, qty, delivery_date, outcome)", "sample": "[ { item_code, qty, delivery_date, outcome }, ... ]"},
    {"key": "undo.link", "label": "Undo Link", "sample": "https://crm.example.com/scm/order-inquiries/{id}"},
    {"key": "actor.name", "label": "Actor Name", "sample": "Aina Rahman"},
    {"key": "actor.email", "label": "Actor Email", "sample": "aina@example.com"},
    {"key": "company.name", "label": "Company Name (from the email theme)", "sample": "Sorento"},
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
        "handover": {
            "headline": "ORDER, AMEND",
            "subject_scope": "KL WAREHOUSE @ SO-26-0412",
            "link": "https://crm.example.com/scm/order-inquiries/sample",
            "orders": [{"so_number": "SO-26-0412", "customer": "Lim Hardware Sdn Bhd", "project": "Taman Melati Phase 2"}],
            "lines": [
                {"so_date": today.isoformat(), "so_number": "SO-26-0412", "location": "KL WAREHOUSE", "item_code": "SRT-6060-GL", "qty": "120", "was": {"qty": "100"}, "delivery_date": today.isoformat(), "remark": "Split delivery", "attachments": []},
                {"so_date": today.isoformat(), "so_number": "SO-26-0412", "location": "KL WAREHOUSE", "item_code": "SRT-3030-MT", "qty": "80", "was": None, "delivery_date": today.isoformat(), "remark": "", "attachments": []},
            ],
        },
        "undo": {
            "headline": "UNDONE",
            "so_number": "SO-26-0412",
            "revision_no": 3,
            "customer": "Lim Hardware Sdn Bhd",
            "project": "Taman Melati Phase 2",
            "link": "https://crm.example.com/scm/order-inquiries/sample",
            "lines": [{"item_code": "SRT-6060-GL", "qty": "120", "delivery_date": today.isoformat(), "outcome": "Restored"}],
        },
        "actor": {"name": "Aina Rahman", "email": "aina@example.com"},
        "today": today.isoformat(),
        "recipient": {"name": "Sample Recipient", "email": "sample@example.com"},
    }


def sample_context_for(code: Optional[str]) -> dict[str, Any]:
    """The generic sample context, overlaid with a system template's own sample."""
    ctx = sample_context()
    st = get_system_template(code) if code else None
    if st is not None:
        ctx.update(st.sample)
    return ctx


def variables_for(code: Optional[str]) -> list[dict[str, Any]]:
    """The editor's catalog: a system template's own variables first, then the rest."""
    st = get_system_template(code) if code else None
    own = list(st.variables) if st is not None else []
    seen = {v["key"] for v in own}
    return own + [v for v in TEMPLATE_VARIABLE_CATALOG if v["key"] not in seen]


FONT_LABELS: dict[str, str] = {
    "system": "System (Apple, Segoe, Roboto)",
    "arial": "Arial",
    "helvetica": "Helvetica",
    "verdana": "Verdana",
    "trebuchet": "Trebuchet MS",
    "georgia": "Georgia (serif)",
}


def _mirror_body_html(doc: EmailDocument) -> str:
    """body_html kept equal to the custom text blocks (#1349 D3): search, the list and a
    downgrade that drops layout_json all keep a sensible body."""
    return "\n".join(b.html for b in doc.blocks if b.type == "custom_text" and b.html)


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

    @staticmethod
    def _refuse_credential_code(code: Optional[str]) -> None:
        if code and code in CREDENTIAL_CODES:
            raise AppException(
                status_code=422,
                message=f"'{code}' is a built-in security email and cannot be edited",
            )

    def create(self, payload: dict[str, Any], user_id: Optional[str]) -> EmailTemplate:
        self._refuse_credential_code(payload.get("code"))
        if self.get_by_code(payload["code"]):
            raise AppException(status_code=409, message=f"Email template with code '{payload['code']}' already exists")
        layout = payload.get("layout_json")
        doc = EmailDocument.model_validate(layout) if layout else None
        body_html = _mirror_body_html(doc) if doc is not None else (payload.get("body_html") or "")
        if doc is not None:
            # Derived from the blocks at render time unless the author typed one.
            body_text = payload.get("body_text") or None
        else:
            body_text = payload.get("body_text") or html_to_text(body_html)
        row = EmailTemplate(
            code=payload["code"],
            name=payload["name"],
            description=payload.get("description"),
            subject=payload["subject"],
            body_html=body_html,
            body_text=body_text,
            preheader=(payload.get("preheader") or None),
            layout_json=doc.model_dump(mode="json") if doc is not None else None,
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
        self._refuse_credential_code(payload.get("code") or row.code)
        if "code" in payload and payload["code"] and payload["code"] != row.code:
            existing = self.get_by_code(payload["code"])
            if existing and str(existing.id) != str(row.id):
                raise AppException(status_code=409, message=f"Email template with code '{payload['code']}' already exists")
        for field in ("code", "name", "description", "subject", "is_active"):
            if field in payload and payload[field] is not None:
                setattr(row, field, payload[field])
        if "preheader" in payload:
            row.preheader = payload["preheader"] or None
        layout = payload.get("layout_json")
        if layout:
            doc = EmailDocument.model_validate(layout)
            if row.layout_json is None:
                # First arrangement of a legacy template: a text part that was only ever
                # derived from the old body would freeze the mail's text to that body and
                # hide every block added now (review S1). Drop it so text derives from the
                # blocks; a hand-written text part (e.g. the OI pipe tables) is kept.
                derived_old = html_to_text(row.body_html or "")
                if (row.body_text or "").strip() == derived_old.strip():
                    row.body_text = None
                if (payload.get("body_text") or "").strip() == derived_old.strip():
                    payload["body_text"] = None
            row.layout_json = doc.model_dump(mode="json")
            row.body_html = _mirror_body_html(doc)
            if "body_text" in payload:
                row.body_text = payload["body_text"] or None
        else:
            if "body_html" in payload and payload["body_html"] is not None:
                row.body_html = payload["body_html"]
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

    # ------------------------------------------------------------------ render

    def theme(self) -> ResolvedTheme:
        """The effective theme, read once per service instance (an automation run renders
        one mail per recipient with the same service)."""
        cached = getattr(self, "_theme_cache", None)
        if cached is None:
            cached = load_theme(self.db)
            self._theme_cache = cached
        return cached

    def _with_company(self, context: Optional[dict[str, Any]], theme: ResolvedTheme) -> dict[str, Any]:
        ctx = dict(context or {})
        ctx.setdefault("company", {"name": theme.company_name})
        return ctx

    def _document_of(self, template: Any) -> EmailDocument:
        try:
            return parse_document(getattr(template, "layout_json", None), str(getattr(template, "body_html", "") or ""))
        except Exception as exc:  # noqa: BLE001 - a stored document that stopped validating
            logger.error("email template %s: layout_json invalid, using its body: %s", getattr(template, "code", "?"), exc)
            return implicit_document(str(getattr(template, "body_html", "") or ""))

    def render(
        self,
        template: EmailTemplate,
        context: dict[str, Any],
        theme: Optional[ResolvedTheme] = None,
    ) -> dict[str, str]:
        """Subject + branded HTML + text for one template. Never raises on template content
        and never returns `[template-error:...]` (email_layout.render_document falls back)."""
        theme = theme or self.theme()
        return render_document(
            self._document_of(template),
            subject=str(template.subject or ""),
            context=self._with_company(context, theme),
            theme=theme,
            preheader=getattr(template, "preheader", None),
            body_text=getattr(template, "body_text", None),
        ).as_dict()

    def render_code(self, code: str, context: dict[str, Any]) -> dict[str, str]:
        """Render the system mail `code`: the admin's row when present and active, else the
        built-in document (email_system_templates.py). Producers pass context, never HTML."""
        row = None if code in CREDENTIAL_CODES else self.get_by_code(code)
        if row is not None and bool(row.is_active):
            return self.render(row, context)
        st = get_system_template(code)
        if st is None:
            if row is not None:
                return self.render(row, context)
            raise KeyError(f"Unknown system email template code: {code}")
        theme = self.theme()
        return render_document(
            EmailDocument.model_validate(st.document()),
            subject=st.subject,
            context=self._with_company(context, theme),
            theme=theme,
            preheader=st.preheader,
            body_text=st.body_text,
        ).as_dict()

    def preview(
        self,
        template_id: str,
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, str]:
        template = self.get(template_id)
        if not template:
            raise AppException(status_code=404, message="Email template not found")
        ctx = context if context else sample_context_for(template.code)
        return self.render(template, ctx)

    def preview_draft(self, payload: dict[str, Any]) -> dict[str, str]:
        """Render an unsaved template (the editor's live preview). Nothing is stored."""

        class _Draft:
            pass

        draft = _Draft()
        draft.code = payload.get("code") or "draft"
        draft.subject = payload.get("subject") or ""
        draft.preheader = payload.get("preheader")
        draft.layout_json = payload.get("layout_json")
        draft.body_html = payload.get("body_html") or ""
        draft.body_text = payload.get("body_text") or None
        ctx = payload.get("context") or sample_context_for(payload.get("code"))
        return self.render(draft, ctx)  # type: ignore[arg-type]

    # ------------------------------------------------------------------- theme

    def _settings_row(self):
        from app.models.user import SystemSetting

        return self.db.query(SystemSetting).first()

    def get_theme(self) -> dict[str, Any]:
        settings = self._settings_row()
        stored = getattr(settings, "email_theme", None) if settings is not None else None
        theme = EmailTheme()
        if isinstance(stored, dict):
            clean = {}
            for key, value in stored.items():
                try:
                    clean[key] = getattr(EmailTheme.model_validate({key: value}), key)
                except Exception:  # noqa: BLE001 - shown as unset, default applies
                    continue
            theme = EmailTheme(**clean)
        return {
            "theme": theme,
            "defaults": self._defaults_theme(settings),
            "fonts": [{"value": k, "label": FONT_LABELS.get(k, k)} for k in FONT_STACKS],
        }

    def _defaults_theme(self, settings: Any) -> ResolvedTheme:
        return resolve_theme(None, theme_defaults(settings, first_company_logo(self.db)))

    def save_theme(self, theme: EmailTheme) -> dict[str, Any]:
        """A side-write: touches only system_settings.email_theme (#1349 D10)."""
        settings = self._settings_row()
        if settings is None:
            raise AppException(status_code=404, message="System settings not initialised")
        settings.email_theme = theme.model_dump(mode="json", exclude_none=True)
        self.db.commit()
        self._theme_cache = None
        return self.get_theme()

    def preview_theme(self, theme: EmailTheme) -> dict[str, str]:
        """One sample mail (password reset) under an UNSAVED theme."""
        settings = self._settings_row()
        resolved = resolve_theme(
            theme.model_dump(mode="json", exclude_none=True),
            theme_defaults(settings, first_company_logo(self.db)),
        )
        st = SYSTEM_TEMPLATES["auth_password_reset"]
        return render_document(
            EmailDocument.model_validate(st.document()),
            subject=st.subject,
            context=self._with_company(sample_context_for(st.code), resolved),
            theme=resolved,
            preheader=st.preheader,
        ).as_dict()

