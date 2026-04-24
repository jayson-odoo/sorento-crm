"""Schemas for AI assistant settings and chat APIs."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class AIAssistantConfigUpdate(BaseModel):
    provider: str = Field(..., max_length=64)
    model: str = Field(..., max_length=128)
    temperature: int = Field(0, ge=0, le=2)
    system_prompt: str = ""
    api_key: Optional[str] = Field(None, description="Optional replacement API key")
    enabled_tools: list[str] = Field(default_factory=list)
    rag_enabled: bool = True
    is_enabled: bool = True


class AIAssistantConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    model: str
    temperature: int
    system_prompt: str
    api_key_masked: Optional[str] = None
    enabled_tools: list[str]
    rag_enabled: bool
    is_enabled: bool
    created_at: datetime
    updated_at: datetime


class AIAssistantMessageCreate(BaseModel):
    conversation_id: Optional[str] = None
    message: str = Field(..., min_length=1)


class AIAssistantMessageResponse(BaseModel):
    id: str
    role: Literal["user", "assistant", "tool"]
    content: str
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AIAssistantConversationResponse(BaseModel):
    id: str
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    messages: list[AIAssistantMessageResponse] = Field(default_factory=list)


class AIAssistantAuthContext(BaseModel):
    user_id: str
    role_ids: list[str]
    permission_slugs: list[str]
    enabled_modules: list[str]
