"""Background extraction of uploaded project documents (customer PO, delivery schedule).

Off the request path because reading ten scanned pages takes a couple of minutes, and
an upload that holds the browser open for two minutes is an upload people stop doing.
The API stores the document, creates the version row with
``extraction_state='queued'``, and enqueues one of these.

Both tasks follow the same contract with the UI: the version row always ends in a
terminal state with a readable reason. A task that raised into RQ's failed registry
would leave a version stuck on "queued" forever, which reads to the user as a hung
system rather than a document that needs finishing by hand.

Reminder for local dev: RQ tasks are NOT reloaded. Restart the worker after editing
this file or the services it calls.
"""
import logging

from app.database import SessionLocal
from app.services.company_scope import set_company_scope

logger = logging.getLogger(__name__)


def extract_po_version(po_version_id: str) -> dict:
    """Read a customer PO version and persist its lines and annotations."""
    db = SessionLocal()
    # Worker sessions start at the fail-closed UNSET scope. The version's own company
    # is on the row, so run system-wide and let the service scope by what it loads.
    set_company_scope(db, None)
    try:
        from app.services.project_po_extraction_service import ProjectPOExtractionService

        return ProjectPOExtractionService(db).run_extraction(po_version_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("PO extraction failed for version %s", po_version_id)
        _mark_failed(db, "project_po_versions", po_version_id, exc)
        return {"status": "failed", "error": str(exc)[:300]}
    finally:
        db.close()


def extract_schedule_version(schedule_version_id: str) -> dict:
    """Read a delivery-schedule version and persist its phases, products and cells."""
    db = SessionLocal()
    set_company_scope(db, None)
    try:
        from app.services.project_schedule_service import ProjectScheduleService

        return ProjectScheduleService(db).run_extraction(schedule_version_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Schedule extraction failed for version %s", schedule_version_id)
        _mark_failed(db, "delivery_schedule_versions", schedule_version_id, exc)
        return {"status": "failed", "error": str(exc)[:300]}
    finally:
        db.close()


def _mark_failed(db, table: str, row_id: str, exc: Exception) -> None:
    """Last-resort state write, so nothing is left showing "queued" after a crash."""
    from sqlalchemy import text

    try:
        db.rollback()
        db.execute(
            text(
                f"UPDATE {table} SET extraction_state = 'failed', extraction_error = :err "  # noqa: S608 - table is a literal from this module
                "WHERE id = :id"
            ),
            {"err": str(exc)[:500], "id": row_id},
        )
        db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("could not mark %s %s as failed", table, row_id)
