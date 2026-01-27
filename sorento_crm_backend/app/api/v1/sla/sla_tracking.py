"""SLA tracking API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status, Request
from datetime import timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user_or_api_key
from app.services.sla_service import ConversationSLATrackingService
from app.services.integration_service import IntegrationLogService
from app.schemas.sla import (
    ConversationSLATrackingCreate,
    ConversationSLATrackingUpdate,
    ConversationSLATrackingResponse,
    ConversationSLAEventLogCreate,
    ConversationSLAEventLogResponse,
    ConversationSLATrackingStatusUpdate,
)
from app.schemas.integration import IntegrationLogCreate
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error, handle_validation_error

router = APIRouter()


@router.get("/dashboard")
async def get_sla_tracking_dashboard(
    current_user: dict = Depends(get_current_user_or_api_key),
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
    current_user: dict = Depends(get_current_user_or_api_key),
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


@router.post("/", response_model=ConversationSLATrackingResponse, status_code=status.HTTP_201_CREATED)
async def create_sla_tracking(
    tracking_data: ConversationSLATrackingCreate,
    current_user: dict = Depends(get_current_user_or_api_key),
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


@router.post("/integration", status_code=status.HTTP_200_OK)
async def create_sla_tracking_integration(
    tracking_data: ConversationSLATrackingCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create SLA tracking from integration and log the request."""
    try:
        service = ConversationSLATrackingService(db)
        tracking = service.create_tracking(tracking_data)

        log_service = IntegrationLogService(db)
        log_service.create_integration_log(
            IntegrationLogCreate(
                integration_channel="sla_tracking_creation",
                business_table="conversation_sla_tracking",
                business_id=tracking.id,
                external_reference=tracking.respond_contact_phone,
                direction="inbound",
                endpoint=str(request.url),
                http_method="POST",
                status="success"
            ),
            request_payload_dict=tracking_data.model_dump()
        )

        return {"status": "success", "message": "SLA tracking created successfully.", "tracking_id": tracking.id}
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{tracking_id}", response_model=ConversationSLATrackingResponse)
async def update_sla_tracking(
    tracking_id: UUID,
    tracking_data: ConversationSLATrackingUpdate,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Update an SLA tracking record."""
    try:
        tracking_id = str(tracking_id)
        service = ConversationSLATrackingService(db)
        tracking = service.update_tracking(tracking_id, tracking_data)
        return tracking
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{tracking_id}/escalate", response_model=ConversationSLAEventLogResponse, status_code=status.HTTP_201_CREATED)
async def escalate_sla_tracking(
    tracking_id: UUID,
    event_data: ConversationSLAEventLogCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create escalation event log for SLA tracking."""
    try:
        tracking_id = str(tracking_id)
        service = ConversationSLATrackingService(db)
        # Get the tracking to access assigned_to_id
        tracking = service.get_tracking(tracking_id)
        payload = ConversationSLAEventLogCreate(
            sla_tracking_id=tracking_id,
            event_type="escalation",
            from_tier=event_data.from_tier,
            to_tier=event_data.to_tier,
            event_at=event_data.event_at,
            reason=event_data.reason,
            assigned_to=event_data.assigned_to or tracking.assigned_to,  # Keep for backward compatibility
            assigned_to_id=event_data.assigned_to_id or tracking.assigned_to_id,
            due_at=event_data.due_at,
            response_time=event_data.response_time,
            resolution_time=event_data.resolution_time,
        )
        log = service.create_event_log(payload)

        log_service = IntegrationLogService(db)
        log_service.create_integration_log(
            IntegrationLogCreate(
                integration_channel="sla_escalation",
                business_table="conversation_sla_event_log",
                business_id=log.id,
                external_reference=tracking_id,
                direction="inbound",
                endpoint=str(request.url),
                http_method="POST",
                status="success"
            ),
            request_payload_dict=event_data.model_dump(exclude_unset=True)
        )

        return log
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


def _calculate_duration_hours(start_at, end_at) -> Decimal:
    """Calculate duration in hours with two-decimal precision."""
    start_at = start_at if start_at.tzinfo else start_at.replace(tzinfo=timezone.utc)
    end_at = end_at if end_at.tzinfo else end_at.replace(tzinfo=timezone.utc)
    hours = Decimal(str((end_at - start_at).total_seconds() / 3600))
    return hours.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@router.post("/integration/{tracking_id}", status_code=status.HTTP_200_OK)
@router.put("/integration/{tracking_id}", status_code=status.HTTP_200_OK)
async def update_sla_tracking_status_integration(
    tracking_id: UUID,
    update_data: ConversationSLATrackingStatusUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update SLA tracking status fields from integration and log the request."""
    try:
        tracking_id = str(tracking_id)
        service = ConversationSLATrackingService(db)
        tracking = service.get_tracking(tracking_id)

        if update_data.is_responded and not update_data.responded_at:
            raise handle_validation_error("responded_at is required when is_responded is true.")
        if update_data.is_resolved and not update_data.resolved_at:
            raise handle_validation_error("resolved_at is required when is_resolved is true.")

        update_dict = update_data.model_dump(exclude_unset=True)
        update_dict.pop("response_time", None)
        update_dict.pop("resolution_duration", None)
        update_dict.pop("resolution_time", None)

        if update_data.responded_at:
            update_dict["response_time"] = _calculate_duration_hours(
                tracking.current_tier_started_at, update_data.responded_at
            )
        if update_data.resolved_at:
            update_dict["resolution_duration"] = _calculate_duration_hours(
                tracking.current_tier_started_at, update_data.resolved_at
            )

        tracking = service.update_tracking(tracking_id, ConversationSLATrackingUpdate(**update_dict))

        # Create event logs for responded/resolved when applicable
        if update_data.is_responded:
            service.create_event_log(ConversationSLAEventLogCreate(
                sla_tracking_id=tracking_id,
                event_type="response",
                event_at=update_data.responded_at,
                response_time=update_dict.get("response_time"),
                assigned_to=tracking.assigned_to,  # Keep for backward compatibility
                assigned_to_id=tracking.assigned_to_id,
            ))

        if update_data.is_resolved:
            # Try to find user by resolved_by (might be name, email, or ID)
            resolved_by_user_id = None
            if tracking.resolved_by:
                from app.models.user import User
                resolved_user = db.query(User).filter(
                    (User.id == tracking.resolved_by) |
                    (User.respond_user_id == tracking.resolved_by) |
                    (User.email == tracking.resolved_by) |
                    (User.name == tracking.resolved_by)
                ).first()
                if resolved_user:
                    resolved_by_user_id = resolved_user.id
            
            service.create_event_log(ConversationSLAEventLogCreate(
                sla_tracking_id=tracking_id,
                event_type="resolution",
                event_at=update_data.resolved_at,
                resolution_time=update_dict.get("resolution_duration"),
                assigned_to=tracking.resolved_by,  # Keep for backward compatibility
                assigned_to_id=resolved_by_user_id,
            ))

        log_service = IntegrationLogService(db)
        log_service.create_integration_log(
            IntegrationLogCreate(
                integration_channel="sla_tracking_update",
                business_table="conversation_sla_tracking",
                business_id=tracking.id,
                external_reference=tracking.respond_contact_phone,
                direction="inbound",
                endpoint=str(request.url),
                http_method="PUT",
                status="success"
            ),
            request_payload_dict=update_data.model_dump(exclude_unset=True)
        )

        return {"status": "success", "message": "SLA tracking updated successfully.", "tracking_id": tracking.id}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/event-logs", response_model=ConversationSLAEventLogResponse, status_code=status.HTTP_201_CREATED)
async def create_event_log(
    event_data: ConversationSLAEventLogCreate,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Create a new SLA event log entry."""
    try:
        payload = event_data
        if event_data.assigned_to and not event_data.assigned_to_id:
            from app.models.user import User

            assigned_to_value = str(event_data.assigned_to).strip()
            user = db.query(User).filter(
                (User.respond_user_id == assigned_to_value) |
                (User.id == assigned_to_value) |
                (User.email == assigned_to_value)
            ).first()
            if not user:
                raise handle_validation_error(
                    f"User not found for respond_user_id: {assigned_to_value}"
                )
            payload = ConversationSLAEventLogCreate(
                **{**event_data.model_dump(exclude_unset=True), "assigned_to_id": user.id}
            )

        service = ConversationSLATrackingService(db)
        log = service.create_event_log(payload)
        return log
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/event-logs", response_model=ListResponse[ConversationSLAEventLogResponse])
async def get_event_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    tracking_id: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    assigned_to: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get SLA event logs with pagination and filtering."""
    try:
        service = ConversationSLATrackingService(db)
        result = service.list_event_logs(
            page=page,
            limit=limit,
            tracking_id=tracking_id,
            event_type=event_type,
            assigned_to=assigned_to
        )
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{tracking_id}", response_model=ConversationSLATrackingResponse)
async def get_sla_tracking_record(
    tracking_id: UUID,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get a single SLA tracking record by ID."""
    try:
        tracking_id = str(tracking_id)
        service = ConversationSLATrackingService(db)
        tracking = service.get_tracking(tracking_id)
        
        # Manually construct response to ensure policy and relationships are included
        from app.schemas.sla import ConversationSLATrackingResponse, ConversationSLAEventLogResponse
        
        # Get contact info from relationship
        contact_phone = tracking.contact.phone_number if tracking.contact else None
        contact_name = tracking.contact.name if tracking.contact else None
        
        # Get user info from relationship
        assigned_user_name = tracking.assigned_user.name if tracking.assigned_user else None
        assigned_user_email = tracking.assigned_user.email if tracking.assigned_user else None
        
        # Build event logs with user relationships
        event_logs_data = []
        if tracking.event_logs:
            for log in tracking.event_logs:
                log_data = {
                    "id": str(log.id),
                    "sla_tracking_id": str(log.sla_tracking_id),
                    "event_type": log.event_type,
                    "from_tier": log.from_tier,
                    "to_tier": log.to_tier,
                    "event_at": log.event_at,
                    "reason": log.reason,
                    "assigned_to": log.assigned_to,
                    "assigned_to_id": log.assigned_to_id,
                    "due_at": log.due_at,
                    "response_time": log.response_time,
                    "resolution_time": log.resolution_time,
                    "reminder_count": log.reminder_count,
                    "last_reminder_at": log.last_reminder_at,
                    "created_at": log.created_at,
                    "assigned_user": {
                        "id": log.assigned_user.id,
                        "email": log.assigned_user.email,
                        "name": log.assigned_user.name
                    } if log.assigned_user else None,
                    "assigned_user_name": log.assigned_user.name if log.assigned_user else None,
                    "assigned_user_email": log.assigned_user.email if log.assigned_user else None,
                }
                event_logs_data.append(log_data)
        
        # Construct response dict
        response_dict = {
            "id": str(tracking.id),
            "policy_id": str(tracking.policy_id),
            "current_tier": tracking.current_tier,
            "assigned_to": tracking.assigned_to,
            "assigned_to_id": tracking.assigned_to_id,
            "initiated_at": tracking.initiated_at,
            "current_tier_started_at": tracking.current_tier_started_at,
            "due_at": tracking.due_at,
            "escalated_at": tracking.escalated_at,
            "escalation_reason": tracking.escalation_reason,
            "is_responded": tracking.is_responded,
            "responded_at": tracking.responded_at,
            "response_time": tracking.response_time,
            "is_resolved": tracking.is_resolved,
            "resolved_at": tracking.resolved_at,
            "resolved_by": tracking.resolved_by,
            "respond_contact_id": tracking.respond_contact_id,
            "created_at": tracking.created_at,
            "updated_at": tracking.updated_at,
            "synced_to_excel": tracking.synced_to_excel,
            "last_synced_to_excel": tracking.last_synced_to_excel,
            "resolution_duration": tracking.resolution_duration,
            "policy": {
                "id": str(tracking.policy.id),
                "code": tracking.policy.code,
                "name": tracking.policy.name
            } if tracking.policy else None,
            "policy_code": tracking.policy.code if tracking.policy else None,
            "policy_name": tracking.policy.name if tracking.policy else None,
            "contact": {
                "id": tracking.contact.id,
                "phone_number": tracking.contact.phone_number,
                "name": tracking.contact.name
            } if tracking.contact else None,
            "assigned_user": {
                "id": tracking.assigned_user.id,
                "email": tracking.assigned_user.email,
                "name": tracking.assigned_user.name
            } if tracking.assigned_user else None,
            "contact_phone": contact_phone,
            "contact_name": contact_name,
            "assigned_user_name": assigned_user_name,
            "assigned_user_email": assigned_user_email,
            "event_logs": event_logs_data,
        }
        
        return ConversationSLATrackingResponse.model_validate(response_dict)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
