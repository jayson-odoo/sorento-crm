"""Background tasks for imports."""
import json
import os
import re
import time
import zipfile
import hashlib
import mimetypes
import logging
from collections import defaultdict
from datetime import date, datetime, time as dt_time
from decimal import Decimal
from io import BytesIO
from typing import Optional, List, Any, Dict, cast

from sqlalchemy import func

from app.database import SessionLocal
from app.services.inventory_service import StockService, WarehouseService
from app.services.order_service import OrderService
from app.services.product_service import ProductService
from app.services.import_log_service import ImportLogService
from app.services.job_service import JobService
from app.services.procurement_service import SPOAllocationService, PickingHeaderService
from app.services.resources_service import (
    AttachmentDirectoryService,
    AttachmentService,
    AttachmentTypeService,
)
from app.services.attachment_webhook_helper import create_and_send_webhook
from app.api.v1.external.utils import (
    get_inbound_shipment_by_container_number,
    get_products_by_code_exact,
    get_warehouses_by_code_or_name,
    parse_date_value,
)
from app.models.job import JobStatus
from app.models.procurement import SPOAllocation
from app.models.order import Order, OrderLine
from app.schemas.resources import AttachmentCreate
from app.schemas.procurement import SPOAllocationCreate

logger = logging.getLogger(__name__)

# Batch size for attachment bulk import (files per batch); sleep between batches to avoid overload
ATTACHMENT_BULK_IMPORT_BATCH_SIZE = 5
ATTACHMENT_BULK_IMPORT_BATCH_DELAY_SECONDS = 0.5


def _normalize_zip_path(name: str) -> str:
    return name.replace("\\", "/").strip("/")


def _is_macos_metadata_path(normalized_path: str) -> bool:
    """True if path is macOS metadata (._* files or under __MACOSX)."""
    if not normalized_path:
        return False
    parts = [p for p in normalized_path.split("/") if p.strip()]
    if any(p == "__MACOSX" for p in parts):
        return True
    if parts and parts[-1].strip().startswith("._"):
        return True
    return False


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

    job_id_str: str = str(job.job_id)
    try:
        # Mark job as started
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
        job_service.fail_job(job_id_str, str(e))
    finally:
        db.close()


def process_warehouse_import(db_job_id: str, warehouses_data: list, user_id: str):
    """Process warehouse import in background. Upserts by warehouse_code."""
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

    job_id_str: str = str(job.job_id)
    try:
        job_service.start_job(job_id_str)

        warehouse_service = WarehouseService(db)
        result = warehouse_service.bulk_import_warehouses(warehouses_data, user_id)

        job_service.complete_job(
            job_id=job_id_str,
            result={
                "created": result["created"],
                "updated": result["updated"],
                "skipped": result["skipped"],
                "errors": result["errors"],
                "warnings": result["warnings"],
                "import_session_id": result["import_session_id"],
            },
            successful_rows=result["created"] + result["updated"],
            failed_rows=len(result["errors"]),
            skipped_rows=result["skipped"],
            processed_rows=len(warehouses_data),
        )

        logger.info(f"Warehouse import job {job.job_id} completed successfully")

    except Exception as e:
        logger.error(f"Warehouse import job {job.job_id} failed: {str(e)}", exc_info=True)
        job_service.fail_job(job_id_str, str(e))
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

    job_id_str: str = str(job.job_id)
    try:
        job_service.start_job(job_id_str)
        job_service.update_job_progress(job_id_str, total_rows=len(products_data))

        def on_progress(processed: int, successful: int, failed: int, skipped: int) -> None:
            job_service.update_job_progress(
                job_id_str,
                processed_rows=processed,
                successful_rows=successful,
                failed_rows=failed,
                skipped_rows=skipped,
            )

        product_service = ProductService(db)
        result = product_service.bulk_import_products(products_data, user_id, on_progress=on_progress)

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
        job_service.fail_job(job_id_str, str(e))
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
    
    job_id_str: str = str(job.job_id)
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
            skipped_rows=len(warnings),
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
                filename=str(job.filename) if (job and job.filename is not None) else None,
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
    zip_path: str,
    attachment_type_id: str,
    access_levels_json: str,
    parent_directory_id: Optional[str],
    user_id: str,
):
    """Process attachment bulk import (ZIP) in background with batch processing. Reads ZIP from temp file path."""
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
        if os.path.isfile(zip_path):
            try:
                os.remove(zip_path)
            except OSError:
                pass
        return

    job_id_str: str = str(job.job_id)
    try:
        dir_service = AttachmentDirectoryService(db)
        attachment_service = AttachmentService(db)
        type_service = AttachmentTypeService(db)
        from app.services.storage_router import (
            cdn_base_url,
            default_provider,
            get_backend,
        )
        storage_provider = default_provider()
        storage_backend = get_backend(storage_provider)

        access_levels_payload = None
        try:
            parsed = json.loads(access_levels_json or "[]")
            if isinstance(parsed, list):
                access_levels_payload = parsed
        except Exception:
            pass
        from app.services.contact_access_type_service import ContactAccessTypeService
        access_svc = ContactAccessTypeService(db)
        if access_levels_payload:
            try:
                access_levels_payload = access_svc.validate_access_levels(access_levels_payload, field_name="access_levels")
            except Exception:
                access_levels_payload = access_svc.get_default_access_levels()
        else:
            access_levels_payload = access_svc.get_default_access_levels()

        job_service.start_job(job_id_str)

        try:
            attachment_type = type_service.get_type(attachment_type_id)
        except Exception:
            job_service.fail_job(job_id_str, "Invalid attachment type ID")
            db.close()
            return

        _allowed_raw = attachment_type.allowed_extensions
        _allowed_str = str(_allowed_raw) if _allowed_raw is not None else ""
        allowed_extensions: set[str] = set(
            ext.strip().lower().replace(".", "")
            for ext in _allowed_str.split(",")
            if ext.strip()
        )
        _mb = attachment_type.max_file_size_mb
        max_bytes = (int(cast(int, _mb)) if _mb is not None else 10) * 1024 * 1024

        with zipfile.ZipFile(zip_path, "r") as zf:
            all_names = [_normalize_zip_path(n) for n in zf.namelist()]

        dir_paths = set()
        file_paths: List[str] = []
        for name in all_names:
            if not name:
                continue
            if _is_macos_metadata_path(name):
                continue
            if name.endswith("/"):
                dir_path = name.rstrip("/")
                if dir_path and not _is_macos_metadata_path(dir_path):
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
                    with zipfile.ZipFile(zip_path, "r") as zf:
                        raw_name = next((n for n in zf.namelist() if _normalize_zip_path(n) == file_path), None)
                    if not raw_name:
                        errors.append(f"Not found in zip: {file_path}")
                        failed += 1
                        processed += 1
                        continue
                    with zipfile.ZipFile(zip_path, "r") as zf:
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

                    safe_filename = "".join(
                        c for c in original_filename if c.isalnum() or c in (" ", "-", "_", ".")
                    ).strip()
                    stored_filename = safe_filename or "file"
                    entity_type = (attachment_type.type_name or "general").lower().replace(" ", "_")
                    s3_file_path = f"{entity_type}/{stored_filename}"
                    guessed_type, _ = mimetypes.guess_type(original_filename)
                    s3_key, _ = storage_backend.upload_file(
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
                        file_path=cdn_base_url(storage_provider, s3_key),
                        file_size_bytes=len(file_content),
                        mime_type=guessed_type or "application/octet-stream",
                        file_hash=hashlib.sha256(file_content).hexdigest(),
                        entity_type=None,
                        entity_id=None,
                        directory_id=directory_id,
                        access_levels=access_levels_payload,
                        storage_provider=storage_provider,
                    )
                    attachment = attachment_service.create_attachment(attachment_data, user_id)
                    if attachment is not None:
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
        if zip_path and os.path.isfile(zip_path):
            try:
                os.remove(zip_path)
            except OSError as e:
                logger.warning("Could not remove temp zip %s: %s", zip_path, e)


def _spo_import_normalize_header(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _spo_import_find_column(row_data: dict, *candidates: str) -> Any:
    """Return first matching column value (case-insensitive key match)."""
    keys_lower = {k.lower(): k for k in row_data if k}
    for c in candidates:
        cl = c.lower().strip()
        if cl in keys_lower:
            return row_data.get(keys_lower[cl])
    return None


def _spo_import_extract_container(loading_date_value: Any) -> Optional[str]:
    """Extract shipping container number: text after first space in Loading Date cell."""
    if loading_date_value is None:
        return None
    s = str(loading_date_value).strip()
    if not s:
        return None
    parts = s.split(None, 1)  # max 2 parts
    if len(parts) < 2:
        return None
    return parts[1].strip() or None


def process_spo_import(db_job_id: str, file_data: bytes, filename: str, user_id: str):
    """Process SPO allocation import from Excel in background.

    Parsing rules:
    - Filename (without extension) = SPO number.
    - Item Code = product code.
    - Loading Date = cell text; text after first space = shipping container number (link to inbound shipment).
    - Location = warehouse code.
    - Qty = allocated quantity.

    Rows are grouped by (spo_number, product_id, warehouse_id); quantities are summed.
    One allocation is created per group, linked to the first valid inbound shipment for that group.
    """
    from rq import get_current_job
    import openpyxl

    db = SessionLocal()
    job_service = JobService(db)
    rq_job = get_current_job()
    rq_job_id = rq_job.id if rq_job else None

    job = job_service.get_job_by_db_id(db_job_id) if db_job_id else None
    if not job and rq_job_id:
        job = job_service.get_job(rq_job_id)

    if not job:
        logger.error("SPO import job not found: db_job_id=%s, rq_job_id=%s", db_job_id, rq_job_id)
        db.close()
        return

    job_id_str: str = str(job.job_id)

    try:
        job_service.start_job(job_id_str)

        spo_number = re.sub(r"\.xlsx?$", "", filename or "", flags=re.IGNORECASE).strip()
        if not spo_number:
            job_service.fail_job(job_id_str, "Filename must provide SPO number (e.g. SPO-2025.10-0050.xlsx)")
            db.close()
            return

        try:
            workbook = openpyxl.load_workbook(BytesIO(file_data), data_only=True)
        except Exception as exc:
            job_service.fail_job(job_id_str, f"Failed to read Excel file: {exc}")
            db.close()
            return

        sheet = workbook.active
        if not sheet:
            job_service.fail_job(job_id_str, "Workbook has no active sheet")
            db.close()
            return

        from app.api.v1.external.utils import normalize_code

        headers = [_spo_import_normalize_header(cell.value) for cell in sheet[1]]
        # Collect all data rows (non-empty) and extract codes/locations for lookup
        data_rows: List[tuple[int, dict]] = []  # (row_idx, row_data dict)
        all_product_codes = set()
        all_locations = set()

        for row_idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
            if not any(cell is not None and str(cell).strip() for cell in row):
                continue
            row_data = {}
            for idx, value in enumerate(row):
                if idx < len(headers) and headers[idx]:
                    row_data[headers[idx]] = value
            item_code_raw = _spo_import_find_column(
                row_data, "Item Code", "Item code", "Product Code", "Product code"
            )
            location_raw = _spo_import_find_column(
                row_data, "Location", "Warehouse", "Warehouse Code"
            )
            qty_raw = _spo_import_find_column(
                row_data, "Qty", "Quantity", "Allocated", "Allocated Quantity"
            )
            loading_date_raw = _spo_import_find_column(
                row_data, "Loading Date", "Loading date"
            )
            item_code = (item_code_raw and str(item_code_raw).strip()) or None
            location = (location_raw and str(location_raw).strip()) or None
            try:
                qty = int(float(qty_raw)) if qty_raw is not None else 0
            except (TypeError, ValueError):
                qty = 0
            container = _spo_import_extract_container(loading_date_raw)
            if item_code:
                all_product_codes.add(item_code)
            if location:
                all_locations.add(location)
            data_rows.append((row_idx, row_data))

        total_data_rows = len(data_rows)
        if not total_data_rows:
            job_service.complete_job(
                job_id=job_id_str,
                result={"message": "No valid data rows found"},
                successful_rows=0,
                failed_rows=0,
                skipped_rows=0,
                processed_rows=0,
                total_rows=0,
            )
            db.close()
            return

        products_by_code = get_products_by_code_exact(db, all_product_codes)
        warehouses_map = get_warehouses_by_code_or_name(db, all_locations)

        resolved_rows: List[tuple[str, str, str, int, int]] = []  # product_id, warehouse_id, shipment_id, qty, row_idx
        skipped_rows_detail: List[dict] = []  # [{"row": int, "reason": str}, ...]

        for row_idx, row_data in data_rows:
            item_code_raw = _spo_import_find_column(
                row_data, "Item Code", "Item code", "Product Code", "Product code"
            )
            loading_date_raw = _spo_import_find_column(
                row_data, "Loading Date", "Loading date"
            )
            location_raw = _spo_import_find_column(
                row_data, "Location", "Warehouse", "Warehouse Code"
            )
            qty_raw = _spo_import_find_column(
                row_data, "Qty", "Quantity", "Allocated", "Allocated Quantity"
            )

            item_code = (item_code_raw and str(item_code_raw).strip()) or None
            location = (location_raw and str(location_raw).strip()) or None
            try:
                qty = int(float(qty_raw)) if qty_raw is not None else 0
            except (TypeError, ValueError):
                qty = 0

            if not item_code:
                skipped_rows_detail.append({"row": row_idx, "reason": "Missing Item Code / Product Code"})
                continue
            if not location:
                skipped_rows_detail.append({"row": row_idx, "reason": "Missing Location / Warehouse"})
                continue
            if qty <= 0:
                skipped_rows_detail.append({"row": row_idx, "reason": "Invalid or zero Qty"})
                continue
            container = _spo_import_extract_container(loading_date_raw)
            if not container:
                skipped_rows_detail.append({"row": row_idx, "reason": "Missing or invalid Loading Date (no container number)"})
                continue

            product = products_by_code.get(item_code)
            warehouse = warehouses_map.get(normalize_code(location)) if location else None
            shipment = get_inbound_shipment_by_container_number(db, container)

            if not product:
                skipped_rows_detail.append({"row": row_idx, "reason": f"Product not found: {item_code}"})
                continue
            if not warehouse:
                skipped_rows_detail.append({"row": row_idx, "reason": f"Warehouse not found: {location}"})
                continue
            if not shipment:
                skipped_rows_detail.append({"row": row_idx, "reason": f"Inbound shipment not found for container: {container}"})
                continue
            resolved_rows.append((str(product.id), str(warehouse.id), str(shipment.id), qty, row_idx))

        # Group by (product_id, warehouse_id): sum qty, keep first shipment_id
        groups: Dict[tuple[str, str], tuple[int, str]] = defaultdict(lambda: (0, ""))
        for product_id, warehouse_id, shipment_id, qty, row_idx in resolved_rows:
            key = (product_id, warehouse_id)
            total, first_shipment = groups[key]
            if not first_shipment:
                first_shipment = shipment_id
            groups[key] = (total + qty, first_shipment)

        num_groups = len(groups)
        row_level_skipped = len(skipped_rows_detail)
        job_service.update_job_progress(job_id_str, total_rows=total_data_rows)

        successful = 0
        failed = 0
        skipped_groups = 0
        processed = 0
        errors: List[str] = []
        proc_service = SPOAllocationService(db)

        for (product_id, warehouse_id), (total_qty, shipment_id) in groups.items():
            processed += 1
            try:
                allocation_data = SPOAllocationCreate(
                    spo_number=spo_number,
                    inbound_shipment_id=shipment_id,
                    warehouse_id=warehouse_id,
                    product_id=product_id,
                    allocated_quantity=total_qty,
                    receipt_status="pending",
                    quantity_received=0,
                    quantity_rejected=0,
                )
                proc_service.create_allocation(allocation_data, user_id)
                successful += 1
            except Exception as e:
                if "already exists" in str(e).lower() or "conflict" in str(e).lower():
                    skipped_groups += 1
                    errors.append(f"Skipped duplicate: {spo_number} / product {product_id} / warehouse {warehouse_id}")
                else:
                    failed += 1
                    errors.append(f"Create allocation: {e}")

            total_skipped = row_level_skipped + skipped_groups
            job_service.update_job_progress(
                job_id_str,
                processed_rows=processed,
                successful_rows=successful,
                failed_rows=failed,
                skipped_rows=total_skipped,
                result={"errors": errors[-50:], "skipped_rows_detail": skipped_rows_detail[-200:]},
            )

        total_skipped = row_level_skipped + skipped_groups
        job_service.complete_job(
            job_id=job_id_str,
            result={
                "message": "SPO import completed",
                "data_rows": total_data_rows,
                "allocations_created": successful,
                "skipped_rows_detail": _json_safe(skipped_rows_detail[-200:]),
                "skipped_rows_count": total_skipped,
                "errors": _json_safe(errors[-100:]),
            },
            successful_rows=successful,
            failed_rows=failed,
            skipped_rows=total_skipped,
            processed_rows=total_data_rows,
            total_rows=total_data_rows,
        )
        logger.info(
            "SPO import job %s completed: %s data rows, %s ok, %s failed, %s skipped",
            job_id_str, total_data_rows, successful, failed, total_skipped,
        )
    except Exception as e:
        logger.exception("SPO import job %s failed", job_id_str)
        job_service.fail_job(job_id_str, str(e))
    finally:
        db.close()


def validate_spo_import(file_data: bytes, filename: str) -> Dict[str, Any]:
    """Run SPO import validation (same parsing and row validation as process_spo_import). No allocations created."""
    import openpyxl

    spo_number = re.sub(r"\.xlsx?$", "", filename or "", flags=re.IGNORECASE).strip()
    if not spo_number:
        return {"valid": False, "errors": ["Filename must provide SPO number (e.g. SPO-2025.10-0050.xlsx)"], "warnings": [], "summary": {}}

    db = SessionLocal()
    try:
        workbook = openpyxl.load_workbook(BytesIO(file_data), data_only=True)
    except Exception as exc:
        db.close()
        return {"valid": False, "errors": [f"Failed to read Excel: {exc}"], "warnings": [], "summary": {}}
    sheet = workbook.active
    if not sheet:
        db.close()
        return {"valid": False, "errors": ["Workbook has no active sheet"], "warnings": [], "summary": {}}

    headers = [_spo_import_normalize_header(cell.value) for cell in sheet[1]]
    data_rows: List[tuple[int, dict]] = []
    all_product_codes = set()
    all_locations = set()
    for row_idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        if not any(cell is not None and str(cell).strip() for cell in row):
            continue
        row_data = {}
        for idx, value in enumerate(row):
            if idx < len(headers) and headers[idx]:
                row_data[headers[idx]] = value
        item_code_raw = _spo_import_find_column(row_data, "Item Code", "Item code", "Product Code", "Product code")
        location_raw = _spo_import_find_column(row_data, "Location", "Warehouse", "Warehouse Code")
        qty_raw = _spo_import_find_column(row_data, "Qty", "Quantity", "Allocated", "Allocated Quantity")
        loading_date_raw = _spo_import_find_column(row_data, "Loading Date", "Loading date")
        item_code = (item_code_raw and str(item_code_raw).strip()) or None
        location = (location_raw and str(location_raw).strip()) or None
        try:
            qty = int(float(qty_raw)) if qty_raw is not None else 0
        except (TypeError, ValueError):
            qty = 0
        container = _spo_import_extract_container(loading_date_raw)
        if item_code:
            all_product_codes.add(item_code)
        if location:
            all_locations.add(location)
        data_rows.append((row_idx, row_data))

    if not data_rows:
        db.close()
        return {"valid": True, "errors": [], "warnings": [], "summary": {"total_data_rows": 0}}

    from app.api.v1.external.utils import normalize_code
    products_by_code = get_products_by_code_exact(db, all_product_codes)
    warehouses_map = get_warehouses_by_code_or_name(db, all_locations)
    skipped_rows_detail: List[dict] = []
    would_succeed = 0
    for row_idx, row_data in data_rows:
        item_code_raw = _spo_import_find_column(row_data, "Item Code", "Item code", "Product Code", "Product code")
        loading_date_raw = _spo_import_find_column(row_data, "Loading Date", "Loading date")
        location_raw = _spo_import_find_column(row_data, "Location", "Warehouse", "Warehouse Code")
        qty_raw = _spo_import_find_column(row_data, "Qty", "Quantity", "Allocated", "Allocated Quantity")
        item_code = (item_code_raw and str(item_code_raw).strip()) or None
        location = (location_raw and str(location_raw).strip()) or None
        try:
            qty = int(float(qty_raw)) if qty_raw is not None else 0
        except (TypeError, ValueError):
            qty = 0
        container = _spo_import_extract_container(loading_date_raw)
        if not item_code:
            skipped_rows_detail.append({"row": row_idx, "reason": "Missing Item Code / Product Code"})
            continue
        if not location:
            skipped_rows_detail.append({"row": row_idx, "reason": "Missing Location / Warehouse"})
            continue
        if qty <= 0:
            skipped_rows_detail.append({"row": row_idx, "reason": "Invalid or zero Qty"})
            continue
        if not container:
            skipped_rows_detail.append({"row": row_idx, "reason": "Missing or invalid Loading Date (no container number)"})
            continue
        product = products_by_code.get(item_code)
        warehouse = warehouses_map.get(normalize_code(location)) if location else None
        shipment = get_inbound_shipment_by_container_number(db, container)
        if not product:
            skipped_rows_detail.append({"row": row_idx, "reason": f"Product not found: {item_code}"})
            continue
        if not warehouse:
            skipped_rows_detail.append({"row": row_idx, "reason": f"Warehouse not found: {location}"})
            continue
        if not shipment:
            skipped_rows_detail.append({"row": row_idx, "reason": f"Inbound shipment not found for container: {container}"})
            continue
        would_succeed += 1

    errors = [f"Row {s['row']}: {s['reason']}" for s in skipped_rows_detail]
    db.close()
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": [],
        "summary": {
            "spo_number": spo_number,
            "total_data_rows": len(data_rows),
            "would_succeed": would_succeed,
            "would_skip": len(skipped_rows_detail),
            "skipped_rows_detail": skipped_rows_detail[-100:],
        },
    }


def _grn_import_normalize_header(value: Any) -> str:
    """Normalize Excel header for GRN import (lowercase, trim, punctuation-insensitive)."""
    if value is None:
        return ""
    s = str(value).strip().lower()
    if not s:
        return ""
    # Treat variants like "Doc. No.", "Doc No", "DOC-NO" as the same key.
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# GRN listing "Transfer from" and line sheet "From Doc. No." both carry the SPO number.
_GRN_SPO_COLUMN_CANDIDATES = (
    "transfer from",
    "transfer from ",
    "spo number",
    "from doc no",
    "from doc number",
    "from document no",
    "from document number",
)


def _run_grn_listing_import_core(
    db,
    file_data: bytes,
    job_service: Optional[JobService] = None,
    job_id_str: Optional[str] = None,
) -> Dict[str, Any]:
    """Parse GRN listing Excel and run upsert loop. Returns counts and errors. Caller must commit or rollback."""
    import openpyxl

    try:
        workbook = openpyxl.load_workbook(BytesIO(file_data), data_only=True)
    except Exception as exc:
        return {"error": f"Failed to read Excel: {exc}", "successful": 0, "failed": 0, "skipped": 0, "errors": [], "skipped_rows_detail": [], "total_data_rows": 0}

    sheet = workbook.active
    if not sheet:
        return {"error": "Workbook has no active sheet", "successful": 0, "failed": 0, "skipped": 0, "errors": [], "skipped_rows_detail": [], "total_data_rows": 0}

    headers = [_grn_import_normalize_header(cell.value) for cell in sheet[1]]
    data_rows: List[dict] = []
    for row in sheet.iter_rows(min_row=2, values_only=True):
        if not any(cell is not None and str(cell).strip() for cell in row):
            continue
        row_data = {}
        for idx, value in enumerate(row):
            if idx < len(headers) and headers[idx]:
                row_data[headers[idx]] = value
        data_rows.append(row_data)

    def _find(row: dict, *candidates: str) -> Any:
        for c in candidates:
            cl = _grn_import_normalize_header(c)
            if cl in row:
                return row.get(cl)
        return None

    total_data_rows = len(data_rows)
    if job_service and job_id_str:
        job_service.update_job_progress(job_id_str, total_rows=total_data_rows)

    proc = PickingHeaderService(db)
    successful = 0
    failed = 0
    skipped = 0
    errors: List[str] = []
    skipped_rows_detail: List[dict] = []

    for row_idx, row in enumerate(data_rows, start=2):
        doc_num = _find(row, "doc number", "doc. no.", "doc. number", "doc number ", "grn number")
        grn_number = (doc_num and str(doc_num).strip()) or None
        if not grn_number:
            skipped += 1
            skipped_rows_detail.append({"row": row_idx, "reason": "Missing doc number / GRN number"})
            if job_service and job_id_str:
                job_service.update_job_progress(job_id_str, processed_rows=row_idx - 1, successful_rows=successful, failed_rows=failed, skipped_rows=skipped)
            continue
        transfer_from = _find(row, *_GRN_SPO_COLUMN_CANDIDATES)
        spo_number = (transfer_from and str(transfer_from).strip()) or None
        date_val = _find(row, "date", "picking date", "picking date ")
        try:
            _pd = parse_date_value(date_val) if date_val is not None else date.today()
            picking_date = _pd if _pd is not None else date.today()
        except Exception:
            picking_date = date.today()
        try:
            proc.upsert_grn_header_for_import(grn_number, spo_number, picking_date)
            successful += 1
        except Exception as e:
            failed += 1
            errors.append(f"{grn_number}: {e}")
        if job_service and job_id_str:
            job_service.update_job_progress(job_id_str, processed_rows=row_idx - 1, successful_rows=successful, failed_rows=failed, skipped_rows=skipped)

    return {
        "successful": successful,
        "failed": failed,
        "skipped": skipped,
        "errors": errors,
        "skipped_rows_detail": skipped_rows_detail,
        "total_data_rows": total_data_rows,
    }


def validate_grn_listing_import(file_data: bytes) -> Dict[str, Any]:
    """Run GRN listing validation (same logic as import, then rollback). No DB writes."""
    db = SessionLocal()
    try:
        result = _run_grn_listing_import_core(db, file_data)
        db.rollback()
        if "error" in result:
            return {"valid": False, "errors": [result["error"]], "warnings": [], "summary": result}
        return {
            "valid": result["failed"] == 0 and len(result["errors"]) == 0,
            "errors": result["errors"],
            "warnings": [],
            "summary": {
                "total_data_rows": result["total_data_rows"],
                "would_succeed": result["successful"],
                "would_fail": result["failed"],
                "would_skip": result["skipped"],
                "skipped_rows_detail": result["skipped_rows_detail"][-100:],
            },
        }
    finally:
        db.close()


def validate_grn_lines_import(file_data: bytes) -> Dict[str, Any]:
    """Run GRN lines validation: parse file and run grouping-phase checks (same as import). No line creation."""
    import openpyxl
    from app.api.v1.external.utils import normalize_code

    db = SessionLocal()
    try:
        workbook = openpyxl.load_workbook(BytesIO(file_data), data_only=True)
    except Exception as exc:
        db.close()
        return {"valid": False, "errors": [f"Failed to read Excel: {exc}"], "warnings": [], "summary": {}}
    sheet = workbook.active
    if not sheet:
        db.close()
        return {"valid": False, "errors": ["Workbook has no active sheet"], "warnings": [], "summary": {}}

    headers = [_grn_import_normalize_header(cell.value) for cell in sheet[1]]
    data_rows: List[tuple] = []
    all_doc_nos = set()
    all_product_codes = set()
    all_locations = set()

    for row in sheet.iter_rows(min_row=2, values_only=True):
        if not any(cell is not None and str(cell).strip() for cell in row):
            continue
        row_data = {}
        for idx, value in enumerate(row):
            if idx < len(headers) and headers[idx]:
                row_data[headers[idx]] = value

        def _find(row_d: dict, *candidates: str) -> Any:
            for c in candidates:
                cl = _grn_import_normalize_header(c)
                if cl in row_d:
                    return row_d.get(cl)
            return None

        doc_no = (_find(row_data, "doc no", "doc number", "grn number") and str(_find(row_data, "doc no", "doc number", "grn number")).strip()) or None
        item_code = (_find(row_data, "item code", "item code ", "product code", "product code ") and str(_find(row_data, "item code", "item code ", "product code", "product code ")).strip()) or None
        location = (_find(row_data, "location", "warehouse", "warehouse code") and str(_find(row_data, "location", "warehouse", "warehouse code")).strip()) or None
        qty_raw = _find(row_data, "qty", "quantity", "qty ")
        line_spo_raw = _find(row_data, *_GRN_SPO_COLUMN_CANDIDATES)
        line_spo = (str(line_spo_raw).strip() if line_spo_raw is not None else "") or None
        try:
            qty = int(float(qty_raw)) if qty_raw is not None else 0
        except (TypeError, ValueError):
            qty = 0
        if doc_no:
            all_doc_nos.add(doc_no)
        if item_code:
            all_product_codes.add(item_code)
        if location:
            all_locations.add(location)
        data_rows.append((doc_no, item_code, location, qty, line_spo))

    if not data_rows:
        db.close()
        return {"valid": True, "errors": [], "warnings": [], "summary": {"total_data_rows": 0}}

    proc = PickingHeaderService(db)
    products_by_code = get_products_by_code_exact(db, all_product_codes)
    warehouses_map = get_warehouses_by_code_or_name(db, all_locations)
    headers_by_number: Dict[str, Any] = {}
    for pn in all_doc_nos:
        h = proc.get_grn_by_picking_number(pn)
        if h:
            headers_by_number[pn] = h

    errors = []
    skipped_detail: List[dict] = []
    would_succeed = 0
    for row_idx, row_tuple in enumerate(data_rows, start=2):
        doc_no, item_code, location, qty, _line_spo = row_tuple
        if not doc_no:
            skipped_detail.append({"row": row_idx, "reason": "Missing doc no"})
            continue
        if not item_code:
            skipped_detail.append({"row": row_idx, "reason": "Missing item code"})
            continue
        if not location:
            skipped_detail.append({"row": row_idx, "reason": "Missing location"})
            continue
        if qty <= 0:
            skipped_detail.append({"row": row_idx, "reason": "Invalid quantity"})
            continue
        if doc_no not in headers_by_number:
            skipped_detail.append({"row": row_idx, "reason": f"GRN header not found: {doc_no}"})
            continue
        product = products_by_code.get((item_code or "").strip())
        warehouse = warehouses_map.get(normalize_code(location)) if location else None
        if not product:
            skipped_detail.append({"row": row_idx, "reason": f"Product not found: {item_code}"})
            continue
        if not warehouse:
            skipped_detail.append({"row": row_idx, "reason": f"Warehouse not found: {location}"})
            continue
        would_succeed += 1

    errors = [f"Row {s['row']}: {s['reason']}" for s in skipped_detail]
    db.close()
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": [],
        "summary": {
            "total_data_rows": len(data_rows),
            "would_succeed": would_succeed,
            "would_skip": len(skipped_detail),
            "skipped_rows_detail": skipped_detail[-100:],
        },
    }


def _normalize_spo_number(spo_number: Optional[str]) -> str:
    """Normalize SPO number for matching: allow different separators (e.g. / vs .).
    E.g. SPO-2026/01-0178 and SPO-2026.01-0178 match."""
    if not spo_number or not str(spo_number).strip():
        return ""
    s = str(spo_number).strip()
    # Canonicalize common separators to dot: / and backslash -> .
    s = s.replace("/", ".").replace("\\", ".")
    return s


def process_grn_listing_import(db_job_id: str, file_data: bytes, filename: str, user_id: str):
    """Process GRN listing Excel: create/update picking headers. Idempotent."""
    from rq import get_current_job

    db = SessionLocal()
    job_service = JobService(db)
    rq_job = get_current_job()
    rq_job_id = rq_job.id if rq_job else None
    job = job_service.get_job_by_db_id(db_job_id) if db_job_id else None
    if not job and rq_job_id:
        job = job_service.get_job(rq_job_id)
    if not job:
        logger.error("GRN listing import job not found: db_job_id=%s", db_job_id)
        db.close()
        return

    job_id_str: str = str(job.job_id)
    try:
        job_service.start_job(job_id_str)
        result = _run_grn_listing_import_core(db, file_data, job_service=job_service, job_id_str=job_id_str)
        if "error" in result:
            job_service.fail_job(job_id_str, result["error"])
            db.close()
            return
        db.commit()
        job_service.complete_job(
            job_id=job_id_str,
            result={
                "message": "GRN listing import completed",
                "errors": result["errors"][-100:],
                "skipped_rows_detail": _json_safe(result["skipped_rows_detail"][-500:]),
            },
            successful_rows=result["successful"],
            failed_rows=result["failed"],
            skipped_rows=result["skipped"],
            processed_rows=result["total_data_rows"],
            total_rows=result["total_data_rows"],
        )
        logger.info(
            "GRN listing import job %s completed: %s ok, %s failed, %s skipped",
            job_id_str, result["successful"], result["failed"], result["skipped"],
        )
    except Exception as e:
        logger.exception("GRN listing import job %s failed", job_id_str)
        job_service.fail_job(job_id_str, str(e))
    finally:
        db.close()


def process_grn_lines_import(db_job_id: str, file_data: bytes, filename: str, user_id: str):
    """Process GRN lines Excel: create/update picking lines. Idempotent.
    Columns: doc no -> GRN picking_number; item code; location -> warehouse; qty.
    Optional SPO source (same as listing Transfer from): transfer from, spo number, from doc. no., etc.
    Line-level SPO overrides the header’s spo_number for SPO allocation matching. Groups split by effective SPO so mixed SPOs on one GRN do not merge.
    """
    from rq import get_current_job
    import openpyxl

    db = SessionLocal()
    job_service = JobService(db)
    rq_job = get_current_job()
    rq_job_id = rq_job.id if rq_job else None
    job = job_service.get_job_by_db_id(db_job_id) if db_job_id else None
    if not job and rq_job_id:
        job = job_service.get_job(rq_job_id)
    if not job:
        logger.error("GRN lines import job not found: db_job_id=%s", db_job_id)
        db.close()
        return

    job_id_str: str = str(job.job_id)
    try:
        job_service.start_job(job_id_str)
        try:
            workbook = openpyxl.load_workbook(BytesIO(file_data), data_only=True)
        except Exception as exc:
            job_service.fail_job(job_id_str, f"Failed to read Excel: {exc}")
            db.close()
            return

        sheet = workbook.active
        if not sheet:
            job_service.fail_job(job_id_str, "Workbook has no active sheet")
            db.close()
            return

        headers = [_grn_import_normalize_header(cell.value) for cell in sheet[1]]
        data_rows: List[tuple] = []  # (doc_no, item_code, location, qty, line_spo)
        all_doc_nos = set()
        all_product_codes = set()
        all_locations = set()

        for row in sheet.iter_rows(min_row=2, values_only=True):
            if not any(cell is not None and str(cell).strip() for cell in row):
                continue
            row_data = {}
            for idx, value in enumerate(row):
                if idx < len(headers) and headers[idx]:
                    row_data[headers[idx]] = value

            def _find(row_d: dict, *candidates: str) -> Any:
                for c in candidates:
                    cl = _grn_import_normalize_header(c)
                    if cl in row_d:
                        return row_d.get(cl)
                return None

            doc_no = (_find(row_data, "doc no", "doc number", "grn number") and str(_find(row_data, "doc no", "doc number", "grn number")).strip()) or None
            item_code = (_find(row_data, "item code", "item code ", "product code", "product code ") and str(_find(row_data, "item code", "item code ", "product code", "product code ")).strip()) or None
            location = (_find(row_data, "location", "warehouse", "warehouse code") and str(_find(row_data, "location", "warehouse", "warehouse code")).strip()) or None
            qty_raw = _find(row_data, "qty", "quantity", "qty ")
            line_spo_raw = _find(row_data, *_GRN_SPO_COLUMN_CANDIDATES)
            line_spo = (str(line_spo_raw).strip() if line_spo_raw is not None else "") or None
            try:
                qty = int(float(qty_raw)) if qty_raw is not None else 0
            except (TypeError, ValueError):
                qty = 0
            if doc_no:
                all_doc_nos.add(doc_no)
            if item_code:
                all_product_codes.add(item_code)
            if location:
                all_locations.add(location)
            data_rows.append((doc_no, item_code, location, qty, line_spo))

        total_data_rows = len(data_rows)
        # Set total_rows immediately after reading all rows, before any processing
        job_service.update_job_progress(job_id_str, total_rows=total_data_rows, processed_rows=0)

        if not data_rows:
            job_service.complete_job(
                job_id=job_id_str,
                result={"message": "No valid data rows"},
                successful_rows=0,
                failed_rows=0,
                skipped_rows=0,
                processed_rows=0,
                total_rows=total_data_rows,
            )
            db.close()
            return

        proc = PickingHeaderService(db)
        products_by_code = get_products_by_code_exact(db, all_product_codes)
        warehouses_map = get_warehouses_by_code_or_name(db, all_locations)
        from app.api.v1.external.utils import normalize_code

        product_id_to_code = {str(p.id): code for code, p in products_by_code.items()}
        warehouse_id_to_display = {
            str(w.id): (getattr(w, "code", None) or getattr(w, "name", None) or str(w.id))
            for w in warehouses_map.values()
        }

        # Resolve headers by picking_number
        headers_by_number: Dict[str, Any] = {}
        for pn in all_doc_nos:
            h = proc.get_grn_by_picking_number(pn)
            if h:
                headers_by_number[pn] = h

        # Group by (doc_no, product_id, warehouse_id) and sum quantity; track skipped with Excel row number
        groups: Dict[tuple[str, str, str, Optional[str]], Dict[str, Any]] = {}
        skipped_detail: List[dict] = []  # [{"row": int, "reason": str}, ...]
        for row_idx, row_tuple in enumerate(data_rows, start=2):  # Excel row 2 = first data row
            doc_no, item_code, location, qty, line_spo = row_tuple
            if not doc_no:
                skipped_detail.append({"row": row_idx, "reason": "Missing doc no"})
                job_service.update_job_progress(job_id_str, total_rows=total_data_rows, processed_rows=row_idx - 1, skipped_rows=len(skipped_detail))
                continue
            if not item_code:
                skipped_detail.append({"row": row_idx, "reason": "Missing item code"})
                job_service.update_job_progress(job_id_str, total_rows=total_data_rows, processed_rows=row_idx - 1, skipped_rows=len(skipped_detail))
                continue
            if not location:
                skipped_detail.append({"row": row_idx, "reason": "Missing location"})
                job_service.update_job_progress(job_id_str, total_rows=total_data_rows, processed_rows=row_idx - 1, skipped_rows=len(skipped_detail))
                continue
            if qty <= 0:
                skipped_detail.append({"row": row_idx, "reason": "Invalid quantity"})
                job_service.update_job_progress(job_id_str, total_rows=total_data_rows, processed_rows=row_idx - 1, skipped_rows=len(skipped_detail))
                continue
            header = headers_by_number.get(doc_no)
            if not header:
                skipped_detail.append({"row": row_idx, "reason": f"GRN header not found: {doc_no}"})
                job_service.update_job_progress(job_id_str, total_rows=total_data_rows, processed_rows=row_idx - 1, skipped_rows=len(skipped_detail))
                continue
            _hdr_spo = getattr(header, "spo_number", None)
            hdr_spo = str(_hdr_spo).strip() if (_hdr_spo is not None and str(_hdr_spo).strip()) else None
            effective_spo: Optional[str] = line_spo if line_spo else hdr_spo
            product = products_by_code.get((item_code or "").strip())
            warehouse = warehouses_map.get(normalize_code(location)) if location else None
            if not product:
                skipped_detail.append({"row": row_idx, "reason": f"Product not found: {item_code}"})
                job_service.update_job_progress(job_id_str, total_rows=total_data_rows, processed_rows=row_idx - 1, skipped_rows=len(skipped_detail))
                continue
            if not warehouse:
                skipped_detail.append({"row": row_idx, "reason": f"Warehouse not found: {location}"})
                job_service.update_job_progress(job_id_str, total_rows=total_data_rows, processed_rows=row_idx - 1, skipped_rows=len(skipped_detail))
                continue
            # Group by (doc_no, product_id, warehouse_id, effective_spo) so line-level SPO (e.g. From Doc. No.) is not merged across SPOs.
            key = (doc_no, str(product.id), str(warehouse.id), effective_spo)
            if key not in groups:
                groups[key] = {"qty": 0, "warehouse_id": str(warehouse.id)}
            groups[key]["qty"] += qty
            job_service.update_job_progress(job_id_str, total_rows=total_data_rows, processed_rows=row_idx - 1, skipped_rows=len(skipped_detail))

        # After grouping phase: all data rows are "processed"; skipped count is final for this phase
        job_service.update_job_progress(
            job_id_str,
            total_rows=total_data_rows,
            processed_rows=total_data_rows,
            successful_rows=0,
            failed_rows=0,
            skipped_rows=len(skipped_detail),
        )

        # FIFO matching: match SPO allocations by spo_number + product (ignore warehouse)
        # Process GR lines grouped by (doc_no, product_id) to share SPO pool FIFO
        successful = 0
        failed = 0
        errors: List[str] = []
        successful_detail: List[Dict[str, Any]] = []

        def _record_success(grn_number: str, product_id: str, warehouse_id: str, qty: int) -> None:
            successful_detail.append({
                "grn_number": grn_number,
                "product_code": product_id_to_code.get(product_id, product_id),
                "warehouse": warehouse_id_to_display.get(warehouse_id, warehouse_id),
                "quantity": qty,
            })

        # Group GR lines by (doc_no, product_id, effective_spo) for FIFO SPO matching
        # Keep warehouse info for creating picking lines
        gr_lines_by_product: Dict[tuple, List[tuple]] = defaultdict(list)
        for (doc_no, product_id, warehouse_id, effective_spo), group_data in groups.items():
            header = headers_by_number.get(doc_no)
            if not header:
                failed += 1
                continue
            gr_lines_by_product[(doc_no, product_id, effective_spo)].append((warehouse_id, group_data["qty"], header))

        # Process each (doc_no, product, effective_spo) group with shared FIFO SPO pool
        for (doc_no, product_id, effective_spo), gr_line_list in gr_lines_by_product.items():
            header = headers_by_number.get(doc_no)
            if not header:
                failed += 1
                continue

            spo_number: Optional[str] = effective_spo
            if not spo_number:
                # No SPO number, create all lines without spo_allocation_id
                for warehouse_id, qty, hdr in gr_line_list:
                    try:
                        proc.upsert_grn_line_for_import(
                            picking_header_id=hdr.id,
                            product_id=product_id,
                            source_warehouse_id=warehouse_id,
                            quantity=qty,
                            spo_allocation_id=None,
                        )
                        successful += 1
                        _record_success(doc_no, product_id, warehouse_id, qty)
                    except Exception as e:
                        failed += 1
                        errors.append(str(e))
                continue

            # Get all SPO allocations for this product, then filter by normalized spo_number
            # (SPO numbers may use / or . e.g. SPO-2026/01-0178 vs SPO-2026.01-0178)
            spo_normalized = _normalize_spo_number(spo_number)
            all_allocations = (
                db.query(SPOAllocation)
                .filter(SPOAllocation.product_id == product_id)
                .order_by(SPOAllocation.created_at.asc())
                .all()
            )
            def _alloc_spo_val(a: Any) -> str:
                v = a.spo_number
                return str(v) if v is not None else ""
            spo_allocations = [a for a in all_allocations if _normalize_spo_number(_alloc_spo_val(a)) == spo_normalized]

            # Build pool: (alloc_id, alloc_warehouse_id, available) FIFO by created_at.
            # FIFO from SPO allocation: prefer allocation whose warehouse matches GR line location.
            spo_pool: List[List[Any]] = []
            for alloc in spo_allocations:
                available_val = int(cast(int, alloc.allocated_quantity or 0)) - int(cast(int, alloc.quantity_received or 0))
                if available_val > 0:
                    spo_pool.append([str(alloc.id), str(alloc.warehouse_id), available_val])  # mutable for in-place update

            for warehouse_id, gr_qty, hdr in gr_line_list:
                remaining_qty = gr_qty

                # First pass: consume from allocations with same warehouse (location match) FIFO
                for entry in spo_pool:
                    alloc_id, alloc_wh, avail = entry
                    if alloc_wh != warehouse_id or avail <= 0 or remaining_qty <= 0:
                        continue
                    take_qty = min(remaining_qty, avail)
                    try:
                        proc.upsert_grn_line_for_import(
                            picking_header_id=hdr.id,
                            product_id=product_id,
                            source_warehouse_id=warehouse_id,
                            quantity=take_qty,
                            spo_allocation_id=alloc_id,
                        )
                        successful += 1
                        _record_success(doc_no, product_id, warehouse_id, take_qty)
                        remaining_qty -= take_qty
                        entry[2] = avail - take_qty
                    except Exception as e:
                        failed += 1
                        errors.append(str(e))

                # Second pass: consume from other allocations FIFO
                for entry in spo_pool:
                    alloc_id, alloc_wh, avail = entry
                    if alloc_wh == warehouse_id or avail <= 0 or remaining_qty <= 0:
                        continue
                    take_qty = min(remaining_qty, avail)
                    try:
                        proc.upsert_grn_line_for_import(
                            picking_header_id=hdr.id,
                            product_id=product_id,
                            source_warehouse_id=warehouse_id,
                            quantity=take_qty,
                            spo_allocation_id=alloc_id,
                        )
                        successful += 1
                        _record_success(doc_no, product_id, warehouse_id, take_qty)
                        remaining_qty -= take_qty
                        entry[2] = avail - take_qty
                    except Exception as e:
                        failed += 1
                        errors.append(str(e))

                if remaining_qty > 0:
                    try:
                        proc.upsert_grn_line_for_import(
                            picking_header_id=hdr.id,
                            product_id=product_id,
                            source_warehouse_id=warehouse_id,
                            quantity=remaining_qty,
                            spo_allocation_id=None,
                        )
                        successful += 1
                        _record_success(doc_no, product_id, warehouse_id, remaining_qty)
                    except Exception as e:
                        failed += 1
                        errors.append(str(e))

            job_service.update_job_progress(
                job_id_str,
                total_rows=total_data_rows,
                processed_rows=total_data_rows,
                successful_rows=successful,
                failed_rows=failed,
                skipped_rows=len(skipped_detail),
            )

        db.commit()

        # After GRN lines import: reflect received quantities to SPO allocations (confirmed GRN)
        for header in headers_by_number.values():
            try:
                proc.sync_grn_received_to_spo(header.id)
            except Exception as e:
                logger.warning("Sync GRN received to SPO failed for header %s: %s", header.id, e)

        job_service.complete_job(
            job_id=job_id_str,
            result={
                "message": "GRN lines import completed",
                "errors": _json_safe(errors[-100:]),
                "skipped_rows_detail": _json_safe(skipped_detail[-500:]),
                "successful_rows_detail": _json_safe(successful_detail[-500:]),
            },
            successful_rows=successful,
            failed_rows=failed,
            skipped_rows=len(skipped_detail),
            processed_rows=total_data_rows,
            total_rows=total_data_rows,
        )
        logger.info("GRN lines import job %s completed: %s ok, %s failed", job_id_str, successful, failed)
    except Exception as e:
        logger.exception("GRN lines import job %s failed", job_id_str)
        job_service.fail_job(job_id_str, str(e))
    finally:
        db.close()


def _delivery_order_detail_normalize_header(value: Any) -> str:
    """Normalize column header for delivery order detail import."""
    if value is None:
        return ""
    s = str(value).strip().lower()
    if not s:
        return ""
    return s


def _decimal_or_none(value: Any) -> Optional[Decimal]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _decimal_or_none_pct(value: Any) -> Optional[Decimal]:
    """Decimal parser that also accepts trailing '%'. Returns the percent value as a Decimal
    (e.g. '45%' -> Decimal('45')). Empty / unparseable -> None."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("%"):
        s = s[:-1].strip()
        if not s:
            return None
    try:
        return Decimal(s)
    except Exception:
        return None


def _norm_decimal_for_key(v: Any) -> Decimal:
    """Normalize a Decimal-or-None for composite-key equality. None -> 0."""
    if v is None:
        return Decimal("0")
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal("0")


def process_delivery_order_detail_import(db_job_id: str, file_data: bytes, filename: str, user_id: str):
    """Process delivery order detail Excel: one new order line per spreadsheet row.
    Columns: doc no -> order (order_number), item code -> product, location -> warehouse,
    qty, unit price, discount, total, tax, total excluding tax, total including tax.
    Duplicate product+warehouse on the same order produce separate lines (sequenced).
    """
    from rq import get_current_job
    import openpyxl
    from app.api.v1.external.utils import normalize_code

    db = SessionLocal()
    job_service = JobService(db)
    rq_job = get_current_job()
    rq_job_id = rq_job.id if rq_job else None
    job = job_service.get_job_by_db_id(db_job_id) if db_job_id else None
    if not job and rq_job_id:
        job = job_service.get_job(rq_job_id)
    if not job:
        logger.error("Delivery order detail import job not found: db_job_id=%s", db_job_id)
        db.close()
        return

    job_id_str = str(job.job_id)
    try:
        job_service.start_job(job_id_str)
        try:
            workbook = openpyxl.load_workbook(BytesIO(file_data), data_only=True)
        except Exception as exc:
            job_service.fail_job(job_id_str, f"Failed to read Excel: {exc}")
            db.close()
            return

        sheet = workbook.active
        if not sheet:
            job_service.fail_job(job_id_str, "Workbook has no active sheet")
            db.close()
            return

        headers = [_delivery_order_detail_normalize_header(cell.value) for cell in sheet[1]]
        data_rows: List[Dict[str, Any]] = []
        all_doc_nos = set()
        all_product_codes = set()
        all_locations = set()

        for row in sheet.iter_rows(min_row=2, values_only=True):
            if not any(cell is not None and str(cell).strip() for cell in row):
                continue
            row_data = {}
            for idx, value in enumerate(row):
                if idx < len(headers) and headers[idx]:
                    row_data[headers[idx]] = value

            def _find(row_d: dict, *candidates: str) -> Any:
                for c in candidates:
                    cl = c.lower().strip()
                    if cl in row_d:
                        return row_d.get(cl)
                return None

            doc_no = (_find(row_data, "doc no", "doc number", "order number") and str(_find(row_data, "doc no", "doc number", "order number")).strip()) or None
            item_code = (_find(row_data, "item code", "product code") and str(_find(row_data, "item code", "product code")).strip()) or None
            location = (_find(row_data, "location", "warehouse", "warehouse code") and str(_find(row_data, "location", "warehouse", "warehouse code")).strip()) or None

            # Skip rows with no order-line identity (trailing formatted blanks, stray numeric defaults, etc.)
            if not doc_no and not item_code and not location:
                continue

            qty = _decimal_or_none(_find(row_data, "qty", "quantity"))
            unit_price = _decimal_or_none(_find(row_data, "unit price", "unit price "))
            discount = _decimal_or_none_pct(_find(row_data, "discount"))
            total = _decimal_or_none(_find(row_data, "total"))
            tax = _decimal_or_none(_find(row_data, "tax"))
            total_excl = _decimal_or_none(_find(row_data, "total excluding tax", "total excluding tax "))
            total_incl = _decimal_or_none(_find(row_data, "total including tax", "total including tax "))

            if doc_no:
                all_doc_nos.add(doc_no)
            if item_code:
                all_product_codes.add(item_code)
            if location:
                all_locations.add(location)
            data_rows.append({
                "doc_no": doc_no,
                "item_code": item_code,
                "location": location,
                "quantity": qty,
                "unit_price": unit_price,
                "discount": discount,
                "total": total,
                "tax": tax,
                "total_excluding_tax": total_excl,
                "total_including_tax": total_incl,
            })

        total_data_rows = len(data_rows)
        job_service.update_job_progress(job_id_str, total_rows=total_data_rows, processed_rows=0)

        if not data_rows:
            job_service.complete_job(
                job_id=job_id_str,
                result={"message": "No valid data rows"},
                successful_rows=0,
                failed_rows=0,
                skipped_rows=0,
                processed_rows=0,
                total_rows=total_data_rows,
            )
            db.close()
            return

        doc_strips = {(d or "").strip() for d in all_doc_nos if d}
        orders_by_number: Dict[str, Any] = {}
        if doc_strips:
            batch_orders = (
                db.query(Order)
                .filter(Order.deleted_at.is_(None), Order.order_number.in_(list(doc_strips)))
                .all()
            )
            by_order_number = {(o.order_number or "").strip(): o for o in batch_orders}
            for doc_no in all_doc_nos:
                o = by_order_number.get((doc_no or "").strip())
                if o:
                    orders_by_number[doc_no] = o

        products_by_code = get_products_by_code_exact(db, all_product_codes)
        warehouses_map = get_warehouses_by_code_or_name(db, all_locations)

        # Next line_sequence per order (append after existing lines if key does not exist yet)
        seq_next: Dict[str, int] = {o.id: 0 for o in orders_by_number.values()}
        if seq_next:
            oids = list(seq_next.keys())
            for oid, mx in (
                db.query(OrderLine.order_id, func.max(OrderLine.line_sequence))
                .filter(OrderLine.order_id.in_(oids))
                .group_by(OrderLine.order_id)
                .all()
            ):
                seq_next[oid] = int(mx or 0)

        def _line_key(
            order_id: str,
            product_id: str,
            warehouse_id: str,
            quantity: Any,
            unit_price: Any,
            discount: Any,
            total: Any,
        ) -> tuple[str, str, str, Decimal, Decimal, Decimal, Decimal]:
            """Composite identity for an order line within an order. Same product+warehouse with
            different quantity/unit_price/discount/total are SEPARATE lines (no aggregation).
            Used both to deduplicate against existing rows on re-upload and to keep import
            rows distinct when source data has same product/warehouse repeated."""
            return (
                str(order_id),
                str(product_id),
                str(warehouse_id),
                _norm_decimal_for_key(quantity),
                _norm_decimal_for_key(unit_price),
                _norm_decimal_for_key(discount),
                _norm_decimal_for_key(total),
            )

        # Resolve each import row to a per-row entry. NO pre-aggregation — every row stays distinct
        # so two source rows with same product/warehouse but different price/discount produce two
        # separate order lines, matching the source spreadsheet.
        resolved_rows: List[Dict[str, Any]] = []
        successful = 0
        failed = 0
        skipped = 0
        errors: List[Dict[str, Any]] = []
        progress_every = max(100, min(500, total_data_rows // 50 or 100))

        for row_idx, row_data in enumerate(data_rows, start=2):
            try:
                doc_no = row_data.get("doc_no")
                item_code = row_data.get("item_code")
                location = row_data.get("location")
                if not doc_no:
                    skipped += 1
                    errors.append({"row": row_idx, "error": "Missing doc no"})
                    continue
                if not item_code:
                    skipped += 1
                    errors.append({"row": row_idx, "error": "Missing item code"})
                    continue
                if not location:
                    skipped += 1
                    errors.append({"row": row_idx, "error": "Missing location"})
                    continue

                order = orders_by_number.get(doc_no)
                product = products_by_code.get((item_code or "").strip())
                warehouse = warehouses_map.get(normalize_code(location)) if location else None
                if not order:
                    skipped += 1
                    errors.append({"row": row_idx, "error": f"Order not found: {doc_no}"})
                    continue
                if not product:
                    skipped += 1
                    errors.append({"row": row_idx, "error": f"Product not found: {item_code}"})
                    continue
                if not warehouse:
                    skipped += 1
                    errors.append({"row": row_idx, "error": f"Warehouse not found: {location}"})
                    continue

                resolved_rows.append({
                    "row_idx": row_idx,
                    "order_id": str(order.id),
                    "product_id": str(product.id),
                    "warehouse_id": str(warehouse.id),
                    "quantity": row_data.get("quantity"),
                    "unit_price": row_data.get("unit_price"),
                    "discount": row_data.get("discount"),
                    "total": row_data.get("total"),
                    "tax": row_data.get("tax"),
                    "total_excluding_tax": row_data.get("total_excluding_tax"),
                    "total_including_tax": row_data.get("total_including_tax"),
                })
            finally:
                cur = row_idx - 1
                if cur % progress_every == 0 or cur == total_data_rows:
                    job_service.update_job_progress(
                        job_id_str,
                        processed_rows=cur,
                        successful_rows=successful,
                        failed_rows=failed,
                        skipped_rows=skipped,
                    )

        # Load existing lines for the involved orders and count multiplicity per composite key.
        # Re-uploading an incremental file should NOT create duplicates: for each incoming row,
        # if an unmatched existing line with the identical composite key remains, we consume it
        # (skip insert); only the surplus (new rows in the file) becomes new OrderLine inserts.
        order_ids = list({r["order_id"] for r in resolved_rows})
        existing_remaining: Dict[
            tuple[str, str, str, Decimal, Decimal, Decimal, Decimal],
            int,
        ] = {}
        if order_ids:
            existing_lines = (
                db.query(OrderLine)
                .filter(OrderLine.order_id.in_(order_ids))
                .all()
            )
            for line in existing_lines:
                ex_key = _line_key(
                    str(line.order_id),
                    str(line.product_id),
                    str(line.warehouse_id),
                    getattr(line, "quantity", None),
                    getattr(line, "unit_price", None),
                    getattr(line, "discount", None),
                    getattr(line, "total", None),
                )
                existing_remaining[ex_key] = existing_remaining.get(ex_key, 0) + 1

        for entry in resolved_rows:
            try:
                key = _line_key(
                    entry["order_id"],
                    entry["product_id"],
                    entry["warehouse_id"],
                    entry["quantity"],
                    entry["unit_price"],
                    entry["discount"],
                    entry["total"],
                )
                if existing_remaining.get(key, 0) > 0:
                    existing_remaining[key] -= 1
                    skipped += 1
                    continue

                seq_next[entry["order_id"]] += 1
                new_line = OrderLine(
                    order_id=entry["order_id"],
                    product_id=entry["product_id"],
                    warehouse_id=entry["warehouse_id"],
                    line_sequence=seq_next[entry["order_id"]],
                    quantity=entry.get("quantity") or Decimal("0"),
                    unit_price=entry.get("unit_price"),
                    discount=entry.get("discount"),
                    total=entry.get("total"),
                    tax=entry.get("tax"),
                    total_excluding_tax=entry.get("total_excluding_tax"),
                    total_including_tax=entry.get("total_including_tax"),
                )
                db.add(new_line)
                successful += 1
            except Exception as e:
                failed += 1
                errors.append({"row": entry.get("row_idx"), "error": str(e)})

        db.commit()
        job_service.complete_job(
            job_id=job_id_str,
            result={
                "message": "Delivery order detail import completed",
                "errors": _json_safe(errors[:100]),
            },
            successful_rows=successful,
            failed_rows=failed,
            skipped_rows=skipped,
            processed_rows=total_data_rows,
            total_rows=total_data_rows,
        )
        logger.info("Delivery order detail import job %s completed: %s ok, %s failed, %s skipped", job_id_str, successful, failed, skipped)
    except Exception as e:
        logger.exception("Delivery order detail import job %s failed", job_id_str)
        job_service.fail_job(job_id_str, str(e))
    finally:
        db.close()
