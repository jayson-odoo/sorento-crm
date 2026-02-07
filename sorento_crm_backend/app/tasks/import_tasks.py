"""Background tasks for imports."""
from app.database import SessionLocal
from app.services.inventory_service import StockService
from app.services.order_service import OrderService
from app.services.job_service import JobService
from app.models.job import JobStatus
import logging

logger = logging.getLogger(__name__)


def process_stock_import(db_job_id: str, stock_data: list, user_id: str):
    """Process stock import in background."""
    from rq import get_current_job
    
    db = SessionLocal()
    job_service = JobService(db)
    
    # Get RQ job ID
    rq_job = get_current_job()
    rq_job_id = rq_job.id if rq_job else None
    
    # Find job by DB ID or RQ job ID
    job = job_service.get_job_by_db_id(db_job_id) if db_job_id else None
    if not job and rq_job_id:
        job = job_service.get_job(rq_job_id)
    
    if not job:
        logger.error(f"Job not found: db_job_id={db_job_id}, rq_job_id={rq_job_id}")
        db.close()
        return
    
    try:
        # Mark job as started
        job_service.start_job(job.job_id)
        
        # Process import
        stock_service = StockService(db)
        result = stock_service.bulk_import_stock(stock_data, user_id)
        
        # Mark job as completed
        job_service.complete_job(
            job_id=job.job_id,
            result={
                'created': result['created'],
                'updated': result['updated'],
                'skipped': result['skipped'],
                'errors': result['errors'],
                'warnings': result['warnings'],
                'import_session_id': result['import_session_id'],
            },
            successful_rows=result['created'] + result['updated'],
            failed_rows=len(result['errors']),
            skipped_rows=result['skipped'],
            processed_rows=len(stock_data)
        )
        
        logger.info(f"Stock import job {job.job_id} completed successfully")
        
    except Exception as e:
        logger.error(f"Stock import job {job.job_id} failed: {str(e)}", exc_info=True)
        job_service.fail_job(job.job_id, str(e))
    finally:
        db.close()


def process_order_tracking_import(db_job_id: str, file_data: bytes, user_id: str):
    """Process order tracking import in background."""
    from rq import get_current_job
    
    db = SessionLocal()
    job_service = JobService(db)
    
    # Get RQ job ID
    rq_job = get_current_job()
    rq_job_id = rq_job.id if rq_job else None
    
    # Find job by DB ID or RQ job ID
    job = job_service.get_job_by_db_id(db_job_id) if db_job_id else None
    if not job and rq_job_id:
        job = job_service.get_job(rq_job_id)
    
    if not job:
        logger.error(f"Job not found: db_job_id={db_job_id}, rq_job_id={rq_job_id}")
        db.close()
        return
    
    try:
        # Mark job as started
        job_service.start_job(job.job_id)
        
        # Process import
        order_service = OrderService(db)
        result = order_service.import_excel_tracking(file_data, user_id)

        created = result.get('created', 0)
        updated = result.get('updated', 0)
        errors = result.get('errors', [])
        master_rows = result.get('master_rows', 0)
        tracking_rows = result.get('tracking_rows', 0)
        failed_count = len(errors)
        successful_rows = created + updated
        processed_rows = master_rows + tracking_rows

        # Mark job as completed with correct counts
        job_service.complete_job(
            job_id=job.job_id,
            result={
                'created': created,
                'updated': updated,
                'failed': failed_count,
                'master_rows': master_rows,
                'tracking_rows': tracking_rows,
                'kpi_warnings': result.get('kpi_warnings', []),
                'import_session_id': result.get('import_session_id'),
                'errors': errors[:50],  # First 50 errors for UI/log
            },
            successful_rows=successful_rows,
            failed_rows=failed_count,
            skipped_rows=0,
            processed_rows=processed_rows,
        )

        logger.info(
            "Order tracking import job %s completed: processed=%s (Master=%s, Tracking=%s), created=%s, updated=%s, failed=%s",
            job.job_id, processed_rows, master_rows, tracking_rows, created, updated, failed_count,
        )
        if errors:
            for i, err in enumerate(errors[:3]):
                logger.warning("Order tracking import job %s error [%s]: row=%s %s", job.job_id, i + 1, err.get('row'), err.get('error'))
        
    except Exception as e:
        logger.error(f"Order tracking import job {job.job_id} failed: {str(e)}", exc_info=True)
        job_service.fail_job(job.job_id, str(e))
    finally:
        db.close()
