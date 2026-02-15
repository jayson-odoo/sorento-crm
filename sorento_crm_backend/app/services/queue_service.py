"""Queue service for background job processing."""
import redis
from rq import Queue
from rq.job import Job, JobStatus
from rq.command import send_stop_job_command
from typing import Optional, Dict, Any
from app.config import settings
import logging

logger = logging.getLogger(__name__)

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
    """Enqueue a job to the specified queue."""
    queue = get_queue(queue_name)
    job = queue.enqueue(
        func,
        *args,
        job_timeout=job_timeout,
        **kwargs
    )
    logger.info(f"Job {job.id} enqueued to {queue_name} queue")
    return job


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
