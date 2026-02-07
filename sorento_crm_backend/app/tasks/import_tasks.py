"""Background tasks for imports."""
from app.database import SessionLocal
from app.services.inventory_service import StockService
from app.services.order_service import OrderService
from app.services.product_service import ProductService
from app.services.import_log_service import ImportLogService
from app.services.job_service import JobService
from app.models.job import JobStatus
import logging
from datetime import date, datetime, time as dt_time
from decimal import Decimal

logger = logging.getLogger(__name__)


def _json_safe(value):
    if isinstance(value, (datetime, date, dt_time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


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
        job_id_str = job.job_id
        job_service.start_job(job_id_str)
        
        # Process import
        stock_service = StockService(db)
        result = stock_service.bulk_import_stock(stock_data, user_id)
        
        # Mark job as completed
        job_service.complete_job(
            job_id=job_id_str,
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


def process_product_import(db_job_id: str, products_data: list, user_id: str):
    """Process product import in background."""
    from rq import get_current_job

    db = SessionLocal()
    job_service = JobService(db)

    rq_job = get_current_job()
    rq_job_id = rq_job.id if rq_job else None

    job = job_service.get_job_by_db_id(db_job_id) if db_job_id else None
    if not job and rq_job_id:
        job = job_service.get_job(rq_job_id)

    if not job:
        logger.error(f"Job not found: db_job_id={db_job_id}, rq_job_id={rq_job_id}")
        db.close()
        return

    try:
        job_id_str = job.job_id
        job_service.start_job(job_id_str)

        product_service = ProductService(db)
        result = product_service.bulk_import_products(products_data, user_id)

        job_service.complete_job(
            job_id=job_id_str,
            result={
                'created': result['created'],
                'updated': result['updated'],
                'errors': result['errors'][:200],  # Cap for storage
            },
            successful_rows=result['created'] + result['updated'],
            failed_rows=len(result['errors']),
            skipped_rows=0,
            processed_rows=len(products_data),
        )

        logger.info(
            "Product import job %s completed: created=%s, updated=%s, errors=%s",
            job_id_str, result['created'], result['updated'], len(result['errors']),
        )
    except Exception as e:
        logger.error("Product import job %s failed: %s", job.job_id, str(e), exc_info=True)
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
    
    job_id_str = job.job_id
    try:
        # Mark job as started
        job_service.start_job(job_id_str)
        
        # Process import
        order_service = OrderService(db)
        result = order_service.import_excel_tracking(file_data, user_id)

        created = result.get('created', 0)
        updated = result.get('updated', 0)
        errors = result.get('errors', [])
        warnings = result.get('warnings', [])
        master_rows = result.get('master_rows', 0)
        tracking_rows = result.get('tracking_rows', 0)
        failed_count = len(errors)
        successful_rows = created + updated
        processed_rows = master_rows + tracking_rows
        total_rows = processed_rows

        # Mark job as completed with correct counts
        job_service.complete_job(
            job_id=job_id_str,
            result={
                'created': created,
                'updated': updated,
                'failed': failed_count,
                'master_rows': master_rows,
                'tracking_rows': tracking_rows,
                'kpi_warnings': result.get('kpi_warnings', []),
                'import_session_id': result.get('import_session_id'),
                'errors': _json_safe(errors[:50]),  # First 50 errors for UI/log
                'warnings': _json_safe(warnings[:50]),
            },
            successful_rows=successful_rows,
            failed_rows=failed_count,
            skipped_rows=0,
            processed_rows=processed_rows,
            total_rows=total_rows,
        )

        logger.info(
            "Order tracking import job %s completed: processed=%s (Master=%s, Tracking=%s), created=%s, updated=%s, failed=%s",
            job_id_str, processed_rows, master_rows, tracking_rows, created, updated, failed_count,
        )
        if errors:
            for i, err in enumerate(errors[:3]):
                logger.warning("Order tracking import job %s error [%s]: row=%s %s", job_id_str, i + 1, err.get('row'), err.get('error'))
        if warnings:
            for i, warn in enumerate(warnings[:3]):
                logger.warning("Order tracking import job %s warning [%s]: row=%s %s", job_id_str, i + 1, warn.get('row'), warn.get('warning'))
        
    except Exception as e:
        logger.error("Order tracking import job %s failed: %s", job_id_str, str(e), exc_info=True)
        db.rollback()
        job_service.fail_job(job_id_str, str(e))
        try:
            import_log_service = ImportLogService(db)
            import_log_service.create_import_log(
                entity_type="order",
                entity_table="orders",
                import_session_id=job_id_str,
                filename=job.filename if job else None,
                import_type="EXCEL_IMPORT",
                total_rows=0,
                successful_rows=0,
                created_rows=0,
                updated_rows=0,
                failed_rows=0,
                skipped_rows=0,
                warnings=None,
                errors=_json_safe([{"row": None, "error": str(e), "data": None}]),
                summary=None,
                imported_by=user_id,
                duration_ms=None,
            )
        except Exception:
            pass
    finally:
        db.close()
