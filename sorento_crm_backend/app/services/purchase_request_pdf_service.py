"""Render a Purchase Request / Sponsorship Form PDF via WeasyPrint.

Decoupled from the request path: called by the RQ task
``generate_purchase_request_pdf``. Mirrors ``stock_inquiry_pdf_service`` and
``complaint_pdf_service`` — same helpers, same "printed copy agrees with the
screen" rule, same exclusion of internal-only fields (SLA tier/assignee, handling
lock, audit trail) because the printed sheet gets handed to a driver.

Why this exists at all: the only export was Excel, and a long delivery address
stretched one cell to an enormous width, making the printed sheet unusable. A
spreadsheet auto-sizes to its content; a document must not. Hence
``table-layout: fixed`` plus an explicit break rule — the two things that stop a
cell widening the page no matter what is in it.

One table serves both request types (they share ``purchase_requests``), so every
label decision here has to read correctly for a Purchase Request AND a
Sponsorship Form; rows that belong to only one type are emitted only when set.
"""
import logging
from datetime import date, datetime
from decimal import Decimal
from html import escape
from typing import Optional

from sqlalchemy.orm import Session

from app.models.procurement import PurchaseRequestHeader
from app.services.pdf_render import (
    PDFRenderingUnavailable,
    embedded_images,
    names_list_html,
    non_image_names,
    photos_section_html,
    render_html,
)

logger = logging.getLogger(__name__)

__all__ = ["PurchaseRequestPDFService", "PDFRenderingUnavailable"]

_SPONSORSHIP = "sponsorship_form"

# Mirrors the FE status pills so the printed status matches the screen.
_STATUS_LABELS = {
    "draft": "Draft",
    "submitted": "Submitted",
    "pending": "Pending Approval",
    "approved": "Approved",
    "rejected": "Rejected",
    "processed_by_cs": "Processed by CS",
    "closed": "Closed",
    "voided": "Voided",
}


def _fmt(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, Decimal):
        # Money-ish: thousands separated, trailing .00 dropped for whole numbers.
        q = value.normalize()
        return f"{q:,.2f}".rstrip("0").rstrip(".") if q == q.to_integral_value() else f"{value:,.2f}"
    s = str(value).strip()
    return escape(s) if s else "—"


def _row(label: str, value) -> str:
    return f"<tr><th>{escape(label)}</th><td>{_fmt(value)}</td></tr>"


def _row_if(label: str, value) -> str:
    """Only emit a row that actually has a value — used for the type-specific
    fields so a Purchase Request does not print empty Sponsorship rows."""
    return _row(label, value) if value not in (None, "") else ""


class PurchaseRequestPDFService:
    def __init__(self, db: Session):
        self.db = db

    def _is_sponsorship(self, req: PurchaseRequestHeader) -> bool:
        return (getattr(req, "request_type", None) or "") == _SPONSORSHIP

    def build_filename(self, req: PurchaseRequestHeader) -> str:
        """Name the file after what the document IS, so a folder of downloads
        sorts into purchase requests and sponsorship forms."""
        stem = "sponsorship-form" if self._is_sponsorship(req) else "purchase-request"
        num = (getattr(req, "request_number", None) or str(req.id)).strip()
        safe = "".join(c for c in num if c.isalnum() or c in ("-", "_")) or stem
        return f"{stem}-{safe}.pdf"

    def _load(self, request_id: str) -> PurchaseRequestHeader:
        req = (
            self.db.query(PurchaseRequestHeader)
            .filter(PurchaseRequestHeader.id == str(request_id))
            .first()
        )
        if req is None:
            from app.services.error_handler import handle_not_found

            raise handle_not_found("Purchase Request", request_id)
        return req

    def _attachment_links(self, req: PurchaseRequestHeader) -> list:
        try:
            from app.services.entity_attachment_service import EntityAttachmentService

            return (
                EntityAttachmentService(self.db).list_links("purchase_request", str(req.id))
                or []
            )
        except Exception:  # pragma: no cover - never break the PDF on link lookup
            logger.warning(
                "purchase request PDF: failed to list entity attachment links", exc_info=True
            )
            return []

    def _status_label(self, req: PurchaseRequestHeader) -> str:
        """Lifecycle status wins over approval_status — the same precedence
        ``getDisplayStatus`` uses on the FE, so an approved-then-processed form
        reads "Processed by CS" here exactly as it does on the list and portal."""
        raw = (getattr(req, "status", None) or "").strip()
        if not raw:
            raw = (getattr(req, "approval_status", None) or "").strip()
        if not raw:
            return "—"
        return _STATUS_LABELS.get(raw, raw.replace("_", " ").title())

    def _lines_html(self, req: PurchaseRequestHeader) -> str:
        lines = sorted(
            list(getattr(req, "lines", None) or []),
            key=lambda ln: (getattr(ln, "sort_order", None) or 0),
        )
        if not lines:
            return '<p class="empty">No items on this request.</p>'

        sponsorship = self._is_sponsorship(req)
        head = (
            "<tr><th>#</th><th>Item Code</th><th>Qty</th><th>Unit Price</th>"
            "<th>Total</th><th>Remark</th></tr>"
            if sponsorship
            else "<tr><th>#</th><th>Item Code</th><th>Qty</th><th>Remark</th></tr>"
        )
        body = []
        for i, ln in enumerate(lines, start=1):
            cells = [f"<td>{i}</td>", f"<td>{_fmt(getattr(ln, 'item_code', None))}</td>",
                     f"<td>{_fmt(getattr(ln, 'quantity', None))}</td>"]
            if sponsorship:
                cells.append(f"<td>{_fmt(getattr(ln, 'unit_price', None))}</td>")
                cells.append(f"<td>{_fmt(getattr(ln, 'total', None))}</td>")
            cells.append(f"<td>{_fmt(getattr(ln, 'remark', None))}</td>")
            body.append(f"<tr>{''.join(cells)}</tr>")
        return f'<table class="items">{head}{"".join(body)}</table>'

    def _html(self, req: PurchaseRequestHeader) -> str:
        sponsorship = self._is_sponsorship(req)
        doc_title = "Sponsorship Form" if sponsorship else "Purchase Request"

        rows = [
            _row("Date", getattr(req, "submitted_at", None) or getattr(req, "request_date", None)),
            _row(
                "Sponsorship Form Number" if sponsorship else "Purchase Request Number",
                getattr(req, "request_number", None),
            ),
            _row("Customer Name", getattr(req, "customer_name", None)),
            # PIC sits directly under Customer Name, on screen and in print, so a
            # reader finds the human where they expect them - and stops anyone
            # appending the contact to the address again.
            _row("PIC", getattr(req, "pic", None)),
            _row("Delivery Address", getattr(req, "delivery_address", None)),
            _row("Project Title", getattr(req, "project_title", None)),
        ]

        if sponsorship:
            rows += [
                _row_if(
                    "Total Project Value",
                    getattr(req, "total_project_value", None)
                    or getattr(req, "total_project_value_text", None),
                ),
                _row_if("Sponsor Subject", getattr(req, "sponsor_subject_other", None)
                        or getattr(req, "sponsor_subject", None)),
            ]
        else:
            rows += [
                _row_if("Purpose", getattr(req, "purpose", None)),
                _row_if("Sales Type", getattr(req, "sales_type", None)),
            ]

        rows += [
            _row("Date of Delivery", getattr(req, "expected_delivery_date", None)),
            _row_if(
                "Expected PO Date",
                getattr(req, "expected_po_date", None)
                or getattr(req, "expected_po_date_text", None),
            ),
            _row("Requested By", getattr(req, "requested_by", None)),
            _row_if("Approved By", getattr(req, "approved_by", None)),
        ]
        form_rows = "".join(rows)

        links = self._attachment_links(req)
        photos_html = photos_section_html(
            embedded_images(links, context="purchase request PDF")
        )
        other_html = names_list_html(non_image_names(links))

        title_num = _fmt(getattr(req, "request_number", None))
        status = escape(self._status_label(req))

        return f"""<!doctype html><html><head><meta charset="utf-8"/>
<style>
  @page {{ size: A4; margin: 16mm 14mm; }}
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; color: #1a1a1a; font-size: 11px; }}
  .doc-title {{ text-align: center; font-size: 15px; font-weight: bold; text-transform: uppercase;
                letter-spacing: .06em; text-decoration: underline; padding: 8px 0 10px; }}
  .meta {{ color: #666; font-size: 9px; text-align: center; margin-bottom: 12px; }}
  /* table-layout:fixed + the break rules below are what stop a long delivery
     address widening a column and wrecking the print - the exact failure the
     Excel export had. Without `fixed` the cell grows to its content. */
  table.form {{ width: 100%; table-layout: fixed; border-collapse: collapse; border: 2px solid #1a1a1a; }}
  table.form th, table.form td {{ border: 1px solid #b8b8b8; padding: 6px 8px; vertical-align: top;
                                  text-align: left; white-space: pre-wrap;
                                  overflow-wrap: anywhere; word-break: break-word; }}
  table.form th {{ width: 34%; background: #f2f2f2; font-weight: bold; text-transform: uppercase;
                   letter-spacing: .03em; font-size: 10px; }}
  table.items {{ width: 100%; table-layout: fixed; border-collapse: collapse; margin-top: 4px; }}
  table.items th, table.items td {{ border: 1px solid #b8b8b8; padding: 5px 7px; text-align: left;
                                    vertical-align: top; font-size: 10px;
                                    overflow-wrap: anywhere; word-break: break-word; }}
  table.items th {{ background: #f2f2f2; text-transform: uppercase; font-size: 9px; }}
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
  <div class="doc-title">{escape(doc_title)}</div>
  <div class="meta">{title_num} · {status} · printed {date.today().strftime('%d/%m/%Y')}</div>

  <table class="form">{form_rows}</table>

  <h2>Items</h2>
  {self._lines_html(req)}

  <h2>Photos</h2>
  {photos_html}

  <h2>Other Attachments</h2>
  {other_html}

  <div class="footer">This document is a system-generated copy of the {escape(doc_title.lower())} record.</div>
</body></html>"""

    def render_pdf(self, request_id: str) -> tuple[bytes, str]:
        """Return (pdf_bytes, filename). Raises PDFRenderingUnavailable if
        WeasyPrint cannot render (native libs missing)."""
        req = self._load(request_id)
        return render_html(self._html(req)), self.build_filename(req)
