"""AutoCount pull lifecycle (PLAN-autocount-pull-review.md, SR1: start / current / status).

A pull is one `import_jobs` row (`job_type` `autocount_products_pull` /
`autocount_stock_pull`). It stays `pending` while FoundryX builds the snapshot - there is
no RQ job for that half, so the orphan sweep (which only ever looks at `queued` and
`started`) never touches it. When FoundryX reports the snapshot ready, the SAME row flips
`pending` -> `queued` and the preview task (`app.tasks.autocount_pull_tasks`) takes it the
rest of the way to `finished`. Confirm (SR3) creates a SECOND row for the apply.

Everything the FE needs about a pull's state - its phase, progress, header facts, counts,
compare summary, confirm gate, apply job id - lives in ONE JSONB column
(`import_jobs.metadata["autocount_pull"]`), never a new table: the plan's "no staging
table, two job rows per pull" (P1/P2).

`enqueue_job` is imported under this exact name (not `app.services.queue_service.enqueue_job`
qualified inline) because the SR1 tests patch `app.services.autocount_pull_service.enqueue_job`
directly - see the test file's module docstring.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.job import ImportJob, JobStatus
from app.services.foundryx_autocount_client import FoundryxAutocountClient, FoundryxPullError
from app.services.queue_service import enqueue_job

#: Entity name (as the FE/route spells it) -> the permission slug that gates it.
ENTITY_PERMISSIONS = {
    "products": "master_data.products.autocount_pull",
    "stock_balances": "inventory.stock.autocount_pull",
}

#: Entity name -> the `import_jobs.job_type` a pull of it is stored under.
JOB_TYPES = {
    "products": "autocount_products_pull",
    "stock_balances": "autocount_stock_pull",
}

#: Phases that make a pull "open" - reused by a second start, and what `current` looks for.
_OPEN_PHASES = ("building", "previewing", "review")

#: A pull still `building` past this age is abandoned server-side (AC-BD-4): FoundryX
#: itself never guarantees a snapshot build finishes, and nothing else times this out.
BUILD_EXPIRY = timedelta(minutes=60)

#: Header keys never persisted onto the job row. Both can be large (a stock snapshot's
#: `negativePairList` runs into the thousands) and both are FoundryX-owned lists the
#: preview/apply tasks read straight off a fresh snapshot read, not off this cache.
_HEADER_KEYS_NOT_STORED = ("excludedRows", "negativePairList")


class UnknownEntity(ValueError):
    """Raised for an `entity` this lane does not know - the route turns it into a 404."""


def _job_type_for(entity: str) -> str:
    try:
        return JOB_TYPES[entity]
    except KeyError:
        raise UnknownEntity(entity)


def _pull_meta(job: ImportJob) -> dict:
    meta = job.job_metadata or {}
    return dict(meta.get("autocount_pull") or {})


def _with_pull(job: ImportJob, pull: dict) -> dict:
    meta = dict(job.job_metadata or {})
    meta["autocount_pull"] = pull
    return meta


def _is_build_expired(job: ImportJob) -> bool:
    if not job.created_at:
        return False
    return datetime.utcnow() - job.created_at > BUILD_EXPIRY


def entity_of(job: ImportJob) -> str:
    return _pull_meta(job).get("entity", "")


def _company_code(db: Session, company_id: str) -> str:
    from app.models.company import Company

    company = db.query(Company).filter(Company.id == company_id).first()
    return company.code if company is not None else ""


def find_open_pull(
    db: Session, *, user_id: str, company_id: Optional[str], entity: str
) -> Optional[ImportJob]:
    """The caller's own open pull for this company + entity, else None (AC-PL-4)."""
    if not company_id:
        return None
    job_type = _job_type_for(entity)
    candidates = (
        db.query(ImportJob)
        .filter(
            ImportJob.job_type == job_type,
            ImportJob.user_id == user_id,
            ImportJob.company_id == company_id,
        )
        .order_by(ImportJob.created_at.desc())
        .all()
    )
    for job in candidates:
        pull = _pull_meta(job)
        if pull.get("phase") not in _OPEN_PHASES:
            continue
        if pull.get("phase") == "building" and _is_build_expired(job):
            continue
        return job
    return None


def get_owned_pull(db: Session, *, job_id: str, user_id: str) -> Optional[ImportJob]:
    """The job, owner-checked - never revealed to anyone but its owner (AC-BD-7, P12)."""
    try:
        job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
    except Exception:
        # A malformed id (not a UUID) is "not found", not a server error - the DB
        # column is a real UUID, so the driver raises rather than returning no rows.
        db.rollback()
        return None
    if job is None or job.user_id != user_id:
        return None
    return job


def start_pull(db: Session, *, user_id: str, company_id: str, entity: str) -> ImportJob:
    """Reuses an open pull; otherwise asks FoundryX to build a snapshot and creates the
    pending row (AC-PL-3, AC-PL-4). Raises `FoundryxPullError` on any FoundryX refusal -
    the caller is responsible for leaving no job row behind on that path, which is true
    here because the row is only ever constructed AFTER `client.build` returns.
    """
    existing = find_open_pull(db, user_id=user_id, company_id=company_id, entity=entity)
    if existing is not None:
        return existing

    company_code = _company_code(db, company_id)
    client = FoundryxAutocountClient()  # raises FoundryxPullError(NOT_CONFIGURED) if unset
    body = client.build(company_code, entity)

    pull = {
        "entity": entity,
        "company_code": company_code,
        "snapshot_id": body.get("snapshotId"),
        "phase": "building",
        "progress": None,
        "header": None,
        "counts": {},
        "confirm_blocked_reason": None,
        "compare": None,
        "apply_job_id": None,
    }
    job = ImportJob(
        job_id=str(uuid.uuid4()),
        job_type=_job_type_for(entity),
        status=JobStatus.PENDING.value,
        user_id=user_id,
        company_id=company_id,
        job_metadata={"autocount_pull": pull},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _claim_and_enqueue_preview(db: Session, job: ImportJob, pull: dict, ready_header: dict) -> None:
    """Flips a still-`pending` pull to `queued` and enqueues the preview task EXACTLY
    ONCE (AC-BD-2). The `status == PENDING` clause in the UPDATE is the conditional
    update: a second caller racing this one finds zero rows to update and enqueues
    nothing, whether the race is two threads or two sequential polls."""
    stored_header = {k: v for k, v in ready_header.items() if k not in _HEADER_KEYS_NOT_STORED}
    pull["header"] = stored_header
    pull["phase"] = "previewing"
    pull["progress"] = None
    new_meta = _with_pull(job, pull)

    result = db.execute(
        update(ImportJob)
        .where(ImportJob.id == job.id, ImportJob.status == JobStatus.PENDING.value)
        .values(status=JobStatus.QUEUED.value, job_metadata=new_meta, updated_at=datetime.utcnow())
        .execution_options(synchronize_session=False)
    )
    db.commit()
    if result.rowcount != 1:
        return

    from app.tasks.autocount_pull_tasks import preview_autocount_pull

    enqueue_job(
        preview_autocount_pull,
        str(job.id),
        queue_name="imports",
        job_timeout=3600,
        job_id=str(job.job_id),
    )


def _mark_failed(db: Session, job: ImportJob, pull: dict, *, phase: str, error: str) -> None:
    pull["phase"] = phase
    job.job_metadata = _with_pull(job, pull)
    job.status = JobStatus.FAILED.value
    job.error = error
    job.completed_at = datetime.utcnow()
    job.updated_at = datetime.utcnow()
    db.commit()


def refresh_pull_status(db: Session, job: ImportJob) -> dict:
    """AC-BD-1..4: while `building`, reads FoundryX and advances the row; every other
    phase is a plain read of what is already stored (no outbound call)."""
    pull = _pull_meta(job)

    if pull.get("phase") == "building":
        if _is_build_expired(job):
            _mark_failed(db, job, pull, phase="expired", error="pull again")
            db.refresh(job)
            return serialize(job)

        client = FoundryxAutocountClient()
        body = client.status(pull.get("snapshot_id"))
        foundryx_status = body.get("status")

        if foundryx_status == "ready":
            _claim_and_enqueue_preview(db, job, pull, body)
            db.refresh(job)
            return serialize(job)

        if foundryx_status == "failed":
            error = body.get("error") or {}
            code = error.get("code", "BUILD_FAILED")
            message = error.get("message", "")
            _mark_failed(db, job, pull, phase="failed", error=f"{code}: {message}".rstrip(": "))
            db.refresh(job)
            return serialize(job)

        # Still building - store progress when FoundryX sent one.
        if body.get("progress") is not None:
            pull["progress"] = body["progress"]
            job.job_metadata = _with_pull(job, pull)
            job.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(job)

    return serialize(job)


def serialize(job: ImportJob) -> dict:
    pull = _pull_meta(job)
    return {
        "job_id": str(job.id),
        "phase": pull.get("phase"),
        "progress": pull.get("progress"),
        "header": pull.get("header"),
        "counts": pull.get("counts") or {},
        "confirm_blocked_reason": pull.get("confirm_blocked_reason"),
        "compare": pull.get("compare"),
        "apply_job_id": pull.get("apply_job_id"),
    }
