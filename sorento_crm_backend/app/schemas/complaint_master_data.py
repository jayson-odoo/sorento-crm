"""Schemas for complaint root cause and resolution master data."""
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime


class ComplaintRootCauseBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v


class ComplaintRootCauseCreate(ComplaintRootCauseBase):
    pass


class ComplaintRootCauseUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v


class ComplaintRootCauseResponse(ComplaintRootCauseBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    complaint_count: Optional[int] = None

    class Config:
        from_attributes = True


class ComplaintRootCauseSimple(BaseModel):
    id: str
    name: str

    class Config:
        from_attributes = True


class ComplaintResolutionBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v


class ComplaintResolutionCreate(ComplaintResolutionBase):
    pass


class ComplaintResolutionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v


class ComplaintResolutionResponse(ComplaintResolutionBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    complaint_count: Optional[int] = None

    class Config:
        from_attributes = True


class ComplaintResolutionSimple(BaseModel):
    id: str
    name: str

    class Config:
        from_attributes = True
