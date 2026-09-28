"""Schemas for email templates."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator

from app.services.email_layout import EmailDocument, EmailTheme, ResolvedTheme


class EmailTemplateBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    subject: str = Field(..., min_length=1, max_length=512)
    body_html: str = Field(..., min_length=1)
    body_text: Optional[str] = None
    is_active: bool = True


class EmailTemplateCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    subject: str = Field(..., min_length=1, max_length=512)
    # Optional once a block document is sent: the service mirrors the custom text
    # blocks into body_html (#1349 D3). A legacy (no layout_json) template still needs it.
    body_html: Optional[str] = None
    body_text: Optional[str] = None
    preheader: Optional[str] = Field(None, max_length=255)
    layout_json: Optional[EmailDocument] = None
    is_active: bool = True

    @model_validator(mode="after")
    def _body_or_blocks(self) -> "EmailTemplateCreate":
        if self.layout_json is None and not (self.body_html or "").strip():
            raise ValueError("body_html is required when layout_json is not provided")
        return self


class EmailTemplateUpdate(BaseModel):
    code: Optional[str] = Field(None, min_length=1, max_length=80)
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    subject: Optional[str] = Field(None, min_length=1, max_length=512)
    body_html: Optional[str] = Field(None, min_length=1)
    body_text: Optional[str] = None
    preheader: Optional[str] = Field(None, max_length=255)
    layout_json: Optional[EmailDocument] = None
    is_active: Optional[bool] = None


class EmailTemplateResponse(EmailTemplateBase):
    id: str
    body_html: str = ""
    preheader: Optional[str] = None
    layout_json: Optional[dict[str, Any]] = None
    # True when `code` is a built-in system mail (app/services/email_system_templates.py).
    is_system: bool = False
    created_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @model_validator(mode="after")
    def _flag_system(self) -> "EmailTemplateResponse":
        from app.services.email_system_templates import SYSTEM_TEMPLATES

        self.is_system = self.code in SYSTEM_TEMPLATES
        return self


class EmailTemplatePreviewRequest(BaseModel):
    context: Optional[dict[str, Any]] = None


class EmailTemplateDraftPreviewRequest(BaseModel):
    """An unsaved template, as the editor holds it (#1349 AC-EM031)."""

    subject: str = Field("", max_length=512)
    preheader: Optional[str] = Field(None, max_length=255)
    layout_json: Optional[EmailDocument] = None
    body_html: Optional[str] = None
    body_text: Optional[str] = None
    code: Optional[str] = Field(None, max_length=80)
    context: Optional[dict[str, Any]] = None


class EmailThemeFont(BaseModel):
    value: str
    label: str


class EmailThemeResponse(BaseModel):
    theme: EmailTheme
    defaults: ResolvedTheme
    fonts: list[EmailThemeFont]


class EmailThemePreviewRequest(BaseModel):
    theme: EmailTheme = Field(default_factory=EmailTheme)


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
