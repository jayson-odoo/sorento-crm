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
    
    model_config = ConfigDict(from_attributes=True)


class JobStatusResponse(BaseModel):
    """Schema for job status response."""
    job_id: str
    status: str
    progress: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
