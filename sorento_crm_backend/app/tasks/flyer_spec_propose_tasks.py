"""Read a flyer for specifications on the worker, and write the answer onto its batch.

The request that asked for this returned 202 seconds ago and is long gone, so **the
batch row is the record**: every outcome ends as `proposed` or `failed` on
`product_spec_flyer_batches`, with the reason in words a merchandiser can read. It
never re-raises - a poisoned queue helps nobody, and an RQ failure registry is not a
surface anybody reviewing a flyer can reach.

Shape mirrors `flyer_read_tasks.read_flyer`: its own session, the company scope turned
off to find the row and then narrowed to the row's own company, one delegation to the
service, and a `finally` that always puts back what it borrowed.

It runs on the SAME queue as the read (`flyer_read`), so there is no new worker
configuration. The worker has no reload - restart it after editing this file.
"""
from __future__ import annotations

import logging

from app.database import SessionLocal
from app.models.product_spec import ProductSpecFlyerBatch
from app.services.company_scope import get_company_scope, set_company_scope
from app.services.product_spec_flyer_ingest import run_propose

logger = logging.getLogger(__name__)


def propose_specs_for_flyer(batch_id: str, *, _db=None) -> dict:
    """Compute one batch of flyer spec proposals.

    `_db` is a test seam and nothing else: a suite passes its own rolled-back Postgres
    session so the whole POST -> 202 -> job -> GET journey can be walked without Redis
    and without a worker. When it is supplied the session is neither opened nor closed
    here, and the company scope it arrived with is put back afterwards, so a test's next
    statement sees the session it lent.

    The scope is turned OFF to load the batch - the worker has no request to scope by,
    and a batch it cannot see is a batch it would fail for the wrong reason - and then
    narrowed to the batch's own company, so every read the pass makes (the reading, the
    products, their spec rows) lands where the flyer lives.
    """
    db = _db if _db is not None else SessionLocal()
    owns_session = _db is None
    previous_scope = get_company_scope(db)

    try:
        set_company_scope(db, None)
        batch = (
            db.query(ProductSpecFlyerBatch)
            .filter(ProductSpecFlyerBatch.id == batch_id)
            .first()
        )
        if batch is None:
            logger.info("propose_specs_for_flyer: batch %s is gone; nothing to do", batch_id)
            return {"batch_id": str(batch_id), "status": "gone"}

        if batch.company_id:
            set_company_scope(db, frozenset({batch.company_id}))

        return run_propose(db, batch_id)

    except Exception as exc:  # noqa: BLE001 - loading or scoping itself failed
        # The row still says `proposing` and no other job will ever finish it, so it
        # gets the same words the service's own failure arm writes.
        logger.exception("propose_specs_for_flyer: batch %s could not be started", batch_id)
        from app.services.product_spec_flyer_ingest import _mark_failed

        return _mark_failed(
            db, batch_id, f"The flyer could not be read for specifications: {exc}"
        )
    finally:
        if owns_session:
            db.close()
        else:
            set_company_scope(db, previous_scope)
