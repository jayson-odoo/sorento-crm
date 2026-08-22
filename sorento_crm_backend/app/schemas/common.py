"""Common Pydantic schemas."""
from pydantic import BaseModel, Field, field_validator
from typing import Any, Dict, Optional, List, Generic, TypeVar

T = TypeVar('T')


class FormVoidRequest(BaseModel):
    """Body for the per-form ``POST /{id}/void`` endpoints.

    ``void_reason`` is required and must be free-text with at least 3 non-space
    characters. Blank / whitespace-only / too-short values fail here (Pydantic
    422) before the service runs (UAC SCH-3 / ACT-3).
    """
    void_reason: str = Field(..., description="Required free-text reason (>= 3 non-space chars).")

    @field_validator("void_reason")
    @classmethod
    def _non_empty_min_len(cls, v: str) -> str:
        cleaned = (v or "").strip()
        if len(cleaned) < 3:
            raise ValueError("A void reason of at least 3 characters is required.")
        return cleaned

# Shared ceiling for DataGrid list endpoints (`page`/`limit` pagination).
# The frontend pagination selector offers up to 1000 rows per page; every
# `ListResponse[...]` GET endpoint MUST allow at least this much or the grid
# 422s and renders empty when a user picks a large page size. Keep this in
# lockstep with the FE page-size options in `data-grid-pagination.tsx`.
# Bulk export is NOT bound by this — it streams the full filtered set server-side.
MAX_PAGE_LIMIT = 1000


class PaginationParams(BaseModel):
    """Pagination query parameters."""
    page: int = 1
    limit: int = 50


class PaginationResponse(BaseModel):
    """Pagination metadata."""
    total: int
    page: int
    limit: int


class ListResponse(BaseModel, Generic[T]):
    """Standard list response with pagination."""
    data: List[T]
    pagination: PaginationResponse
    empty: bool = False
    fallback_used: bool = False
    # Populated by endpoints that accept an `entities` free-text bag (resolved via
    # entity_resolver). Mirrors the resolver's matched/ambiguous/unresolved buckets
    # so the agent can surface "what did we actually filter on" back to the user.
    resolved_entities: Optional[Dict[str, Any]] = None
    # Every company this lookup actually searched, `{"id", "name"}` sorted by name.
    # Set ONLY when the lookup spans more than one company (see
    # `company_scope.stamp_lookup_companies`), so a single-company reply is
    # unchanged - and an empty two-company result can still say which companies
    # were checked.
    lookup_companies: Optional[List[Dict[str, Any]]] = None


class ErrorResponse(BaseModel):
    """Standard error response."""
    message: str
    detail: Optional[str] = None
    code: Optional[str] = None


class SuccessResponse(BaseModel):
    """Standard success response."""
    message: str
    data: Optional[dict] = None


class ValidateImportResponse(BaseModel):
    """Response for validate-only import (products, GRN, SPO, order tracking). No DB writes."""
    valid: bool  # True if no errors (warnings allowed)
    errors: List[str] = []
    warnings: List[str] = []
    summary: Optional[dict] = None  # e.g. total_rows, would_create, would_update
