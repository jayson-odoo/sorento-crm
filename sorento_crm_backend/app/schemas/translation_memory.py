"""Schemas for the translation memory admin list (AC-G4, purchasing consolidation batch,
lane C)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TranslationMemoryResponse(BaseModel):
    id: str
    source_text: str
    source_lang: str
    target_lang: str
    target_text: str
    source: str
    # A name, never a UUID (no-UUIDs-in-the-UI rule) - resolved by the service, null when
    # the row was written by the AI fill or the writing user has since been removed.
    created_by_name: Optional[str] = None
    updated_at: datetime
    hit_count: int

    class Config:
        from_attributes = True


class TranslationMemoryUpdate(BaseModel):
    target_text: str = Field(..., min_length=1)
