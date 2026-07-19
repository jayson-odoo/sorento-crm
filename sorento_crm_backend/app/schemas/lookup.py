from __future__ import annotations
import re
from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{0,79}$")


class LookupKeywordIn(BaseModel):
    keyword: str = Field(min_length=1, max_length=150)
    locale: Optional[str] = Field(default=None, max_length=10)

    @field_validator("keyword")
    @classmethod
    def _strip_keyword(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("keyword must not be blank")
        return v


class LookupKeywordOut(LookupKeywordIn):
    id: str
    model_config = ConfigDict(from_attributes=True)


class LookupOptionCreate(BaseModel):
    value: str = Field(min_length=1, max_length=150)
    label: str = Field(min_length=1, max_length=255)
    sort_order: int = 0
    is_active: bool = True
    description: Optional[str] = None
    keywords: List[LookupKeywordIn] = Field(default_factory=list)


class LookupOptionUpdate(BaseModel):
    value: Optional[str] = Field(default=None, min_length=1, max_length=150)
    label: Optional[str] = Field(default=None, min_length=1, max_length=255)
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None
    description: Optional[str] = None
    keywords: Optional[List[LookupKeywordIn]] = None  # None = leave unchanged; [] = clear


class LookupOptionResponse(BaseModel):
    id: str
    set_id: str
    value: str
    label: str
    sort_order: int
    is_active: bool
    description: Optional[str]
    keywords: List[LookupKeywordOut]
    created_at: datetime
    updated_at: Optional[datetime]
    model_config = ConfigDict(from_attributes=True)


class LookupSetCreate(BaseModel):
    set_key: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=150)
    description: Optional[str] = None
    is_active: bool = True
    initial_binding: Optional["LookupBindingCreate"] = None  # used by FE create flow

    @field_validator("set_key")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError("set_key must match ^[a-z][a-z0-9_]{0,79}$")
        return v


class LookupSetUpdate(BaseModel):
    set_key: Optional[str] = Field(default=None, min_length=1, max_length=80)
    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    description: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("set_key")
    @classmethod
    def _slug(cls, v):
        if v is not None and not _SLUG_RE.match(v):
            raise ValueError("set_key must match ^[a-z][a-z0-9_]{0,79}$")
        return v


class LookupSetResponse(BaseModel):
    id: str
    tenant_id: Optional[str]
    set_key: str
    name: str
    description: Optional[str]
    is_active: bool
    option_count: int = 0   # populated by service via SQL count(); not an ORM column
    binding_count: int = 0  # populated by service via SQL count(); not an ORM column
    created_at: datetime
    updated_at: Optional[datetime]
    model_config = ConfigDict(from_attributes=True)


class LookupBindingCreate(BaseModel):
    table_name: str = Field(min_length=1, max_length=100)
    column_name: str = Field(min_length=1, max_length=100)
    # Optional default option value the FE pre-selects on a NEW form; validated ∈ set.
    default_value: Optional[str] = Field(default=None, max_length=150)


class LookupBindingResponse(BaseModel):
    id: str
    tenant_id: Optional[str]
    set_id: str
    table_name: str
    column_name: str
    default_value: Optional[str] = None  # option the FE pre-selects on a new form
    table_label: Optional[str] = None   # resolved from eligibility registry at query time
    column_label: Optional[str] = None  # resolved from eligibility registry at query time
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class LookupBindingDefaultUpdate(BaseModel):
    default_value: Optional[str] = Field(default=None, max_length=150)


class LookupEligibilityResponse(BaseModel):
    table_name: str
    column_name: str
    table_label: str
    column_label: str
    data_type: Literal["string", "int"]
    nullable: bool
    is_bound: bool = False  # set when ?available filter applied


class LookupResolveRequest(BaseModel):
    set_key: str
    raw: str = Field(min_length=1)
    locale: Optional[str] = None


class LookupResolveResponse(BaseModel):
    value: str
    label: str
    matched_keyword: Optional[str]
    match_type: Literal["exact_value", "exact_label", "exact_keyword", "normalized"]
    score: float


LookupSetCreate.model_rebuild()
