"""Attachments API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status, UploadFile, File, Form, Response, Request, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional
import uuid
import hashlib
import logging
import os
import json
from app.database import get_db
from app.dependencies import get_current_user
from app.services.resources_service import AttachmentService, AttachmentTypeService
from app.services.integration_service import IntegrationLogService
from app.schemas.resources import AttachmentCreate, AttachmentUpdate, AttachmentResponse, AttachmentBulkDeleteRequest
from app.schemas.integration import IntegrationLogCreate
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=ListResponse[AttachmentResponse])
async def get_attachments(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get attachments with pagination and filtering."""
    try:
        service = AttachmentService(db)
        result = service.list_attachments(
            page=page,
            limit=limit,
            entity_type=entity_type,
            entity_id=entity_id
        )
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


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
        return attachment
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
        
        # Parse access levels for webhook payload (JSON array string expected)
        access_levels_payload = None
        if access_levels:
            try:
                parsed = json.loads(access_levels)
                if isinstance(parsed, list):
                    access_levels_payload = parsed
            except Exception:
                logger.warning("Invalid access_levels payload; expected JSON array.")

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
            entity_id=entity_id
        )
        
        service = AttachmentService(db)
        attachment = service.create_attachment(attachment_data, current_user["id"])
        
        # Create integration log for n8n webhook after successful S3 upload and attachment creation
        try:
            n8n_webhook_url = os.getenv("N8N_WEBHOOK_URL", "").strip()
            if n8n_webhook_url:
                # Validate and fix URL - ensure it has http:// or https:// protocol
                if not n8n_webhook_url.startswith(('http://', 'https://')):
                    if n8n_webhook_url.startswith('//'):
                        n8n_webhook_url = 'https:' + n8n_webhook_url
                    elif '://' not in n8n_webhook_url:
                        # Auto-add https:// if no protocol specified
                        n8n_webhook_url = 'https://' + n8n_webhook_url
                        logger.warning(f"N8N_WEBHOOK_URL missing protocol, auto-adding https://. Fixed URL: {n8n_webhook_url}")
                integration_service = IntegrationLogService(db)
                
                # Create integration log with pending status first
                integration_log_data = IntegrationLogCreate(
                    integration_channel="n8n",
                    business_table="attachments",
                    business_id=attachment.id,
                    direction="outbound",
                    endpoint=n8n_webhook_url,
                    http_method="POST",
                    created_by=current_user["id"],
                    status="pending"
                )
                
                integration_log = integration_service.create_integration_log(integration_log_data)
                
                # Prepare webhook payload with actual integration_log_id and attachment_type name
                webhook_payload = {
                    "integration_log_id": integration_log.id,
                    "s3_url": s3_url,
                    "attachment_id": attachment.id,
                    "attachment_filename": attachment.original_filename,
                    "attachment_type": attachment_type.type_name if attachment_type else None,
                    "access_levels": access_levels_payload,
                }
                
                # Update log with payload containing the correct integration_log_id
                integration_log.request_payload = json.dumps(webhook_payload)
                db.commit()
                db.refresh(integration_log)
                
                # Send webhook asynchronously in background (non-blocking)
                # Using threading to ensure true async execution
                import threading
                def send_webhook_async():
                    try:
                        # Get a new database session for background task
                        from app.database import SessionLocal
                        bg_db = SessionLocal()
                        try:
                            bg_service = IntegrationLogService(bg_db)
                            bg_service.send_webhook_for_log(integration_log.id)
                        finally:
                            bg_db.close()
                    except Exception as e:
                        logger.error(f"Background webhook send failed for log {integration_log.id}: {str(e)}", exc_info=True)
                
                # Start background thread
                thread = threading.Thread(target=send_webhook_async, daemon=True)
                thread.start()
                
                logger.info(f"Created integration log {integration_log.id} for attachment {attachment.id}")
        except Exception as e:
            # Don't fail attachment upload if integration log creation fails
            logger.error(f"Failed to create integration log for attachment {attachment.id}: {str(e)}", exc_info=True)
        
        return attachment
    
    except HTTPException:
        raise
    except ValueError as e:
        # S3 configuration error
        logger.error(f"S3 configuration error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="S3 storage is not properly configured. Please contact administrator."
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
        return attachment
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
    """Delete an attachment (soft delete)."""
    try:
        service = AttachmentService(db)
        result = service.delete_attachment(attachment_id, current_user["id"])
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
    """Mass delete attachments (soft delete)."""
    try:
        service = AttachmentService(db)
        result = service.delete_attachments(body.attachment_ids, current_user["id"])
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
