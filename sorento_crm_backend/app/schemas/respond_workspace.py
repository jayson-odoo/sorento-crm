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
    ideation_shared_service_url: Optional[str] = Field(
        None,
        max_length=512,
        description="Ideation shared-service base URL (create_idea intake endpoint host).",
    )
    ideation_product_id: Optional[str] = Field(
        None,
        max_length=64,
        description="Shared-service Product id this workspace's ideas map to (admin config).",
    )
    ideation_embed_connection_id: Optional[str] = Field(
        None,
        max_length=128,
        description="Ideas iframe embed connection id (matches the shared-service registry).",
    )
    ideation_embed_fe_base_url: Optional[str] = Field(
        None,
        max_length=512,
        description="Ideas iframe FE root URL (shared-service frontend; the iframe points here, NOT the backend base).",
    )


class RespondWorkspaceCreate(RespondWorkspaceBase):
    api_key: str = Field(..., min_length=1, description="Plain API key pasted from Respond.io")
    ideation_intake_api_key: Optional[str] = Field(
        None, description="Plain ideation intake API key (Bearer token for create_idea)."
    )
    ideation_embed_signing_secret: Optional[str] = Field(
        None, description="Plain ideation embed signing secret (mints the SSO assertion)."
    )


class RespondWorkspaceUpdate(BaseModel):
    space_id: Optional[str] = Field(None, max_length=64)
    name: Optional[str] = Field(None, max_length=255)
    base_url: Optional[str] = Field(None, max_length=512)
    whatsapp_number: Optional[str] = Field(None, max_length=32)
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    api_key: Optional[str] = Field(None, description="When set, replaces stored key")
    ideation_shared_service_url: Optional[str] = Field(None, max_length=512)
    ideation_product_id: Optional[str] = Field(None, max_length=64)
    ideation_intake_api_key: Optional[str] = Field(
        None, description="When set, replaces stored ideation intake key"
    )
    ideation_embed_connection_id: Optional[str] = Field(None, max_length=128)
    ideation_embed_fe_base_url: Optional[str] = Field(None, max_length=512)
    ideation_embed_signing_secret: Optional[str] = Field(
        None, description="When set, replaces stored ideation embed signing secret"
    )


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
    ideation_shared_service_url: Optional[str] = None
    ideation_product_id: Optional[str] = None
    ideation_intake_api_key_masked: Optional[str] = None
    ideation_embed_connection_id: Optional[str] = None
    ideation_embed_fe_base_url: Optional[str] = None
    ideation_embed_signing_secret_masked: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class RespondWorkspaceSelectItem(BaseModel):
    """Minimal row for dropdowns (lead form)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    space_id: str
    name: Optional[str] = None
    is_default: bool = False
