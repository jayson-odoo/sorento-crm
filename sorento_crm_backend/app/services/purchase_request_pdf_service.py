"""Render a Purchase Request / Sponsorship Form PDF via WeasyPrint.

Decoupled from the request path: called by the RQ task
``generate_purchase_request_pdf``. Mirrors ``stock_inquiry_pdf_service`` and
``complaint_pdf_service`` — same helpers, same "printed copy agrees with the
screen" rule, same exclusion of internal-only fields (SLA tier/assignee, handling
lock, audit trail) because the printed sheet gets handed to a driver.

Why this exists at all: the only export was Excel, and a long delivery address
stretched one cell to an enormous width, making the printed sheet unusable. A
spreadsheet auto-sizes to its content; a document must not. The items table
pins that with ``table-layout: fixed``; the label/value tables use auto layout
(so a value sits beside its label instead of at a fixed offset) and rely on
``overflow-wrap: anywhere``, which lowers a cell's min-content width so an
unbroken token wraps instead of widening the table.

One table serves both request types (they share ``purchase_requests``), so every
label decision here has to read correctly for a Purchase Request AND a
Sponsorship Form; rows that belong to only one type are emitted only when set.
"""
import logging
from datetime import date, datetime
from decimal import Decimal
from html import escape
from typing import Optional

from sqlalchemy import func
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

# The printed form is Sorento letterhead. Same three lines the Excel export
# writes (``SORENTO_HEADER`` in purchase-request-excel-export.ts) - the PDF
# replaces that export, so it has to carry the same company block or the printed
# copy stops looking like a company document.
_LETTERHEAD = (
    "SORENTO SDN BHD",
    "No 5, Jalan Astana 2/KU2, Bandar Bukit Raja, 41050 Klang, Selangor, Malaysia.",
    "Tel: +603-3082 9778, Fax: +603-30829278.",
)

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

def _blank(value) -> str:
    """Empty renders as empty, not as a dash.

    The Excel export leaves an unfilled cell blank and the printed form is meant
    to be signed off by hand, so a row like ``Approved by:`` has to print as an
    empty space someone can write in - a "—" reads as "not applicable".
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, Decimal):
        return f"{value:,.2f}"
    return escape(str(value).strip())


def _date_cell(value) -> str:
    """``6/8/2026`` - every date on a Purchase Request.

    The Excel export wrote the header date as ``6/8/26`` and the rest as
    ``6/8/2026``. Two formats on one page invite the reader to wonder what the
    difference means, and there isn't one, so the document uses a single format
    throughout.
    """
    if not isinstance(value, (date, datetime)):
        return _blank(value)
    return f"{value.day}/{value.month}/{value.year}"


def _date_long(value) -> str:
    """``6-Aug-2026`` - the Sponsorship Form date format."""
    if not isinstance(value, (date, datetime)):
        return _blank(value)
    return f"{value.day}-{_MONTHS[value.month - 1]}-{value.year}"


def _field(label: str, value: str, *, label2: str = "", value2: str = "") -> str:
    """One label/value line, optionally with a second pair on the same line
    (``Sponsorship form number: X    Date: Y``), mirroring the Excel columns."""
    if label2:
        # The right-hand label and its value share ONE cell. As separate columns
        # the label column stretched to its widest member - "Expected date to
        # receive PO:" - so the short "Date:" on another row was left with its
        # value stranded at the far side of that column. In one cell the value
        # always follows its own label, whatever else is on the page.
        return (
            f'<tr><td class="lbl">{escape(label)}</td>'
            f'<td class="val tight">{value}</td>'
            f'<td class="pair" colspan="2">'
            f'<span class="lbl">{escape(label2)}</span>{value2}</td></tr>'
        )
    # No second pair: let the value run to the right edge instead of wrapping
    # inside a quarter-width column. A delivery address is the reason.
    return (
        f'<tr><td class="lbl">{escape(label)}</td>'
        f'<td class="val" colspan="3">{value}</td></tr>'
    )


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

    def _lookup_label(self, column: str, value: Optional[str]) -> Optional[str]:
        """Resolve a lookup-bound code to the label the screen shows.

        ``sales_type`` stores ``cash_sales``; the detail page renders "Cash Sales"
        through ``LookupBoundLabel``. Printing the raw code would make the paper
        disagree with the screen. Falls back to the stored value if the binding
        or option is missing - a code on the page beats a blank.
        """
        code = (value or "").strip()
        if not code:
            return None
        try:
            from app.models.lookup import LookupBinding, LookupOption

            binding = (
                self.db.query(LookupBinding)
                .filter(
                    LookupBinding.table_name == "purchase_requests",
                    LookupBinding.column_name == column,
                )
                .first()
            )
            if binding is None:
                return code
            option = (
                self.db.query(LookupOption)
                .filter(
                    LookupOption.set_id == binding.set_id,
                    func.lower(LookupOption.value) == code.lower(),
                )
                .first()
            )
            return (option.label if option else None) or code
        except Exception:  # pragma: no cover - never fail the PDF on a lookup
            logger.warning("purchase request PDF: lookup label failed", exc_info=True)
            return code

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

    def _lines_html(self, req: PurchaseRequestHeader) -> tuple[str, str]:
        """Return (table_html, grand_total_text).

        Column sets differ by type, exactly as the Excel export does: a
        Sponsorship Form prices its items (U/P, Total, Grand Total), a Purchase
        Request does not.
        """
        lines = sorted(
            list(getattr(req, "lines", None) or []),
            key=lambda ln: (getattr(ln, "sort_order", None) or 0),
        )
        sponsorship = self._is_sponsorship(req)

        if sponsorship:
            cols = '<col style="width:8%"/><col style="width:24%"/><col style="width:9%"/>' \
                   '<col style="width:12%"/><col style="width:13%"/><col style="width:34%"/>'
            head = ("<tr><th>NO.</th><th>Item Code</th><th>Qty</th><th>U/P</th>"
                    "<th>Total</th><th>Remark</th></tr>")
            span_before_total = 3
        else:
            cols = '<col style="width:8%"/><col style="width:30%"/><col style="width:12%"/>' \
                   '<col style="width:50%"/>'
            head = "<tr><th>#</th><th>Item Code</th><th>Qty</th><th>Remark</th></tr>"
            span_before_total = 0

        grand = Decimal("0")
        body: list[str] = []
        for i, ln in enumerate(lines, start=1):
            qty = getattr(ln, "quantity", None)
            cells = [
                f"<td>{i}</td>",
                f'<td>{_blank(getattr(ln, "item_code", None))}</td>',
                f"<td>{_blank(qty)}</td>",
            ]
            if sponsorship:
                unit = getattr(ln, "unit_price", None) or Decimal("0")
                total = getattr(ln, "total", None)
                if total is None:
                    total = (Decimal(str(qty or 0)) * Decimal(str(unit)))
                grand += Decimal(str(total))
                cells.append(f'<td class="num">{Decimal(str(unit)):,.2f}</td>')
                cells.append(f'<td class="num">{Decimal(str(total)):,.2f}</td>')
            cells.append(f'<td>{_blank(getattr(ln, "remark", None))}</td>')
            body.append(f"<tr>{''.join(cells)}</tr>")

        if not body:
            span = 6 if sponsorship else 4
            body.append(
                f'<tr><td colspan="{span}" class="empty">No items on this request.</td></tr>'
            )

        if sponsorship:
            body.append(
                f'<tr class="grand"><td colspan="{span_before_total}"></td>'
                f'<td class="lbl">Grand Total:</td>'
                f'<td class="num">{grand:,.2f}</td><td></td></tr>'
            )

        table = f'<table class="items"><colgroup>{cols}</colgroup>{head}{"".join(body)}</table>'
        return table, f"{grand:,.2f}"

    def _fields_html(self, req: PurchaseRequestHeader) -> str:
        """The label/value block, in the order the Excel document uses."""
        sponsorship = self._is_sponsorship(req)
        submitted = getattr(req, "submitted_at", None) or getattr(req, "request_date", None)

        rows: list[str] = []
        if sponsorship:
            rows.append(
                _field(
                    "Sponsorship form number:", _blank(getattr(req, "request_number", None)),
                    label2="Date:", value2=_date_long(submitted),
                )
            )
            rows.append('<tr class="spacer"><td colspan="4"></td></tr>')
            subject = (
                getattr(req, "sponsor_subject_other", None)
                or getattr(req, "sponsor_subject", None)
            )
            tpv = (
                getattr(req, "total_project_value_text", None)
                or getattr(req, "total_project_value", None)
            )
            rows += [
                _field("Customer Name:", _blank(getattr(req, "customer_name", None))),
                # PIC sits directly under Customer Name, on screen and in print, so a
                # reader finds the human where they expect them - and stops anyone
                # appending the contact to the address again.
                _field("PIC:", _blank(getattr(req, "pic", None))),
                _field("Delivery Address:", _blank(getattr(req, "delivery_address", None))),
                _field("Project Title:", _blank(getattr(req, "project_title", None))),
                _field("Total Project Value:", _blank(tpv)),
                _field("Sponsor Subject:", _blank(subject)),
                _field(
                    "Date of Delivery:",
                    _date_long(getattr(req, "expected_delivery_date", None)),
                ),
            ]
        else:
            rows.append(
                _field(
                    "Purchase request number:", _blank(getattr(req, "request_number", None)),
                    label2="Date:", value2=_date_cell(submitted),
                )
            )
            rows.append('<tr class="spacer"><td colspan="4"></td></tr>')
            expected_po = (
                getattr(req, "expected_po_date_text", None)
                or _date_cell(getattr(req, "expected_po_date", None))
            )
            rows += [
                _field("Customer Name:", _blank(getattr(req, "customer_name", None))),
                _field("PIC:", _blank(getattr(req, "pic", None))),
                _field("Project Title:", _blank(getattr(req, "project_title", None))),
                _field("Purpose:", _blank(getattr(req, "purpose", None))),
                # Lookup-bound: print the label the screen shows, not the code.
                _field(
                    "Sales Type:",
                    _blank(self._lookup_label("sales_type", getattr(req, "sales_type", None))),
                ),
                _field(
                    "Expected Date of Delivery:",
                    _date_cell(getattr(req, "expected_delivery_date", None)),
                    label2="Expected date to receive PO:",
                    value2=_blank(expected_po),
                ),
            ]
        return f'<table class="fields">{"".join(rows)}</table>'

    def _signoff_html(self, req: PurchaseRequestHeader) -> str:
        """Requested by / Approved by + Date - the sign-off block that closes the
        document. Printed even when unfilled: the blank IS the place to sign."""
        sponsorship = self._is_sponsorship(req)
        fmt = _date_long if sponsorship else _date_cell
        return (
            '<table class="fields signoff">'
            + _field("Requested by:", _blank(getattr(req, "requested_by", None)))
            + _field(
                "Approved by:", _blank(getattr(req, "approved_by", None)),
                label2="Date:", value2=fmt(getattr(req, "approved_at", None)),
            )
            + "</table>"
        )

    def _appendix_html(self, req: PurchaseRequestHeader) -> str:
        """Attachments print only when there are some, so an ordinary form is the
        one-page document the Excel export produced."""
        links = self._attachment_links(req)
        if not links:
            return ""
        images = embedded_images(links, context="purchase request PDF")
        others = non_image_names(links)
        parts = []
        if images:
            parts.append("<h2>Photos</h2>" + photos_section_html(images))
        if others:
            parts.append("<h2>Other Attachments</h2>" + names_list_html(others))
        return "".join(parts)

    def _html(self, req: PurchaseRequestHeader) -> str:
        sponsorship = self._is_sponsorship(req)
        doc_title = "Project Sales Sponsorship Form" if sponsorship else "Purchase Request"
        items_html, _ = self._lines_html(req)
        head_lines = "".join(
            f'<div class="{"co" if i == 0 else "co-sub"}">{escape(line)}</div>'
            for i, line in enumerate(_LETTERHEAD)
        )

        return f"""<!doctype html><html><head><meta charset="utf-8"/>
<style>
  @page {{ size: A4; margin: 14mm 14mm; }}
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; color: #000; font-size: 11px; }}
  .co {{ font-size: 15px; font-weight: bold; letter-spacing: .02em; }}
  .co-sub {{ font-size: 10.5px; }}
  .letterhead {{ padding-bottom: 10px; }}
  .doc-title {{ font-size: 13px; font-weight: bold; margin: 14px 0 12px; }}
  /* table-layout:fixed + the break rules are what stop a long delivery address
     widening a column and wrecking the print - the exact failure the Excel
     export had. Without `fixed` the cell grows to its content. */
  /* `auto` layout, not `fixed`: a label column sized to its widest label puts
     every value right next to its label instead of at a fixed 22% - the
     sign-off block used to derive different widths because its first row spans
     columns, leaving "Tester" stranded far from "Requested by:".
     `overflow-wrap: anywhere` shrinks a cell's min-content width, so an
     unbroken delivery address still wraps under auto layout rather than
     widening the table - the guarantee is kept, by a different mechanism. */
  table.fields {{ width: 100%; table-layout: auto; border-collapse: collapse; }}
  table.fields td {{ padding: 2.5px 14px 2.5px 0; vertical-align: top;
                     white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word; }}
  table.fields td.lbl {{ width: 1%; white-space: nowrap; }}
  /* label and value in one cell: the label keeps its own gap, the value
     follows immediately, and nothing on another row can push them apart. */
  table.fields td.pair span.lbl {{ padding-right: 14px; }}
  /* A paired row shrinks both its own cells: the left value to its content
     and the pair to one unbroken line. Otherwise the left column soaks up
     the row width and the right-hand date is squeezed against the margin,
     wrapping mid-value ("6-" / "Aug-2026"). */
  table.fields td.tight {{ width: 1%; white-space: nowrap; }}
  table.fields td.pair {{ white-space: nowrap; }}
  table.fields tr.spacer td {{ padding: 0; height: 8px; }}
  .signoff {{ margin-top: 22px; }}
  table.items {{ width: 100%; table-layout: fixed; border-collapse: collapse; margin-top: 6px; }}
  table.items th, table.items td {{ border: 1px solid #999; padding: 4px 6px; text-align: left;
                                    vertical-align: top; font-size: 10px;
                                    overflow-wrap: anywhere; word-break: break-word; }}
  table.items th {{ background: #f2f2f2; font-weight: bold; }}
  table.items td.num {{ text-align: right; }}
  table.items tr.grand td {{ border: none; font-weight: bold; padding-top: 6px; }}
  table.items tr.grand td.lbl {{ text-align: right; }}
  .empty {{ color: #777; font-style: italic; }}
  h2 {{ font-size: 11px; font-weight: bold; margin: 18px 0 6px; }}
  .photos {{ display: flex; flex-wrap: wrap; gap: 10px; }}
  figure {{ margin: 0; width: 30%; }}
  figure img {{ width: 100%; border: 1px solid #ddd; }}
  figcaption {{ font-size: 9px; color: #777; margin-top: 2px; word-break: break-all; }}
  ul {{ margin: 4px 0 0 16px; padding: 0; }}
</style></head><body>
  <div class="letterhead">{head_lines}</div>
  <div class="doc-title">{escape(doc_title)}</div>

  {self._fields_html(req)}

  {items_html}

  {self._signoff_html(req)}

  {self._appendix_html(req)}
</body></html>"""

    def render_pdf(self, request_id: str) -> tuple[bytes, str]:
        """Return (pdf_bytes, filename). Raises PDFRenderingUnavailable if
        WeasyPrint cannot render (native libs missing)."""
        req = self._load(request_id)
        return render_html(self._html(req)), self.build_filename(req)
