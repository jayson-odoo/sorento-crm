"""Generate small raster thumbnails for the Files grid view.

Product photos are stored at full resolution (routinely 3000 - 4500 px on the
long edge - 10 - 20 MP). The Drive grid renders them into a ~114 px box, so the
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

    ``None`` is returned for non-images and for any decode/encode failure - the
    caller must treat that as "no thumbnail" and serve the original. Aspect
    ratio is preserved (``Image.thumbnail`` only ever downscales), so the grid's
    ``object-cover`` crop never distorts.
    """
    if not content or not _looks_like_image(mime):
        return None

    try:
        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(content)) as opened:
            # Let a big JPEG decode at reduced size (never below the thumbnail): the transpose
            # below copies the image, which would otherwise force a full-size decode.
            opened.draft("RGB", (max_edge, max_edge))
            # Upright first: a JPEG re-encode drops the EXIF orientation a browser honours on
            # the original, so a phone photo's thumbnail came out on its side.
            im = ImageOps.exif_transpose(opened) or opened
            # Flatten alpha / palette onto WHITE (a plain convert puts black behind a cut-out
            # product), CMYK straight to RGB, so the JPEG is valid and WhatsApp-safe.
            if im.mode in ("RGBA", "LA", "P", "PA"):
                rgba = im.convert("RGBA")
                canvas = Image.new("RGB", rgba.size, (255, 255, 255))
                canvas.paste(rgba, mask=rgba.split()[-1])
                im = canvas
            elif im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            im.thumbnail((max_edge, max_edge), Image.LANCZOS)
            out = io.BytesIO()
            im.save(out, format="JPEG", quality=quality, optimize=True)
            return out.getvalue()
    except Exception as exc:  # noqa: BLE001 - not a decodable image / encode failed
        logger.warning("Thumbnail generation skipped (mime=%s): %s", mime, exc)
        return None


def store_thumbnail(backend, provider, original_key: str, content: bytes, mime) -> Optional[str]:
    """Generate + upload a grid thumbnail for an image; return its CDN base URL.

    Shared by every upload path (single-file route + bulk-import task). Best-effort:
    a non-image, or any generate/upload failure, returns None so the grid falls back
    to the original - a failed thumbnail must NEVER fail the upload.
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
    except Exception as exc:  # noqa: BLE001 - thumbnail is optional, never block upload
        logger.warning("Thumbnail store skipped for key=%s: %s", (original_key or "")[:80], exc)
        return None


# =============================================================================
# IMAGE-UNIFY: the rendition service (documentation/plans/resources/PLAN-image-unify-03nov.md)
# =============================================================================

import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Any, Callable, Dict, Mapping, Optional as _Opt, Tuple

#: Renditions live beside their original under a derived key and are only ever replaced by a
#: regeneration from the same original, so a cache may keep them for a year.
RENDITION_CACHE_CONTROL = "public, max-age=31536000, immutable"

# ----------------------------------------------------------------------------- print copy (Q1)

#: Owner, 3 Nov: a printed photo is "the same size as what's designed": its image layer's box.
PRINT_DPI = 300
#: Same floor as the designer's crop handles (lib/dealer-kit/image-crop.ts MIN_CROP_FRACTION).
_MIN_CROP_FRACTION = 0.02


def print_box_px(width_mm: float, height_mm: float, dpi: int = PRINT_DPI) -> Tuple[int, int]:
    """An image layer's designed box in printer pixels, rounded up so a copy is never short."""
    return (
        math.ceil(float(width_mm) / 25.4 * dpi - 1e-9),
        math.ceil(float(height_mm) / 25.4 * dpi - 1e-9),
    )


def _crop_fraction(crop: _Opt[Mapping[str, Any]], axis: str) -> float:
    try:
        value = float((crop or {}).get(axis, 1) or 0)
    except (TypeError, ValueError):
        value = 1.0
    return min(max(value, _MIN_CROP_FRACTION), 1.0)


def print_scale(
    src_w: int,
    src_h: int,
    box_px: Tuple[int, int],
    fit: _Opt[str],
    crop: _Opt[Mapping[str, Any]] = None,
) -> float:
    """How far the original can shrink and still fill its layer box at full print resolution.

    Mirrors how the layer is drawn (``KonvaTagLayer`` / ``TagSheetRenderer``): the normalised
    ``crop`` picks the source window first, then ``fit`` places that window in the box. ``cover``
    scales by the looser axis, ``contain`` by the tighter, ``stretch`` per axis (the copy keeps
    its aspect, so the sharper axis decides). Never above 1: a copy is never upscaled.
    """
    if src_w <= 0 or src_h <= 0:
        return 1.0
    window_w = src_w * _crop_fraction(crop, "width")
    window_h = src_h * _crop_fraction(crop, "height")
    sx = box_px[0] / window_w
    sy = box_px[1] / window_h
    scale = max(sx, sy) if fit in ("cover", "stretch") else min(sx, sy)
    return min(1.0, scale)


# ----------------------------------------------------------------------------- on-demand (Q4)

#: The whole wait one request may spend on renditions (owner Q4: fast; plan: 8 s, then thumb).
RENDITION_WAIT_SECONDS = 8.0
#: Lock lifetime in Redis: longer than any single generation, short enough that a crashed
#: holder does not block a file for long.
_LOCK_SECONDS = 120
_LOCK_POLL_SECONDS = 0.25
#: A file that could not be made is not tried again for this long.
_MISS_SECONDS = 10 * 60
_KNOWN_MAX = 20000
_MISSED_MAX = 4096

_memo_lock = threading.Lock()
_known: set = set()
_missed: Dict[str, float] = {}
_inflight: Dict[str, threading.Event] = {}
#: Two generations at once per process: a 40 MP PNG decodes to ~160 MB, so this bounds memory.
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="rendition")
_DEFAULT_REDIS = object()


def reset_rendition_memo() -> None:
    """For tests."""
    with _memo_lock:
        _known.clear()
        _missed.clear()
        _inflight.clear()


def forget_rendition(token: str) -> None:
    """Drop what this process knows about ``token`` (an original was just replaced)."""
    with _memo_lock:
        _known.discard(token)
        _missed.pop(token, None)


def _remember(token: str) -> None:
    with _memo_lock:
        if len(_known) >= _KNOWN_MAX:
            _known.clear()
        _known.add(token)
        _missed.pop(token, None)


def _miss(token: str) -> None:
    with _memo_lock:
        if len(_missed) >= _MISSED_MAX:
            _missed.clear()
        _missed[token] = time.monotonic() + _MISS_SECONDS


def _default_redis():
    try:
        from app.services.queue_service import redis_conn

        return redis_conn
    except Exception:  # noqa: BLE001 - no Redis: one process still single-flights on its own
        return None


def _finish(token: str, event: threading.Event, lock) -> None:
    if lock is not None:
        try:
            lock.release()
        except Exception:  # noqa: BLE001 - expired or Redis gone; the TTL frees it
            pass
    with _memo_lock:
        _inflight.pop(token, None)
    event.set()


def single_flight(
    token: str,
    exists: Callable[[], bool],
    make: Callable[[], bool],
    *,
    deadline: float,
    redis: Any = _DEFAULT_REDIS,
) -> bool:
    """True once the object named by ``token`` exists, making it at most once.

    ``exists`` asks storage; ``make`` builds and stores the object and says whether it did.
    One generation per object: concurrent callers in this process wait on the first; callers in
    other processes see its Redis lock and wait for it to clear. Redis down means each process
    makes its own (identical bytes under the same key, so wasted work, never a wrong picture).
    Nobody waits past ``deadline`` (monotonic): a caller out of time gets False while the work
    carries on and is remembered for the next caller. A failed make is remembered as a miss for
    ``_MISS_SECONDS``.
    """
    now = time.monotonic()
    with _memo_lock:
        if token in _known:
            return True
        missed_until = _missed.get(token)
        if missed_until is not None and missed_until > now:
            return False
        event = _inflight.get(token)
        leader = event is None
        if leader:
            event = threading.Event()
            _inflight[token] = event

    if not leader:
        event.wait(max(0.0, deadline - time.monotonic()))
        with _memo_lock:
            return token in _known

    lock = None
    handed_off = False
    try:
        try:
            present = bool(exists())
        except Exception:  # noqa: BLE001 - unknown reads as absent; making it again is safe
            logger.warning("rendition: existence check failed for %s", token[:120], exc_info=True)
            present = False
        if present:
            _remember(token)
            return True

        client = _default_redis() if redis is _DEFAULT_REDIS else redis
        name = f"image-rendition:{token}"
        if client is not None:
            try:
                candidate = client.lock(name, timeout=_LOCK_SECONDS, blocking=False)
                if candidate.acquire(blocking=False):
                    lock = candidate
                else:
                    return _wait_for_other_process(token, exists, client, name, deadline)
            except Exception:  # noqa: BLE001 - Redis down: make it here
                lock = None

        def run() -> bool:
            try:
                ok = bool(make())
            except Exception:  # noqa: BLE001 - undecodable, over the ceiling, storage error
                logger.warning("rendition: could not make %s", token[:120], exc_info=True)
                ok = False
            if ok:
                _remember(token)
            else:
                _miss(token)
            _finish(token, event, lock)
            return ok

        future = _pool.submit(run)
        handed_off = True
        try:
            return future.result(timeout=max(0.0, deadline - time.monotonic()))
        except FuturesTimeout:
            return False
    finally:
        if not handed_off:
            _finish(token, event, lock)


def _wait_for_other_process(token, exists, client, name, deadline) -> bool:
    while time.monotonic() < deadline:
        time.sleep(min(_LOCK_POLL_SECONDS, max(0.0, deadline - time.monotonic())))
        try:
            if not client.exists(name):
                break
        except Exception:  # noqa: BLE001 - Redis gone mid-wait: just look at storage
            break
    try:
        if exists():
            _remember(token)
            return True
    except Exception:  # noqa: BLE001
        pass
    return False
