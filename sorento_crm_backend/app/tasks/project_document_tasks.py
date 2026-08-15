"""Background extraction of uploaded project documents (customer PO, delivery schedule).

Off the request path because reading ten scanned pages takes a couple of minutes, and
an upload that holds the browser open for two minutes is an upload people stop doing.
The API stores the document, creates the version row with
``extraction_state='queued'``, and enqueues one of these.

Both tasks follow the same contract with the UI: the version row always ends in a
terminal state with a readable reason. A task that raised into RQ's failed registry
would leave a version stuck on "queued" forever, which reads to the user as a hung
system rather than a document that needs finishing by hand.

**That contract holds only while this process is alive.** The failure is written in an
``except`` block, and an ``except`` block does not run when the process is KILLED -
SIGTERM from a deploy, the RQ job timeout, an out-of-memory kill, a native crash inside
page rendering. Measured on 2026-08-08: a work-horse killed with signal 15 left a PO
version on ``running`` for ever, with the UI showing a progress bar for work that had
stopped. Nothing inside a dying process can report its own death, so the reporting lives
outside it, in ``app.services.project_extraction_recovery_service``, which reconciles a
non-terminal row against what RQ knows about the job whose id the row records.

Reminder for local dev: RQ tasks are NOT reloaded. Restart the worker after editing
this file or the services it calls.
"""
import logging

from app.database import SessionLocal
from app.services.company_scope import set_company_scope

logger = logging.getLogger(__name__)

# Its own queue, not `imports`.
#
# Two reasons, and the second is the one that bites. Extraction is minutes of waiting
# on a remote model, so parking it behind a spreadsheet import (or the reverse) makes
# both feel broken. More importantly, every checkout of this repository shares one
# Redis, so a worker started from a different working tree happily claims a job whose
# task module it does not have and fails it on import. A dedicated queue means only a
# worker that was started for THIS code can take these jobs.
PROJECT_DOCS_QUEUE = "project_docs"


def enqueue_po_extraction(po_version_id: str):
    """Queue a PO version for reading. Call this rather than enqueueing by hand, so
    the queue name lives in one place."""
    from app.services.queue_service import enqueue_job

    return enqueue_job(
        extract_po_version, po_version_id, queue_name=PROJECT_DOCS_QUEUE, job_timeout=1800
    )


def enqueue_schedule_extraction(schedule_version_id: str):
    """Queue a delivery-schedule version for reading."""
    from app.services.queue_service import enqueue_job

    return enqueue_job(
        extract_schedule_version,
        schedule_version_id,
        queue_name=PROJECT_DOCS_QUEUE,
        job_timeout=1800,
    )


def extract_po_version(po_version_id: str) -> dict:
    """Read a customer PO version and persist its lines and annotations."""
    from app.models.project_so import ProjectPOVersion

    db = SessionLocal()
    # Worker sessions start at the fail-closed UNSET scope. The version's own company
    # is on the row, so run system-wide and let the service scope by what it loads.
    set_company_scope(db, None)
    try:
        from app.services.project_po_extraction_service import ProjectPOExtractionService

        return ProjectPOExtractionService(db).run_extraction(po_version_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("PO extraction failed for version %s", po_version_id)
        _mark_failed(db, ProjectPOVersion, po_version_id, exc)
        return {"status": "failed", "error": str(exc)[:300]}
    finally:
        db.close()


def extract_schedule_version(schedule_version_id: str) -> dict:
    """Read a delivery-schedule version and persist its phases, products and cells."""
    from app.models.project_so import DeliveryScheduleVersion

    db = SessionLocal()
    set_company_scope(db, None)
    try:
        from app.services.project_schedule_service import ProjectScheduleService

        return ProjectScheduleService(db).run_extraction(schedule_version_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Schedule extraction failed for version %s", schedule_version_id)
        _mark_failed(db, DeliveryScheduleVersion, schedule_version_id, exc)
        return {"status": "failed", "error": str(exc)[:300]}
    finally:
        db.close()


def _mark_failed(db, model, row_id: str, exc: Exception) -> None:
    """Last-resort state write, so nothing is left showing "queued" after a crash.

    Takes the MODEL, not a table name. Both of these tables live in the `projects`
    schema now (ADR-0011), so a raw ``UPDATE project_po_versions`` would need
    qualifying by hand, and a hardcoded ``projects.`` reaches past a test fixture's
    scratch schema into the real one. The mapped class carries its own schema and
    honours the fixture's translation.
    """
    try:
        db.rollback()
        db.query(model).filter(model.id == row_id).update(
            {
                model.extraction_state: "failed",
                model.extraction_error: str(exc)[:500],
            },
            synchronize_session=False,
        )
        db.commit()
    except Exception:  # noqa: BLE001
        # Qualified, so the log line says which `purchase_orders` (ADR-0011).
        logger.exception("could not mark %s %s as failed", model.__table__.fullname, row_id)
