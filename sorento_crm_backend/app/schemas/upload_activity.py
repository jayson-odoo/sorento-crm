"""
Upload Activity drawer feed schemas.

These shapes mirror the FE contract at
sorento_crm_frontend/services/uploadActivityService.ts. Phase 2 of
the upload-activity drawer rollout (see docs/plans/PLAN-upload-activity-drawer.md).
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


FileStatus = Literal[
    "uploading",
    "processing",
    "linked",
    "unlinked",
    "failed",
]

SessionStatus = Literal[
    "uploading",
    "processing",
    "linked",
    "partial",
    "failed",
]

SessionType = Literal["single", "multi", "bulk_zip", "import_job"]


class LinkedEntity(BaseModel):
    entity_type: str
    entity_id: str
    display_name: str
    matched_by: str


class UnlinkedReason(BaseModel):
    reason: str


class UploadActivityFile(BaseModel):
    """One leaf row inside a session — corresponds to one attachment."""

    client_id: str  # echoes attachment_id (no FE-only state here)
    attachment_id: Optional[str] = None
    filename: str
    status: FileStatus
    summary: str = ""
    linked: List[LinkedEntity] = Field(default_factory=list)
    unlinked_reasons: List[UnlinkedReason] = Field(default_factory=list)
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    integration_log_id: Optional[str] = None
    last_updated_at: datetime


class SessionAggregate(BaseModel):
    total: int
    uploading: int = 0
    processing: int = 0
    linked: int = 0
    unlinked: int = 0
    failed: int = 0


class UploadActivitySession(BaseModel):
    session_id: str
    session_type: SessionType
    title: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: SessionStatus
    aggregate: SessionAggregate
    files: List[UploadActivityFile] = Field(default_factory=list)
    import_job_id: Optional[str] = None
    needs_action: bool = False
    # ---- import_job sessions only (Excel/data imports, no attachment rows).
    # Replaces the per-page LatestImportStatusPanel bar — see
    # docs/plans/PLAN-do-macro-upload-and-drawer-import-jobs.md.
    job_type: Optional[str] = None
    total_rows: Optional[int] = None
    processed_rows: Optional[int] = None
    successful_rows: Optional[int] = None
    failed_rows: Optional[int] = None
    skipped_rows: Optional[int] = None
    job_error: Optional[str] = None


class UploadActivityResponse(BaseModel):
    sessions: List[UploadActivitySession]
