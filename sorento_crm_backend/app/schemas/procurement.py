"""Procurement schemas."""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal
import uuid
from app.schemas.resources import AttachmentTypeSimple


class SupplierBase(BaseModel):
    supplier_code: str
    supplier_name: str
    contact_name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    website: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    payment_terms_days: Optional[int] = 30
    is_active: bool = True


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    supplier_name: Optional[str] = None
    contact_name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    website: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    payment_terms_days: Optional[int] = None
    is_active: Optional[bool] = None


class SupplierSimple(BaseModel):
    id: str
    supplier_code: str
    supplier_name: str
    
    class Config:
        from_attributes = True


class SupplierResponse(SupplierBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class ProductSimple(BaseModel):
    """Simple product reference."""
    id: str
    product_code: str
    product_name: str
    
    class Config:
        from_attributes = True


class PackingListLineSPOSimple(BaseModel):
    id: str
    spo_number: Optional[str] = None
    allocated_quantity: Optional[int] = None
    receipt_status: Optional[str] = None

    class Config:
        from_attributes = True


class PackingListLineGRNSimple(BaseModel):
    id: str
    picking_number: Optional[str] = None
    spo_number: Optional[str] = None
    picking_status: Optional[str] = None
    picking_date: Optional[date] = None

    class Config:
        from_attributes = True


class ProductSupplierBase(BaseModel):
    product_id: str
    supplier_id: str
    standard_lead_time_days: Optional[int] = None


class ProductSupplierCreate(ProductSupplierBase):
    pass


class ProductSupplierUpdate(BaseModel):
    standard_lead_time_days: Optional[int] = None


class ProductSupplierResponse(ProductSupplierBase):
    id: str
    created_at: datetime
    product: Optional[ProductSimple] = None
    supplier: Optional[SupplierSimple] = None
    
    class Config:
        from_attributes = True


class InboundShipmentLineBase(BaseModel):
    product_id: str
    quantity_shipped: int
    uom_id: Optional[str] = None
    batch_number: Optional[str] = None
    serial_number_range_from: Optional[str] = None
    serial_number_range_to: Optional[str] = None
    carton_number: Optional[str] = None
    cartons_count: int = 1
    weight_per_carton: Optional[Decimal] = None
    unit_cost: Optional[Decimal] = None


class InboundShipmentLineCreate(InboundShipmentLineBase):
    pass


class InboundShipmentLineResponse(InboundShipmentLineBase):
    id: str
    shipment_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    product: Optional[ProductSimple] = None
    spo_allocated_quantity: Optional[int] = None  # Total SPO allocated qty for this product on this shipment (all warehouses)
    quantity_received: Optional[int] = None  # Sum of quantity_received from SPO allocations for this line
    line_status: Optional[str] = None  # Stored in DB: in_transit, allocated, partially_allocated, received, partially_received (for n8n/API)
    related_spo_allocations: Optional[List[PackingListLineSPOSimple]] = None
    related_grns: Optional[List[PackingListLineGRNSimple]] = None

    class Config:
        from_attributes = True


class InboundShipmentBase(BaseModel):
    shipment_number: str
    supplier_id: Optional[str] = None
    shipment_date: date
    estimated_arrival_date: Optional[date] = None
    actual_arrival_date: Optional[date] = None
    bill_of_lading_number: Optional[str] = None
    shipping_container_number: Optional[str] = None
    invoice_number: Optional[str] = None
    shipment_status: str = "in_transit"
    total_items_shipped: Optional[int] = None
    total_cartons: Optional[int] = None
    notes: Optional[str] = None
    attachment_id: Optional[str] = None


class InboundShipmentCreate(InboundShipmentBase):
    shipment_lines: Optional[List[InboundShipmentLineCreate]] = None


class InboundShipmentUpdate(BaseModel):
    supplier_id: Optional[str] = None
    shipment_date: Optional[date] = None
    estimated_arrival_date: Optional[date] = None
    actual_arrival_date: Optional[date] = None
    bill_of_lading_number: Optional[str] = None
    shipping_container_number: Optional[str] = None
    invoice_number: Optional[str] = None
    shipment_status: Optional[str] = None
    total_items_shipped: Optional[int] = None
    total_cartons: Optional[int] = None
    notes: Optional[str] = None
    attachment_id: Optional[str] = None
    shipment_lines: Optional[List[InboundShipmentLineCreate]] = None


class AttachmentSimple(BaseModel):
    """Simple attachment reference for InboundShipment."""
    id: str
    original_filename: str
    stored_filename: str
    file_path: str
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    attachment_type: Optional[AttachmentTypeSimple] = None
    
    class Config:
        from_attributes = True


class InboundShipmentResponse(InboundShipmentBase):
    id: str
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    synced_to_excel: bool = False
    last_synced_to_excel: Optional[datetime] = None
    supplier: Optional[SupplierSimple] = None
    attachment: Optional[AttachmentSimple] = None
    shipment_lines: Optional[List[InboundShipmentLineResponse]] = None
    lines_count: Optional[int] = 0
    spo_allocations_count: Optional[int] = 0
    display_total_items: Optional[int] = None
    display_total_cartons: Optional[int] = None
    
    @field_validator('created_by', mode='before')
    @classmethod
    def convert_created_by_uuid(cls, v):
        """Convert UUID objects to strings for created_by."""
        if v is None:
            return None
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v else None
    
    class Config:
        from_attributes = True


class InboundShipmentListItemResponse(InboundShipmentBase):
    id: str
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    synced_to_excel: bool = False
    last_synced_to_excel: Optional[datetime] = None
    supplier: Optional[SupplierSimple] = None
    lines_count: Optional[int] = 0
    spo_allocations_count: Optional[int] = 0
    display_total_items: Optional[int] = None
    display_total_cartons: Optional[int] = None

    @field_validator('created_by', mode='before')
    @classmethod
    def convert_created_by_uuid(cls, v):
        """Convert UUID objects to strings for created_by."""
        if v is None:
            return None
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v else None

    class Config:
        from_attributes = True


class SPOAllocationBase(BaseModel):
    spo_number: Optional[str] = None
    spo_line_number: Optional[int] = None
    inbound_shipment_id: str
    warehouse_id: str
    storage_zone_id: Optional[str] = None
    allocated_quantity: int
    uom_id: Optional[str] = None
    receipt_status: str = "pending"
    quantity_received: int = 0
    quantity_rejected: int = 0
    allocation_notes: Optional[str] = None
    product_id: str


class SPOAllocationCreate(SPOAllocationBase):
    pass


class SPOAllocationUpdate(BaseModel):
    spo_number: Optional[str] = None
    inbound_shipment_id: Optional[str] = None
    warehouse_id: Optional[str] = None
    product_id: Optional[str] = None
    storage_zone_id: Optional[str] = None
    allocated_quantity: Optional[int] = None
    receipt_status: Optional[str] = None
    quantity_received: Optional[int] = None
    quantity_rejected: Optional[int] = None
    allocation_notes: Optional[str] = None


class BulkDeleteSPOAllocationsRequest(BaseModel):
    ids: List[str]


class BulkDeletePurchaseRequestsRequest(BaseModel):
    """Request body for bulk delete of purchase requests / sponsorship forms."""
    ids: List[str]


class InboundShipmentSimple(BaseModel):
    id: str
    shipment_number: str
    shipping_container_number: Optional[str] = None

    class Config:
        from_attributes = True


class WarehouseSimple(BaseModel):
    id: str
    warehouse_code: str
    warehouse_name: str
    
    class Config:
        from_attributes = True


class SPOAllocationSimple(BaseModel):
    """Minimal SPO allocation for embedding in picking line responses."""
    id: str
    spo_number: Optional[str] = None
    spo_line_number: Optional[int] = None

    class Config:
        from_attributes = True


class LinkedGRNSimple(BaseModel):
    """Minimal GRN info for SPO → GRN navigation."""
    id: str
    picking_number: Optional[str] = None
    picking_status: Optional[str] = None
    picking_date: Optional[date] = None

    class Config:
        from_attributes = True


class SPOAllocationResponse(SPOAllocationBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None
    synced_to_excel: bool = False
    last_synced_to_excel: Optional[datetime] = None
    inbound_shipment: Optional[InboundShipmentSimple] = None
    warehouse: Optional[WarehouseSimple] = None
    product: Optional[ProductSimple] = None
    grn_lines_count: Optional[int] = 0
    linked_grns: Optional[List["LinkedGRNSimple"]] = None
    
    @field_validator('created_by', mode='before')
    @classmethod
    def convert_created_by_uuid(cls, v):
        """Convert UUID objects to strings for created_by."""
        if v is None:
            return None
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v else None
    
    class Config:
        from_attributes = True


class ShipmentAllocationSummaryGroup(BaseModel):
    """Inbound shipment summary for grouped shipment search."""
    inbound_shipment: InboundShipmentSimple
    matched_spo_allocations_count: int = 0
    shipment_lines_count: int = 0


class SPOAllocationWithShippedResponse(SPOAllocationResponse):
    """SPO allocation with quantity_shipped from packing list (shipment lines)."""
    quantity_shipped: Optional[int] = None


class SPOWithAllocationsGroup(BaseModel):
    """SPO number with its allocations (grouped list view by SPO)."""
    spo_number: str
    spo_allocations: List[SPOAllocationWithShippedResponse]


class PickingLineBase(BaseModel):
    spo_allocation_id: Optional[str] = None
    product_id: str
    quantity_expected: int
    quantity_picked: int
    # quantity_discrepancy is a DB-generated column; do not include in create
    uom_id: Optional[str] = None
    picked_condition: str = "good"
    condition_remarks: Optional[str] = None
    batch_number_picked: Optional[str] = None
    expiry_date: Optional[date] = None
    unit_cost: Optional[Decimal] = None
    line_total: Optional[Decimal] = None
    source_warehouse_id: Optional[str] = None
    destination_warehouse_id: Optional[str] = None


class PickingLineCreate(PickingLineBase):
    pass


class PickingLineResponse(PickingLineBase):
    id: str
    picking_header_id: str
    quantity_discrepancy: int = 0  # from DB generated column
    created_at: datetime
    updated_at: Optional[datetime] = None
    product: Optional[ProductSimple] = None
    spo_allocation: Optional[SPOAllocationSimple] = None
    source_warehouse: Optional[WarehouseSimple] = None
    destination_warehouse: Optional[WarehouseSimple] = None

    class Config:
        from_attributes = True


class PickingHeaderBase(BaseModel):
    picking_number: str
    spo_number: Optional[str] = None
    picking_type: str
    source_entity_type: Optional[str] = None
    source_entity_id: Optional[str] = None
    picking_date: date
    picked_by_user_id: Optional[str] = None
    inspection_status: str = "pending"
    quality_remarks: Optional[str] = None
    inspected_by_user_id: Optional[str] = None
    inspection_date: Optional[datetime] = None
    picking_status: str = "draft"
    total_items_picked: Optional[int] = None
    total_items_discrepancy: Optional[int] = None
    total_cost: Optional[Decimal] = None
    notes: Optional[str] = None

    @field_validator("picked_by_user_id", "inspected_by_user_id", mode="before")
    @classmethod
    def coerce_user_id_to_str(cls, v: object) -> Optional[str]:
        if v is None:
            return None
        return str(v)


class PickingHeaderCreate(PickingHeaderBase):
    picking_lines: Optional[List[PickingLineCreate]] = None


class PickingHeaderUpdate(BaseModel):
    spo_number: Optional[str] = None
    picking_date: Optional[date] = None
    picked_by_user_id: Optional[str] = None
    inspection_status: Optional[str] = None
    quality_remarks: Optional[str] = None
    inspected_by_user_id: Optional[str] = None
    inspection_date: Optional[datetime] = None
    picking_status: Optional[str] = None
    total_items_picked: Optional[int] = None
    total_items_discrepancy: Optional[int] = None
    total_cost: Optional[Decimal] = None
    notes: Optional[str] = None
    picking_lines: Optional[List[PickingLineCreate]] = None


class PickingHeaderResponse(PickingHeaderBase):
    id: str
    created_at: datetime
    updated_at: datetime
    picking_lines: Optional[List[PickingLineResponse]] = None
    lines_count: Optional[int] = 0
    
    class Config:
        from_attributes = True


def _parse_date_string(v: Optional[str | date]) -> Optional[date]:
    """Parse date from string; accept dd/mm/yyyy, dd-mm-yyyy, yyyy-mm-dd."""
    if v is None:
        return None
    if isinstance(v, date):
        return v
    if not isinstance(v, str):
        return None
    s = v.strip()
    if not s:
        return None
    from datetime import datetime as dt
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return dt.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _coerce_numeric_or_text_to_string(v: object) -> Optional[str]:
    """Accept numeric/text values and normalize as trimmed string."""
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s if s else None
    if isinstance(v, (int, float, Decimal)):
        return str(v)
    return None


def _coerce_scope_id_to_string(v: object) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s if s else None
    if isinstance(v, (int, float, Decimal)):
        return str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)
    s = str(v).strip()
    return s if s else None


class StockInquiryBase(BaseModel):
    salesperson: Optional[str] = None
    product_code: Optional[str] = None
    item_description: Optional[str] = None
    project_customer: Optional[str] = None
    project_name: Optional[str] = None
    quantity: Optional[str] = None
    delivery_date: Optional[str] = None
    remark: Optional[str] = None
    additional_remark: Optional[str] = None
    purchasing_response: Optional[str] = None
    contact_id: Optional[str] = None
    space_id: Optional[str] = None
    status: Optional[str] = None
    last_responded_by: Optional[str] = None
    last_responded_at: Optional[datetime] = None

    @field_validator("quantity", mode="before")
    @classmethod
    def coerce_quantity_to_string(cls, v: object) -> Optional[str]:
        return _coerce_numeric_or_text_to_string(v)

    @field_validator("contact_id", "space_id", mode="before")
    @classmethod
    def coerce_scope_ids(cls, v: object) -> Optional[str]:
        return _coerce_scope_id_to_string(v)


class StockInquiryCreate(StockInquiryBase):
    """Create payload. Optional ``inquiry_number`` is used only for lookup: if a rejected inquiry
    with that number exists, that row is updated instead of inserting a new one."""

    inquiry_number: Optional[str] = Field(
        default=None,
        description="When set, if a rejected inquiry with this number exists it is updated with the rest of the payload and status; otherwise 409 if the number exists and is not rejected.",
    )
    user_confirmed: Optional[bool] = Field(
        default=None,
        description=(
            "External/MCP submissions only: must be true after the end user explicitly confirms "
            "the final summary (e.g. OK, YES, CONFIRM). Not required for in-app CRM creates."
        ),
    )


class StockInquiryUpdate(BaseModel):
    salesperson: Optional[str] = None
    product_code: Optional[str] = None
    item_description: Optional[str] = None
    project_customer: Optional[str] = None
    project_name: Optional[str] = None
    quantity: Optional[str] = None
    delivery_date: Optional[str] = None
    remark: Optional[str] = None
    additional_remark: Optional[str] = None
    purchasing_response: Optional[str] = None
    contact_id: Optional[str] = None
    space_id: Optional[str] = None
    status: Optional[str] = None
    last_responded_by: Optional[str] = None
    last_responded_at: Optional[datetime] = None

    @field_validator("quantity", mode="before")
    @classmethod
    def coerce_quantity_to_string(cls, v: object) -> Optional[str]:
        return _coerce_numeric_or_text_to_string(v)

    @field_validator("contact_id", "space_id", mode="before")
    @classmethod
    def coerce_scope_ids(cls, v: object) -> Optional[str]:
        return _coerce_scope_id_to_string(v)


class StockInquiryAttachmentResponse(BaseModel):
    id: str
    inquiry_id: str
    attachment_id: Optional[str] = None
    file_name: Optional[str] = None
    original_filename: Optional[str] = None
    file_url: Optional[str] = None
    file_size_bytes: Optional[int] = None
    uploaded_at: Optional[datetime] = None
    link_type: Optional[str] = None


class StockInquiryRejectReopenRequest(BaseModel):
    reason: Optional[str] = Field(
        default=None,
        description="Required (non-empty) for project-sales-reject and purchasing-reject; optional for reopen.",
    )


class StockInquiryResponse(StockInquiryBase):
    id: str
    system_id: Optional[str] = None
    form_type: Optional[str] = None
    inquiry_number: Optional[str] = None
    view_url: Optional[str] = None
    respond_inbox_url: Optional[str] = None
    status: Optional[str] = None
    last_responded_by: Optional[str] = None
    last_responded_by_name: Optional[str] = None
    last_responded_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    rejected_at: Optional[datetime] = None
    rejected_by: Optional[str] = None
    rejected_by_name: Optional[str] = None
    rejected_from: Optional[str] = None
    reopen_reason: Optional[str] = None
    reopened_at: Optional[datetime] = None
    reopened_by: Optional[str] = None
    reopened_by_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    attachments: Optional[List[StockInquiryAttachmentResponse]] = []

    class Config:
        from_attributes = True


# Purchase Request / Sponsorship Form
class PurchaseRequestLineBase(BaseModel):
    item_code: Optional[str] = None
    quantity: Optional[Decimal] = None
    remark: Optional[str] = None
    unit_price: Optional[Decimal] = None  # sponsorship form line
    total: Optional[Decimal] = None  # sponsorship form line (qty * unit_price)


class PurchaseRequestLineCreate(PurchaseRequestLineBase):
    pass


class PurchaseRequestLineResponse(PurchaseRequestLineBase):
    id: str
    purchase_request_id: str
    sort_order: Optional[int] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PurchaseRequestHeaderBase(BaseModel):
    request_type: str  # purchase_request | sponsorship_form
    request_number: Optional[str] = None  # User-assignable form number (e.g. PR-2026-001)
    request_date: Optional[date] = None
    customer_name: Optional[str] = None
    project_title: Optional[str] = None
    purpose: Optional[str] = None
    delivery_address: Optional[str] = None  # sponsorship form
    total_project_value: Optional[Decimal] = None  # sponsorship form
    total_project_value_text: Optional[str] = None  # sponsorship form (e.g. 800K)
    sponsor_subject: Optional[str] = None  # sponsorship: showroom/mockup/others
    expected_delivery_date: Optional[date] = None
    expected_po_date: Optional[date] = None
    expected_po_date_text: Optional[str] = None
    requested_by: Optional[str] = None
    requested_at: Optional[date] = None
    status: Optional[str] = None
    source: Optional[str] = None
    external_reference: Optional[str] = None
    contact_id: Optional[str] = None
    space_id: Optional[str] = None
    approver_user_id: Optional[str] = None
    approver_email: Optional[str] = None
    approval_status: Optional[str] = None  # pending | approved | rejected
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    approval_signature_ref: Optional[str] = None
    approval_comments: Optional[str] = None


class PurchaseRequestHeaderCreate(PurchaseRequestHeaderBase):
    products: Optional[List[PurchaseRequestLineCreate]] = []

    @field_validator("request_type")
    @classmethod
    def validate_request_type(cls, v: Optional[str]) -> Optional[str]:
        if v and v.strip() not in ("purchase_request", "sponsorship_form"):
            raise ValueError("request_type must be purchase_request or sponsorship_form")
        return v.strip() if v else None

    @field_validator("request_date", "expected_delivery_date", "expected_po_date", "requested_at", mode="before")
    @classmethod
    def parse_date(cls, v: Optional[str | date]) -> Optional[date]:
        return _parse_date_string(v)

    @field_validator("contact_id", "space_id", mode="before")
    @classmethod
    def coerce_scope_ids(cls, v: object) -> Optional[str]:
        return _coerce_scope_id_to_string(v)


class PurchaseRequestHeaderUpdate(BaseModel):
    request_type: Optional[str] = None
    request_number: Optional[str] = None
    request_date: Optional[date] = None
    customer_name: Optional[str] = None
    project_title: Optional[str] = None
    purpose: Optional[str] = None
    delivery_address: Optional[str] = None
    total_project_value: Optional[Decimal] = None
    total_project_value_text: Optional[str] = None
    sponsor_subject: Optional[str] = None
    expected_delivery_date: Optional[date] = None
    expected_po_date: Optional[date] = None
    expected_po_date_text: Optional[str] = None
    requested_by: Optional[str] = None
    requested_at: Optional[date] = None
    status: Optional[str] = None
    contact_id: Optional[str] = None
    space_id: Optional[str] = None
    approver_user_id: Optional[str] = None
    approver_email: Optional[str] = None
    products: Optional[List[PurchaseRequestLineCreate]] = None

    @field_validator("request_type", mode="before")
    @classmethod
    def validate_request_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        s = v.strip() if isinstance(v, str) else v
        if s not in ("purchase_request", "sponsorship_form"):
            raise ValueError("request_type must be purchase_request or sponsorship_form")
        return s

    @field_validator("request_date", "expected_delivery_date", "expected_po_date", "requested_at", mode="before")
    @classmethod
    def parse_date(cls, v: Optional[str | date]) -> Optional[date]:
        return _parse_date_string(v)

    @field_validator("contact_id", "space_id", mode="before")
    @classmethod
    def coerce_scope_ids(cls, v: object) -> Optional[str]:
        return _coerce_scope_id_to_string(v)


class PurchaseRequestUpdateAndReply(PurchaseRequestHeaderUpdate):
    """Update purchase request and send a reply to the conversation via Respond.io.
    Either reply_message or request_number must be set (form number is replied as assigned)."""
    reply_message: Optional[str] = None


class PurchaseRequestHeaderListResponse(PurchaseRequestHeaderBase):
    """Response for list endpoint (no lines)."""
    id: str
    request_number: Optional[str] = None
    view_url: Optional[str] = None
    respond_inbox_url: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PurchaseRequestAttachmentResponse(BaseModel):
    id: str
    purchase_request_id: str
    attachment_id: Optional[str] = None
    file_name: Optional[str] = None
    original_filename: Optional[str] = None
    file_url: Optional[str] = None
    file_size_bytes: Optional[int] = None
    uploaded_at: Optional[datetime] = None
    link_type: Optional[str] = None


class PurchaseRequestAttachmentLinkRequest(BaseModel):
    attachment_id: str


class PurchaseRequestHeaderResponse(PurchaseRequestHeaderBase):
    id: str
    request_number: Optional[str] = None
    view_url: Optional[str] = None
    respond_inbox_url: Optional[str] = None
    approver_display_name: Optional[str] = None  # Resolved from User when approver_user_id is set
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    lines: Optional[List[PurchaseRequestLineResponse]] = []
    attachments: Optional[List[PurchaseRequestAttachmentResponse]] = []
    grand_total: Optional[Decimal] = None  # Sum of line totals; set for sponsorship_form

    class Config:
        from_attributes = True


class SendApprovalLinkRequest(BaseModel):
    """Request to create approval token and get public link; optionally send link by email to approver."""
    approver_email: Optional[str] = None
    approver_user_id: Optional[str] = None
    expires_hours: Optional[int] = 24
    send_email: Optional[bool] = False
    base_url: Optional[str] = None  # Frontend origin (e.g. https://app.example.com) so approval link in email is absolute


class SendApprovalLinkResponse(BaseModel):
    approval_url: str
    expires_at: datetime
    token_id: str
    email_sent: Optional[bool] = None
    email_error: Optional[str] = None


class ViewLinkRequest(BaseModel):
    """Optional base URL to build full view URL (e.g. frontend origin)."""
    base_url: Optional[str] = None


class ViewLinkResponse(BaseModel):
    view_token: str
    view_url: str  # Full URL if base_url was provided, else relative path
    portal_url: Optional[str] = None  # Landing for the contact's submission portal (mintable when contact_id+space_id known)


class PublicApprovalLineSummary(BaseModel):
    """Single line for public approval/view. Remark for purchase_request; unit_price/total for sponsorship_form."""
    item_code: Optional[str] = None
    quantity: Optional[float] = None  # from Numeric in DB
    remark: Optional[str] = None
    unit_price: Optional[Decimal] = None  # sponsorship form
    total: Optional[Decimal] = None  # sponsorship form
    sort_order: Optional[int] = None

    class Config:
        from_attributes = True


class PublicApprovalSummaryResponse(BaseModel):
    """Summary of request for public approval page (no sensitive data)."""
    entity_type: str
    entity_id: str
    request_number: Optional[str] = None
    request_type: str
    customer_name: Optional[str] = None
    project_title: Optional[str] = None
    purpose: Optional[str] = None
    delivery_address: Optional[str] = None  # sponsorship form
    total_project_value: Optional[Decimal] = None  # sponsorship form (numeric)
    total_project_value_text: Optional[str] = None  # sponsorship form (descriptive)
    sponsor_subject: Optional[str] = None  # sponsorship form
    requested_by: Optional[str] = None
    request_date: Optional[date] = None
    created_at: Optional[datetime] = None
    expected_delivery_date: Optional[date] = None
    expected_po_date: Optional[date] = None
    expected_po_date_text: Optional[str] = None
    expires_at: Optional[datetime] = None  # None when used for view (no expiry)
    lines: Optional[List[PublicApprovalLineSummary]] = []
    grand_total: Optional[Decimal] = None  # sponsorship form: sum of line totals
    approval_status: Optional[str] = None  # draft | pending | approved | rejected
    approver_display_name: Optional[str] = None  # Prefill "Your name" when approver is system user
    approver_email: Optional[str] = None  # Prefill fallback when no display name
    requested_at: Optional[date] = None  # Date next to Requested by (document footer)
    approved_at: Optional[datetime] = None  # Set when approved or rejected via link
    approved_by: Optional[str] = None  # Approver name/email (same field for approve/reject)
    approval_comments: Optional[str] = None  # Approval notes or rejection reason


class PublicApprovalSubmitRequest(BaseModel):
    action: str  # approved | rejected
    approved_by: Optional[str] = None
    approval_signature_ref: Optional[str] = None
    approval_comments: Optional[str] = Field(
        default=None,
        description="Notes for approval; must be non-empty when action is rejected.",
    )
