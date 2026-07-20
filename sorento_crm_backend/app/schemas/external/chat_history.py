"""External chat history schemas."""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ChatHistoryMessageIngestRequest(BaseModel):
    channel: str = "whatsapp"
    contact_id: str
    phone_number: str
    message: str
    sent_at: int = Field(..., description="Epoch milliseconds")
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    type: str
    message_id: Optional[str] = Field(
        None, max_length=64, description="Respond.io message id of this message"
    )
    result: Optional[list[dict[str, Any]]] = Field(
        None,
        description="Numbered-options result set sent in this message "
        "(idx/uuid/label/...), referencable later via conversation-variables.",
    )
    reply_to_message_id: Optional[str] = Field(
        None,
        max_length=64,
        description="Incoming quote-reply only: respond.io message id of the "
        "replied-to message. Matches the `message_id` of the earlier outgoing "
        "row. Null for normal (non-reply) messages.",
    )
    reply_to_message: Optional[str] = Field(
        None, description="Incoming quote-reply only: text of the replied-to message."
    )
    turn_id: Optional[str] = Field(
        None,
        max_length=64,
        description="n8n $execution.id, stamped on BOTH the incoming and the outgoing "
        "save of one turn. Pairs a reply to the message that triggered it exactly, so "
        "round-trip latency survives message bursts and reordering. Omit on proactive "
        "sends (campaigns, SLA notices) — those are excluded from the latency SLA "
        "rather than paired by proximity.",
    )


class ChatHistoryMessageIngestResponse(BaseModel):
    id: int
    status: str = "created"


class ChatHistoryMessagesRequest(BaseModel):
    channel: str = "whatsapp"
    contact_id: str
    limit: int = 50
    order: Literal["asc", "desc"] = "asc"


class ChatHistoryMessageItem(BaseModel):
    id: int
    channel: str
    contact_id: str
    phone_number: str
    message: str
    sent_at: datetime
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    type: str
    message_id: Optional[str] = None
    result: Optional[list[dict[str, Any]]] = None
    reply_to_message_id: Optional[str] = None
    reply_to_message: Optional[str] = None


class ChatHistoryMessagesResponse(BaseModel):
    messages: list[ChatHistoryMessageItem]

