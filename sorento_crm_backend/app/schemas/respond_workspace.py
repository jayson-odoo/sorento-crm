"""Respond.io workspace admin schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class RespondWorkspaceBase(BaseModel):
    space_id: str = Field(..., max_length=64)
    name: Optional[str] = Field(None, max_length=255)
    base_url: Optional[str] = Field(None, max_length=512)
    whatsapp_number: Optional[str] = Field(
        None,
        max_length=32,
        description="Business WhatsApp number (digits, E.164 without '+') for the portal wa.me escape hatch.",
    )
    is_active: bool = True
    is_default: bool = False


class RespondWorkspaceCreate(RespondWorkspaceBase):
    api_key: str = Field(..., min_length=1, description="Plain API key pasted from Respond.io")


class RespondWorkspaceUpdate(BaseModel):
    space_id: Optional[str] = Field(None, max_length=64)
    name: Optional[str] = Field(None, max_length=255)
    base_url: Optional[str] = Field(None, max_length=512)
    whatsapp_number: Optional[str] = Field(None, max_length=32)
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    api_key: Optional[str] = Field(None, description="When set, replaces stored key")


class RespondWorkspaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    space_id: str
    name: Optional[str] = None
    base_url: Optional[str] = None
    whatsapp_number: Optional[str] = None
    is_active: bool
    is_default: bool = False
    api_key_masked: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class RespondWorkspaceSelectItem(BaseModel):
    """Minimal row for dropdowns (lead form)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    space_id: str
    name: Optional[str] = None
    is_default: bool = False
