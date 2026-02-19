"""SLA service for business logic."""
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from typing import Optional
from datetime import datetime, timezone, timedelta
from app.models.sla import SLAPolicy, SLAPolicyTier, ConversationSLATracking, ConversationSLAEventLog
from app.models.access import RespondContact
from app.schemas.sla import (
    SLAPolicyCreate, SLAPolicyUpdate, SLAPolicyTierCreate, SLAPolicyTierUpdate,
    ConversationSLATrackingCreate, ConversationSLATrackingUpdate, ConversationSLAEventLogCreate
)
from app.services.error_handler import handle_not_found, handle_conflict, handle_validation_error

# Malaysia timezone (UTC+8) for all SLA timestamps
MALAYSIA_TZ = timezone(timedelta(hours=8))

# Optional: set USE_REMOTE_TIME=1 to get "now" from a time API (avoids server clock drift)
_REMOTE_TIME_URL = "https://worldtimeapi.org/api/timezone/Etc/UTC"


def _utc_now_from_remote() -> Optional[datetime]:
    """Fetch current UTC from a time API. Returns None on any failure."""
    try:
        import urllib.request
        import json
        with urllib.request.urlopen(_REMOTE_TIME_URL, timeout=3) as r:
            data = json.loads(r.read().decode())
            # e.g. "2026-02-06T04:06:36.123456+00:00"
            s = data.get("datetime") or data.get("utc_datetime")
            if s:
                return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        pass
    return None


def now_malaysia() -> datetime:
    """Current time in Malaysia (UTC+8). Use for all SLA 'now' timestamps so DB shows Malaysia time.
    If USE_REMOTE_TIME=1, fetches UTC from a time API first (use when server clock is wrong).
    """
    import os
    if os.environ.get("USE_REMOTE_TIME", "").strip() == "1":
        utc = _utc_now_from_remote()
        if utc is not None:
            return utc.astimezone()
    return datetime.now()


def to_aware_utc8(dt: Optional[datetime]) -> Optional[datetime]:
    """Convert datetime to timezone-aware Malaysia (UTC+8) for DB storage.
    Naive datetimes are treated as Malaysia time. Use before writing to timestamptz.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=MALAYSIA_TZ)
    return dt.astimezone(MALAYSIA_TZ)


def to_naive_datetime(dt: datetime) -> datetime:
    """Convert timezone-aware datetime to naive datetime (Malaysia UTC+8).
    For naive datetimes, returns as-is (assumes they're already Malaysia time).
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    dt_utc8 = dt.astimezone(MALAYSIA_TZ)
    return dt_utc8.replace(tzinfo=None)


class SLAPolicyService:
    """Service for SLA policy operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_policies(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        status: Optional[str] = None,
        sort_field: str = "created_at",
        sort_dir: str = "asc"
    ):
        """List SLA policies."""
        q = self.db.query(SLAPolicy)
        
        filters = []
        if status and status != "all":
            filters.append(SLAPolicy.is_active == (status == "active"))
        
        if query:
            filters.append(
                or_(
                    SLAPolicy.code.ilike(f"%{query}%"),
                    SLAPolicy.name.ilike(f"%{query}%"),
                    SLAPolicy.description.ilike(f"%{query}%")
                )
            )
        
        if filters:
            from sqlalchemy import and_
            q = q.filter(and_(*filters))
        
        sort_map = {
            "code": SLAPolicy.code,
            "name": SLAPolicy.name,
            "created_at": SLAPolicy.created_at,
            "updated_at": SLAPolicy.updated_at,
        }
        sort_column = sort_map.get(sort_field, SLAPolicy.created_at)
        if sort_dir == "desc":
            q = q.order_by(sort_column.desc())
        else:
            q = q.order_by(sort_column.asc())
        
        total = q.count()
        offset = (page - 1) * limit
        policies = q.offset(offset).limit(limit).all()
        
        # Add counts
        result = []
        for policy in policies:
            tiers_count = self.db.query(func.count(SLAPolicyTier.id)).filter(
                SLAPolicyTier.policy_id == policy.id
            ).scalar() or 0
            
            tracking_count = self.db.query(func.count(ConversationSLATracking.id)).filter(
                ConversationSLATracking.policy_id == policy.id
            ).scalar() or 0
            
            policy_dict = {
                **{c.name: getattr(policy, c.name) for c in policy.__table__.columns},
                "tiers_count": tiers_count,
                "tracking_count": tracking_count
            }
            result.append(policy_dict)
        
        return {
            "data": policies,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_policy(self, policy_id: str):
        """Get an SLA policy by ID."""
        policy = self.db.query(SLAPolicy).filter(SLAPolicy.id == policy_id).first()
        if not policy:
            raise handle_not_found("SLA Policy", policy_id)
        return policy
    
    def create_policy(self, policy_data: SLAPolicyCreate):
        """Create a new SLA policy with tiers."""
        existing = self.db.query(SLAPolicy).filter(SLAPolicy.code == policy_data.code).first()
        if existing:
            raise handle_conflict("SLA policy code already exists.")
        
        policy_dict = policy_data.model_dump(exclude={"tiers"})
        policy = SLAPolicy(**policy_dict)
        self.db.add(policy)
        self.db.flush()
        
        # Create tiers if provided
        if policy_data.tiers:
            for tier_data in policy_data.tiers:
                tier = SLAPolicyTier(**tier_data.model_dump(), policy_id=policy.id)
                self.db.add(tier)
        
        self.db.commit()
        self.db.refresh(policy)
        return policy
    
    def update_policy(self, policy_id: str, policy_data: SLAPolicyUpdate):
        """Update an SLA policy."""
        policy = self.get_policy(policy_id)
        
        update_data = policy_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(policy, key, value)
        
        self.db.commit()
        self.db.refresh(policy)
        return policy


class SLAPolicyTierService:
    """Service for SLA policy tier operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_tiers(self, policy_id: str):
        """List tiers for a policy."""
        tiers = self.db.query(SLAPolicyTier).filter(
            SLAPolicyTier.policy_id == policy_id
        ).order_by(SLAPolicyTier.tier_level).all()
        return tiers
    
    def get_tier(self, tier_id: str):
        """Get a tier by ID."""
        tier = self.db.query(SLAPolicyTier).filter(SLAPolicyTier.id == tier_id).first()
        if not tier:
            raise handle_not_found("SLA Policy Tier", tier_id)
        return tier
    
    def create_tier(self, tier_data: SLAPolicyTierCreate):
        """Create a new tier."""
        # Check unique constraint
        existing = self.db.query(SLAPolicyTier).filter(
            SLAPolicyTier.policy_id == tier_data.policy_id,
            SLAPolicyTier.tier_level == tier_data.tier_level
        ).first()
        if existing:
            raise handle_conflict("Tier level already exists for this policy.")
        
        tier = SLAPolicyTier(**tier_data.model_dump())
        self.db.add(tier)
        self.db.commit()
        self.db.refresh(tier)
        return tier
    
    def update_tier(self, tier_id: str, tier_data: SLAPolicyTierUpdate):
        """Update a tier."""
        tier = self.get_tier(tier_id)
        
        update_data = tier_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(tier, key, value)
        
        self.db.commit()
        self.db.refresh(tier)
        return tier
    
    def delete_tier(self, tier_id: str):
        """Delete a tier."""
        tier = self.get_tier(tier_id)
        self.db.delete(tier)
        self.db.commit()
        return {"message": "SLA policy tier deleted successfully"}


def _now_utc() -> datetime:
    """Current time as timezone-aware UTC for DB storage and duration math."""
    return datetime.now(timezone.utc)


def _to_aware_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Convert to timezone-aware UTC for DB storage and duration calculations. Naive treated as UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def compute_tracking_timings(tracking, tier) -> dict:
    """
    Compute time-in-tier and time-remaining for response and resolution.
    Response timers stop when is_responded=True; resolution timers stop when is_resolved=True.
    Returns dict with time_in_tier_response_seconds, time_remaining_response_seconds,
    time_in_tier_resolution_seconds, time_remaining_resolution_seconds, resolution_due_at.
    """
    if tier is None:
        return {
            "time_in_tier_response_seconds": None,
            "time_remaining_response_seconds": None,
            "time_in_tier_resolution_seconds": None,
            "time_remaining_resolution_seconds": None,
            "resolution_due_at": None,
        }
    now = _now_utc()
    initiated_at = _to_aware_utc(tracking.initiated_at)
    current_tier_started_at = _to_aware_utc(tracking.current_tier_started_at)
    due_at = _to_aware_utc(tracking.due_at)
    responded_at = _to_aware_utc(tracking.responded_at)
    resolved_at = _to_aware_utc(tracking.resolved_at)
    due_at_resolution = _to_aware_utc(getattr(tracking, "due_at_resolution", None))
    resolution_hours = getattr(tier, "resolution_hours", None) or 24
    resolution_due_at = due_at_resolution if due_at_resolution is not None else (
        (initiated_at + timedelta(hours=resolution_hours)) if initiated_at else None
    )

    # Time in tier (response): if responded = responded_at - initiated_at; else timer keeps counting
    if tracking.is_responded and responded_at and initiated_at:
        time_in_tier_response_seconds = (responded_at - initiated_at).total_seconds()
    elif current_tier_started_at:
        time_in_tier_response_seconds = (now - current_tier_started_at).total_seconds()
    else:
        time_in_tier_response_seconds = None

    # Time remaining for response (0 when is_responded)
    if tracking.is_responded:
        time_remaining_response_seconds = 0.0
    elif due_at:
        time_remaining_response_seconds = max(0.0, (due_at - now).total_seconds())
    else:
        time_remaining_response_seconds = None

    # Time in tier (resolution): if resolved = resolved_at - initiated_at; else timer keeps counting
    if tracking.is_resolved and resolved_at and initiated_at:
        time_in_tier_resolution_seconds = (resolved_at - initiated_at).total_seconds()
    elif initiated_at:
        time_in_tier_resolution_seconds = (now - initiated_at).total_seconds()
    else:
        time_in_tier_resolution_seconds = None

    # Time remaining for resolution (0 when is_resolved)
    if tracking.is_resolved:
        time_remaining_resolution_seconds = 0.0
    elif resolution_due_at:
        time_remaining_resolution_seconds = max(0.0, (resolution_due_at - now).total_seconds())
    else:
        time_remaining_resolution_seconds = None

    return {
        "time_in_tier_response_seconds": time_in_tier_response_seconds,
        "time_remaining_response_seconds": time_remaining_response_seconds,
        "time_in_tier_resolution_seconds": time_in_tier_resolution_seconds,
        "time_remaining_resolution_seconds": time_remaining_resolution_seconds,
        "resolution_due_at": resolution_due_at,
    }


class ConversationSLATrackingService:
    """Service for conversation SLA tracking operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_tracking(
        self,
        page: int = 1,
        limit: int = 50,
        policy_id: Optional[str] = None,
        query: Optional[str] = None,
        sort_field: str = "created_at",
        sort_dir: str = "desc",
        assigned_to: Optional[str] = None,
    ):
        """List SLA tracking records. query filters by contact phone or contact name."""
        from sqlalchemy.orm import joinedload
        from sqlalchemy import asc, desc
        from app.models.sla import ConversationSLAEventLog
        from app.models.user import User

        q = self.db.query(ConversationSLATracking).options(
            joinedload(ConversationSLATracking.policy),
            joinedload(ConversationSLATracking.contact),
            joinedload(ConversationSLATracking.assigned_user),
            joinedload(ConversationSLATracking.event_logs).joinedload(ConversationSLAEventLog.assigned_user)
        )

        if policy_id:
            q = q.filter(ConversationSLATracking.policy_id == policy_id)

        if query and query.strip():
            term = f"%{query.strip()}%"
            q = q.join(RespondContact, ConversationSLATracking.respond_contact_id == RespondContact.id).filter(
                or_(
                    RespondContact.phone_number.ilike(term),
                    RespondContact.name.ilike(term),
                )
            )

        if assigned_to and assigned_to.strip():
            assignee_val = assigned_to.strip()
            # Only show trackings that have an assignee and that assignee matches (exclude unassigned)
            q = q.filter(ConversationSLATracking.assigned_to_id.isnot(None)).join(
                User, ConversationSLATracking.assigned_to_id == User.id
            ).filter(
                or_(
                    User.respond_user_id == assignee_val,
                    User.id == assignee_val,
                )
            )

        order_col = getattr(ConversationSLATracking, sort_field, None)
        if order_col is not None and hasattr(order_col, "desc"):
            q = q.order_by(desc(order_col) if sort_dir == "desc" else asc(order_col))
        else:
            q = q.order_by(ConversationSLATracking.created_at.desc())

        total = q.count()
        offset = (page - 1) * limit
        tracking = q.offset(offset).limit(limit).all()
        
        # Convert to dict for proper validation with relationships
        result_data = []
        for track in tracking:
            # Get contact info from relationship
            contact_phone = track.contact.phone_number if track.contact else None
            contact_name = track.contact.name if track.contact else None
            
            # Get user info from relationship
            assigned_user_name = track.assigned_user.name if track.assigned_user else None
            assigned_user_email = track.assigned_user.email if track.assigned_user else None
            
            # Look up user names for responded_by and resolved_by
            responded_by_user_name = None
            resolved_by_user_name = None
            if track.responded_by:
                from app.models.user import User
                responded_by_user = self.db.query(User).filter(
                    (User.id == track.responded_by) |
                    (User.respond_user_id == track.responded_by) |
                    (User.email == track.responded_by)
                ).first()
                responded_by_user_name = responded_by_user.name if responded_by_user else track.responded_by
            
            if track.resolved_by:
                from app.models.user import User
                resolved_by_user = self.db.query(User).filter(
                    (User.id == track.resolved_by) |
                    (User.respond_user_id == track.resolved_by) |
                    (User.email == track.resolved_by)
                ).first()
                resolved_by_user_name = resolved_by_user.name if resolved_by_user else track.resolved_by
            
            track_dict = {
                "id": str(track.id),
                "policy_id": str(track.policy_id),
                "current_tier": track.current_tier,
                "assigned_to": track.assigned_to,  # Keep for backward compatibility
                "assigned_to_id": track.assigned_to_id,
                "initiated_at": track.initiated_at,
                "current_tier_started_at": track.current_tier_started_at,
                "due_at": track.due_at,
                "due_at_resolution": getattr(track, "due_at_resolution", None),
                "escalated_at": track.escalated_at,
                "escalation_reason": track.escalation_reason,
                "is_responded": track.is_responded,
                "responded_at": track.responded_at,
                "responded_by": track.responded_by,
                "response_time": track.response_time,
                "is_resolved": track.is_resolved,
                "resolved_at": track.resolved_at,
                "resolved_by": track.resolved_by,
                "respond_contact_id": track.respond_contact_id,
                "created_at": track.created_at,
                "updated_at": track.updated_at,
                "synced_to_excel": track.synced_to_excel,
                "last_synced_to_excel": track.last_synced_to_excel,
                "resolution_duration": track.resolution_duration,
                "policy": {
                    "id": str(track.policy.id),
                    "code": track.policy.code,
                    "name": track.policy.name
                } if track.policy else None,
                "policy_code": track.policy.code if track.policy else None,
                "policy_name": track.policy.name if track.policy else None,
                "contact": {
                    "id": track.contact.id,
                    "phone_number": track.contact.phone_number,
                    "name": track.contact.name
                } if track.contact else None,
                "assigned_user": {
                    "id": track.assigned_user.id,
                    "email": track.assigned_user.email,
                    "name": track.assigned_user.name
                } if track.assigned_user else None,
                "contact_phone": contact_phone,
                "contact_name": contact_name,
                "assigned_user_name": assigned_user_name,
                "assigned_user_email": assigned_user_email,
                "responded_by_user_name": responded_by_user_name,
                "resolved_by_user_name": resolved_by_user_name,
                "event_logs": []  # Initialize as empty
            }
            # Compute time-in-tier and time-remaining (response stops when is_responded, resolution when is_resolved)
            tier = self.db.query(SLAPolicyTier).filter(
                SLAPolicyTier.policy_id == track.policy_id,
                SLAPolicyTier.tier_level == track.current_tier,
            ).first()
            track_dict.update(compute_tracking_timings(track, tier))
            track_dict["tier_response_hours"] = tier.response_hours if tier else None
            track_dict["tier_resolution_hours"] = getattr(tier, "resolution_hours", None) if tier else None

            # Try to load event_logs if relationship exists
            try:
                if hasattr(track, 'event_logs'):
                    event_logs_list = list(track.event_logs) if track.event_logs else []
                    track_dict["event_logs"] = [
                        {
                            "id": str(log.id),
                            "sla_tracking_id": str(log.sla_tracking_id),
                            "event_type": log.event_type,
                            "from_tier": log.from_tier,
                            "to_tier": log.to_tier,
                            "event_at": log.event_at,
                            "reason": log.reason,
                            "assigned_to": log.assigned_to,  # Keep for backward compatibility
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
                        for log in event_logs_list
                    ]
            except Exception:
                track_dict["event_logs"] = []
            
            result_data.append(track_dict)
        
        return {
            "data": result_data,
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0
        }
    
    def get_tracking(self, tracking_id: str):
        """Get a tracking record by ID."""
        from sqlalchemy.orm import joinedload
        from app.models.sla import ConversationSLAEventLog
        # Load tracking with all relationships, including user relationship for event logs
        tracking = self.db.query(ConversationSLATracking).options(
            joinedload(ConversationSLATracking.policy),
            joinedload(ConversationSLATracking.contact),
            joinedload(ConversationSLATracking.assigned_user),
            joinedload(ConversationSLATracking.event_logs).joinedload(ConversationSLAEventLog.assigned_user)
        ).filter(
            ConversationSLATracking.id == tracking_id
        ).first()
        if not tracking:
            raise handle_not_found("SLA Tracking", tracking_id)
        
        # Sort event logs by event_at descending (latest first)
        if tracking.event_logs:
            tracking.event_logs.sort(key=lambda x: x.event_at, reverse=True)
        
        return tracking

    def get_tracking_by_source_entity(self, source_entity_type: str, source_entity_id: str) -> Optional[ConversationSLATracking]:
        """Get a tracking record by source entity (e.g. stock_inquiry, complaint)."""
        return (
            self.db.query(ConversationSLATracking)
            .filter(
                ConversationSLATracking.source_entity_type == source_entity_type,
                ConversationSLATracking.source_entity_id == source_entity_id,
            )
            .first()
        )

    def get_existing_assignee_for_contact_phone(self, contact_phone: str) -> Optional[dict]:
        """
        If there is a conversation SLA tracking for this contact phone that already has an assignee,
        return that user's info (id, email, name, respond_user_id). Otherwise return None.
        Used by next-assignee API to avoid reassigning conversations that are already assigned.
        """
        from sqlalchemy.orm import joinedload
        from app.models.access import RespondContact
        from app.models.user import User

        phone = (contact_phone or "").strip()
        if not phone:
            return None
        contact = self.db.query(RespondContact).filter(RespondContact.phone_number == phone).first()
        if not contact:
            return None
        tracking = (
            self.db.query(ConversationSLATracking)
            .options(joinedload(ConversationSLATracking.assigned_user))
            .filter(
                ConversationSLATracking.respond_contact_id == contact.id,
                ConversationSLATracking.assigned_to_id.isnot(None),
            )
            .first()
        )
        if not tracking or not tracking.assigned_to_id:
            return None
        user = tracking.assigned_user
        if not user:
            user = self.db.query(User).filter(User.id == tracking.assigned_to_id).first()
        if not user:
            return None
        return {
            "id": user.id,
            "email": user.email,
            "name": user.name or user.email,
            "respond_user_id": user.respond_user_id,
        }

    def sync_assignee_from_respond(self, tracking_id: str) -> dict:
        """
        Fetch contact from Respond.io by phone, get assignee.id, match to user by respond_user_id,
        and update tracking assigned_to if different. Uses existing Respond.io config (base URL, API key).
        """
        import json
        import logging
        from app.models.user import User
        from app.services.integration_service import RespondClient, IntegrationLogService
        from app.schemas.integration import IntegrationLogCreate

        logger = logging.getLogger(__name__)
        tracking = self.get_tracking(tracking_id)
        phone = None
        if tracking.contact:
            phone = (getattr(tracking.contact, "phone_number", None) or "").strip()
        if not phone:
            raise handle_validation_error("No contact phone for this conversation SLA tracking; cannot sync assignee from Respond.io.")

        log_service = IntegrationLogService(self.db)
        endpoint_path = f"/v2/contact/phone:{phone}"

        try:
            client = RespondClient()
            payload = client.get_contact_by_phone(phone)
        except ValueError as e:
            logger.warning("Respond.io not configured or error: %s", e)
            log_service.create_integration_log(
                IntegrationLogCreate(
                    integration_channel="respond_io",
                    business_table="conversation_sla_tracking",
                    business_id=tracking_id,
                    direction="outbound",
                    endpoint=endpoint_path,
                    http_method="GET",
                    status="failed",
                    error_message=str(e),
                ),
                request_payload_dict={"action": "sync_assignee", "phone": phone},
            )
            raise handle_validation_error(f"Respond.io API is not configured or error: {e!s}")
        except Exception as e:
            logger.exception("Respond.io get_contact_by_phone failed for tracking %s", tracking_id)
            resp_payload = None
            if hasattr(e, "response") and getattr(e.response, "text", None):
                resp_payload = e.response.text[:2000] if len(e.response.text) > 2000 else e.response.text
            log_service.create_integration_log(
                IntegrationLogCreate(
                    integration_channel="respond_io",
                    business_table="conversation_sla_tracking",
                    business_id=tracking_id,
                    direction="outbound",
                    endpoint=endpoint_path,
                    http_method="GET",
                    status="failed",
                    error_message=str(e),
                    response_payload=resp_payload,
                ),
                request_payload_dict={"action": "sync_assignee", "phone": phone},
            )
            raise

        log_service.create_integration_log(
            IntegrationLogCreate(
                integration_channel="respond_io",
                business_table="conversation_sla_tracking",
                business_id=tracking_id,
                direction="outbound",
                endpoint=endpoint_path,
                http_method="GET",
                status="success",
                response_payload=json.dumps(payload, indent=2),
            ),
            request_payload_dict={"action": "sync_assignee", "phone": phone},
        )

        assignee = payload.get("assignee")
        if not assignee or assignee.get("id") is None:
            # Keep in sync with Respond.io: set assigned_to to null when there is no assignee there
            self.update_tracking(tracking_id, ConversationSLATrackingUpdate(assigned_to=None))
            return {"updated": True, "message": "Sync successful. No assignee in Respond.io; Assigned To cleared."}

        assignee_id = assignee.get("id")
        assignee_respond_id = str(assignee_id)
        user = self.db.query(User).filter(User.respond_user_id == assignee_respond_id).first()
        if not user:
            return {
                "updated": False,
                "message": f"Sync successful. No user in CRM with respond_user_id '{assignee_respond_id}'; Assigned To unchanged. Link Respond.io user ID in User Management to sync.",
            }

        if tracking.assigned_to_id == user.id:
            return {"updated": False, "message": "Sync successful. Assignee already in sync."}

        self.update_tracking(tracking_id, ConversationSLATrackingUpdate(assigned_to=assignee_respond_id))
        tracking = self.get_tracking(tracking_id)
        return {
            "updated": True,
            "message": "Assignee synced from Respond.io.",
            "assigned_to_id": str(user.id),
            "assigned_to": user.name or user.email or assignee_respond_id,
        }

    def create_tracking(self, tracking_data: ConversationSLATrackingCreate):
        """Create a new tracking record."""
        from datetime import timedelta, datetime, timezone
        from app.models.sla import SLAPolicy, SLAPolicyTier
        
        tracking_dict = tracking_data.model_dump()
        contact_phone_number = tracking_dict.pop("contact_phone_number", None)

        # contact_phone_number is required and validated in schema
        if not contact_phone_number:
            raise handle_validation_error("contact_phone_number is required")

        # Find contact by phone number
        normalized_phone = contact_phone_number.strip()
        contact = self.db.query(RespondContact).filter(
            RespondContact.phone_number == normalized_phone
        ).first()
        if not contact:
            raise handle_validation_error(
                f"Respond contact not found for phone number: {normalized_phone}"
            )
        tracking_dict["respond_contact_id"] = contact.id

        # Resolve assigned_to to assigned_to_id
        if not tracking_dict.get("assigned_to_id") and tracking_dict.get("assigned_to"):
            from app.models.user import User

            assigned_to_value = str(tracking_dict["assigned_to"]).strip()
            user = self.db.query(User).filter(
                (User.respond_user_id == assigned_to_value) |
                (User.id == assigned_to_value) |
                (User.email == assigned_to_value)
            ).first()
            if not user:
                raise handle_validation_error(
                    f"User not found for respond_user_id: {assigned_to_value}"
                )
            tracking_dict["assigned_to_id"] = user.id

        # Auto-populate initiated_at and current_tier_started_at to now (UTC)
        now_utc = _now_utc()
        if not tracking_dict.get("initiated_at"):
            tracking_dict["initiated_at"] = now_utc
        else:
            tracking_dict["initiated_at"] = _to_aware_utc(tracking_dict["initiated_at"])

        if not tracking_dict.get("current_tier_started_at"):
            tracking_dict["current_tier_started_at"] = now_utc
        else:
            tracking_dict["current_tier_started_at"] = _to_aware_utc(tracking_dict["current_tier_started_at"])

        # Reset escalation and resolution fields
        tracking_dict["escalated_at"] = None
        tracking_dict["escalation_reason"] = None
        tracking_dict["is_resolved"] = False
        tracking_dict["resolved_at"] = None
        tracking_dict["resolved_by"] = None
        tracking_dict["resolution_duration"] = None
        tracking_dict["is_responded"] = False
        tracking_dict["responded_at"] = None
        tracking_dict["responded_by"] = None
        tracking_dict["response_time"] = None

        # Get policy and tier to calculate due_at
        policy = self.db.query(SLAPolicy).filter(SLAPolicy.id == tracking_dict["policy_id"]).first()
        if not policy:
            raise handle_not_found("SLA Policy", tracking_dict["policy_id"])
        
        tier = self.db.query(SLAPolicyTier).filter(
            SLAPolicyTier.policy_id == tracking_dict["policy_id"],
            SLAPolicyTier.tier_level == tracking_dict["current_tier"]
        ).first()
        if not tier:
            raise handle_validation_error(
                f"SLA policy tier {tracking_dict['current_tier']} not found for policy {tracking_dict['policy_id']}"
            )

        # Calculate due_at (response) and due_at_resolution from tier (UTC)
        current_tier_started_at = _to_aware_utc(tracking_dict["current_tier_started_at"])
        initiated_at_utc = _to_aware_utc(tracking_dict["initiated_at"])
        response_hours = tier.response_hours if tier.response_hours is not None else 24
        resolution_hours = getattr(tier, "resolution_hours", None) or 24
        if current_tier_started_at:
            tracking_dict["due_at"] = current_tier_started_at + timedelta(hours=response_hours)
        else:
            tracking_dict["due_at"] = None
        if initiated_at_utc:
            tracking_dict["due_at_resolution"] = initiated_at_utc + timedelta(hours=resolution_hours)
        else:
            tracking_dict["due_at_resolution"] = None

        # Check if tracking already exists for this contact
        existing = self.db.query(ConversationSLATracking).filter(
            ConversationSLATracking.respond_contact_id == tracking_dict["respond_contact_id"]
        ).first()
        
        if existing:
            # Update existing tracking record
            # Fields to preserve (don't update these)
            preserve_fields = {"id", "created_at", "respond_contact_id"}  # respond_contact_id should stay the same
            
            # Update all fields from tracking_dict (except preserved fields)
            # This includes the auto-populated and reset fields
            for key, value in tracking_dict.items():
                if key not in preserve_fields:
                    setattr(existing, key, value)
            
            # Always recalculate due_at and due_at_resolution based on tier (UTC)
            tier = self.db.query(SLAPolicyTier).filter(
                SLAPolicyTier.policy_id == tracking_dict["policy_id"],
                SLAPolicyTier.tier_level == tracking_dict["current_tier"]
            ).first()
            if tier:
                current_tier_started_at = _to_aware_utc(tracking_dict["current_tier_started_at"])
                initiated_at_utc = _to_aware_utc(tracking_dict["initiated_at"])
                res_hours = getattr(tier, "resolution_hours", None) or 24
                if current_tier_started_at:
                    existing.due_at = current_tier_started_at + timedelta(hours=(tier.response_hours or 24))
                if initiated_at_utc:
                    existing.due_at_resolution = initiated_at_utc + timedelta(hours=res_hours)
            
            self.db.commit()
            self.db.refresh(existing)
            return existing
        
        # Create new tracking record (set due_at_resolution explicitly so it is never omitted)
        tracking = ConversationSLATracking(**tracking_dict)
        if tracking_dict.get("due_at_resolution") is not None:
            tracking.due_at_resolution = tracking_dict["due_at_resolution"]
        if tracking_dict.get("due_at") is not None:
            tracking.due_at = tracking_dict["due_at"]
        self.db.add(tracking)
        self.db.commit()
        self.db.refresh(tracking)
        return tracking
    
    def update_tracking(self, tracking_id: str, tracking_data: ConversationSLATrackingUpdate):
        """Update a tracking record."""
        from datetime import datetime, timezone
        from app.models.user import User
        
        tracking = self.get_tracking(tracking_id)
        
        update_data = tracking_data.model_dump(exclude_unset=True)
        
        # Explicitly clear assignee when assigned_to is None (keep in sync with Respond.io)
        if "assigned_to" in update_data and update_data["assigned_to"] is None:
            update_data["assigned_to_id"] = None

        # Resolve assigned_to to assigned_to_id when it's a non-empty string
        if "assigned_to_id" not in update_data and update_data.get("assigned_to"):
            assigned_to_value = str(update_data["assigned_to"]).strip()
            user = self.db.query(User).filter(
                (User.respond_user_id == assigned_to_value) |
                (User.id == assigned_to_value) |
                (User.email == assigned_to_value)
            ).first()
            if not user:
                raise handle_validation_error(
                    f"User not found for respond_user_id: {assigned_to_value}"
                )
            update_data["assigned_to_id"] = user.id
        
        # Coerce flags to bool for consistent handling (e.g. JSON "true", 1, or string "true")
        is_responded = update_data.get("is_responded")
        is_responded = is_responded is True or (isinstance(is_responded, str) and is_responded.lower() in ("true", "1")) or is_responded == 1
        is_resolved = update_data.get("is_resolved")
        is_resolved = is_resolved is True or (isinstance(is_resolved, str) and is_resolved.lower() in ("true", "1")) or is_resolved == 1
        # If client sent resolved_by or resolved_at without is_resolved, treat as marking resolved
        if not is_resolved and (update_data.get("resolved_by") or ("resolved_at" in update_data and update_data.get("resolved_at") is not None)):
            is_resolved = True

        # Smart handling for is_responded (same as responded_at / responded_by)
        if is_responded:
            if tracking.is_responded:
                raise handle_validation_error("Conversation is already responded.")
            update_data["is_responded"] = True
            # Auto-set responded_at to now (UTC)
            if "responded_at" not in update_data or update_data.get("responded_at") is None:
                update_data["responded_at"] = _now_utc()
            
            # Auto-calculate response_time from initiated_at to responded_at (UTC)
            if "response_time" not in update_data or update_data.get("response_time") is None:
                responded_at = update_data["responded_at"]
                if isinstance(responded_at, str):
                    responded_at = datetime.fromisoformat(responded_at.replace('Z', '+00:00'))
                responded_at_utc = _to_aware_utc(responded_at)
                initiated_at = tracking.initiated_at
                if initiated_at and responded_at_utc:
                    initiated_at_utc_val = _to_aware_utc(initiated_at)
                    from decimal import Decimal, ROUND_HALF_UP
                    duration = (responded_at_utc - initiated_at_utc_val).total_seconds() / 3600
                    update_data["response_time"] = Decimal(str(max(0, duration))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            
            # Resolve responded_by to user UUID (users.id); accept respond_user_id, email, or id
            if "responded_by" in update_data and update_data.get("responded_by"):
                responded_by_value = str(update_data["responded_by"]).strip()
                responded_by_user = self.db.query(User).filter(
                    (User.respond_user_id == responded_by_value) |
                    (User.id == responded_by_value) |
                    (User.email == responded_by_value)
                ).first()
                if not responded_by_user:
                    raise handle_validation_error(
                        f"User not found for responded_by (respond_user_id): {responded_by_value}"
                    )
                update_data["responded_by"] = responded_by_user.id
        elif update_data.get("is_responded") is False:
            # If setting is_responded to False, clear response fields
            update_data["responded_at"] = None
            update_data["response_time"] = None
            update_data["responded_by"] = None
        
        # Smart handling for is_resolved (same pattern: resolved_at, resolution_duration, resolved_by as user UUID)
        if is_resolved:
            if tracking.is_resolved:
                raise handle_validation_error("Conversation is already resolved.")
            update_data["is_resolved"] = True
            # Unset assignee when resolving (same as n8n / external API behaviour)
            update_data["assigned_to"] = None
            update_data["assigned_to_id"] = None
            # Always set resolved_at when marking resolved (UTC)
            if "resolved_at" not in update_data or update_data.get("resolved_at") is None:
                update_data["resolved_at"] = _now_utc()
            
            # Auto-calculate resolution_duration from initiated_at to resolved_at (UTC)
            if "resolution_duration" not in update_data or update_data.get("resolution_duration") is None:
                resolved_at = update_data["resolved_at"]
                if isinstance(resolved_at, str):
                    resolved_at = datetime.fromisoformat(resolved_at.replace('Z', '+00:00'))
                resolved_at_utc = _to_aware_utc(resolved_at)
                initiated_at = tracking.initiated_at
                if initiated_at and resolved_at_utc:
                    initiated_at_utc_val = _to_aware_utc(initiated_at)
                    from decimal import Decimal, ROUND_HALF_UP
                    duration = (resolved_at_utc - initiated_at_utc_val).total_seconds() / 3600
                    update_data["resolution_duration"] = Decimal(str(max(0, duration))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            
            # Resolve resolved_by to user UUID (users.id); accept respond_user_id (e.g. 971724), email, or id
            if "resolved_by" in update_data and update_data.get("resolved_by") is not None:
                resolved_by_value = str(update_data["resolved_by"]).strip()
                resolved_by_user = self.db.query(User).filter(
                    (User.respond_user_id == resolved_by_value) |
                    (User.id == resolved_by_value) |
                    (User.email == resolved_by_value)
                ).first()
                if not resolved_by_user:
                    raise handle_validation_error(
                        f"User not found for resolved_by (respond_user_id): {resolved_by_value}"
                    )
                update_data["resolved_by"] = resolved_by_user.id
        elif update_data.get("is_resolved") is False:
            # If setting is_resolved to False, clear resolution fields
            update_data["resolved_at"] = None
            update_data["resolution_duration"] = None
            update_data["resolved_by"] = None
        
        # Convert all datetime fields to timezone-aware UTC before storing
        datetime_fields = ["initiated_at", "current_tier_started_at", "due_at", "due_at_resolution", "escalated_at",
                          "responded_at", "resolved_at"]
        for field in datetime_fields:
            if field in update_data and update_data[field] is not None:
                dt = update_data[field]
                if isinstance(dt, str):
                    dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
                if isinstance(dt, datetime):
                    update_data[field] = _to_aware_utc(dt)
        
        # Apply all updates
        for key, value in update_data.items():
            setattr(tracking, key, value)
        
        self.db.commit()
        self.db.refresh(tracking)
        return tracking
    
    def delete_tracking(self, tracking_id: str):
        """Delete a tracking record."""
        tracking = self.get_tracking(tracking_id)
        self.db.delete(tracking)
        self.db.commit()
        return tracking

    def delete_event_log(self, log_id: str):
        """Delete an event log entry."""
        from app.models.sla import ConversationSLAEventLog
        log = self.db.query(ConversationSLAEventLog).filter(
            ConversationSLAEventLog.id == log_id
        ).first()
        if not log:
            from app.services.error_handler import handle_not_found
            raise handle_not_found("Event Log", log_id)
        self.db.delete(log)
        self.db.commit()
        return {"message": "Event log deleted successfully"}

    def create_event_log(self, event_data: ConversationSLAEventLogCreate):
        """Create an SLA event log entry."""
        from app.models.user import User
        from decimal import Decimal, ROUND_HALF_UP
        
        log_dict = event_data.model_dump(exclude_unset=True)
        
        # If assigned_to_id is not provided but assigned_to is, try to find the user
        if not log_dict.get("assigned_to_id") and log_dict.get("assigned_to"):
            assigned_to_value = log_dict["assigned_to"]
            # Try to find user by ID, respond_user_id, or email
            user = self.db.query(User).filter(
                (User.id == assigned_to_value) |
                (User.respond_user_id == assigned_to_value) |
                (User.email == assigned_to_value)
            ).first()
            if user:
                log_dict["assigned_to_id"] = user.id
        
        # Auto-populate event_at to now (UTC)
        if not log_dict.get("event_at"):
            log_dict["event_at"] = _now_utc()
        else:
            dt = log_dict.get("event_at")
            if isinstance(dt, datetime):
                log_dict["event_at"] = _to_aware_utc(dt)
        
        # For response or resolution events, auto-populate from_time and duration
        event_type = log_dict.get("event_type", "").lower()
        if event_type in ["response", "resolution"]:
            # Get the tracking record to access initiated_at
            tracking = self.db.query(ConversationSLATracking).filter(
                ConversationSLATracking.id == log_dict["sla_tracking_id"]
            ).first()
            
            if tracking and tracking.initiated_at:
                # Set from_time to initiated_at (UTC)
                initiated_at = tracking.initiated_at
                if isinstance(initiated_at, str):
                    initiated_at = datetime.fromisoformat(initiated_at.replace('Z', '+00:00'))
                log_dict["from_time"] = _to_aware_utc(initiated_at) if isinstance(initiated_at, datetime) else initiated_at
                
                # Calculate duration from initiated_at to event_at (UTC)
                event_at = log_dict["event_at"]
                if isinstance(event_at, str):
                    event_at = datetime.fromisoformat(event_at.replace('Z', '+00:00'))
                initiated_at_utc = _to_aware_utc(initiated_at)
                event_at_utc = _to_aware_utc(event_at)
                if initiated_at_utc and event_at_utc:
                    duration_seconds = (event_at_utc - initiated_at_utc).total_seconds()
                    duration_seconds = max(0.0, duration_seconds)  # clamp for bad legacy data
                    duration_hours = Decimal(str(duration_seconds / 3600)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    log_dict["duration"] = duration_hours
        
        log = ConversationSLAEventLog(**log_dict)
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log
    
    def list_event_logs(
        self,
        page: int = 1,
        limit: int = 50,
        tracking_id: Optional[str] = None,
        event_type: Optional[str] = None,
        assigned_to: Optional[str] = None
    ):
        """List SLA event logs with filtering."""
        from sqlalchemy.orm import joinedload
        from app.schemas.common import ListResponse
        from app.schemas.sla import ConversationSLAEventLogResponse
        
        q = self.db.query(ConversationSLAEventLog).options(
            joinedload(ConversationSLAEventLog.assigned_user)
        )
        
        if tracking_id:
            q = q.filter(ConversationSLAEventLog.sla_tracking_id == tracking_id)
        if event_type:
            q = q.filter(ConversationSLAEventLog.event_type == event_type)
        if assigned_to:
            q = q.filter(ConversationSLAEventLog.assigned_to == assigned_to)
        
        total = q.count()
        
        logs = q.order_by(ConversationSLAEventLog.event_at.desc()).offset((page - 1) * limit).limit(limit).all()
        
        return ListResponse(
            data=[ConversationSLAEventLogResponse.model_validate(log) for log in logs],
            pagination={
                "total": total,
                "page": page,
                "limit": limit
            }
        )
    
    def get_dashboard_metrics(self):
        """Get dashboard metrics for SLA tracking."""
        from datetime import datetime, timedelta, timezone
        from decimal import Decimal

        def _safe_resolution_hours(t):
            try:
                if t.resolution_duration is None:
                    return 0.0
                if isinstance(t.resolution_duration, Decimal):
                    return float(t.resolution_duration)
                return float(t.resolution_duration)
            except (TypeError, ValueError):
                return 0.0

        def _initiated_at_date(t):
            """Return date part of initiated_at whether it's datetime or date."""
            if t.initiated_at is None:
                return None
            if isinstance(t.initiated_at, datetime):
                return t.initiated_at.date()
            if hasattr(t.initiated_at, "isoformat"):  # date-like
                return t.initiated_at
            return None

        def _initiated_at_aware(t):
            """Return timezone-aware datetime for comparison, or None."""
            if t.initiated_at is None:
                return None
            if isinstance(t.initiated_at, datetime):
                return _to_aware_utc(t.initiated_at)
            if hasattr(t.initiated_at, "year"):  # date -> treat as UTC midnight
                return datetime.combine(t.initiated_at, datetime.min.time()).replace(tzinfo=timezone.utc)
            return None

        # Get all trackings
        all_trackings = self.db.query(ConversationSLATracking).all()

        total_trackings = len(all_trackings)
        resolved_count = sum(1 for t in all_trackings if t.is_resolved)
        pending_count = sum(1 for t in all_trackings if not t.is_resolved and not t.escalated_at)
        escalated_count = sum(1 for t in all_trackings if t.escalated_at is not None)

        # Calculate average resolution time (in hours)
        resolved_trackings = [t for t in all_trackings if t.is_resolved and t.resolution_duration]
        average_resolution_time = 0.0
        if resolved_trackings:
            total_duration = sum(_safe_resolution_hours(t) for t in resolved_trackings)
            average_resolution_time = total_duration / len(resolved_trackings)

        # Calculate escalation rate
        escalation_rate = float(escalated_count / total_trackings * 100) if total_trackings > 0 else 0.0

        # Response time trends (last 30 days) — UTC
        thirty_days_ago = _now_utc() - timedelta(days=30)
        recent_trackings = [
            t for t in all_trackings
            if _initiated_at_aware(t) is not None and _initiated_at_aware(t) >= thirty_days_ago
        ]

        response_time_trends = []
        for i in range(30):
            date = _now_utc() - timedelta(days=29 - i)
            date_str = date.date().isoformat()

            day_trackings = [
                t for t in recent_trackings
                if _initiated_at_date(t) is not None and _initiated_at_date(t).isoformat() == date_str
            ]

            avg_response_time = 0.0
            if day_trackings:
                total_duration = sum(_safe_resolution_hours(t) for t in day_trackings)
                avg_response_time = total_duration / len(day_trackings)

            response_time_trends.append({
                "date": date_str,
                "average_response_time": avg_response_time,
            })

        # Escalation rates by tier
        escalation_by_tier = {}
        for t in all_trackings:
            if t.escalated_at and t.current_tier is not None:
                try:
                    tier_level = int(t.current_tier) if isinstance(t.current_tier, (int, str)) else int(float(t.current_tier))
                except (TypeError, ValueError):
                    tier_level = 0
                escalation_by_tier[tier_level] = escalation_by_tier.get(tier_level, 0) + 1
        
        escalation_rates_by_tier = [
            {"tier_level": tier_level, "escalation_count": count}
            for tier_level, count in escalation_by_tier.items()
        ]
        
        # Resolution time distribution
        resolution_time_distribution = {
            "resolved": resolved_count,
            "unresolved": total_trackings - resolved_count,
        }
        
        # Status breakdown
        status_breakdown = {
            "resolved": resolved_count,
            "escalated": escalated_count,
            "pending": pending_count,
        }
        
        return {
            "total_trackings": total_trackings,
            "resolved_count": resolved_count,
            "pending_count": pending_count,
            "escalated_count": escalated_count,
            "average_resolution_time": average_resolution_time,
            "escalation_rate": escalation_rate,
            "response_time_trends": response_time_trends,
            "escalation_rates_by_tier": escalation_rates_by_tier,
            "resolution_time_distribution": resolution_time_distribution,
            "status_breakdown": status_breakdown,
        }