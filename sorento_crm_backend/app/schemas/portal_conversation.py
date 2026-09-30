"""The portal Conversation view's list row (lane SALES-CONVO)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class PortalConversationRow(BaseModel):
    #: `respond_contacts.id`: the key the thread routes take. The only id on the wire.
    contact_id: str
    customer_name: Optional[str] = None
    customer_code: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    last_message_at: Optional[str] = None
    last_message_snippet: Optional[str] = None
    #: `incoming` (the customer wrote last) or `outgoing`.
    last_message_direction: Optional[str] = None
