"""Render a formal complaint PDF (supporting-document copy) via WeasyPrint.

Decoupled from the request path: called by the RQ task ``generate_complaint_pdf``.
Content is the formal subset agreed with the complaint team — details, customer
info, product lines, defect description, technical response, resolution, and
embedded image attachments. Internal-only fields (audit trail, assignee, SLA)
are deliberately excluded.

WeasyPrint needs native cairo/pango/gdk-pixbuf libs; the import is guarded so the
API/worker never crash if they're missing — the caller marks the download failed
with a clear message instead.
"""
import base64
import logging
import mimetypes
import os
from datetime import date, datetime
from html import escape
from typing import Optional

from sqlalchemy.orm import Session

from app.models.complaints import Complaint
from app.services.storage_router import extract_key, get_backend, normalize_provider

logger = logging.getLogger(__name__)

_IMAGE_MIME_PREFIX = "image/"
# Fallback when the stored mime_type is missing/generic (e.g. WhatsApp .jpeg
# uploads land as application/octet-stream or NULL). Extension wins so any photo
# type renders in the PHOTOS section instead of being dumped under OTHER.
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".heif", ".tif", ".tiff"}


def _image_mime(att) -> Optional[str]:
    """Return an image/* mime for an attachment, or None if not an image.

    Trusts a stored image/* mime first; otherwise infers from the filename
    extension so photos with missing/generic mime_type still count as images.
    """
    mime = (getattr(att, "mime_type", None) or "").lower()
    if mime.startswith(_IMAGE_MIME_PREFIX):
        return mime
    name = getattr(att, "original_filename", None) or getattr(att, "file_path", None) or ""
    ext = os.path.splitext(str(name))[1].lower()
    if ext in _IMAGE_EXTS:
        return mimetypes.types_map.get(ext) or f"image/{ext.lstrip('.')}"
    return None


class PDFRenderingUnavailable(RuntimeError):
    """Raised when WeasyPrint cannot render (native libs missing)."""


def _fmt(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, (datetime, date)):
        return value.strftime("%d %b %Y")
    s = str(value).strip()
    return escape(s) if s else "—"


def _row(label: str, value) -> str:
    return f'<tr><th>{escape(label)}</th><td>{_fmt(value)}</td></tr>'


class ComplaintPDFService:
    def __init__(self, db: Session):
        self.db = db

    def build_filename(self, complaint: Complaint) -> str:
        num = (getattr(complaint, "complaint_number", None) or str(complaint.id)).strip()
        safe = "".join(c for c in num if c.isalnum() or c in ("-", "_")) or "complaint"
        return f"complaint-{safe}.pdf"

    def _load(self, complaint_id: str) -> Complaint:
        complaint = self.db.query(Complaint).filter(Complaint.id == str(complaint_id)).first()
        if complaint is None:
            from app.services.error_handler import handle_not_found
            raise handle_not_found("Complaint", complaint_id)
        return complaint

    def _image_data_uris(self, complaint: Complaint) -> list[dict]:
        """Download image attachments and return data-URI + filename dicts.

        Non-image attachments are listed by filename only (handled by the caller
        via _other_attachment_names). Best-effort: a failed fetch is skipped.
        """
        out: list[dict] = []
        for link in self._attachment_links(complaint):
            att = getattr(link, "attachment", None)
            if att is None:
                continue
            mime = _image_mime(att)
            if mime is None:
                continue
            try:
                provider = normalize_provider(getattr(att, "storage_provider", None))
                key = extract_key(getattr(att, "file_path", None))
                if not key:
                    continue
                raw = get_backend(provider).download_file(key)
                b64 = base64.b64encode(raw).decode("ascii")
                out.append(
                    {
                        "name": getattr(att, "original_filename", None) or "image",
                        "data_uri": f"data:{mime};base64,{b64}",
                    }
                )
            except Exception:  # pragma: no cover - best-effort per image
                logger.warning(
                    "complaint PDF: failed to embed attachment %s", getattr(att, "id", "?"), exc_info=True
                )
        return out

    def _attachment_links(self, complaint: Complaint) -> list:
        """Linked attachments for the complaint, from the generic
        entity_attachment_links table (the source the detail UI uses) — NOT the
        legacy complaint_attachments join, which the "Link Attachment" flow no
        longer writes to. Each link exposes ``.attachment`` (an Attachment row)."""
        try:
            from app.services.entity_attachment_service import EntityAttachmentService
            return EntityAttachmentService(self.db).list_links("complaint", str(complaint.id)) or []
        except Exception:  # pragma: no cover - never break PDF on link lookup
            logger.warning("complaint PDF: failed to list entity attachment links", exc_info=True)
            return []

    def _other_attachment_names(self, complaint: Complaint) -> list[str]:
        names: list[str] = []
        for link in self._attachment_links(complaint):
            att = getattr(link, "attachment", None)
            if att is None:
                continue
            if _image_mime(att) is None:
                names.append(getattr(att, "original_filename", None) or "attachment")
        return names

    def _html(self, complaint: Complaint) -> str:
        rc = getattr(complaint, "root_cause", None)
        res = getattr(complaint, "resolution", None)

        details = "".join(
            [
                _row("Complaint No.", getattr(complaint, "complaint_number", None)),
                _row("Complaint Date", getattr(complaint, "complaint_date", None)),
                _row("Status", getattr(complaint, "status", None)),
                _row("Delivery Order", getattr(complaint, "delivery_order_number", None)),
                _row("Within Warranty", getattr(complaint, "within_warranty", None)),
                _row("Complaint Type", getattr(complaint, "complaint_type", None)),
                _row("Product Type", getattr(complaint, "product_type", None)),
                _row("Defects Discovered", getattr(complaint, "defects_discovered", None)),
            ]
        )
        customer = "".join(
            [
                _row("Customer", getattr(complaint, "customer_name", None)),
                _row("Customer Type", getattr(complaint, "customer_type", None)),
                _row("Contact Person", getattr(complaint, "contact_person", None)),
                _row("Contact Number", getattr(complaint, "contact_number", None)),
                _row("Address", getattr(complaint, "customer_address", None)),
                _row("Project", getattr(complaint, "project_title", None)),
                _row("Salesperson", getattr(complaint, "salesperson", None)),
            ]
        )

        lines = sorted(
            getattr(complaint, "product_lines", []) or [],
            key=lambda pl: (getattr(pl, "sort_order", None) or 0),
        )
        if lines:
            line_rows = "".join(
                f"<tr><td>{_fmt(getattr(pl, 'product_code', None))}</td>"
                f"<td>{_fmt(getattr(pl, 'product_type', None))}</td>"
                f"<td>{_fmt(getattr(pl, 'quantity', None))}</td></tr>"
                for pl in lines
            )
            products_html = (
                "<table class='grid'><thead><tr><th>Product Code</th><th>Type</th>"
                f"<th>Qty</th></tr></thead><tbody>{line_rows}</tbody></table>"
            )
        else:
            products_html = "<p class='empty'>No product lines recorded.</p>"

        images = self._image_data_uris(complaint)
        if images:
            imgs_html = "".join(
                f"<figure><img src='{img['data_uri']}'/>"
                f"<figcaption>{escape(img['name'])}</figcaption></figure>"
                for img in images
            )
            photos_html = f"<div class='photos'>{imgs_html}</div>"
        else:
            photos_html = "<p class='empty'>No photo attachments.</p>"

        other = self._other_attachment_names(complaint)
        other_html = (
            "<ul>" + "".join(f"<li>{escape(n)}</li>" for n in other) + "</ul>"
            if other
            else "<p class='empty'>None.</p>"
        )

        defect = _fmt(getattr(complaint, "defect_description", None))
        tech = _fmt(getattr(complaint, "technical_team_response", None))
        root_cause = _fmt(getattr(rc, "name", None) if rc is not None else None)
        resolution = _fmt(getattr(res, "name", None) if res is not None else None)
        title_num = _fmt(getattr(complaint, "complaint_number", None))

        return f"""<!doctype html><html><head><meta charset="utf-8"/>
<style>
  @page {{ size: A4; margin: 18mm 16mm; }}
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; color: #1a1a1a; font-size: 11px; }}
  h1 {{ font-size: 18px; margin: 0 0 2px; }}
  .sub {{ color: #666; font-size: 10px; margin-bottom: 14px; }}
  h2 {{ font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: #444;
        border-bottom: 1px solid #ccc; padding-bottom: 3px; margin: 16px 0 8px; }}
  table.kv {{ width: 100%; border-collapse: collapse; }}
  table.kv th {{ text-align: left; width: 36%; color: #555; font-weight: 600;
                 padding: 3px 8px 3px 0; vertical-align: top; }}
  table.kv td {{ padding: 3px 0; vertical-align: top; }}
  table.grid {{ width: 100%; border-collapse: collapse; margin-top: 4px; }}
  table.grid th, table.grid td {{ border: 1px solid #ddd; padding: 4px 6px; text-align: left; }}
  table.grid th {{ background: #f5f5f5; }}
  .box {{ border: 1px solid #e2e2e2; background: #fafafa; padding: 8px 10px; border-radius: 4px;
          white-space: pre-wrap; }}
  .empty {{ color: #999; font-style: italic; }}
  .cols {{ display: flex; gap: 24px; }}
  .cols > div {{ flex: 1; }}
  .photos {{ display: flex; flex-wrap: wrap; gap: 10px; }}
  figure {{ margin: 0; width: 30%; }}
  figure img {{ width: 100%; border: 1px solid #ddd; border-radius: 3px; }}
  figcaption {{ font-size: 9px; color: #777; margin-top: 2px; word-break: break-all; }}
  .footer {{ margin-top: 22px; color: #999; font-size: 9px; border-top: 1px solid #eee; padding-top: 6px; }}
</style></head><body>
  <h1>Complaint {title_num}</h1>
  <div class="sub">Supporting document · generated {date.today().strftime('%d %b %Y')}</div>

  <div class="cols">
    <div><h2>Complaint Details</h2><table class="kv">{details}</table></div>
    <div><h2>Customer</h2><table class="kv">{customer}</table></div>
  </div>

  <h2>Defect Description</h2>
  <div class="box">{defect}</div>

  <h2>Products</h2>
  {products_html}

  <h2>Technical Team Response</h2>
  <div class="box">{tech}</div>

  <div class="cols">
    <div><h2>Root Cause</h2><div class="box">{root_cause}</div></div>
    <div><h2>Resolution</h2><div class="box">{resolution}</div></div>
  </div>

  <h2>Photos</h2>
  {photos_html}

  <h2>Other Attachments</h2>
  {other_html}

  <div class="footer">This document is a system-generated copy of the complaint record.</div>
</body></html>"""

    def render_pdf(self, complaint_id: str) -> tuple[bytes, str]:
        """Return (pdf_bytes, filename). Raises PDFRenderingUnavailable if WeasyPrint
        cannot render (native libs missing)."""
        complaint = self._load(complaint_id)
        html = self._html(complaint)
        try:
            from weasyprint import HTML  # noqa: WPS433 (guarded optional dep)
        except Exception as e:  # ImportError or native-lib load error
            raise PDFRenderingUnavailable(
                f"PDF rendering is unavailable on this host (WeasyPrint import failed: {e})."
            ) from e
        try:
            pdf_bytes = HTML(string=html).write_pdf()
        except Exception as e:
            raise PDFRenderingUnavailable(
                f"PDF rendering failed (WeasyPrint native libraries missing or broken: {e})."
            ) from e
        return pdf_bytes, self.build_filename(complaint)
