"""RQ task wrapping the SCM M3 reorder run job.

Enqueued by ``reorder_run_service.create_run`` on the ``imports`` queue (drained by
the dedicated worker container). The task creates its own DB session inside the RQ
work-horse and drives ``run_reorder``, which records success/failure on the run row
and NEVER raises — so a broken run never crashes the worker.

WORKER RESTART: editing this module (or ``reorder_run_service``) requires restarting
the RQ worker — it has NO reload. On macOS run it with
``OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES``.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def run_reorder_job(run_id: str) -> dict:
    """RQ entry point: run the reorder planning job for ``run_id``."""
    from app.services.scm.reorder_run_service import run_reorder

    log.info("run_reorder_job: starting reorder run %s", run_id)
    result = run_reorder(run_id)
    log.info("run_reorder_job: run %s finished status=%s", run_id, result.get("status"))
    return result
