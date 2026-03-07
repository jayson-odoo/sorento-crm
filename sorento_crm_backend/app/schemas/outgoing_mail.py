"""Schemas for outgoing email log (notification deliveries)."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class OutgoingMailResponse(BaseModel):
    id: str
    notification_id: str
    user_id: str
    to_email: str
    subject: str
    body: Optional[str] = None
    status: str  # pending | sent | failed
    created_at: datetime
    sent_at: Optional[datetime] = None
    error_message: Optional[str] = None

    # Optional linkage for deep links / troubleshooting
    notification_type: Optional[str] = None
    source_entity_type: Optional[str] = None
    source_entity_id: Optional[str] = None
    event_type: Optional[str] = None

