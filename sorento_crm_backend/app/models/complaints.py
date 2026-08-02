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

    # --- Parties and the Site (after-sales S1: AC-B1, AC-B6, AC-M37) ---------
    # The Dealer gets a real home. The free-text customer_name above is superseded
    # and read-only for one release (AC-B6); it is dropped in a later slice.
    customer_id = Column(
        UUID(as_uuid=False),
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
    )
    # The Site is whatever was REPORTED, never the Dealer's address. AC-B3: a
    # dealer's owner reporting a fault in his own home carries a dealer binding and
    # a residential Site on the same row. Deriving the Site from the customer record
    # sends a technician to a shop.
    site_address = Column(Text, nullable=True)
    site_contact_name = Column(Text, nullable=True)
    site_contact_phone = Column(Text, nullable=True)
    # AC-M37 / AC-B21: the pin is what a technician navigates to, so it is Numeric
    # with scale 7 (about 1cm). Float does not round-trip a value copied between
    # systems and text cannot be bounded-box queried. Precision 10 leaves 3 integer
    # digits, which covers longitude to 180. Deliberately NOT reconciled against
    # site_address (AC-M39): the pin is for navigation, the address for documents.
    latitude = Column(Numeric(10, 7), nullable=True)
    longitude = Column(Numeric(10, 7), nullable=True)
    place_id = Column(String(128), nullable=True)
    # ADDED, never a rename of customer_type (AC-B6). Nullable because most live
    # rows carry an account category (Project / SMC / E Commerce) that says nothing
    # about who reported the fault, and NULL is the honest value for them (AC-B16).
    # Vocabulary: app.services.party_service.REPORTED_BY_ROLES.
    reported_by_role = Column(String(20), nullable=True)

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

    __table_args__ = (
        Index("ix_complaints_delivery_order_number", "delivery_order_number"),
        Index("ix_complaints_complaint_date", "complaint_date"),
        Index("ix_complaints_customer_name", "customer_name"),
        Index("ix_complaints_complaint_number", "complaint_number"),
        Index("ix_complaints_root_cause_id", "root_cause_id"),
        Index("ix_complaints_resolution_id", "resolution_id"),
        Index("ix_complaints_customer_id", "customer_id"),
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
    # AC-L16. Cover is per product and per part, so a warranty assessment reaches its
    # purchase DATE through this line, never through the complaint. Nullable: a
    # complaint routinely arrives before any receipt does, and blocking intake on it
    # is exactly what AC-C14 forbids.
    consumer_purchase_line_id = Column(
        UUID(as_uuid=False),
        ForeignKey("consumer_purchase_lines.id", ondelete="SET NULL"),
        nullable=True,
    )
    # AC-L31. AC-D5 makes the defect type part of entitlement and the
    # `complaints_defect_type` vocabulary was seeded for it, but until now nothing on
    # a complaint pointed at it - so the engine was called with defect_type_id=None on
    # every complaint and every defect-restricted term, including the lifetime ceramic
    # body (crack and leak only), answered `unknown` forever.
    # `complaints.defects_discovered` is NOT this: it is the
    # `complaints_defects_discovered` lookup, which records WHEN a defect was noticed
    # ("Upon delivery after unloading"), not what it is.
    defect_type_id = Column(
        UUID(as_uuid=False), ForeignKey("lookup_options.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    complaint = relationship("Complaint", back_populates="product_lines")

    __table_args__ = (
        Index("ix_complaint_product_lines_complaint_id", "complaint_id"),
        Index("ix_complaint_product_lines_purchase_line", "consumer_purchase_line_id"),
        Index("ix_complaint_product_lines_defect_type_id", "defect_type_id"),
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


