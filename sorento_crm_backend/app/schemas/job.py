"""Pydantic schemas for import jobs."""
from pydantic import BaseModel, ConfigDict
from typing import Optional, Dict, Any
from datetime import datetime
from app.models.job import JobStatus


class ImportJobBase(BaseModel):
    """Base schema for import job."""
    job_type: str
    filename: Optional[str] = None
    job_metadata: Optional[Dict[str, Any]] = None


class ImportJobCreate(ImportJobBase):
    """Schema for creating import job."""
    pass


class ImportJobResponse(BaseModel):
    """Schema for import job response."""
    id: str
    job_id: str
    job_type: str
    status: str  # Store as string (enum value) for compatibility
    user_id: str
    filename: Optional[str] = None
    total_rows: int = 0
    processed_rows: int = 0
    successful_rows: int = 0
    failed_rows: int = 0
    skipped_rows: int = 0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    job_metadata: Optional[Dict[str, Any]] = None
    # Retained source file (tracing). Raw storage key is intentionally NOT exposed  - 
    # the FE downloads via GET /jobs/{id}/source which returns a fresh signed URL.
    source_filename: Optional[str] = None
    source_file_size: Optional[int] = None
    has_source_file: bool = False

    model_config = ConfigDict(from_attributes=True)


class ImportJobRowResponse(BaseModel):
    """One captured source row of an import job.

    ``identity`` carries the row's mapped business columns (doc no, item code,
    location...) - never raw UUIDs, since the UI prints it verbatim.
    """
    id: str
    row_number: Optional[int] = None
    outcome: str
    code: str
    label: Optional[str] = None
    message: Optional[str] = None
    value: Optional[str] = None
    identity: Optional[Dict[str, Any]] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class JobStatusResponse(BaseModel):
    """Schema for job status response."""
    job_id: str
    status: str
    progress: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
