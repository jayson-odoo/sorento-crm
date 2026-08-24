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

Two revision modes (round 6, PLAN-portal-submission-revisions 6.3/6.4):

* ``revision_id`` - print ONE version. Same table, same row order, every value
  read from that version's stored snapshot.
* ``include_revisions`` - the current form first, then every EARLIER version
  newest first, each on its own page. The newest lineage entry is skipped: it is
  the version the current form shows, so printing it too gave the reader the same
  form twice. Its label, submitter and reason ride on the current form instead.

Both are read-only views of history, so neither ever reads a value off the live
row: that is the whole point of a snapshot.
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
    in_malaysia,
    names_list_html,
    non_image_names,
    photos_section_html,
    render_html,
    today_in_malaysia,
)
from app.services.pdf_revision_support import (
    appended_revision_entries,
    export_filename,
    filename_with_revision,
    find_revision_entry,
    is_superseded,
    latest_revision_entry,
    revision_attachment_sections,
    revision_document_number,
    revision_entries,
    revision_heading,
    revision_reason,
    snapshot_datetime,
)

logger = logging.getLogger(__name__)

__all__ = ["StockInquiryPDFService", "PDFRenderingUnavailable", "FILENAME_STEM"]

# What the document IS, in front of the number, on every export of this form.
# Shared with the route so the pending download row and the finished artifact
# cannot be named differently.
FILENAME_STEM = "product-inquiry"

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
        return "-"
    # Timestamps are stored naive UTC; the page must read as the Malaysia wall
    # clock every other surface shows (a date column is left alone).
    value = in_malaysia(value)
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    s = str(value).strip()
    return escape(s) if s else "-"


def _row(label: str, value) -> str:
    return f"<tr><th>{escape(label)}</th><td>{_fmt(value)}</td></tr>"


class StockInquiryPDFService:
    def __init__(self, db: Session):
        self.db = db

    def build_filename(self, inquiry: StockInquiry) -> str:
        # The filename carries the revision too, so two revisions of the same
        # inquiry do not land in a downloads folder as one overwritten file (UAC N5).
        return export_filename(
            FILENAME_STEM, display_document_number(inquiry) or str(inquiry.id)
        )

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
            return "-"
        return _STATUS_LABELS.get(raw, raw.replace("_", " ").title())

    def _form_rows(self, inquiry: StockInquiry) -> str:
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
        return f"{form_rows}{extra_rows}"

    def _current_page(self, inquiry: StockInquiry, latest: Optional[dict] = None) -> str:
        """The form as it stands now - the document this export has always been.

        ``latest`` is the newest lineage entry, passed only by the
        include-revisions export. That entry gets no page of its own (it IS this
        form), so what it uniquely carried - which revision this is, who sent it,
        when, and why - reads here instead, in the same wording a revision page's
        own heading uses.
        """
        links = self._attachment_links(inquiry)
        photos_html = photos_section_html(
            embedded_images(links, context="product inquiry PDF")
        )
        other_html = names_list_html(non_image_names(links))

        title_num = _fmt(display_document_number(inquiry) or None)
        status = escape(self._status_label(inquiry))
        version_html = ""
        if latest:
            heading = escape(revision_heading(latest, superseded=False))
            reason = revision_reason(latest)
            version_html = f'<div class="meta">{heading}</div>' + (
                f'<div class="meta">Reason: {escape(reason)}</div>' if reason else ""
            )

        return f"""  <div class="doc-title">Product Inquiry Form</div>
  <div class="meta">{title_num} · {status} · printed {today_in_malaysia().strftime('%d/%m/%Y')}</div>
  {version_html}

  <table class="form">{self._form_rows(inquiry)}</table>

  <h2>Photos</h2>
  {photos_html}

  <h2>Other Attachments</h2>
  {other_html}
"""

    def _revision_rows(self, entry: dict) -> str:
        """The same table, every value read from the version's stored snapshot.

        The Date row carries the date THIS version was submitted, not the record's
        creation date: on a revision page that is the date the reader means.
        Rows the live form fills in after submission (the purchasing reply, the
        rejection / reopen / void reasons) print only when the snapshot itself
        carries them - printing an empty row would imply the version had one.
        ``status`` is never printed here (see pdf_revision_support).
        """
        snapshot = entry.get("snapshot") or {}
        rows = [
            _row("Date", snapshot_datetime(entry.get("submitted_at"))),
            _row("Stock Inquiry Number", revision_document_number(entry, "inquiry_number")),
            _row("Sales Person", snapshot.get("salesperson")),
            _row("Product Code", snapshot.get("product_code")),
            _row("Item Description", snapshot.get("item_description")),
            _row("Project Customer", snapshot.get("project_customer")),
            _row("Project Name", snapshot.get("project_name")),
            _row("Qty", snapshot.get("quantity")),
            _row("Delivery Date", snapshot.get("delivery_date")),
            _row("Remark", snapshot.get("remark")),
            _row("Additional Remark", snapshot.get("additional_remark")),
        ]
        for label, name in (
            ("Comment / Reply by Purchasing", "purchasing_response"),
            ("Rejection Reason", "rejection_reason"),
            ("Reopen Reason", "reopen_reason"),
            ("Void Reason", "void_reason"),
        ):
            if snapshot.get(name):
                rows.append(_row(label, snapshot.get(name)))
        return "".join(rows)

    def _revision_page(
        self, entry: dict, *, superseded: bool, page_break: bool = False
    ) -> str:
        """One superseded version, headed by which version it is and why it changed."""
        number = _fmt(revision_document_number(entry, "inquiry_number"))
        heading = escape(revision_heading(entry, superseded=superseded))
        reason = revision_reason(entry)
        reason_html = (
            f'<div class="meta">Reason: {escape(reason)}</div>' if reason else ""
        )
        # A version's photos are embedded from ITS OWN attachment set, through the
        # same two helpers the current form uses, so a revision page is the same
        # document with older values rather than a list of filenames.
        images, other_names = revision_attachment_sections(
            self.db, entry, context="product inquiry PDF"
        )
        photos_html = photos_section_html(images)
        other_html = names_list_html(other_names)
        break_style = ' style="page-break-before: always;"' if page_break else ""

        return f"""  <div class="page"{break_style}>
  <div class="doc-title">Product Inquiry Form</div>
  <div class="meta">{number} · {heading} · printed {today_in_malaysia().strftime('%d/%m/%Y')}</div>
  {reason_html}

  <table class="form">{self._revision_rows(entry)}</table>

  <h2>Photos</h2>
  {photos_html}

  <h2>Other Attachments</h2>
  {other_html}
  </div>
"""

    def _document(self, body: str) -> str:
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
{body}
  <div class="footer">This document is a system-generated copy of the product inquiry record.</div>
</body></html>"""

    def _html(self, inquiry: StockInquiry) -> str:
        """The current form on its own - the export's default document."""
        return self._document(self._current_page(inquiry))

    def build_html(
        self,
        inquiry_id: str,
        *,
        revision_id: Optional[str] = None,
        include_revisions: bool = False,
    ) -> str:
        """The document HTML, without WeasyPrint - what the tests assert on."""
        return self._build(
            inquiry_id, revision_id=revision_id, include_revisions=include_revisions
        )[0]

    def _build(
        self,
        inquiry_id: str,
        *,
        revision_id: Optional[str] = None,
        include_revisions: bool = False,
    ) -> tuple[str, str]:
        """(html, filename). One place decides which pages a request produces."""
        inquiry = self._load(inquiry_id)
        filename = self.build_filename(inquiry)

        # A single revision wins over the lineage: the two are mutually exclusive
        # and the route rejects the combination, so this is the second line of
        # defence rather than the contract.
        if revision_id:
            entries = revision_entries(self.db, "stock_inquiry", str(inquiry.id))
            entry = find_revision_entry(entries, revision_id, label="stock inquiry")
            return (
                self._document(
                    self._revision_page(entry, superseded=is_superseded(entries, entry))
                ),
                filename_with_revision(
                    FILENAME_STEM,
                    entry,
                    "inquiry_number",
                    fallback=display_document_number(inquiry) or str(inquiry.id),
                ),
            )

        if not include_revisions:
            return self._document(self._current_page(inquiry)), filename

        # The EARLIER versions print newest first, behind the current form. The
        # newest entry is the version this form already shows, so it gets no page
        # of its own - its label, submitter and reason go onto the current page.
        entries = revision_entries(self.db, "stock_inquiry", str(inquiry.id))
        pages = [self._current_page(inquiry, latest_revision_entry(entries))]
        pages += [
            self._revision_page(
                entry,
                superseded=is_superseded(entries, entry),
                page_break=True,
            )
            for entry in appended_revision_entries(entries)
        ]
        return self._document("".join(pages)), filename

    def render_pdf(
        self,
        inquiry_id: str,
        revision_id: Optional[str] = None,
        include_revisions: bool = False,
    ) -> tuple[bytes, str]:
        """Return (pdf_bytes, filename). Raises PDFRenderingUnavailable if WeasyPrint
        cannot render (native libs missing)."""
        html, filename = self._build(
            inquiry_id, revision_id=revision_id, include_revisions=include_revisions
        )
        return render_html(html), filename
