"""SLA service for business logic."""
import re
from sqlalchemy.orm import Session
from sqlalchemy import or_, func, update
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


def _respond_contact_phone_lookup_candidates(raw: str) -> list[str]:
    """
    Build possible respond_contacts.phone_number values for integration lookups.
    Tries exact/stripped input, compact form, with/without leading +, MY local 0-prefix → +60.
    """
    s = (raw or "").strip()
    if not s:
        return []
    compact = re.sub(r"[\s\-\(\)]", "", s)
    out: list[str] = []
    for c in (s, compact):
        if c and c not in out:
            out.append(c)
    if not compact:
        return out
    if compact.startswith("+"):
        no_plus = compact[1:]
        if no_plus.isdigit() and no_plus not in out:
            out.append(no_plus)
    elif compact.isdigit():
        if compact.startswith("0") and len(compact) >= 9:
            my = "+60" + compact[1:]
            if my not in out:
                out.append(my)
        else:
            with_plus = f"+{compact}"
            if with_plus not in out:
                out.append(with_plus)
    return out


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
        (current_tier_started_at + timedelta(hours=resolution_hours)) if current_tier_started_at else None
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


def conversation_tracking_scope():
    """SQLAlchemy filter selecting conversation-SLA rows only.

    Conversation SLA (created by n8n, max one open per contact — mirrors the
    Respond.io conversation) and form SLA stage rows (created by
    form_sla_service, per-entity, multi-active) share this table. Form rows are
    identified by source_entity_type in FORM_SLA_TYPES; everything contact-keyed
    on the conversation side must apply this filter or it can falsely match a
    form row (e.g. the create-time singleton check, thread-assignee lookups).
    """
    from app.services.form_sla_service import FORM_SLA_TYPES

    return or_(
        ConversationSLATracking.source_entity_type.is_(None),
        ConversationSLATracking.source_entity_type.notin_(FORM_SLA_TYPES),
    )


def event_log_assignee_fields(db: Session, user_ref: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Resolve (display label, user id) for SLA event log assigned_to / assigned_to_id."""
    if user_ref is None or (isinstance(user_ref, str) and not str(user_ref).strip()):
        return None, None
    v = str(user_ref).strip()
    from app.models.user import User

    user = (
        db.query(User)
        .filter(
            (User.id == v) | (User.respond_user_id == v) | (User.email == v),
        )
        .first()
    )
    if not user:
        return v, None
    name = getattr(user, "name", None)
    email = getattr(user, "email", None)
    respond_user_id = getattr(user, "respond_user_id", None)
    label = (
        str(name).strip()
        if name is not None and str(name).strip()
        else str(email).strip()
        if email is not None and str(email).strip()
        else str(respond_user_id).strip()
        if respond_user_id is not None and str(respond_user_id).strip()
        else None
    )
    return label, str(getattr(user, "id"))


class ConversationSLATrackingService:
    """Service for conversation SLA tracking operations."""
    
    def __init__(self, db: Session):
        self.db = db

    def _resolve_tracking_assignee_user_id(self, tracking: ConversationSLATracking) -> Optional[str]:
        """Current assignee as users.id before clearing assignment (FK first, then legacy assigned_to text)."""
        assigned_to_id = getattr(tracking, "assigned_to_id", None)
        if assigned_to_id is not None and str(assigned_to_id).strip():
            return str(assigned_to_id)
        assigned_to = getattr(tracking, "assigned_to", None)
        if assigned_to is None or not str(assigned_to).strip():
            return None
        from app.models.user import User

        raw = str(assigned_to).strip()
        user = (
            self.db.query(User)
            .filter(
                (User.respond_user_id == raw) | (User.id == raw) | (User.email == raw),
            )
            .first()
        )
        return str(getattr(user, "id")) if user else None
    
    def list_tracking(
        self,
        page: int = 1,
        limit: int = 50,
        policy_id: Optional[str] = None,
        query: Optional[str] = None,
        sort_field: str = "created_at",
        sort_dir: str = "desc",
        assigned_to: Optional[str] = None,
        tracking_ids: Optional[list[str]] = None,
    ):
        """List SLA tracking records. query filters by contact phone or contact name."""
        from sqlalchemy.orm import joinedload
        from sqlalchemy import asc, desc
        from app.models.sla import ConversationSLAEventLog
        from app.models.user import User

        from app.models.access import AccessAgent
        q = self.db.query(ConversationSLATracking).options(
            joinedload(ConversationSLATracking.policy),
            joinedload(ConversationSLATracking.contact),
            joinedload(ConversationSLATracking.assigned_user),
            joinedload(ConversationSLATracking.agent),
            joinedload(ConversationSLATracking.event_logs).joinedload(ConversationSLAEventLog.assigned_user)
        )

        # Conversation SLA list excludes form trackers (stock_inquiry / purchase_request /
        # sponsorship_form / complaint). Those have their own per-form SLA Tracking tab and
        # detail flow; surfacing them in this list inflates contact-keyed rows and breaks
        # back-navigation to the originating form.
        q = q.filter(conversation_tracking_scope())

        if policy_id:
            q = q.filter(ConversationSLATracking.policy_id == policy_id)

        if tracking_ids is not None:
            q = q.filter(ConversationSLATracking.id.in_(tracking_ids))

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
            if track.responded_by is not None and str(track.responded_by).strip():
                from app.models.user import User
                responded_by_user = self.db.query(User).filter(
                    (User.id == track.responded_by) |
                    (User.respond_user_id == track.responded_by) |
                    (User.email == track.responded_by)
                ).first()
                responded_by_user_name = responded_by_user.name if responded_by_user else track.responded_by
            
            if track.resolved_by is not None and str(track.resolved_by).strip():
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
                "agent_id": getattr(track, "agent_id", None),
                "agent_code": track.agent.code if getattr(track, "agent", None) else None,
                "agent": {
                    "id": str(track.agent.id),
                    "code": track.agent.code,
                    "name": track.agent.name,
                } if getattr(track, "agent", None) else None,
                "team_set_code": getattr(track, "team_set_code", None),
                "message_id": getattr(track, "message_id", None),
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
    
    def get_tracking(self, tracking_id: str, *, load_event_logs: bool = True):
        """Get a tracking record by ID. Set load_event_logs=False for lighter reads (e.g. external summary)."""
        from sqlalchemy.orm import joinedload
        from app.models.sla import ConversationSLAEventLog
        from app.models.user import User

        opts = [
            joinedload(ConversationSLATracking.policy),
            joinedload(ConversationSLATracking.contact),
            joinedload(ConversationSLATracking.assigned_user).joinedload(User.superior),
            joinedload(ConversationSLATracking.agent),
        ]
        if load_event_logs:
            opts.append(
                joinedload(ConversationSLATracking.event_logs).joinedload(
                    ConversationSLAEventLog.assigned_user
                )
            )
        tracking = (
            self.db.query(ConversationSLATracking)
            .options(*opts)
            .filter(ConversationSLATracking.id == tracking_id)
            .first()
        )
        if not tracking:
            raise handle_not_found("SLA Tracking", tracking_id)

        if load_event_logs and tracking.event_logs:
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

    def list_my_pending(self, user_id: str, limit: int = 50) -> list[dict]:
        """Unresolved SLA trackers assigned to ``user_id``, soonest-due first.

        Unlike ``list_tracking`` (the conversation list, which excludes form SLA
        types), this powers a per-user to-do widget and INCLUDES form trackers
        (stock_inquiry / complaint / purchase_request) since those are the items
        the assignee must action.
        """
        from sqlalchemy.orm import joinedload

        rows = (
            self.db.query(ConversationSLATracking)
            .options(joinedload(ConversationSLATracking.policy))
            .filter(
                ConversationSLATracking.assigned_to_id == user_id,
                ConversationSLATracking.is_resolved.is_(False),
            )
            .order_by(ConversationSLATracking.due_at.asc())
            .limit(limit)
            .all()
        )
        reference_by_row = self._resolve_my_pending_references(rows)
        return [
            {
                "id": str(r.id),
                "source_entity_type": r.source_entity_type,
                "source_entity_id": r.source_entity_id,
                "reference": reference_by_row.get(str(r.id)),
                "due_at": r.due_at.isoformat() if r.due_at else None,
                "is_responded": bool(r.is_responded),
                "current_tier": r.current_tier,
                "policy_name": r.policy.name if r.policy else None,
            }
            for r in rows
        ]

    def _resolve_my_pending_references(
        self, rows: list[ConversationSLATracking]
    ) -> dict[str, Optional[str]]:
        """Map each tracker id -> a human-readable reference number.

        complaint -> complaint_number, stock_inquiry -> inquiry_number,
        purchase_request/sponsorship_form -> request_number, ticket -> ticket_number,
        and conversation SLAs with no source entity -> contact phone/name.
        Batched per type to avoid per-row queries.
        """
        from app.models.complaints import Complaint
        from app.models.procurement import StockInquiry, PurchaseRequestHeader
        from app.models.tickets import Ticket

        # Collect source ids per type and contact ids for fallback.
        ids_by_type: dict[str, set[str]] = {}
        contact_ids: set[str] = set()
        for r in rows:
            et = (r.source_entity_type or "").strip()
            if et and r.source_entity_id:
                ids_by_type.setdefault(et, set()).add(str(r.source_entity_id))
            elif r.respond_contact_id:
                contact_ids.add(str(r.respond_contact_id))

        def _num_map(id_col, num_col, ids: set[str]) -> dict[str, str]:
            """Batched id->number lookup. Fail-safe: any DB error (e.g. table not
            present in a minimal test schema) yields no references rather than
            breaking the widget."""
            if not ids:
                return {}
            try:
                out: dict[str, str] = {}
                for rec_id, num in self.db.query(id_col, num_col).filter(id_col.in_(ids)).all():
                    if num:
                        out[str(rec_id)] = str(num)
                return out
            except Exception:  # noqa: BLE001
                self.db.rollback()
                return {}

        complaint_map = _num_map(Complaint.id, Complaint.complaint_number, ids_by_type.get("complaint") or set())
        inquiry_map = _num_map(StockInquiry.id, StockInquiry.inquiry_number, ids_by_type.get("stock_inquiry") or set())
        pr_ids = (ids_by_type.get("purchase_request") or set()) | (ids_by_type.get("sponsorship_form") or set())
        pr_map = _num_map(PurchaseRequestHeader.id, PurchaseRequestHeader.request_number, pr_ids)
        ticket_map = _num_map(Ticket.id, Ticket.ticket_number, ids_by_type.get("ticket") or set())

        contact_map: dict[str, Optional[str]] = {}
        if contact_ids:
            try:
                for cid, name, phone in (
                    self.db.query(RespondContact.id, RespondContact.name, RespondContact.phone_number)
                    .filter(RespondContact.id.in_(contact_ids))
                    .all()
                ):
                    contact_map[str(cid)] = (name or phone or "").strip() or None
            except Exception:  # noqa: BLE001
                self.db.rollback()

        result: dict[str, Optional[str]] = {}
        for r in rows:
            et = (r.source_entity_type or "").strip()
            sid = str(r.source_entity_id) if r.source_entity_id else None
            ref: Optional[str] = None
            if et == "complaint" and sid:
                ref = complaint_map.get(sid)
            elif et == "stock_inquiry" and sid:
                ref = inquiry_map.get(sid)
            elif et in ("purchase_request", "sponsorship_form") and sid:
                ref = pr_map.get(sid)
            elif et == "ticket" and sid:
                ref = ticket_map.get(sid)
            elif r.respond_contact_id:
                ref = contact_map.get(str(r.respond_contact_id))
            result[str(r.id)] = ref
        return result

    def get_preferred_tracking_for_contact(
        self, contact: RespondContact
    ) -> Optional[ConversationSLATracking]:
        """Prefer open tracking, else most recent by created_at."""
        from sqlalchemy.orm import joinedload
        from app.models.sla import ConversationSLAEventLog

        return (
            self.db.query(ConversationSLATracking)
            .options(
                joinedload(ConversationSLATracking.policy),
                joinedload(ConversationSLATracking.contact),
                joinedload(ConversationSLATracking.assigned_user),
                joinedload(ConversationSLATracking.event_logs).joinedload(ConversationSLAEventLog.assigned_user),
            )
            .filter(
                ConversationSLATracking.respond_contact_id == contact.id,
                conversation_tracking_scope(),
            )
            .order_by(
                ConversationSLATracking.is_resolved.asc(),
                ConversationSLATracking.created_at.desc(),
            )
            .first()
        )

    def resolve_respond_contact(
        self,
        *,
        phone_number: Optional[str] = None,
        contact_id: Optional[str] = None,
    ) -> tuple[Optional[RespondContact], Optional[str]]:
        """
        Resolve RespondContact from phone and/or contact_id.

        contact_id matches respond_io_id first, then respond_contacts.id.

        Returns (contact, conflict_error_message). conflict_error_message is set when both
        identifiers are provided but refer to different contacts.
        """
        phone = (phone_number or "").strip()
        cid = (contact_id or "").strip()
        if not phone and not cid:
            return None, None
        by_phone: Optional[RespondContact] = None
        by_cid: Optional[RespondContact] = None
        if phone:
            by_phone = (
                self.db.query(RespondContact)
                .filter(RespondContact.phone_number == phone)
                .first()
            )
        if cid:
            by_cid = (
                self.db.query(RespondContact)
                .filter(RespondContact.respond_io_id == cid)
                .first()
            )
            if not by_cid:
                by_cid = (
                    self.db.query(RespondContact)
                    .filter(RespondContact.id == cid)
                    .first()
                )
        if phone and cid:
            if (
                by_cid is not None
                and by_phone is not None
                and str(getattr(by_cid, "id")) != str(getattr(by_phone, "id"))
            ):
                return None, "contact_id and phone_number refer to different contacts."
            if by_cid is not None:
                return by_cid, None
            return by_phone, None
        if cid:
            return by_cid, None
        return by_phone, None

    def get_tracking_by_phone_or_contact_id(
        self,
        *,
        phone_number: Optional[str] = None,
        contact_id: Optional[str] = None,
    ) -> Optional[ConversationSLATracking]:
        """
        Latest SLA tracking for the contact (open first, else newest).
        Pass contact_id (Respond.io id or CRM respond_contacts.id) and/or phone_number.
        """
        contact, _err = self.resolve_respond_contact(
            phone_number=phone_number, contact_id=contact_id
        )
        if not contact:
            return None
        return self.get_preferred_tracking_for_contact(contact)

    def get_tracking_by_contact_phone(self, phone: str) -> Optional[ConversationSLATracking]:
        """
        Get the conversation SLA tracking for a contact by phone number.
        Prefers an unresolved (open) tracking; otherwise returns the most recent by created_at.
        """
        normalized = (phone or "").strip()
        if not normalized:
            return None
        contact = self.db.query(RespondContact).filter(
            RespondContact.phone_number == normalized
        ).first()
        if not contact:
            return None
        return self.get_preferred_tracking_for_contact(contact)

    def get_tracking_by_contact_and_policy(
        self,
        respond_contact_id: str,
        policy_id: str,
    ) -> Optional[ConversationSLATracking]:
        """
        Get the conversation SLA tracking for a contact and policy.
        Prefers an unresolved (open) tracking; otherwise returns the most recent by created_at.
        """
        from sqlalchemy.orm import joinedload
        from app.models.sla import ConversationSLAEventLog

        tracking = (
            self.db.query(ConversationSLATracking)
            .options(
                joinedload(ConversationSLATracking.policy),
                joinedload(ConversationSLATracking.contact),
                joinedload(ConversationSLATracking.event_logs).joinedload(ConversationSLAEventLog.assigned_user),
            )
            .filter(
                ConversationSLATracking.respond_contact_id == respond_contact_id,
                ConversationSLATracking.policy_id == policy_id,
                conversation_tracking_scope(),
            )
            .order_by(
                ConversationSLATracking.is_resolved.asc(),  # False first
                ConversationSLATracking.created_at.desc(),
            )
            .first()
        )
        return tracking

    def resolve_internal_respond_contact_id(self, respond_contact_id: str) -> Optional[str]:
        """Map API respond_contact_id to respond_contacts.id (CRM id, Respond.io id, or phone / E.164)."""
        from app.models.access import RespondContact

        raw = str(respond_contact_id or "").strip()
        if not raw:
            return None
        row = self.db.query(RespondContact).filter(RespondContact.id == raw).first()
        if row:
            return str(row.id)
        row = self.db.query(RespondContact).filter(RespondContact.respond_io_id == raw).first()
        if row:
            return str(row.id)
        candidates = _respond_contact_phone_lookup_candidates(raw)
        if candidates:
            row = (
                self.db.query(RespondContact)
                .filter(RespondContact.phone_number.in_(candidates))
                .first()
            )
            if row:
                return str(row.id)
        return None

    # Map source_entity_type (on tracking) to access agent code for tier-based escalation.
    ENTITY_TYPE_TO_AGENT_CODE = {
        "complaint": "complaint",
        "stock_inquiry": "lead_time_enquiries",
        "purchase_request": "purchase_request",
    }

    def get_escalation_assignee_for_tier(
        self,
        source_entity_type: Optional[str],
        target_tier: int,
        team_set_code: Optional[str] = None,
        agent_code_override: Optional[str] = None,
        agent_id_override: Optional[str] = None,
    ) -> dict:
        """
        Resolve the next assignee for escalation to the given tier using agent tier-team and round-robin.
        Uses only that tier's round-robin cursor (no dependency on the previous tier's assignee).
        Priority: agent_id_override (UUID FK) > agent_code_override > source_entity_type mapping.
        Returns dict with id, email, name, respond_user_id. Raises if agent or tier team not configured.
        """
        from app.services.user_service import AccessAgentService
        from app.models.access import AccessAgent

        agent_svc = AccessAgentService(self.db)

        if agent_id_override:
            agent_id = str(agent_id_override)
            # Resolve display code for error messages
            _agent = self.db.query(AccessAgent).filter(AccessAgent.id == agent_id).first()
            agent_code = _agent.code if _agent else agent_id
        elif agent_code_override and agent_code_override.strip():
            agent_code = agent_code_override.strip()
            agent_id = agent_svc.get_agent_id_by_code(agent_code)
        else:
            agent_code = self.ENTITY_TYPE_TO_AGENT_CODE.get(
                (source_entity_type or "").strip().lower()
            ) or "complaint"
            agent_id = agent_svc.get_agent_id_by_code(agent_code)

        if not agent_id:
            raise handle_validation_error(
                f"No access agent found with code '{agent_code}'. Cannot resolve escalation assignee. "
                "Create the Access Agent and assign tier teams (tier 1, 2, 3)."
            )
        team_id = agent_svc.get_team_id_by_tier(
            agent_id,
            target_tier,
            team_set_code=team_set_code,
        )
        if not team_id:
            suffix = (
                f" in team set '{team_set_code}'"
                if team_set_code
                else ""
            )
            raise handle_validation_error(
                f"No team assigned for agent '{agent_code}' with tier {target_tier}{suffix}. "
                f"Add a Team Assignment with Tier = {target_tier} for this agent."
            )
        assignee = agent_svc.get_next_assignee(agent_id, team_id)
        if not assignee:
            raise handle_validation_error(
                f"No assignee in team for agent '{agent_code}' tier {target_tier}. Ensure the team has members."
            )
        return assignee

    def escalate_tracking(
        self,
        respond_contact_id: str,
        policy_id: str,
        current_tier: int,
        escalation_reason: str,
    ) -> ConversationSLATracking:
        """
        Escalate a conversation SLA tracking by respond_contact_id and policy_id: set new tier,
        timestamps, and recalculate due_at (response) and due_at_resolution from policy tier KPIs.
        Creates an escalation event log. Called by external system via integration API.
        """
        from datetime import timedelta

        tracking = self.get_tracking_by_contact_and_policy(respond_contact_id, policy_id)
        if not tracking:
            raise handle_not_found(
                "Conversation SLA tracking",
                f"respond_contact_id={respond_contact_id}, policy_id={policy_id}",
            )
        if bool(getattr(tracking, "is_resolved", False)):
            raise handle_validation_error(
                "Cannot escalate a resolved conversation SLA tracking."
            )

        tier = self.db.query(SLAPolicyTier).filter(
            SLAPolicyTier.policy_id == tracking.policy_id,
            SLAPolicyTier.tier_level == current_tier,
        ).first()
        if not tier:
            raise handle_validation_error(
                f"SLA policy tier {current_tier} not found for policy {tracking.policy_id}."
            )

        from_tier = tracking.current_tier
        now_utc = _now_utc()
        initiated_at_raw = getattr(tracking, "initiated_at", None)
        initiated_at_utc = _to_aware_utc(
            initiated_at_raw if isinstance(initiated_at_raw, datetime) else None
        )
        response_hours_raw = getattr(tier, "response_hours", None)
        response_hours = float(response_hours_raw) if response_hours_raw is not None else 24.0
        resolution_hours_raw = getattr(tier, "resolution_hours", None)
        resolution_hours = float(resolution_hours_raw) if resolution_hours_raw is not None else 24.0

        setattr(tracking, "current_tier", current_tier)
        setattr(tracking, "current_tier_started_at", now_utc)
        setattr(tracking, "escalated_at", now_utc)
        setattr(tracking, "escalation_reason", escalation_reason)
        setattr(tracking, "due_at", now_utc + timedelta(hours=response_hours))
        # On escalation, due_at_resolution = escalation time (now) + resolution_hours from policy
        setattr(tracking, "due_at_resolution", now_utc + timedelta(hours=resolution_hours))

        self.db.flush()
        self.create_event_log(
            ConversationSLAEventLogCreate(
                sla_tracking_id=str(getattr(tracking, "id")),
                event_type="escalation",
                from_tier=(
                    int(from_tier)
                    if isinstance(from_tier, (int, str, float))
                    else None
                ),
                to_tier=current_tier,
                event_at=now_utc,
                reason=escalation_reason,
                assigned_to_id=(
                    str(getattr(tracking, "assigned_to_id"))
                    if getattr(tracking, "assigned_to_id", None) is not None
                    else None
                ),
                due_at=(
                    getattr(tracking, "due_at")
                    if isinstance(getattr(tracking, "due_at", None), datetime)
                    else None
                ),
            )
        )
        self.db.refresh(tracking)
        return tracking

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
                conversation_tracking_scope(),
            )
            .first()
        )
        if tracking is None or getattr(tracking, "assigned_to_id", None) is None:
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
            response_obj = getattr(e, "response", None)
            response_text = getattr(response_obj, "text", None)
            if isinstance(response_text, str) and response_text:
                resp_payload = response_text[:2000] if len(response_text) > 2000 else response_text
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

        if str(getattr(tracking, "assigned_to_id", "")) == str(getattr(user, "id")):
            return {"updated": False, "message": "Sync successful. Assignee already in sync."}

        self.update_tracking(tracking_id, ConversationSLATrackingUpdate(assigned_to=assignee_respond_id))
        # Assignee-driven routing correction (see apply_assignee_team_derivation).
        derivation = self.apply_assignee_team_derivation(
            tracking_id, str(user.id), source="sync-assignee"
        )
        tracking = self.get_tracking(tracking_id)
        return {
            "updated": True,
            "message": "Assignee synced from Respond.io.",
            "assigned_to_id": str(user.id),
            "assigned_to": user.name or user.email or assignee_respond_id,
            "routing": derivation,
        }

    def set_assignee_for_tracking(self, tracking_id: str, assignee_respond_user_id: str) -> dict:
        """
        Update the assignee on Conversation SLA Tracking in our system only (no Respond.io call).
        Used by external API: look up tracking by contact phone, then update assigned_to/assigned_to_id.

        After the assignee update, routing is re-derived from the new assignee's team
        membership (apply_assignee_team_derivation): a tier-1 member pulls the tracking to
        their (agent, team_set) at tier 1; a tier-2/3 member of the current team set moves
        the tier to match; otherwise agent/team/tier stay as-is. Tier/team changes restart
        the tier clock and log a 'reassignment' event.

        For resolved trackings, this still updates only assignee fields and keeps resolution status.
        assignee_respond_user_id: Respond.io user id (e.g. 1023495). Use empty string to unassign.
        """
        from app.models.user import User

        tracking = self.get_tracking(tracking_id)
        original_assignee = (
            (tracking.assigned_user.name or tracking.assigned_user.email)
            if tracking.assigned_user else (tracking.assigned_to or None)
        )
        original_tier = tracking.current_tier

        assignee_id = (assignee_respond_user_id or "").strip()
        user = None
        if assignee_id:
            user = self.db.query(User).filter(User.respond_user_id == assignee_id).first()

        update_kw: dict = {"assigned_to": assignee_id if assignee_id else None}
        self.update_tracking(tracking_id, ConversationSLATrackingUpdate(**update_kw))

        # Assignee-driven routing correction: re-derive agent/team(/tier) from the new
        # assignee's team membership so escalation follows the correct team afterwards.
        # Unassign carries no routing signal — skip derivation.
        derivation = None
        if user is not None:
            derivation = self.apply_assignee_team_derivation(
                tracking_id, str(user.id), source="conversation-assignee"
            )

        tracking = self.get_tracking(tracking_id)
        phone = None
        if tracking.contact:
            phone = (getattr(tracking.contact, "phone_number", None) or "").strip()
        changed_at_utc = _now_utc()
        changed_at_malaysia = changed_at_utc.astimezone(MALAYSIA_TZ)
        assignee_changed_at = f"{changed_at_malaysia.strftime('%Y-%m-%d %H:%M:%S')} +08"
        return {
            "updated": True,
            "message": "Conversation SLA tracking assignee updated.",
            "tracking_id": tracking_id,
            "contact_phone": phone,
            "original_assignee": original_assignee,
            "original_tier": original_tier,
            "current_tier": tracking.current_tier,
            "team_set_code": getattr(tracking, "team_set_code", None),
            "routing": derivation,
            "assigned_to": (user.name or user.email or assignee_id) if user else (assignee_id or None),
            "assigned_to_id": str(user.id) if user else None,
            "assignee_respond_user_id": assignee_id or None,
            "assignee_changed_at": assignee_changed_at,
        }

    def derive_team_for_assignee(
        self,
        user_id: str,
        current_agent_id: Optional[str] = None,
        current_team_set_code: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Resolve the (agent_id, team_set_code, tier, team_id) an assignee belongs to, for
        assignee-driven routing correction (PLAN-sla-assignee-team-derivation).

        Step 1 — global tier-1 lookup: the user's unique tier-1-linked TEAM wins (team-level
        invariant enforced in TeamService/AccessAgentService: a user belongs to at most one
        team that is linked at tier 1). The same team is commonly linked at tier 1 under
        many agents (shared executive pools), so among that team's tier-1 links prefer the
        tracking's current agent (agent stays put, only the team set flips); otherwise pick
        the deterministic first link (code, then agent_id) — tier-2/3 configuration is
        expected to be equivalent across those agents.
        Step 2 — scoped tier-2/3 lookup: otherwise, if the user is in the tier-2/3 team of
        the tracking's current (agent_id, team_set_code), keep agent/team and return the
        matched tier (lowest when in both).
        Step 3 — None: unknown user, or a manager of some other team set (ambiguous).
        """
        import logging
        from app.models.access import AgentTeam, TeamMember

        uid = (user_id or "").strip()
        if not uid:
            return None

        tier1_links = (
            self.db.query(AgentTeam)
            .join(TeamMember, TeamMember.team_id == AgentTeam.team_id)
            .filter(TeamMember.user_id == uid, AgentTeam.tier == 1)
            .order_by(AgentTeam.code.asc(), AgentTeam.agent_id.asc())
            .all()
        )
        distinct_teams = {str(l.team_id) for l in tier1_links}
        if len(distinct_teams) > 1:
            # Team-level invariant violated (config predates enforcement) — ambiguous.
            logging.getLogger(__name__).warning(
                "User %s is a member of multiple tier-1-linked teams %s; "
                "skipping assignee-driven routing.",
                uid,
                sorted(distinct_teams),
            )
            return None
        if tier1_links:
            link = next(
                (
                    l
                    for l in tier1_links
                    if current_agent_id and str(l.agent_id) == str(current_agent_id)
                ),
                tier1_links[0],
            )
            return {
                "agent_id": str(link.agent_id),
                "team_set_code": str(link.code),
                "tier": 1,
                "team_id": str(link.team_id),
            }

        if current_agent_id and current_team_set_code:
            scoped = (
                self.db.query(AgentTeam)
                .join(TeamMember, TeamMember.team_id == AgentTeam.team_id)
                .filter(
                    TeamMember.user_id == uid,
                    AgentTeam.agent_id == str(current_agent_id),
                    AgentTeam.code == str(current_team_set_code),
                    AgentTeam.tier.in_([2, 3]),
                )
                .order_by(AgentTeam.tier.asc())
                .first()
            )
            if scoped:
                return {
                    "agent_id": str(scoped.agent_id),
                    "team_set_code": str(scoped.code),
                    "tier": int(getattr(scoped, "tier")),
                    "team_id": str(scoped.team_id),
                }
        return None

    def apply_assignee_team_derivation(
        self, tracking_id: str, user_id: str, source: str
    ) -> Optional[dict]:
        """
        After an assignee change, re-derive (agent_id, team_set_code, current_tier) from the
        new assignee's team membership and apply when different.

        - Tier or team change restarts the tier clock (current_tier_started_at = now;
          due_at / due_at_resolution from the policy's matched-tier hours) and writes a
          'reassignment' event log row (including team-only changes at the same tier).
        - Team change advances the round-robin cursor of the new (agent, team) to the
          manually picked assignee so auto-assign continues fairly after them.
        - Returns a change summary dict, or None when no derivation / nothing changed.
        """
        from app.models.access import AgentTeamRoundRobinCursor

        from app.services.form_sla_service import FORM_SLA_TYPES

        tracking = self.get_tracking(tracking_id)
        # Resolved trackings clear escalation routing on resolve — never resurrect it.
        if bool(getattr(tracking, "is_resolved", False)):
            return None
        # Form SLA trackings own their routing via FormSLAConfig stages — assignee changes
        # must not flip stage-configured agent/team. Conversation trackings only.
        if (getattr(tracking, "source_entity_type", None) or "") in FORM_SLA_TYPES:
            return None
        current_agent_id = getattr(tracking, "agent_id", None)
        current_team_set = getattr(tracking, "team_set_code", None)
        derived = self.derive_team_for_assignee(
            user_id,
            current_agent_id=str(current_agent_id) if current_agent_id else None,
            current_team_set_code=str(current_team_set) if current_team_set else None,
        )
        if not derived:
            return None

        from_tier = int(getattr(tracking, "current_tier", 0) or 0)
        team_changed = (
            str(current_agent_id or "") != derived["agent_id"]
            or str(current_team_set or "") != derived["team_set_code"]
        )
        tier_changed = from_tier != derived["tier"]
        if not team_changed and not tier_changed:
            return None

        now_utc = _now_utc()
        setattr(tracking, "agent_id", derived["agent_id"])
        setattr(tracking, "team_set_code", derived["team_set_code"])
        setattr(tracking, "current_tier", derived["tier"])

        # Restart the tier clock from the matched tier's policy hours. If the tier row is
        # missing (misconfigured policy), keep existing clocks — routing fix still applies.
        tier_row = self.db.query(SLAPolicyTier).filter(
            SLAPolicyTier.policy_id == tracking.policy_id,
            SLAPolicyTier.tier_level == derived["tier"],
        ).first()
        if tier_row is not None:
            response_hours = float(getattr(tier_row, "response_hours", None) or 24.0)
            resolution_hours = float(getattr(tier_row, "resolution_hours", None) or 24.0)
            setattr(tracking, "current_tier_started_at", now_utc)
            setattr(tracking, "due_at", now_utc + timedelta(hours=response_hours))
            setattr(tracking, "due_at_resolution", now_utc + timedelta(hours=resolution_hours))

        # Advance the new team's round-robin cursor to the manual pick before the event-log
        # commit so everything lands in one transaction.
        if team_changed:
            cursor = (
                self.db.query(AgentTeamRoundRobinCursor)
                .filter(
                    AgentTeamRoundRobinCursor.agent_id == derived["agent_id"],
                    AgentTeamRoundRobinCursor.team_id == derived["team_id"],
                )
                .with_for_update()
                .first()
            )
            if cursor:
                setattr(cursor, "last_assigned_user_id", str(user_id))
            else:
                self.db.add(
                    AgentTeamRoundRobinCursor(
                        agent_id=derived["agent_id"],
                        team_id=derived["team_id"],
                        last_assigned_user_id=str(user_id),
                    )
                )

        reason_parts = [f"assignee correction via {source}"]
        if team_changed:
            reason_parts.append(
                f"team_set: {current_team_set or '—'} → {derived['team_set_code']}"
            )
        self.db.flush()
        self.create_event_log(
            ConversationSLAEventLogCreate(
                sla_tracking_id=str(getattr(tracking, "id")),
                event_type="reassignment",
                from_tier=from_tier if from_tier >= 1 else None,
                to_tier=derived["tier"],
                event_at=now_utc,
                reason="; ".join(reason_parts),
                assigned_to_id=str(user_id),
                due_at=(
                    getattr(tracking, "due_at")
                    if isinstance(getattr(tracking, "due_at", None), datetime)
                    else None
                ),
            )
        )
        return {
            "routing_updated": True,
            "team_changed": team_changed,
            "tier_changed": tier_changed,
            "from_tier": from_tier or None,
            "to_tier": derived["tier"],
            "from_team_set_code": current_team_set,
            "team_set_code": derived["team_set_code"],
            "agent_id": derived["agent_id"],
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

        # Resolve agent_code → agent_id (FK). When no assignee is passed, pick via round-robin
        # for current_tier (same as escalation). When assigned_to / assigned_to_id is passed
        # (e.g. after external next-assignee), use it and do not advance the tier cursor again.
        raw_agent_code = tracking_dict.pop("agent_code", None)
        aid_raw = tracking_dict.get("assigned_to_id")
        ato_raw = tracking_dict.get("assigned_to")
        has_explicit_assignee = (
            (aid_raw is not None and str(aid_raw).strip() != "")
            or (ato_raw is not None and str(ato_raw).strip() != "")
        )
        if raw_agent_code:
            from app.models.access import AccessAgent as _AccessAgent
            from app.models.user import User as _User

            _agent = self.db.query(_AccessAgent).filter(
                _AccessAgent.code == raw_agent_code.strip()
            ).first()
            if not _agent:
                raise handle_validation_error(
                    f"No access agent found with code '{raw_agent_code}'. "
                    "Create the Access Agent first."
                )
            tracking_dict["agent_id"] = str(_agent.id)
            if has_explicit_assignee:
                if aid_raw is not None and str(aid_raw).strip():
                    user = self.db.query(_User).filter(_User.id == str(aid_raw).strip()).first()
                    if not user:
                        raise handle_validation_error(
                            f"User not found for assigned_to_id: {aid_raw}"
                        )
                    tracking_dict["assigned_to_id"] = user.id
                    rid = getattr(user, "respond_user_id", None)
                    tracking_dict["assigned_to"] = (
                        str(rid).strip() if rid is not None and str(rid).strip() else None
                    )
                else:
                    assigned_to_value = str(ato_raw).strip()
                    user = self.db.query(_User).filter(
                        (_User.respond_user_id == assigned_to_value)
                        | (_User.id == assigned_to_value)
                        | (_User.email == assigned_to_value)
                    ).first()
                    if not user:
                        raise handle_validation_error(
                            f"User not found for respond_user_id: {assigned_to_value}"
                        )
                    tracking_dict["assigned_to_id"] = user.id
                    rid = getattr(user, "respond_user_id", None)
                    tracking_dict["assigned_to"] = (
                        str(rid).strip()
                        if rid is not None and str(rid).strip()
                        else assigned_to_value
                    )
            else:
                assignee = self.get_escalation_assignee_for_tier(
                    source_entity_type=None,
                    target_tier=tracking_dict["current_tier"],
                    team_set_code=tracking_dict.get("team_set_code") or None,
                    agent_id_override=str(_agent.id),
                )
                tracking_dict["assigned_to_id"] = assignee["id"]
                tracking_dict["assigned_to"] = (
                    str(assignee["respond_user_id"])
                    if assignee.get("respond_user_id") is not None
                    else None
                )
        elif not tracking_dict.get("assigned_to_id") and tracking_dict.get("assigned_to"):
            # Fallback: resolve explicit assigned_to (respond_user_id / user id / email) to assigned_to_id
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

        # Calculate due_at (response) and due_at_resolution from current_tier_started_at + tier hours
        current_tier_started_at = _to_aware_utc(tracking_dict["current_tier_started_at"])
        response_hours_raw = getattr(tier, "response_hours", None)
        response_hours = float(response_hours_raw) if response_hours_raw is not None else 24.0
        resolution_hours_raw = getattr(tier, "resolution_hours", None)
        resolution_hours = float(resolution_hours_raw) if resolution_hours_raw is not None else 24.0
        if current_tier_started_at:
            tracking_dict["due_at"] = current_tier_started_at + timedelta(hours=response_hours)
            tracking_dict["due_at_resolution"] = current_tier_started_at + timedelta(hours=resolution_hours)
        else:
            tracking_dict["due_at"] = None
            tracking_dict["due_at_resolution"] = None

        # Singleton check: one open conversation tracking per contact (mirrors the
        # Respond.io conversation). Scoped to conversation rows — an active form-SLA
        # stage row for the same contact must not block (or be returned by) this.
        existing = self.db.query(ConversationSLATracking).filter(
            ConversationSLATracking.respond_contact_id == tracking_dict["respond_contact_id"],
            conversation_tracking_scope(),
        ).order_by(
            ConversationSLATracking.is_resolved.asc(),  # open first
            ConversationSLATracking.created_at.desc(),
        ).first()

        if existing:
            if not bool(getattr(existing, "is_resolved", False)):
                # Active conversation already tracked — idempotent hit. The new inbound
                # message belongs to the same open Respond.io conversation: return the
                # existing tracking untouched (clocks, assignee, agent, team) except for
                # message_id, refreshed so inbox deep-links point at the latest message.
                if tracking_dict.get("message_id") is not None:
                    setattr(existing, "message_id", tracking_dict["message_id"])
                    self.db.commit()
                    self.db.refresh(existing)
                setattr(existing, "_already_active", True)
                return existing

            # Existing tracking is resolved — overwrite it for the new conversation.
            # History is carried by event logs (kept: FK by tracking id), not by rows.
            preserve_fields = {"id", "created_at", "respond_contact_id"}
            for key, value in tracking_dict.items():
                if key not in preserve_fields:
                    setattr(existing, key, value)

            self.db.commit()
            self.db.refresh(existing)
            self._write_assign_event_log(existing)
            setattr(existing, "_overwrote_resolved", True)
            return existing

        # Create new tracking record (set due_at_resolution explicitly so it is never omitted)
        tracking = ConversationSLATracking(**tracking_dict)
        if tracking_dict.get("due_at_resolution") is not None:
            setattr(tracking, "due_at_resolution", tracking_dict["due_at_resolution"])
        if tracking_dict.get("due_at") is not None:
            setattr(tracking, "due_at", tracking_dict["due_at"])
        self.db.add(tracking)
        self.db.commit()
        self.db.refresh(tracking)
        self._write_assign_event_log(tracking)
        return tracking

    def _write_assign_event_log(self, tracking: ConversationSLATracking) -> None:
        """Write the initial 'assign' event log for a newly started conversation.

        Owned by the backend (n8n's flow no longer posts it) so an idempotent
        create hit cannot produce duplicate assign logs.

        Best-effort: the tracking row is already committed when this runs, so a
        failure here must not fail the create — n8n would get a 500 for a create
        that succeeded, and its retry would take the idempotent path which never
        backfills the log. Log a warning and continue instead.
        """
        import logging

        try:
            assignee_ref = (
                getattr(tracking, "assigned_to_id", None)
                or getattr(tracking, "assigned_to", None)
            )
            label, user_id = event_log_assignee_fields(self.db, assignee_ref)
            tier = getattr(tracking, "current_tier", 1)
            due_at = getattr(tracking, "due_at", None)
            self.create_event_log(ConversationSLAEventLogCreate(
                sla_tracking_id=str(tracking.id),
                event_type="assign",
                from_tier=tier,
                to_tier=tier,
                event_at=_now_utc(),
                assigned_to=label,
                assigned_to_id=user_id,
                # DB stores naive UTC; pass aware UTC so create_event_log's
                # naive-means-MYT normalization doesn't shift it by -8h.
                due_at=_to_aware_utc(due_at) if isinstance(due_at, datetime) else None,
                reason=f"New Assignee {label}" if label else "New conversation tracking",
            ))
        except Exception:
            self.db.rollback()
            logging.getLogger(__name__).warning(
                "Failed to write assign event log for tracking %s; "
                "tracking exists without its initial assign log.",
                getattr(tracking, "id", None),
                exc_info=True,
            )
    
    def update_tracking(self, tracking_id: str, tracking_data: ConversationSLATrackingUpdate):
        """Update a tracking record."""
        from datetime import datetime, timezone
        from decimal import Decimal, ROUND_HALF_UP
        from app.models.user import User
        
        tracking = self.get_tracking(tracking_id)
        
        update_data = tracking_data.model_dump(exclude_unset=True)

        # Resolve agent_code → agent_id FK if caller passed a code string
        raw_agent_code = update_data.pop("agent_code", None)
        if raw_agent_code:
            from app.models.access import AccessAgent as _AccessAgent
            _agent = self.db.query(_AccessAgent).filter(
                _AccessAgent.code == raw_agent_code.strip()
            ).first()
            if not _agent:
                raise handle_validation_error(
                    f"No access agent found with code '{raw_agent_code}'. "
                    "Create the Access Agent first."
                )
            update_data["agent_id"] = str(_agent.id)
        elif "agent_code" in tracking_data.model_fields_set and raw_agent_code is None:
            # Explicitly set to null — clear the FK
            update_data["agent_id"] = None

        # Explicitly clear assignee when assigned_to is None (keep in sync with Respond.io)
        if "assigned_to" in update_data and update_data["assigned_to"] is None:
            update_data["assigned_to_id"] = None

        # Resolve assigned_to to assigned_to_id when it's a non-empty string
        if "assigned_to_id" not in update_data and (
            update_data.get("assigned_to") is not None and str(update_data.get("assigned_to")).strip()
        ):
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

        # Short-circuit: caller tries to resolve an already-resolved tracking.
        # Return current state with a transient marker; let the route signal
        # "already resolved, not updated" via response header. n8n decides routing.
        if is_resolved and bool(getattr(tracking, "is_resolved", False)):
            setattr(tracking, "_already_resolved", True)
            return tracking

        # Smart handling for is_responded (same as responded_at / responded_by)
        if is_responded:
            if bool(getattr(tracking, "is_responded", False)):
                raise handle_validation_error("Conversation is already responded.")
            _resp_by = update_data.get("responded_by")
            if _resp_by is None or (isinstance(_resp_by, str) and not str(_resp_by).strip()):
                _aid = self._resolve_tracking_assignee_user_id(tracking)
                if _aid:
                    update_data["responded_by"] = _aid
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
                initiated_at = getattr(tracking, "initiated_at", None)
                if isinstance(initiated_at, datetime) and responded_at_utc:
                    initiated_at_utc_val = _to_aware_utc(initiated_at)
                    duration = (
                        (responded_at_utc - initiated_at_utc_val).total_seconds() / 3600
                        if initiated_at_utc_val is not None
                        else 0.0
                    )
                    update_data["response_time"] = Decimal(str(max(0, duration))).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
            
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
        resolved_in_this_request = False
        if is_resolved:
            # Short-circuit above already returned for already-resolved case.
            resolved_in_this_request = True
            _res_by = update_data.get("resolved_by")
            if _res_by is None or (isinstance(_res_by, str) and not str(_res_by).strip()):
                _rid = self._resolve_tracking_assignee_user_id(tracking)
                if _rid:
                    update_data["resolved_by"] = _rid
            update_data["is_resolved"] = True
            # Conversation SLA: unset assignee + escalation routing on resolve so n8n / external
            # API stops looking at the row. Form SLA: keep all those fields so the audit trail
            # (agent / stage / assignee at resolution) survives in the per-form SLA Tracking tab.
            from app.services.form_sla_service import FORM_SLA_TYPES

            _is_form_tracker = (
                getattr(tracking, "source_entity_type", None) in FORM_SLA_TYPES
            )
            if not _is_form_tracker:
                update_data["assigned_to"] = None
                update_data["assigned_to_id"] = None
                update_data["agent_id"] = None
                update_data["team_set_code"] = None
                update_data["message_id"] = None
            # Always set resolved_at when marking resolved (UTC)
            if "resolved_at" not in update_data or update_data.get("resolved_at") is None:
                update_data["resolved_at"] = _now_utc()
            
            # Auto-calculate resolution_duration from initiated_at to resolved_at (UTC)
            if "resolution_duration" not in update_data or update_data.get("resolution_duration") is None:
                resolved_at = update_data["resolved_at"]
                if isinstance(resolved_at, str):
                    resolved_at = datetime.fromisoformat(resolved_at.replace('Z', '+00:00'))
                resolved_at_utc = _to_aware_utc(resolved_at)
                initiated_at = getattr(tracking, "initiated_at", None)
                if isinstance(initiated_at, datetime) and resolved_at_utc:
                    initiated_at_utc_val = _to_aware_utc(initiated_at)
                    duration = (
                        (resolved_at_utc - initiated_at_utc_val).total_seconds() / 3600
                        if initiated_at_utc_val is not None
                        else 0.0
                    )
                    update_data["resolution_duration"] = Decimal(str(max(0, duration))).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
            
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

        # Force NULL for routing / external ids on resolve. Some session edge cases (e.g. after a prior
        # commit in the same request) can leave ORM-only clears from not flushing; a direct UPDATE
        # matches DB state (used by test-overrides "Mark as resolved" and all other resolve paths).
        # Skip for form trackers — they keep agent / team / assignee for audit.
        from app.services.form_sla_service import FORM_SLA_TYPES as _FORM_TYPES

        if resolved_in_this_request and (
            getattr(tracking, "source_entity_type", None) not in _FORM_TYPES
        ):
            self.db.execute(
                update(ConversationSLATracking)
                .where(ConversationSLATracking.id == tracking.id)
                .values(message_id=None, team_set_code=None, agent_id=None)
            )

        self.db.commit()
        self.db.refresh(tracking)
        return tracking

    def admin_test_override_tracking(self, tracking_id: str, updates: dict):
        """
        Apply assignee / timestamp overrides for testing. Recalculates due_at when tier start changes.
        `updates` should be model_dump(exclude_unset=True) from ConversationSLATestOverrideRequest.
        """
        from app.models.user import User
        from app.schemas.sla import ConversationSLATrackingUpdate

        if not updates:
            raise handle_validation_error("No fields to update.")

        tracking = self.get_tracking(tracking_id)
        now_utc = _now_utc()
        old_assigned_to_id = tracking.assigned_to_id
        old_assigned_to = tracking.assigned_to
        old_current_tier_started_at = tracking.current_tier_started_at
        old_initiated_at = tracking.initiated_at
        assign_changed = False
        current_tier_started_changed = False
        initiated_at_changed = False

        if "assigned_to_id" in updates:
            aid = updates["assigned_to_id"]
            if aid is None or (isinstance(aid, str) and not str(aid).strip()):
                setattr(tracking, "assigned_to_id", None)
                setattr(tracking, "assigned_to", None)
                assign_changed = (
                    old_assigned_to_id is not None or old_assigned_to is not None
                )
            else:
                user = self.db.query(User).filter(User.id == str(aid).strip()).first()
                if not user:
                    raise handle_validation_error("User not found for assigned_to_id.")
                setattr(tracking, "assigned_to_id", str(getattr(user, "id")))
                setattr(
                    tracking,
                    "assigned_to",
                    str(user.respond_user_id) if user.respond_user_id is not None else None,
                )
                assign_changed = str(old_assigned_to_id or "") != str(user.id)

        if "current_tier_started_at" in updates:
            raw = updates["current_tier_started_at"]
            if isinstance(raw, str):
                raw = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if not isinstance(raw, datetime):
                raise handle_validation_error("current_tier_started_at must be a datetime.")
            started = _to_aware_utc(raw)
            if started is None:
                raise handle_validation_error("current_tier_started_at must be a valid datetime.")
            setattr(tracking, "current_tier_started_at", started)

            tier = self.db.query(SLAPolicyTier).filter(
                SLAPolicyTier.policy_id == tracking.policy_id,
                SLAPolicyTier.tier_level == tracking.current_tier,
            ).first()
            if not tier:
                raise handle_validation_error(
                    f"No tier {tracking.current_tier} for this policy."
                )
            response_hours_raw = getattr(tier, "response_hours", None)
            response_hours = float(response_hours_raw) if response_hours_raw is not None else 24.0
            resolution_hours_raw = getattr(tier, "resolution_hours", None)
            resolution_hours = float(resolution_hours_raw) if resolution_hours_raw is not None else 24.0
            setattr(tracking, "due_at", started + timedelta(hours=response_hours))
            setattr(tracking, "due_at_resolution", started + timedelta(hours=resolution_hours))
            current_tier_started_changed = (
                _to_aware_utc(
                    old_current_tier_started_at
                    if isinstance(old_current_tier_started_at, datetime)
                    else None
                )
                != started
            )

        if "initiated_at" in updates:
            raw = updates["initiated_at"]
            if isinstance(raw, str):
                raw = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if not isinstance(raw, datetime):
                raise handle_validation_error("initiated_at must be a datetime.")
            initiated = _to_aware_utc(raw)
            if initiated is None:
                raise handle_validation_error("initiated_at must be a valid datetime.")
            setattr(tracking, "initiated_at", initiated)
            initiated_at_changed = (
                _to_aware_utc(old_initiated_at if isinstance(old_initiated_at, datetime) else None)
                != initiated
            )

        # Delegate is_responded / is_resolved to the smart update logic (handles auto-calc, validation).
        status_updates = {}
        if "is_responded" in updates and updates["is_responded"] is True:
            status_updates["is_responded"] = True
        if "is_resolved" in updates and updates["is_resolved"] is True:
            status_updates["is_resolved"] = True

        self.db.commit()
        self.db.refresh(tracking)

        if assign_changed:
            assignee_name = (
                tracking.assigned_user.name
                if getattr(tracking, "assigned_user", None)
                else None
            )
            reason = (
                f"New Assignee {assignee_name}"
                if assignee_name
                else "Assignee cleared"
            )
            self.create_event_log(
                ConversationSLAEventLogCreate(
                    sla_tracking_id=str(getattr(tracking, "id")),
                    event_type="assign",
                    from_tier=int(getattr(tracking, "current_tier", 0)),
                    to_tier=int(getattr(tracking, "current_tier", 0)),
                    event_at=now_utc,
                    reason=reason,
                    assigned_to=(
                        str(getattr(tracking, "assigned_to"))
                        if getattr(tracking, "assigned_to", None) is not None
                        else None
                    ),
                    assigned_to_id=(
                        str(getattr(tracking, "assigned_to_id"))
                        if getattr(tracking, "assigned_to_id", None) is not None
                        else None
                    ),
                    due_at=(
                        getattr(tracking, "due_at")
                        if isinstance(getattr(tracking, "due_at", None), datetime)
                        else None
                    ),
                )
            )

        if current_tier_started_changed:
            self.create_event_log(
                ConversationSLAEventLogCreate(
                    sla_tracking_id=str(getattr(tracking, "id")),
                    event_type="adjust",
                    from_tier=int(getattr(tracking, "current_tier", 0)),
                    to_tier=int(getattr(tracking, "current_tier", 0)),
                    event_at=now_utc,
                    reason="Adjusted current tier started at for testing.",
                    assigned_to=(
                        str(getattr(tracking, "assigned_to"))
                        if getattr(tracking, "assigned_to", None) is not None
                        else None
                    ),
                    assigned_to_id=(
                        str(getattr(tracking, "assigned_to_id"))
                        if getattr(tracking, "assigned_to_id", None) is not None
                        else None
                    ),
                    due_at=(
                        getattr(tracking, "due_at")
                        if isinstance(getattr(tracking, "due_at", None), datetime)
                        else None
                    ),
                )
            )

        if initiated_at_changed:
            self.create_event_log(
                ConversationSLAEventLogCreate(
                    sla_tracking_id=str(getattr(tracking, "id")),
                    event_type="adjust",
                    from_tier=int(getattr(tracking, "current_tier", 0)),
                    to_tier=int(getattr(tracking, "current_tier", 0)),
                    event_at=now_utc,
                    reason="Adjusted initiated at for testing.",
                    assigned_to=(
                        str(getattr(tracking, "assigned_to"))
                        if getattr(tracking, "assigned_to", None) is not None
                        else None
                    ),
                    assigned_to_id=(
                        str(getattr(tracking, "assigned_to_id"))
                        if getattr(tracking, "assigned_to_id", None) is not None
                        else None
                    ),
                    due_at=(
                        getattr(tracking, "due_at")
                        if isinstance(getattr(tracking, "due_at", None), datetime)
                        else None
                    ),
                )
            )

        if status_updates:
            updated_tracking = self.update_tracking(
                tracking_id, ConversationSLATrackingUpdate(**status_updates)
            )

            if status_updates.get("is_responded") is True:
                alabel, aid = event_log_assignee_fields(
                    self.db,
                    (
                        str(getattr(updated_tracking, "responded_by"))
                        if getattr(updated_tracking, "responded_by", None) is not None
                        else None
                    ),
                )
                self.create_event_log(
                    ConversationSLAEventLogCreate(
                        sla_tracking_id=tracking_id,
                        event_type="response",
                        from_tier=int(getattr(updated_tracking, "current_tier", 0)),
                        to_tier=int(getattr(updated_tracking, "current_tier", 0)),
                        assigned_to=alabel,
                        assigned_to_id=aid,
                        reason="Responded",
                    )
                )

            if status_updates.get("is_resolved") is True:
                alabel, aid = event_log_assignee_fields(
                    self.db,
                    (
                        str(getattr(updated_tracking, "resolved_by"))
                        if getattr(updated_tracking, "resolved_by", None) is not None
                        else None
                    ),
                )
                self.create_event_log(
                    ConversationSLAEventLogCreate(
                        sla_tracking_id=tracking_id,
                        event_type="resolution",
                        from_tier=int(getattr(updated_tracking, "current_tier", 0)),
                        to_tier=int(getattr(updated_tracking, "current_tier", 0)),
                        assigned_to=alabel,
                        assigned_to_id=aid,
                        reason="Resolved",
                    )
                )

            return updated_tracking

        return self.get_tracking(tracking_id)

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
        """Create an SLA event log entry. Must not update the tracking record or recalculate due_at/due_at_resolution."""
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
        
        def _normalize_api_datetime_to_utc(value):
            """
            Normalize API datetime input to timezone-aware UTC.
            Naive values are interpreted as Malaysia local time (UTC+8).
            """
            if value is None:
                return None
            dt = value
            if isinstance(dt, str):
                dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            if not isinstance(dt, datetime):
                raise handle_validation_error("Invalid datetime payload in event log.")
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=MALAYSIA_TZ)
            return dt.astimezone(timezone.utc)

        # Auto-populate event_at to now (UTC)
        if not log_dict.get("event_at"):
            log_dict["event_at"] = _now_utc()
        else:
            log_dict["event_at"] = _normalize_api_datetime_to_utc(log_dict.get("event_at"))

        # Normalize optional datetime fields if supplied.
        for field in ("from_time", "due_at", "last_reminder_at"):
            if field in log_dict and log_dict.get(field) is not None:
                log_dict[field] = _normalize_api_datetime_to_utc(log_dict.get(field))
        
        # For response or resolution events, auto-populate from_time and duration
        event_type = log_dict.get("event_type", "").lower()
        if event_type in ["response", "resolution"]:
            # Get the tracking record to access initiated_at
            tracking = self.db.query(ConversationSLATracking).filter(
                ConversationSLATracking.id == log_dict["sla_tracking_id"]
            ).first()
            
            if tracking is not None and isinstance(getattr(tracking, "initiated_at", None), datetime):
                # Set from_time to initiated_at (UTC)
                initiated_at = getattr(tracking, "initiated_at", None)
                if isinstance(initiated_at, str):
                    initiated_at = datetime.fromisoformat(initiated_at.replace("Z", "+00:00"))
                log_dict["from_time"] = _to_aware_utc(initiated_at) if isinstance(initiated_at, datetime) else initiated_at
                
                # Calculate duration from initiated_at to event_at (UTC)
                event_at = log_dict["event_at"]
                if isinstance(event_at, str):
                    event_at = datetime.fromisoformat(str(event_at).replace("Z", "+00:00"))
                initiated_at_utc = _to_aware_utc(initiated_at if isinstance(initiated_at, datetime) else None)
                event_at_utc = _to_aware_utc(event_at)
                if initiated_at_utc and event_at_utc:
                    duration_seconds = (event_at_utc - initiated_at_utc).total_seconds()
                    duration_seconds = max(0.0, duration_seconds)  # clamp for bad legacy data
                    duration_hours = Decimal(str(duration_seconds / 3600)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    log_dict["duration"] = duration_hours

            if not log_dict.get("assigned_to_id") and tracking:
                uid_ref = (
                    tracking.responded_by
                    if event_type == "response"
                    else tracking.resolved_by
                )
                if uid_ref is not None and str(uid_ref).strip():
                    label, uid = event_log_assignee_fields(self.db, str(uid_ref))
                    if uid:
                        log_dict["assigned_to_id"] = uid
                    if label:
                        log_dict["assigned_to"] = label
        
        log = ConversationSLAEventLog(**log_dict)
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log
    
    def list_event_logs(
        self,
        page: int = 1,
        limit: int = 50,
        sort_field: Optional[str] = "event_at",
        sort_dir: Optional[str] = "desc",
        tracking_id: Optional[str] = None,
        event_type: Optional[str] = None,
        assigned_to: Optional[str] = None,
        assigned_to_id: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ):
        """List SLA event logs with filtering. date_from/date_to filter on event_at (inclusive, UTC)."""
        from datetime import datetime, timezone
        from sqlalchemy.orm import joinedload
        from app.schemas.common import ListResponse, PaginationResponse
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
        if assigned_to_id:
            q = q.filter(ConversationSLAEventLog.assigned_to_id == assigned_to_id)
        if date_from:
            try:
                dt = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
                if dt.tzinfo is not None:
                    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                q = q.filter(ConversationSLAEventLog.event_at >= dt)
            except ValueError:
                pass
        if date_to:
            try:
                dt = datetime.fromisoformat(date_to.replace("Z", "+00:00"))
                if dt.tzinfo is not None:
                    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                end = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
                q = q.filter(ConversationSLAEventLog.event_at <= end)
            except ValueError:
                pass

        total = q.count()

        sort_map = {
            "event_type": ConversationSLAEventLog.event_type,
            "from_tier": ConversationSLAEventLog.from_tier,
            "to_tier": ConversationSLAEventLog.to_tier,
            "event_at": ConversationSLAEventLog.event_at,
            "from_time": ConversationSLAEventLog.from_time,
            "duration": ConversationSLAEventLog.duration,
            "reason": ConversationSLAEventLog.reason,
            "assigned_user_name": ConversationSLAEventLog.assigned_to,
            "assigned_to": ConversationSLAEventLog.assigned_to,
            "created_at": ConversationSLAEventLog.created_at,
        }
        order_col = sort_map.get((sort_field or "").strip(), ConversationSLAEventLog.event_at)
        order_expr = order_col.desc() if str(sort_dir or "desc").lower() == "desc" else order_col.asc()
        logs = q.order_by(order_expr).offset((page - 1) * limit).limit(limit).all()

        # Build response items as dicts (same shape as get_tracking) to avoid ORM->schema validation edge cases
        data = []
        for log in logs:
            item = {
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
                "reminder_count": log.reminder_count or 0,
                "last_reminder_at": log.last_reminder_at,
                "created_at": log.created_at,
                "assigned_user": (
                    {
                        "id": log.assigned_user.id,
                        "email": log.assigned_user.email or "",
                        "name": getattr(log.assigned_user, "name", None),
                    }
                    if log.assigned_user
                    else None
                ),
                "assigned_user_name": log.assigned_user.name if log.assigned_user else None,
                "assigned_user_email": log.assigned_user.email if log.assigned_user else None,
            }
            data.append(ConversationSLAEventLogResponse.model_validate(item))

        return ListResponse(
            data=data,
            pagination=PaginationResponse(total=total, page=page, limit=limit),
        )
    
    def get_dashboard_metrics(self):
        """Get dashboard metrics for SLA tracking."""
        from datetime import datetime, timedelta
        from decimal import Decimal

        def _safe_log_hours(log: ConversationSLAEventLog, kind: str) -> Optional[float]:
            try:
                # Prefer duration; fallback to explicit fields for older data.
                duration = getattr(log, "duration", None)
                response_time = getattr(log, "response_time", None)
                resolution_time = getattr(log, "resolution_time", None)
                if isinstance(duration, (Decimal, int, float, str)):
                    return float(duration)
                if kind == "response" and isinstance(response_time, (Decimal, int, float, str)):
                    return float(response_time)
                if kind == "resolution" and isinstance(resolution_time, (Decimal, int, float, str)):
                    return float(resolution_time)
            except (TypeError, ValueError):
                return None
            return None

        now_utc = _now_utc()
        thirty_days_ago = now_utc - timedelta(days=30)

        # Conversation dashboard excludes form trackers (those have their own per-form view).
        all_trackings = (
            self.db.query(ConversationSLATracking)
            .filter(conversation_tracking_scope())
            .all()
        )
        all_logs = self.db.query(ConversationSLAEventLog).all()
        response_logs = [l for l in all_logs if (l.event_type or "").lower() == "response"]
        resolution_logs = [l for l in all_logs if (l.event_type or "").lower() == "resolution"]

        total_trackings = len(all_trackings)
        responded_count = sum(1 for t in all_trackings if bool(getattr(t, "is_responded", False)))
        resolved_count = sum(1 for t in all_trackings if bool(getattr(t, "is_resolved", False)))
        pending_count = total_trackings - responded_count  # not yet responded
        responded_not_resolved_count = sum(
            1
            for t in all_trackings
            if bool(getattr(t, "is_responded", False)) and not bool(getattr(t, "is_resolved", False))
        )
        escalated_count = sum(1 for t in all_trackings if t.escalated_at is not None)

        # Overdue: not responded and due_at passed; not resolved and due_at_resolution passed
        overdue_at_response_count = 0
        overdue_at_resolution_count = 0
        overdue_at_resolution_responded_count = 0
        for t in all_trackings:
            if not bool(getattr(t, "is_responded", False)) and getattr(t, "due_at", None) is not None:
                due_at_raw = getattr(t, "due_at", None)
                due_at_utc = _to_aware_utc(due_at_raw if isinstance(due_at_raw, datetime) else None)
                if due_at_utc and due_at_utc < now_utc:
                    overdue_at_response_count += 1
            if not bool(getattr(t, "is_resolved", False)) and getattr(t, "due_at_resolution", None) is not None:
                due_res_raw = getattr(t, "due_at_resolution", None)
                due_res_utc = _to_aware_utc(due_res_raw if isinstance(due_res_raw, datetime) else None)
                if due_res_utc and due_res_utc < now_utc:
                    overdue_at_resolution_count += 1
                    if bool(getattr(t, "is_responded", False)):
                        overdue_at_resolution_responded_count += 1

        # Average durations (hours) from event logs
        response_times = [_safe_log_hours(l, "response") for l in response_logs]
        response_times = [t for t in response_times if t is not None]
        average_response_time = sum(response_times) / len(response_times) if response_times else 0.0

        resolution_times = [_safe_log_hours(l, "resolution") for l in resolution_logs]
        resolution_times = [t for t in resolution_times if t is not None]
        average_resolution_time = sum(resolution_times) / len(resolution_times) if resolution_times else 0.0

        # Calculate escalation rate
        escalation_rate = float(escalated_count / total_trackings * 100) if total_trackings > 0 else 0.0

        # Trends (last 30 days) from event logs by event_at date.
        response_resolution_trends = []
        for i in range(30):
            date = now_utc - timedelta(days=29 - i)
            date_str = date.date().isoformat()

            day_response_logs = []
            for log in response_logs:
                event_at_raw = getattr(log, "event_at", None)
                event_at = _to_aware_utc(event_at_raw if isinstance(event_at_raw, datetime) else None)
                if event_at and event_at >= thirty_days_ago and event_at.date().isoformat() == date_str:
                    day_response_logs.append(log)
            day_resolution_logs = []
            for log in resolution_logs:
                event_at_raw = getattr(log, "event_at", None)
                event_at = _to_aware_utc(event_at_raw if isinstance(event_at_raw, datetime) else None)
                if event_at and event_at >= thirty_days_ago and event_at.date().isoformat() == date_str:
                    day_resolution_logs.append(log)

            day_response_times = [_safe_log_hours(l, "response") for l in day_response_logs]
            day_response_times = [v for v in day_response_times if v is not None]
            day_resolution_times = [_safe_log_hours(l, "resolution") for l in day_resolution_logs]
            day_resolution_times = [v for v in day_resolution_times if v is not None]

            response_resolution_trends.append({
                "date": date_str,
                "average_response_time": (sum(day_response_times) / len(day_response_times)) if day_response_times else 0.0,
                "average_resolution_time": (sum(day_resolution_times) / len(day_resolution_times)) if day_resolution_times else 0.0,
            })

        # Escalation rates by tier
        escalation_by_tier = {}
        for t in all_trackings:
            if getattr(t, "escalated_at", None) is not None and getattr(t, "current_tier", None) is not None:
                try:
                    tier_value = getattr(t, "current_tier", None)
                    if isinstance(tier_value, (int, str, float)):
                        tier_level = int(tier_value)
                    else:
                        tier_level = 0
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
            "responded_not_resolved": responded_not_resolved_count,
            "pending": pending_count,
        }

        pending_response_overdue_breakdown = {
            "not_yet_overdue": max(0, pending_count - overdue_at_response_count),
            "overdue_at_response": overdue_at_response_count,
        }
        responded_resolution_overdue_breakdown = {
            "not_yet_overdue": max(0, responded_not_resolved_count - overdue_at_resolution_responded_count),
            "overdue_at_resolution": overdue_at_resolution_responded_count,
        }
        
        return {
            "total_trackings": total_trackings,
            "pending_count": pending_count,
            "responded_count": responded_count,
            "responded_not_resolved_count": responded_not_resolved_count,
            "resolved_count": resolved_count,
            "escalated_count": escalated_count,
            "overdue_at_response_count": overdue_at_response_count,
            "overdue_at_resolution_count": overdue_at_resolution_count,
            "average_response_time": average_response_time,
            "average_resolution_time": average_resolution_time,
            "escalation_rate": escalation_rate,
            "response_time_trends": response_resolution_trends,
            "response_resolution_trends": response_resolution_trends,
            "escalation_rates_by_tier": escalation_rates_by_tier,
            "resolution_time_distribution": resolution_time_distribution,
            "status_breakdown": status_breakdown,
            "pending_response_overdue_breakdown": pending_response_overdue_breakdown,
            "responded_resolution_overdue_breakdown": responded_resolution_overdue_breakdown,
        }

    def _respond_io_identifier_for_tracking(self, tracking: ConversationSLATracking) -> Optional[str]:
        if tracking.contact and getattr(tracking.contact, "respond_io_id", None):
            s = str(tracking.contact.respond_io_id).strip()
            return s or None
        return None

    def fetch_respond_conversation_for_tracking(
        self, tracking_id: str, limit: int = 50, cursor: Optional[str] = None
    ) -> dict:
        tracking = self.get_tracking(tracking_id)
        ident = self._respond_io_identifier_for_tracking(tracking)
        if not ident:
            return {"items": [], "pagination": {}, "error": "No Respond.io contact linked"}
        from app.services.integration_service import RespondClient

        client = RespondClient()
        return client.list_messages(ident, limit=limit, cursor=cursor)

    def send_conversation_reply_for_tracking(
        self,
        tracking_id: str,
        message: str,
        respond_user_id: str,
        crm_sender_user_id: Optional[str] = None,
        request_url: str = "",
    ) -> dict:
        import logging

        logger = logging.getLogger(__name__)
        tracking = self.get_tracking(tracking_id)
        ident = self._respond_io_identifier_for_tracking(tracking)
        if not ident:
            raise handle_validation_error("No Respond.io contact linked for this tracking.")
        text = (message or "").strip()
        if not text:
            raise handle_validation_error("message is required.")
        from app.services.integration_service import RespondClient
        from app.services.crm_chat_outbound_webhook import (
            enqueue_crm_chat_outbound_webhook,
            resolve_assignee_respond_user_id_from_tracking,
        )

        client = RespondClient()
        try:
            response = client.send_message(ident, text)
        except Exception:
            logger.exception("Respond send failed for SLA tracking %s", tracking_id)
            raise
        enqueue_crm_chat_outbound_webhook(
            self.db,
            business_table="conversation_sla_tracking",
            business_id=str(tracking_id),
            contact_respond_io_id=ident,
            message_text=text,
            respond_api_response=response if isinstance(response, dict) else None,
            space_id=None,
            crm_sender_user_id=crm_sender_user_id,
            respond_user_id_fallback=respond_user_id,
            assignee_respond_user_id=resolve_assignee_respond_user_id_from_tracking(self.db, tracking),
        )
        return response if isinstance(response, dict) else {}