"""Item Class reference schemas (ITEM-CLASS, PLAN-item-class-29oct.md D4)."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ItemClassBase(BaseModel):
    item_class_code: str = Field(..., min_length=1, max_length=50)
    item_class_name: str = Field(..., min_length=1, max_length=150)
    description: Optional[str] = None
    is_active: bool = True


class ItemClassCreate(ItemClassBase):
    pass


class ItemClassUpdate(BaseModel):
    item_class_code: Optional[str] = Field(None, min_length=1, max_length=50)
    item_class_name: Optional[str] = Field(None, min_length=1, max_length=150)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class ItemClassResponse(ItemClassBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    product_count: Optional[int] = None

    class Config:
        from_attributes = True


class ItemClassSimple(BaseModel):
    id: str
    item_class_code: str
    item_class_name: str

    class Config:
        from_attributes = True


class ItemClassSelectItem(ItemClassSimple):
    is_active: bool = True
