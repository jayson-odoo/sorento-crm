"""Scheduler for processing integration logs."""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.database import SessionLocal
from app.services.integration_service import IntegrationLogService

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
    
    scheduler.start()
    logger.info("Integration log scheduler started (runs every 2 minutes)")
    
    return scheduler
