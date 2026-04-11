"""External chat history schemas."""

from typing import List

from pydantic import BaseModel


class ChatHistoryHumanMessagesRequest(BaseModel):
    contact_id: str
    limit: int = 10


class ChatHistoryHumanMessagesResponse(BaseModel):
    content: List[str]

