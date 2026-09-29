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
    entity_label: Optional[str] = None  # the record in words (activity feed resolver), never an id
    action: str
    user_id: Optional[str] = None
    contact_id: Optional[str] = None  # acting contact (respond_contacts.id) for portal/public writes
    user_display_name: Optional[str] = None  # Resolved: contact name -> staff name -> "System"
    changed_at: datetime
    old_values: Optional[dict[str, Any]] = None
    new_values: Optional[dict[str, Any]] = None
    description: Optional[str] = None
    ip_address: Optional[str] = None
    # Audit actor (identity S0, AC-13). `actor_label` is the actor in words, never an id.
    actor_type: Optional[str] = None
    auth_method: Optional[str] = None
    real_user_id: Optional[str] = None
    integration_id: Optional[str] = None
    job_id: Optional[str] = None
    actor_label: Optional[str] = None
    # Audit standard S0 (#1281): the business action. request_id IS the trace_id column.
    request_id: Optional[str] = Field(default=None, validation_alias=AliasChoices("request_id", "trace_id"))
    correlation_id: Optional[str] = None
    event: Optional[str] = None
    source: Optional[str] = None
    reason: Optional[str] = None
    root_entity_type: Optional[str] = None
    root_entity_id: Optional[str] = None

    _normalize_id = field_validator("id", mode="before")(_str_or_uuid)
    _normalize_entity_id = field_validator("entity_id", mode="before")(_str_or_uuid)
    _normalize_user_id = field_validator("user_id", mode="before")(_str_or_uuid)
    _normalize_real_user_id = field_validator("real_user_id", mode="before")(_str_or_uuid)
    _normalize_integration_id = field_validator("integration_id", mode="before")(_str_or_uuid)

    class Config:
        from_attributes = True
