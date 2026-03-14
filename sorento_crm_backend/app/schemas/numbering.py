"""Pydantic schemas for document numbering rules."""
from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime


class DocumentNumberingRuleResponse(BaseModel):
    id: str
    doc_type: str
    enabled: bool
    prefix_template: Optional[str] = None
    number_digits: int
    next_value: int
    start_value: int
    reset_policy: str
    last_reset_key: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentNumberingRuleUpdate(BaseModel):
    enabled: Optional[bool] = None
    prefix_template: Optional[str] = None
    number_digits: Optional[int] = None
    next_value: Optional[int] = None
    start_value: Optional[int] = None
    reset_policy: Optional[str] = None
