"""Read a supplier catalogue PDF on the worker (CATALOG-IMAGES).

Runs on the ``flyer_read`` queue, which the worker already listens to. The row is the record:
every outcome ends as ``ready`` or ``failed`` on ``catalogue_photo_readings``, and the task never
re-raises. A restart of the Worker is needed after editing this file (the worker has no reload).
"""
from __future__ import annotations

import logging

from app.database import SessionLocal
from app.models.catalogue_photos import CataloguePhotoReading
from app.services import catalogue_photo_service as svc
from app.services.company_scope import get_company_scope, set_company_scope
from app.services.dealer_kit.flyer_extraction import EncryptedFlyerError

logger = logging.getLogger(__name__)


def _load(db, reading_id: str):
    return db.query(CataloguePhotoReading).filter(CataloguePhotoReading.id == reading_id).first()


def process_catalogue_photo_reading(reading_id: str, *, _db=None) -> dict:
    """``_db`` is a test seam: the session is neither opened nor closed, and its scope is restored."""
    db = _db if _db is not None else SessionLocal()
    previous_scope = get_company_scope(db)
    try:
        set_company_scope(db, None)
        reading = _load(db, reading_id)
        if reading is None:
            return {"reading_id": reading_id, "status": "gone"}
        if reading.company_id:
            set_company_scope(db, frozenset({reading.company_id}))
        if reading.status != "queued":
            # A re-delivered job for a reading that already ran (or is running) does nothing.
            return {"reading_id": reading_id, "status": "skipped"}
        try:
            reading.status = "reading"
            db.commit()
            stats = svc.process_reading(db, reading)
            svc._finish_job(db, reading, result=stats if isinstance(stats, dict) else None)
            return {"reading_id": reading_id, "status": "ready"}
        except Exception as exc:  # noqa: BLE001 - the row records it, the queue survives
            db.rollback()
            logger.exception("catalogue reading %s failed", reading_id)
            # Only a message written for the user is shown; anything else is logged, never stored.
            message = (
                str(exc)
                if isinstance(exc, (svc.CatalogueReadError, EncryptedFlyerError))
                else svc.FAILED_MESSAGE
            )
            failed = _load(db, reading_id)
            if failed is not None:
                failed.status = "failed"
                failed.error = message[:1000]
                db.commit()
                svc._finish_job(db, failed, error=message)
            return {"reading_id": reading_id, "status": "failed"}
    finally:
        if _db is None:
            db.close()
        else:
            set_company_scope(db, previous_scope)
