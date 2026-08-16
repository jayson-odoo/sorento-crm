"""Read a flyer on the worker, and write the answer onto its row.

The request that asked for this returned 202 seconds ago and is long gone, so
there is nobody left to raise at. **The row is the record**: every outcome this
job can reach ends as ``done`` or ``failed`` on ``dealer_kit.flyer_reading``,
with the reason in the words the request used to say. It never re-raises - a
poisoned queue helps nobody, and an RQ failure registry is not a surface any
designer can read.

Shape mirrors ``dealer_kit_export_tasks.generate_catalogue_pdf``: its own
session, one try/except that marks the row, a finally that always cleans up, and
a small dict back for the operator reading the job log.

**Extraction runs here, in the RQ work-horse.** That is a forked process on the
worker with no event loop of its own, so nothing about ``run_in_threadpool``
applies - and the 18 seconds the real flyer costs are 18 seconds nobody is
waiting on.

**No report recompute.** The brief asked for one; there is nothing to recompute
INTO. The report is never stored (a binding design of this module - see
``flyer_reading_service``), so the review screen computes it on the GET, which
measures 0.9 seconds against the real flyer's 998 codes on a plain ``def``
route. Recorded as a deliberate deviation in the plan rather than left as a
silent omission.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.database import SessionLocal
from app.models.dealer_kit import FlyerReadingRecord
from app.services.company_scope import get_company_scope, set_company_scope
from app.services.dealer_kit import flyer_reading_service as svc
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)


def _load(db, reading_id: str) -> Optional[FlyerReadingRecord]:
    return (
        db.query(FlyerReadingRecord).filter(FlyerReadingRecord.id == reading_id).first()
    )


def _staged_bytes(provider: Optional[str], key: str) -> bytes:
    """The upload's parked bytes.

    ``storage_router`` is reached through the module at call time, never by a
    name bound at import, so ``tests/_fake_storage.patch_storage`` reaches this
    too. Same rule as the service's staging half.
    """
    from app.services import storage_router

    try:
        return storage_router.get_backend(provider).download_file(key)
    except Exception as exc:  # noqa: BLE001 - the bucket's problem, said in words
        logger.warning("Staged flyer %s could not be fetched: %s", key, exc)
        raise AppException(
            status_code=502,
            message=(
                "That file could not be fetched from storage. "
                "Try again, or upload the flyer from your computer."
            ),
            code="FLYER_SOURCE_UNREADABLE",
        ) from exc


def read_flyer(
    reading_id: str,
    staged_provider: Optional[str] = None,
    staged_key: Optional[str] = None,
    *,
    _db=None,
) -> dict:
    """Fetch the bytes behind a reading, extract them, and finish the row.

    ``_db`` is a test seam and nothing else: a suite passes its own rolled-back
    Postgres session so the whole POST -> 202 -> read -> GET journey can be
    walked without Redis and without a worker. When it is supplied the session
    is neither opened nor closed here, and the company scope it arrived with is
    put back afterwards, so a test's next statement sees the session it lent.

    The order matters:

    1. Load the row with the scope OFF. The worker has no request to scope by,
       and a reading it cannot see is a reading it would mark failed for the
       wrong reason.
    2. Narrow to the reading's OWN company before anything else. This is what
       makes the attachment lookup and the banner inserts land where the reading
       lives - a scope of "everything" cannot stamp an owned row at all, so
       skipping this would fail every banner insert.
    3. Fetch the bytes. Staged object for an upload, the attachment for a
       library read, with the same refusals the request would have raised.
    4. RE-LOAD the row before writing. The fetch takes seconds and the designer
       may have deleted the reading in the meantime; writing banners and a
       report onto a row that is gone is the one way this job can leave litter
       behind (AC-J3.4).
    5. Complete it, or mark it failed with the reason.

    The staged object is discarded in ``finally``, on success AND on failure
    (AC-J3.3). It is a copy of a file the designer already holds; keeping it for
    a failed read buys nothing and costs a bucket nobody audits.
    """
    db = _db if _db is not None else SessionLocal()
    owns_session = _db is None

    previous_scope = get_company_scope(db)
    staged = bool(staged_key)

    try:
        set_company_scope(db, None)
        record = _load(db, reading_id)
        if record is None:
            logger.info("read_flyer: reading %s is gone; nothing to do", reading_id)
            return {"reading_id": reading_id, "status": "gone"}

        if record.company_id:
            set_company_scope(db, frozenset({record.company_id}))

        source_attachment_id = record.source_attachment_id
        filename = record.filename

        try:
            if staged_key:
                data = _staged_bytes(staged_provider, staged_key)
                svc.assert_within_limit(len(data))
            elif source_attachment_id:
                attachment = svc.assert_attachment_readable(db, str(source_attachment_id))
                data = svc.attachment_bytes(db, attachment)
            else:
                # Neither a staged copy nor a source row: the enqueue that wrote
                # this is broken, and saying so beats a generic failure.
                raise AppException(
                    status_code=422,
                    message=(
                        "That flyer has no stored copy the system can read. "
                        "Upload the flyer from your computer instead."
                    ),
                    code="FLYER_SOURCE_MISSING",
                )

            record = _load(db, reading_id)
            if record is None:
                logger.info(
                    "read_flyer: reading %s was deleted while it was being read",
                    reading_id,
                )
                return {"reading_id": reading_id, "status": "gone"}

            svc.complete_reading(db, record, data=data, filename=filename)
            logger.info(
                "read_flyer: reading %s done (%d bytes, %d pages)",
                reading_id,
                len(data),
                svc.page_count(record),
            )
            return {"reading_id": reading_id, "status": svc.ReadingStatus.DONE}

        except AppException as exc:
            # A refusal the designer has to be able to read: not a PDF, password
            # protected, over the ceiling, storage unreachable. Same words the
            # synchronous route used to answer with.
            # NOT ``exc.message``: an AppException carries its words in
            # ``detail["message"]``, and reading the attribute that is not there
            # would raise inside the handler for the refusal - leaving the row
            # `processing` forever with nothing said about why.
            message = svc.refusal_message(exc)
            logger.warning("read_flyer: reading %s refused: %s", reading_id, message)
            return _mark_failed(db, reading_id, message)
        except Exception as exc:  # noqa: BLE001 - the row records it, the queue survives
            logger.exception("read_flyer: reading %s failed", reading_id)
            return _mark_failed(db, reading_id, f"The flyer could not be read: {exc}")

    except Exception as exc:  # noqa: BLE001 - loading or scoping itself failed
        # The row still says ``processing`` and no other job will ever finish
        # it, so it gets the same words the inner generic arm writes. If the row
        # is what could not be loaded, ``_mark_failed`` finds nothing and says
        # so, which is the honest answer.
        logger.exception("read_flyer: reading %s could not be started", reading_id)
        return _mark_failed(db, reading_id, f"The flyer could not be read: {exc}")
    finally:
        if staged:
            svc.discard_staged(staged_provider, staged_key)
        if owns_session:
            db.close()
        else:
            set_company_scope(db, previous_scope)


def _mark_failed(db, reading_id: str, message: str) -> dict:
    """Write the refusal onto the row, whatever state the attempt left behind.

    The rollback is first and it is load-bearing: a failure part way through
    ``complete_reading`` can leave half-written banner rows in the session, and
    committing the status on top of them would persist assets belonging to a
    reading that has none. Rolling back drops them; the objects those rows had
    already PUT are the bounded orphan family ``_store_banners`` documents.

    A row that vanished mid-read is not an error here. The designer deleted it,
    which is an answer, and there is nothing left to write to (AC-J3.4).
    """
    try:
        db.rollback()
    except Exception:  # noqa: BLE001
        logger.exception("read_flyer: rollback before failing %s did not work", reading_id)

    record = _load(db, reading_id)
    if record is None:
        return {"reading_id": reading_id, "status": "gone"}

    try:
        svc.fail_reading(db, record, message=message)
    except Exception:  # noqa: BLE001 - nothing left to do but say so in the log
        logger.exception("read_flyer: could not mark reading %s failed", reading_id)
    return {
        "reading_id": reading_id,
        "status": svc.ReadingStatus.FAILED,
        "error": message,
    }
