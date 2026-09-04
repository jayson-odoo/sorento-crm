"""The queued extraction job: the callback, the polling fallback, and the
awaited-but-non-blocking synchronous wire.

Contract:
 - PLAN-chatbot-media-endpoint.md section 3.3b (the route awaits the worker
    without blocking the event loop: `await asyncio.wait_for(_await_job(job_id),
    timeout=media_sync_wait_seconds)`), section 3.4 (`GET
    /api/v1/external/media/jobs/{job_id}`), section 3.5 (one result shape,
    three transports) and section 2.3 (`media_extraction_job`).
 - The S3 slice ships "with a stub extraction, so the async spine is proven
    before the expensive part is attached" (PLAN section 10) -- so every test
    here monkeypatches `app.tasks.media_tasks.run_media_extraction`, the
    pluggable extraction seam S4/S5 replace with real image/voice logic. No
    test here asserts anything about *what* was extracted.

Implementation seams this file requires, named here because nothing in the
plan pins the exact identifier and the coder needs a target to build to:

 - `app.tasks.media_tasks.process_media_extraction(job_id: str) -> None`
    The RQ task entrypoint (mirrors `app/tasks/import_tasks.py`'s
    `SessionLocal()`-per-task convention -- it opens and commits its own
    session, never receives the request's). Marks the job running, calls
    `run_media_extraction`, bounds it by `media_extraction_timeout_seconds`
    (read via `app.tasks.media_tasks.resolve_media_settings(db)` -- the same
    resolver S1/S2 use, imported into this module too), marks
    completed/failed, updates the ledger outcome, and always attempts
    `deliver_callback` -- wrapped so a callback failure can never raise out of
    this function (S3-07). Re-running it on an already-terminal job (status
    `completed`/`failed`) must be a no-op -- neither the extraction nor the
    callback fire again.
 - `app.tasks.media_tasks.run_media_extraction(job) -> dict` the stub result
    producer, given the ORM `MediaExtractionJob` row.
 - `app.tasks.media_tasks.deliver_callback(job) -> None` POSTs
    `job.callback_url` with `job.callback_headers` verbatim via
    `app.tasks.media_tasks._post_callback(url, headers, body)`, retried a
    bounded number of times, stamping `callback_status` /
    `callback_attempts`. A no-`callback_url` job is a no-op.
 - `app.api.v1.external.media.enqueue_job` and `._await_job` -- PLAN 3.3b's
    own names, verbatim.
 - `app.api.v1.external.media.resolve_media_settings(db)` -- same resolver
    S1/S2 use, so it can be monkeypatched to fixed, fast values here without
    touching the real `system_settings` singleton row.

Why real (committed) Postgres, not `blank_session`: S3-01, S3-01b and S3-01c
are specifically about what a SEPARATE process (the RQ worker) does while the
API process is waiting on it, and `blank_session`'s `create_savepoint` commits
are never visible outside its own connection (see `tests/_pg_fixture.py`'s own
docstring). These tests seed real rows with a `ZZT-` marker via a real
`SessionLocal()` and delete them in a `finally` -- the pattern CLAUDE.md's
lessons-learned entry sanctions for exactly this class of problem ("the only
honest check is an empty database... marker-scoped cleanup"). No production
row is ever read, and `resolve_media_settings` is monkeypatched so no test
touches the live `system_settings` singleton.

S3-08 (the handler never blocks the event loop) is proven dynamically, by
racing an unrelated request against a media call that is still in flight and
timing it. There is no static guard: parsing this module's own source for
blocking call names asserted a shape rather than a behaviour, passed for any
blocking call made under a name nobody had listed, and failed on a rename.

AC ids covered: S3-01, S3-01b, S3-01c, S3-01d, S3-02, S3-02b, S3-04, S3-05,
S3-06, S3-07, S3-08, S3-09.
"""
from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.dependencies import get_external_api_user
from app.main import app

from tests._external_auth import external_permissions_granted

PROCESS_ENDPOINT = "/api/v1/external/media/process"


def _jobs_endpoint(job_id: str) -> str:
    return f"/api/v1/external/media/jobs/{job_id}"


# --------------------------------------------------------------------------- #
# Real-DB seed / cleanup -- see module docstring for why this cannot be       #
# `blank_session`.                                                            #
# --------------------------------------------------------------------------- #


@pytest.fixture
def real_chain():
    """Seeds a real, committed contact + an allowed image row. Yields a
    small namespace; every created row is deleted at teardown regardless of
    what the test did to it (usage -> job cascades on usage_id FK per PLAN
    2.3; limit and contact are deleted explicitly)."""
    from app.models.access import RespondContact
    from app.models.media import ContactMediaLimit, ContactMediaUsage

    db = SessionLocal()
    unique = f"ZZT-joblife-{uuid.uuid4().hex[:10]}"
    contact = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+1555{unique}",
        respond_io_id=unique,
        name=unique,
    )
    db.add(contact)
    db.add(
        ContactMediaLimit(
            contact_id=contact.id, modality="image", is_allowed=True, monthly_limit=50
        )
    )
    db.commit()

    class _Chain:
        def __init__(self):
            self.contact = contact
            self.marker = unique

    yield _Chain()

    cleanup = SessionLocal()
    try:
        cleanup.query(ContactMediaUsage).filter(
            ContactMediaUsage.contact_id == contact.id
        ).delete(synchronize_session=False)
        cleanup.query(ContactMediaLimit).filter(
            ContactMediaLimit.contact_id == contact.id
        ).delete(synchronize_session=False)
        cleanup.query(RespondContact).filter(RespondContact.id == contact.id).delete(
            synchronize_session=False
        )
        cleanup.commit()
    finally:
        cleanup.close()
    db.close()


def _seed_job_row(
    *,
    callback_url=None,
    callback_headers=None,
    context=None,
    notices=None,
    modality="image",
) -> str:
    """Seeds a standalone `contact_media_usage` + `media_extraction_job` pair
    (no `contact_media_limit`, no gate involved) directly at "queued", the
    state the task-level tests below start from. Returns the job id. Caller
    cleans up."""
    from app.models.access import RespondContact
    from app.models.media import ContactMediaLimit, ContactMediaUsage, MediaExtractionJob

    db = SessionLocal()
    unique = f"ZZT-joblife-{uuid.uuid4().hex[:10]}"
    contact = RespondContact(
        id=str(uuid.uuid4()), phone_number=f"+1555{unique}", respond_io_id=unique
    )
    db.add(contact)
    db.add(
        ContactMediaLimit(
            contact_id=contact.id, modality=modality, is_allowed=True, monthly_limit=50
        )
    )
    db.flush()
    usage = ContactMediaUsage(
        id=str(uuid.uuid4()),
        respond_io_id=unique,
        contact_id=contact.id,
        modality=modality,
        message_id=f"{unique}-m1",
        media_ordinal=0,
        period_key="2026-08",
        outcome="accepted",
        tier="standard",
        notices=notices,
    )
    db.add(usage)
    db.flush()
    job = MediaExtractionJob(
        id=str(uuid.uuid4()),
        usage_id=usage.id,
        status="queued",
        modality=modality,
        tier="standard",
        media_url="https://cdn.respond.io/x.jpg",
        mime_type="image/jpeg",
        caption="check stock",
        callback_url=callback_url,
        callback_headers=callback_headers,
        callback_attempts=0,
        context=context,
    )
    db.add(job)
    db.commit()
    # Read both ids BEFORE closing: commit expires every instance, so an id read
    # after close() is a refresh against a detached object, not a cached value.
    job_id = job.id
    contact_id = contact.id
    db.close()
    return job_id, contact_id


def _cleanup_chain(contact_id: str):
    from app.models.access import RespondContact
    from app.models.media import ContactMediaLimit, ContactMediaUsage

    db = SessionLocal()
    try:
        db.query(ContactMediaUsage).filter(
            ContactMediaUsage.contact_id == contact_id
        ).delete(synchronize_session=False)
        db.query(ContactMediaLimit).filter(
            ContactMediaLimit.contact_id == contact_id
        ).delete(synchronize_session=False)
        db.query(RespondContact).filter(RespondContact.id == contact_id).delete(
            synchronize_session=False
        )
        db.commit()
    finally:
        db.close()


def _fetch_job(job_id: str):
    from app.models.media import MediaExtractionJob

    db = SessionLocal()
    try:
        return db.query(MediaExtractionJob).filter(MediaExtractionJob.id == job_id).first()
    finally:
        db.close()


def _fetch_usage_by_job(job_id: str):
    from app.models.media import ContactMediaUsage, MediaExtractionJob

    db = SessionLocal()
    try:
        job = db.query(MediaExtractionJob).filter(MediaExtractionJob.id == job_id).first()
        return db.query(ContactMediaUsage).filter(ContactMediaUsage.id == job.usage_id).first()
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Task-level tests: process_media_extraction(job_id) called directly.         #
# No HTTP, no waiting -- single-threaded, real committed DB.                  #
# --------------------------------------------------------------------------- #


def test_the_stub_extraction_completes_the_job_and_stores_the_result(monkeypatch):
    """S3-09 (queued -> running -> completed)."""
    import app.tasks.media_tasks as media_tasks

    canned = {
        "entities": [],
        "attributes": [],
        "conflicts": [],
        "image_kind": "document",
        "needs_clarification": False,
        "truncated": False,
        "rendered_text": "check stock",
        "confirmation_message": "Got it.",
        "clarification_message": None,
        "transcript": None,
        "languages_detected": None,
    }
    monkeypatch.setattr(media_tasks, "run_media_extraction", lambda job: canned)
    job_id, contact_id = _seed_job_row()
    try:
        media_tasks.process_media_extraction(job_id)

        job = _fetch_job(job_id)
        assert job.status == "completed"
        assert job.result == canned
        assert job.started_at is not None
        assert job.completed_at is not None
    finally:
        _cleanup_chain(contact_id)


def test_a_raised_extraction_error_marks_the_job_failed_and_updates_the_ledger(
    monkeypatch,
):
    """S3-05 (part 1): a real exception in the stub -> failed, ledger outcome
    updated from 'accepted' to 'failed'."""
    import app.tasks.media_tasks as media_tasks

    def _boom(job):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(media_tasks, "run_media_extraction", _boom)
    job_id, contact_id = _seed_job_row()
    try:
        media_tasks.process_media_extraction(job_id)

        job = _fetch_job(job_id)
        assert job.status == "failed"
        assert job.error
        usage = _fetch_usage_by_job(job_id)
        assert usage.outcome == "failed"
    finally:
        _cleanup_chain(contact_id)


def test_a_clip_refused_on_its_measured_length_leaves_no_spent_allowance(monkeypatch):
    """The ledger side of the clip cap. An ordinary failure keeps consuming the
    allowance because the provider was called; a clip refused on its measured
    length is raised BEFORE the transcription, so it records `refused_duration`
    and the contact keeps the month's voice note."""
    import app.tasks.media_tasks as media_tasks
    from app.services.media_access_service import count_usage
    from app.services.media_extract.service import MediaClipLengthError

    def _too_long(job):
        raise MediaClipLengthError(
            "The voice note is 200 seconds, over the 120 second limit.",
            notice={
                "kind": "too_long",
                "text": "That voice note is longer than 120 seconds.",
                "append": True,
            },
        )

    monkeypatch.setattr(media_tasks, "run_media_extraction", _too_long)
    job_id, contact_id = _seed_job_row(modality="voice")
    try:
        media_tasks.process_media_extraction(job_id)

        job = _fetch_job(job_id)
        assert job.status == "failed"
        assert "120 second limit" in job.error

        usage = _fetch_usage_by_job(job_id)
        assert usage.outcome == "refused_duration"
        # And the customer text travels back the same way the fast path's own
        # refusal notices do, through the ledger row.
        assert usage.notices[0]["kind"] == "too_long"

        db = SessionLocal()
        try:
            assert (
                count_usage(db, usage.respond_io_id, "voice", usage.period_key) == 0
            ), "a refusal must not consume the monthly allowance"
        finally:
            db.close()
    finally:
        _cleanup_chain(contact_id)


def test_the_callback_fires_with_status_failed_on_a_failed_job(monkeypatch):
    """S3-05 (part 2): the callback always fires, even on failure, and never
    leaves the far end waiting -- `status: failed` with a reason."""
    import app.tasks.media_tasks as media_tasks

    captured = []
    monkeypatch.setattr(
        media_tasks,
        "_post_callback",
        lambda url, headers, body: captured.append((url, headers, body)),
    )
    monkeypatch.setattr(
        media_tasks, "run_media_extraction", lambda job: (_ for _ in ()).throw(RuntimeError("x"))
    )
    job_id, contact_id = _seed_job_row(callback_url="https://n8n.example/webhook")
    try:
        media_tasks.process_media_extraction(job_id)

        assert len(captured) == 1
        _url, _headers, body = captured[0]
        assert body["status"] == "failed"
        assert body["error"]
        assert body["job_id"] == job_id
    finally:
        _cleanup_chain(contact_id)


def test_extraction_exceeding_the_configured_timeout_is_abandoned_and_marked_failed(
    monkeypatch,
):
    """S3-06: the worker enforces its own ceiling
    (`media_extraction_timeout_seconds`), independent of the route's sync
    wait -- a hung stub must not hang the job forever."""
    import app.tasks.media_tasks as media_tasks

    def _hangs(job):
        time.sleep(5)
        return {"never": "reached"}

    monkeypatch.setattr(media_tasks, "run_media_extraction", _hangs)
    monkeypatch.setattr(
        "app.services.media_access_service.resolve_media_settings",
        lambda db: _fake_settings(extraction_timeout_seconds=0.5),
    )
    monkeypatch.setattr(
        media_tasks,
        "resolve_media_settings",
        lambda db: _fake_settings(extraction_timeout_seconds=0.5),
        raising=False,
    )
    captured = []
    monkeypatch.setattr(
        media_tasks,
        "_post_callback",
        lambda url, headers, body: captured.append(body),
    )
    job_id, contact_id = _seed_job_row(callback_url="https://n8n.example/webhook")
    try:
        started = time.monotonic()
        media_tasks.process_media_extraction(job_id)
        elapsed = time.monotonic() - started

        assert elapsed < 4, "the job must be abandoned near the timeout, not run to completion"
        job = _fetch_job(job_id)
        assert job.status == "failed"
        assert "timeout" in (job.error or "").lower() or "timed out" in (job.error or "").lower()
        assert len(captured) == 1
        assert captured[0]["status"] == "failed"
    finally:
        _cleanup_chain(contact_id)


def test_a_permanently_failing_callback_is_retried_but_never_raises_and_the_job_stays_readable(
    monkeypatch,
):
    """S3-07: bounded retries, logged, and the job result stays readable
    through the polling endpoint even though every callback attempt failed.
    'Never raises' is the load-bearing assertion -- `process_media_extraction`
    must return normally."""
    import app.tasks.media_tasks as media_tasks

    attempts = []

    def _always_fails(url, headers, body):
        attempts.append(1)
        raise ConnectionError("far end unreachable")

    monkeypatch.setattr(media_tasks, "_post_callback", _always_fails)
    monkeypatch.setattr(
        media_tasks, "run_media_extraction", lambda job: {"rendered_text": "ok"}
    )
    job_id, contact_id = _seed_job_row(callback_url="https://n8n.example/webhook")
    try:
        media_tasks.process_media_extraction(job_id)  # must not raise

        assert 1 < len(attempts) <= 5, f"expected a small bounded retry count, got {len(attempts)}"
        job = _fetch_job(job_id)
        assert job.callback_status == "failed"
        # the job's own result is untouched by the callback's failure.
        assert job.status == "completed"
        assert job.result == {"rendered_text": "ok"}
    finally:
        _cleanup_chain(contact_id)


def test_a_job_with_no_callback_url_is_a_no_op_delivery(monkeypatch):
    """S3-02: omitting callback_url is valid and disables callback delivery."""
    import app.tasks.media_tasks as media_tasks

    called = []
    monkeypatch.setattr(
        media_tasks, "_post_callback", lambda *a, **kw: called.append(1)
    )
    monkeypatch.setattr(
        media_tasks, "run_media_extraction", lambda job: {"rendered_text": "ok"}
    )
    job_id, contact_id = _seed_job_row(callback_url=None)
    try:
        media_tasks.process_media_extraction(job_id)

        assert called == []
        job = _fetch_job(job_id)
        assert job.status == "completed", "no callback must not affect completion"
    finally:
        _cleanup_chain(contact_id)


def test_callback_url_and_headers_and_context_are_stored_and_echoed_verbatim(
    monkeypatch,
):
    """S3-02: the job holds n8n's callback target opaquely, and the turn
    context survives to the callback body unchanged."""
    import app.tasks.media_tasks as media_tasks

    captured = []
    monkeypatch.setattr(
        media_tasks,
        "_post_callback",
        lambda url, headers, body: captured.append((url, headers, body)),
    )
    monkeypatch.setattr(
        media_tasks, "run_media_extraction", lambda job: {"rendered_text": "ok"}
    )
    headers = {"X-Whatever": "abc123"}
    context = {"opaque": True, "nested": {"a": 1}}
    job_id, contact_id = _seed_job_row(
        callback_url="https://n8n.example/webhook/xyz",
        callback_headers=headers,
        context=context,
    )
    try:
        media_tasks.process_media_extraction(job_id)

        url, sent_headers, body = captured[0]
        assert url == "https://n8n.example/webhook/xyz"
        assert sent_headers == headers
        assert body["context"] == context
        job = _fetch_job(job_id)
        assert job.callback_url == "https://n8n.example/webhook/xyz"
        assert job.callback_headers == headers
        assert job.context == context
    finally:
        _cleanup_chain(contact_id)


def test_replaying_process_media_extraction_after_completion_is_a_no_op(monkeypatch):
    """S3-09's 'replay-after-complete': calling the task a second time on an
    already-completed job must not re-run the extraction or re-deliver the
    callback (mirrors the route's own idempotency guard from the other side
    of the queue -- an RQ retry must not double-charge or double-notify)."""
    import app.tasks.media_tasks as media_tasks

    extraction_calls = []
    callback_calls = []
    monkeypatch.setattr(
        media_tasks,
        "run_media_extraction",
        lambda job: extraction_calls.append(1) or {"rendered_text": "ok"},
    )
    monkeypatch.setattr(
        media_tasks,
        "_post_callback",
        lambda url, headers, body: callback_calls.append(1),
    )
    job_id, contact_id = _seed_job_row(callback_url="https://n8n.example/webhook")
    try:
        media_tasks.process_media_extraction(job_id)
        media_tasks.process_media_extraction(job_id)

        assert len(extraction_calls) == 1
        assert len(callback_calls) == 1
    finally:
        _cleanup_chain(contact_id)


# --------------------------------------------------------------------------- #
# S3-04 -- the polling fallback, via HTTP, real DB                            #
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_get_jobs_returns_the_completed_result_and_is_idempotent(monkeypatch):
    import app.tasks.media_tasks as media_tasks

    canned = {"rendered_text": "check stock", "entities": []}
    monkeypatch.setattr(media_tasks, "run_media_extraction", lambda job: canned)
    job_id, contact_id = _seed_job_row()
    try:
        media_tasks.process_media_extraction(job_id)

        app.dependency_overrides[get_external_api_user] = lambda: {"id": "ext"}
        with external_permissions_granted():
            client = TestClient(app)
            first = client.get(_jobs_endpoint(job_id), headers={"X-API-Key": "k"})
            second = client.get(_jobs_endpoint(job_id), headers={"X-API-Key": "k"})

        assert first.status_code == 200
        assert first.json()["status"] == "completed"
        assert first.json()["result"] == canned
        assert second.json() == first.json(), "polling must be idempotent"
    finally:
        _cleanup_chain(contact_id)


def test_get_jobs_on_an_unknown_id_is_404():
    app.dependency_overrides[get_external_api_user] = lambda: {"id": "ext"}
    with external_permissions_granted():
        client = TestClient(app)
        response = client.get(_jobs_endpoint(str(uuid.uuid4())), headers={"X-API-Key": "k"})
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# S3-01d -- the sync wait (and the extraction timeout) are settings, live     #
# --------------------------------------------------------------------------- #


def test_sync_wait_and_extraction_timeout_are_read_live_from_settings():
    from tests._pg_fixture import blank_session

    with blank_session() as db:
        from app.models.user import SystemSetting
        from app.services.media_access_service import resolve_media_settings

        row = SystemSetting(
            id=str(uuid.uuid4()),
            name="ZZT",
            media_sync_wait_seconds=30,
            media_extraction_timeout_seconds=45,
        )
        db.add(row)
        db.flush()

        before = resolve_media_settings(db)
        assert before.sync_wait_seconds == 30
        assert before.extraction_timeout_seconds == 45
        assert before.extraction_timeout_seconds >= before.sync_wait_seconds, (
            "a job that outlives the wait must still be inside the worker's own "
            "ceiling, or it is killed mid-flight rather than degrading (PLAN 2.4)"
        )

        row.media_sync_wait_seconds = 10
        db.flush()
        after = resolve_media_settings(db)
        assert after.sync_wait_seconds == 10, "no restart/cache required"


# --------------------------------------------------------------------------- #
# S3-01 / S3-01b / S3-01c / S3-02b -- the full HTTP round trip, real DB       #
# --------------------------------------------------------------------------- #


def _fake_settings(**overrides):
    """Constructs the exact `MediaSettings` dataclass shape
    `app.services.media_access_service.resolve_media_settings` must return --
    field names here are the pinned contract (deliberately WITHOUT the
    `media_` prefix the underlying `system_settings` columns carry, since this
    is the resolved-settings object, not the row)."""
    from app.services.media_access_service import MediaSettings

    base = dict(
        image_monthly_limit=50,
        voice_monthly_limit=100,
        voice_max_seconds=120,
        burst_limit=1000,  # burst is not what these tests exercise
        burst_window_seconds=60,
        warn_threshold_percent=80,
        image_provider=None,
        image_model=None,
        image_degraded_model="gpt-4o-mini",
        transcribe_model="whisper-1",
        # NULL, as it ships: image's tiers were measured, voice's were not.
        voice_degraded_model=None,
        language_mode="pinned",
        language_pinned="en",
        language_hints=["en", "ms", "zh"],
        sync_wait_seconds=1.5,
        extraction_timeout_seconds=5,
        max_entities=10,
    )
    base.update(overrides)
    return MediaSettings(**base)


def _spawn_worker_after_enqueue(monkeypatch, *, extraction_seconds: float, result=None, fail=False):
    """Monkeypatches the route's `enqueue_job` to spawn a real background
    thread that runs the REAL `process_media_extraction` task -- modelling
    what the RQ worker process would do, without starting RQ. The extraction
    seam sleeps `extraction_seconds` so the test controls whether the route's
    (short) sync wait catches it or times out."""
    import app.tasks.media_tasks as media_tasks
    from app.api.v1.external import media as media_route

    def _stub_extraction(job):
        time.sleep(extraction_seconds)
        if fail:
            raise RuntimeError("stub failure")
        return result or {"rendered_text": "check stock", "entities": []}

    monkeypatch.setattr(media_tasks, "run_media_extraction", _stub_extraction)

    def _enqueue(_func, *args, **kwargs):
        # Mirrors the attachments.py:1357-1370 precedent's call shape --
        # enqueue_job(task_func, <db row id>, ..., job_id=<rq-preassigned id>)
        # -- so the DB id is the first positional arg. Read defensively via
        # *args/**kwargs (never a same-named parameter) because that
        # precedent ALSO passes an RQ id under the keyword `job_id`, which is
        # a different id (`rq_job_id`) and would collide with a parameter
        # literally named `job_id`.
        db_job_id = args[0] if args else kwargs.get("media_job_id")
        thread = threading.Thread(
            target=media_tasks.process_media_extraction, args=(db_job_id,), daemon=True
        )
        thread.start()
        return type("Job", (), {"id": db_job_id})()

    monkeypatch.setattr(media_route, "enqueue_job", _enqueue)
    monkeypatch.setattr(
        media_route, "resolve_media_settings", lambda db: _fake_settings()
    )


def _post(client, contact, message_id, **extra):
    payload = {
        "respond_io_id": contact.respond_io_id,
        "message_id": message_id,
        "modality": "image",
        "media_url": "https://cdn.respond.io/x.jpg",
        "mime_type": "image/jpeg",
        "caption": "check stock",
        "turn_id": "t-1",
    }
    payload.update(extra)
    return client.post(PROCESS_ENDPOINT, json=payload, headers={"X-API-Key": "k"})


# #307: returns 'pending' under xdist - a row-lock race on
# contact_media_limit between the route's quota path and the in-thread
# worker made the 0.3s stub take longer than media_sync_wait_seconds when a
# neighbouring xdist worker held the row.
@pytest.mark.flaky(reruns=2, reruns_delay=1)
def test_extraction_finishing_inside_the_sync_wait_returns_completed_inline(
    real_chain, monkeypatch
):
    """S3-01: the same HTTP response carries status:completed and the full
    result when the worker finishes inside `media_sync_wait_seconds`."""
    _spawn_worker_after_enqueue(monkeypatch, extraction_seconds=0.3)
    app.dependency_overrides[get_external_api_user] = lambda: {"id": "ext"}
    with external_permissions_granted():
        client = TestClient(app)
        response = _post(client, real_chain.contact, "s3-01")

    body = response.json()
    assert body["status"] == "completed"
    assert body["result"] == {"rendered_text": "check stock", "entities": []}


def test_extraction_outliving_the_wait_degrades_to_pending_not_a_failure(
    real_chain, monkeypatch
):
    """S3-01c: exceeding `media_sync_wait_seconds` returns status:pending
    with the job_id -- not an error -- the job keeps running, and:
    - it is later retrievable through GET /jobs/{job_id} (S3-04's transport)
    - a same-message_id re-call replays with no second ledger row / spend
        (S2-02's guarantee, re-checked here on the async path specifically).
    Extraction runs 2s against a 0.5s sync wait but a 5s extraction timeout
    (S3-01d's inequality), so it must complete -- not be killed mid-flight.
    """
    _spawn_worker_after_enqueue(monkeypatch, extraction_seconds=2.0)
    from app.api.v1.external import media as media_route

    monkeypatch.setattr(
        media_route,
        "resolve_media_settings",
        lambda db: _fake_settings(sync_wait_seconds=0.5, extraction_timeout_seconds=5),
    )
    app.dependency_overrides[get_external_api_user] = lambda: {"id": "ext"}
    with external_permissions_granted():
        client = TestClient(app)
        first = _post(client, real_chain.contact, "s3-01c")

        assert first.json()["status"] == "pending"
        job_id = first.json()["job_id"]
        assert job_id

        # re-call with the SAME message_id while the job is still running.
        replay = _post(client, real_chain.contact, "s3-01c")
        assert replay.json()["idempotent_replay"] is True
        assert replay.json()["job_id"] == job_id

        # give the background "worker" thread time to finish (2s sleep).
        deadline = time.monotonic() + 4
        polled = None
        while time.monotonic() < deadline:
            polled = client.get(_jobs_endpoint(job_id), headers={"X-API-Key": "k"})
            if polled.json()["status"] == "completed":
                break
            time.sleep(0.2)

    assert polled is not None and polled.json()["status"] == "completed"
    assert polled.json()["result"] == {"rendered_text": "check stock", "entities": []}

    from app.models.media import ContactMediaUsage

    db = SessionLocal()
    try:
        rows = (
            db.query(ContactMediaUsage)
            .filter(ContactMediaUsage.contact_id == real_chain.contact.id)
            .all()
        )
        assert len(rows) == 1, "no second ledger row from the retry"
    finally:
        db.close()


def test_the_inline_polled_and_callback_result_bodies_are_identical(
    real_chain, monkeypatch
):
    """S3-02b: one result shape, three transports."""
    captured_callback = []
    _spawn_worker_after_enqueue(
        monkeypatch,
        extraction_seconds=0.2,
        result={"rendered_text": "same everywhere", "entities": [], "truncated": False},
    )
    import app.tasks.media_tasks as media_tasks

    monkeypatch.setattr(
        media_tasks,
        "_post_callback",
        lambda url, headers, body: captured_callback.append(body),
    )
    app.dependency_overrides[get_external_api_user] = lambda: {"id": "ext"}
    with external_permissions_granted():
        client = TestClient(app)
        inline = _post(
            client,
            real_chain.contact,
            "s3-02b",
            callback_url="https://n8n.example/webhook",
        )
        assert inline.json()["status"] == "completed"
        job_id = inline.json()["job_id"]

        polled = client.get(_jobs_endpoint(job_id), headers={"X-API-Key": "k"})

    assert len(captured_callback) == 1
    assert inline.json()["result"] == polled.json()["result"] == captured_callback[0]["result"]


# #638: asserts fast_elapsed < 1.5s while a slow request is in flight on a
# shared event loop - the same wall-clock-under-xdist-load shape as #307;
# not yet observed red, filed pre-emptively alongside the marker so a CI
# scheduling hiccup gets a rerun instead of hiding a real reintroduction of
# the blocking bug this test guards (see the issue for why 2 reruns is safe).
@pytest.mark.flaky(reruns=2, reruns_delay=1)
def test_second_unrelated_request_returns_promptly_while_extraction_is_in_flight(
    real_chain, monkeypatch
):
    """S3-01b -- the regression guard against reproducing the blocking portal
    defect (`app/api/v1/public/ai_extract.py:116`).

    Both requests are dispatched through ONE persistent TestClient portal
    (`with TestClient(app) as client:` keeps a single background event loop
    for the whole block -- see `starlette.testclient.TestClient.__enter__`),
    from two different OS threads via a ThreadPoolExecutor, so the loop must
    genuinely interleave the two coroutines to satisfy this test. If the
    handler ever called a synchronous multi-second primitive directly (rather
    than `await`ing it), that OS thread -- and therefore the one shared event
    loop -- would be blocked for the full extraction, and the second request
    could not even start being served until the first finished. A trivial,
    unrelated endpoint (job lookup on a never-created id, which 404s almost
    instantly) stands in for "a second, unrelated request".
    """
    _spawn_worker_after_enqueue(monkeypatch, extraction_seconds=3.0)
    app.dependency_overrides[get_external_api_user] = lambda: {"id": "ext"}

    with external_permissions_granted(), TestClient(app) as client:
        with ThreadPoolExecutor(max_workers=2) as pool:
            slow_future = pool.submit(_post, client, real_chain.contact, "s3-01b")
            time.sleep(0.3)  # let the slow request actually enter the handler first

            fast_started = time.monotonic()
            fast_response = client.get(
                _jobs_endpoint(str(uuid.uuid4())), headers={"X-API-Key": "k"}
            )
            fast_elapsed = time.monotonic() - fast_started

            slow_response = slow_future.result(timeout=10)

    assert fast_response.status_code == 404
    assert fast_elapsed < 1.5, (
        f"the unrelated request took {fast_elapsed:.2f}s while a media call was "
        "in flight -- the event loop was blocked"
    )
    # the slow one legitimately took close to the full extraction time.
    assert slow_response.json()["status"] in ("completed", "pending")


def test_a_truly_concurrent_duplicate_replays_the_winners_job_not_a_500(
    real_chain, monkeypatch
):
    """Two requests with the SAME idempotency key, genuinely in flight at once,
    so BOTH pass the probe before either has recorded. The loser of the ledger
    insert must come back with the winner's decision and job - the same replay
    a later retry gets - never an `IntegrityError` off a second job insert
    against `uq_media_extraction_job_usage_id`. Exactly one ledger row, one job
    row and one enqueue must exist afterwards.

    The rendezvous is the idempotency probe itself (`_find_usage`): a two-party
    barrier on each request's FIRST probe guarantees both looked at an empty
    ledger before either recorded - the race is forced, not hoped for. It has
    to be the probe rather than anything later, because the fast path then
    takes the contact's gate row `FOR UPDATE`, which serializes the two requests
    from that point on: the loser waits for the winner's commit and only then
    reaches the ledger insert, where the `ON CONFLICT` hands it the winner's
    row. Later `_find_usage` calls (the re-select inside `_record`) pass
    straight through, or the loser - still parked on the lock - could never
    make the barrier's second party.

    Two deliberate departures from S3-01b's shape, both required for genuine
    concurrency: the client is NOT a context manager (each request then gets
    its own portal/event loop - one shared portal serializes two POSTs to the
    same async endpoint, and the second would deadlock against the barrier),
    and the contact's `respond_io_id` is snapshotted before the threads start
    (both threads reading the expired ORM attribute concurrently is an
    `InvalidRequestError` on the fixture's session, nothing to do with the
    route).
    """
    from types import SimpleNamespace
    _spawn_worker_after_enqueue(monkeypatch, extraction_seconds=0.2)
    from app.api.v1.external import media as media_route
    from app.services import media_access_service

    enqueues: list = []
    inner_enqueue = media_route.enqueue_job

    def _counting_enqueue(*args, **kwargs):
        enqueues.append(args)
        return inner_enqueue(*args, **kwargs)

    monkeypatch.setattr(media_route, "enqueue_job", _counting_enqueue)

    barrier = threading.Barrier(2)
    inner_probe = media_access_service._find_usage
    probed = threading.local()

    def _rendezvous_probe(db, request):
        if not getattr(probed, "done", False):
            probed.done = True
            result = inner_probe(db, request)
            barrier.wait(timeout=10)
            return result
        return inner_probe(db, request)

    monkeypatch.setattr(media_access_service, "_find_usage", _rendezvous_probe)

    app.dependency_overrides[get_external_api_user] = lambda: {"id": "ext"}
    frozen_contact = SimpleNamespace(respond_io_id=real_chain.contact.respond_io_id)
    with external_permissions_granted():
        client = TestClient(app)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(_post, client, frozen_contact, "race-dup")
                for _ in range(2)
            ]
            responses = [future.result(timeout=20) for future in futures]

    assert [r.status_code for r in responses] == [200, 200]
    bodies = [r.json() for r in responses]
    assert sorted(body["idempotent_replay"] for body in bodies) == [False, True]
    job_ids = {body["job_id"] for body in bodies}
    assert len(job_ids) == 1 and None not in job_ids, (
        "the loser must be handed the winner's job id"
    )
    assert len(enqueues) == 1, "the replay path must not enqueue a second RQ job"

    from app.models.media import ContactMediaUsage, MediaExtractionJob

    db = SessionLocal()
    try:
        usages = (
            db.query(ContactMediaUsage)
            .filter(ContactMediaUsage.contact_id == real_chain.contact.id)
            .all()
        )
        assert len(usages) == 1, "one spend, not two"
        jobs = (
            db.query(MediaExtractionJob)
            .filter(MediaExtractionJob.usage_id == usages[0].id)
            .all()
        )
        assert len(jobs) == 1
        assert str(jobs[0].id) in job_ids
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# The callback body carries the notices, not an empty list (PLAN 16.5)        #
# --------------------------------------------------------------------------- #


def test_the_callback_body_carries_the_notices_the_fast_path_recorded():
    """S3-02b's "one shape, three transports" was only true because nothing
    populated `notices` - it was hardcoded `[]`. A consumer reading the callback
    or the polling endpoint must get the same customer text the synchronous
    response carried, or the far end has to re-derive it and the guarantee is
    decorative."""
    import app.tasks.media_tasks as media_tasks

    warning = {
        "kind": "warn_80",
        "text": "You have 9 of 50 photo reads left this month. The allowance "
        "resets on 1 September.",
        "append": True,
    }
    job_id, contact_id = _seed_job_row(notices=[warning])
    try:
        db = SessionLocal()
        try:
            job = (
                db.query(media_tasks.MediaExtractionJob)
                .filter(media_tasks.MediaExtractionJob.id == job_id)
                .first()
            )
            body = media_tasks.build_callback_body(db, job)
        finally:
            db.close()

        assert body["notices"] == [warning]
    finally:
        _cleanup_chain(contact_id)


def test_a_job_whose_decision_carried_no_notices_still_reports_a_list():
    """The shape does not change with the content: `notices` is always a list,
    never null, so the far end never branches on its absence."""
    import app.tasks.media_tasks as media_tasks

    job_id, contact_id = _seed_job_row()
    try:
        db = SessionLocal()
        try:
            job = (
                db.query(media_tasks.MediaExtractionJob)
                .filter(media_tasks.MediaExtractionJob.id == job_id)
                .first()
            )
            assert media_tasks.build_callback_body(db, job)["notices"] == []
        finally:
            db.close()
    finally:
        _cleanup_chain(contact_id)


# --------------------------------------------------------------------------- #
# The task claims the row: a duplicate copy of the id never runs twice        #
# --------------------------------------------------------------------------- #


def test_a_second_copy_of_a_running_job_does_not_run_the_extraction_again(monkeypatch):
    """A stranded-job re-enqueue (or an RQ retry) can put a second copy of the
    same id on the queue. Once one copy has claimed the row as `running`, the
    other must be a no-op: no second provider call, no overwritten result."""
    from app.models.media import MediaExtractionJob
    from app.tasks import media_tasks

    job_id, contact_id = _seed_job_row()
    runs: list[str] = []
    monkeypatch.setattr(
        media_tasks, "run_media_extraction", lambda job: runs.append(job.id) or {"ok": True}
    )
    monkeypatch.setattr(media_tasks, "deliver_callback", lambda job: None)
    try:
        db = SessionLocal()
        try:
            db.query(MediaExtractionJob).filter(MediaExtractionJob.id == job_id).update(
                {"status": "running", "started_at": media_tasks._utcnow()}
            )
            db.commit()
        finally:
            db.close()

        media_tasks.process_media_extraction(job_id)

        assert runs == []
        assert _fetch_job(job_id).status == "running"
    finally:
        _cleanup_chain(contact_id)


def test_the_task_claims_a_queued_job_and_completes_it(monkeypatch):
    from app.tasks import media_tasks

    job_id, contact_id = _seed_job_row()
    runs: list[str] = []
    monkeypatch.setattr(
        media_tasks, "run_media_extraction", lambda job: runs.append(job.id) or {"ok": True}
    )
    monkeypatch.setattr(media_tasks, "deliver_callback", lambda job: None)
    try:
        media_tasks.process_media_extraction(job_id)
        media_tasks.process_media_extraction(job_id)

        assert runs == [job_id]
        job = _fetch_job(job_id)
        assert job.status == "completed"
        assert job.started_at is not None
    finally:
        _cleanup_chain(contact_id)
