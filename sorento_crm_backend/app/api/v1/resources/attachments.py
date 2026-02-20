"""Attachments API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status, UploadFile, File, Form, Response, Request, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional, List
import uuid
import hashlib
import logging
import os
import json
import zipfile
import io
import threading
import mimetypes
from app.database import get_db
from app.dependencies import get_current_user
from app.services.resources_service import AttachmentService, AttachmentTypeService, AttachmentDirectoryService
from app.services.integration_service import IntegrationLogService
from app.schemas.resources import AttachmentCreate, AttachmentUpdate, AttachmentResponse, AttachmentBulkDeleteRequest, AttachmentReorderRequest
from app.schemas.integration import IntegrationLogCreate
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

logger = logging.getLogger(__name__)

router = APIRouter()


def _create_and_send_webhook(
    db: Session,
    attachment,
    attachment_type,
    access_levels_payload: Optional[list],
    current_user_id: str,
):
    """Delegate to shared helper (used by single upload and bulk-import task)."""
    from app.services.attachment_webhook_helper import create_and_send_webhook
    create_and_send_webhook(db, attachment, attachment_type, access_levels_payload, current_user_id)


def _enrich_uploaded_by_user(db, attachment) -> Optional[dict]:
    """Resolve uploaded_by UUID to user name/email for display. Returns UploadedByUser dict or None."""
    from app.schemas.resources import UploadedByUser
    from app.models.user import User

    uploaded_by = getattr(attachment, "uploaded_by", None)
    if not uploaded_by:
        return None
    try:
        user_id = str(uploaded_by)
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            display_name = (user.name or "").strip() or (user.email or None)
            return UploadedByUser(
                id=str(user.id),
                name=display_name,
                email=user.email or None,
            ).model_dump()
    except Exception as e:
        logger.warning("Could not resolve uploaded_by user for attachment %s: %s", getattr(attachment, "id"), e)
    return None


@router.get("/", response_model=ListResponse[AttachmentResponse])
async def get_attachments(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    query: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    dir: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    directory_id: Optional[str] = Query(None),
    is_deleted: Optional[bool] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get attachments with pagination and filtering (optional directory_id, query by filename, is_deleted for trash)."""
    try:
        service = AttachmentService(db)
        result = service.list_attachments(
            page=page,
            limit=limit,
            query=query,
            sort=sort,
            dir=dir or "desc",
            entity_type=entity_type,
            entity_id=entity_id,
            directory_id=directory_id,
            is_deleted=is_deleted,
        )
        # Enrich each attachment with uploaded_by_user for display
        enriched = []
        for att in result["data"]:
            data = AttachmentResponse.model_validate(att).model_dump()
            user_info = _enrich_uploaded_by_user(db, att)
            if user_info:
                data["uploaded_by_user"] = user_info
            enriched.append(data)
        result["data"] = enriched
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


def _attachment_response_with_linked_entities(service: AttachmentService, attachment) -> dict:
    """Build attachment response dict including linked entities from product_attachments, promotion_attachments, forms."""
    from app.schemas.resources import AttachmentResponse, LinkedEntityRef

    attachment_id = str(attachment.id) if attachment.id else attachment.id
    data = AttachmentResponse.model_validate(attachment).model_dump()
    linked = service.get_linked_entities(attachment_id)
    data["linked_products"] = [LinkedEntityRef.model_validate(p).model_dump() for p in linked["linked_products"]]
    data["linked_promotions"] = [LinkedEntityRef.model_validate(p).model_dump() for p in linked["linked_promotions"]]
    data["linked_form"] = LinkedEntityRef.model_validate(linked["linked_form"]).model_dump() if linked["linked_form"] else None
    if linked["linked_products"]:
        data["entity_display_name"] = linked["linked_products"][0]["name"]
    elif linked["linked_promotions"]:
        data["entity_display_name"] = linked["linked_promotions"][0]["name"]
    elif linked["linked_form"]:
        data["entity_display_name"] = linked["linked_form"]["name"]
    else:
        data["entity_display_name"] = service.get_entity_display_name(
            attachment.entity_type, attachment.entity_id
        )
    user_info = _enrich_uploaded_by_user(service.db, attachment)
    if user_info:
        data["uploaded_by_user"] = user_info
    return data


@router.get("/{attachment_id}", response_model=AttachmentResponse)
async def get_attachment(
    attachment_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single attachment by ID."""
    try:
        service = AttachmentService(db)
        attachment = service.get_attachment(attachment_id)
        return _attachment_response_with_linked_entities(service, attachment)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=AttachmentResponse, status_code=status.HTTP_201_CREATED)
async def create_attachment(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    attachment_type_id: str = Form(...),
    entity_type: Optional[str] = Form(None),
    entity_id: Optional[str] = Form(None),
    directory_id: Optional[str] = Form(None),
    access_levels: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload a new attachment to S3."""
    try:
        # Debug: Log request details
        logger.info(f"Content-Type: {request.headers.get('content-type')}")
        logger.info(f"File received: {file.filename if file else 'None'}")
        logger.info(f"Attachment type ID: {attachment_type_id}")
        
        # Validate file is provided
        if not file or not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File is required"
            )
        from app.services.s3_service import S3Service
        
        # Read file content
        file_content = await file.read()
        file_size = len(file_content)
        
        # Calculate SHA-256 hash for duplicate detection
        file_hash = hashlib.sha256(file_content).hexdigest()
        
        # Generate stored filename
        file_uuid = str(uuid.uuid4())
        original_filename = file.filename or "unknown"
        # Sanitize filename - remove special characters that might cause issues
        safe_filename = "".join(c for c in original_filename if c.isalnum() or c in (' ', '-', '_', '.')).strip()
        stored_filename = f"{file_uuid}-{safe_filename}"
        
        # Get attachment type to determine entity_type if not provided
        type_service = AttachmentTypeService(db)
        attachment_type = None
        if attachment_type_id:
            try:
                attachment_type = type_service.get_type(attachment_type_id)
            except HTTPException:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid attachment type ID"
                )
        
        # Determine entity_type:
        # 1. Use provided entity_type if given
        # 2. Otherwise, use attachment_type.type_name (sanitized for S3 path)
        # 3. Fallback to "general"
        if entity_type:
            final_entity_type = entity_type.lower().replace(' ', '_')
        elif attachment_type:
            final_entity_type = attachment_type.type_name.lower().replace(' ', '_')
        else:
            final_entity_type = "general"
        
        # Construct S3 key: {entity_type}/{stored_filename}
        s3_file_path = f"{final_entity_type}/{stored_filename}"
        
        # Upload to S3
        s3_service = S3Service()
        try:
            s3_key, s3_url = s3_service.upload_file(
                file_content=file_content,
                file_path=s3_file_path,
                content_type=file.content_type
            )
        except Exception as s3_error:
            logger.error(f"S3 upload failed: {str(s3_error)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload file to storage: {str(s3_error)}"
            )
        
        # Parse access levels for attachment record and webhook (JSON array string expected)
        access_levels_payload = None
        if access_levels:
            try:
                parsed = json.loads(access_levels)
                if isinstance(parsed, list):
                    access_levels_payload = parsed
            except Exception:
                logger.warning("Invalid access_levels payload; expected JSON array.")
        if not access_levels_payload:
            access_levels_payload = ["dealer", "end_user"]

        # Create attachment record
        attachment_data = AttachmentCreate(
            attachment_type_id=attachment_type_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_path=s3_url,  # Store S3 URL (https://...)
            file_size_bytes=file_size,
            mime_type=file.content_type or "application/octet-stream",  # Default if None
            file_hash=file_hash,
            entity_type=entity_type,  # Store original entity_type if provided
            entity_id=entity_id,
            directory_id=directory_id,
            access_levels=access_levels_payload,
        )
        
        service = AttachmentService(db)
        attachment = service.create_attachment(attachment_data, current_user["id"])
        try:
            _create_and_send_webhook(db, attachment, attachment_type, access_levels_payload or attachment.access_levels, current_user["id"])
        except Exception as e:
            logger.error("Failed to create integration log for attachment %s: %s", attachment.id, e, exc_info=True)
        return attachment
    
    except HTTPException:
        raise
    except ValueError as e:
        # S3 configuration error (missing or empty env vars)
        logger.error(f"S3 configuration error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e) or "S3 storage is not properly configured. Set AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_S3_BUCKET_NAME in the backend environment."
        )
    except Exception as e:
        import traceback
        error_msg = str(e)
        logger.error(f"Error in create_attachment: {error_msg}")
        logger.error(traceback.format_exc())
        
        # If it's a validation error, return more details
        if "validation" in error_msg.lower() or "422" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Validation error: {error_msg}"
            )
        
        raise handle_internal_error(error_msg)


def _normalize_zip_path(name: str) -> str:
    """Normalize zip entry name: strip slashes, use forward slash."""
    return name.replace("\\", "/").strip("/")


@router.post("/bulk-import", status_code=status.HTTP_202_ACCEPTED)
async def bulk_import_attachments(
    file: UploadFile = File(..., description="ZIP file containing folders and files"),
    attachment_type_id: str = Form(...),
    access_levels: Optional[str] = Form(None),
    parent_directory_id: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Queue a ZIP import job. Import runs in the background with batch processing. Poll GET /api/v1/system/jobs/{job_id}/status for progress."""
    import tempfile
    import os

    if not file or not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A ZIP file is required")

    type_service = AttachmentTypeService(db)
    try:
        type_service.get_type(attachment_type_id)
    except HTTPException:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid attachment type ID")

    zip_content = await file.read()
    try:
        with zipfile.ZipFile(io.BytesIO(zip_content), "r") as zf:
            zf.testzip()
    except zipfile.BadZipFile:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or corrupted ZIP file")

    # Save ZIP to temp file instead of passing bytes to Redis (avoids BrokenPipe on large files)
    fd, zip_path = tempfile.mkstemp(suffix=".zip")
    try:
        os.write(fd, zip_content)
    finally:
        os.close(fd)

    from app.services.job_service import JobService
    from app.services.queue_service import enqueue_job
    from app.tasks.import_tasks import process_attachment_bulk_import

    job_service = JobService(db)
    job = job_service.create_job(
        job_type="attachment_bulk_import",
        user_id=current_user["id"],
        filename=file.filename,
        metadata={
            "attachment_type_id": attachment_type_id,
            "parent_directory_id": parent_directory_id,
        },
    )
    db.commit()

    rq_job = enqueue_job(
        process_attachment_bulk_import,
        str(job.id),
        zip_path,
        attachment_type_id,
        access_levels or "[]",
        parent_directory_id,
        current_user["id"],
        queue_name="imports",
        job_timeout=7200,
    )
    job_service.update_job_with_rq_id(job, rq_job.id)

    return {
        "message": "Import started. Processing in the background. You can close this dialog.",
        "job_id": job.job_id,
        "id": str(job.id),
    }


@router.put("/{attachment_id}", response_model=AttachmentResponse)
async def update_attachment(
    attachment_id: str,
    attachment_data: AttachmentUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an attachment."""
    try:
        service = AttachmentService(db)
        attachment = service.update_attachment(attachment_id, attachment_data)
        return attachment
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{attachment_id}/download")
async def download_attachment(
    attachment_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Download an attachment file from S3."""
    try:
        service = AttachmentService(db)
        attachment = service.get_attachment(attachment_id)
        
        # Get file content from S3
        file_content = service.get_file_content(attachment_id)
        
        # Return file as streaming response
        return Response(
            content=file_content,
            media_type=attachment.mime_type or "application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{attachment.original_filename}"',
                "Content-Length": str(attachment.file_size_bytes or len(file_content))
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"Error in download_attachment: {str(e)}")
        logger.error(traceback.format_exc())
        raise handle_internal_error(str(e))


@router.get("/{attachment_id}/metadata", response_model=AttachmentResponse)
async def get_attachment_metadata(
    attachment_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get attachment metadata without downloading the file."""
    try:
        service = AttachmentService(db)
        attachment = service.get_attachment(attachment_id)
        return _attachment_response_with_linked_entities(service, attachment)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{attachment_id}", status_code=status.HTTP_200_OK)
async def delete_attachment(
    attachment_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete an attachment permanently (hard delete). Use archive for retention."""
    try:
        service = AttachmentService(db)
        result = service.delete_attachment(attachment_id, current_user["id"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{attachment_id}/archive", status_code=status.HTTP_200_OK)
async def archive_attachment(
    attachment_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Archive an attachment (soft delete). Data remains for retention. Use restore to unarchive."""
    try:
        service = AttachmentService(db)
        result = service.archive_attachment(attachment_id, current_user["id"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{attachment_id}/restore", status_code=status.HTTP_200_OK)
async def restore_attachment(
    attachment_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Restore an archived attachment."""
    try:
        service = AttachmentService(db)
        result = service.restore_attachment(attachment_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/bulk-archive", status_code=status.HTTP_200_OK)
async def bulk_archive_attachments(
    body: AttachmentBulkDeleteRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Archive multiple attachments (soft delete)."""
    try:
        service = AttachmentService(db)
        result = service.archive_attachments(body.attachment_ids, current_user["id"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/bulk-delete", status_code=status.HTTP_200_OK)
async def bulk_delete_attachments(
    body: AttachmentBulkDeleteRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mass delete attachments permanently (hard delete)."""
    try:
        service = AttachmentService(db)
        result = service.delete_attachments(body.attachment_ids, current_user["id"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/reorder", status_code=status.HTTP_200_OK)
async def reorder_attachments(
    body: AttachmentReorderRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reorder attachments within a folder (sets sort_order by list position)."""
    try:
        service = AttachmentService(db)
        result = service.reorder_attachments(body.attachment_ids, body.directory_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{attachment_id}/resubmit", status_code=status.HTTP_200_OK)
async def resubmit_attachment_webhook(
    attachment_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Resubmit attachment webhook to n8n without re-uploading the file."""
    try:
        # Verify attachment exists
        attachment_service = AttachmentService(db)
        attachment = attachment_service.get_attachment(attachment_id)
        
        # Find the integration log for this attachment
        integration_service = IntegrationLogService(db)
        logs_result = integration_service.list_integration_logs(
            page=1,
            limit=1,
            business_table="attachments",
            business_id=attachment_id,
            integration_channel="n8n"
        )
        
        if not logs_result.get("data") or len(logs_result["data"]) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No integration log found for this attachment. The attachment may not have been processed yet."
            )
        
        # Get the most recent log
        integration_log = logs_result["data"][0]
        
        # Resend the webhook
        success, error_msg = integration_service.send_webhook_for_log(integration_log.id)
        
        if success:
            return {
                "message": "Webhook resubmitted successfully",
                "integration_log_id": integration_log.id
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to resubmit webhook: {error_msg or 'Unknown error'}"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resubmitting attachment webhook: {str(e)}", exc_info=True)
        raise handle_internal_error(str(e))
