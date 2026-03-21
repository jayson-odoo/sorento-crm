"""Pydantic schemas for dynamic list query (filter DSL) and export."""
from __future__ import annotations

from typing import Any, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FilterCondition(BaseModel):
    field_key: str = Field(..., min_length=1)
    op: Literal[
        "eq",
        "ne",
        "contains",
        "starts_with",
        "in",
        "gt",
        "gte",
        "lt",
        "lte",
        "is_null",
    ]
    value: Optional[Any] = None


class FilterGroup(BaseModel):
    op: Literal["and", "or"]
    children: List[Union["FilterGroup", FilterCondition]] = Field(default_factory=list)

    @field_validator("children")
    @classmethod
    def non_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("filter group must have at least one child")
        return v


FilterGroup.model_rebuild()


class ListSearchRequest(BaseModel):
    resource: Literal["orders", "products", "suppliers"]
    filter: Optional[FilterGroup] = None
    page: int = Field(1, ge=1)
    limit: int = Field(50, ge=1, le=1000)
    sort: Optional[str] = None
    dir: Optional[Literal["asc", "desc"]] = "asc"
    """Free-text search merged with AND (same behaviour as legacy list `query` param)."""
    quick_search: Optional[str] = None
    # Legacy list filters (merged with AND) — same as existing GET list endpoints
    customer_id: Optional[str] = None
    order_status_id: Optional[str] = None
    has_order_lines: Optional[str] = None
    category_id: Optional[str] = None
    brand_id: Optional[str] = None
    product_status: Optional[str] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    item_type: Optional[str] = None


class ExportFieldSelection(BaseModel):
    field_key: str = Field(..., min_length=1)


class ListExportRequest(BaseModel):
    resource: Literal["orders", "products", "suppliers"]
    filter: Optional[FilterGroup] = None
    quick_search: Optional[str] = None
    fields: List[ExportFieldSelection] = Field(..., min_length=1)
    """When set, export is limited to these ids (ANDed with filters — only rows matching both are returned)."""
    record_ids: Optional[List[str]] = Field(default=None, max_length=5000)
    customer_id: Optional[str] = None
    order_status_id: Optional[str] = None
    has_order_lines: Optional[str] = None
    category_id: Optional[str] = None
    brand_id: Optional[str] = None
    product_status: Optional[str] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    item_type: Optional[str] = None


class ListQueryFieldResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    field_key: str
    label: str
    data_type: str
    compile_key: str
    allowed_operators: List[str]
    filterable: bool
    exportable: bool
    export_column_name: Optional[str] = None
    is_line_field: bool = False
    sort_order: int = 0
    """UI grouping for export dialog: order | line (orders resource only)."""
    export_section: Optional[Literal["order", "line"]] = None
    """Nested group under line: product | warehouse (orders resource only)."""
    export_subgroup: Optional[Literal["product", "warehouse"]] = None


class ListQueryResourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    resource_key: str
    display_name: str
    description: Optional[str] = None
