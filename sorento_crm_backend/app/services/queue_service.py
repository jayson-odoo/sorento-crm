"""Queue service for background job processing."""
import redis
import threading
from rq import Queue
from rq.job import Job, JobStatus
from rq.command import send_stop_job_command
from typing import Optional, Dict, Any
from app.config import settings
import logging

logger = logging.getLogger(__name__)

# Queues whose enqueue should immediately kick a daemon-thread drain in the same
# process. Pinned set keeps unrelated queues (e.g. embeddings) on their own scheduler.
#
# `imports` is intentionally NOT here: the dedicated worker container runs a
# blocking RQ Worker on ['imports', 'respond_io'] and picks jobs up instantly,
# so in-process draining adds no latency — it only risks running a heavy,
# many-query import on a daemon thread inside the multithreaded uvicorn process,
# sharing the global engine pool with request threads. That cross-thread use of
# pooled psycopg2 connections corrupts the libpq protocol ("PGRES_TUPLES_OK and
# no message from the libpq"). Let the worker own imports.
_IMMEDIATE_DRAIN_QUEUES: Dict[str, int] = {"notifications": 5}

# Initialize Redis connection for RQ (binary mode required for pickled jobs)
# RQ stores pickled Python objects which are binary, so decode_responses must be False
redis_conn = redis.from_url(settings.redis_url, decode_responses=False)

# Create default queue
default_queue = Queue('imports', connection=redis_conn)


def get_queue(name: str = 'imports') -> Queue:
    """Get a queue by name."""
    return Queue(name, connection=redis_conn)


def enqueue_job(
    func,
    *args,
    queue_name: str = 'imports',
    job_timeout: int = 3600,  # 1 hour default timeout
    **kwargs
) -> Job:
    """Enqueue a job to the specified queue.

    For queues in `_IMMEDIATE_DRAIN_QUEUES`, fire a daemon-thread drain in the
    same process right after enqueue so the user does not wait up to one
    scheduler heartbeat (~1 minute) for the queued job to start. The scheduler
    heartbeat remains a safety net for jobs that any process failed to drain.
    Drain uses atomic `lpop`, so concurrent drainers cannot double-claim.
    """
    queue = get_queue(queue_name)
    job = queue.enqueue(
        func,
        *args,
        job_timeout=job_timeout,
        **kwargs
    )
    logger.info(f"Job {job.id} enqueued to {queue_name} queue")
    max_jobs = _IMMEDIATE_DRAIN_QUEUES.get(queue_name)
    if max_jobs:
        trigger_drain_async(queue_name, max_jobs)
    return job


def trigger_drain_async(queue_name: str, max_jobs: int = 1) -> None:
    """Spawn a daemon thread that drains up to `max_jobs` from `queue_name` now."""
    def _drain():
        try:
            run_sync_rq_jobs(queue_name, max_jobs)
        except Exception:
            logger.exception("Immediate drain failed for queue %s", queue_name)

    threading.Thread(
        target=_drain,
        name=f"queue-drain-{queue_name}",
        daemon=True,
    ).start()


def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    """Get job status and result."""
    try:
        job = Job.fetch(job_id, connection=redis_conn)
        
        status_info = {
            'id': job.id,
            'status': job.get_status(),
            'created_at': job.created_at.isoformat() if job.created_at else None,
            'started_at': job.started_at.isoformat() if job.started_at else None,
            'ended_at': job.ended_at.isoformat() if job.ended_at else None,
            'result': None,
            'exc_info': None,
            'meta': job.meta if hasattr(job, 'meta') else {},
        }
        
        # Get result if job is finished
        if job.is_finished:
            try:
                status_info['result'] = job.result
            except Exception as e:
                status_info['result'] = {'error': str(e)}
        
        # Get exception info if job failed
        if job.is_failed:
            status_info['exc_info'] = job.exc_info
        
        return status_info
    except Exception as e:
        logger.error(f"Error fetching job {job_id}: {str(e)}")
        return None


def run_sync_rq_jobs(queue_name: str, max_jobs: int) -> dict[str, int]:
    """Pop up to max_jobs from the RQ list and execute each synchronously.

    Uses O(max_jobs) Redis ops instead of scanning every queued job id (important when
    the backlog is large). Semantics match the scheduler's previous _run_queue_jobs_impl.
    """
    queue = get_queue(queue_name)
    processed = 0
    for _ in range(max_jobs):
        # NOTE: do NOT use queue.pop_job_id() here. In rq 2.x that helper calls
        # as_text(connection.lpop(...)) without a None-check, so an empty queue
        # raises ValueError("Unknown type <class 'NoneType'>"). We pop via the
        # raw Redis connection and guard for None explicitly.
        try:
            popped = queue.connection.lpop(queue.key)
        except Exception as e:
            logger.warning("RQ lpop failed for queue %s: %s", queue_name, e)
            break
        if popped is None:
            break
        job_id = popped.decode() if isinstance(popped, bytes) else popped
        if not job_id:
            break
        try:
            job = Job.fetch(job_id, connection=redis_conn)
        except Exception as e:
            logger.warning("RQ job fetch failed after pop (%s): %s", job_id, e)
            continue
        if job.get_status() != JobStatus.QUEUED:
            logger.warning(
                "RQ popped job %s has status %s (expected queued); skipping execution",
                job_id,
                job.get_status(),
            )
            continue
        try:
            job.set_status(JobStatus.STARTED)
            job.save()
            job.func(*job.args, **job.kwargs)
            job.set_status(JobStatus.FINISHED)
            job.save()
            try:
                queue.remove(job)
            except Exception:
                pass
            processed += 1
        except Exception as e:
            logger.error(
                "Error processing %s job %s: %s",
                queue_name,
                job.id,
                e,
                exc_info=True,
            )
            try:
                job.set_status(JobStatus.FAILED)
                job.meta["exc_info"] = str(e)
                job.save()
                queue.remove(job)
            except Exception:
                pass
    remaining = queue.count
    return {"processed": processed, "queued": remaining, "queued_remaining": remaining}


def cancel_job(job_id: str) -> bool:
    """Cancel a job. Uses send_stop_job_command for running jobs, job.cancel() for queued."""
    try:
        job = Job.fetch(job_id, connection=redis_conn)
        status = job.get_status()
        if status == JobStatus.STARTED:
            send_stop_job_command(redis_conn, job_id)
            logger.info(f"Job {job_id} stop command sent (was running)")
        else:
            job.cancel()
            logger.info(f"Job {job_id} cancelled")
        return True
    except Exception as e:
        logger.error(f"Error cancelling job {job_id}: {str(e)}")
        return False
