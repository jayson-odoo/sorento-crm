"""Saved accessories box designs (PRICETAG-ACCESSORY-DESIGNER). Plan:
documentation/plans/dealer-kit/PLAN-pricetag-accessory-designer-07nov.md "Accessory templates"."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_DESIGN_BYTES = 64 * 1024
#: Per-box keys: they live on the box in a tag template, never in the shared design.
PER_BOX_KEYS = ("kind", "subjectSlot", "subjectPart", "presetId")


def _clean_name(value: str) -> str:
    cleaned = " ".join(str(value).split())
    if not cleaned:
        raise ValueError("A name is required")
    return cleaned


def _clean_design(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("The design must be an object")
    if len(json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")) > MAX_DESIGN_BYTES:
        raise ValueError("The design is larger than 64 KB")
    return {key: item for key, item in value.items() if key not in PER_BOX_KEYS}


class AccessoryTemplateCreate(BaseModel):
    name: str = Field(..., max_length=100)
    design: Dict[str, Any]

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _clean_name(value)

    @field_validator("design", mode="before")
    @classmethod
    def _design(cls, value: Any) -> Dict[str, Any]:
        return _clean_design(value)


class AccessoryTemplateUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    design: Optional[Dict[str, Any]] = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else _clean_name(value)

    @field_validator("design", mode="before")
    @classmethod
    def _design(cls, value: Any) -> Optional[Dict[str, Any]]:
        return None if value is None else _clean_design(value)


class AccessoryTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    design: Dict[str, Any]
    #: How many tag templates carry a box linked to this design.
    used_in: int = 0
    created_by_name: Optional[str] = None
    updated_at: datetime
    created_at: datetime
    #: Only on a PUT that changed the design: boxes rewritten across every document.
    rewritten: int = 0


class AccessoryTemplateUsageItem(BaseModel):
    id: str
    name: str


class AccessoryTemplateUsageOut(BaseModel):
    templates: List[AccessoryTemplateUsageItem] = []
