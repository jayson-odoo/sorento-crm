"""SLA management schemas."""
from pydantic import BaseModel, field_validator, model_validator
from typing import Optional
from datetime import datetime
from decimal import Decimal
import uuid


class SLAPolicyTierBase(BaseModel):
    policy_id: str
    tier_level: int
    tier_name: str
    response_hours: int


class SLAPolicyTierCreate(SLAPolicyTierBase):
    pass


class SLAPolicyTierUpdate(BaseModel):
    tier_name: Optional[str] = None
    response_hours: Optional[int] = None


class SLAPolicyTierResponse(SLAPolicyTierBase):
    id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


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
    
    class Config:
        from_attributes = True


class ConversationSLATrackingBase(BaseModel):
    policy_id: str
    current_tier: int
    assigned_to: Optional[str] = None  # Keep for backward compatibility
    assigned_to_id: Optional[str] = None  # FK to users
    initiated_at: datetime
    current_tier_started_at: datetime
    due_at: datetime
    escalated_at: Optional[datetime] = None
    escalation_reason: Optional[str] = None
    is_responded: bool = False
    responded_at: Optional[datetime] = None
    response_time: Optional[Decimal] = None
    is_resolved: bool = False
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    respond_contact_id: Optional[str] = None  # FK to respond_contacts
    resolution_duration: Optional[Decimal] = None


class ConversationSLATrackingCreate(ConversationSLATrackingBase):
    contact_phone_number: Optional[str] = None


class ConversationSLATrackingUpdate(BaseModel):
    current_tier: Optional[int] = None
    assigned_to: Optional[str] = None
    escalated_at: Optional[datetime] = None
    escalation_reason: Optional[str] = None
    is_responded: Optional[bool] = None
    responded_at: Optional[datetime] = None
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


class ConversationSLATrackingStatusUpdate(BaseModel):
    is_responded: Optional[bool] = None
    responded_at: Optional[datetime] = None
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


class SLAPolicySimple(BaseModel):
    """Simple policy reference for tracking responses."""
    id: str
    code: str
    name: str
    
    class Config:
        from_attributes = True


class ContactSimple(BaseModel):
    """Simple contact reference for tracking responses."""
    id: str
    phone_number: str
    name: Optional[str] = None
    
    class Config:
        from_attributes = True


class UserSimple(BaseModel):
    """Simple user reference for tracking responses."""
    id: str
    email: str
    name: Optional[str] = None
    
    class Config:
        from_attributes = True


class ConversationSLAEventLogResponse(BaseModel):
    """SLA event log response schema."""
    id: str
    sla_tracking_id: str
    event_type: str
    from_tier: Optional[int] = None
    to_tier: Optional[int] = None
    event_at: datetime
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
    
    class Config:
        from_attributes = True


class ConversationSLAEventLogCreate(BaseModel):
    sla_tracking_id: str
    event_type: str
    from_tier: Optional[int] = None
    to_tier: Optional[int] = None
    event_at: Optional[datetime] = None
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
    assigned_to_id: Optional[str] = None
    # Related objects
    contact: Optional[ContactSimple] = None
    assigned_user: Optional[UserSimple] = None
    # Renamed field for API consumers
    response_duration: Optional[Decimal] = None
    # Computed fields for backward compatibility
    contact_phone: Optional[str] = None  # From contact.phone_number or respond_contact_phone
    contact_name: Optional[str] = None  # From contact.name or respond_contact_name
    assigned_user_name: Optional[str] = None  # From assigned_user.name
    assigned_user_email: Optional[str] = None  # From assigned_user.email
    
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
            # If no contact relationship, set to None/empty
            self.contact_phone = None
            self.contact_name = None
        
        # Populate assigned_user_name and assigned_user_email from assigned_user relationship
        if self.assigned_user:
            self.assigned_user_name = self.assigned_user.name
            self.assigned_user_email = self.assigned_user.email
        else:
            # If no assigned_user relationship, set to None
            self.assigned_user_name = None
            self.assigned_user_email = None
        
        return self
    
    class Config:
        from_attributes = True
