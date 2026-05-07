"""Schemas for email templates."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class EmailTemplateBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    subject: str = Field(..., min_length=1, max_length=512)
    body_html: str = Field(..., min_length=1)
    body_text: Optional[str] = None
    is_active: bool = True


class EmailTemplateCreate(EmailTemplateBase):
    pass


class EmailTemplateUpdate(BaseModel):
    code: Optional[str] = Field(None, min_length=1, max_length=80)
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    subject: Optional[str] = Field(None, min_length=1, max_length=512)
    body_html: Optional[str] = Field(None, min_length=1)
    body_text: Optional[str] = None
    is_active: Optional[bool] = None


class EmailTemplateResponse(EmailTemplateBase):
    id: str
    created_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EmailTemplatePreviewRequest(BaseModel):
    context: Optional[dict[str, Any]] = None


class EmailTemplatePreviewResponse(BaseModel):
    subject: str
    body_html: str
    body_text: str


class TemplateVariable(BaseModel):
    key: str
    label: str
    sample: Optional[str] = None


class TemplateVariablesCatalog(BaseModel):
    variables: list[TemplateVariable]
