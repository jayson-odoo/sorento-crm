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
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from app.database import SessionLocal
from app.models.job import ImportJob, JobStatus
from app.services import import_outcome_codes as codes
from app.services.foundryx_autocount_client import FoundryxAutocountClient
from app.services.import_outcome import ImportOutcome
from app.services.master_ingest_service import IngestOutcome, MasterIngestService

logger = logging.getLogger(__name__)


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


def _preview_products(db, job: ImportJob, pull: dict) -> dict:
    client = FoundryxAutocountClient()
    rows = client.all_rows(pull.get("snapshot_id"))
    header = pull.get("header") or {}
    _check_snapshot_guards(rows, header, pull)

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
            outcome_writer.success(
                value=item_code,
                identity={"item_code": item_code},
                entity_id=record.entity_id,
                entity_type="product",
            )
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
            outcome_writer.fail(
                code=_first_error_code(record.errors),
                message="; ".join(f"{k}: {v}" for k, v in (record.errors or {}).items()) or None,
                value=item_code,
                identity={"item_code": item_code},
            )

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


def _check_snapshot_guards(rows: list[dict], header: dict, pull: dict) -> None:
    """AC-PP-1: refuse when the snapshot cannot be trusted; contentHash only warns."""
    if not header.get("complete", False):
        raise ValueError("AutoCount snapshot is incomplete; pull again.")
    expected_count = header.get("recordCount")
    if len(rows) != expected_count:
        raise ValueError(
            f"Assembled row count ({len(rows)}) does not match the snapshot header "
            f"record count ({expected_count})."
        )
    if header.get("companyCode") != pull.get("company_code"):
        raise ValueError(
            f"Snapshot company ({header.get('companyCode')!r}) does not match this "
            f"pull's own company ({pull.get('company_code')!r})."
        )
    _warn_if_content_hash_mismatch(rows, header)


def _warn_if_content_hash_mismatch(rows: list[dict], header: dict) -> None:
    """A5 (cross-repo contract, FoundryX plan 10 appendix) - a mismatch is recorded as a
    warning, never a refusal. The exact hashing rule lives in the FoundryX contract this
    slice does not have machine-checkable access to; this recomputes a stable hash over
    every row's `source_ref` (its identity) so a transit corruption is at least visible in
    the server log without asserting a stronger claim about the algorithm than SR1 can
    verify against real fixtures.
    """
    expected = header.get("contentHash")
    if not expected:
        return
    digest = hashlib.sha256(
        "|".join(sorted(str(r.get("source_ref", "")) for r in rows)).encode("utf-8")
    ).hexdigest()
    if digest != expected:
        logger.warning(
            "autocount pull contentHash mismatch (recomputed=%s, header=%s) - not refusing",
            digest,
            expected,
        )


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
