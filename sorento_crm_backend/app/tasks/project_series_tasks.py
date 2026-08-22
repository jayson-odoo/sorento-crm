"""Background task: load a products sheet onto a project series.

**Why this is not done in the request.** The client's own workbook is 9.2 MB and takes
seconds to open. The upload route was ``async def``, so that parse ran ON the event loop and
blocked EVERY other request in the process for its duration, not just the one waiting for it.
The person who uploaded saw a button that said "Loading..." and no way to tell a slow read
from a dead one.

The job writes its answer into ``import_jobs.result``, which is the shape the existing
``GET /system/jobs/{job_id}/status`` already returns, so the browser polls one endpoint it
already knows and needs no new status route.

The report stored here is the SAME dict the synchronous paste path returns
(``apply_series_product_codes``), so the screen renders one shape whichever way the codes
arrived. In particular ``unmatched_codes`` survives: a third of a real sheet misses, and that
list is the entire value of the import.
"""

import logging
from typing import Optional

from app.database import SessionLocal
from app.models.job import ImportJob
from app.models.projects import ProjectSeries
from app.services.company_scope import set_company_scope
from app.services.job_service import JobService

logger = logging.getLogger(__name__)

JOB_TYPE = "project_series_import"


def _apply_job_scope(db, db_job_id: Optional[str]) -> None:
    """Re-establish the uploader's company scope on the worker session.

    Every ``SessionLocal()`` starts UNSET and fail-closed, so without this the series read
    below returns nothing and the job reports "series not found" for a series that plainly
    exists. Mirrors ``import_tasks._apply_import_job_scope``; kept as its own copy rather
    than imported because that module pulls in half the procurement domain at import time.
    """
    company_id = None
    if db_job_id:
        try:
            job = db.query(ImportJob).filter(ImportJob.id == db_job_id).first()
            company_id = getattr(job, "company_id", None) if job else None
        except Exception:  # noqa: BLE001
            company_id = None
    if company_id:
        set_company_scope(db, frozenset({str(company_id)}))
    else:
        logger.warning(
            "Series import job %s has no company snapshot; running system-scoped", db_job_id
        )
        set_company_scope(db, None)


def process_series_product_import(
    db_job_id: str,
    file_data: bytes,
    filename: str,
    series_id: str,
    mode: str,
    user_id: str,
):
    """Read the sheet and apply it to the series. Runs on the imports queue."""
    from rq import get_current_job

    from app.services import project_pricing_service as pricing
    from app.services import project_series_import_service as sheets

    db = SessionLocal()
    _apply_job_scope(db, db_job_id)
    job_service = JobService(db)
    rq_job = get_current_job()
    rq_job_id = rq_job.id if rq_job else None

    job = job_service.get_job_by_db_id(db_job_id) if db_job_id else None
    if not job and rq_job_id:
        job = job_service.get_job(rq_job_id)
    if not job:
        logger.error(
            "Series import job not found: db_job_id=%s, rq_job_id=%s", db_job_id, rq_job_id
        )
        db.close()
        return

    job_id_str = str(job.job_id)
    try:
        job_service.start_job(job_id_str)

        series = (
            db.query(ProjectSeries).filter(ProjectSeries.id == str(series_id)).first()
        )
        if series is None:
            job_service.fail_job(job_id_str, "That series no longer exists.")
            return

        rows = sheets.extract_series_rows(file_data, filename=filename or "")
        report = pricing.apply_series_product_codes(
            db, series=series, codes=rows, mode=mode
        )
        db.commit()

        # `total`/`processed` drive the percentage the status endpoint returns. Codes are the
        # only unit of work here that means anything to the person watching - "92 of 141" is
        # a sentence they can check against their spreadsheet.
        submitted = int(report.get("submitted") or 0)
        job_service.complete_job(
            job_id_str,
            result=_json_safe(report),
            successful_rows=int(report.get("matched_codes") or 0),
            skipped_rows=len(report.get("unmatched_codes") or []),
            processed_rows=submitted,
            total_rows=submitted,
        )
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        # `AppException` carries the sentence written for the user (an empty file, an
        # unreadable workbook, a mode nobody supports); anything else is ours to own.
        message = getattr(exc, "message", None) or str(exc)
        logger.exception("Series import job %s failed", job_id_str)
        job_service.fail_job(job_id_str, message[:500])
    finally:
        db.close()


def _json_safe(value):
    """Decimals and UUIDs do not survive a JSONB write. Strings all the way down.

    The report carries `selling_price`-shaped Decimals only indirectly today, but the
    codes are user text and the ids are UUIDs, and a job whose result cannot be written is
    a job that reports success and shows the user nothing.
    """
    from decimal import Decimal
    from uuid import UUID

    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    return value
