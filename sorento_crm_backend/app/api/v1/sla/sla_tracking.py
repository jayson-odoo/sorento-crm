"""SLA tracking API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user
from app.services.sla_service import ConversationSLATrackingService
from app.schemas.sla import ConversationSLATrackingCreate, ConversationSLATrackingUpdate, ConversationSLATrackingResponse
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error

router = APIRouter()


@router.get("/dashboard")
async def get_sla_tracking_dashboard(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get dashboard metrics for SLA tracking."""
    try:
        service = ConversationSLATrackingService(db)
        metrics = service.get_dashboard_metrics()
        return metrics
    except Exception as e:
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_sla_tracking_dashboard: {str(e)}")
        logger.error(traceback.format_exc())
        raise handle_internal_error(str(e))


@router.get("/", response_model=ListResponse[ConversationSLATrackingResponse])
async def get_sla_tracking(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    policy_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get SLA tracking records with pagination."""
    try:
        service = ConversationSLATrackingService(db)
        result = service.list_tracking(page=page, limit=limit, policy_id=policy_id)
        return result
    except Exception as e:
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_sla_tracking: {str(e)}")
        logger.error(traceback.format_exc())
        raise handle_internal_error(str(e))


@router.get("/{tracking_id}", response_model=ConversationSLATrackingResponse)
async def get_sla_tracking_record(
    tracking_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single SLA tracking record by ID."""
    try:
        service = ConversationSLATrackingService(db)
        tracking = service.get_tracking(tracking_id)
        return tracking
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/", response_model=ConversationSLATrackingResponse, status_code=status.HTTP_201_CREATED)
async def create_sla_tracking(
    tracking_data: ConversationSLATrackingCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new SLA tracking record."""
    try:
        service = ConversationSLATrackingService(db)
        tracking = service.create_tracking(tracking_data)
        return tracking
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{tracking_id}", response_model=ConversationSLATrackingResponse)
async def update_sla_tracking(
    tracking_id: str,
    tracking_data: ConversationSLATrackingUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an SLA tracking record."""
    try:
        service = ConversationSLATrackingService(db)
        tracking = service.update_tracking(tracking_id, tracking_data)
        return tracking
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
