"""Integration logs API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
import logging
import traceback
from datetime import datetime
from app.database import get_db
from app.dependencies import get_current_user
from app.services.integration_service import IntegrationLogService
from app.schemas.integration import IntegrationLogResponse, IntegrationLogUpdateRequest
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", response_model=ListResponse[IntegrationLogResponse])
async def get_integration_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[str] = Query(None),
    integration_channel: Optional[str] = Query(None),
    business_table: Optional[str] = Query(None),
    business_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get integration logs with pagination and filtering."""
    try:
        logger.info(f"Getting integration logs: page={page}, limit={limit}, status={status}")
        service = IntegrationLogService(db)
        result = service.list_integration_logs(
            page=page,
            limit=limit,
            status=status,
            integration_channel=integration_channel,
            business_table=business_table,
            business_id=business_id
        )
        logger.info(f"Successfully retrieved {len(result.get('data', []))} integration logs")
        return result
    except Exception as e:
        error_traceback = traceback.format_exc()
        logger.error(f"Error getting integration logs: {str(e)}")
        logger.error(f"Traceback:\n{error_traceback}")
        raise handle_internal_error(str(e))


@router.get("/{log_id}", response_model=IntegrationLogResponse)
async def get_integration_log(
    log_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single integration log by ID."""
    try:
        service = IntegrationLogService(db)
        log = service.get_integration_log(log_id)
        return log
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{log_id}", response_model=IntegrationLogResponse)
async def update_integration_log(
    log_id: str,
    update_data: IntegrationLogUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update integration log status (called by n8n callback).
    
    This endpoint allows n8n to update the integration log after processing.
    """
    try:
        service = IntegrationLogService(db)
        
        # Prepare update data with processed timestamp
        from app.schemas.integration import IntegrationLogUpdate
        
        update_payload = IntegrationLogUpdate(
            status=update_data.status,
            status_code=update_data.status_code,
            response_payload=update_data.response_payload,
            error_code=update_data.error_code,
            error_message=update_data.error_message,
            processed_at=datetime.utcnow() if update_data.status in ["success", "failed"] else None
        )
        
        log = service.update_integration_log(log_id, update_payload)
        return log
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{log_id}/retry", response_model=IntegrationLogResponse)
async def retry_integration_log(
    log_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Manually retry sending webhook for an integration log."""
    try:
        service = IntegrationLogService(db)
        success, error_msg = service.send_webhook_for_log(log_id)
        
        # Get updated log
        log = service.get_integration_log(log_id)
        return log
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
