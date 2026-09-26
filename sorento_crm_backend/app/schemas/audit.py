"""Audit log schemas."""
from uuid import UUID
from pydantic import AliasChoices, BaseModel, Field, field_validator
from typing import Optional, Any
from datetime import datetime


def _str_or_uuid(v: Any) -> Optional[str]:
    """Coerce UUID or str to str for response serialization."""
    if v is None:
        return None
    if isinstance(v, UUID):
        return str(v)
    return str(v) if v else None


class AuditLogResponse(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    action: str
    user_id: Optional[str] = None
    contact_id: Optional[str] = None  # acting contact (respond_contacts.id) for portal/public writes
    user_display_name: Optional[str] = None  # Resolved: contact name -> staff name -> "System"
    changed_at: datetime
    old_values: Optional[dict[str, Any]] = None
    new_values: Optional[dict[str, Any]] = None
    description: Optional[str] = None
    ip_address: Optional[str] = None
    # Audit standard S0 (#1281). request_id IS the trace_id column (one per request or job).
    request_id: Optional[str] = Field(default=None, validation_alias=AliasChoices("request_id", "trace_id"))
    correlation_id: Optional[str] = None
    event: Optional[str] = None
    source: Optional[str] = None
    reason: Optional[str] = None
    principal_type: Optional[str] = None
    principal_id: Optional[str] = None
    on_behalf_of_user_id: Optional[str] = None
    root_entity_type: Optional[str] = None
    root_entity_id: Optional[str] = None

    _normalize_id = field_validator("id", mode="before")(_str_or_uuid)
    _normalize_entity_id = field_validator("entity_id", mode="before")(_str_or_uuid)
    _normalize_user_id = field_validator("user_id", mode="before")(_str_or_uuid)
    _normalize_on_behalf = field_validator("on_behalf_of_user_id", mode="before")(_str_or_uuid)

    class Config:
        from_attributes = True
