"""Schemas for the AI assistant prompt registry API.

Field names match ``docs/plans/PLAN-ai-assistant-prompt-registry.md`` §8b and the
UAC contract verbatim — the FE prototype is built against these exact shapes.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PromptKeySummary(BaseModel):
    """One row of ``GET /ai-assistant/prompts``."""

    name: str
    role: str
    active: bool
    activates_in: Optional[str] = None
    variables: list[str] = Field(default_factory=list)
    production_version: Optional[int] = None
    staging_version: Optional[int] = None
    # The LLM this agent runs on in production. None = the global assistant model.
    provider: Optional[str] = None
    model: Optional[str] = None
    latest_version: Optional[int] = None
    updated_at: Optional[datetime] = None
    updated_by_name: Optional[str] = None


class PromptVersionRow(BaseModel):
    """One entry in a key's version history."""

    id: str
    version: int
    commit_message: Optional[str] = None
    created_by_name: Optional[str] = None
    created_at: datetime
    labels: list[str] = Field(default_factory=list)


class PromptVersionsResponse(BaseModel):
    """``GET /ai-assistant/prompts/{name}/versions``."""

    name: str
    role: str
    active: bool
    activates_in: Optional[str] = None
    variables: list[str] = Field(default_factory=list)
    labels: dict[str, Optional[int]] = Field(default_factory=dict)
    versions: list[PromptVersionRow] = Field(default_factory=list)


class PromptVersionDetail(BaseModel):
    """``GET /ai-assistant/prompts/{name}/versions/{v}`` and the 201 save body."""

    id: str
    name: str
    version: int
    template: str
    variables: list[str] = Field(default_factory=list)
    commit_message: Optional[str] = None
    created_by_name: Optional[str] = None
    created_at: datetime
    labels: list[str] = Field(default_factory=list)
    # Echoed on save so the FE can surface the soft-warn (declared var removed).
    missing_vars: list[str] = Field(default_factory=list)


class SaveVersionRequest(BaseModel):
    template: str
    commit_message: str


class SetLabelRequest(BaseModel):
    label: str = Field(..., description="production | staging")
    version_id: str


class SetLabelResponse(BaseModel):
    labels: dict[str, Optional[int]] = Field(default_factory=dict)


class SetAgentModelRequest(BaseModel):
    """Point one agent at one LLM. Empty strings clear the override."""

    label: str = Field(default="production", description="production | staging")
    provider: Optional[str] = Field(default=None, max_length=64)
    model: Optional[str] = Field(default=None, max_length=128)


class SetAgentModelResponse(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None


class DryRunRequest(BaseModel):
    message: str = Field(..., min_length=1)
    version_id: str


class DryRunToolCall(BaseModel):
    name: str
    ok: bool


class DryRunResponse(BaseModel):
    output: str
    token_usage: dict[str, int] = Field(default_factory=dict)
    tool_calls: list[DryRunToolCall] = Field(default_factory=list)
    used_overrides: dict[str, str] = Field(default_factory=dict)
