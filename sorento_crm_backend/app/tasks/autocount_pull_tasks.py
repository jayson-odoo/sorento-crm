"""RQ tasks for the AutoCount pull lifecycle (PLAN-autocount-pull-review.md).

`preview_autocount_pull` runs the SAME `import_jobs` row the `POST /autocount/pulls`
route created, once `autocount_pull_service._claim_and_enqueue_preview` enqueues it
(queue `imports`, `job_timeout=3600`). SR1 previews `products` only; a `stock_balances`
pull fails loudly with `UnsupportedPullEntity` rather than doing nothing - stock preview
is SR4 (`PLAN-autocount-pull-review.md` Slices table).

`from app.database import SessionLocal` at module top, not a lazy import - the repo
convention every other `app/tasks/*.py` module follows (see `import_tasks.py`), and what
lets a test replace `app.tasks.autocount_pull_tasks.SessionLocal` with a private
connection instead of opening a second, real one.

**The task re-fetches the snapshot header, once, at its own start** (captain ruling,
SR1 fix round): `GET /snapshots/{id}` again via `client.status`, never the copy the route
already stored on the job. The stored copy (`pull["header"]`) is stripped of
`excludedRows`/`negativePairList` (AC-BD-2) and exists for the review PAGE only; the
guards (complete, recordCount vs the assembled rows, companyCode), the A5 contentHash
check and `excludedRows` itself all read from the FRESH fetch instead, so a page that
never loaded still gets a task that decides correctly. `fetch_verified_snapshot` is the
one function that does this - SR3's apply task reuses it unchanged (AC-PC-2 re-checks the
same guards against the same snapshot before it writes anything for real).
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from app.database import SessionLocal
from app.models.job import ImportJob, JobStatus
from app.services import import_outcome_codes as codes
from app.services.foundryx_autocount_client import FoundryxAutocountClient, FoundryxPullError
from app.services.import_outcome import ImportOutcome
from app.services.master_ingest_service import IngestOutcome, MasterIngestService

logger = logging.getLogger(__name__)

#: Warning code appended to `metadata.autocount_pull.warnings` on an A5 contentHash
#: mismatch. Never a refusal - see `_content_hash_warnings`.
CONTENT_HASH_MISMATCH = "content_hash_mismatch"


class UnsupportedPullEntity(ValueError):
    """A pull entity this task cannot preview yet."""


def preview_autocount_pull(db_job_id: str) -> None:
    """AC-PP-1..6: refetch every row, dry-run ingest it, write per-row outcomes, store
    counts, and leave the job `finished` in phase `review` - or `failed` with the reason
    stored, on any guard failure or unexpected error."""
    db = SessionLocal()
    try:
        job = db.query(ImportJob).filter(ImportJob.id == db_job_id).first()
        if job is None:
            logger.warning("preview_autocount_pull: job %s not found", db_job_id)
            return

        pull = dict((job.job_metadata or {}).get("autocount_pull") or {})
        entity = pull.get("entity")

        try:
            if entity == "products":
                counts = _preview_products(db, job, pull)
            else:
                raise UnsupportedPullEntity(
                    f"Stock preview is not implemented yet (SR4); entity={entity!r}."
                )
        except Exception as exc:  # noqa: BLE001 - one job's failure, reported on the job
            db.rollback()
            logger.warning(
                "autocount pull preview failed job=%s entity=%s", db_job_id, entity, exc_info=True
            )
            pull["phase"] = "failed"
            job.job_metadata = {**(job.job_metadata or {}), "autocount_pull": pull}
            job.status = JobStatus.FAILED.value
            job.error = str(exc)[:2000]
            job.completed_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
            db.commit()
            return

        pull["phase"] = "review"
        pull["counts"] = counts
        job.job_metadata = {**(job.job_metadata or {}), "autocount_pull": pull}
        job.status = JobStatus.FINISHED.value
        job.completed_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


def apply_autocount_pull(db_job_id: str) -> None:
    """AC-PC-2/3/4: the SECOND job Confirm creates. Re-verifies the SAME snapshot through
    `fetch_verified_snapshot` (the same guards the preview ran, against a fresh fetch -
    FoundryX answering `SNAPSHOT_EXPIRED` / `UNKNOWN_SNAPSHOT` fails the job with "pull
    again" and writes nothing), then runs `MasterIngestService.ingest` for REAL - not a dry
    run - stamping the confirming user onto every created/updated product (AC-PC-4)."""
    db = SessionLocal()
    try:
        job = db.query(ImportJob).filter(ImportJob.id == db_job_id).first()
        if job is None:
            logger.warning("apply_autocount_pull: job %s not found", db_job_id)
            return

        apply_meta = dict((job.job_metadata or {}).get("autocount_apply") or {})
        entity = apply_meta.get("entity")
        snapshot_id = apply_meta.get("snapshot_id")

        try:
            if entity == "products":
                summary = _apply_products(db, job, snapshot_id)
            else:
                raise UnsupportedPullEntity(
                    f"Stock apply is not implemented yet (SR4); entity={entity!r}."
                )
        except Exception as exc:  # noqa: BLE001 - one job's failure, reported on the job
            db.rollback()
            logger.warning(
                "autocount pull apply failed job=%s entity=%s", db_job_id, entity, exc_info=True
            )
            job.status = JobStatus.FAILED.value
            job.error = str(exc)[:2000]
            job.completed_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
            db.commit()
            return

        apply_meta["counts"] = summary
        job.job_metadata = {**(job.job_metadata or {}), "autocount_apply": apply_meta}
        job.status = JobStatus.FINISHED.value
        job.completed_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


def _apply_products(db, job: ImportJob, snapshot_id: str) -> dict:
    client = FoundryxAutocountClient()
    header, rows, warnings = fetch_verified_snapshot(
        client, snapshot_id=snapshot_id, company_code=_company_code(db, job.company_id)
    )

    company_id = str(job.company_id) if job.company_id else None
    ingest = MasterIngestService(db, company_id=company_id, stamp_user_id=str(job.user_id))
    result = ingest.ingest("products", rows)

    outcome_writer = ImportOutcome(job.id)
    for raw, record in zip(rows, result.records):
        item_code = raw.get("code") if isinstance(raw, dict) else None
        if record.outcome == IngestOutcome.CREATED:
            _write_created_outcome(outcome_writer, item_code, record)
        elif record.outcome == IngestOutcome.UPDATED:
            # A real ingest carries no `diff` (dry-run only) - one outcome per updated
            # record either way, just without the field-by-field detail the preview shows.
            outcome_writer.updated(
                message=f"Product updated: {item_code}",
                value=item_code,
                identity={"item_code": item_code},
                entity_id=record.entity_id,
                entity_type="product",
            )
        else:
            _write_failed_outcome(outcome_writer, item_code, record)
    outcome_writer.flush()

    return result.as_dict()["summary"]


def _company_code(db, company_id) -> str:
    """Same shape as `autocount_pull_service._company_code` - duplicated rather than
    imported (that one is a module-private helper; `supplier_notice_service.py` carries
    its own copy of this exact lookup for the same reason)."""
    from app.models.company import Company

    if not company_id:
        return ""
    company = db.query(Company).filter(Company.id == str(company_id)).first()
    return company.code if company is not None else ""


def _preview_products(db, job: ImportJob, pull: dict) -> dict:
    client = FoundryxAutocountClient()
    header, rows, warnings = fetch_verified_snapshot(
        client, snapshot_id=pull.get("snapshot_id"), company_code=pull.get("company_code")
    )
    # Always a list, never left absent, once a preview has run - "absent or empty on a
    # match" is satisfied by the empty-list case; the mismatch case names the code.
    pull["warnings"] = warnings

    company_id = str(job.company_id) if job.company_id else None
    ingest = MasterIngestService(db, company_id=company_id)
    result = ingest.ingest("products", rows, dry_run=True)

    outcome_writer = ImportOutcome(job.id)
    counts = {
        "received": len(rows),
        "new": 0,
        "changed": 0,
        "unchanged": 0,
        "failed": 0,
        "left_out": 0,
        "price_to_zero": 0,
    }

    for raw, record in zip(rows, result.records):
        item_code = raw.get("code") if isinstance(raw, dict) else None
        if record.outcome == IngestOutcome.CREATED:
            counts["new"] += 1
            _write_created_outcome(outcome_writer, item_code, record)
        elif record.outcome == IngestOutcome.UPDATED:
            diff = record.diff or {}
            if not diff:
                # AC-PP-3: an updated record with an empty diff is unchanged - no row.
                counts["unchanged"] += 1
                continue
            counts["changed"] += 1
            if _moves_price_to_zero(diff):
                counts["price_to_zero"] += 1
            outcome_writer.updated(
                message=_diff_message(diff),
                value=item_code,
                identity={"item_code": item_code, "diff": diff},
                entity_id=record.entity_id,
                entity_type="product",
            )
        else:  # FAILED or RETRYABLE - both surface as a failed row on the pull
            counts["failed"] += 1
            _write_failed_outcome(outcome_writer, item_code, record)

    excluded_rows = header.get("excludedRows") or []
    counts["left_out"] = len(excluded_rows)
    for entry in excluded_rows:
        outcome_writer.skip(
            code=codes.AUTOCOUNT_EXCLUDED,
            message=entry.get("message"),
            value=entry.get("code"),
            identity={"item_code": entry.get("code"), "reason": entry.get("reason")},
        )

    outcome_writer.flush()
    return counts


def _write_created_outcome(outcome_writer: ImportOutcome, item_code, record) -> None:
    """CREATED is written the same way whether this is a dry-run preview or a real
    apply - shared by `_preview_products` and `_apply_products` (SR3)."""
    outcome_writer.success(
        value=item_code,
        identity={"item_code": item_code},
        entity_id=record.entity_id,
        entity_type="product",
    )


def _write_failed_outcome(outcome_writer: ImportOutcome, item_code, record) -> None:
    """FAILED/RETRYABLE is written the same way whether this is a dry-run preview or a
    real apply - shared by `_preview_products` and `_apply_products` (SR3)."""
    outcome_writer.fail(
        code=_first_error_code(record.errors),
        message="; ".join(f"{k}: {v}" for k, v in (record.errors or {}).items()) or None,
        value=item_code,
        identity={"item_code": item_code},
    )


def fetch_verified_snapshot(
    client: FoundryxAutocountClient, *, snapshot_id: str, company_code: str
) -> tuple[dict, list[dict], list[str]]:
    """Re-fetches the snapshot header and every row, and checks the AC-PP-1 guards
    against THAT fetch - never a copy stored on the job. Shared by the preview task
    (SR1) and the apply task (SR3, AC-PC-2 re-checks the same guards before it writes
    anything for real).

    Returns ``(header, rows, warnings)``. Raises ``ValueError`` (a message safe to store
    verbatim as ``import_jobs.error``) on any guard failure - an incomplete snapshot, an
    assembled row count that does not match the header, a company mismatch, a snapshot
    FoundryX no longer answers `ready` for, or a snapshot FoundryX cannot find at all.
    """
    header = _fetch_ready_header(client, snapshot_id)
    rows = client.all_rows(snapshot_id)
    _check_header_guards(rows, header, company_code)
    warnings = _content_hash_warnings(rows, header)
    return header, rows, warnings


def _fetch_ready_header(client: FoundryxAutocountClient, snapshot_id: str) -> dict:
    try:
        header = client.status(snapshot_id)
    except FoundryxPullError as exc:
        # Covers FoundryX 404 UNKNOWN_SNAPSHOT / 410 SNAPSHOT_EXPIRED as much as an
        # outright transport failure - none of them leave anything left to verify.
        raise ValueError(f"Snapshot no longer available ({exc.code}); pull again.") from exc
    if header.get("status") != "ready":
        raise ValueError(
            f"AutoCount snapshot is no longer ready (status={header.get('status')!r}); "
            f"pull again."
        )
    return header


def _check_header_guards(rows: list[dict], header: dict, company_code: str) -> None:
    """AC-PP-1: refuse when the snapshot cannot be trusted."""
    if not header.get("complete", False):
        raise ValueError("AutoCount snapshot is incomplete; pull again.")
    expected_count = header.get("recordCount")
    if len(rows) != expected_count:
        raise ValueError(
            f"Assembled row count ({len(rows)}) does not match the snapshot header "
            f"record count ({expected_count})."
        )
    if header.get("companyCode") != company_code:
        raise ValueError(
            f"Snapshot company ({header.get('companyCode')!r}) does not match this "
            f"pull's own company ({company_code!r})."
        )


def _content_hash(rows: list[dict]) -> str:
    """The A5 rule (FoundryX contract, fixtures README "contentHash - how it was
    computed"): sha256 over the concatenation, page-then-row order, of
    ``json.dumps(row, sort_keys=True, separators=(",", ":")) + "\\n"`` per row, utf-8.
    ``rows`` is already in that order - `FoundryxAutocountClient.all_rows` extends page
    by page, in the order FoundryX served them.
    """
    digest = hashlib.sha256()
    for row in rows:
        digest.update(json.dumps(row, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _content_hash_warnings(rows: list[dict], header: dict) -> list[str]:
    """A mismatch is recorded as a warning, never a refusal (AC-PP-1). Never logs row
    content - only the two digests and the snapshot id.
    """
    expected = header.get("contentHash")
    if not expected:
        return []
    digest = _content_hash(rows)
    if digest == expected:
        return []
    logger.warning(
        "autocount pull contentHash mismatch snapshot=%s recomputed=%s header=%s - not refusing",
        header.get("snapshotId"),
        digest,
        expected,
    )
    return [CONTENT_HASH_MISMATCH]


def _moves_price_to_zero(diff: dict) -> bool:
    price = diff.get("list_price")
    if not isinstance(price, dict):
        return False
    current = price.get("current")
    incoming = price.get("incoming")
    return bool(current) and not incoming


def _diff_message(diff: dict) -> str:
    parts = []
    for field, values in diff.items():
        if not isinstance(values, dict):
            continue
        parts.append(f"{field}: {values.get('current')} -> {values.get('incoming')}")
    return "; ".join(parts)


def _first_error_code(errors: Optional[dict]) -> str:
    if not errors:
        return codes.ROW_ERROR
    return str(next(iter(errors)))[:64]
