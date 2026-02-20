"""Resource management models."""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Integer, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid


class AttachmentDirectory(Base):
    """Hierarchical folder for organizing attachments."""
    __tablename__ = "attachment_directories"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    parent_id = Column(UUID(as_uuid=False), ForeignKey("attachment_directories.id", ondelete="CASCADE"), nullable=True)
    name = Column(String(255), nullable=False)
    sort_order = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime(timezone=False), nullable=True)
    deleted_by = Column(String, nullable=True)

    parent = relationship("AttachmentDirectory", remote_side="AttachmentDirectory.id", back_populates="children")
    children = relationship("AttachmentDirectory", back_populates="parent", cascade="all, delete-orphan")
    attachments = relationship("Attachment", back_populates="directory")

    __table_args__ = (Index("ix_attachment_directories_parent_id", "parent_id"), Index("ix_attachment_directories_is_deleted", "is_deleted"),)


class AttachmentType(Base):
    __tablename__ = "attachment_types"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(50), unique=True, nullable=True)
    type_name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    allowed_extensions = Column(String(255), nullable=False)
    max_file_size_mb = Column(Integer, default=10, nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    
    attachments = relationship("Attachment", back_populates="attachment_type")


class Attachment(Base):
    __tablename__ = "attachments"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    attachment_type_id = Column(UUID(as_uuid=False), ForeignKey("attachment_types.id", ondelete="SET NULL"), nullable=True)
    original_filename = Column(String(255), nullable=False)
    stored_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size_bytes = Column(Integer, nullable=True)
    mime_type = Column(String(100), nullable=True)
    file_hash = Column(String(64), nullable=True)
    entity_type = Column(String(100), nullable=True)
    entity_id = Column(String, nullable=True)
    uploaded_by = Column(String, nullable=True)
    uploaded_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime(timezone=False), nullable=True)
    deleted_by = Column(String, nullable=True)
    directory_id = Column(UUID(as_uuid=False), ForeignKey("attachment_directories.id", ondelete="SET NULL"), nullable=True)
    full_directory_path = Column(Text, nullable=True)  # e.g. "SORENTO CABANA (DEALER) --> SORENTO --> Product Photo --> Angle Valve"
    description = Column(Text, nullable=True)  # User-editable description for search / n8n AI agent
    access_levels = Column(JSONB, nullable=False, server_default='["dealer","end_user"]')  # dealer / end_user visibility
    sort_order = Column(Integer, nullable=True)

    attachment_type = relationship("AttachmentType", back_populates="attachments")
    directory = relationship("AttachmentDirectory", back_populates="attachments")

    __table_args__ = (
        Index("ix_attachments_entity_type_entity_id", "entity_type", "entity_id"),
        Index("ix_attachments_uploaded_by", "uploaded_by"),
        Index("ix_attachments_is_deleted", "is_deleted"),
        Index("ix_attachments_file_hash", "file_hash"),
        Index("ix_attachments_directory_id", "directory_id"),
        Index("ix_attachments_access_levels", "access_levels", postgresql_using="gin"),
    )
