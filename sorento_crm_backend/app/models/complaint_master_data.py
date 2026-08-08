"""Complaint master data models — root causes and resolutions."""
from sqlalchemy import Column, String, Boolean, DateTime, Text, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.database import Base
import uuid


class ComplaintRootCause(Base):
    __tablename__ = "complaint_root_causes"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(150), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)

    __table_args__ = (
        Index("ix_complaint_root_causes_is_active", "is_active"),
    )


class ComplaintResolution(Base):
    __tablename__ = "complaint_resolutions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(150), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    # Whether choosing this resolution means somebody has to go to the site.
    #
    # Data rather than code because Sorento owns this vocabulary and adds to it: a
    # hardcoded list would need a deployment per new resolution, which is a change nobody
    # makes in time. Defaults false so a resolution an admin adds and forgets to configure
    # dispatches nobody - the opposite default sends a van by omission.
    requires_service_job = Column(
        Boolean, default=False, nullable=False, server_default=text("false")
    )
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)

    __table_args__ = (
        Index("ix_complaint_resolutions_is_active", "is_active"),
    )
