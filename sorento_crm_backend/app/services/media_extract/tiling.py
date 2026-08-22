"""Split one wide image into overlapping crops before the vision call.

A Sorento promo flyer is several product panels sharing a single frame. The
model tiles whatever it is given as one unit, so a three-panel flyer spends its
tile budget across all three and each panel's product codes - already 4-5 px
tall on an 841x317 screenshot - land below what the model can resolve. Cropping
the frame into per-panel images first gives every panel its own tile grid, which
is the same "zoom in" a person does, done deterministically and without asking
the model to drive it.

The crops go out as extra image parts on the SAME request, not as extra calls.
The model therefore sees every panel together and returns one JSON, so the
overlap between crops is reconciled by the model itself - there is no merge
step, no cross-call dedupe and no conflict resolution here.

Splitting is NOT free and NOT always right: a single-product portrait flyer
gains nothing and would only pay for the extra tiles. The split count is derived
from the aspect ratio rather than fixed, so a frame that is not wide is passed
through untouched.
"""
from __future__ import annotations

import base64
import io
import logging
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters for typing
    from app.services.llm_provider import ImagePart

logger = logging.getLogger(__name__)

# Below this the frame is a single subject and splitting it buys nothing. 2.0
# clears the shapes a lone product arrives in - a 1.27 portrait single-product
# flyer, an ordinary 1.5 (3:2) or 1.33 (4:3) phone photo - and sits below the
# ~2.65 of the three-panel promo sheet this exists for. Splitting a plain photo
# of one item would only multiply its tile cost.
SPLIT_MIN_RATIO = 2.0

# A panorama would otherwise derive a split count that blows the token budget for
# no extra readability, so the derived count is capped.
MAX_SPLITS = 4

# Enough that a product code straddling a seam is whole in one of the two crops
# either side of it. The model reconciles the duplicate itself.
OVERLAP_FRACTION = 0.12

# A frame with a short edge under this is too small for its crops to carry any
# more detail than the whole, and splitting it only multiplies the tile count.
MIN_SHORT_EDGE_PX = 200

# JPEG is re-encoded at high quality rather than the default: compression
# artifacts land hardest on exactly the small text this is trying to rescue.
_JPEG_QUALITY = 92


def split_count(width: int, height: int) -> int:
    """How many crops this frame should become. 1 means "leave it alone"."""
    long_edge, short_edge = max(width, height), min(width, height)
    if short_edge < MIN_SHORT_EDGE_PX:
        return 1
    ratio = long_edge / short_edge
    if ratio < SPLIT_MIN_RATIO:
        return 1
    return min(math.ceil(ratio), MAX_SPLITS)


def _spans(length: int, count: int) -> list[tuple[int, int]]:
    """Start/end offsets along the long axis, overlapping by OVERLAP_FRACTION."""
    step = length / count
    overlap = step * OVERLAP_FRACTION
    out: list[tuple[int, int]] = []
    for i in range(count):
        start = max(0, int(round(i * step - overlap)))
        end = min(length, int(round((i + 1) * step + overlap)))
        out.append((start, end))
    return out


def split_image_part(part: "ImagePart") -> list["ImagePart"]:
    """Return ``part`` alone, or the overlapping crops it should become.

    Any failure to decode is returned as the original part rather than raised:
    a frame this cannot open is one the vision call can still try, and losing the
    read entirely is a worse outcome than reading it un-split.
    """
    from PIL import Image  # local: keeps Pillow off the import path of callers

    from app.services.llm_provider import ImagePart

    try:
        raw = base64.b64decode(part.data_b64)
        image = Image.open(io.BytesIO(raw))
        image.load()
    except Exception:  # noqa: BLE001 - an unreadable frame is not a failed job
        logger.warning("media tiling could not decode the image; sending it whole")
        return [part]

    count = split_count(image.width, image.height)
    if count == 1:
        return [part]

    horizontal = image.width >= image.height
    fmt, mime = ("JPEG", "image/jpeg") if part.mime == "image/jpeg" else ("PNG", "image/png")
    if fmt == "JPEG" and image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    crops: list[ImagePart] = []
    for start, end in _spans(image.width if horizontal else image.height, count):
        box = (start, 0, end, image.height) if horizontal else (0, start, image.width, end)
        buf = io.BytesIO()
        save_kwargs = {"quality": _JPEG_QUALITY} if fmt == "JPEG" else {}
        image.crop(box).save(buf, format=fmt, **save_kwargs)
        crops.append(
            ImagePart(mime=mime, data_b64=base64.b64encode(buf.getvalue()).decode("ascii"))
        )

    logger.info(
        "media tiling split %dx%d into %d crops along the %s axis",
        image.width,
        image.height,
        count,
        "horizontal" if horizontal else "vertical",
    )
    return crops
