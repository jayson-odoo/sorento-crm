"""Audit log schemas."""
from uuid import UUID
from pydantic import BaseModel, field_validator
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

    _normalize_id = field_validator("id", mode="before")(_str_or_uuid)
    _normalize_entity_id = field_validator("entity_id", mode="before")(_str_or_uuid)
    _normalize_user_id = field_validator("user_id", mode="before")(_str_or_uuid)

    class Config:
        from_attributes = True
