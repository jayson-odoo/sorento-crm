"""Complaint management models."""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Numeric, Date, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid


class Complaint(Base):
    __tablename__ = "complaints"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    delivery_order_number = Column(Text, nullable=True)
    complaint_date = Column(Date, nullable=True)
    customer_type = Column(Text, nullable=True)
    customer_type_others = Column(Text, nullable=True)
    within_warranty = Column(Text, nullable=True)
    product_type = Column(Text, nullable=True)
    defects_discovered = Column(Text, nullable=True)
    complaint_type = Column(Text, nullable=True)
    defect_description = Column(Text, nullable=True)
    product_code = Column(Text, nullable=True)
    salesperson = Column(Text, nullable=True)
    customer_name = Column(Text, nullable=True)
    contact_person = Column(Text, nullable=True)
    contact_number = Column(Text, nullable=True)
    customer_address = Column(Text, nullable=True)
    project_title = Column(Text, nullable=True)
    
    attachments = relationship("ComplaintAttachment", back_populates="complaint")
    
    __table_args__ = (
        Index("ix_complaints_delivery_order_number", "delivery_order_number"),
        Index("ix_complaints_complaint_date", "complaint_date"),
        Index("ix_complaints_customer_name", "customer_name"),
    )


class ComplaintAttachment(Base):
    __tablename__ = "complaint_attachments"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    complaint_id = Column(UUID(as_uuid=False), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False)
    file_name = Column(Text, nullable=True)
    file_url = Column(Text, nullable=True)
    file_size_bytes = Column(Numeric(20, 0), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    complaint = relationship("Complaint", back_populates="attachments")
    
    __table_args__ = (
        Index("ix_complaint_attachments_complaint_id", "complaint_id"),
    )


class ComplaintManualAttachment(Base):
    __tablename__ = "complaint_manual_attachments"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    complaint_id = Column(UUID(as_uuid=False), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False)
    attachment_id = Column(UUID(as_uuid=False), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_complaint_manual_attachments_complaint_id", "complaint_id"),
        Index("ix_complaint_manual_attachments_attachment_id", "attachment_id"),
    )


