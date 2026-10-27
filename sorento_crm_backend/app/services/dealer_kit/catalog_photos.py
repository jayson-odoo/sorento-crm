"""Product photos and their captions, read out of a supplier catalogue PDF (CATALOG-IMAGES).

Contract: ``documentation/plans/products/PLAN-catalog-image-extract-27oct.md``, "Phase 2
contract" and "Contract changes". Pure: no database. The flyer reader's own helpers do the
geometry (visible rectangle, crop fractions, full-bleed test) and the refusals, so a PDF this
system will not read as a flyer it will not read as a catalogue either.
"""
from __future__ import annotations

import hashlib
import io
import logging
import re
from dataclasses import dataclass
from typing import Optional

import fitz  # PyMuPDF

from app.services.dealer_kit.flyer_extraction import (
    EncryptedFlyerError,
    _covers_the_page,
    _crop_of,
    _pixel_box,
    _visible_rect,
)
from app.services.image_normalizer import ensure_rgb_image

logger = logging.getLogger(__name__)

__all__ = [
    "CatalogPhoto",
    "EncryptedFlyerError",
    "dhash",
    "extract_catalog_photos",
    "hamming",
]

# The owner's shape, plus hyphenated tokens that carry a digit (SRT73-WH-DIY, SRT-FH12-CP).
_CODE_PATTERNS = (
    re.compile(r"^[A-Z]{3,}\d{3,}[A-Z0-9\-]*$"),
    re.compile(r"^[A-Z][A-Z0-9]*\d[A-Z0-9]*(?:-[A-Z0-9]+)+$"),
    re.compile(r"^[A-Z]+(?:-[A-Z0-9]+)*-[A-Z0-9]*\d[A-Z0-9]*(?:-[A-Z0-9]+)*$"),
)
_PLACEHOLDER_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*_{3,}$")

# Same ceiling as the Excel importer's image check (npa_xlsx.py): a placement or soft mask
# above this is skipped before it is decoded, so one hostile PDF cannot exhaust the worker.
CATALOGUE_MAX_PIXELS = 40_000_000
CATALOGUE_MAX_PAGES = 300

MIN_SIDE_PT = 40.0
WIDE_BAND_FRACTION = 0.8
CAPTION_X_SLACK_PT = 20.0
_JPEG_QUALITY = 90


@dataclass(frozen=True)
class CatalogPhoto:
    page: int
    rect: tuple[float, float, float, float]
    block_codes: list[str]
    placeholders: list[str]
    image_bytes: bytes
    mime: str
    sha256: str
    width: int
    height: int

    @property
    def primary_code(self) -> Optional[str]:
        return self.block_codes[0] if self.block_codes else None


@dataclass(frozen=True)
class _Caption:
    anchor: tuple[float, float, float, float]
    codes: list[str]
    placeholders: list[str]


def _word(raw: str) -> str:
    return raw.strip().rstrip(",;:.")


def _is_code(word: str) -> bool:
    return any(pattern.match(word) for pattern in _CODE_PATTERNS)


COLUMN_GAP_PT = 30.0


def _segments(block: dict) -> list[tuple[list[str], tuple[float, float, float, float]]]:
    """A block's text as ``(words, bbox)`` pieces: one per line, split where a line jumps columns."""
    pieces: list[tuple[list[str], tuple[float, float, float, float]]] = []
    for line in block.get("lines", []):
        run: list[dict] = []
        runs: list[list[dict]] = []
        for span in line.get("spans", []):
            if not span.get("text", "").strip():
                continue
            if run and span["bbox"][0] - run[-1]["bbox"][2] > COLUMN_GAP_PT:
                runs.append(run)
                run = []
            run.append(span)
        if run:
            runs.append(run)
        for spans in runs:
            words = " ".join(span["text"] for span in spans).split()
            if words:
                bbox = (
                    min(span["bbox"][0] for span in spans),
                    min(span["bbox"][1] for span in spans),
                    max(span["bbox"][2] for span in spans),
                    max(span["bbox"][3] for span in spans),
                )
                pieces.append((words, bbox))
    return pieces


def _columns(
    pieces: list[tuple[list[str], tuple[float, float, float, float]]],
) -> list[list[tuple[list[str], tuple[float, float, float, float]]]]:
    """Pieces grouped by the column they start in, so two captions on one baseline stay two."""
    groups: list[list[tuple[list[str], tuple[float, float, float, float]]]] = []
    for piece in pieces:
        for group in groups:
            if abs(group[0][1][0] - piece[1][0]) <= COLUMN_GAP_PT:
                group.append(piece)
                break
        else:
            groups.append([piece])
    return groups


def _glue(
    group: list[tuple[list[str], tuple[float, float, float, float]]],
) -> list[tuple[list[str], tuple[float, float, float, float]]]:
    """A line whose first word starts with a hyphen is the tail of the previous line's last word."""
    lines: list[tuple[list[str], tuple[float, float, float, float]]] = []
    for words, bbox in group:
        words = list(words)
        if words[0].startswith("-") and lines:
            previous_words, previous_bbox = lines[-1]
            previous_words[-1] = previous_words[-1] + words[0]
            previous_words.extend(words[1:])
            continue
        lines.append((words, bbox))
    return lines


def _captions(page: "fitz.Page") -> list[_Caption]:
    captions: list[_Caption] = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for group in _columns(_segments(block)):
            anchor = None
            codes: list[str] = []
            placeholders: list[str] = []
            for words, bbox in _glue(group):
                for raw in words:
                    word = _word(raw)
                    if _PLACEHOLDER_PATTERN.match(word):
                        placeholders.append(word)
                    elif _is_code(word):
                        codes.append(word)
                        anchor = anchor or bbox
            if codes:
                captions.append(_Caption(anchor=anchor, codes=codes, placeholders=placeholders))
    return captions


def _caption_for(rect: tuple[float, float, float, float], captions: list[_Caption]) -> Optional[_Caption]:
    """The owner's proximity rule: below the photo's centre, inside its column, nearest wins."""
    cx_y = (rect[1] + rect[3]) / 2
    best: Optional[tuple[float, _Caption]] = None
    for caption in captions:
        if not caption.codes:
            continue
        x0, y0 = caption.anchor[0], caption.anchor[1]
        if y0 < cx_y:
            continue
        if not (rect[0] - CAPTION_X_SLACK_PT <= x0 <= rect[2]):
            continue
        distance = (y0 - cx_y) + 0.5 * abs(x0 - rect[0])
        if best is None or distance < best[0]:
            best = (distance, caption)
    return best[1] if best else None


def _smask_pixels(document: "fitz.Document", smask: int) -> Optional[int]:
    try:
        width = int(document.xref_get_key(smask, "Width")[1])
        height = int(document.xref_get_key(smask, "Height")[1])
    except Exception:  # noqa: BLE001
        return None
    return width * height


def _encode(
    document: "fitz.Document", xref: int, crop: tuple[float, float, float, float]
) -> Optional[tuple[bytes, str, int, int]]:
    """The placement's pixels, RGB, cut to the visible part. PNG with a soft mask, JPEG without."""
    from PIL import Image

    try:
        raw = document.extract_image(xref)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Catalogue image xref=%s could not be extracted: %s", xref, exc)
        return None
    content = raw.get("image")
    if not content:
        return None
    smask = int(raw.get("smask") or 0)
    if smask:
        pixels = _smask_pixels(document, smask)
        # An unreadable mask size is not trusted: skip rather than decode it.
        if pixels is None or pixels > CATALOGUE_MAX_PIXELS:
            return None
    extension = (raw.get("ext") or "").lower()
    content, _name, _mime = ensure_rgb_image(content, f"photo.{extension}", None)

    try:
        with Image.open(io.BytesIO(content)) as opened:
            image = opened.convert("RGB")
        mask = None
        if smask:
            mask_png = fitz.Pixmap(document, smask).tobytes("png")
            with Image.open(io.BytesIO(mask_png)) as opened_mask:
                mask = opened_mask.convert("L").resize(image.size)
        box = _pixel_box(crop, image.width, image.height)
        if box:
            image = image.crop(box)
            mask = mask.crop(box) if mask is not None else None
        out = io.BytesIO()
        if mask is not None:
            rgba = image.convert("RGBA")
            rgba.putalpha(mask)
            rgba.save(out, format="PNG")
            return out.getvalue(), "image/png", rgba.width, rgba.height
        image.save(out, format="JPEG", quality=_JPEG_QUALITY)
        return out.getvalue(), "image/jpeg", image.width, image.height
    except Exception as exc:  # noqa: BLE001 - a picture PIL cannot open
        logger.warning("Catalogue image xref=%s could not be re-encoded: %s", xref, exc)
        return None


def extract_catalog_photos(data: bytes, limit: Optional[int] = None) -> list[CatalogPhoto]:
    """Every kept photo. With ``limit``, decoding stops at ``limit + 1`` so a caller can tell the
    PDF holds too many without paying to decode them all."""
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # pragma: no cover
        raise ValueError("That file could not be read as a PDF.") from exc
    if document.needs_pass:
        document.close()
        raise EncryptedFlyerError("The PDF is password protected")
    if document.page_count == 0:
        document.close()
        raise ValueError("The PDF has no pages")
    if document.page_count > CATALOGUE_MAX_PAGES:
        document.close()
        raise ValueError(f"The PDF has more than {CATALOGUE_MAX_PAGES} pages.")

    photos: list[CatalogPhoto] = []
    encoded_cache: dict = {}
    try:
        for index in range(document.page_count):
            room = None if limit is None else limit + 1 - len(photos)
            if room is not None and room <= 0:
                break
            photos.extend(_read_page(document, document[index], index + 1, encoded_cache, room))
    finally:
        document.close()
    return photos


def _read_page(
    document: "fitz.Document",
    page: "fitz.Page",
    number: int,
    encoded_cache: dict,
    room: Optional[int],
) -> list[CatalogPhoto]:
    width = page.rect.width or 1
    height = page.rect.height or 1
    captions = _captions(page)
    found: list[CatalogPhoto] = []

    for placed in page.get_image_info(xrefs=True):
        bbox = placed.get("bbox")
        xref = int(placed.get("xref", 0))
        if not bbox or not xref:
            continue
        visible = _visible_rect(bbox, width, height)
        if visible is None:
            continue
        if visible[2] - visible[0] < MIN_SIDE_PT or visible[3] - visible[1] < MIN_SIDE_PT:
            continue
        if _covers_the_page(visible, width, height):
            continue
        # PyMuPDF 2.0 writes placement sizes as float32 (475.998 for 476), so compare with a hair of slack.
        if (visible[2] - visible[0]) >= WIDE_BAND_FRACTION * width - 0.01:
            continue
        if int(placed.get("width", 0)) * int(placed.get("height", 0)) > CATALOGUE_MAX_PIXELS:
            continue

        if room is not None and len(found) >= room:
            break
        crop = _crop_of(bbox, visible)
        # One (image, crop) is re-encoded once per run, however many times it is placed.
        cache_key = (xref, tuple(round(v, 4) for v in crop))
        if cache_key not in encoded_cache:
            encoded_cache[cache_key] = _encode(document, xref, crop)
        encoded = encoded_cache[cache_key]
        if encoded is None:
            continue
        image_bytes, mime, px_w, px_h = encoded
        caption = _caption_for(visible, captions)
        found.append(
            CatalogPhoto(
                page=number,
                rect=visible,
                block_codes=list(caption.codes) if caption else [],
                placeholders=list(caption.placeholders) if caption else [],
                image_bytes=image_bytes,
                mime=mime,
                sha256=hashlib.sha256(image_bytes).hexdigest(),
                width=px_w,
                height=px_h,
            )
        )

    found.sort(key=lambda photo: (round(photo.rect[1]), photo.rect[0]))
    return found


def dhash(image_bytes: bytes) -> str:
    """64-bit difference hash, 16 lowercase hex characters."""
    from PIL import Image

    with Image.open(io.BytesIO(image_bytes)) as opened:
        small = opened.convert("L").resize((9, 8), Image.LANCZOS)
    pixels = list(small.getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (1 if pixels[row * 9 + col] > pixels[row * 9 + col + 1] else 0)
    return f"{bits:016x}"


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")
