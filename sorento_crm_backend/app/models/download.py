"""User download model: async-generated files (e.g. complaint PDFs) surfaced in
the "My Downloads" drawer.

A download row is created in status 'pending' when a user requests an export, an
RQ task flips it to 'processing' then 'ready' (with a storage key) or 'failed'
(with an error). The drawer polls per-user rows while any are in flight.
"""
import enum
import uuid

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class DownloadStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class UserDownload(Base):
    __tablename__ = "user_downloads"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    # What kind of export this is, e.g. 'complaint_pdf'. Free-form for forward-compat.
    kind = Column(String(50), nullable=False)
    # Optional source pointer so the drawer can deep-link / dedupe.
    source_entity_type = Column(String(50), nullable=True)
    # Polymorphic (no FK) but always a uuid — see migration 300.
    source_entity_id = Column(UUID(as_uuid=False), nullable=True, index=True)
    status = Column(
        SQLEnum(
            DownloadStatus,
            native_enum=False,
            length=20,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=DownloadStatus.PENDING.value,
        nullable=False,
        index=True,
    )
    filename = Column(String(255), nullable=True)
    storage_provider = Column(String(10), nullable=True)  # 's3' | 'r2'
    storage_key = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False, index=True)
    ready_at = Column(DateTime(timezone=False), nullable=True)
