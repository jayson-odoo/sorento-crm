"""Pydantic schemas for Respond.io WhatsApp template configuration."""
from __future__ import annotations

from typing import Dict

from pydantic import BaseModel, Field


class TemplateDefaultUpsertRequest(BaseModel):
    template_id: str = Field(..., min_length=1)
    # {"1": "contact_name", ...} - positional template param -> CRM variable.
    param_mapping: Dict[str, str] = Field(default_factory=dict)
