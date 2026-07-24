"""Compile the linked attachment flyers of one or more promotions into a single
PDF (for printing — the printer does N-up).

Decoupled from the request path: called by the RQ task ``generate_promotions_pdf``.
Attachments are merged in the FE grid display order (the caller passes
``promotion_ids`` already ordered), and within a promo by ``sort_order`` NULLS
LAST then ``created_at``. Each attachment's bytes are fetched via the storage
router (per-row ``storage_provider``); PDFs have their pages appended, images get
a full page, and any other type is skipped and reported back.

PyMuPDF (``fitz``) is already a dependency (complaint PDF export uses WeasyPrint,
this path uses fitz for byte-level PDF/image merging).
"""
import io
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

import fitz  # PyMuPDF

from sqlalchemy.orm import Session

from app.models.marketing import Promotion, PromotionAttachment
from app.models.resources import Attachment
from app.services.storage_router import extract_key, get_backend, normalize_provider

logger = logging.getLogger(__name__)

_MALAYSIA_TZ = timezone(timedelta(hours=8))

# Image types fitz can place on a page via insert_image.
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
_PDF_EXTS = {".pdf"}


def _ext_for(att: Attachment) -> str:
    name = (
        getattr(att, "original_filename", None)
        or getattr(att, "stored_filename", None)
        or getattr(att, "file_path", None)
        or ""
    )
    return os.path.splitext(str(name))[1].lower()


def _is_pdf(att: Attachment) -> bool:
    mime = (getattr(att, "mime_type", None) or "").lower()
    return mime == "application/pdf" or _ext_for(att) in _PDF_EXTS


def _is_image(att: Attachment) -> bool:
    mime = (getattr(att, "mime_type", None) or "").lower()
    return mime.startswith("image/") or _ext_for(att) in _IMAGE_EXTS


class PromotionsPdfService:
    def __init__(self, db: Session):
        self.db = db

    def render_pdf(self, promotion_ids: List[str]) -> Tuple[bytes, str, List[str]]:
        """Merge every promotion's linked attachments into one PDF.

        Returns ``(pdf_bytes, filename, skipped)`` where ``skipped`` lists the
        filenames of non-printable / unreadable attachments. Raises if the merged
        document ends up with zero pages (nothing printable at all).
        """
        ids = [str(pid) for pid in (promotion_ids or []) if pid]
        out = fitz.open()
        skipped: List[str] = []
        try:
            for promotion_id in ids:  # preserve caller (grid) order
                links = (
                    self.db.query(PromotionAttachment)
                    .filter(PromotionAttachment.promotion_id == promotion_id)
                    .order_by(
                        PromotionAttachment.sort_order.asc().nullslast(),
                        PromotionAttachment.created_at.asc(),
                    )
                    .all()
                )
                for link in links:
                    att = getattr(link, "attachment", None)
                    if att is None:
                        continue
                    label = (
                        getattr(att, "original_filename", None)
                        or getattr(att, "stored_filename", None)
                        or str(getattr(att, "id", "attachment"))
                    )
                    try:
                        provider = normalize_provider(getattr(att, "storage_provider", None))
                        key = extract_key(getattr(att, "file_path", None))
                        if not key:
                            skipped.append(label)
                            continue
                        raw = get_backend(provider).download_file(key)
                    except Exception:  # noqa: BLE001 - best-effort per attachment
                        logger.warning(
                            "promotions PDF: failed to download attachment %s",
                            getattr(att, "id", "?"),
                            exc_info=True,
                        )
                        skipped.append(label)
                        continue

                    if _is_pdf(att):
                        try:
                            with fitz.open(stream=raw, filetype="pdf") as src:
                                out.insert_pdf(src)
                        except Exception:  # noqa: BLE001
                            logger.warning(
                                "promotions PDF: failed to append PDF attachment %s",
                                getattr(att, "id", "?"),
                                exc_info=True,
                            )
                            skipped.append(label)
                    elif _is_image(att):
                        try:
                            self._append_image_page(out, raw)
                        except Exception:  # noqa: BLE001
                            logger.warning(
                                "promotions PDF: failed to embed image attachment %s",
                                getattr(att, "id", "?"),
                                exc_info=True,
                            )
                            skipped.append(label)
                    else:
                        skipped.append(label)

            if out.page_count == 0:
                raise ValueError(
                    "No printable attachments found for the selected promotions."
                )

            buf = io.BytesIO()
            out.save(buf)
            pdf_bytes = buf.getvalue()
        finally:
            out.close()

        today = datetime.now(_MALAYSIA_TZ).strftime("%d-%m-%Y")
        filename = f"promotions-expiring-{today}.pdf"
        return pdf_bytes, filename, skipped

    @staticmethod
    def _append_image_page(doc: "fitz.Document", raw: bytes) -> None:
        """Add one page sized to the image and draw the image full-bleed."""
        img = fitz.open(stream=raw, filetype=None)  # image → single-page doc
        try:
            rect = img[0].rect
            pdf_bytes = img.convert_to_pdf()
        finally:
            img.close()
        with fitz.open(stream=pdf_bytes, filetype="pdf") as img_pdf:
            page = doc.new_page(width=rect.width, height=rect.height)
            page.show_pdf_page(page.rect, img_pdf, 0)
