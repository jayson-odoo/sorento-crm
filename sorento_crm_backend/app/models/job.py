"""Job tracking model for import jobs."""
from sqlalchemy import Column, String, Integer, DateTime, Text, JSON, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid
import enum
from app.database import Base


class JobStatus(str, enum.Enum):
    """Job status enumeration."""
    PENDING = "pending"
    QUEUED = "queued"
    STARTED = "started"
    FINISHED = "finished"
    FAILED = "failed"
    CANCELLED = "cancelled"
    
    def __str__(self):
        return self.value


class ImportJob(Base):
    """Model for tracking import jobs."""
    __tablename__ = "import_jobs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(String, unique=True, nullable=False, index=True)  # RQ job ID
    job_type = Column(String, nullable=False)  # e.g., 'stock_import', 'order_import'
    status = Column(SQLEnum(JobStatus, name="jobstatus", native_enum=True, values_callable=lambda obj: [e.value for e in obj]), default=JobStatus.PENDING.value, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    
    # Job metadata
    filename = Column(String, nullable=True)
    total_rows = Column(Integer, default=0)
    processed_rows = Column(Integer, default=0)
    successful_rows = Column(Integer, default=0)
    failed_rows = Column(Integer, default=0)
    skipped_rows = Column(Integer, default=0)
    
    # Results and errors
    result = Column(JSONB, nullable=True)  # Store job result
    error = Column(Text, nullable=True)  # Store error message
    
    # Timestamps
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=False), nullable=True)
    completed_at = Column(DateTime(timezone=False), nullable=True)
    updated_at = Column(DateTime(timezone=False), nullable=True)
    
    # Retained source file (tracing): the ORIGINAL uploaded bytes are streamed to the
    # storage bucket at import time so the file is retrievable later. All nullable —
    # storage is best-effort (never blocks an import) and older jobs / non-file imports
    # (products, warehouses) have none. See docs/plans/imports/.
    source_filename = Column(String, nullable=True)       # original upload name (display)
    source_file_key = Column(String, nullable=True)       # storage object key
    source_file_provider = Column(String, nullable=True)  # 's3' | 'r2'
    source_file_size = Column(Integer, nullable=True)      # bytes

    # Additional metadata
    job_metadata = Column('metadata', JSONB, nullable=True)  # Store additional job metadata
    
    def __repr__(self):
        return f"<ImportJob {self.job_id} ({self.status})>"
