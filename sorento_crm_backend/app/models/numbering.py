"""Document numbering rules for system-generated running numbers."""
import uuid
from sqlalchemy import Column, String, Integer, Boolean, Text, DateTime, func
from sqlalchemy.sql import func
from app.database import Base


class DocumentNumberingRule(Base):
    """Configurable running number rule per document type (e.g. purchase_request, sponsorship_form)."""
    __tablename__ = "document_numbering_rules"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    doc_type = Column(String(50), unique=True, nullable=False, index=True)
    enabled = Column(Boolean, default=True, nullable=False)
    prefix_template = Column(Text, nullable=True)  # e.g. "PR-{year}-" or "SF-{year}{month}-"
    number_digits = Column(Integer, default=4, nullable=False)
    next_value = Column(Integer, default=1, nullable=False)
    start_value = Column(Integer, default=1, nullable=False)
    reset_policy = Column(String(20), default="none", nullable=False)  # none | yearly | monthly
    last_reset_key = Column(String(20), nullable=True)  # e.g. "2026" or "2026-03"
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)
