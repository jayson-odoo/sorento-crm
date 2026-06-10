"""SLA management schemas."""
from pydantic import BaseModel, BeforeValidator, field_validator, model_validator, model_serializer, ConfigDict
from typing import Annotated, Optional
from datetime import datetime, timezone
from decimal import Decimal
import uuid


def _coerce_optional_message_id(v):
    """Accept int, numeric string, or null for external message ids (e.g. n8n)."""
    if v is None:
        return None
    if isinstance(v, bool):
        raise ValueError("message_id must be an integer")
    if isinstance(v, str):
        s = v.strip()
        if not s or s.lower() in ("null", "undefined", "[null]", "[undefined]"):
            return None
        try:
            return int(s)
        except ValueError as e:
            raise ValueError("message_id must be a valid integer") from e
    if isinstance(v, float):
        if not v.is_integer():
            raise ValueError("message_id must be a whole number")
        return int(v)
    if isinstance(v, int):
        return v
    raise ValueError("message_id must be an integer")


OptionalMessageId = Annotated[Optional[int], BeforeValidator(_coerce_optional_message_id)]


class SLAPolicyTierBase(BaseModel):
    policy_id: str
    tier_level: int
    tier_name: str
    response_hours: int
    resolution_hours: int = 24


class SLAPolicyTierCreate(SLAPolicyTierBase):
    pass


class SLAPolicyTierUpdate(BaseModel):
    tier_level: Optional[int] = None
    tier_name: Optional[str] = None
    response_hours: Optional[int] = None
    resolution_hours: Optional[int] = None


class SLAPolicyTierResponse(SLAPolicyTierBase):
    id: str
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class SLAPolicyBase(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    is_active: bool = True


class SLAPolicyCreate(SLAPolicyBase):
    tiers: Optional[list[SLAPolicyTierCreate]] = None


class SLAPolicyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class SLAPolicyResponse(SLAPolicyBase):
    id: str
    created_at: datetime
    updated_at: datetime
    tiers_count: Optional[int] = 0
    tracking_count: Optional[int] = 0
    
    model_config = ConfigDict(from_attributes=True)


class ConversationSLATrackingBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    policy_id: str
    current_tier: int
    assigned_to: Optional[str] = None  # Keep for backward compatibility
    assigned_to_id: Optional[str] = None  # FK to users
    initiated_at: datetime
    current_tier_started_at: datetime
    due_at: datetime  # Response deadline
    due_at_resolution: Optional[datetime] = None  # Resolution deadline (current_tier_started_at + tier.resolution_hours)
    escalated_at: Optional[datetime] = None
    escalation_reason: Optional[str] = None
    is_responded: bool = False
    responded_at: Optional[datetime] = None
    responded_by: Optional[str] = None
    response_time: Optional[Decimal] = None
    is_resolved: bool = False
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    respond_contact_id: Optional[str] = None  # FK to respond_contacts
    resolution_duration: Optional[Decimal] = None
    agent_id: Optional[str] = None  # FK to access_agents.id
    team_set_code: Optional[str] = None
    message_id: Optional[int] = None  # External message id; cleared when resolved


class ConversationSLATrackingCreate(BaseModel):
    policy_id: str
    current_tier: int
    assigned_to: Optional[str] = None  # Keep for backward compatibility
    assigned_to_id: Optional[str] = None  # FK to users
    initiated_at: Optional[datetime] = None  # Auto-populated to now if not provided
    current_tier_started_at: Optional[datetime] = None  # Auto-populated to now if not provided
    # due_at is calculated from policy tier, not provided by requester
    escalated_at: Optional[datetime] = None  # Will be reset to None
    escalation_reason: Optional[str] = None  # Will be reset to None
    is_responded: bool = False
    responded_at: Optional[datetime] = None  # Will be reset to None
    responded_by: Optional[str] = None  # Will be reset to None
    response_time: Optional[Decimal] = None  # Will be reset to None
    is_resolved: bool = False  # Will be reset to False
    resolved_at: Optional[datetime] = None  # Will be reset to None
    resolved_by: Optional[str] = None  # Will be reset to None
    respond_contact_id: Optional[str] = None  # FK to respond_contacts
    resolution_duration: Optional[Decimal] = None  # Will be reset to None
    agent_code: Optional[str] = None  # resolved → agent_id FK in service
    team_set_code: Optional[str] = None  # Team assignment set code for escalation
    message_id: OptionalMessageId = None
    contact_phone_number: str  # Required field

    @field_validator('contact_phone_number')
    @classmethod
    def validate_contact_phone_number(cls, v):
        """Validate contact_phone_number is not empty, null, or undefined."""
        if v is None:
            raise ValueError("contact_phone_number is required and cannot be null or undefined")
        v_str = str(v).strip()
        if not v_str or v_str.lower() in ['null', 'undefined', '[undefined]', '[null]']:
            raise ValueError("contact_phone_number is required and cannot be empty, null, or undefined")
        return v_str


class ConversationSLATrackingUpdate(BaseModel):
    current_tier: Optional[int] = None
    current_tier_started_at: Optional[datetime] = None
    assigned_to: Optional[str] = None
    due_at: Optional[datetime] = None
    due_at_resolution: Optional[datetime] = None
    escalated_at: Optional[datetime] = None
    escalation_reason: Optional[str] = None
    is_responded: Optional[bool] = None
    responded_at: Optional[datetime] = None
    responded_by: Optional[str] = None
    response_time: Optional[Decimal] = None
    is_resolved: Optional[bool] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolution_duration: Optional[Decimal] = None
    resolution_time: Optional[Decimal] = None
    agent_code: Optional[str] = None  # resolved → agent_id FK in service
    team_set_code: Optional[str] = None
    message_id: OptionalMessageId = None

    @model_validator(mode='after')
    def map_resolution_time(self):
        """Allow resolution_time as an alias for resolution_duration."""
        if self.resolution_duration is None and self.resolution_time is not None:
            self.resolution_duration = self.resolution_time
        return self


class ConversationSLATestOverrideRequest(BaseModel):
    """Gated by sla_management.conversation_sla_tracking.test_override. At least one field required in the request body."""
    assigned_to_id: Optional[str] = None
    current_tier_started_at: Optional[datetime] = None
    initiated_at: Optional[datetime] = None
    is_responded: Optional[bool] = None
    is_resolved: Optional[bool] = None

    @model_validator(mode='after')
    def at_least_one_field(self):
        updatable = {"assigned_to_id", "current_tier_started_at", "initiated_at", "is_responded", "is_resolved"}
        if not (self.model_fields_set & updatable):
            raise ValueError(
                "Provide at least one of: assigned_to_id (including null to unassign), "
                "current_tier_started_at, initiated_at, is_responded, or is_resolved."
            )
        return self


class ConversationSLATrackingStatusUpdate(BaseModel):
    is_responded: Optional[bool] = None
    responded_at: Optional[datetime] = None
    responded_by: Optional[str] = None
    response_time: Optional[Decimal] = None
    is_resolved: Optional[bool] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolution_duration: Optional[Decimal] = None
    resolution_time: Optional[Decimal] = None

    @model_validator(mode='after')
    def map_resolution_time(self):
        """Allow resolution_time as an alias for resolution_duration."""
        if self.resolution_duration is None and self.resolution_time is not None:
            self.resolution_duration = self.resolution_time
        return self


class ConversationSLAEscalateRequest(BaseModel):
    """Request body for external escalation API (by respond_contact_id and policy_id).

    respond_contact_id: CRM respond_contacts.id, Respond.io id, or phone (E.164 / variants).
    """
    respond_contact_id: str
    policy_id: str
    # Target tier after escalation (1–3), must be greater than the row's current tier.
    # Omit (None) for signal-only escalation: the server escalates to current tier + 1,
    # or returns escalated=false when already at tier 3.
    current_tier: Optional[int] = None
    # Omit for signal-only callers (e.g. the scheduled n8n runner, which doesn't know the
    # tier before the call): the server fills an auto-escalation reason using from_tier.
    escalation_reason: Optional[str] = None
    team_set_code: Optional[str] = None  # Optional team set key to resolve tier within a set

    @field_validator("respond_contact_id")
    @classmethod
    def validate_respond_contact_id(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            raise ValueError("respond_contact_id is required")
        return str(v).strip()

    @field_validator("policy_id")
    @classmethod
    def validate_policy_id(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            raise ValueError("policy_id is required")
        return str(v).strip()

    @field_validator("escalation_reason")
    @classmethod
    def validate_reason(cls, v):
        # Optional: explicit null / blank normalizes to None (same as omitting the field);
        # the service fills the auto-escalation default. Validators don't run on the
        # default, so None must be accepted here too or explicit-null callers get a 422.
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return str(v).strip()


class SLAPolicySimple(BaseModel):
    """Simple policy reference for tracking responses."""
    id: str
    code: str
    name: str
    
    model_config = ConfigDict(from_attributes=True)


class AgentSimple(BaseModel):
    """Simple access agent reference for tracking responses."""
    id: str
    code: str
    name: str

    model_config = ConfigDict(from_attributes=True)


class ContactSimple(BaseModel):
    """Simple contact reference for tracking responses."""
    id: str
    phone_number: str
    name: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)


class UserSuperiorSimple(BaseModel):
    """Superior of assigned user (for tooltip)."""
    name: Optional[str] = None
    email: Optional[str] = None


class UserSimple(BaseModel):
    """Simple user reference for tracking responses."""
    id: str
    email: str
    name: Optional[str] = None
    superior: Optional[UserSuperiorSimple] = None  # For assignee tooltip in tracking detail

    model_config = ConfigDict(from_attributes=True)


class ConversationSLAEventLogResponse(BaseModel):
    """SLA event log response schema."""
    id: str
    sla_tracking_id: str
    event_type: str
    from_tier: Optional[int] = None
    to_tier: Optional[int] = None
    event_at: datetime
    from_time: Optional[datetime] = None  # For response/resolution events, stores initiated_at
    duration: Optional[Decimal] = None  # Duration in hours, calculated for response/resolution events
    reason: Optional[str] = None
    assigned_to: Optional[str] = None  # Keep for backward compatibility
    assigned_to_id: Optional[str] = None
    due_at: Optional[datetime] = None
    response_time: Optional[Decimal] = None
    resolution_time: Optional[Decimal] = None
    reminder_count: int = 0
    last_reminder_at: Optional[datetime] = None
    created_at: datetime
    # Related objects
    assigned_user: Optional[UserSimple] = None
    # Computed fields
    assigned_user_name: Optional[str] = None  # From assigned_user.name
    assigned_user_email: Optional[str] = None  # From assigned_user.email
    
    model_config = ConfigDict(from_attributes=True)
    
    @model_serializer(mode='wrap', when_used='json')
    def serialize_model(self, serializer, info):
        """Custom serialization to convert timezone-aware datetimes to naive UTC strings."""
        data = serializer(self)
        # Convert timezone-aware datetimes to naive UTC
        datetime_fields = ['event_at', 'from_time', 'due_at', 'last_reminder_at', 'created_at']
        for field in datetime_fields:
            if field in data and data[field] is not None:
                value = getattr(self, field)
                if isinstance(value, datetime) and value.tzinfo is not None:
                    # Convert to UTC and remove timezone for naive representation
                    data[field] = value.astimezone(timezone.utc).replace(tzinfo=None).isoformat()
        return data
    
    @field_validator('sla_tracking_id', mode='before')
    @classmethod
    def convert_uuid(cls, v):
        """Convert UUID objects to strings."""
        if v is None:
            return None
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v else None
    
    @field_validator('assigned_to', mode='before')
    @classmethod
    def convert_text_field(cls, v):
        """Convert UUID objects to strings for text fields."""
        if v is None:
            return None
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v else None
    
    @model_validator(mode='after')
    def populate_computed_fields(self):
        """Populate computed fields from relationships."""
        # Populate assigned_user_name and assigned_user_email from assigned_user relationship
        if self.assigned_user:
            self.assigned_user_name = self.assigned_user.name
            self.assigned_user_email = self.assigned_user.email
        else:
            # If no assigned_user relationship, set to None
            self.assigned_user_name = None
            self.assigned_user_email = None
        
        return self


class ConversationSLAEventLogCreate(BaseModel):
    sla_tracking_id: str
    event_type: str
    from_tier: Optional[int] = None
    to_tier: Optional[int] = None
    event_at: Optional[datetime] = None
    from_time: Optional[datetime] = None  # For response/resolution events, stores initiated_at
    duration: Optional[Decimal] = None  # Duration in hours, calculated for response/resolution events
    reason: Optional[str] = None
    assigned_to: Optional[str] = None  # Keep for backward compatibility
    assigned_to_id: Optional[str] = None  # FK to users
    due_at: Optional[datetime] = None
    response_time: Optional[Decimal] = None
    resolution_time: Optional[Decimal] = None


class ConversationSLATrackingResponse(ConversationSLATrackingBase):
    id: str
    created_at: datetime
    updated_at: datetime
    synced_to_excel: bool = False
    last_synced_to_excel: Optional[datetime] = None
    policy: Optional[SLAPolicySimple] = None
    event_logs: Optional[list[ConversationSLAEventLogResponse]] = []
    # Foreign key fields
    respond_contact_id: Optional[str] = None
    respond_io_id: Optional[str] = None  # Respond.io contact id for inbox URL
    assigned_to_id: Optional[str] = None
    # Related objects
    contact: Optional[ContactSimple] = None
    assigned_user: Optional[UserSimple] = None
    agent: Optional[AgentSimple] = None  # FK to access_agents
    # Renamed field for API consumers
    response_duration: Optional[Decimal] = None
    # Computed fields for backward compatibility
    agent_code: Optional[str] = None  # Resolved from agent.code FK
    contact_phone: Optional[str] = None  # From contact.phone_number or respond_contact_phone
    contact_name: Optional[str] = None  # From contact.name or respond_contact_name
    assigned_user_name: Optional[str] = None  # From assigned_user.name
    assigned_user_email: Optional[str] = None  # From assigned_user.email
    assigned_user_superior_name: Optional[str] = None  # From assigned_user.superior (for tooltip)
    assigned_user_superior_email: Optional[str] = None  # From assigned_user.superior (for tooltip)
    responded_by_user_name: Optional[str] = None  # Looked up from responded_by user ID
    resolved_by_user_name: Optional[str] = None  # Looked up from resolved_by user ID
    # Average times calculated from event logs
    average_response_time: Optional[Decimal] = None  # Average duration from event logs with event_type="response"
    average_resolution_time: Optional[Decimal] = None  # Average duration from event logs with event_type="resolution"
    # Time-in-tier and time-remaining (computed; response timers stop when is_responded, resolution when is_resolved)
    time_in_tier_response_seconds: Optional[float] = None
    time_remaining_response_seconds: Optional[float] = None
    time_in_tier_resolution_seconds: Optional[float] = None
    time_remaining_resolution_seconds: Optional[float] = None
    resolution_due_at: Optional[datetime] = None  # current_tier_started_at + tier.resolution_hours
    # Tier KPI hours (for frontend to color response_time / resolution_duration)
    tier_response_hours: Optional[int] = None
    tier_resolution_hours: Optional[int] = None
    # Idempotent-update indicators: true when the caller tried to resolve an
    # already-resolved tracking. The body is still returned so the caller can
    # branch its own routing without parsing a 4xx error envelope.
    already_resolved: Optional[bool] = False
    updated_in_request: Optional[bool] = True
    # Idempotent-create indicator: true when create found an open conversation
    # tracking for the contact and returned it (message_id refreshed) instead of
    # creating a new row. n8n branches on this to skip new-conversation steps.
    already_active: Optional[bool] = False

    @model_serializer(mode='wrap', when_used='json')
    def serialize_model(self, serializer, info):
        """Custom serialization to convert timezone-aware datetimes to naive UTC strings."""
        data = serializer(self)
        # Convert timezone-aware datetimes to naive UTC
        datetime_fields = [
            'initiated_at', 'current_tier_started_at', 'due_at', 'due_at_resolution', 'escalated_at',
            'responded_at', 'resolved_at', 'created_at', 'updated_at', 'last_synced_to_excel',
            'resolution_due_at'
        ]
        for field in datetime_fields:
            if field in data and data[field] is not None:
                value = getattr(self, field)
                if isinstance(value, datetime) and value.tzinfo is not None:
                    # Convert to UTC and remove timezone for naive representation
                    data[field] = value.astimezone(timezone.utc).replace(tzinfo=None).isoformat()
        return data
    
    @field_validator('policy_id', mode='before')
    @classmethod
    def convert_policy_id_uuid(cls, v):
        """Convert UUID objects to strings for policy_id."""
        if v is None:
            return None
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v else None
    
    @field_validator('assigned_to', 'resolved_by', mode='before')
    @classmethod
    def convert_text_fields(cls, v):
        """Convert UUID objects to strings for text fields."""
        if v is None:
            return None
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v else None
    
    @model_validator(mode='after')
    def populate_computed_fields(self):
        """Populate computed fields from relationships."""
        if self.response_duration is None and self.response_time is not None:
            self.response_duration = self.response_time

        # Populate contact_phone and contact_name from contact relationship
        if self.contact:
            self.contact_phone = self.contact.phone_number
            self.contact_name = self.contact.name
        else:
            self.contact_phone = None
            self.contact_name = None

        # Populate assigned_user_name and assigned_user_email from assigned_user relationship
        if self.assigned_user:
            self.assigned_user_name = self.assigned_user.name
            self.assigned_user_email = self.assigned_user.email
        else:
            self.assigned_user_name = None
            self.assigned_user_email = None

        # Populate agent_code from agent FK relationship
        if self.agent and self.agent_code is None:
            self.agent_code = self.agent.code

        return self


_FORM_SLA_TYPES = ("stock_inquiry", "purchase_request", "sponsorship_form", "complaint", "ticket")


class FormSLAConfigBase(BaseModel):
    source_entity_type: str
    stage_code: str
    policy_id: str
    agent_code: str
    team_set_code: Optional[str] = None
    start_event: str
    respond_event: Optional[str] = None
    resolve_event: Optional[str] = None
    next_config_id: Optional[str] = None
    advance_on_event: Optional[str] = None
    is_active: bool = True
    notify_assignee: bool = True

    @field_validator("source_entity_type")
    @classmethod
    def _check_source_entity_type(cls, v: str) -> str:
        v = (v or "").strip()
        if v not in _FORM_SLA_TYPES:
            raise ValueError(
                f"source_entity_type must be one of {_FORM_SLA_TYPES}; got {v!r}"
            )
        return v

    @field_validator("stage_code", "agent_code", "start_event")
    @classmethod
    def _strip_required(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("must be a non-empty string")
        return v


class FormSLAConfigCreate(FormSLAConfigBase):
    pass


class FormSLAConfigUpdate(BaseModel):
    source_entity_type: Optional[str] = None
    stage_code: Optional[str] = None
    policy_id: Optional[str] = None
    agent_code: Optional[str] = None
    team_set_code: Optional[str] = None
    start_event: Optional[str] = None
    respond_event: Optional[str] = None
    resolve_event: Optional[str] = None
    next_config_id: Optional[str] = None
    advance_on_event: Optional[str] = None
    is_active: Optional[bool] = None
    notify_assignee: Optional[bool] = None


class FormSLAConfigResponse(FormSLAConfigBase):
    id: str
    created_at: datetime
    updated_at: datetime
    policy_code: Optional[str] = None
    policy_name: Optional[str] = None
    next_stage_code: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
