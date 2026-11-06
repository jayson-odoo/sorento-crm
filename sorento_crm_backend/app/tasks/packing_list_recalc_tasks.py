"""RQ task: recompute one packing list after one of its inputs changed.

Enqueued by `app.services.scm.packing_list_recalc.dispatch_recalc` on the `scm_recalc`
queue (job id `pl-recalc-<shipment id>`). Runs on an all-companies session as the
`worker` actor; never raises, a failure is logged and the hourly open-container sweep
retries it.

WORKER RESTART: editing this module requires restarting the RQ worker (no reload).
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def recalc_packing_list_job(shipment_id: str) -> bool:
    from app.database import SessionLocal
    from app.models.base import set_company_scope
    from app.services.scm.packing_list_recalc import recalc_packing_list

    db = SessionLocal()
    try:
        set_company_scope(db, None)
        return recalc_packing_list(db, shipment_id, trigger="input_change")
    finally:
        db.close()
