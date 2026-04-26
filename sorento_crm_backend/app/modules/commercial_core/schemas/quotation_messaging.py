"""Schemas: quotation PDF print and customer email preview/send."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class QuotationEmailPreviewRequest(BaseModel):
    template_id: Optional[str] = None


class QuotationEmailPreviewResponse(BaseModel):
    default_to: str = ""
    subject: str = ""
    body_html: str = ""
    pdf_attachment_filename: str = ""
    token_keys: List[str] = Field(default_factory=list)


class QuotationEmailSendRequest(BaseModel):
    to: List[str] = Field(default_factory=list)
    cc: List[str] = Field(default_factory=list)
    bcc: List[str] = Field(default_factory=list)
    subject: str = ""
    body_html: str = ""


class QuotationEmailSendResponse(BaseModel):
    ok: bool = True
    error: Optional[str] = None
