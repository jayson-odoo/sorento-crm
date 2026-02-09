"""Generic import log schemas."""
from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


class ImportLogBase(BaseModel):
    import_session_id: str
    entity_type: str
    entity_table: str
    filename: Optional[str] = None
    import_type: str
    total_rows: int = 0
    successful_rows: int = 0
    created_rows: int = 0
    updated_rows: int = 0
    failed_rows: int = 0
    skipped_rows: int = 0
    warnings: Optional[Any] = None
    errors: Optional[Any] = None
    summary: Optional[Any] = None
    imported_by: Optional[str] = None
    duration_ms: Optional[int] = None


class ImportLogCreate(ImportLogBase):
    pass


class ImportLogResponse(ImportLogBase):
    id: str
    imported_at: datetime
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
