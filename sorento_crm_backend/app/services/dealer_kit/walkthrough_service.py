"""Showroom walkthroughs: named, ordered panoramic stops.

PLAN-showroom-walkthrough-28oct.md. Same request/worker split as the flyer
read (``flyer_reading_service``): the request stages the uploaded bytes, writes
the stop as ``processing`` and queues the build; the worker
(``app.tasks.walkthrough_tasks``) turns the bytes into one panorama and writes
``done`` or ``failed`` with the reason.

A stop has no company of its own. It is reached only through its walkthrough,
which is company scoped, so every lookup here goes through ``get_walkthrough``.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.dealer_kit import Walkthrough, WalkthroughStop
from app.services.dealer_kit.panorama import VIDEO_EXTENSIONS, Panorama
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

WALKTHROUGH_QUEUE = "walkthrough"
# A 24-frame stitch measures well under a minute; this is the ceiling for a
# loaded worker, not the expectation.
WALKTHROUGH_JOB_TIMEOUT = 15 * 60

# A minute of 1080p phone video is roughly 100 to 150 MB.
MAX_STOP_UPLOAD_BYTES = 300 * 1024 * 1024
MAX_STOP_FILES = 40

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
STAGING_PREFIX = "walkthroughs/pending/"
PANORAMA_PREFIX = "walkthroughs/panoramas/"


class StopStatus:
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


def _now() -> datetime:
    """Naive UTC, matching every other timestamp column in this system."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --------------------------------------------------------------------------- #
# Walkthroughs
# --------------------------------------------------------------------------- #
def list_walkthroughs(db: Session) -> list[Walkthrough]:
    return (
        db.query(Walkthrough)
        .order_by(Walkthrough.created_at.desc(), Walkthrough.id.desc())
        .all()
    )


def get_walkthrough(db: Session, walkthrough_id: str) -> Walkthrough:
    walkthrough = db.query(Walkthrough).filter(Walkthrough.id == walkthrough_id).first()
    if walkthrough is None:
        # Another company's walkthrough answers the same as a missing one.
        raise AppException(status_code=404, message="Walkthrough not found")
    return walkthrough


def create_walkthrough(db: Session, *, name: str, user_id: Optional[str]) -> Walkthrough:
    walkthrough = Walkthrough(name=name.strip(), created_by=user_id)
    db.add(walkthrough)
    db.commit()
    db.refresh(walkthrough)
    return walkthrough


def rename_walkthrough(db: Session, walkthrough_id: str, *, name: str) -> Walkthrough:
    walkthrough = get_walkthrough(db, walkthrough_id)
    walkthrough.name = name.strip()
    db.commit()
    db.refresh(walkthrough)
    return walkthrough


def delete_walkthrough(db: Session, walkthrough_id: str) -> None:
    walkthrough = get_walkthrough(db, walkthrough_id)
    objects = [_stored(stop) for stop in walkthrough.stops]
    db.delete(walkthrough)
    db.commit()
    # After the commit: bytes are the one part no rollback can bring back.
    _purge(objects)


# --------------------------------------------------------------------------- #
# Stops
# --------------------------------------------------------------------------- #
def get_stop(db: Session, walkthrough_id: str, stop_id: str) -> WalkthroughStop:
    walkthrough = get_walkthrough(db, walkthrough_id)
    stop = next((s for s in walkthrough.stops if s.id == stop_id), None)
    if stop is None:
        raise AppException(status_code=404, message="Stop not found")
    return stop


def delete_stop(db: Session, stop_id: str) -> None:
    """By stop id alone, for the deferred delete; scope comes from the parent."""
    stop = db.query(WalkthroughStop).filter(WalkthroughStop.id == stop_id).first()
    if stop is None:
        raise AppException(status_code=404, message="Stop not found")
    get_walkthrough(db, stop.walkthrough_id)
    stored = _stored(stop)
    db.delete(stop)
    db.commit()
    _purge([stored])


def assert_upload_acceptable(files: list[tuple[str, int]]) -> None:
    """``files`` is ``(filename, byte_size)``. Checked before any byte is staged."""
    if not files:
        raise AppException(status_code=400, message="Add a video or some photos for this stop.")
    if len(files) > MAX_STOP_FILES:
        raise AppException(
            status_code=400,
            message=f"A stop takes at most {MAX_STOP_FILES} photos.",
        )
    for filename, _size in files:
        if not (filename or "").lower().endswith(IMAGE_EXTENSIONS + VIDEO_EXTENSIONS):
            raise AppException(
                status_code=400,
                message=f"{filename or 'That file'} is not a photo (JPG, PNG, WebP) or a video.",
                code="WALKTHROUGH_UNSUPPORTED_FILE",
            )
    assert_within_limit(sum(size for _name, size in files))


def assert_within_limit(total_bytes: int) -> None:
    if total_bytes > MAX_STOP_UPLOAD_BYTES:
        raise AppException(
            status_code=413,
            message=(
                f"A stop's files may total at most {MAX_STOP_UPLOAD_BYTES // (1024 * 1024)} MB. "
                "Trim the video, or use fewer photos."
            ),
            code="WALKTHROUGH_UPLOAD_TOO_LARGE",
        )


def add_stop(
    db: Session,
    walkthrough_id: str,
    *,
    title: Optional[str],
    files: list[tuple[str, bytes]],
) -> WalkthroughStop:
    """Stage the files, write the stop as ``processing``, and queue the build."""
    walkthrough = get_walkthrough(db, walkthrough_id)
    assert_upload_acceptable([(name, len(data)) for name, data in files])

    staged = [_stage(name, data) for name, data in files]
    try:
        next_position = (
            db.query(func.coalesce(func.max(WalkthroughStop.position), 0))
            .filter(WalkthroughStop.walkthrough_id == walkthrough.id)
            .scalar()
            + 1
        )
        stop = WalkthroughStop(
            walkthrough_id=walkthrough.id,
            position=next_position,
            title=(title or "").strip()[:200] or f"Stop {next_position}",
            status=StopStatus.PROCESSING,
        )
        db.add(stop)
        db.commit()
        db.refresh(stop)
    except Exception:
        discard_staged(staged)
        raise

    try:
        stop.job_id = _enqueue(stop, staged)
    except Exception as exc:  # noqa: BLE001 - the queue's problem, said on the row
        logger.exception("Walkthrough stop %s could not be queued", stop.id)
        discard_staged(staged)
        fail_stop(db, stop, message=f"Could not queue the build: {exc}")
        return stop
    db.commit()
    db.refresh(stop)
    return stop


def _enqueue(stop: WalkthroughStop, staged: list[list[str]]) -> Optional[str]:
    """The one seam tests patch to run the build inline."""
    from app.services.queue_service import enqueue_job
    from app.tasks.walkthrough_tasks import build_stop

    job = enqueue_job(
        build_stop,
        str(stop.id),
        staged,
        queue_name=WALKTHROUGH_QUEUE,
        job_timeout=WALKTHROUGH_JOB_TIMEOUT,
    )
    return getattr(job, "id", None)


def complete_stop(db: Session, stop: WalkthroughStop, panorama: Panorama) -> None:
    from app.services import storage_router

    provider = storage_router.default_provider()
    key, _url = storage_router.get_backend(provider).upload_file(
        file_content=panorama.jpeg,
        file_path=f"{PANORAMA_PREFIX}{stop.id}.jpg",
        content_type="image/jpeg",
    )
    stop.storage_provider = provider
    stop.panorama_key = key
    stop.h_fov_deg = panorama.h_fov_deg
    stop.v_fov_deg = panorama.v_fov_deg
    stop.status = StopStatus.DONE
    stop.error_message = None
    stop.finished_at = _now()
    db.commit()


def fail_stop(db: Session, stop: WalkthroughStop, *, message: str) -> None:
    stop.status = StopStatus.FAILED
    stop.error_message = message
    stop.finished_at = _now()
    db.commit()


def panorama_bytes(db: Session, walkthrough_id: str, stop_id: str) -> bytes:
    stop = get_stop(db, walkthrough_id, stop_id)
    if stop.status != StopStatus.DONE or not stop.panorama_key:
        raise AppException(
            status_code=409,
            message="This stop has no panorama yet.",
            code="WALKTHROUGH_STOP_NOT_READY",
        )
    from app.services import storage_router

    return storage_router.get_backend(stop.storage_provider).download_file(stop.panorama_key)


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #
def _stage(filename: str, data: bytes) -> list[str]:
    """Park one upload where the worker can reach it: ``[provider, key, filename]``.

    ``storage_router`` is reached through the module at call time so
    ``tests/_fake_storage.patch_storage`` reaches it too.
    """
    from app.services import storage_router

    provider = storage_router.default_provider()
    extension = os.path.splitext(filename or "")[1].lower()
    try:
        key, _url = storage_router.get_backend(provider).upload_file(
            file_content=data,
            file_path=f"{STAGING_PREFIX}{uuid.uuid4().hex}{extension}",
            content_type="application/octet-stream",
        )
    except Exception as exc:  # noqa: BLE001 - the bucket's problem, said in words
        logger.exception("A walkthrough upload could not be staged")
        raise AppException(
            status_code=502,
            message="Those files could not be stored for processing. Try again in a moment.",
            code="WALKTHROUGH_STAGING_FAILED",
        ) from exc
    return [provider, key, filename]


def discard_staged(staged: list[list[str]]) -> None:
    from app.services import storage_router

    for provider, key, _filename in staged:
        storage_router.delete_object_best_effort(provider or "", key)


def _stored(stop: WalkthroughStop) -> tuple[Optional[str], Optional[str]]:
    return stop.storage_provider, stop.panorama_key


def _purge(objects: list[tuple[Optional[str], Optional[str]]]) -> None:
    from app.services import storage_router

    for provider, key in objects:
        if key:
            storage_router.delete_object_best_effort(provider or "", key)
