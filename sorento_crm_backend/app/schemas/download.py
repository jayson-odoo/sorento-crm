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


class PdfExportOptions(BaseModel):
    """Optional body of an entity PDF export (PLAN-portal-submission-revisions 6.3/6.4).

    Both fields are optional and mutually exclusive; an absent or empty body is
    the export as it has always behaved, so every existing caller keeps working.

    * ``revision_id`` - print that ONE stored version instead of the current form.
    * ``include_revisions`` - print the current form followed by the whole
      revision lineage.
    """

    revision_id: Optional[str] = None
    include_revisions: bool = False
