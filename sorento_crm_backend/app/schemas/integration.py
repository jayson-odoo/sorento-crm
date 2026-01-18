"""Integration logging schemas."""
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime
import uuid
import json


class IntegrationLogBase(BaseModel):
    integration_channel: str
    business_table: str
    business_id: str
    external_reference: Optional[str] = None
    direction: str  # "inbound" or "outbound"
    endpoint: str
    http_method: str
    request_headers: Optional[str] = None
    request_payload: Optional[str] = None


class IntegrationLogCreate(IntegrationLogBase):
    status: str = "pending"
    retry_count: int = 0
    max_retry_allowed: int = 3
    correlation_id: Optional[str] = None
    created_by: Optional[str] = None


class IntegrationLogUpdate(BaseModel):
    status: Optional[str] = None
    status_code: Optional[int] = None
    response_headers: Optional[str] = None
    response_payload: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: Optional[int] = None
    next_retry_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None


class IntegrationLogResponse(IntegrationLogBase):
    id: str
    status_code: Optional[int] = None
    status: str
    response_headers: Optional[str] = None
    response_payload: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    correlation_id: Optional[str] = None
    retry_count: int
    max_retry_allowed: int
    next_retry_at: Optional[datetime] = None
    created_at: datetime
    created_by: Optional[str] = None
    processed_at: Optional[datetime] = None
    updated_at: datetime
    
    @field_validator('id', 'business_id', 'correlation_id', 'created_by', mode='before')
    @classmethod
    def convert_uuid_to_string(cls, v):
        """Convert UUID objects to strings."""
        if v is None:
            return None
        if isinstance(v, uuid.UUID):
            return str(v)
        if isinstance(v, bytes):
            return v.decode('utf-8') if v else None
        return str(v) if v else None
    
    class Config:
        from_attributes = True


class IntegrationLogWebhookPayload(BaseModel):
    """Payload sent to n8n webhook."""
    integration_log_id: str
    s3_url: str


class IntegrationLogUpdateRequest(BaseModel):
    """Request from n8n to update integration log status."""
    status: str  # "success", "failed", "processing"
    status_code: Optional[int] = None
    response_payload: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
