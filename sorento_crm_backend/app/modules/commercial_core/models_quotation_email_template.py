"""DB-backed email templates for quotation customer emails (token placeholders)."""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


def _uuid_str() -> str:
    return str(uuid.uuid4())


class QuotationEmailTemplate(Base):
    __tablename__ = "quotation_email_templates"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    code = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    subject_template = Column(Text, nullable=False)
    body_html_template = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, server_default="true")
    is_default = Column(Boolean, nullable=False, server_default="false")
    sort_order = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("code", name="uq_quotation_email_templates_code"),
        Index("ix_quotation_email_templates_active_default", "is_active", "is_default"),
    )
