"""RQ task: run one chatbot-media extraction and deliver its result.

See `documentation/plans/ideation/PLAN-chatbot-media-endpoint.md` sections 3.3b
and 3.5.

This is where the multi-second provider work happens - in the RQ work-horse
process, never inside the API's `async def` handler. The route enqueues, then
awaits the job row without holding the event loop. That is deliberately the
opposite of the live portal defect at `app/api/v1/public/ai_extract.py:116`,
which calls a synchronous multi-second `extract` from inside an async route and
freezes the backend for the duration. That defect is out of scope and is not to
be reproduced here.

``run_media_extraction`` is the pluggable seam S4 (image) and S5 (voice) fill in.
Everything around it - the lifecycle, the bounded timeout, the ledger update, the
callback and its bounded retries - is real now, so the async spine is proven
before the expensive part is attached.

Editing this file requires a Worker restart: the RQ worker has NO reload.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import update

from app.database import SessionLocal
from app.models.media import ContactMediaUsage, MediaExtractionJob
from app.services.media_access_service import (
    mark_usage_outcome,
    resolve_media_settings,
)

logger = logging.getLogger(__name__)

# The queue this task runs on. Must also appear in `worker.py`'s queue list or
# jobs enqueue and are never drained.
MEDIA_QUEUE = "media"

# Bounded callback retries. Small on purpose: the polling endpoint is the
# durable fallback, so a callback that will not land is a logged nuisance, not a
# reason to keep hammering a dead webhook.
CALLBACK_MAX_ATTEMPTS = 3
CALLBACK_BACKOFF_SECONDS = (0.25, 0.5)

TERMINAL_STATUSES = ("completed", "failed")


class MediaExtractionTimeout(Exception):
    """The extraction outlived `media_extraction_timeout_seconds`."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def run_media_extraction(job: MediaExtractionJob) -> dict:
    """Produce the result body for one job.

    The seam S3 left open, now filled by S4 (image) and S5 (voice). **The only
    dispatch is `job.modality`** - `MediaExtractService` sends `image` to the
    vision call and `voice` to the transcription call. The document-versus-label
    split inside the image lane is not a second dispatch: the model classifies
    and extracts in the same pass, because a second round trip would double both
    the cost and the latency that now sits inside n8n's lock budget.

    The SHAPE returned is unchanged from the S3 stub (PLAN 3.5), which is the
    point of having built the spine first.

    Runs on a worker thread with a bounded join, so it must not lazy-load off the
    ORM session - every attribute it reads is refreshed before the thread starts,
    and `MediaJobInput.from_job` snapshots them into a plain dataclass before any
    provider work begins. The extraction then uses a session of its own.
    """
    from app.services.media_extract.service import run_extraction

    return run_extraction(job)


def _run_bounded(job: MediaExtractionJob, timeout_seconds: float) -> dict:
    """Run the extraction with the worker's own hard ceiling (UAC S3-06).

    A plain daemon thread with a bounded `join` rather than a ThreadPoolExecutor:
    a hung provider call cannot be killed either way, but a daemon thread does not
    make the interpreter wait for it at exit, so one stuck job cannot hold the
    worker process open.
    """
    box: dict[str, Any] = {}

    def _work() -> None:
        try:
            box["result"] = run_media_extraction(job)
        except BaseException as exc:  # noqa: BLE001 - re-raised on the caller's thread
            box["error"] = exc

    thread = threading.Thread(
        target=_work, name=f"media-extract-{job.id}", daemon=True
    )
    thread.start()
    thread.join(timeout_seconds)
    if thread.is_alive():
        raise MediaExtractionTimeout(
            f"Extraction timed out after {timeout_seconds:g}s"
        )
    if "error" in box:
        raise box["error"]
    return box.get("result") or {}


def process_media_extraction(job_id: str) -> None:
    """The RQ entrypoint. Owns its own session, and never raises.

    The row is claimed with a compare-and-set (`queued` -> `running`), so a
    second copy of the same job id - an RQ retry, or a stranded-job re-enqueue
    racing the original on a second worker - finds nothing to claim and does
    nothing: it must not re-spend the extraction or re-notify the far end, which
    is the same guarantee the route's idempotency probe gives from the other
    side of the queue.
    """
    db = SessionLocal()
    try:
        claimed = db.execute(
            update(MediaExtractionJob)
            .where(
                MediaExtractionJob.id == job_id,
                MediaExtractionJob.status == "queued",
            )
            .values(status="running", started_at=_utcnow())
        ).rowcount
        db.commit()
        job = (
            db.query(MediaExtractionJob)
            .filter(MediaExtractionJob.id == job_id)
            .first()
        )
        if job is None:
            logger.warning("media extraction job %s not found", job_id)
            return
        if claimed != 1:
            logger.info(
                "media extraction job %s already %s; nothing to do", job_id, job.status
            )
            return

        settings = resolve_media_settings(db)
        # Load every column now, on this thread: the extraction runs on another
        # one and must never trigger a lazy refresh against a session it does not
        # own (the failure surfaces far from the cause, as a closed cursor).
        db.refresh(job)

        try:
            result = _run_bounded(job, settings.extraction_timeout_seconds)
            terminal_status = "completed"
            terminal_result: Optional[dict] = result
            terminal_error: Optional[str] = None
        except Exception as exc:  # noqa: BLE001 - every failure is a failed job
            logger.exception("media extraction job %s failed", job_id)
            terminal_status = "failed"
            terminal_result = None
            terminal_error = str(exc) or exc.__class__.__name__
            _mark_usage_failed(db, job, exc)
        # The terminal write is a compare-and-set just like the claim: a job the
        # replay path already reclaimed as failed (its ledger row is stamped)
        # must not flip back to completed and report success for an item metered
        # as failed.
        finalized = db.execute(
            update(MediaExtractionJob)
            .where(
                MediaExtractionJob.id == job_id,
                MediaExtractionJob.status == "running",
            )
            .values(
                status=terminal_status,
                result=terminal_result,
                error=terminal_error,
                completed_at=_utcnow(),
            )
        ).rowcount
        db.commit()
        if finalized != 1:
            logger.info(
                "media extraction job %s was reclaimed while running; "
                "leaving its terminal state alone",
                job_id,
            )
            return
        db.refresh(job)

        # Post-commit side effect: best-effort by construction. A callback that
        # cannot be delivered must never turn a job that actually succeeded into
        # a raised exception - the result stays readable through the polling
        # endpoint either way.
        try:
            deliver_callback(job)
            db.commit()
        except Exception:  # noqa: BLE001
            logger.exception(
                "media extraction job %s: callback delivery raised", job_id
            )
            db.rollback()
    except Exception:  # noqa: BLE001 - an RQ task must not explode the worker
        logger.exception("media extraction task %s failed unexpectedly", job_id)
        db.rollback()
        _fail_job_last_resort(job_id)
    finally:
        db.close()


def _fail_job_last_resort(job_id: str) -> None:
    """Terminal backstop for a crash between the claim commit and the result
    commit (settings resolution, the refresh, the ledger stamp, the commit
    itself). Without it the job sits at `running` durably: the polling consumer
    sees `running` forever and no callback fires, because the replay-path
    reclaim only runs on another POST /process. A fresh session because the
    crashed one may be unusable; the compare-and-set leaves alone anything
    another path already finished or reclaimed.
    """
    session = SessionLocal()
    try:
        job = (
            session.query(MediaExtractionJob)
            .filter(MediaExtractionJob.id == job_id)
            .first()
        )
        failed = session.execute(
            update(MediaExtractionJob)
            .where(
                MediaExtractionJob.id == job_id,
                MediaExtractionJob.status == "running",
            )
            .values(
                status="failed",
                result=None,
                error="The extraction task failed before it could record a result.",
                completed_at=_utcnow(),
            )
        ).rowcount
        if failed == 1 and job is not None:
            mark_usage_outcome(session, job.usage_id, "failed")
        session.commit()
    except Exception:  # noqa: BLE001 - the backstop must not raise either
        logger.exception(
            "media extraction job %s: last-resort failed write did not land", job_id
        )
        session.rollback()
    finally:
        session.close()


def _mark_usage_failed(db, job: MediaExtractionJob, exc: BaseException) -> None:
    """Flip the ledger outcome to `failed`. Still consumes quota, deliberately:
    the provider was called and the money was spent.

    Except for a clip refused on its measured length, which is raised BEFORE the
    transcription call - nothing was spent, so it records `refused_duration` and
    the contact keeps the allowance, exactly as the fast path does when the
    stated duration is over the cap. It carries the customer notice onto the
    ledger row too, because that is what the callback and the polling endpoint
    hand back.

    Both outcomes go through `mark_usage_outcome`, which stays the only writer
    of `outcome` after the insert, so the "re-stamp an accepted row only" rule
    holds for the refusal exactly as it does for the failure.
    """
    from app.services.media_extract.service import MediaClipLengthError

    if isinstance(exc, MediaClipLengthError):
        mark_usage_outcome(
            db, job.usage_id, "refused_duration", notices=[exc.notice]
        )
        return
    mark_usage_outcome(db, job.usage_id, "failed")


def build_callback_body(db, job: MediaExtractionJob) -> dict:
    """The one result shape, carried by all three transports (UAC S3-02b).

    The turn context is echoed back verbatim so the far end can rebuild the turn
    without re-reading anything.

    `notices` comes off the ledger row the fast path wrote, not a hardcoded empty
    list: a consumer reading the callback or the polling endpoint must get the
    same customer text the synchronous response carried, or the guarantee is only
    true because nothing populated the field.
    """
    usage = (
        db.query(ContactMediaUsage)
        .filter(ContactMediaUsage.id == job.usage_id)
        .first()
    )
    return {
        "job_id": job.id,
        "status": job.status,
        "respond_io_id": usage.respond_io_id if usage else None,
        "message_id": usage.message_id if usage else None,
        "modality": job.modality,
        "turn_id": usage.turn_id if usage else None,
        "context": job.context,
        "tier": job.tier,
        "result": job.result,
        "notices": list(usage.notices or []) if usage else [],
        "error": job.error,
    }


def deliver_callback(job: MediaExtractionJob) -> None:
    """POST the result to n8n's opaque callback target, if it supplied one.

    The CRM makes no assumption about what consumes it: a Wait-node resume URL, a
    plain webhook that re-enqueues the turn, or nothing at all. Omitting
    `callback_url` is valid and disables delivery.
    """
    if not job.callback_url:
        return
    from sqlalchemy.orm import object_session

    db = object_session(job)
    body = build_callback_body(db, job)
    headers = job.callback_headers or {}

    last_error: Optional[Exception] = None
    for attempt in range(1, CALLBACK_MAX_ATTEMPTS + 1):
        job.callback_attempts = attempt
        try:
            _post_callback(job.callback_url, headers, body)
            job.callback_status = "delivered"
            return
        except Exception as exc:  # noqa: BLE001 - bounded retry, then give up
            last_error = exc
            logger.warning(
                "media callback attempt %s/%s for job %s failed: %s",
                attempt,
                CALLBACK_MAX_ATTEMPTS,
                job.id,
                exc,
            )
            if attempt <= len(CALLBACK_BACKOFF_SECONDS):
                time.sleep(CALLBACK_BACKOFF_SECONDS[attempt - 1])

    job.callback_status = "failed"
    logger.error(
        "media callback for job %s gave up after %s attempts: %s",
        job.id,
        CALLBACK_MAX_ATTEMPTS,
        last_error,
    )


def _post_callback(url: str, headers: dict, body: dict) -> None:
    """The single HTTP seam, so every test above can capture it without a network."""
    import httpx

    response = httpx.post(url, json=body, headers=headers, timeout=15.0)
    response.raise_for_status()
