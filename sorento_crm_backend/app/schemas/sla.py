"""SLA management schemas."""
from pydantic import BaseModel, field_validator
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
    assigned_to: Optional[str] = None
    initiated_at: datetime
    current_tier_started_at: datetime
    due_at: datetime
    escalated_at: Optional[datetime] = None
    escalation_reason: Optional[str] = None
    is_resolved: bool = False
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    respond_contact_id: str
    resolution_duration: Optional[Decimal] = None


class ConversationSLATrackingCreate(ConversationSLATrackingBase):
    pass


class ConversationSLATrackingUpdate(BaseModel):
    current_tier: Optional[int] = None
    assigned_to: Optional[str] = None
    escalated_at: Optional[datetime] = None
    escalation_reason: Optional[str] = None
    is_resolved: Optional[bool] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolution_duration: Optional[Decimal] = None


class SLAPolicySimple(BaseModel):
    """Simple policy reference for tracking responses."""
    id: str
    code: str
    name: str
    
    class Config:
        from_attributes = True


class ConversationSLATrackingResponse(ConversationSLATrackingBase):
    id: str
    created_at: datetime
    updated_at: datetime
    synced_to_excel: bool = False
    last_synced_to_excel: Optional[datetime] = None
    policy: Optional[SLAPolicySimple] = None
    
    @field_validator('policy_id', mode='before')
    @classmethod
    def convert_policy_id_uuid(cls, v):
        """Convert UUID objects to strings for policy_id."""
        if v is None:
            return None
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v else None
    
    @field_validator('assigned_to', 'resolved_by', 'respond_contact_id', mode='before')
    @classmethod
    def convert_text_fields(cls, v):
        """Convert UUID objects to strings for text fields."""
        if v is None:
            return None
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v else None
    
    class Config:
        from_attributes = True
