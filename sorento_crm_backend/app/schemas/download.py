"""Schemas for user downloads (My Downloads drawer)."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class DownloadResponse(BaseModel):
    id: str
    kind: str
    status: str
    filename: Optional[str] = None
    source_entity_type: Optional[str] = None
    source_entity_id: Optional[str] = None
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    ready_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DownloadListResponse(BaseModel):
    downloads: List[DownloadResponse]


class DownloadUrlResponse(BaseModel):
    url: str
    filename: Optional[str] = None
