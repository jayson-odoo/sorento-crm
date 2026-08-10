"""Render a Product Inquiry Form PDF via WeasyPrint.

Decoupled from the request path: called by the RQ task
``generate_stock_inquiry_pdf``. The layout mirrors the PRODUCT INQUIRY FORM the
detail page renders (bordered label/value table, same row order and wording) so a
printed copy and the screen agree, followed by the record's image attachments
embedded inline and the remaining attachments listed by filename.

Internal-only fields (SLA tier/assignee, handling lock, audit trail) are
deliberately excluded - the same rule the complaint PDF follows.

The document heading is "PRODUCT INQUIRY FORM" because that is what the detail
page has always printed at the top of this form; the row labels and the 404 text
mirror the rest of the UI, which still says Stock Inquiry.
"""
import logging
from datetime import date, datetime
from html import escape
from typing import Optional

from sqlalchemy.orm import Session

from app.models.procurement import StockInquiry
from app.services.document_number import display_document_number
from app.services.pdf_render import (
    PDFRenderingUnavailable,
    embedded_images,
    names_list_html,
    non_image_names,
    photos_section_html,
    render_html,
)

logger = logging.getLogger(__name__)

__all__ = ["StockInquiryPDFService", "PDFRenderingUnavailable"]

# Same wording as STOCK_INQUIRY_STATUS_LABELS on the frontend, so the printed
# status matches the pill on the detail page.
_STATUS_LABELS = {
    "new": "New",
    "pending_project_sales": "Pending project sales",
    "pending_purchasing": "Pending purchasing",
    "rejected": "Rejected",
    "responded": "Responded",
    "updated": "Updated",  # legacy
    "voided": "Voided",
}


def _fmt(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    s = str(value).strip()
    return escape(s) if s else "—"


def _row(label: str, value) -> str:
    return f"<tr><th>{escape(label)}</th><td>{_fmt(value)}</td></tr>"


class StockInquiryPDFService:
    def __init__(self, db: Session):
        self.db = db

    def build_filename(self, inquiry: StockInquiry) -> str:
        # The filename carries the revision too, so two revisions of the same
        # inquiry do not land in a downloads folder as one overwritten file (UAC N5).
        num = (display_document_number(inquiry) or str(inquiry.id)).strip()
        safe = "".join(c for c in num if c.isalnum() or c in ("-", "_")) or "product-inquiry"
        return f"product-inquiry-{safe}.pdf"

    def _load(self, inquiry_id: str) -> StockInquiry:
        inquiry = self.db.query(StockInquiry).filter(StockInquiry.id == str(inquiry_id)).first()
        if inquiry is None:
            from app.services.error_handler import handle_not_found
            raise handle_not_found("Stock Inquiry", inquiry_id)
        return inquiry

    def _attachment_links(self, inquiry: StockInquiry) -> list:
        """Linked attachments from the generic entity_attachment_links table - the
        same source the detail UI and the Excel export read. Each link exposes
        ``.attachment`` (an Attachment row)."""
        try:
            from app.services.entity_attachment_service import EntityAttachmentService
            return EntityAttachmentService(self.db).list_links("stock_inquiry", str(inquiry.id)) or []
        except Exception:  # pragma: no cover - never break the PDF on link lookup
            logger.warning(
                "product inquiry PDF: failed to list entity attachment links", exc_info=True
            )
            return []

    def _salesperson(self, inquiry: StockInquiry) -> Optional[str]:
        """Requestor display name, resolved live from the FK with the stored text
        column as fallback - the same precedence the detail page uses."""
        return getattr(inquiry, "salesperson_contact_name", None) or getattr(
            inquiry, "salesperson", None
        )

    def _status_label(self, inquiry: StockInquiry) -> str:
        raw = (getattr(inquiry, "status", None) or "").strip()
        if not raw:
            return "—"
        return _STATUS_LABELS.get(raw, raw.replace("_", " ").title())

    def _html(self, inquiry: StockInquiry) -> str:
        form_rows = "".join(
            [
                _row("Date", getattr(inquiry, "created_at", None)),
                _row("Stock Inquiry Number", display_document_number(inquiry) or None),
                _row("Sales Person", self._salesperson(inquiry)),
                _row("Product Code", getattr(inquiry, "product_code", None)),
                _row("Item Description", getattr(inquiry, "item_description", None)),
                _row("Project Customer", getattr(inquiry, "project_customer", None)),
                _row("Project Name", getattr(inquiry, "project_name", None)),
                _row("Qty", getattr(inquiry, "quantity", None)),
                _row("Delivery Date", getattr(inquiry, "delivery_date", None)),
                _row("Remark", getattr(inquiry, "remark", None)),
                _row("Additional Remark", getattr(inquiry, "additional_remark", None)),
                _row(
                    "Comment / Reply by Purchasing",
                    getattr(inquiry, "purchasing_response", None),
                ),
            ]
        )

        # Rejection / reopen / void reasons are rows on the on-screen form too, so
        # they print - but only when set, exactly as the page renders them.
        extra_rows = "".join(
            [
                _row("Rejection Reason", getattr(inquiry, "rejection_reason", None))
                if getattr(inquiry, "rejection_reason", None)
                else "",
                _row("Reopen Reason", getattr(inquiry, "reopen_reason", None))
                if getattr(inquiry, "reopen_reason", None)
                else "",
                _row("Void Reason", getattr(inquiry, "void_reason", None))
                if getattr(inquiry, "void_reason", None)
                else "",
            ]
        )

        links = self._attachment_links(inquiry)
        photos_html = photos_section_html(
            embedded_images(links, context="product inquiry PDF")
        )
        other_html = names_list_html(non_image_names(links))

        title_num = _fmt(display_document_number(inquiry) or None)
        status = escape(self._status_label(inquiry))

        return f"""<!doctype html><html><head><meta charset="utf-8"/>
<style>
  @page {{ size: A4; margin: 16mm 14mm; }}
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; color: #1a1a1a; font-size: 11px; }}
  .doc-title {{ text-align: center; font-size: 15px; font-weight: bold; text-transform: uppercase;
                letter-spacing: .06em; text-decoration: underline; padding: 8px 0 10px; }}
  .meta {{ color: #666; font-size: 9px; text-align: center; margin-bottom: 12px; }}
  table.form {{ width: 100%; border-collapse: collapse; border: 2px solid #1a1a1a; }}
  table.form th, table.form td {{ border: 1px solid #b8b8b8; padding: 6px 8px; vertical-align: top;
                                  text-align: left; white-space: pre-wrap; }}
  table.form th {{ width: 34%; background: #f2f2f2; font-weight: bold; text-transform: uppercase;
                   letter-spacing: .03em; font-size: 10px; }}
  h2 {{ font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: #444;
        border-bottom: 1px solid #ccc; padding-bottom: 3px; margin: 16px 0 8px; }}
  .empty {{ color: #999; font-style: italic; }}
  .photos {{ display: flex; flex-wrap: wrap; gap: 10px; }}
  figure {{ margin: 0; width: 30%; }}
  figure img {{ width: 100%; border: 1px solid #ddd; border-radius: 3px; }}
  figcaption {{ font-size: 9px; color: #777; margin-top: 2px; word-break: break-all; }}
  ul {{ margin: 4px 0 0 16px; padding: 0; }}
  .footer {{ margin-top: 22px; color: #999; font-size: 9px; border-top: 1px solid #eee; padding-top: 6px; }}
</style></head><body>
  <div class="doc-title">Product Inquiry Form</div>
  <div class="meta">{title_num} · {status} · printed {date.today().strftime('%d/%m/%Y')}</div>

  <table class="form">{form_rows}{extra_rows}</table>

  <h2>Photos</h2>
  {photos_html}

  <h2>Other Attachments</h2>
  {other_html}

  <div class="footer">This document is a system-generated copy of the product inquiry record.</div>
</body></html>"""

    def render_pdf(self, inquiry_id: str) -> tuple[bytes, str]:
        """Return (pdf_bytes, filename). Raises PDFRenderingUnavailable if WeasyPrint
        cannot render (native libs missing)."""
        inquiry = self._load(inquiry_id)
        return render_html(self._html(inquiry)), self.build_filename(inquiry)
