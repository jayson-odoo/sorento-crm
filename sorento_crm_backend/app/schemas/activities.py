"""Activities & Notes schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ActivityActor(BaseModel):
    id: Optional[str] = None
    display_name: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None


class ActivityEventResponse(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    kind: str
    body_html: Optional[str] = None
    body_text: Optional[str] = None
    system_template: Optional[str] = None
    system_payload: Optional[dict[str, Any]] = None
    actor: Optional[ActivityActor] = None
    attachment_ids: list[str] = Field(default_factory=list)
    mentioned_user_ids: list[str] = Field(default_factory=list)
    created_at: datetime

    class Config:
        from_attributes = True


class ActivityEventCreate(BaseModel):
    body_html: str
    attachment_ids: list[str] = Field(default_factory=list)
    mentioned_user_ids: list[str] = Field(default_factory=list)


class InternalNoteResponse(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    author_id: str
    body_html: Optional[str] = None
    body_text: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class InternalNoteCreate(BaseModel):
    body_html: str


class InternalNoteUpdate(BaseModel):
    body_html: str


class EntityRespondContact(BaseModel):
    id: str
    name: Optional[str] = None
    phone_number: Optional[str] = None
    respond_io_id: Optional[str] = None
    is_primary: bool = False


class EntityMessageSendRequest(BaseModel):
    contact_id: str
    body: str
    attachment_ids: list[str] = Field(default_factory=list)
