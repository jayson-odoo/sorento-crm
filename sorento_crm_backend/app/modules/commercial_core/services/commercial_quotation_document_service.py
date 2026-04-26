"""Quotation PDF (HTML + Playwright) and shared messaging context for email templates."""
from __future__ import annotations

import base64
import logging
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session, joinedload

from app.modules.commercial_core.models import (
    CommercialMasterQuotation,
    CommercialQuotationRevision,
    CommercialTender,
    CommercialProject,
    CommercialLead,
)
from app.models.order import CustomerContact
from app.models.resources import Attachment
from app.models.user import User, SystemSetting
from app.modules.commercial_core.services.commercial_hierarchy_service import CommercialHierarchyError
from app.modules.commercial_core.services.commercial_quotation_price_policy import (
    compute_snapshot_line_net,
    compute_snapshot_subtotal,
    snapshot_order_items,
    snapshot_quotation_meta,
    user_may_access_project_quotations,
)
from app.services.error_handler import handle_not_found
from app.services.s3_service import S3Service

logger = logging.getLogger(__name__)

# Templates stay in app/templates/ (shared location, not module-specific)
_PRINT_TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "templates" / "quotation"


def _jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_PRINT_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )


def _lead_delivery_address(qualification: Any) -> str:
    if not isinstance(qualification, dict):
        return ""
    q = qualification

    def _s(key: str) -> str:
        v = q.get(key)
        if v is None or v == "":
            return ""
        return str(v).strip()

    parts = [
        _s("address_line_1"),
        _s("address_line_2"),
        _s("city"),
        _s("postcode"),
        _s("state"),
        _s("country"),
    ]
    parts = [p for p in parts if p]
    return ", ".join(parts) if parts else ""


def _money(d: Decimal, currency: str) -> str:
    return f"{d.quantize(Decimal('0.01')):,.2f} {currency}".strip()


def _format_date(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip()
    return s[:10] if len(s) >= 10 else s


def _download_attachment_bytes(att: Attachment) -> bytes:
    fp = (att.file_path or "").strip()
    if fp.startswith("http://") or fp.startswith("https://"):
        with httpx.Client(timeout=30.0) as client:
            r = client.get(fp)
            r.raise_for_status()
            return r.content
    svc = S3Service()
    return svc.download_file(fp)


def _first_image_data_url(db: Session, attachment_ids: List[str]) -> Optional[str]:
    for raw_id in attachment_ids:
        aid = (raw_id or "").strip()
        if not aid:
            continue
        att = (
            db.query(Attachment)
            .filter(Attachment.id == aid, Attachment.is_deleted.is_(False))
            .first()
        )
        if not att:
            continue
        mime = (att.mime_type or "image/jpeg").strip() or "image/jpeg"
        if not mime.startswith("image/"):
            continue
        try:
            data = _download_attachment_bytes(att)
        except Exception as e:
            logger.warning("Quotation PDF: could not load image attachment %s: %s", aid, e)
            continue
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{b64}"
    return None


def _attachment_file_names(db: Session, attachment_ids: List[str]) -> List[str]:
    names: List[str] = []
    for raw_id in attachment_ids:
        aid = (raw_id or "").strip()
        if not aid:
            continue
        att = (
            db.query(Attachment)
            .filter(Attachment.id == aid, Attachment.is_deleted.is_(False))
            .first()
        )
        if not att:
            continue
        fn = (att.original_filename or "").strip() or (att.stored_filename or "").strip()
        if fn:
            names.append(fn)
    return names


def _notes_pic_name(notes: Optional[str]) -> str:
    raw = (notes or "").splitlines()
    for line in raw:
        t = line.strip()
        if not t:
            continue
        if ":" not in t:
            continue
        key, val = t.split(":", 1)
        if key.strip().lower() == "pic name":
            return val.strip()
    return ""


def _company_logo_data_url(settings: Optional[SystemSetting]) -> str:
    if not settings:
        return ""
    src = (settings.logo or "").strip()
    if not src:
        return ""
    try:
        if src.startswith("http://") or src.startswith("https://"):
            with httpx.Client(timeout=30.0) as client:
                r = client.get(src)
                r.raise_for_status()
                data = r.content
            content_type = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
            mime = content_type if content_type.startswith("image/") else "image/png"
        else:
            data = S3Service().download_file(src)
            s = src.lower()
            if s.endswith(".jpg") or s.endswith(".jpeg"):
                mime = "image/jpeg"
            elif s.endswith(".gif"):
                mime = "image/gif"
            elif s.endswith(".webp"):
                mime = "image/webp"
            elif s.endswith(".svg"):
                mime = "image/svg+xml"
            else:
                mime = "image/png"
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception as e:
        logger.warning("Quotation PDF: could not load system logo: %s", e)
        return ""


class CommercialQuotationDocumentService:
    def __init__(self, db: Session):
        self.db = db

    def get_revision_with_master(self, revision_id: str) -> Tuple[CommercialMasterQuotation, CommercialQuotationRevision]:
        rev = (
            self.db.query(CommercialQuotationRevision)
            .filter(CommercialQuotationRevision.id == revision_id)
            .first()
        )
        if not rev:
            raise handle_not_found("Quotation revision", revision_id)
        mq = (
            self.db.query(CommercialMasterQuotation)
            .options(
                joinedload(CommercialMasterQuotation.quotation_stage),
                joinedload(CommercialMasterQuotation.tender)
                .joinedload(CommercialTender.project)
                .joinedload(CommercialProject.lead)
                .joinedload(CommercialLead.customer),
                joinedload(CommercialMasterQuotation.owner),
            )
            .filter(CommercialMasterQuotation.id == rev.master_quotation_id)
            .first()
        )
        if not mq:
            raise handle_not_found("Master quotation", str(rev.master_quotation_id))
        return mq, rev

    def ensure_terminal_and_project_access(self, mq: CommercialMasterQuotation, user_id: str) -> None:
        st = mq.quotation_stage
        if not st or not bool(st.is_terminal):
            raise CommercialHierarchyError(
                "Print and email are only available when the quotation is in a terminal workflow stage."
            )
        t = mq.tender
        if not t:
            raise CommercialHierarchyError("Tender not loaded for this quotation.")
        pid = str(t.project_id)
        if not user_may_access_project_quotations(self.db, pid, user_id):
            raise CommercialHierarchyError("You do not have access to this quotation.")

    def default_customer_email(self, mq: CommercialMasterQuotation) -> str:
        lead = None
        if mq.tender and mq.tender.project:
            lead = mq.tender.project.lead
        if not lead:
            return ""
        cust = lead.customer
        if cust and (cust.email or "").strip():
            return (cust.email or "").strip()
        cc = (
            self.db.query(CustomerContact)
            .filter(
                CustomerContact.customer_id == lead.customer_id,
                CustomerContact.contact_role == "main",
            )
            .order_by(CustomerContact.sort_order.asc(), CustomerContact.created_at.asc())
            .first()
        )
        if cc and (cc.email or "").strip():
            return (cc.email or "").strip()
        cc2 = (
            self.db.query(CustomerContact)
            .filter(CustomerContact.customer_id == lead.customer_id)
            .order_by(CustomerContact.sort_order.asc(), CustomerContact.created_at.asc())
            .first()
        )
        if cc2 and (cc2.email or "").strip():
            return (cc2.email or "").strip()
        return ""

    def build_token_context(self, mq: CommercialMasterQuotation, rev: CommercialQuotationRevision) -> Dict[str, str]:
        snap = dict(rev.pricing_snapshot or {})
        meta = snapshot_quotation_meta(snap)
        subtotal = compute_snapshot_subtotal(snap)
        currency = (mq.quoted_currency or "MYR").strip() or "MYR"

        client_name = ""
        client_address = ""
        lead = mq.tender.project.lead if mq.tender and mq.tender.project else None
        if lead:
            if lead.customer:
                client_name = (lead.customer.customer_name or "").strip()
            client_address = _lead_delivery_address(lead.qualification)
        clabel = meta.get("customer_label")
        if isinstance(clabel, str) and clabel.strip():
            client_name = clabel.strip()

        owner_name = ""
        if mq.owner:
            owner_name = ((mq.owner.name or "").strip() or (mq.owner.email or "").strip())
        suid = meta.get("salesperson_user_id")
        if suid and str(suid).strip():
            su = self.db.query(User).filter(User.id == str(suid).strip()).first()
            if su:
                owner_name = ((su.name or "").strip() or (su.email or "").strip()) or owner_name

        tender_code = mq.tender.tender_code if mq.tender else ""
        return {
            "quotation_code": (mq.quotation_code or "").strip(),
            "tender_code": tender_code or "",
            "revision_number": str(rev.revision_number) if rev.revision_number is not None else "",
            "client_name": client_name,
            "client_address": client_address,
            "valid_until": _format_date(mq.valid_until),
            "payment_terms": (mq.payment_terms or "").strip() if getattr(mq, "payment_terms", None) else "",
            "quoted_total": _money(subtotal, currency),
            "currency": currency,
            "sales_owner": owner_name,
            "project_title": (mq.tender.project.title if mq.tender and mq.tender.project else "") or "",
            "description": (mq.title or "").strip(),
        }

    def build_print_model(self, mq: CommercialMasterQuotation, rev: CommercialQuotationRevision) -> Dict[str, Any]:
        snap = dict(rev.pricing_snapshot or {})
        meta = snapshot_quotation_meta(snap)
        currency = (mq.quoted_currency or "MYR").strip() or "MYR"

        ctx = self.build_token_context(mq, rev)
        details = dict(mq.commercial_details or {}) if isinstance(mq.commercial_details, dict) else {}
        desc = mq.title
        rem = details.get("remark")
        if isinstance(rem, str) and rem.strip():
            remark = rem.strip()
        else:
            remark = ""

        lead = mq.tender.project.lead if mq.tender and mq.tender.project else None
        customer = lead.customer if lead and lead.customer else None
        customer_phone = (meta.get("customer_phone") or "").strip() if isinstance(meta.get("customer_phone"), str) else ""
        if not customer_phone and customer and (customer.phone_number or "").strip():
            customer_phone = (customer.phone_number or "").strip()
        customer_email = (meta.get("customer_email") or "").strip() if isinstance(meta.get("customer_email"), str) else ""
        if not customer_email and customer and (customer.email or "").strip():
            customer_email = (customer.email or "").strip()
        customer_pic = (meta.get("customer_pic_name") or "").strip() if isinstance(meta.get("customer_pic_name"), str) else ""
        if not customer_pic and customer:
            customer_pic = _notes_pic_name(customer.notes)
        attention_to = (
            (meta.get("customer_attention_to") or "").strip()
            if isinstance(meta.get("customer_attention_to"), str)
            else ""
        )
        if not attention_to:
            attention_to = customer_pic
        seller_reference = (meta.get("seller_reference") or "").strip() if isinstance(meta.get("seller_reference"), str) else ""
        customer_reference = (
            (meta.get("customer_reference") or "").strip() if isinstance(meta.get("customer_reference"), str) else ""
        )
        seller_name = ""
        seller_mobile = ""
        if mq.owner:
            seller_name = ((mq.owner.name or "").strip() or (mq.owner.email or "").strip())
            seller_mobile = (mq.owner.contact_number or "").strip()
        suid = meta.get("salesperson_user_id")
        if suid and str(suid).strip():
            su = self.db.query(User).filter(User.id == str(suid).strip()).first()
            if su:
                seller_name = ((su.name or "").strip() or (su.email or "").strip()) or seller_name
                seller_mobile = (su.contact_number or "").strip() or seller_mobile

        settings = self.db.query(SystemSetting).first()
        company_logo_data_url = _company_logo_data_url(settings)
        company_name = (settings.name or "").strip() if settings and settings.name else "Quotation"
        company_address = (settings.address or "").strip() if settings and settings.address else ""

        lines_out: List[Dict[str, Any]] = []
        optional_lines_out: List[Dict[str, Any]] = []
        required_subtotal = Decimal("0")
        for line in snapshot_order_items(snap):
            ids_raw = line.get("product_image_attachment_ids")
            att_ids: List[str] = []
            if isinstance(ids_raw, list):
                att_ids = [str(x) for x in ids_raw if x is not None and str(x).strip()]
            img = _first_image_data_url(self.db, att_ids)
            tech_raw = line.get("technical_spec_attachment_ids")
            tech_ids: List[str] = []
            if isinstance(tech_raw, list):
                tech_ids = [str(x) for x in tech_raw if x is not None and str(x).strip()]
            tech_names = _attachment_file_names(self.db, tech_ids)
            tech_image = _first_image_data_url(self.db, tech_ids)
            qty_raw = line.get("qty") if line.get("qty") is not None else line.get("quantity")
            qty_s = str(qty_raw if qty_raw not in (None, "") else "1")
            net = compute_snapshot_line_net(line)
            up_raw = line.get("unit_price")
            try:
                up_dec = Decimal(str(up_raw)) if up_raw not in (None, "") else Decimal("0")
            except Exception:
                up_dec = Decimal("0")
            is_optional = bool(line.get("is_optional"))
            line_out = {
                "description": str(line.get("description") or "").strip() or "—",
                "brand": str(line.get("brand") or "").strip(),
                "product_code": str(line.get("product_code") or "").strip(),
                "is_optional": is_optional,
                "qty": qty_s,
                "uom": str(line.get("uom_code") or line.get("uom") or "").strip(),
                "unit_price": _money(up_dec, currency),
                "line_total": _money(net, currency),
                "image_data_url": img,
                "technical_spec_names": tech_names,
                "technical_spec_image_data_url": tech_image,
            }
            if is_optional:
                line_out["line_total"] = ""
                optional_lines_out.append(line_out)
            else:
                required_subtotal += net
                lines_out.append(line_out)

        notes_meta = meta.get("notes")
        notes_str = str(notes_meta).strip() if notes_meta else ""

        return {
            "company_label": company_name,
            "company_logo_data_url": company_logo_data_url,
            "company_address": company_address,
            "quotation_code": ctx["quotation_code"],
            "revision_number": rev.revision_number,
            "project_title": ctx["project_title"] or "",
            "seller_reference": seller_reference,
            "customer_reference": customer_reference,
            "valid_until": ctx["valid_until"],
            "payment_terms": ctx["payment_terms"] or "",
            "client_name": ctx["client_name"] or "—",
            "client_address": ctx["client_address"],
            "client_phone": customer_phone,
            "client_email": customer_email,
            "attention_to": attention_to,
            "lines": lines_out,
            "optional_lines": optional_lines_out,
            "subtotal": _money(required_subtotal, currency),
            "discount_label": "",
            "discount_amount": "",
            "grand_total": _money(required_subtotal, currency),
            "currency": currency,
            "description": notes_str,
            "remark": remark,
            "seller_name": seller_name,
            "seller_mobile": seller_mobile,
        }

    @staticmethod
    def render_print_html(model: Dict[str, Any]) -> str:
        env = _jinja_env()
        tpl = env.get_template("print.html")
        return tpl.render(**model)

    @staticmethod
    def html_to_pdf_bytes(html: str) -> bytes:
        from playwright.sync_api import sync_playwright

        # Args help headless Chromium in Docker / low-shm environments; harmless on macOS.
        launch_kwargs: Dict[str, Any] = {
            "headless": True,
            "args": ["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu"],
        }
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(**launch_kwargs)
            except Exception as exc:
                err = str(exc).lower()
                if "executable doesn't exist" in err or "download new browsers" in err:
                    raise RuntimeError(
                        "Playwright Chromium is not installed. From the same Python environment as the API, run: "
                        "python -m playwright install chromium"
                    ) from exc
                raise
            try:
                page = browser.new_page()
                # Static quotation HTML: "load" is reliable; "networkidle" often flakes on data: URLs / fonts.
                page.set_content(html, wait_until="load", timeout=60_000)
                return page.pdf(
                    format="A4",
                    print_background=True,
                    margin={"top": "12mm", "bottom": "12mm", "left": "12mm", "right": "12mm"},
                )
            finally:
                browser.close()

    @staticmethod
    def suggested_pdf_filename(mq: CommercialMasterQuotation, rev: CommercialQuotationRevision) -> str:
        safe_code = "".join(
            c if c.isalnum() or c in ("-", "_") else "_" for c in (mq.quotation_code or "quotation")
        )
        return f"quotation_{safe_code}_rev{rev.revision_number}.pdf"

    def generate_quotation_pdf(self, revision_id: str, *, user_id: str) -> Tuple[bytes, str]:
        mq, rev = self.get_revision_with_master(revision_id)
        self.ensure_terminal_and_project_access(mq, user_id)
        model = self.build_print_model(mq, rev)
        html = CommercialQuotationDocumentService.render_print_html(model)
        pdf = self.html_to_pdf_bytes(html)
        filename = self.suggested_pdf_filename(mq, rev)
        return pdf, filename
