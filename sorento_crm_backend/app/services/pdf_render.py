"""Shared helpers for the entity PDF exports (complaint, product inquiry, ...).

Every export follows the same shape: build an HTML document from the record,
inline its image attachments as base64 data URIs, and hand the string to
WeasyPrint. That plumbing lives here so the per-entity services only own their
own layout, and a fix to image classification or the WeasyPrint guard lands in
one place.

WeasyPrint needs native cairo/pango/gdk-pixbuf libs; the import is guarded so
the API/worker never crash if they're missing - the caller marks the download
failed with a clear message instead.
"""
import base64
import logging
import mimetypes
import os
from html import escape
from typing import Optional

logger = logging.getLogger(__name__)

_IMAGE_MIME_PREFIX = "image/"
# Fallback when the stored mime_type is missing/generic (e.g. WhatsApp .jpeg
# uploads land as application/octet-stream or NULL). Extension wins so any photo
# type renders in the PHOTOS section instead of being dumped under OTHER.
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".heif", ".tif", ".tiff"}


class PDFRenderingUnavailable(RuntimeError):
    """Raised when WeasyPrint cannot render (native libs missing)."""


def image_mime(att) -> Optional[str]:
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


def embedded_images(links, *, context: str = "PDF") -> list[dict]:
    """Download the image attachments behind ``links`` as data-URI dicts.

    ``links`` are entity_attachment_links rows, each exposing ``.attachment``.
    Returns ``[{"name": ..., "data_uri": ...}]``. Best-effort per image: a failed
    fetch is logged and skipped rather than failing the whole export.
    """
    from app.services.storage_router import extract_key, get_backend, normalize_provider

    out: list[dict] = []
    for link in links or []:
        att = getattr(link, "attachment", None)
        if att is None:
            continue
        mime = image_mime(att)
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
                "%s: failed to embed attachment %s", context, getattr(att, "id", "?"), exc_info=True
            )
    return out


def non_image_names(links) -> list[str]:
    """Filenames of the non-image attachments behind ``links`` (listed, not embedded)."""
    names: list[str] = []
    for link in links or []:
        att = getattr(link, "attachment", None)
        if att is None:
            continue
        if image_mime(att) is None:
            names.append(getattr(att, "original_filename", None) or "attachment")
    return names


def photos_section_html(images: list[dict], *, empty: str = "No photo attachments.") -> str:
    """`<figure>` grid for embedded images, or an italic empty state."""
    if not images:
        return f"<p class='empty'>{escape(empty)}</p>"
    figures = "".join(
        f"<figure><img src='{img['data_uri']}'/>"
        f"<figcaption>{escape(img['name'])}</figcaption></figure>"
        for img in images
    )
    return f"<div class='photos'>{figures}</div>"


def names_list_html(names: list[str], *, empty: str = "None.") -> str:
    """`<ul>` of attachment filenames, or an italic empty state."""
    if not names:
        return f"<p class='empty'>{escape(empty)}</p>"
    return "<ul>" + "".join(f"<li>{escape(n)}</li>" for n in names) + "</ul>"


def render_html(html: str) -> bytes:
    """Render an HTML string to PDF bytes.

    Raises PDFRenderingUnavailable when WeasyPrint cannot load or render, so the
    caller can mark the download failed with a readable message.
    """
    try:
        from weasyprint import HTML  # noqa: WPS433 (guarded optional dep)
    except Exception as e:  # ImportError or native-lib load error
        raise PDFRenderingUnavailable(
            f"PDF rendering is unavailable on this host (WeasyPrint import failed: {e})."
        ) from e
    try:
        return HTML(string=html).write_pdf()
    except Exception as e:
        raise PDFRenderingUnavailable(
            f"PDF rendering failed (WeasyPrint native libraries missing or broken: {e})."
        ) from e
