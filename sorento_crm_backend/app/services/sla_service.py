"""SLA service for business logic."""
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from typing import Optional
from app.models.sla import SLAPolicy, SLAPolicyTier, ConversationSLATracking, ConversationSLAEventLog
from app.models.access import RespondContact
from app.schemas.sla import (
    SLAPolicyCreate, SLAPolicyUpdate, SLAPolicyTierCreate, SLAPolicyTierUpdate,
    ConversationSLATrackingCreate, ConversationSLATrackingUpdate, ConversationSLAEventLogCreate
)
from app.services.error_handler import handle_not_found, handle_conflict, handle_validation_error


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


class ConversationSLATrackingService:
    """Service for conversation SLA tracking operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def list_tracking(self, page: int = 1, limit: int = 50, policy_id: Optional[str] = None):
        """List SLA tracking records."""
        from sqlalchemy.orm import joinedload
        from app.models.sla import ConversationSLAEventLog
        # Eagerly load policy, contact, assigned_user, and event_logs with their assigned_user
        q = self.db.query(ConversationSLATracking).options(
            joinedload(ConversationSLATracking.policy),
            joinedload(ConversationSLATracking.contact),
            joinedload(ConversationSLATracking.assigned_user),
            joinedload(ConversationSLATracking.event_logs).joinedload(ConversationSLAEventLog.assigned_user)
        )
        
        if policy_id:
            q = q.filter(ConversationSLATracking.policy_id == policy_id)
        
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
            
            track_dict = {
                "id": str(track.id),
                "policy_id": str(track.policy_id),
                "current_tier": track.current_tier,
                "assigned_to": track.assigned_to,  # Keep for backward compatibility
                "assigned_to_id": track.assigned_to_id,
                "initiated_at": track.initiated_at,
                "current_tier_started_at": track.current_tier_started_at,
                "due_at": track.due_at,
                "escalated_at": track.escalated_at,
                "escalation_reason": track.escalation_reason,
                "is_responded": track.is_responded,
                "responded_at": track.responded_at,
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
                "event_logs": []  # Initialize as empty
            }
            
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
        
        # Sort event logs by event_at chronologically
        if tracking.event_logs:
            tracking.event_logs.sort(key=lambda x: x.event_at)
        
        return tracking
    
    def create_tracking(self, tracking_data: ConversationSLATrackingCreate):
        """Create a new tracking record."""
        tracking_dict = tracking_data.model_dump()
        contact_phone_number = tracking_dict.pop("contact_phone_number", None)

        if not tracking_dict.get("respond_contact_id") and contact_phone_number:
            normalized_phone = contact_phone_number.strip()
            contact = self.db.query(RespondContact).filter(
                RespondContact.phone_number == normalized_phone
            ).first()
            if not contact:
                raise handle_validation_error(
                    f"Respond contact not found for phone number: {normalized_phone}"
                )
            tracking_dict["respond_contact_id"] = contact.id

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

        # Check unique constraint on respond_contact_id
        if tracking_dict.get("respond_contact_id"):
            existing = self.db.query(ConversationSLATracking).filter(
                ConversationSLATracking.respond_contact_id == tracking_dict["respond_contact_id"]
            ).first()
            if existing:
                raise handle_conflict("Tracking already exists for this contact.")

        # If assigned_to_id is provided, use it; otherwise keep assigned_to for backward compatibility
        tracking = ConversationSLATracking(**tracking_dict)
        self.db.add(tracking)
        self.db.commit()
        self.db.refresh(tracking)
        return tracking
    
    def update_tracking(self, tracking_id: str, tracking_data: ConversationSLATrackingUpdate):
        """Update a tracking record."""
        tracking = self.get_tracking(tracking_id)
        
        update_data = tracking_data.model_dump(exclude_unset=True)
        if "assigned_to_id" not in update_data and update_data.get("assigned_to"):
            from app.models.user import User

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
        for key, value in update_data.items():
            setattr(tracking, key, value)
        
        self.db.commit()
        self.db.refresh(tracking)
        return tracking

    def create_event_log(self, event_data: ConversationSLAEventLogCreate):
        """Create an SLA event log entry."""
        from app.models.user import User
        
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
        
        if not log_dict.get("event_at"):
            log_dict["event_at"] = func.now()
        
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
        from datetime import datetime, timedelta
        from decimal import Decimal
        
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
            total_duration = sum(
                float(t.resolution_duration) if isinstance(t.resolution_duration, Decimal)
                else float(t.resolution_duration or 0)
                for t in resolved_trackings
            )
            average_resolution_time = total_duration / len(resolved_trackings)
        
        # Calculate escalation rate
        escalation_rate = float(escalated_count / total_trackings * 100) if total_trackings > 0 else 0.0
        
        # Response time trends (last 30 days)
        from datetime import timezone
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        recent_trackings = [
            t for t in all_trackings
            if t.initiated_at and t.initiated_at.replace(tzinfo=timezone.utc) >= thirty_days_ago
        ]
        
        response_time_trends = []
        for i in range(30):
            date = datetime.now(timezone.utc) - timedelta(days=29 - i)
            date_str = date.date().isoformat()
            
            day_trackings = [
                t for t in recent_trackings
                if t.initiated_at and t.initiated_at.date().isoformat() == date_str
            ]
            
            avg_response_time = 0.0
            if day_trackings:
                total_duration = sum(
                    float(t.resolution_duration) if isinstance(t.resolution_duration, Decimal)
                    else float(t.resolution_duration or 0)
                    for t in day_trackings
                )
                avg_response_time = total_duration / len(day_trackings)
            
            response_time_trends.append({
                "date": date_str,
                "average_response_time": avg_response_time,
            })
        
        # Escalation rates by tier
        escalation_by_tier = {}
        for t in all_trackings:
            if t.escalated_at and t.current_tier is not None:
                tier_level = int(t.current_tier) if isinstance(t.current_tier, (int, str)) else 0
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