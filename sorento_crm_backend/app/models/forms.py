"""Forms management models."""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Integer, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid


class Form(Base):
    __tablename__ = "forms"
    __audit_track__ = True  # who changed what (Sub-plan D Tier-2)
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(100), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    # Legacy / downloadable catalog forms (flower stand, sponsorship, etc.). Default marketing for current data.
    form_type = Column(String(64), nullable=False, server_default="marketing", default="marketing")
    purpose = Column(Text, nullable=True)
    language = Column(String(10), default="en", nullable=False)
    version = Column(Integer, default=1, nullable=False)
    is_active = Column(Boolean, default=False, nullable=False)
    attachment_id = Column(UUID(as_uuid=False), ForeignKey("attachments.id", ondelete="SET NULL"), nullable=True)
    access_levels = Column(JSONB, nullable=False, server_default='["dealer","end_user"]')
    # created_by column doesn't exist in database, removed from model
    # created_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    sections = relationship("FormSection", back_populates="form")
    versions = relationship("FormVersion", back_populates="form")
    attachment = relationship("Attachment", foreign_keys=[attachment_id])
    
    __table_args__ = (
        Index("ix_forms_is_active", "is_active"),
        Index("ix_forms_language", "language"),
        Index("ix_forms_form_type", "form_type"),
        Index("ix_forms_access_levels", "access_levels", postgresql_using="gin"),
    )


class FormSection(Base):
    __tablename__ = "form_sections"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    form_id = Column(UUID(as_uuid=False), ForeignKey("forms.id", ondelete="CASCADE"), nullable=False)
    section_name = Column(String(255), nullable=False)
    section_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    
    form = relationship("Form", back_populates="sections")
    fields = relationship("FormField", back_populates="section")
    
    __table_args__ = (
        Index("ix_form_sections_form_id", "form_id"),
        Index("ix_form_sections_section_order", "section_order"),
    )


class FormField(Base):
    __tablename__ = "form_fields"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    section_id = Column(UUID(as_uuid=False), ForeignKey("form_sections.id", ondelete="CASCADE"), nullable=False)
    field_name = Column(String(100), nullable=False)
    field_label = Column(String(255), nullable=False)
    field_type = Column(String(50), nullable=False)
    is_required = Column(Boolean, default=False, nullable=False)
    help_text = Column(Text, nullable=True)
    placeholder = Column(Text, nullable=True)
    validation_rule = Column(String(500), nullable=True)
    min_length = Column(Integer, nullable=True)
    max_length = Column(Integer, nullable=True)
    default_value = Column(Text, nullable=True)
    conditional_logic = Column(JSONB, nullable=True)
    field_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    
    section = relationship("FormSection", back_populates="fields")
    
    __table_args__ = (
        Index("ix_form_fields_section_id", "section_id"),
        Index("ix_form_fields_field_order", "field_order"),
    )


class FormVersion(Base):
    __tablename__ = "form_versions"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    form_id = Column(UUID(as_uuid=False), ForeignKey("forms.id", ondelete="CASCADE"), nullable=False)
    version_number = Column(Integer, nullable=False)
    structure = Column(JSONB, nullable=False)
    change_summary = Column(Text, nullable=True)
    is_active = Column(Boolean, default=False, nullable=False)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    
    form = relationship("Form", back_populates="versions")
    
    __table_args__ = (
        Index("ix_form_versions_form_id", "form_id"),
        Index("uq_form_versions_form_id_version_number", "form_id", "version_number", unique=True),
    )


class FormSubmission(Base):
    __tablename__ = "form_submissions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    form_id = Column(UUID(as_uuid=False), ForeignKey("forms.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(50), default="draft", nullable=False)
    submission_data = Column(JSONB, nullable=False)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    form = relationship("Form")

    __table_args__ = (
        Index("ix_form_submissions_form_id", "form_id"),
        Index("ix_form_submissions_status", "status"),
    )
