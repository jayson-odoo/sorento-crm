"""SLA tracking API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException, status, Request
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID
from sqlalchemy.orm import Session
from typing import Optional
import httpx
from app.database import get_db
from pydantic import BaseModel, Field
from app.dependencies import get_current_user_or_api_key, require_permission, get_current_user
from app.services.sla_service import (
    ConversationSLATrackingService,
    to_naive_datetime,
    compute_tracking_timings,
    event_log_assignee_fields,
)
from app.services.integration_service import IntegrationLogService
from app.schemas.sla import (
    ConversationSLATrackingCreate,
    ConversationSLATrackingUpdate,
    ConversationSLATrackingResponse,
    ConversationSLAEventLogCreate,
    ConversationSLAEventLogResponse,
    ConversationSLATrackingStatusUpdate,
    ConversationSLAEscalateRequest,
    ConversationSLATestOverrideRequest,
)
from app.schemas.integration import IntegrationLogCreate
from app.schemas.common import ListResponse
from app.services.error_handler import handle_internal_error, handle_validation_error, handle_not_found, AppException
from app.models.sla import ConversationSLATracking, SLAPolicyTier
from app.models.user import User

router = APIRouter()


class SlaTrackingConversationReplyBody(BaseModel):
    message: str = Field(..., min_length=1)


def _sla_reply_respond_user_id(current_user: dict) -> str:
    rid = (current_user or {}).get("respond_user_id") or (current_user or {}).get("respondUserId")
    if rid and str(rid).strip():
        return str(rid).strip()
    uid = (current_user or {}).get("id")
    if uid and str(uid).strip():
        return str(uid).strip()
    raise HTTPException(
        status_code=400,
        detail="User respond_user_id or id is required to send a message.",
    )


@router.get("/dashboard")
async def get_sla_tracking_dashboard(
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get dashboard metrics for SLA tracking."""
    import logging
    import traceback
    logger = logging.getLogger(__name__)
    try:
        service = ConversationSLATrackingService(db)
        metrics = service.get_dashboard_metrics()
        return metrics
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Error in get_sla_tracking_dashboard: {str(e)}")
        logger.error(tb)
        # Include detail in response for debugging (remove in production if desired)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": str(e), "type": type(e).__name__, "traceback": tb},
        )


@router.get("/", response_model=ListResponse[ConversationSLATrackingResponse])
async def get_sla_tracking(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    policy_id: Optional[str] = Query(None),
    query: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    dir: Optional[str] = Query(None),
    assigned_to: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get SLA tracking records with pagination. query searches contact phone and contact name."""
    try:
        service = ConversationSLATrackingService(db)
        result = service.list_tracking(
            page=page,
            limit=limit,
            policy_id=policy_id,
            query=query,
            sort_field=sort or "created_at",
            sort_dir=dir or "desc",
            assigned_to=assigned_to,
        )
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
    request: Request,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Create a new SLA tracking record."""
    log_service = IntegrationLogService(db)
    try:
        service = ConversationSLATrackingService(db)
        tracking = service.create_tracking(tracking_data)
        log_service.create_integration_log(
            IntegrationLogCreate(
                integration_channel="sla_management",
                business_table="conversation_sla_tracking",
                business_id=tracking.id,
                external_reference=tracking_data.contact_phone_number.strip() if getattr(tracking_data, "contact_phone_number", None) else str(tracking.id),
                direction="inbound",
                endpoint=str(request.url),
                http_method="POST",
                status="success",
            ),
            request_payload_dict=tracking_data.model_dump(),
        )
        return service.get_tracking(str(tracking.id))
    except HTTPException:
        raise
    except Exception as e:
        try:
            log_service.create_integration_log(
                IntegrationLogCreate(
                    integration_channel="sla_management",
                    business_table="conversation_sla_tracking",
                    business_id="00000000-0000-0000-0000-000000000000",
                    external_reference=tracking_data.contact_phone_number.strip() if getattr(tracking_data, "contact_phone_number", None) else "",
                    direction="inbound",
                    endpoint=str(request.url),
                    http_method="POST",
                    status="failed",
                    error_message=str(e),
                ),
                request_payload_dict=tracking_data.model_dump(),
            )
        except Exception:
            pass
        raise handle_internal_error(str(e))


@router.post("/integration/escalate", status_code=status.HTTP_200_OK)
async def escalate_sla_tracking_integration(
    body: ConversationSLAEscalateRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Escalate a conversation SLA tracking by respond_contact_id and policy_id (for external systems).

    Resolves the next assignee from the target tier's team (tier_{current_tier}) under the agent
    mapped from tracking.source_entity_type (complaint, stock_inquiry, purchase_request), using
    round-robin. Updates tracking tier, timestamps, and assigns to that user. Returns the
    assignee's Respond user ID for n8n to update Respond.io.
    """
    log_service = IntegrationLogService(db)
    try:
        service = ConversationSLATrackingService(db)
        tracking = service.get_tracking_by_contact_and_policy(
            body.respond_contact_id,
            body.policy_id,
        )
        if not tracking:
            raise handle_not_found(
                "Conversation SLA tracking",
                f"respond_contact_id={body.respond_contact_id}, policy_id={body.policy_id}",
            )
        if tracking.is_resolved:
            raise handle_validation_error(
                "Cannot escalate a resolved conversation SLA tracking."
            )

        from_tier = int(getattr(tracking, "current_tier", 0) or 0)
        target_tier = from_tier + 1
        if from_tier < 1:
            raise handle_validation_error("Current SLA tier is invalid for escalation.")
        if target_tier > 3:
            raise handle_validation_error("Conversation is already at the highest SLA tier.")
        if body.current_tier != target_tier:
            raise handle_validation_error(
                f"Escalation must move from tier {from_tier} to tier {target_tier}. "
                f"Received current_tier={body.current_tier}."
            )

        # Prefer agent_id FK / team_set_code stored on the tracking record.
        # Fall back to body.team_set_code if not yet persisted, and to source_entity_type→agent mapping.
        resolved_team_set_code = (
            getattr(tracking, "team_set_code", None)
            or body.team_set_code
            or None
        )
        resolved_agent_id = getattr(tracking, "agent_id", None) or None
        assignee = service.get_escalation_assignee_for_tier(
            getattr(tracking, "source_entity_type", None),
            target_tier,
            resolved_team_set_code,
            agent_id_override=resolved_agent_id,
        )

        tracking = service.escalate_tracking(
            respond_contact_id=body.respond_contact_id,
            policy_id=body.policy_id,
            current_tier=target_tier,
            escalation_reason=body.escalation_reason,
        )
        tracking.assigned_to_id = assignee["id"]
        tracking.assigned_to = str(assignee["respond_user_id"]) if assignee.get("respond_user_id") is not None else None
        db.commit()
        db.refresh(tracking)

        log_service.create_integration_log(
            IntegrationLogCreate(
                integration_channel="sla_escalation",
                business_table="conversation_sla_tracking",
                business_id=tracking.id,
                external_reference=body.respond_contact_id,
                direction="inbound",
                endpoint=str(request.url),
                http_method="POST",
                status="success",
            ),
            request_payload_dict=body.model_dump(),
        )
        assigned_to_respond_user_id = str(assignee.get("respond_user_id") or "")
        assigned_to_id = str(assignee.get("id") or "")
        assigned_to_name = assignee.get("name")

        # Return new due dates and remaining hours (based on SLA policy)
        now_utc = datetime.now(timezone.utc)

        def _to_aware_utc(dt):
            if dt is None:
                return None
            if getattr(dt, "tzinfo", None) is not None:
                return dt.astimezone(timezone.utc)
            return dt.replace(tzinfo=timezone.utc)

        due_at_utc = _to_aware_utc(tracking.due_at)
        due_at_resolution_utc = _to_aware_utc(getattr(tracking, "due_at_resolution", None))

        remaining_response_hours = None
        if due_at_utc:
            secs = (due_at_utc - now_utc).total_seconds()
            remaining_response_hours = int(round(max(0.0, secs / 3600.0)))  # full hours

        remaining_resolution_hours = None
        if due_at_resolution_utc:
            secs = (due_at_resolution_utc - now_utc).total_seconds()
            remaining_resolution_hours = int(round(max(0.0, secs / 3600.0)))  # full hours

        def _iso(dt):
            if dt is None:
                return None
            d = _to_aware_utc(dt) if getattr(dt, "tzinfo", None) is None else dt.astimezone(timezone.utc)
            return d.isoformat()

        return {
            "status": "success",
            "message": "SLA tracking escalated successfully.",
            "tracking_id": tracking.id,
            "assigned_to_id": assigned_to_id,
            "assigned_to_name": assigned_to_name,
            "assigned_to_respond_user_id": assigned_to_respond_user_id,
            "due_at": _iso(tracking.due_at),
            "due_at_resolution": _iso(tracking.due_at_resolution),
            "remaining_response_hours": remaining_response_hours,
            "remaining_resolution_hours": remaining_resolution_hours,
        }
    except HTTPException:
        raise
    except Exception as e:
        try:
            log_service.create_integration_log(
                IntegrationLogCreate(
                    integration_channel="sla_escalation",
                    business_table="conversation_sla_tracking",
                    business_id="",
                    external_reference=body.respond_contact_id,
                    direction="inbound",
                    endpoint=str(request.url),
                    http_method="POST",
                    status="failed",
                    error_message=str(e),
                ),
                request_payload_dict=body.model_dump(),
            )
        except Exception:
            pass
        raise handle_internal_error(str(e))


@router.post("/integration", status_code=status.HTTP_200_OK)
async def create_sla_tracking_integration(
    tracking_data: ConversationSLATrackingCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create or update SLA tracking from integration and log the request.
    
    If a tracking record already exists for the contact (based on contact_phone_number),
    it will be updated with the new data. Otherwise, a new tracking record will be created.
    """
    try:
        service = ConversationSLATrackingService(db)
        
        # Check if tracking exists for this contact before calling create_tracking
        contact_phone_number = tracking_data.contact_phone_number.strip()
        from app.models.access import RespondContact
        contact = db.query(RespondContact).filter(
            RespondContact.phone_number == contact_phone_number
        ).first()
        
        is_update = False
        if contact:
            existing = db.query(ConversationSLATracking).filter(
                ConversationSLATracking.respond_contact_id == contact.id
            ).first()
            if existing:
                is_update = True
        
        tracking = service.create_tracking(tracking_data)

        log_service = IntegrationLogService(db)
        log_service.create_integration_log(
            IntegrationLogCreate(
                integration_channel="sla_tracking_creation" if not is_update else "sla_tracking_update",
                business_table="conversation_sla_tracking",
                business_id=tracking.id,
                external_reference=contact_phone_number,
                direction="inbound",
                endpoint=str(request.url),
                http_method="POST",
                status="success"
            ),
            request_payload_dict=tracking_data.model_dump()
        )

        message = "SLA tracking updated successfully." if is_update else "SLA tracking created successfully."
        return {"status": "success", "message": message, "tracking_id": tracking.id, "is_update": is_update}
    except Exception as e:
        raise handle_internal_error(str(e))


@router.put("/{tracking_id}", response_model=ConversationSLATrackingResponse)
async def update_sla_tracking(
    tracking_id: UUID,
    tracking_data: ConversationSLATrackingUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Update an SLA tracking record."""
    tracking_id_str = str(tracking_id)
    log_service = IntegrationLogService(db)
    try:
        service = ConversationSLATrackingService(db)
        tracking = service.update_tracking(tracking_id_str, tracking_data)
        log_service.create_integration_log(
            IntegrationLogCreate(
                integration_channel="sla_management",
                business_table="conversation_sla_tracking",
                business_id=tracking.id,
                external_reference=(tracking.contact.phone_number if tracking.contact else None) or str(tracking.id),
                direction="inbound",
                endpoint=str(request.url),
                http_method="PUT",
                status="success",
            ),
            request_payload_dict=tracking_data.model_dump(exclude_unset=True),
        )
        return service.get_tracking(str(tracking.id))
    except HTTPException:
        raise
    except Exception as e:
        try:
            log_service.create_integration_log(
                IntegrationLogCreate(
                    integration_channel="sla_management",
                    business_table="conversation_sla_tracking",
                    business_id=tracking_id_str,
                    external_reference="",
                    direction="inbound",
                    endpoint=str(request.url),
                    http_method="PUT",
                    status="failed",
                    error_message=str(e),
                ),
                request_payload_dict=tracking_data.model_dump(exclude_unset=True),
            )
        except Exception:
            pass
        raise handle_internal_error(str(e))


@router.post("/{tracking_id}/sync-assignee")
async def sync_assignee_from_respond(
    tracking_id: UUID,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """Sync assignee from Respond.io: fetch contact by phone, match assignee.id to user respond_user_id, update assigned_to if different."""
    try:
        service = ConversationSLATrackingService(db)
        result = service.sync_assignee_from_respond(str(tracking_id))
        return result
    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        if code == 404:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"message": "Contact not found in Respond.io", "code": "CONTACT_NOT_FOUND"})
        if code == 401:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail={"message": "Respond.io API unauthorized", "code": "UNAUTHORIZED"})
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail={"message": f"Respond.io API error: HTTP {code}", "code": f"HTTP_{code}"})
    except httpx.TimeoutException:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail={"message": "Respond.io API timed out", "code": "TIMEOUT"})
    except httpx.ConnectError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"message": "Failed to connect to Respond.io", "code": "CONNECTION_ERROR"})
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{tracking_id}/test-overrides", status_code=status.HTTP_200_OK)
async def post_sla_tracking_test_overrides(
    tracking_id: UUID,
    body: ConversationSLATestOverrideRequest,
    _current_user: dict = Depends(
        require_permission("sla_management.conversation_sla_tracking.test_override")
    ),
    db: Session = Depends(get_db),
):
    """Override assignee or SLA timestamps (permission-gated; for testing workflows)."""
    try:
        service = ConversationSLATrackingService(db)
        service.admin_test_override_tracking(
            str(tracking_id), body.model_dump(exclude_unset=True)
        )
        return {"message": "Updated"}
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.delete("/{tracking_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sla_tracking(
    tracking_id: UUID,
    request: Request,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Delete an SLA tracking record."""
    tracking_id_str = str(tracking_id)
    log_service = IntegrationLogService(db)
    try:
        service = ConversationSLATrackingService(db)
        service.delete_tracking(tracking_id_str)
        log_service.create_integration_log(
            IntegrationLogCreate(
                integration_channel="sla_management",
                business_table="conversation_sla_tracking",
                business_id=tracking_id_str,
                external_reference=tracking_id_str,
                direction="inbound",
                endpoint=str(request.url),
                http_method="DELETE",
                status="success",
            ),
        )
        return None
    except HTTPException:
        raise
    except Exception as e:
        try:
            log_service.create_integration_log(
                IntegrationLogCreate(
                    integration_channel="sla_management",
                    business_table="conversation_sla_tracking",
                    business_id=tracking_id_str,
                    external_reference=tracking_id_str,
                    direction="inbound",
                    endpoint=str(request.url),
                    http_method="DELETE",
                    status="failed",
                    error_message=str(e),
                ),
            )
        except Exception:
            pass
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
    """Calculate duration in hours with two-decimal precision.
    
    Handles both naive and timezone-aware datetimes.
    Naive datetimes are treated as UTC+8 (local timezone).
    """
    from datetime import timedelta
    
    # Convert naive datetimes to UTC+8 for calculation
    if start_at.tzinfo is None:
        start_at = start_at.replace(tzinfo=timezone(timedelta(hours=8)))
    if end_at.tzinfo is None:
        end_at = end_at.replace(tzinfo=timezone(timedelta(hours=8)))
    
    # Normalize both to UTC for calculation
    start_at_utc = start_at.astimezone(timezone.utc)
    end_at_utc = end_at.astimezone(timezone.utc)
    
    hours = Decimal(str((end_at_utc - start_at_utc).total_seconds() / 3600))
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
        # resolved_at is optional when is_resolved is true; service will set it to now if missing

        update_dict = update_data.model_dump(exclude_unset=True)
        update_dict.pop("response_time", None)
        update_dict.pop("resolution_duration", None)
        update_dict.pop("resolution_time", None)

        # Convert timestamps to naive (no timezone) before storing
        if update_data.responded_at:
            update_dict["responded_at"] = to_naive_datetime(update_data.responded_at) if isinstance(update_data.responded_at, datetime) and update_data.responded_at.tzinfo else update_data.responded_at
            update_dict["response_time"] = _calculate_duration_hours(
                tracking.initiated_at, update_dict["responded_at"]
            )
        if update_data.resolved_at:
            update_dict["resolved_at"] = to_naive_datetime(update_data.resolved_at) if isinstance(update_data.resolved_at, datetime) and update_data.resolved_at.tzinfo else update_data.resolved_at
            update_dict["resolution_duration"] = _calculate_duration_hours(
                tracking.initiated_at, update_dict["resolved_at"]
            )

        tracking = service.update_tracking(tracking_id, ConversationSLATrackingUpdate(**update_dict))

        # Create event logs for responded/resolved when applicable
        if update_data.is_responded:
            # Convert responded_at to UTC before creating event log
            responded_at_utc = update_data.responded_at
            if isinstance(responded_at_utc, datetime) and responded_at_utc.tzinfo:
                responded_at_utc = responded_at_utc.astimezone(timezone.utc)

            alabel, aid = event_log_assignee_fields(db, tracking.responded_by)

            service.create_event_log(ConversationSLAEventLogCreate(
                sla_tracking_id=tracking_id,
                event_type="response",
                event_at=responded_at_utc,
                response_time=update_dict.get("response_time"),
                assigned_to=alabel,
                assigned_to_id=aid,
            ))

        if update_data.is_resolved:
            # Use tracking.resolved_at (set by service if not sent) for event log
            resolved_at_utc = update_data.resolved_at or getattr(tracking, "resolved_at", None)
            if isinstance(resolved_at_utc, datetime) and resolved_at_utc.tzinfo:
                resolved_at_utc = resolved_at_utc.astimezone(timezone.utc)
            elif isinstance(resolved_at_utc, datetime) and not resolved_at_utc.tzinfo:
                resolved_at_utc = resolved_at_utc.replace(tzinfo=timezone.utc)

            rlabel, rid = event_log_assignee_fields(db, tracking.resolved_by)

            service.create_event_log(ConversationSLAEventLogCreate(
                sla_tracking_id=tracking_id,
                event_type="resolution",
                event_at=resolved_at_utc,
                resolution_time=update_dict.get("resolution_duration"),
                assigned_to=rlabel,
                assigned_to_id=rid,
            ))

        log_service = IntegrationLogService(db)
        log_service.create_integration_log(
            IntegrationLogCreate(
                integration_channel="sla_tracking_update",
                business_table="conversation_sla_tracking",
                business_id=tracking.id,
                external_reference=(tracking.contact.phone_number if tracking.contact else None) or str(tracking.id),
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


@router.delete("/event-logs/{log_id}", status_code=status.HTTP_200_OK)
async def delete_event_log(
    log_id: UUID,
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Delete an event log entry. Only admins can delete logs."""
    try:
        # Check if user is admin
        user_role = current_user.get("role") if isinstance(current_user, dict) else None
        if user_role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can delete event logs"
            )
        
        log_id = str(log_id)
        service = ConversationSLATrackingService(db)
        result = service.delete_event_log(log_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/event-logs", response_model=ListResponse[ConversationSLAEventLogResponse])
async def get_event_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    sort: Optional[str] = Query("event_at"),
    dir: Optional[str] = Query("desc"),
    tracking_id: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    assigned_to: Optional[str] = Query(None),
    assigned_to_id: Optional[str] = Query(None, description="Filter by user id (assigned_to_id)"),
    date_from: Optional[str] = Query(None, description="Filter event_at >= date (ISO date or datetime)"),
    date_to: Optional[str] = Query(None, description="Filter event_at <= date (ISO date or datetime, end of day)"),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db)
):
    """Get SLA event logs with pagination and filtering."""
    try:
        service = ConversationSLATrackingService(db)
        result = service.list_event_logs(
            page=page,
            limit=limit,
            sort_field=sort,
            sort_dir=dir,
            tracking_id=tracking_id,
            event_type=event_type,
            assigned_to=assigned_to,
            assigned_to_id=assigned_to_id,
            date_from=date_from,
            date_to=date_to,
        )
        return result
    except Exception as e:
        raise handle_internal_error(str(e))


@router.get("/{tracking_id}/conversation")
async def get_sla_tracking_conversation(
    tracking_id: UUID,
    limit: int = Query(50, ge=1, le=50),
    cursor: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user_or_api_key),
    db: Session = Depends(get_db),
):
    """List Respond.io messages for the contact linked to this SLA tracking (respond_io_id on respond_contacts)."""
    try:
        service = ConversationSLATrackingService(db)
        return service.fetch_respond_conversation_for_tracking(
            str(tracking_id), limit=limit, cursor=cursor
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise handle_internal_error(str(e))


@router.post("/{tracking_id}/conversation/reply")
async def post_sla_tracking_conversation_reply(
    tracking_id: UUID,
    body: SlaTrackingConversationReplyBody,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Send a text message to the Respond.io contact for this SLA tracking."""
    try:
        respond_user_id = _sla_reply_respond_user_id(current_user)
        service = ConversationSLATrackingService(db)
        service.send_conversation_reply_for_tracking(
            str(tracking_id),
            body.message,
            respond_user_id=respond_user_id,
            crm_sender_user_id=current_user.get("id"),
            request_url=str(request.url) if request else "",
        )
        db.commit()
        return {"ok": True}
    except HTTPException:
        raise
    except AppException:
        raise
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
        
        # Look up user names for responded_by and resolved_by
        from app.models.user import User
        responded_by_user_name = None
        if tracking.responded_by:
            responded_by_user = db.query(User).filter(
                (User.id == tracking.responded_by) |
                (User.respond_user_id == tracking.responded_by) |
                (User.email == tracking.responded_by)
            ).first()
            responded_by_user_name = responded_by_user.name if responded_by_user else tracking.responded_by
        
        resolved_by_user_name = None
        if tracking.resolved_by:
            resolved_by_user = db.query(User).filter(
                (User.id == tracking.resolved_by) |
                (User.respond_user_id == tracking.resolved_by) |
                (User.email == tracking.resolved_by)
            ).first()
            resolved_by_user_name = resolved_by_user.name if resolved_by_user else tracking.resolved_by
        
        # Build event logs with user relationships and calculate averages
        event_logs_data = []
        response_durations = []
        resolution_durations = []
        
        if tracking.event_logs:
            for log in tracking.event_logs:
                log_data = {
                    "id": str(log.id),
                    "sla_tracking_id": str(log.sla_tracking_id),
                    "event_type": log.event_type,
                    "from_tier": log.from_tier,
                    "to_tier": log.to_tier,
                    "event_at": log.event_at,
                    "from_time": log.from_time,
                    "duration": log.duration,
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
                
                # Collect durations for average calculation (only positive, to ignore legacy negative values)
                d = float(log.duration) if log.duration is not None else None
                if log.event_type and log.event_type.lower() == "response" and d is not None and d > 0:
                    response_durations.append(d)
                elif log.event_type and log.event_type.lower() == "resolution" and d is not None and d > 0:
                    resolution_durations.append(d)
        
        # Calculate averages
        from decimal import Decimal, ROUND_HALF_UP
        average_response_time = None
        average_resolution_time = None
        
        if response_durations:
            avg = sum(response_durations) / len(response_durations)
            average_response_time = Decimal(str(avg)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        if resolution_durations:
            avg = sum(resolution_durations) / len(resolution_durations)
            average_resolution_time = Decimal(str(avg)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        # Time-in-tier and time-remaining (response stops when is_responded, resolution when is_resolved)
        tier = db.query(SLAPolicyTier).filter(
            SLAPolicyTier.policy_id == tracking.policy_id,
            SLAPolicyTier.tier_level == tracking.current_tier,
        ).first()
        timings = compute_tracking_timings(tracking, tier)
        tier_response_hours = tier.response_hours if tier else None
        tier_resolution_hours = getattr(tier, "resolution_hours", None) if tier else None

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
            "due_at_resolution": tracking.due_at_resolution,
            "escalated_at": tracking.escalated_at,
            "escalation_reason": tracking.escalation_reason,
            "is_responded": tracking.is_responded,
            "responded_at": tracking.responded_at,
            "responded_by": tracking.responded_by,
            "response_time": tracking.response_time,
            "is_resolved": tracking.is_resolved,
            "resolved_at": tracking.resolved_at,
            "resolved_by": tracking.resolved_by,
            "respond_contact_id": tracking.respond_contact_id,
            "respond_io_id": getattr(tracking.contact, "respond_io_id", None) if tracking.contact else None,
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
                "name": tracking.contact.name,
                "respond_io_id": getattr(tracking.contact, "respond_io_id", None),
            } if tracking.contact else None,
            "assigned_user": {
                "id": tracking.assigned_user.id,
                "email": tracking.assigned_user.email,
                "name": tracking.assigned_user.name,
                "superior": {
                    "name": tracking.assigned_user.superior.name if tracking.assigned_user.superior else None,
                    "email": tracking.assigned_user.superior.email if tracking.assigned_user.superior else None,
                } if getattr(tracking.assigned_user, "superior", None) else None,
            } if tracking.assigned_user else None,
            "contact_phone": contact_phone,
            "contact_name": contact_name,
            "assigned_user_name": assigned_user_name,
            "assigned_user_email": assigned_user_email,
            "assigned_user_superior_name": tracking.assigned_user.superior.name if (tracking.assigned_user and getattr(tracking.assigned_user, "superior", None)) else None,
            "assigned_user_superior_email": tracking.assigned_user.superior.email if (tracking.assigned_user and getattr(tracking.assigned_user, "superior", None)) else None,
            "responded_by_user_name": responded_by_user_name,
            "resolved_by_user_name": resolved_by_user_name,
            "average_response_time": average_response_time,
            "average_resolution_time": average_resolution_time,
            "event_logs": event_logs_data,
            "tier_response_hours": tier_response_hours,
            "tier_resolution_hours": tier_resolution_hours,
            "agent_id": getattr(tracking, "agent_id", None),
            "agent_code": tracking.agent.code if getattr(tracking, "agent", None) else None,
            "agent": {
                "id": str(tracking.agent.id),
                "code": tracking.agent.code,
                "name": tracking.agent.name,
            } if getattr(tracking, "agent", None) else None,
            "team_set_code": getattr(tracking, "team_set_code", None),
            **timings,
        }
        
        return ConversationSLATrackingResponse.model_validate(response_dict)
    except HTTPException:
        raise
    except Exception as e:
        raise handle_internal_error(str(e))
