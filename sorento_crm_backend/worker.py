#!/usr/bin/env python
"""RQ worker + APScheduler combined.

Single process owns both queue draining (`imports`, `respond_io`) and cron ticks
fired by `app.scheduler.task_scheduler`. Compose runs exactly one `worker` service
so jobs and ticks are never duplicated across blue/green API containers.

Set `ENABLE_SCHEDULER=true` in the worker container; API containers leave it false.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging
from rq import Worker, Queue
from app.services.queue_service import redis_conn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _maybe_start_scheduler():
    if os.getenv("ENABLE_SCHEDULER", "false").lower() != "true":
        logger.info("APScheduler disabled (ENABLE_SCHEDULER != true)")
        return None
    try:
        from app.scheduler.task_scheduler import start_scheduler
        sched = start_scheduler()
        logger.info("APScheduler started in worker process")
        return sched
    except Exception:
        # Fail fast: this container is the single owner of all cron ticks
        # (email outbox drainer, scheduled tasks heartbeat). Running on with a
        # dead scheduler silently strands work (e.g. email_outbox rows pending
        # forever) — crash instead so `restart: unless-stopped` surfaces it.
        logger.exception("Failed to start APScheduler; exiting so the container restarts visibly")
        sys.exit(1)


if __name__ == '__main__':
    _maybe_start_scheduler()
    worker = Worker(['imports', 'respond_io'], connection=redis_conn)
    logger.info("Starting RQ worker for 'imports' and 'respond_io' queues...")
    worker.work()
