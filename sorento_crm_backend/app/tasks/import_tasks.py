"""Background tasks for imports."""
import io
import json
import time
import zipfile
import hashlib
import uuid
import mimetypes
import logging
from datetime import date, datetime, time as dt_time
from decimal import Decimal
from typing import Optional, List

from app.database import SessionLocal
from app.services.inventory_service import StockService
from app.services.order_service import OrderService
from app.services.product_service import ProductService
from app.services.import_log_service import ImportLogService
from app.services.job_service import JobService
from app.services.resources_service import (
    AttachmentDirectoryService,
    AttachmentService,
    AttachmentTypeService,
)
from app.services.s3_service import S3Service
from app.services.attachment_webhook_helper import create_and_send_webhook
from app.models.job import JobStatus
from app.schemas.resources import AttachmentCreate

logger = logging.getLogger(__name__)

# Batch size for attachment bulk import (files per batch); sleep between batches to avoid overload
ATTACHMENT_BULK_IMPORT_BATCH_SIZE = 5
ATTACHMENT_BULK_IMPORT_BATCH_DELAY_SECONDS = 0.5


def _normalize_zip_path(name: str) -> str:
    return name.replace("\\", "/").strip("/")


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


def process_attachment_bulk_import(
    db_job_id: str,
    zip_content: bytes,
    attachment_type_id: str,
    access_levels_json: str,
    parent_directory_id: Optional[str],
    user_id: str,
):
    """Process attachment bulk import (ZIP) in background with batch processing."""
    from rq import get_current_job

    db = SessionLocal()
    job_service = JobService(db)

    rq_job = get_current_job()
    rq_job_id = rq_job.id if rq_job else None

    job = job_service.get_job_by_db_id(db_job_id) if db_job_id else None
    if not job and rq_job_id:
        job = job_service.get_job(rq_job_id)

    if not job:
        logger.error("Attachment bulk import job not found: db_job_id=%s, rq_job_id=%s", db_job_id, rq_job_id)
        db.close()
        return

    job_id_str = job.job_id
    dir_service = AttachmentDirectoryService(db)
    attachment_service = AttachmentService(db)
    type_service = AttachmentTypeService(db)
    s3_service = S3Service()

    access_levels_payload = None
    try:
        parsed = json.loads(access_levels_json or "[]")
        if isinstance(parsed, list):
            access_levels_payload = parsed
    except Exception:
        pass

    try:
        job_service.start_job(job_id_str)

        try:
            attachment_type = type_service.get_type(attachment_type_id)
        except Exception:
            job_service.fail_job(job_id_str, "Invalid attachment type ID")
            db.close()
            return

        allowed_extensions = set(
            ext.strip().lower().replace(".", "")
            for ext in (attachment_type.allowed_extensions or "").split(",")
            if ext.strip()
        )
        max_bytes = (attachment_type.max_file_size_mb or 10) * 1024 * 1024

        with zipfile.ZipFile(io.BytesIO(zip_content), "r") as zf:
            all_names = [_normalize_zip_path(n) for n in zf.namelist()]

        dir_paths = set()
        file_paths: List[str] = []
        for name in all_names:
            if not name:
                continue
            if name.endswith("/"):
                dir_path = name.rstrip("/")
                if dir_path:
                    dir_paths.add(dir_path)
            else:
                file_paths.append(name)

        # Create all directories first
        for dir_path in sorted(dir_paths):
            parts = [p for p in dir_path.split("/") if p.strip()]
            if parts:
                dir_service.get_or_create_path(parent_directory_id, parts)

        total_files = len(file_paths)
        job_service.update_job_progress(job_id_str, total_rows=total_files, result={"directories_created": len(dir_paths)})

        created_attachments: List[dict] = []
        errors: List[str] = []
        successful = 0
        failed = 0
        skipped = 0
        processed = 0

        for i in range(0, len(file_paths), ATTACHMENT_BULK_IMPORT_BATCH_SIZE):
            batch = file_paths[i : i + ATTACHMENT_BULK_IMPORT_BATCH_SIZE]
            for file_path in batch:
                try:
                    with zipfile.ZipFile(io.BytesIO(zip_content), "r") as zf:
                        raw_name = next((n for n in zf.namelist() if _normalize_zip_path(n) == file_path), None)
                    if not raw_name:
                        errors.append(f"Not found in zip: {file_path}")
                        failed += 1
                        processed += 1
                        continue
                    with zipfile.ZipFile(io.BytesIO(zip_content), "r") as zf:
                        with zf.open(raw_name, "r") as entry:
                            file_content = entry.read()

                    original_filename = file_path.split("/")[-1]
                    ext = (original_filename.split(".")[-1] or "").lower()
                    if allowed_extensions and ext not in allowed_extensions:
                        errors.append(f"Skipped (extension .{ext} not allowed): {file_path}")
                        skipped += 1
                        processed += 1
                        continue
                    if len(file_content) > max_bytes:
                        errors.append(f"Skipped (file too large): {file_path}")
                        skipped += 1
                        processed += 1
                        continue

                    file_uuid = str(uuid.uuid4())
                    safe_filename = "".join(
                        c for c in original_filename if c.isalnum() or c in (" ", "-", "_", ".")
                    ).strip()
                    stored_filename = f"{file_uuid}-{safe_filename}"
                    entity_type = (attachment_type.type_name or "general").lower().replace(" ", "_")
                    s3_file_path = f"{entity_type}/{stored_filename}"
                    guessed_type, _ = mimetypes.guess_type(original_filename)
                    s3_key, s3_url = s3_service.upload_file(
                        file_content=file_content,
                        file_path=s3_file_path,
                        content_type=guessed_type,
                    )
                    dir_parts = [p for p in file_path.split("/")[:-1] if p.strip()]
                    directory_id = dir_service.get_or_create_path(parent_directory_id, dir_parts)

                    attachment_data = AttachmentCreate(
                        attachment_type_id=attachment_type_id,
                        original_filename=original_filename,
                        stored_filename=stored_filename,
                        file_path=s3_url,
                        file_size_bytes=len(file_content),
                        mime_type=guessed_type or "application/octet-stream",
                        file_hash=hashlib.sha256(file_content).hexdigest(),
                        entity_type=None,
                        entity_id=None,
                        directory_id=directory_id,
                    )
                    attachment = attachment_service.create_attachment(attachment_data, user_id)
                    try:
                        create_and_send_webhook(
                            db, attachment, attachment_type, access_levels_payload, user_id
                        )
                    except Exception as e:
                        logger.warning("Webhook creation failed for %s: %s", attachment.id, e)
                    created_attachments.append({"id": attachment.id, "path": file_path})
                    successful += 1
                except Exception as e:
                    errors.append(f"{file_path}: {e}")
                    logger.exception("Bulk import file failed: %s", file_path)
                    failed += 1
                processed += 1

            job_service.update_job_progress(
                job_id_str,
                processed_rows=processed,
                successful_rows=successful,
                failed_rows=failed,
                skipped_rows=skipped,
                result={
                    "directories_created": len(dir_paths),
                    "attachments_created": len(created_attachments),
                    "attachments": created_attachments[-100:],  # Last 100 for response size
                    "errors": errors[-50:],
                },
            )
            if i + len(batch) < len(file_paths):
                time.sleep(ATTACHMENT_BULK_IMPORT_BATCH_DELAY_SECONDS)

        result = {
            "message": "Bulk import completed",
            "directories_created": len(dir_paths),
            "attachments_created": len(created_attachments),
            "attachments": created_attachments,
            "errors": errors,
        }
        job_service.complete_job(
            job_id=job_id_str,
            result=result,
            successful_rows=successful,
            failed_rows=failed,
            skipped_rows=skipped,
            processed_rows=processed,
            total_rows=total_files,
        )
        logger.info(
            "Attachment bulk import job %s completed: %s files, %s created, %s failed, %s skipped",
            job_id_str, processed, successful, failed, skipped,
        )
        return result
    except Exception as e:
        logger.exception("Attachment bulk import job %s failed", job_id_str)
        job_service.fail_job(job_id_str, str(e))
    finally:
        db.close()
