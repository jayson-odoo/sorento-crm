"""Schemas: quotation email templates (admin)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class QuotationEmailTemplateOut(BaseModel):
    id: str
    code: str
    name: str
    subject_template: str
    body_html_template: str
    is_active: bool
    is_default: bool
    sort_order: int


class QuotationEmailTemplateCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    subject_template: str = ""
    body_html_template: str = ""
    is_active: bool = True
    is_default: bool = False
    sort_order: int = 0


class QuotationEmailTemplatePatch(BaseModel):
    code: Optional[str] = Field(None, min_length=1, max_length=64)
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    subject_template: Optional[str] = None
    body_html_template: Optional[str] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    sort_order: Optional[int] = None
