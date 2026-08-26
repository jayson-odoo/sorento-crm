"""Background task for report workbook exports (My Downloads).

Same shape as the other exports in app/tasks/export_tasks.py: the API creates a
UserDownload row in 'pending' and enqueues this; the task renders, uploads through the
storage router and flips the row to 'ready' or 'failed'. Never raises into RQ's failed
registry - a row stuck in 'processing' tells the user nothing.

The export path runs the engine UNCAPPED (``run_workbook`` never caps): the caps exist to
keep a runaway run off the request path, and this is not the request path. What comes back
is the SUMMARY plus one detail table per month of the period, which is the shape the client
keeps by hand.

RQ has no reload: restart the worker after editing this file.
"""
import logging
from typing import Optional

from app.database import SessionLocal
from app.services.company_scope import set_company_scope
from app.services.download_service import DownloadService
from app.services.storage_router import default_provider, get_backend
# The other exports' rollback-then-mark-failed rule, not a second copy of it: when the
# thing that failed was the DATABASE, psycopg2 leaves the transaction aborted and
# `mark_failed` would raise too, leaving the row spinning in 'processing' for good.
from app.tasks.export_tasks import _record_failure

logger = logging.getLogger(__name__)

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def generate_report_xlsx(
    download_id: str,
    key: str,
    params: dict,
    view: Optional[dict],
    user_id: str,
) -> dict:
    """Render a report to a workbook, store it, and update the download row.

    The session runs at the all-companies scope, which is correct for every dataset
    declaring ``scope="none"`` (the only kind that exists today). A ``scope="company"``
    dataset must first snapshot the ENQUEUER's active company into this signature - the
    worker has no request to resolve one from, and the fail-closed UNSET scope would
    otherwise return nothing at all.
    """
    from app.schemas.report import ReportViewConfig
    from app.services.reports import engine, registry as reg
    from app.services.reports.xlsx_renderer import render_workbook

    db = SessionLocal()
    set_company_scope(db, None)
    svc = DownloadService(db)
    try:
        svc.mark_processing(download_id)

        definition = reg.get(key)
        if definition is None:
            raise ValueError(f"Unknown report '{key}'")

        config = ReportViewConfig.model_validate(view) if view else engine.view_config(definition)
        data = engine.run_workbook(db, definition, params or {}, config)
        content = render_workbook(definition, data)

        # The route already named the file from the period the user asked for; re-deriving
        # it here would be a second place for that name to be decided, and to drift.
        row = svc.get(download_id)
        filename = (row.filename if row else None) or f"{definition.key}.xlsx"

        provider = default_provider()
        backend = get_backend(provider)
        stored_key, _signed = backend.upload_file(
            file_content=content,
            file_path=f"exports/report-xlsx/{download_id}/{filename}",
            content_type=_XLSX_MIME,
        )

        svc.mark_ready(
            download_id,
            storage_provider=provider,
            storage_key=stored_key,
            filename=filename,
        )
        logger.info(
            "generate_report_xlsx: download %s ready (%s, %d bytes)",
            download_id,
            key,
            len(content),
        )
        return {"download_id": download_id, "status": "ready", "bytes": len(content)}
    except Exception as e:  # noqa: BLE001 - mark failed, never poison the queue
        logger.exception("generate_report_xlsx failed for download %s", download_id)
        _record_failure(db, svc, download_id, e, "generate_report_xlsx")
        return {"download_id": download_id, "status": "failed", "error": str(e)}
    finally:
        db.close()
