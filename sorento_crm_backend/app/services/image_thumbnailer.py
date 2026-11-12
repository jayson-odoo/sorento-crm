"""The rendition service: every resized copy of a stored image is made here (IMAGE-UNIFY).

Owner ruling, 3 Nov 2026: ONE way to store, size, deliver and render images, so the spec-sheet
freeze (#2126, 165 MB of originals in one tab) cannot come back on another screen.
Plan: documentation/plans/resources/PLAN-image-unify-03nov.md.

Every stored image has two renditions beside it, under derived keys:

* ``<key>.thumb.jpg``  - 320 px: grids, table cells, lists (also kept in ``attachments.thumbnail_path``),
* ``<key>.medium.jpg`` - 1024 px: a screen that shows one picture big (designer, previews).

Both are made at upload (``store_renditions``, one decode) and, for files uploaded before that,
on demand the first time a screen asks (``rendition_urls``, one generation per file however many
ask at once). There is no backfill (owner Q4). A printed copy is sized per export to the image
layer's designed box (``print_box_px`` / ``print_scale``, owner Q1) and is not stored here.

``downscale`` is the ONLY resize routine in the backend; a guard test fails on a new ``Image.open``
anywhere else that is not on its reasoned allow-list (``tests/test_image_unify_p1.py``).
"""
from __future__ import annotations

import io
import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------- sizes

#: Longest edge of each stored rendition. thumb: a 114 px card at 2x dpr is 228 px, so 320 stays
#: sharp. medium: at least twice the ~420 px picture box of the biggest on-screen page, so a
#: drawing's measurements read on a Retina screen (crew, 3 Nov).
RENDITIONS: Dict[str, int] = {"thumb": 320, "medium": 1024}
_QUALITY: Dict[str, int] = {"thumb": 80, "medium": 82}
_MAX_EDGE = RENDITIONS["thumb"]
_JPEG_QUALITY = _QUALITY["thumb"]

#: A rendition's bytes never change under its key: an original is never overwritten in place
#: (Files "Replace" writes a NEW key, crew ruling (b) on #2133), so a browser may keep it a year.
#: A shared cache (the CDN edge) keeps it a day, so a deleted image stops being served there within
#: a day rather than a year (security review, #2133).
RENDITION_CACHE_CONTROL = "public, max-age=31536000, s-maxage=86400, immutable"

#: Only these formats are decoded for a document embed; what comes out is always Pillow's own JPEG
#: re-encode. An SVG (whatever its stored mime) is markup a renderer would follow links out of.
EMBEDDABLE_FORMATS = ("PNG", "JPEG", "WEBP")
#: Refused before decoding (checked after a JPEG draft): a tiny palette PNG can claim hundreds of
#: millions of pixels, and a 40 MP RGBA decode is ~160 MB already.
MAX_IMAGE_PIXELS = 40_000_000

#: What a rendition is ever decoded from. Pillow reads far more (TIFF, PSD, ICO, EPS ...), and those
#: parsers carry most of its CVE history; renditions are for photographs (security review, #2133).
RENDITION_FORMATS = ("JPEG", "PNG", "WEBP", "GIF")
#: The ceiling for renditions. Higher than a document embed's: an upload's thumbnail was made with
#: no ceiling before IMAGE-UNIFY, and a big PNG cannot draft-decode, so 40 MP would leave a 42 MP
#: PNG with no thumbnail and the grid loading its original (code review B1). 100 MP is the
#: ceiling #2126's spec sheet export already decodes to.
RENDITION_MAX_PIXELS = 100_000_000

# Only bytes that decode as a raster image get a rendition. Anything else (PDF, xlsx, ...) is None.
_RASTER_MIMES = {"image/jpeg", "image/jpg", "image/pjpeg", "image/png", "image/webp"}
_SNIFFABLE_MIMES = {"", "application/octet-stream", "binary/octet-stream"}

_SUFFIX = {"thumb": ".thumb.jpg", "medium": ".medium.jpg"}
_THUMB_SUFFIX = _SUFFIX["thumb"]


def rendition_key(original_key: str, size: str) -> str:
    """Deterministic object key of ``size`` ("thumb" | "medium") for ``original_key``."""
    return f"{original_key}{_SUFFIX[size]}"


def thumbnail_key_for(original_key: str) -> str:
    """Deterministic object key for the thumbnail of ``original_key``."""
    return rendition_key(original_key, "thumb")


def _looks_like_image(mime: Optional[str]) -> bool:
    lower = (mime or "").lower()
    if not lower:
        return True  # unknown → let the decode attempt decide
    if lower in _SNIFFABLE_MIMES:
        return True
    return lower in _RASTER_MIMES or lower.startswith("image/")


# ----------------------------------------------------------------------------- the one resize


@dataclass(frozen=True)
class RenderedImage:
    """A JPEG made by ``downscale``."""

    data: bytes
    mime_type: str
    width: int
    height: int


def downscale(
    raw: bytes,
    box: int,
    quality: int = _JPEG_QUALITY,
    *,
    formats: Optional[Sequence[str]] = None,
    upright: bool = True,
    draft: bool = True,
    max_pixels: Optional[int] = None,
    label: Any = None,
) -> Optional[RenderedImage]:
    """Pillow's own JPEG re-encode of ``raw`` inside ``box`` px; ``None`` when it cannot be.

    Only ever shrinks, aspect kept. ``upright`` applies the EXIF orientation first (the re-encode
    drops that tag and a browser honours it on the original). ``draft`` lets a JPEG decode at 1/2,
    1/4 or 1/8 scale (never below ``box``), so a 48 MP photograph is never decoded at full size;
    ``max_pixels`` is then checked on what will actually be decoded. Alpha and palette images are
    flattened onto WHITE (a plain convert puts black behind a cut-out product); CMYK goes to RGB
    (re-saved as-is it renders inverted). ``formats`` limits what is decoded at all.
    """
    try:
        from PIL import Image, ImageOps

        open_kwargs = {"formats": tuple(formats)} if formats else {}
        with Image.open(io.BytesIO(raw), **open_kwargs) as opened:
            if draft:
                opened.draft("RGB", (box, box))
            ceiling = MAX_IMAGE_PIXELS if max_pixels is None else max_pixels
            if opened.width * opened.height > ceiling:
                logger.warning(
                    "image: %s is %dx%d, over the pixel ceiling, no copy made",
                    label,
                    opened.width,
                    opened.height,
                )
                return None
            opened.load()
            image = ImageOps.exif_transpose(opened) or opened if upright else opened
            if image.mode in ("RGBA", "LA", "P", "PA"):
                rgba = image.convert("RGBA")
                canvas = Image.new("RGB", rgba.size, (255, 255, 255))
                canvas.paste(rgba, mask=rgba.split()[-1])
                image = canvas
            else:
                image = image.convert("RGB")
            image.thumbnail((box, box), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=quality, optimize=True)
            return RenderedImage(
                data=buffer.getvalue(),
                mime_type="image/jpeg",
                width=image.width,
                height=image.height,
            )
    except Exception as exc:  # noqa: BLE001 - not a decodable image / encode failed
        # Never the raw bytes: what leaves here is only ever Pillow's own re-encode.
        logger.warning("image: no copy of %s (%d bytes): %s", label, len(raw or b""), exc)
        return None


def generate_thumbnail(
    content: bytes,
    mime: Optional[str] = None,
    *,
    max_edge: int = _MAX_EDGE,
    quality: int = _JPEG_QUALITY,
) -> Optional[bytes]:
    """A small RGB JPEG thumbnail of ``content``, or ``None`` (non-image, decode failure)."""
    if not content or not _looks_like_image(mime):
        return None
    made = downscale(
        content,
        max_edge,
        quality,
        formats=RENDITION_FORMATS,
        max_pixels=RENDITION_MAX_PIXELS,
        label=mime,
    )
    return made.data if made is not None else None


# ----------------------------------------------------------------------------- writing


def _write_renditions(backend, original_key: str, content: bytes, mime) -> Dict[str, bool]:
    """Make and upload both renditions from ONE decode of ``content``.

    The medium is made from the original; the thumb from the medium, so the original is decoded
    once. Each upload is on its own: a failed medium never costs the thumb.
    """
    written = {"thumb": False, "medium": False}
    if not content or not _looks_like_image(mime):
        return written
    medium = downscale(
        content,
        RENDITIONS["medium"],
        _QUALITY["medium"],
        formats=RENDITION_FORMATS,
        max_pixels=RENDITION_MAX_PIXELS,
        label=original_key[:80],
    )
    if medium is None:
        return written
    thumb = downscale(medium.data, RENDITIONS["thumb"], _QUALITY["thumb"], label=original_key[:80])
    for size, made in (("thumb", thumb), ("medium", medium)):
        if made is None:
            continue
        try:
            backend.upload_file(
                file_content=made.data,
                file_path=rendition_key(original_key, size),
                content_type="image/jpeg",
                cache_control=RENDITION_CACHE_CONTROL,
            )
            written[size] = True
        except Exception as exc:  # noqa: BLE001 - a rendition is optional, never blocks
            logger.warning("rendition %s skipped for key=%s: %s", size, original_key[:80], exc)
    return written


def store_renditions(backend, provider, original_key: str, content: bytes, mime) -> Optional[str]:
    """Make and upload the thumb and medium of an image; return the thumb's CDN base URL.

    Shared by every upload path, including a Replace (which writes its new bytes under a NEW key,
    ``storage_router.replace_storage_key``); this process forgets what it knew about the keys.
    Best-effort: a non-image or any failure returns None; a rendition must NEVER fail an upload.
    """
    from app.services.storage_router import cdn_base_url, normalize_provider

    try:
        written = _write_renditions(backend, original_key, content, mime)
        prov = normalize_provider(provider)
        for size in RENDITIONS:
            forget_rendition(_token(prov, rendition_key(original_key, size)))
        if not written["thumb"]:
            return None
        return cdn_base_url(provider, thumbnail_key_for(original_key))
    except Exception as exc:  # noqa: BLE001 - never block the upload
        logger.warning("renditions skipped for key=%s: %s", (original_key or "")[:80], exc)
        return None


#: The name every upload path has called since the grid thumbnails; it now writes both renditions.
store_thumbnail = store_renditions


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


def _crop_fraction(crop: Optional[Mapping[str, Any]], axis: str) -> float:
    try:
        value = float((crop or {}).get(axis, 1) or 0)
    except (TypeError, ValueError):
        value = 1.0
    return min(max(value, _MIN_CROP_FRACTION), 1.0)


def print_scale(
    src_w: int,
    src_h: int,
    box_px: Tuple[int, int],
    fit: Optional[str],
    crop: Optional[Mapping[str, Any]] = None,
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


#: Another process held the file's lock past a caller's whole budget (it may have crashed while
#: holding it): later callers skip the wait for this long instead of each spending their budget.
_HELD_MISS_SECONDS = 30


def _miss(token: str, seconds: float = _MISS_SECONDS) -> None:
    with _memo_lock:
        if len(_missed) >= _MISSED_MAX:
            _missed.clear()
        _missed[token] = time.monotonic() + seconds


def _is_known(token: str) -> bool:
    with _memo_lock:
        return token in _known


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
                # thread_local=False: the lock is taken here and released by the generation thread,
                # and redis-py otherwise keeps its token per thread, so that release would fail
                # and leave the file locked for _LOCK_SECONDS.
                candidate = client.lock(
                    name, timeout=_LOCK_SECONDS, blocking=False, thread_local=False
                )
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
    held = True
    while time.monotonic() < deadline:
        time.sleep(min(_LOCK_POLL_SECONDS, max(0.0, deadline - time.monotonic())))
        try:
            if not client.exists(name):
                held = False
                break
        except Exception:  # noqa: BLE001 - Redis gone mid-wait: just look at storage
            held = False
            break
    try:
        if exists():
            _remember(token)
            return True
    except Exception:  # noqa: BLE001
        pass
    if held:
        _miss(token, _HELD_MISS_SECONDS)
    return False


# ----------------------------------------------------------------------------- reading (Q4)

#: Signed URL lifetime handed to a screen. ``storage_router`` caches each signature for a sixth of
#: this, so a URL a reader receives always has most of its hour left.
URL_EXPIRES_IN = 60 * 60
#: Callers waiting on single-flight generations for one request run side by side, so a page of
#: twenty uncached photos uses both generation threads; generation itself stays at 2 (``_pool``).
_waiters = ThreadPoolExecutor(max_workers=16, thread_name_prefix="rendition-wait")


def _token(provider: str, key: str) -> str:
    return f"{provider}:{key}"


def rendition_urls(
    db,
    attachment_ids: Iterable[Optional[str]],
    size: str,
    *,
    release: Optional[Callable[[], None]] = None,
    wait_seconds: float = RENDITION_WAIT_SECONDS,
    expires_in: int = URL_EXPIRES_IN,
) -> Dict[str, str]:
    """Signed URLs of the ``size`` rendition of each attachment; never the original.

    Where each file lives is read first and ``release`` then hands the DB connection back before
    any byte moves. A rendition that does not exist yet is made from the original (both sizes at
    once), at most once however many requests ask (``single_flight``). An attachment whose
    rendition is not ready within ``wait_seconds`` (whole call), or cannot be made, is LEFT OUT:
    the caller shows the next size down. Its generation carries on and the next ask gets it.
    """
    from app.models.resources import Attachment
    from app.services.storage_router import (
        extract_key,
        get_backend,
        normalize_provider,
        resolve_signed_url,
    )

    if size not in RENDITIONS:
        raise ValueError(f"unknown rendition size {size!r}")
    wanted = list(dict.fromkeys(str(a) for a in attachment_ids if a))
    rows = (
        [
            (str(r.id), r.file_path, r.thumbnail_path, r.storage_provider, r.mime_type)
            for r in db.query(Attachment).filter(Attachment.id.in_(wanted)).all()
        ]
        if wanted
        else []
    )
    if release is not None:
        release()
    deadline = time.monotonic() + wait_seconds

    def sign(target: str, provider: str) -> Optional[str]:
        return resolve_signed_url(target, provider=provider, expires_in=expires_in, strict=True)

    def make_and_sign(attachment_id, backend, provider, original, target, mime) -> Optional[str]:
        def make() -> bool:
            raw = backend.download_file(original)
            return _write_renditions(backend, original, raw, mime)[size]

        try:
            ready = single_flight(
                _token(provider, target),
                lambda: bool(backend.file_exists(target)),
                make,
                deadline=deadline,
            )
            return sign(target, provider) if ready else None
        except Exception:  # noqa: BLE001 - the next size down stays on screen
            logger.warning("rendition: no %s for %s", size, attachment_id, exc_info=True)
            return None

    out: Dict[str, str] = {}
    pending = {}
    for attachment_id, file_path, thumbnail_path, provider_name, mime in rows:
        try:
            original = extract_key(file_path) if file_path else None
            if not original:
                continue
            provider = normalize_provider(provider_name)
            stored_thumb = extract_key(thumbnail_path) if thumbnail_path else None
            if size == "thumb" and stored_thumb:
                target, settled = stored_thumb, True
            else:
                target = rendition_key(original, size)
                settled = _is_known(_token(provider, target))
            if settled:
                # Known to exist: signed here, never queued behind another request's generations.
                url = sign(target, provider)
                if url:
                    out[attachment_id] = url
                continue
            pending[attachment_id] = _waiters.submit(
                make_and_sign, attachment_id, get_backend(provider), provider, original, target, mime
            )
        except Exception:  # noqa: BLE001 - the next size down stays on screen
            logger.warning("rendition: no %s for %s", size, attachment_id, exc_info=True)
    for attachment_id, future in pending.items():
        try:
            url = future.result(timeout=max(0.0, deadline - time.monotonic()) + 0.05)
        except Exception:  # noqa: BLE001 - out of time: left out, generation carries on
            url = None
        if url:
            out[attachment_id] = url
    return out
