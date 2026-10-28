"""Build one walkthrough stop's panorama on the worker.

Same shape as ``flyer_read_tasks.read_flyer``: its own session, the row is the
record (every outcome ends as ``done`` or ``failed`` on the stop), the staged
uploads are discarded in ``finally`` whatever happened, and nothing re-raises
into the queue.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.database import SessionLocal
from app.models.dealer_kit import WalkthroughStop
from app.services.company_scope import get_company_scope, set_company_scope
from app.services.dealer_kit import walkthrough_service as svc
from app.services.dealer_kit.panorama import PanoramaError, build_panorama

logger = logging.getLogger(__name__)


def _load(db, stop_id: str) -> Optional[WalkthroughStop]:
    return db.query(WalkthroughStop).filter(WalkthroughStop.id == stop_id).first()


def build_stop(stop_id: str, staged: list[list[str]], *, _db=None) -> dict:
    """``staged`` is ``[provider, key, filename]`` per upload, in upload order.

    ``_db`` is a test seam: a suite lends its rolled-back session and gets its
    company scope back afterwards.
    """
    from app.services import storage_router

    db = _db if _db is not None else SessionLocal()
    owns_session = _db is None
    previous_scope = get_company_scope(db)
    try:
        # A stop has no company; the worker has no request scope. Load unscoped,
        # then narrow to the parent's company before writing anything.
        set_company_scope(db, None)
        stop = _load(db, stop_id)
        if stop is None:
            return {"stop_id": stop_id, "status": "gone"}
        company_id = stop.walkthrough.company_id
        if company_id:
            set_company_scope(db, frozenset({company_id}))

        try:
            sources = [
                (filename, storage_router.get_backend(provider).download_file(key))
                for provider, key, filename in staged
            ]
            panorama = build_panorama(sources)
            stop = _load(db, stop_id)
            if stop is None:
                # Deleted while it was being built: nothing to write onto.
                return {"stop_id": stop_id, "status": "gone"}
            svc.complete_stop(db, stop, panorama)
            return {"stop_id": stop_id, "status": svc.StopStatus.DONE}
        except PanoramaError as exc:
            return _mark_failed(db, stop_id, str(exc))
        except Exception as exc:  # noqa: BLE001 - the row records it, the queue survives
            logger.exception("build_stop: stop %s failed", stop_id)
            return _mark_failed(db, stop_id, f"This stop could not be built: {exc}")
    finally:
        svc.discard_staged(staged)
        if owns_session:
            db.close()
        else:
            set_company_scope(db, previous_scope)


def _mark_failed(db, stop_id: str, message: str) -> dict:
    db.rollback()
    stop = _load(db, stop_id)
    if stop is None:
        return {"stop_id": stop_id, "status": "gone"}
    svc.fail_stop(db, stop, message=message)
    return {"stop_id": stop_id, "status": svc.StopStatus.FAILED, "error": message}
