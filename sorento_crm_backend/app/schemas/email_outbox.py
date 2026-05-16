"""Schemas for email outbox + event configs admin API."""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class EmailOutboxRowResponse(BaseModel):
    id: str
    event_key: str
    recipient_email: str
    recipients_json: Optional[dict] = None
    subject: str
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    from_name: Optional[str] = None
    metadata: Optional[Any] = None
    priority: int
    status: str
    scheduled_for: datetime
    sent_at: Optional[datetime] = None
    attempt_count: int
    max_attempts: int
    error_message: Optional[str] = None
    cancel_reason: Optional[str] = None
    coalesce_key: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class EmailEventConfigResponse(BaseModel):
    event_key: str
    display_name: str
    description: Optional[str] = None
    enabled: bool
    rate_per_window_override: Optional[int] = None
    window_seconds_override: Optional[int] = None
    priority_override: Optional[int] = None
    coalesce_window_seconds_override: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class EmailEventConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    rate_per_window_override: Optional[int] = None
    window_seconds_override: Optional[int] = None
    priority_override: Optional[int] = None
    coalesce_window_seconds_override: Optional[int] = None
