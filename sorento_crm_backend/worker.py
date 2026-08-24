#!/usr/bin/env python
"""RQ worker + APScheduler combined.

Single process owns both queue draining (see DEFAULT_QUEUES) and cron ticks fired by
`app.scheduler.task_scheduler`. Compose runs exactly one `worker` service so jobs
and ticks are never duplicated across blue/green API containers.

Set `ENABLE_SCHEDULER=true` in the worker container; API containers leave it false.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Loaded HERE, before anything imports the storage layer, because only
# `app/main.py` did it and the worker is a separate process.
#
# The symptom is quiet and expensive: `storage_router.default_provider()` reads
# `STORAGE_DEFAULT_PROVIDER` straight from the environment, so with `.env`
# unloaded the API signed URLs against R2 while the worker signed them against
# S3. A catalogue PDF export then died in the worker on a CloudFront private key
# the deployment does not use. Compose hides it, because `env_file:` puts the
# real variables in the container environment, so it only bites bare-metal and
# local workers - the two places where somebody is trying to reproduce a bug.
try:  # pragma: no cover - import-time wiring
    from dotenv import load_dotenv as _load_dotenv

    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(_env_path):
        _load_dotenv(_env_path, override=True)
    else:
        _load_dotenv(override=True)
except ImportError:
    # A container that ships real environment variables does not need it.
    pass

import logging
from rq import Worker, Queue
from app.services.queue_service import redis_conn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ForkSafeWorker(Worker):
    """RQ worker that disposes the SQLAlchemy engine pool inside each forked
    work-horse before running the job.

    RQ forks a work-horse per job. The child inherits the parent's open DB
    sockets — and when ``ENABLE_SCHEDULER=true`` the parent's APScheduler
    threads are frequently mid-query, so a live connection is shared across the
    fork. Two processes on one libpq socket corrupts the protocol, surfacing far
    from the cause as "This result object does not return rows. It has been
    closed automatically." / "PGRES_TUPLES_OK and no message from the libpq".

    ``perform_job`` runs in the child, so disposing here gives the work-horse a
    fresh pool; ``close=False`` leaves the parent's sockets untouched.
    """

    def perform_job(self, job, queue):  # noqa: ANN001
        try:
            from app.database import engine

            engine.dispose(close=False)
        except Exception:
            logger.exception("ForkSafeWorker: engine.dispose(close=False) failed")
        return super().perform_job(job, queue)


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


# Ordered because RQ drains queues in list order.
#
# `catalogue_render` is separate on purpose: a Chromium render is slow and
# memory-hungry, and sharing the imports queue means one catalogue PDF blocks
# every Excel upload behind it. `flyer_read` is separate for the same reason and
# is listed LAST: a 20 to 60 second PyMuPDF extraction should not sit in front of
# every Excel import. `project_docs` (quotation PDF and Excel rendering) sits
# between them: slower than an import, faster than a flyer read.
#
# `media` drains the chatbot media extraction jobs. The /external/media endpoint
# enqueues and then AWAITS the job, so a worker not draining this queue does not
# merely delay the work - every media turn waits out media_sync_wait_seconds and
# returns `pending`.
#
# `notifications` drains EVERY notification delivery - email, web push, WhatsApp
# (notification_service enqueues them all with queue_name="notifications"). It
# was missing from this list, so those jobs enqueued and nothing ever ran them:
# 86 notification_deliveries rows sat `pending` in production, 32 in one month.
# The failure is silent by construction - the enqueue succeeds and no exception
# is raised anywhere - so tests/test_worker_queue_defaults.py pins it.
#
# PRODUCTION: the compose file on the server is hand-edited and gitignored. If it
# pins WORKER_QUEUES explicitly, a queue added here does NOT reach production
# until that file is edited too. Adding a queue is therefore a two-place change.
DEFAULT_QUEUES = (
    'imports',
    'respond_io',
    'catalogue_render',
    'media',
    'project_docs',
    'flyer_read',
    'notifications',
)


def resolve_queue_names():
    """The queues this worker drains, in drain order.

    WORKER_QUEUES overrides the default so a checkout can run a worker for only
    the queues it cares about: every worktree on this machine points at the SAME
    Redis db 0, so a hardcoded list means whichever worker happens to be running
    drains another checkout's `imports` jobs with its own branch's task code.

    A blank or whitespace-only override falls back to the default rather than
    producing a worker that drains nothing at all.
    """
    raw = os.getenv('WORKER_QUEUES') or ''
    names = [q.strip() for q in raw.split(',') if q.strip()]
    return names or list(DEFAULT_QUEUES)


def _warn_if_vapid_missing():
    """Say so at boot when web push cannot possibly work.

    `notification_tasks._send_web_push_for_notification` reads VAPID_PRIVATE_KEY
    from os.environ and, when it is absent, marks each delivery
    failed/"VAPID not configured" and moves on. 158 deliveries died that way over
    eleven weeks with nothing surfacing it. A WARNING, not a hard failure: a
    worker that refuses to start over one optional channel is worse than one that
    runs without it.
    """
    missing = [k for k in ('VAPID_PRIVATE_KEY', 'VAPID_SUBJECT') if not os.environ.get(k)]
    if missing:
        logger.warning(
            "Web push is DISABLED for this worker: %s not set. Notification "
            "deliveries on the web_push channel will be marked failed.",
            ', '.join(missing),
        )


if __name__ == '__main__':
    # Multi-company isolation: register the fail-closed SELECT filter + insert
    # auto-stamp here too. The worker never runs the API's startup_event, and
    # RQ forks a work-horse per job that inherits these Session-class listeners
    # from the parent. NOTE: worker jobs must set the session scope from the
    # ImportJob company snapshot (later slice) — until then owned-table writes in
    # jobs are fail-closed (rejected). See app/services/company_scope.py.
    from app.services.company_scope import register_company_scope_listeners
    register_company_scope_listeners()

    # The spec listeners were registered in the API's startup_event only, so a Product
    # written inside an RQ job (an import, chiefly) never re-derived its specs - a
    # pre-existing hole, not something this slice introduced. The write backstop would
    # be blind on the same path, which is what surfaced it.
    from app.services.product_spec_change_listener import register_product_spec_listeners
    from app.services.product_spec_write import register_spec_write_backstop
    register_product_spec_listeners()
    register_spec_write_backstop()

    _maybe_start_scheduler()
    _warn_if_vapid_missing()
    queues = resolve_queue_names()
    worker = ForkSafeWorker(queues, connection=redis_conn)
    logger.info("Starting RQ worker for queues: %s", ', '.join(queues))
    worker.work()
