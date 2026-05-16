"""External schemas for n8n conversation-frame memory routes."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# --- open ---

class FrameOpenRequest(BaseModel):
    contact_id: str
    space_id: str
    channel: str = "whatsapp"
    domain: Optional[str] = None
    intent: Optional[str] = None
    active_entities: dict[str, Any] = Field(default_factory=dict)
    access_levels_used: list[str] = Field(default_factory=list)
    last_user_message: Optional[str] = None


class FrameOpenResponse(BaseModel):
    frame_id: str
    status: str = "open"


# --- update ---

class FramePatch(BaseModel):
    domain: Optional[str] = None
    intent: Optional[str] = None
    active_entities: Optional[dict[str, Any]] = None
    access_levels_used: Optional[list[str]] = None
    tools_used: Optional[list[str]] = None
    result_refs: Optional[list[Any]] = None
    pending_request: Optional[dict[str, Any]] = None
    last_user_message: Optional[str] = None
    last_assistant_summary: Optional[str] = None


class FrameUpdateRequest(BaseModel):
    frame_id: str
    patch: FramePatch


class FrameUpdateResponse(BaseModel):
    ok: bool = True
    frame_id: str


# --- close ---

class FrameCloseRequest(BaseModel):
    frame_id: str
    reason: Literal["topic_switch", "role_switch", "idle", "session_end", "manual"]
    summary: Optional[str] = None


class FrameCloseResponse(BaseModel):
    ok: bool = True
    frame_id: str
    embedding_queued: bool


# --- search ---

class FrameSearchRequest(BaseModel):
    contact_id: str
    space_id: str
    query_text: str
    k: int = 3


class FrameSearchHit(BaseModel):
    frame_id: str
    domain: Optional[str] = None
    intent: Optional[str] = None
    active_entities: dict[str, Any] = Field(default_factory=dict)
    access_levels_used: list[str] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    summary: Optional[str] = None
    closed_at: Optional[str] = None
    similarity_score: float


class FrameSearchResponse(BaseModel):
    frames: list[FrameSearchHit]


# --- current ---

class FrameCurrentFrame(BaseModel):
    id: str
    contact_id: str
    space_id: str
    channel: str
    domain: Optional[str] = None
    intent: Optional[str] = None
    active_entities: dict[str, Any] = Field(default_factory=dict)
    access_levels_used: list[str] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    result_refs: list[Any] = Field(default_factory=list)
    pending_request: dict[str, Any] = Field(default_factory=dict)
    last_user_message: Optional[str] = None
    last_assistant_summary: Optional[str] = None
    status: str
    started_at: datetime
    last_activity_at: datetime


class FrameCurrentResponse(BaseModel):
    frame: Optional[FrameCurrentFrame] = None
