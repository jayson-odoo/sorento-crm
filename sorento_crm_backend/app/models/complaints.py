"""Complaint management models."""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Numeric, Date, Index, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.resources import Attachment


class Complaint(Base):
    """Complaint model. Set __audit_track__ = True for automatic audit logging of changes."""
    __tablename__ = "complaints"
    __audit_track__ = True
    __audit_entity_type__ = "complaint"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    complaint_number = Column(Text, nullable=True)
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
    quantity = Column(Text, nullable=True)
    salesperson = Column(Text, nullable=True)
    customer_name = Column(Text, nullable=True)
    contact_person = Column(Text, nullable=True)
    contact_number = Column(Text, nullable=True)
    customer_address = Column(Text, nullable=True)
    project_title = Column(Text, nullable=True)
    contact_id = Column(Text, nullable=True)
    space_id = Column(Text, nullable=True)
    respond_inbox_url = Column(Text, nullable=True)
    technical_team_response = Column(Text, nullable=True)
    status = Column(String(50), default="new", nullable=False)
    last_responded_by = Column(Text, nullable=True)
    last_responded_at = Column(DateTime(timezone=False), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    rejected_at = Column(DateTime(timezone=False), nullable=True)
    rejected_by = Column(Text, nullable=True)
    resolved_at = Column(DateTime(timezone=False), nullable=True)
    resolved_by = Column(Text, nullable=True)
    # Void (terminal, irreversible). DB FK voided_by -> users.id added in migration
    # 287_form_void (kept off the model, mirroring rejected_by/resolved_by Text).
    void_reason = Column(Text, nullable=True)
    voided_by = Column(Text, nullable=True)  # users.id of the actor who voided
    voided_at = Column(DateTime(timezone=False), nullable=True)
    root_cause_id = Column(UUID(as_uuid=False), ForeignKey("complaint_root_causes.id", ondelete="RESTRICT"), nullable=True)
    resolution_id = Column(UUID(as_uuid=False), ForeignKey("complaint_resolutions.id", ondelete="RESTRICT"), nullable=True)
    root_cause_notified_at = Column(DateTime(timezone=False), nullable=True)
    resolution_notified_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    assigned_to = Column(Text, nullable=True)  # Respond.io assignee user id; display name resolved via User.respond_user_id
    portal_draft_at = Column(DateTime(timezone=False), nullable=True)  # set while user is editing in submission portal; cleared on Submit
    required_on_site_support = Column(Boolean, nullable=False, server_default="false")

    attachments = relationship("ComplaintAttachment", back_populates="complaint")
    root_cause = relationship("ComplaintRootCause", foreign_keys=[root_cause_id])
    resolution = relationship("ComplaintResolution", foreign_keys=[resolution_id])
    # Per-product line items (source of truth). The legacy product_code /
    # product_type / quantity Text columns above are kept denormalized (CSV,
    # index-aligned) from these lines for backward compat (n8n, public view).
    product_lines = relationship(
        "ComplaintProductLine",
        back_populates="complaint",
        cascade="all, delete-orphan",
        order_by="ComplaintProductLine.sort_order",
    )

    @property
    def response_write_allowed(self) -> bool:
        """Whether ``technical_team_response`` may be written at this status (UAC O1).

        Read straight off ``response_gate`` - the same module the write path raises
        from - so the flag the UI gates on and the rule the server enforces cannot
        disagree. Derived live; never a column, nothing to backfill.
        """
        from app.services.response_gate import COMPLAINT, is_response_status_allowed

        return is_response_status_allowed(COMPLAINT, self.status)

    __table_args__ = (
        Index("ix_complaints_delivery_order_number", "delivery_order_number"),
        Index("ix_complaints_complaint_date", "complaint_date"),
        Index("ix_complaints_customer_name", "customer_name"),
        Index("ix_complaints_complaint_number", "complaint_number"),
        Index("ix_complaints_root_cause_id", "root_cause_id"),
        Index("ix_complaints_resolution_id", "resolution_id"),
    )


class ComplaintProductLine(Base):
    """One affected product per complaint: code + quantity (+ derived type)."""
    __tablename__ = "complaint_product_lines"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    complaint_id = Column(UUID(as_uuid=False), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False)
    product_code = Column(Text, nullable=False)
    quantity = Column(Text, nullable=True)  # free text to mirror complaints.quantity ("5" or "5 boxes")
    product_type = Column(Text, nullable=True)  # auto-derived from product master category
    sort_order = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    complaint = relationship("Complaint", back_populates="product_lines")

    __table_args__ = (
        Index("ix_complaint_product_lines_complaint_id", "complaint_id"),
    )


class ComplaintAttachment(Base):
    """Link table: complaint_id + attachment_id (like promotion_attachments)."""
    __tablename__ = "complaint_attachments"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    complaint_id = Column(UUID(as_uuid=False), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False)
    attachment_id = Column(UUID(as_uuid=False), ForeignKey("attachments.id", ondelete="CASCADE"), nullable=False)
    is_primary = Column(Boolean, default=False, nullable=False)
    sort_order = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    created_by = Column(UUID(as_uuid=False), nullable=True)
    
    complaint = relationship("Complaint", back_populates="attachments")
    attachment = relationship("Attachment", foreign_keys=[attachment_id])
    
    __table_args__ = (
        Index("ix_complaint_attachments_complaint_id", "complaint_id"),
        Index("ix_complaint_attachments_attachment_id", "attachment_id"),
        Index("uq_complaint_attachment", "complaint_id", "attachment_id", unique=True),
    )


class ComplaintManualAttachment(Base):
    __tablename__ = "complaint_manual_attachments"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    complaint_id = Column(UUID(as_uuid=False), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False)
    attachment_id = Column(UUID(as_uuid=False), nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_complaint_manual_attachments_complaint_id", "complaint_id"),
        Index("ix_complaint_manual_attachments_attachment_id", "attachment_id"),
    )


class ComplaintFulfilmentOrder(Base):
    """Link: complaint <-> replacement/fulfilment Delivery Order.

    Auto-managed from the DO's Remarks CS field (the DO names the complaint
    number(s) it fulfils). Many-to-many; ``delivery_notified_at`` is the
    per-(complaint, DO) idempotency stamp for the delivery notification.
    See docs/plans/PLAN-complaint-do-auto-fulfilment.md.
    """
    __tablename__ = "complaint_fulfilment_orders"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    complaint_id = Column(UUID(as_uuid=False), ForeignKey("complaints.id", ondelete="CASCADE"), nullable=False)
    order_id = Column(UUID(as_uuid=False), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    linked_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    delivery_notified_at = Column(DateTime(timezone=False), nullable=True)

    complaint = relationship("Complaint")
    order = relationship("Order")

    __table_args__ = (
        Index("ix_complaint_fulfilment_orders_complaint_id", "complaint_id"),
        Index("ix_complaint_fulfilment_orders_order_id", "order_id"),
        Index("uq_complaint_fulfilment_order", "complaint_id", "order_id", unique=True),
    )


