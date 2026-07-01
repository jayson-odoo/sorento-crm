"""Generate small raster thumbnails for the Files grid view.

Product photos are stored at full resolution (routinely 3000–4500 px on the
long edge — 10–20 MP). The Drive grid renders them into a ~114 px box, so the
browser downloads and decodes multi-megapixel bitmaps only to paint them at
thumbnail size. A single 4500×4500 image decodes to ~81 MB of raw bitmap in
RAM plus a large GPU texture; a page of 90+ such cards drowns the compositor on
normal hardware and makes scrolling stutter.

We produce a ~320 px JPEG thumbnail at the upload boundary (and via a backfill
for existing rows), stored as its own object next to the original, so the grid
paints a tiny image instead. Best-effort and idempotent: a non-image or a
decode failure yields ``None`` and the caller falls back to the original.
"""
from __future__ import annotations

import io
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Longest-edge target. 114 px card × 2 (retina dpr) ≈ 228 px, so 320 stays sharp.
_MAX_EDGE = 320
_JPEG_QUALITY = 80

# Only bytes that decode as a raster image get a thumbnail. Mirrors the set the
# normalizer inspects; anything else (PDF, xlsx, ...) returns None.
_RASTER_MIMES = {"image/jpeg", "image/jpg", "image/pjpeg", "image/png", "image/webp"}
_SNIFFABLE_MIMES = {"", "application/octet-stream", "binary/octet-stream"}

# Thumbnails are stored at "{original_key}.thumb.jpg".
_THUMB_SUFFIX = ".thumb.jpg"


def thumbnail_key_for(original_key: str) -> str:
    """Deterministic object key for the thumbnail of ``original_key``."""
    return f"{original_key}{_THUMB_SUFFIX}"


def _looks_like_image(mime: Optional[str]) -> bool:
    lower = (mime or "").lower()
    if not lower:
        return True  # unknown → let the decode attempt decide
    if lower in _SNIFFABLE_MIMES:
        return True
    return lower in _RASTER_MIMES or lower.startswith("image/")


def generate_thumbnail(
    content: bytes,
    mime: Optional[str] = None,
    *,
    max_edge: int = _MAX_EDGE,
    quality: int = _JPEG_QUALITY,
) -> Optional[bytes]:
    """Return a small RGB JPEG thumbnail of ``content``, or ``None``.

    ``None`` is returned for non-images and for any decode/encode failure — the
    caller must treat that as "no thumbnail" and serve the original. Aspect
    ratio is preserved (``Image.thumbnail`` only ever downscales), so the grid's
    ``object-cover`` crop never distorts.
    """
    if not content or not _looks_like_image(mime):
        return None

    try:
        from PIL import Image

        with Image.open(io.BytesIO(content)) as im:
            # Flatten alpha / palette / CMYK onto white so the JPEG is valid and
            # WhatsApp-safe, matching the RGB normalization done on upload.
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            im.thumbnail((max_edge, max_edge), Image.LANCZOS)
            out = io.BytesIO()
            im.save(out, format="JPEG", quality=quality, optimize=True)
            return out.getvalue()
    except Exception as exc:  # noqa: BLE001 — not a decodable image / encode failed
        logger.warning("Thumbnail generation skipped (mime=%s): %s", mime, exc)
        return None


def store_thumbnail(backend, provider, original_key: str, content: bytes, mime) -> Optional[str]:
    """Generate + upload a grid thumbnail for an image; return its CDN base URL.

    Shared by every upload path (single-file route + bulk-import task). Best-effort:
    a non-image, or any generate/upload failure, returns None so the grid falls back
    to the original — a failed thumbnail must NEVER fail the upload.
    """
    from app.services.storage_router import cdn_base_url

    try:
        thumb = generate_thumbnail(content, mime)
        if not thumb:
            return None
        thumb_key = thumbnail_key_for(original_key)
        backend.upload_file(
            file_content=thumb, file_path=thumb_key, content_type="image/jpeg"
        )
        return cdn_base_url(provider, thumb_key)
    except Exception as exc:  # noqa: BLE001 — thumbnail is optional, never block upload
        logger.warning("Thumbnail store skipped for key=%s: %s", (original_key or "")[:80], exc)
        return None
