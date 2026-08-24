"""Normalize uploaded raster images to an RGB color space.

WhatsApp Cloud API (and Meta's media validator behind Respond.io) reject JPEGs
in the CMYK / YCCK color space with a generic "Media upload error" - even
though browsers and Respond's own preview render them fine. Print-pipeline
exports (Illustrator, CAD, InDesign) routinely produce 4-channel CMYK JPEGs,
so technical-spec drawings hit this constantly.

We transcode CMYK / YCCK images to RGB JPEG at the upload boundary so stored
bytes are always WhatsApp-safe. RGB/grayscale JPEG and PNG pass through
untouched - only the color spaces Meta actually rejects are converted, so we
don't strip PNG transparency or needlessly re-encode greyscale scans.
See the M9713SS-BL CMYK incident.
"""
from __future__ import annotations

import io
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# Image MIME types we inspect. Blank/octet-stream is sniffed; anything else passes.
_RASTER_MIMES = {"image/jpeg", "image/jpg", "image/pjpeg", "image/png"}
_SNIFFABLE_MIMES = {"", "application/octet-stream", "binary/octet-stream"}

# Only these PIL modes break WhatsApp/Meta. Convert to RGB; leave the rest alone.
_REJECTED_MODES = {"CMYK", "YCCK"}

_JPEG_QUALITY = 90


def _decode_mode(content: bytes) -> str | None:
    """Return the PIL color mode of `content`, or None if not a decodable image."""
    try:
        from PIL import Image

        with Image.open(io.BytesIO(content)) as im:
            return im.mode
    except Exception:  # noqa: BLE001 - not a decodable image
        return None


def needs_rgb_conversion(content: bytes, mime: str | None) -> bool:
    """True if `content` is a raster image in a color space Meta rejects (CMYK/YCCK)."""
    if not content:
        return False
    lower = (mime or "").lower()
    if lower and lower not in _RASTER_MIMES and lower not in _SNIFFABLE_MIMES:
        return False
    return _decode_mode(content) in _REJECTED_MODES


def ensure_rgb_image(
    content: bytes,
    filename: str | None,
    mime: str | None,
) -> Tuple[bytes, str | None, str | None]:
    """Return (content, filename, mime) with any CMYK/YCCK image converted to RGB JPEG.

    Idempotent: an image already in an accepted color space (or a non-image) is
    returned unchanged. Best-effort: any decode/convert failure returns the
    original bytes so a malformed file never blocks an upload.
    """
    if not needs_rgb_conversion(content, mime):
        return content, filename, mime

    try:
        from PIL import Image

        with Image.open(io.BytesIO(content)) as im:
            original_mode = im.mode
            out = io.BytesIO()
            im.convert("RGB").save(out, format="JPEG", quality=_JPEG_QUALITY)
            new_content = out.getvalue()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Image RGB normalization skipped (%s): %s", filename, exc)
        return content, filename, mime

    logger.info(
        "Converted %s image to RGB JPEG (%s): %d -> %d bytes",
        original_mode,
        filename,
        len(content),
        len(new_content),
    )
    # CMYK/YCCK source is always JPEG, so the .jpg/.jpeg extension already fits;
    # leave filename untouched to keep the storage key and display name stable.
    return new_content, filename, "image/jpeg"
