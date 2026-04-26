"""API models for entity activity / internal note threads."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ConversationMessageAuthorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: Optional[str] = None
    email: Optional[str] = None


class ConversationMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    scope: Literal["activity", "internal_note"]
    is_system: bool
    body_html: str
    author: Optional[ConversationMessageAuthorOut] = None
    created_at: datetime


class ConversationMessageCreate(BaseModel):
    scope: Literal["activity", "internal_note"]
    body_html: str = Field(..., min_length=1, max_length=2_000_000)
