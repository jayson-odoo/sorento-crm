"""Procurement models."""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Integer, Numeric, Index, Date, Computed, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid

# Forward references for relationships
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.inventory import Warehouse, StorageZone
    from app.models.resources import Attachment


class Supplier(Base):
    __tablename__ = "suppliers"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    supplier_code = Column(String(50), unique=True, nullable=False)
    supplier_name = Column(String(255), nullable=False)
    contact_name = Column(String(150), nullable=True)
    email = Column(String(150), nullable=True)
    phone_number = Column(String(50), nullable=True)
    website = Column(String(255), nullable=True)
    address_line1 = Column(String(255), nullable=True)
    address_line2 = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    postal_code = Column(String(20), nullable=True)
    country = Column(String(100), nullable=True)
    payment_terms_days = Column(Integer, default=30, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)
    
    product_suppliers = relationship("ProductSupplier", back_populates="supplier")
    inbound_shipments = relationship("InboundShipment", back_populates="supplier")
    
    __table_args__ = (
        Index("ix_suppliers_is_active", "is_active"),
        Index("ix_suppliers_country", "country"),
        Index("ix_suppliers_city", "city"),
    )


class ProductSupplier(Base):
    __tablename__ = "product_suppliers"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    product_id = Column(UUID(as_uuid=False), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    supplier_id = Column(UUID(as_uuid=False), ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False)
    standard_lead_time_days = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    
    product = relationship("Product", back_populates="product_suppliers")
    supplier = relationship("Supplier", back_populates="product_suppliers")
    
    __table_args__ = (
        Index("ix_product_suppliers_product_id", "product_id"),
        Index("ix_product_suppliers_supplier_id", "supplier_id"),
        Index("uq_product_suppliers_product_id_supplier_id", "product_id", "supplier_id", unique=True),
    )


class InboundShipment(Base):
    __tablename__ = "inbound_shipments"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    shipment_number = Column(String(50), unique=True, nullable=False)
    supplier_id = Column(UUID(as_uuid=False), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True)
    shipment_date = Column(Date, nullable=False)
    estimated_arrival_date = Column(Date, nullable=True)
    actual_arrival_date = Column(Date, nullable=True)
    bill_of_lading_number = Column(String(100), nullable=True)
    shipping_container_number = Column(String(100), nullable=True)
    invoice_number = Column(String(100), nullable=True)
    shipment_status = Column(String(50), default="in_transit", nullable=False)
    total_items_shipped = Column(Integer, nullable=True)
    total_cartons = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    created_by = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)
    attachment_id = Column(UUID(as_uuid=False), ForeignKey("attachments.id", ondelete="SET NULL"), nullable=True)
    synced_to_excel = Column(Boolean, default=False, nullable=False)
    last_synced_to_excel = Column(DateTime(timezone=False), nullable=True)
    
    supplier = relationship("Supplier", back_populates="inbound_shipments")
    attachment = relationship("Attachment")
    # Order matters: delete allocations before lines (allocations can reference lines)
    spo_allocations = relationship(
        "SPOAllocation",
        back_populates="inbound_shipment",
        cascade="all, delete-orphan",
    )
    shipment_lines = relationship(
        "InboundShipmentLine",
        back_populates="shipment",
        cascade="all, delete-orphan",
    )

    @property
    def display_total_items(self):
        """Total items for display: sum of quantity_shipped from lines when present and > 0, else total_items_shipped."""
        if self.shipment_lines and len(self.shipment_lines) > 0:
            total = sum((line.quantity_shipped or 0) for line in self.shipment_lines)
            if total > 0:
                return total
        return self.total_items_shipped

    @property
    def display_total_cartons(self):
        """Total cartons for display: sum of cartons_count from lines when present and > 0, else total_cartons."""
        if self.shipment_lines and len(self.shipment_lines) > 0:
            total = sum((line.cartons_count or 0) for line in self.shipment_lines)
            if total > 0:
                return total
        return self.total_cartons

    __table_args__ = (
        Index("ix_inbound_shipments_supplier_id", "supplier_id"),
        Index("ix_inbound_shipments_shipment_number", "shipment_number"),
        Index("ix_inbound_shipments_shipment_status", "shipment_status"),
    )


class InboundShipmentLine(Base):
    __tablename__ = "inbound_shipment_lines"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    shipment_id = Column(UUID(as_uuid=False), ForeignKey("inbound_shipments.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(UUID(as_uuid=False), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    quantity_shipped = Column(Integer, nullable=False)
    uom_id = Column(UUID(as_uuid=False), ForeignKey("units_of_measure.id", ondelete="SET NULL"), nullable=True)
    batch_number = Column(String(100), nullable=True)
    serial_number_range_from = Column(String(100), nullable=True)
    serial_number_range_to = Column(String(100), nullable=True)
    carton_number = Column(String(50), nullable=True)
    cartons_count = Column(Integer, default=1, nullable=False)
    weight_per_carton = Column(Numeric(10, 2), nullable=True)
    unit_cost = Column(Numeric(12, 2), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    synced_to_excel = Column(Boolean, default=False, nullable=False)
    last_synced_to_excel = Column(DateTime(timezone=False), nullable=True)
    updated_at = Column(DateTime(timezone=False), nullable=True)
    spo_allocated_quantity = Column(Integer, default=0, nullable=False)
    quantity_received = Column(Integer, default=0, nullable=False)
    line_status = Column(String(50), default="in_transit", nullable=False)
    
    shipment = relationship("InboundShipment", back_populates="shipment_lines")
    product = relationship("Product", back_populates="inbound_shipment_lines")
    uom = relationship("UnitOfMeasure", foreign_keys=[uom_id])
    spo_allocations = relationship(
        "SPOAllocation",
        back_populates="inbound_shipment_line",
        cascade="all, delete-orphan",
    )
    
    __table_args__ = (
        Index("ix_inbound_shipment_lines_shipment_id", "shipment_id"),
        Index("ix_inbound_shipment_lines_product_id", "product_id"),
        UniqueConstraint("shipment_id", "product_id", name="uk_inbound_shipment_lines_shipment_product"),
    )


class SPOAllocation(Base):
    __tablename__ = "spo_allocations"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    spo_number = Column(String(50), nullable=True)
    spo_line_number = Column(Integer, nullable=True)
    inbound_shipment_lines_id = Column(UUID(as_uuid=False), ForeignKey("inbound_shipment_lines.id", ondelete="CASCADE"), nullable=True)
    inbound_shipment_id = Column(UUID(as_uuid=False), ForeignKey("inbound_shipments.id", ondelete="CASCADE"), nullable=False)
    warehouse_id = Column(UUID(as_uuid=False), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False)
    storage_zone_id = Column(UUID(as_uuid=False), ForeignKey("storage_zones.id", ondelete="SET NULL"), nullable=True)
    allocated_quantity = Column(Integer, nullable=False)
    uom_id = Column(UUID(as_uuid=False), ForeignKey("units_of_measure.id", ondelete="SET NULL"), nullable=True)
    receipt_status = Column(String(50), default="pending", nullable=False)
    quantity_received = Column(Integer, default=0, nullable=False)
    quantity_rejected = Column(Integer, default=0, nullable=False)
    allocation_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    created_by = Column(String, nullable=True)
    product_id = Column(UUID(as_uuid=False), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    synced_to_excel = Column(Boolean, default=False, nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)
    last_synced_to_excel = Column(DateTime(timezone=False), nullable=True)
    
    inbound_shipment_line = relationship("InboundShipmentLine", back_populates="spo_allocations")
    inbound_shipment = relationship("InboundShipment", back_populates="spo_allocations")
    warehouse = relationship("Warehouse", back_populates="spo_allocations")
    storage_zone = relationship("StorageZone", back_populates="spo_allocations")
    product = relationship("Product", back_populates="spo_allocations")
    uom = relationship("UnitOfMeasure", foreign_keys=[uom_id])
    picking_lines = relationship("PickingLine", back_populates="spo_allocation")
    
    __table_args__ = (
        Index("ix_spo_allocations_inbound_shipment_id", "inbound_shipment_id"),
        Index("ix_spo_allocations_warehouse_id", "warehouse_id"),
        Index("ix_spo_allocations_product_id", "product_id"),
        UniqueConstraint("spo_number", "product_id", "warehouse_id", name="uk_spo_allocations_spo_number_product_warehouse"),
    )


class PickingHeader(Base):
    __tablename__ = "picking_headers"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    picking_number = Column(String(50), unique=True, nullable=False)
    spo_number = Column(String(50), nullable=True)
    picking_type = Column(String(50), nullable=False)
    source_entity_type = Column(String(50), nullable=True)
    source_entity_id = Column(String, nullable=True)
    picking_date = Column(Date, server_default=func.current_date(), nullable=False)
    picked_by_user_id = Column(String, nullable=True)
    inspection_status = Column(String(50), default="pending", nullable=False)
    quality_remarks = Column(Text, nullable=True)
    inspected_by_user_id = Column(String, nullable=True)
    inspection_date = Column(DateTime(timezone=False), nullable=True)
    picking_status = Column(String(50), default="draft", nullable=False)
    total_items_picked = Column(Integer, nullable=True)
    total_items_discrepancy = Column(Integer, nullable=True)
    total_cost = Column(Numeric(15, 2), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    picking_lines = relationship("PickingLine", back_populates="picking_header")
    
    __table_args__ = (
        Index("ix_picking_headers_picking_type", "picking_type"),
        Index("ix_picking_headers_picking_number", "picking_number"),
        Index("ix_picking_headers_picking_status", "picking_status"),
        Index("ix_picking_headers_spo_number", "spo_number"),
    )


class PickingLine(Base):
    __tablename__ = "picking_lines"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    picking_header_id = Column(UUID(as_uuid=False), ForeignKey("picking_headers.id", ondelete="CASCADE"), nullable=False)
    spo_allocation_id = Column(UUID(as_uuid=False), ForeignKey("spo_allocations.id", ondelete="SET NULL"), nullable=True)
    product_id = Column(UUID(as_uuid=False), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    quantity_expected = Column(Integer, nullable=False)
    quantity_picked = Column(Integer, nullable=False)
    quantity_discrepancy = Column(Integer, Computed("(quantity_expected - quantity_picked)"), nullable=False)
    uom_id = Column(UUID(as_uuid=False), ForeignKey("units_of_measure.id", ondelete="SET NULL"), nullable=True)
    picked_condition = Column(String(50), default="good", nullable=False)
    condition_remarks = Column(Text, nullable=True)
    batch_number_picked = Column(String(100), nullable=True)
    expiry_date = Column(Date, nullable=True)
    unit_cost = Column(Numeric(12, 2), nullable=True)
    line_total = Column(Numeric(15, 2), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    source_warehouse_id = Column(UUID(as_uuid=False), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=True)
    destination_warehouse_id = Column(UUID(as_uuid=False), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=True)
    synced_to_excel = Column(Boolean, default=False, nullable=False)
    last_synced_to_excel = Column(DateTime(timezone=False), nullable=True)
    updated_at = Column(DateTime(timezone=False), nullable=True)
    
    picking_header = relationship("PickingHeader", back_populates="picking_lines")
    spo_allocation = relationship("SPOAllocation", back_populates="picking_lines")
    product = relationship("Product", back_populates="picking_lines")
    uom = relationship("UnitOfMeasure", foreign_keys=[uom_id])
    source_warehouse = relationship("Warehouse", foreign_keys=[source_warehouse_id], back_populates="source_picking_lines")
    destination_warehouse = relationship("Warehouse", foreign_keys=[destination_warehouse_id], back_populates="destination_picking_lines")
    
    __table_args__ = (
        Index("ix_picking_lines_picking_header_id", "picking_header_id"),
        Index("ix_picking_lines_product_id", "product_id"),
        Index("ix_picking_lines_spo_allocation_id", "spo_allocation_id"),
    )


class StockInquiry(Base):
    """Stock inquiry model. Set __audit_track__ = True for automatic audit logging of changes."""
    __tablename__ = "stock_inquiries"
    __audit_track__ = True
    __audit_entity_type__ = "stock_inquiry"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    salesperson = Column(Text, nullable=True)
    product_code = Column(Text, nullable=True)
    item_description = Column(Text, nullable=True)
    project_customer = Column(Text, nullable=True)
    project_name = Column(Text, nullable=True)
    quantity = Column(Text, nullable=True)
    delivery_date = Column(Text, nullable=True)
    remark = Column(Text, nullable=True)
    additional_remark = Column(Text, nullable=True)
    purchasing_response = Column(Text, nullable=True)
    contact_id = Column(Text, nullable=True)
    space_id = Column(Text, nullable=True)
    respond_inbox_url = Column(Text, nullable=True)
    status = Column(String(50), default="new", nullable=False)
    last_responded_by = Column(Text, nullable=True)
    last_responded_at = Column(DateTime(timezone=False), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    rejected_at = Column(DateTime(timezone=False), nullable=True)
    rejected_by = Column(Text, nullable=True)
    rejected_from = Column(String(50), nullable=True)  # pending_project_sales | pending_purchasing; used on reopen
    reopen_reason = Column(Text, nullable=True)
    reopened_at = Column(DateTime(timezone=False), nullable=True)
    reopened_by = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=True)

    __table_args__ = (
        Index("ix_stock_inquiries_product_code", "product_code"),
        Index("ix_stock_inquiries_delivery_date", "delivery_date"),
        Index("ix_stock_inquiries_created_at", "created_at"),
    )


class PurchaseRequestHeader(Base):
    """Purchase request / sponsorship form header. Set __audit_track__ = True for automatic audit logging."""
    __tablename__ = "purchase_requests"
    __audit_track__ = True
    __audit_entity_type__ = "purchase_request"  # API uses this entity_type for both PR and sponsorship

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    request_type = Column(String(50), nullable=False)  # purchase_request | sponsorship_form
    request_number = Column(String(50), nullable=True)
    request_date = Column(Date, nullable=True)
    customer_name = Column(Text, nullable=True)
    project_title = Column(Text, nullable=True)
    purpose = Column(Text, nullable=True)
    delivery_address = Column(Text, nullable=True)  # sponsorship form
    total_project_value = Column(Numeric(15, 2), nullable=True)  # sponsorship form (numeric)
    total_project_value_text = Column(Text, nullable=True)  # descriptive e.g. "BULK ORDER EST RM1.6MIL"
    sponsor_subject = Column(Text, nullable=True)  # sponsorship: showroom/mockup/others
    expected_delivery_date = Column(Date, nullable=True)
    expected_po_date = Column(Date, nullable=True)
    expected_po_date_text = Column(Text, nullable=True)
    requested_by = Column(Text, nullable=True)
    requested_at = Column(Date, nullable=True)
    status = Column(String(50), default="draft", nullable=False)
    source = Column(String(50), default="external", nullable=False)
    external_reference = Column(Text, nullable=True)
    contact_id = Column(Text, nullable=True)
    space_id = Column(Text, nullable=True)
    respond_inbox_url = Column(Text, nullable=True)
    approver_user_id = Column(String(100), nullable=True)
    approver_email = Column(String(255), nullable=True)
    requested_approval_by_user_id = Column(String(100), nullable=True)  # user who set to pending / sent approval link
    approval_status = Column(String(50), nullable=True)  # pending | approved | rejected
    approved_at = Column(DateTime(timezone=False), nullable=True)
    approved_by = Column(Text, nullable=True)
    approval_signature_ref = Column(Text, nullable=True)
    approval_comments = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)

    lines = relationship(
        "PurchaseRequestLine",
        back_populates="purchase_request",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_purchase_requests_request_type", "request_type"),
        Index("ix_purchase_requests_request_date", "request_date"),
        Index("ix_purchase_requests_customer_name", "customer_name"),
    )


class PurchaseRequestLine(Base):
    __tablename__ = "purchase_request_lines"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    purchase_request_id = Column(
        UUID(as_uuid=False),
        ForeignKey("purchase_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    item_code = Column(Text, nullable=True)
    quantity = Column(Numeric(15, 2), nullable=True)
    remark = Column(Text, nullable=True)
    unit_price = Column(Numeric(15, 2), nullable=True)  # sponsorship form line
    total = Column(Numeric(15, 2), nullable=True)  # sponsorship form line (qty * unit_price)
    sort_order = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    purchase_request = relationship("PurchaseRequestHeader", back_populates="lines")

    __table_args__ = (
        Index("ix_purchase_request_lines_purchase_request_id", "purchase_request_id"),
    )


class ApprovalToken(Base):
    """One-time token for public approval/sign links (no login)."""
    __tablename__ = "approval_tokens"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String(100), nullable=False)
    token = Column(String(255), unique=True, nullable=False, index=True)
    expires = Column(DateTime(timezone=False), nullable=False)
    used_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_approval_tokens_entity_type_entity_id", "entity_type", "entity_id"),
    )


class ViewToken(Base):
    """Reusable token for public view links (no login, read-only). One per purchase request."""
    __tablename__ = "view_tokens"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String(100), nullable=False)
    token = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_view_tokens_entity_type_entity_id", "entity_type", "entity_id", unique=True),
    )
