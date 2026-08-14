"""External API: the chatbot media endpoint (voice + image), PLAN section 3.

One call per inbound media message, **and n8n waits for it**. The wire is
synchronous; the execution is not, and that distinction is the whole design:

* the fast path - resolve the contact, probe idempotency, gate, cap, pace, meter,
  record, create the job - is ordinary milliseconds-of-SQLAlchemy work and runs
  inline, then **commits before any waiting begins**, so the ledger row and the
  decision are durable even if the wait or the worker later dies;
* the multi-second extraction runs in the RQ work-horse. The handler enqueues and
  then awaits the job row through `asyncio.to_thread`, so a hundred concurrent
  media turns cost sleeping coroutines rather than blocked workers.

That second point is the point. The known live defect on the portal extract route
(`app/api/v1/public/ai_extract.py`) calls a synchronous multi-second function from
inside an `async def` handler and freezes the whole backend for the duration. It
is filed separately, it is not fixed here, and it is deliberately not copied -
`tests/test_media_job_lifecycle.py` guards this module against regrowing it, both
statically and by racing a second request against one in flight.

Past `media_sync_wait_seconds` the endpoint stops waiting and returns
`status: pending` with the `job_id`. The job keeps running and the result stays
retrievable through `GET /jobs/{job_id}` and through the callback, so a slow
provider bounds the dispatcher's lock instead of blowing through it. True async is
therefore a configuration switch, not a rebuild.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_external_api_user
from app.models.media import MediaExtractionJob
from app.schemas.external.media import MediaProcessRequest, MediaProcessResponse
from app.services.error_handler import handle_not_found
from app.services.media_access_service import (
    MediaRequest,
    _now_utc,
    decide_and_record,
    resolve_media_settings,
)
from app.services.queue_service import enqueue_job
from app.tasks.media_tasks import (
    MEDIA_QUEUE,
    build_callback_body,
    process_media_extraction,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# How often the awaiting coroutine looks at the job row. Short enough that a
# fast extraction is not padded by the poll interval, long enough that a 30
# second wait is 120 cheap reads rather than a spin.
_POLL_INTERVAL_SECONDS = 0.25

TERMINAL_STATUSES = ("completed", "failed")


def _read_job_snapshot(job_id: str) -> Optional[dict[str, Any]]:
    """Read the job row through a short-lived session of its own.

    Never the request's session: that one is bound to a transaction which, by the
    time we are waiting, has already committed the decision, and re-reading a row
    another process is writing through it would only see this transaction's
    snapshot.
    """
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        job = (
            db.query(MediaExtractionJob)
            .filter(MediaExtractionJob.id == job_id)
            .first()
        )
        if job is None:
            return None
        return {"status": job.status, "result": job.result, "error": job.error}
    finally:
        db.close()


async def _await_job(job_id: str) -> Optional[dict[str, Any]]:
    """Wait for the worker without occupying the event loop.

    Each poll is a short database read moved off the loop with
    `asyncio.to_thread`, and the gap between polls is an `await`. Nothing here
    blocks; the caller bounds the whole thing with `asyncio.wait_for`.
    """
    while True:
        snapshot = await asyncio.to_thread(_read_job_snapshot, job_id)
        if snapshot is not None and snapshot["status"] in TERMINAL_STATUSES:
            return snapshot
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)


@router.post(
    "/process", response_model=MediaProcessResponse, status_code=status.HTTP_200_OK
)
async def process_media(
    payload: MediaProcessRequest,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """Decide, meter, record - then await the worker's result on the same call."""
    _ = current_user

    settings = resolve_media_settings(db)
    decision = decide_and_record(
        db,
        MediaRequest(
            respond_io_id=payload.respond_io_id,
            message_id=payload.message_id,
            modality=payload.modality,
            media_ordinal=payload.media_ordinal,
            media_url=payload.media_url,
            mime_type=payload.mime_type,
            caption=payload.caption,
            duration_ms=payload.duration_ms,
            bytes=payload.bytes,
            turn_id=payload.turn_id,
            callback_url=payload.callback_url,
            callback_headers=payload.callback_headers,
            context=payload.context,
        ),
        settings=settings,
        now=_now_utc(),
    )
    # Everything above is durable from here on, including every refusal.
    db.commit()

    if not decision.accepted or decision.job is None:
        return MediaProcessResponse(
            job_id=None,
            decision=decision.decision,
            status=None,
            idempotent_replay=decision.idempotent_replay,
            tier=decision.tier,
            quota=decision.quota,
            notices=decision.notices,
            language_strategy=decision.language_strategy,
            result=None,
        )

    job_id = str(decision.job.id)
    job_status = str(decision.job.status)
    job_result = decision.job.result
    job_error = decision.job.error

    if not decision.idempotent_replay:
        job_status, job_error = _enqueue(db, decision.job, job_id)

    # Snapshot everything the response still needs BEFORE the wait, so nothing
    # below reads an ORM attribute afterwards. The commit above already released
    # this session's pooled connection; touching an expired ORM attribute during
    # or after a wait of up to `media_sync_wait_seconds` would check one back out
    # and hold it for the rest of the call, which at any real concurrency
    # exhausts the pool and stalls unrelated requests. `_await_job` reads through
    # its own short-lived sessions for the same reason.
    quota = dict(decision.quota)
    notices = [dict(notice) for notice in decision.notices]
    tier = decision.tier
    decision_name = decision.decision
    replay = decision.idempotent_replay
    language_strategy = decision.language_strategy

    if job_status not in TERMINAL_STATUSES:
        snapshot = await _wait_for_worker(job_id, settings.sync_wait_seconds)
    else:
        snapshot = {"status": job_status, "result": job_result, "error": job_error}

    return MediaProcessResponse(
        job_id=job_id,
        decision=decision_name,
        status=(snapshot or {}).get("status") or "pending",
        idempotent_replay=replay,
        tier=tier,
        quota=quota,
        notices=notices,
        language_strategy=language_strategy,
        result=(snapshot or {}).get("result"),
        error=(snapshot or {}).get("error"),
    )


def _enqueue(
    db: Session, job: MediaExtractionJob, job_id: str
) -> tuple[str, Optional[str]]:
    """Hand the job to the worker, returning its (status, error).

    The row is already committed, so the worker cannot pick up an id that is not
    there yet. Follows the `attachments.py` precedent: the DB row first, then
    enqueue with the RQ id pre-assigned to the DB id, then store it back.
    """
    try:
        rq_job = enqueue_job(
            process_media_extraction,
            job_id,
            queue_name=MEDIA_QUEUE,
            job_timeout=600,
            job_id=job_id,  # pre-assign the RQ id = the DB job id
        )
    except Exception:  # noqa: BLE001 - a queue outage is a failed job, not a 500
        logger.exception("failed to enqueue media extraction job %s", job_id)
        error = "Could not queue the extraction."
        job.status = "failed"
        job.error = error
        db.commit()
        return "failed", error
    job.rq_job_id = getattr(rq_job, "id", None)
    db.commit()
    return str(job.status), job.error


async def _wait_for_worker(
    job_id: str, sync_wait_seconds: float
) -> Optional[dict[str, Any]]:
    """Await the worker, bounded. A timeout is `pending`, never an error."""
    try:
        return await asyncio.wait_for(_await_job(job_id), timeout=sync_wait_seconds)
    except (asyncio.TimeoutError, TimeoutError):
        logger.info(
            "media job %s outlived the %ss synchronous wait; returning pending",
            job_id,
            sync_wait_seconds,
        )
        return None


@router.get("/jobs/{job_id}", status_code=status.HTTP_200_OK)
def get_media_job(
    job_id: str,
    current_user: dict = Depends(get_external_api_user),
    db: Session = Depends(get_db),
):
    """The polling fallback. Safe to poll, no side effects, idempotent.

    Returns the identical body the callback carries, so a consumer written
    against one works unchanged against the other (UAC S3-02b). Declared `def`
    rather than `async def` on purpose: Starlette runs it in the threadpool, so
    its short synchronous database read never touches the event loop that the
    awaiting `/process` calls are sharing.
    """
    _ = current_user

    job = (
        db.query(MediaExtractionJob).filter(MediaExtractionJob.id == job_id).first()
    )
    if job is None:
        raise handle_not_found("Media extraction job", job_id)
    return build_callback_body(db, job)
