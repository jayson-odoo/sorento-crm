"""Common Pydantic schemas."""
from pydantic import BaseModel
from typing import Any, Dict, Optional, List, Generic, TypeVar

T = TypeVar('T')


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
