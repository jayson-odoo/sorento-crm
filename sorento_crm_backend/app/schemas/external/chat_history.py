"""External chat history schemas."""

from datetime import datetime
from typing import Literal, Optional

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


class ChatHistoryMessagesResponse(BaseModel):
    messages: list[ChatHistoryMessageItem]

