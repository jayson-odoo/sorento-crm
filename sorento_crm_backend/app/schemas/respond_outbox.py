"""Schemas for the Respond.io outbox (read-only view over integration_log)."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class RespondOutboxRowResponse(BaseModel):
    id: str
    created_at: datetime
    business_table: Optional[str] = None
    business_id: Optional[str] = None
    contact_identifier: Optional[str] = None  # respond_io_id (external_reference)
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    sent_as: str  # 'text' | 'template'
    message_text: Optional[str] = None
    template_name: Optional[str] = None
    status: str  # success | failed | pending | processing
    status_code: Optional[int] = None
    error_message: Optional[str] = None
    response_payload: Optional[str] = None
    created_by: Optional[str] = None
