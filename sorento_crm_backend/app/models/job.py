"""Job tracking model for import jobs."""
from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Text,
    JSON,
    ForeignKey,
    Index,
    Enum as SQLEnum,
)
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

    # Active company snapshotted at enqueue (multi-company isolation). The worker
    # reads this back and re-establishes the request's company scope so owned
    # writes auto-stamp + are isolated. NULL => system/None-scope import.
    # NOT a CompanyScopedMixin (job-tracking infra, never auto-filtered).
    company_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    
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
    # storage bucket at import time so the file is retrievable later. All nullable - 
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


class ImportJobRow(Base):
    """One source row's outcome, so an import can say what it did with every row.

    Written by ``app.services.import_outcome.ImportOutcome`` on its OWN session
    (buffered bulk inserts, never one INSERT per row) so the detail survives an
    import that rolls back, and so a 4k-row file costs a handful of round trips.

    Job-tracking infrastructure like ``ImportJob``: deliberately NOT a
    ``CompanyScopedMixin`` - it is never auto-filtered / business-partitioned.
    """

    __tablename__ = "import_job_rows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    import_job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("import_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    #: Source row number (Excel row / ZIP entry index). Null for job-level entries.
    row_number = Column(Integer, nullable=True)
    #: created | updated | unchanged | skipped | failed
    outcome = Column(String(20), nullable=False)
    #: Stable slug from app.services.import_outcome_codes.
    code = Column(String(64), nullable=False)
    #: Human sentence, safe to show verbatim.
    message = Column(Text, nullable=True)
    #: The offending token (product code, doc no, filename) - powers `top_values`.
    value = Column(String(255), nullable=True)
    #: The row's mapped business columns. Never raw UUIDs (the UI prints this).
    identity = Column(JSONB, nullable=True)
    #: What was written, when known.
    entity_type = Column(String(64), nullable=True)
    entity_id = Column(String(64), nullable=True)

    created_at = Column(
        DateTime(timezone=False), server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (
        Index("ix_import_job_rows_job_outcome", "import_job_id", "outcome"),
        Index("ix_import_job_rows_job_code", "import_job_id", "code"),
        Index("ix_import_job_rows_job_row", "import_job_id", "row_number"),
    )

    def __repr__(self):
        return f"<ImportJobRow {self.import_job_id} row={self.row_number} {self.outcome}:{self.code}>"
