"""Scheduler for processing integration logs and import jobs."""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.database import SessionLocal
from app.services.integration_service import IntegrationLogService
from app.services.queue_service import get_queue

logger = logging.getLogger(__name__)


def process_pending_integration_logs():
    """
    Process pending integration logs that are ready for retry.
    This function is called periodically by the scheduler.
    """
    db = SessionLocal()
    try:
        service = IntegrationLogService(db)
        result = service.process_pending_logs()
        
        if result["processed"] > 0:
            logger.info(
                f"Processed {result['processed']} integration logs: "
                f"{result['succeeded']} succeeded, {result['failed']} failed"
            )
    except Exception as e:
        logger.error(f"Error processing pending integration logs: {str(e)}", exc_info=True)
    finally:
        db.close()


def process_import_jobs():
    """
    Process RQ import jobs from the queue.
    This function is called periodically by the scheduler to process queued import jobs.
    Manually executes jobs without registering a worker to avoid conflicts.
    """
    try:
        from rq.job import Job
        from app.services.queue_service import redis_conn
        import time
        
        # Get the imports queue
        queue = get_queue('imports')
        
        # Check if there are any jobs in the queue
        queue_length = len(queue)
        if queue_length == 0:
            logger.debug("Queue is empty, no jobs to process")
            return
        
        logger.info(f"Found {queue_length} job(s) in queue, checking for queued jobs...")
        
        # Get all job IDs from the queue
        all_job_ids = queue.get_job_ids()
        if not all_job_ids:
            logger.debug("No job IDs found in queue")
            return
        
        # Filter for queued jobs only
        queued_jobs = []
        for job_id in all_job_ids:
            try:
                job = Job.fetch(job_id, connection=redis_conn)
                if job.get_status() == 'queued':
                    queued_jobs.append(job)
            except Exception as e:
                logger.debug(f"Could not fetch job {job_id}: {str(e)}")
                continue
        
        if not queued_jobs:
            logger.debug("No queued jobs found (all jobs are already started/finished/failed)")
            return
        
        logger.info(f"Found {len(queued_jobs)} queued job(s) to process")
        
        # Process up to 2 jobs per scheduler run
        jobs_processed = 0
        max_jobs_per_run = 2
        
        for job in queued_jobs[:max_jobs_per_run]:
            try:
                logger.info(f"Processing job {job.id} (status: {job.get_status()})")
                
                # Mark job as started in RQ
                job.set_status('started')
                job.save()
                
                # Call the job function directly with its arguments
                # This avoids signal handling issues in background threads
                # The job function handles its own database job status updates
                result = job.func(*job.args, **job.kwargs)
                
                # Mark job as finished in RQ
                job.set_status('finished')
                job.save()
                
                jobs_processed += 1
                logger.info(f"Successfully processed import job {job.id} via scheduler")
            except Exception as e:
                logger.error(f"Error processing import job {job.id}: {str(e)}", exc_info=True)
                # Try to mark job as failed
                try:
                    job.set_status('failed')
                    job.meta['exc_info'] = str(e)
                    job.save()
                except Exception as save_error:
                    logger.error(f"Could not mark job {job.id} as failed: {str(save_error)}")
        
        if jobs_processed > 0:
            logger.info(f"Scheduler successfully processed {jobs_processed} import job(s) from queue")
        else:
            logger.debug("No jobs were processed in this run")
            
    except Exception as e:
        logger.error(f"Error processing import jobs in scheduler: {str(e)}", exc_info=True)


def start_scheduler():
    """
    Start the APScheduler background scheduler.
    
    Returns:
        BackgroundScheduler instance
    """
    scheduler = BackgroundScheduler()
    
    # Schedule integration log processing every 2 minutes
    scheduler.add_job(
        process_pending_integration_logs,
        trigger=IntervalTrigger(minutes=2),
        id='process_integration_logs',
        name='Process Pending Integration Logs',
        replace_existing=True
    )
    
    # Schedule import job processing every 5 seconds (for faster response)
    # This processes jobs from the Redis queue
    scheduler.add_job(
        process_import_jobs,
        trigger=IntervalTrigger(seconds=5),
        id='process_import_jobs',
        name='Process Import Jobs',
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("Scheduler started: integration logs (every 2 min), import jobs (every 5 sec)")
    
    return scheduler
