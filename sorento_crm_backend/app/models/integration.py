"""Integration logging models."""
from sqlalchemy import Column, String, Boolean, DateTime, Text, Integer, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.database import Base
import uuid


class IntegrationLog(Base):
    __tablename__ = "integration_log"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    integration_channel = Column(String(100), nullable=False)
    business_table = Column(String(100), nullable=False)
    business_id = Column(UUID(as_uuid=False), nullable=False)
    external_reference = Column(String(255), nullable=True)
    direction = Column(String(10), nullable=False)  # "inbound" or "outbound"
    endpoint = Column(String(512), nullable=False)
    http_method = Column(String(10), nullable=False)
    request_headers = Column(Text, nullable=True)
    request_payload = Column(Text, nullable=True)
    status_code = Column(Integer, nullable=True)
    status = Column(String(50), nullable=False, default="pending")  # pending, processing, success, failed
    response_headers = Column(Text, nullable=True)
    response_payload = Column(Text, nullable=True)
    error_code = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    correlation_id = Column(UUID(as_uuid=False), nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    max_retry_allowed = Column(Integer, default=3, nullable=False)
    next_retry_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    created_by = Column(UUID(as_uuid=False), nullable=True)
    processed_at = Column(DateTime(timezone=False), nullable=True)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_integration_log_business_table_business_id", "business_table", "business_id"),
        Index("ix_integration_log_status", "status"),
        Index("ix_integration_log_integration_channel", "integration_channel"),
        Index("ix_integration_log_created_at", "created_at"),
        Index("ix_integration_log_next_retry_at", "next_retry_at"),
    )
