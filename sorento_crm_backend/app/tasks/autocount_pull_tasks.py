"""RQ tasks for the AutoCount pull lifecycle (PLAN-autocount-pull-review.md).

`preview_autocount_pull` runs the SAME `import_jobs` row the `POST /autocount/pulls`
route created, once `autocount_pull_service._claim_and_enqueue_preview` enqueues it
(queue `imports`, `job_timeout=3600`). SR1 built the `products` half; SR4 adds
`stock_balances` (`_preview_stock` / `_apply_stock`) - same dispatch, same shared
`fetch_verified_snapshot` guard.

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

**Stock needs an ambient company scope the products path never did** (AC-SP-2/AC-SC-2):
`MasterIngestService` wraps every DB op of its own in `company_scope(...)`, but
`StockService.bulk_import_stock` relies on the SESSION's ambient scope for its internal
Product/Warehouse/Stock lookups (same as the manual stock-import job,
`import_tasks.process_stock_import` + `_apply_import_job_scope`) - a worker session starts
`UNSET` (fail-closed, reads return 0 rows), so `_preview_stock`/`_apply_stock` wrap the
`bulk_import_stock` call in `company_scope(db, frozenset({company_id}))` themselves.
`classify_stock_rows`'s own warehouse query is raw SQL with an explicit `company_id`
argument (AC-SP-2's own point) and needs no ambient scope at all.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import text

from app.database import SessionLocal
from app.models.base import company_scope
from app.models.job import ImportJob, JobStatus
from app.services import import_outcome_codes as codes
from app.services.autocount_pull_service import (
    build_stock_workbook,
    classify_stock_rows,
    stock_list_archive_filename,
)
from app.services.foundryx_autocount_client import FoundryxAutocountClient, FoundryxPullError
from app.services.import_outcome import ImportOutcome
from app.services.inventory_service import StockService
from app.services.job_service import JobService
from app.services.master_ingest_service import IngestOutcome, MasterIngestService

logger = logging.getLogger(__name__)

#: Warning code appended to `metadata.autocount_pull.warnings` on an A5 contentHash
#: mismatch. Never a refusal - see `_content_hash_warnings`.
CONTENT_HASH_MISMATCH = "content_hash_mismatch"

#: Warning code appended to the PULL job's `metadata.autocount_pull.warnings` (the row
#: the review page reads, never the apply job's own) when a stock apply's stock import
#: committed but the best-effort Stock List archive step failed (captain ruling, SR4 fix
#: round): the sync is real, but the chatbot/n8n would otherwise keep answering from a
#: stale file with no visible sign anything is wrong.
STOCK_LIST_NOT_ARCHIVED = "stock_list_not_archived"

#: Confirm-blocked / apply-refusal wording when a stock pull's FED batch is empty
#: (Phase 3 fix round, F-1, #1045 HIGH): `StockService.bulk_import_stock`'s own
#: "active warehouse, absent from this batch -> zeroed" sweep is company-wide, so an
#: empty batch would otherwise zero every active warehouse's stock, not just whatever
#: this pull was ever about. Shared by the preview's `confirm_blocked_reason` and the
#: apply's own refusal so the two never say something different about the same guard.
EMPTY_FED_REASON = "No row matched an active warehouse; nothing to apply."


class UnsupportedPullEntity(ValueError):
    """A pull entity this task cannot preview yet."""


def _publish_preview_progress(job_id: str, processed: int, total: int) -> None:
    """B3 (small-fix track): a full-size products preview sits 4-5 minutes on a bare
    spinner today - this is what lets the review page show "N of M" instead. Writes
    through its OWN fresh session, never the preview's own `db` - that session holds the
    whole dry-run ingest in one open transaction (rolled back at the very end), so
    publishing progress on it would commit the preview early, same shape of bug
    `product_spec_change_listener` was just fixed for. Best-effort: this is a progress
    indicator, not the result - a failure here must never fail the preview itself.
    """
    fresh = SessionLocal()
    try:
        JobService(fresh).update_job_progress(job_id, processed_rows=processed, total_rows=total)
    except Exception:  # noqa: BLE001 - never let a progress bump fail the preview
        logger.warning("could not publish preview progress for job %s", job_id, exc_info=True)
    finally:
        fresh.close()


def _stored_pull_phase(db, job_id) -> str:
    """A fresh, direct read of the pull's OWN stored phase - never the ORM's
    identity-mapped `job` object, which this task holds onto (and never refreshes)
    across the whole dry-run ingest. What the "did a Discard land while this task was
    running" guard below checks before writing a terminal phase over it (AC-DS-8a):
    Discard commits on a DIFFERENT session (the request), so only a fresh read sees it.
    """
    row = db.execute(
        text("SELECT metadata FROM import_jobs WHERE id = :id"), {"id": str(job_id)}
    ).mappings().first()
    if row is None:
        return ""
    meta = row["metadata"] or {}
    return (meta.get("autocount_pull") or {}).get("phase") or ""


def preview_autocount_pull(db_job_id: str) -> None:
    """AC-PP-1..6: refetch every row, dry-run ingest it, write per-row outcomes, store
    counts, and leave the job `finished` in phase `review` - or `failed` with the reason
    stored, on any guard failure or unexpected error.

    AC-DS-8a: neither terminal write happens if the pull was discarded WHILE this task
    was running - re-checked against a fresh read right before each write, since a
    Discard lands on a different session/commit than this task's own long-lived one.
    """
    db = SessionLocal()
    try:
        job = db.query(ImportJob).filter(ImportJob.id == db_job_id).first()
        if job is None:
            logger.warning("preview_autocount_pull: job %s not found", db_job_id)
            return

        pull = dict((job.job_metadata or {}).get("autocount_pull") or {})
        entity = pull.get("entity")

        if pull.get("phase") != "previewing":
            # Discarded (or otherwise moved on) before the worker even picked this job up
            # (S2, Phase 3 fix round) - never fetch the snapshot / run a full dry-run
            # ingest for a pull already thrown away; a products pull is ~12k rows.
            return

        try:
            if entity == "products":
                counts = _preview_products(db, job, pull)
            elif entity == "stock_balances":
                counts = _preview_stock(db, job, pull)
            else:
                raise UnsupportedPullEntity(f"Unknown pull entity {entity!r}.")
        except Exception as exc:  # noqa: BLE001 - one job's failure, reported on the job
            db.rollback()
            logger.warning(
                "autocount pull preview failed job=%s entity=%s", db_job_id, entity, exc_info=True
            )
            if _stored_pull_phase(db, db_job_id) == "discarded":
                return
            pull["phase"] = "failed"
            job.job_metadata = {**(job.job_metadata or {}), "autocount_pull": pull}
            job.status = JobStatus.FAILED.value
            job.error = str(exc)[:2000]
            job.completed_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
            db.commit()
            return

        if _stored_pull_phase(db, db_job_id) != "previewing":
            # Discarded (or otherwise moved on) while this preview ran - leave the row
            # exactly as whatever discarded it left it; never resurrect `review` over it.
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
        pull_job_id = apply_meta.get("pull_job_id")

        try:
            if entity == "products":
                summary = _apply_products(db, job, snapshot_id)
            elif entity == "stock_balances":
                summary = _apply_stock(db, job, snapshot_id, pull_job_id)
            else:
                raise UnsupportedPullEntity(f"Unknown pull entity {entity!r}.")
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
    client = FoundryxAutocountClient(db)
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


def _apply_stock(db, job: ImportJob, snapshot_id: str, pull_job_id: Optional[str]) -> dict:
    """AC-SC-2: re-verifies the SAME snapshot, refuses (AC-SC-2/AC-SP-1's own guard,
    re-checked here) when the FETCHED header still reports `excludedNonzeroCount > 0`,
    then runs `bulk_import_stock` for real and archives the Stock List from the FED rows
    - only once the import has committed (AC-SC-4c); a failed import archives nothing.
    `pull_job_id` is where an archive failure's warning goes (see below) - the apply
    job's own metadata is not what the review page reads."""
    client = FoundryxAutocountClient(db)
    header, rows, warnings = fetch_verified_snapshot(
        client, snapshot_id=snapshot_id, company_code=_company_code(db, job.company_id)
    )

    excluded_nonzero = header.get("excludedNonzeroCount") or 0
    if excluded_nonzero > 0:
        raise ValueError(
            f"AutoCount reports {excluded_nonzero} non-zero excluded pair(s); pull again."
        )

    company_id = str(job.company_id) if job.company_id else None
    fed_rows = classify_stock_rows(db, company_id, rows)["fed"]

    if not fed_rows:
        # HIGH (F-1b): refuse BEFORE `bulk_import_stock` ever runs - that call's own
        # "active, absent from this batch -> zeroed" sweep is company-wide, so an empty
        # batch would otherwise wipe every active warehouse's stock, not just whatever
        # this pull was about. Nothing written, nothing archived.
        raise ValueError(EMPTY_FED_REASON)

    outcome_writer = ImportOutcome(job.id)
    scope = frozenset({company_id}) if company_id else None
    with company_scope(db, scope):
        result = StockService(db).bulk_import_stock(
            fed_rows, str(job.user_id), outcome=outcome_writer,
        )
    outcome_writer.flush()

    # The archive happens only after `bulk_import_stock` has committed for real
    # (it commits internally on success) - built from the SAME fed rows the import
    # just ran, every one of them, including a row the import itself skipped.
    # Best-effort, like the manual route's own webhook step: the STOCK IMPORT is
    # what Confirm promised, and a missing/misconfigured Stock_List attachment type
    # must not turn an otherwise-successful apply into a failed job.
    try:
        import app.services.stock_list_archive_service as stock_list_archive_service

        workbook_bytes = build_stock_workbook(fed_rows)
        # D3 (small-fix track): the apply job's OWN metadata carries no `autocount_pull`
        # entity/company_code at all (it is keyed `autocount_apply`) - `download_filename`
        # only ever reads the former, which is how this used to come out
        # `autocount-pull-pull.xlsx`. A real DB lookup by `company_id` instead, the same
        # one `_preview_products`/`_preview_stock` already use for the FoundryX call.
        archive_filename = stock_list_archive_filename(_company_code(db, job.company_id))
        stock_list_archive_service.replace_latest_stock_list(
            db, file_bytes=workbook_bytes, filename=archive_filename,
            user_id=str(job.user_id),
        )
    except Exception:
        logger.warning(
            "autocount pull apply: stock import committed but the Stock List archive "
            "failed (job=%s)", job.id, exc_info=True,
        )
        _append_pull_warning(db, pull_job_id, STOCK_LIST_NOT_ARCHIVED)

    return {
        "created": result.get("created", 0),
        "updated": result.get("updated", 0),
        "skipped": result.get("skipped", 0),
        "system_adjusted_to_zero": result.get("system_adjusted_to_zero", 0),
        "errors": result.get("errors", []),
    }


def _append_pull_warning(db, pull_job_id: Optional[str], code: str) -> None:
    """Appends `code` to the PULL job's own `metadata.autocount_pull.warnings` - the
    row `serialize()`/the review page reads, never the apply job's own metadata.
    Best-effort: a failure here must not turn the apply job itself into a failure
    over and above the thing it is already warning about."""
    if not pull_job_id:
        return
    try:
        pull_job = db.query(ImportJob).filter(ImportJob.id == pull_job_id).first()
        if pull_job is None:
            return
        meta = dict(pull_job.job_metadata or {})
        pull = dict(meta.get("autocount_pull") or {})
        warnings = list(pull.get("warnings") or [])
        if code not in warnings:
            warnings.append(code)
        pull["warnings"] = warnings
        meta["autocount_pull"] = pull
        pull_job.job_metadata = meta
        pull_job.updated_at = datetime.utcnow()
        db.commit()
    except Exception:
        logger.warning(
            "autocount pull apply: could not append warning %r to pull job %s",
            code, pull_job_id, exc_info=True,
        )


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
    client = FoundryxAutocountClient(db)
    header, rows, warnings = fetch_verified_snapshot(
        client, snapshot_id=pull.get("snapshot_id"), company_code=pull.get("company_code")
    )
    # Always a list, never left absent, once a preview has run - "absent or empty on a
    # match" is satisfied by the empty-list case; the mismatch case names the code.
    pull["warnings"] = warnings

    company_id = str(job.company_id) if job.company_id else None
    job_id = str(job.job_id)
    # Publish the total the moment the sheet is read (same reason the customer/GRN
    # importers do it in `import_tasks.py`) - without it the review page shows 0/0 for
    # the whole run, which reads as stuck.
    _publish_preview_progress(job_id, 0, len(rows))
    ingest = MasterIngestService(db, company_id=company_id)
    result = ingest.ingest(
        "products",
        rows,
        dry_run=True,
        on_progress=lambda processed, total: _publish_preview_progress(job_id, processed, total),
    )

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


def _preview_stock(db, job: ImportJob, pull: dict) -> dict:
    """AC-SP-1..5: classify every row, `validate_only` the FED ones, write the not-
    applied / would-skip / negative-pair / quantity-change rows, store all eight
    counters, and set `confirm_blocked_reason` when the header itself says Confirm
    cannot run yet - the preview still finishes in `review` either way (AC-SP-1)."""
    client = FoundryxAutocountClient(db)
    header, rows, warnings = fetch_verified_snapshot(
        client, snapshot_id=pull.get("snapshot_id"), company_code=pull.get("company_code")
    )
    pull["warnings"] = warnings

    company_id = str(job.company_id) if job.company_id else None
    classification = classify_stock_rows(db, company_id, rows)
    fed_rows = classification["fed"]
    inactive_rows = classification["inactive"]
    unknown_rows = classification["unknown"]

    outcome_writer = ImportOutcome(job.id)
    scope = frozenset({company_id}) if company_id else None
    with company_scope(db, scope):
        # `outcome_writer` passed straight in: `bulk_import_stock`'s own PRODUCT_NOT_FOUND
        # skip fires unconditionally (before the `validate_only` branch), so the pull's
        # own "skipped, product not found" rows come from the ONE place that already
        # knows how to say that, never a second re-derivation here.
        validate_result = StockService(db).bulk_import_stock(
            fed_rows, str(job.user_id), validate_only=True, outcome=outcome_writer,
        )

    current_by_pair = _current_stock_by_pair(db, company_id, fed_rows)
    qty_changes = 0
    for row in fed_rows:
        current = current_by_pair.get(_stock_pair_key(row))
        if current is None:
            # No existing stock row for this pair - a brand new pair, nothing to
            # diff against, and the eight counters name no slot for it (AC-SP-4).
            continue
        incoming = row.get("On Hand Qty")
        if current == incoming:
            continue
        qty_changes += 1
        outcome_writer.updated(
            message=(
                f"Quantity change: {row.get('Item Code')} at {row.get('Location')}: "
                f"{current} -> {incoming}"
            ),
            value=row.get("Item Code"),
            identity={
                "item_code": row.get("Item Code"), "location": row.get("Location"),
                "current": current, "incoming": incoming,
            },
        )

    for row in inactive_rows:
        outcome_writer.skip(
            code=codes.AUTOCOUNT_NOT_APPLIED_INACTIVE,
            message=(
                f"Not applied, inactive warehouse: {row.get('Item Code')} at "
                f"{row.get('Location')}"
            ),
            value=row.get("Item Code"),
            identity={"item_code": row.get("Item Code"), "location": row.get("Location")},
        )
    for row in unknown_rows:
        outcome_writer.skip(
            code=codes.AUTOCOUNT_NOT_APPLIED_UNKNOWN,
            message=(
                f"Not applied, unknown location: {row.get('Item Code')} at {row.get('Location')}"
            ),
            value=row.get("Item Code"),
            identity={"item_code": row.get("Item Code"), "location": row.get("Location")},
        )

    # Header-only, display: FoundryX's own record of a negative on-hand pair. Never
    # reaches `bulk_import_stock` - it never rode in `rows` to begin with.
    negative_pairs = header.get("negativePairList") or []
    for entry in negative_pairs:
        item_code = entry.get("item_code")
        location = entry.get("location_code")
        outcome_writer.skip(
            code=codes.AUTOCOUNT_NEGATIVE,
            message=(
                f"AutoCount reports a negative on-hand quantity: {item_code} at "
                f"{location} ({entry.get('qty')})"
            ),
            value=item_code,
            identity={"item_code": item_code, "location": location, "qty": entry.get("qty")},
        )

    outcome_writer.flush()
    # B3: stock has no per-record hook to report mid-run progress through (unlike
    # `MasterIngestService.ingest`'s `on_progress`) - set once at the end, so the review
    # page's spinner still resolves to a definite total rather than staying bare forever.
    _publish_preview_progress(str(job.job_id), len(rows), len(rows))

    summary = validate_result.get("summary") or {}
    # `would_system_adjust_to_zero` is `bulk_import_stock`'s own count of every active-
    # warehouse stock row NOT in this batch (EMPTY_FED_REASON's own point, F-1) - with
    # an empty FED batch that is every active-warehouse row in the company, a number
    # the review screen must never surface: Confirm is already blocked below, so
    # nothing will ever be applied and nothing will actually be set to zero.
    set_to_zero = summary.get("would_system_adjust_to_zero", 0) if fed_rows else 0
    counts = {
        "received": len(rows),
        "fed": len(fed_rows),
        "not_applied_inactive": len(inactive_rows),
        "not_applied_unknown": len(unknown_rows),
        "qty_changes": qty_changes,
        "set_to_zero": set_to_zero,
        "skipped_product_not_found": outcome_writer.count_of(codes.PRODUCT_NOT_FOUND),
        "negative_in_autocount": len(negative_pairs),
    }

    excluded_nonzero = header.get("excludedNonzeroCount") or 0
    if not fed_rows:
        # HIGH (F-1a): no pulled row matched an active warehouse at all - Confirm must
        # never reach `_apply_stock`'s own empty-batch guard for real, so the preview
        # blocks it here too. Takes priority over the excluded-pair message below: an
        # empty batch is the more dangerous state (see `EMPTY_FED_REASON`).
        pull["confirm_blocked_reason"] = EMPTY_FED_REASON
    elif excluded_nonzero > 0:
        pull["confirm_blocked_reason"] = (
            f"AutoCount reports {excluded_nonzero} non-zero excluded pair(s); pull again."
        )
    else:
        pull["confirm_blocked_reason"] = None
    return counts


def _stock_pair_key(row: dict) -> tuple[str, str]:
    return (
        str(row.get("Item Code") or "").strip().upper(),
        str(row.get("Location") or "").strip().upper(),
    )


def _current_stock_by_pair(db, company_id: Optional[str], fed_rows: list[dict]) -> dict:
    """AC-SP-4: ONE query of current on-hand for the FED pairs, keyed the same way
    `_stock_pair_key` reads a fed row - so a preview never queries per row."""
    if not fed_rows or not company_id:
        return {}
    item_codes = list({
        str(r.get("Item Code") or "").strip().upper() for r in fed_rows if r.get("Item Code")
    })
    locations = list({
        str(r.get("Location") or "").strip().upper() for r in fed_rows if r.get("Location")
    })
    if not item_codes or not locations:
        return {}
    rows = db.execute(
        text(
            "SELECT p.product_code, w.warehouse_code, s.quantity_on_hand "
            "FROM stock s "
            "JOIN products p ON p.id = s.product_id "
            "JOIN warehouses w ON w.id = s.warehouse_id "
            "WHERE p.company_id = :cid AND w.company_id = :cid "
            "AND upper(btrim(p.product_code)) = ANY(:codes) "
            "AND upper(btrim(w.warehouse_code)) = ANY(:locs)"
        ),
        {"cid": company_id, "codes": item_codes, "locs": locations},
    ).mappings().all()
    return {
        (str(r["product_code"]).strip().upper(), str(r["warehouse_code"]).strip().upper()):
            r["quantity_on_hand"]
        for r in rows
    }


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
