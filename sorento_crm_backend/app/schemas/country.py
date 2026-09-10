"""Countries master schemas (S1, `PLAN-local-supplier-oi-routing.md`)."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CountryBase(BaseModel):
    code: str = Field(..., min_length=2, max_length=2)
    name: str = Field(..., min_length=1, max_length=100)
    is_active: bool = True


class CountryCreate(CountryBase):
    pass


class CountryUpdate(BaseModel):
    code: Optional[str] = Field(None, min_length=2, max_length=2)
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    is_active: Optional[bool] = None


class CountryResponse(CountryBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CountrySelectItem(BaseModel):
    id: str
    code: str
    name: str

    class Config:
        from_attributes = True
