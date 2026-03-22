"""Notification API schemas."""
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field, field_validator


def _str_uuid(v: Any) -> Optional[str]:
    if v is None:
        return None
    return str(v)


class NotificationResponse(BaseModel):
    id: str
    user_id: str
    type: str
    title: str
    body: Optional[str] = None
    data: Optional[dict[str, Any]] = None
    read_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime
    source_entity_type: Optional[str] = None
    source_entity_id: Optional[str] = None
    event_type: Optional[str] = None

    _normalize_id = field_validator("id", mode="before")(_str_uuid)
    _normalize_user_id = field_validator("user_id", mode="before")(_str_uuid)

    class Config:
        from_attributes = True


class UnreadCountResponse(BaseModel):
    count: int


class PushSubscribeRequest(BaseModel):
    """Web push subscription from the browser Push API."""
    endpoint: str
    p256dh: str
    auth: str


class BulkDeleteNotificationsRequest(BaseModel):
    """Permanently delete multiple notifications owned by the current user."""
    ids: list[str] = Field(..., min_length=1, max_length=100)
