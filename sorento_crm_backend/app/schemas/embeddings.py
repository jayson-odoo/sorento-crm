"""Schemas for embedding queue and retrieval payloads."""
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field


class EmbeddingEventPayload(BaseModel):
    event_id: str
    event_type: str
    event_version: int = 1
    occurred_at: datetime
    source_type: str
    source_id: str
    source_key: Optional[str] = None
    tenant_id: Optional[str] = None
    source_updated_at: Optional[datetime] = None
    source_hash: Optional[str] = None
    changed_fields: list[str] = Field(default_factory=list)
    correlation_id: Optional[str] = None
    triggered_by: Optional[str] = None


class EmbeddingQueueItemResponse(BaseModel):
    id: str
    source_type: str
    source_id: str
    event_type: str
    status: str
    retry_count: int
    available_at: datetime
    last_error: Optional[str] = None
    created_at: datetime
    processed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class EmbeddingSearchRequest(BaseModel):
    query: str
    top_k: int = 5
    source_type: Optional[str] = None
    visibility_scope: Optional[str] = None
    tenant_id: Optional[str] = None


class EmbeddingSearchResultItem(BaseModel):
    id: str
    source_type: str
    source_id: str
    chunk_index: int
    chunk_text: str
    source_key: Optional[str] = None
    title: Optional[str] = None
    visibility_scope: Optional[str] = None
    model_name: str
    model_version: str
    similarity: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class EmbeddingSearchResponse(BaseModel):
    data: list[EmbeddingSearchResultItem]
    model: str
    dimensions: int


class ToolRagSearchRequest(BaseModel):
    query: str
    top_k: int = 5
    include_planned: bool = False
    category: Optional[str] = None
    implementation_status: Optional[str] = None


class ToolRagResultItem(BaseModel):
    tool_name: str
    score: float
    why_selected: str
    status: str
    category: Optional[str] = None
    required_params: list[str] = Field(default_factory=list)
    missing_params: list[str] = Field(default_factory=list)
    source_id: str
    source_type: str
    chunk_text: str


class ToolRagSearchResponse(BaseModel):
    data: list[ToolRagResultItem]
    model: str
    dimensions: int
