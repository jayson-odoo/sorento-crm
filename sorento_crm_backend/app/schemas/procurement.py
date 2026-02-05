"""Procurement schemas."""
from pydantic import BaseModel, field_validator
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

    class Config:
        from_attributes = True


class InboundShipmentBase(BaseModel):
    shipment_number: str
    supplier_id: str
    shipment_date: date
    expected_arrival_date: Optional[date] = None
    actual_arrival_date: Optional[date] = None
    bill_of_lading_number: Optional[str] = None
    shipping_container_number: Optional[str] = None
    invoice_number: Optional[str] = None
    shipment_status: str = "in_transit"
    total_items_shipped: Optional[int] = None
    total_cartons: Optional[int] = None
    notes: Optional[str] = None
    attachment_id: str


class InboundShipmentCreate(InboundShipmentBase):
    shipment_lines: Optional[List[InboundShipmentLineCreate]] = None


class InboundShipmentUpdate(BaseModel):
    shipment_date: Optional[date] = None
    expected_arrival_date: Optional[date] = None
    actual_arrival_date: Optional[date] = None
    bill_of_lading_number: Optional[str] = None
    shipping_container_number: Optional[str] = None
    invoice_number: Optional[str] = None
    shipment_status: Optional[str] = None
    total_items_shipped: Optional[int] = None
    total_cartons: Optional[int] = None
    notes: Optional[str] = None
    attachment_id: Optional[str] = None


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


class SPOAllocationBase(BaseModel):
    spo_number: Optional[str] = None
    spo_line_number: Optional[int] = None
    inbound_shipment_lines_id: Optional[str] = None
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
    storage_zone_id: Optional[str] = None
    allocated_quantity: Optional[int] = None
    receipt_status: Optional[str] = None
    quantity_received: Optional[int] = None
    quantity_rejected: Optional[int] = None
    allocation_notes: Optional[str] = None


class InboundShipmentSimple(BaseModel):
    id: str
    shipment_number: str
    
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


class ShipmentWithAllocationsGroup(BaseModel):
    """Inbound shipment with its SPO allocations for grouped list view."""
    inbound_shipment: InboundShipmentSimple
    spo_allocations: List[SPOAllocationResponse]


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

    class Config:
        from_attributes = True


class PickingHeaderBase(BaseModel):
    picking_number: str
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


class PickingHeaderCreate(PickingHeaderBase):
    picking_lines: Optional[List[PickingLineCreate]] = None


class PickingHeaderUpdate(BaseModel):
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


class StockInquiryBase(BaseModel):
    salesperson: Optional[str] = None
    product_code: Optional[str] = None
    item_description: Optional[str] = None
    project_customer: Optional[str] = None
    project_name: Optional[str] = None
    quantity: Optional[Decimal] = None
    delivery_date: Optional[date] = None
    brand: Optional[str] = None
    additional_remark: Optional[str] = None
    purchasing_response: Optional[str] = None

    @field_validator("delivery_date", mode="before")
    @classmethod
    def parse_delivery_date(cls, v: Optional[str | date]) -> Optional[date]:
        return _parse_date_string(v)


class StockInquiryCreate(StockInquiryBase):
    pass


class StockInquiryUpdate(BaseModel):
    salesperson: Optional[str] = None
    product_code: Optional[str] = None
    item_description: Optional[str] = None
    project_customer: Optional[str] = None
    project_name: Optional[str] = None
    quantity: Optional[Decimal] = None
    delivery_date: Optional[date] = None
    brand: Optional[str] = None
    additional_remark: Optional[str] = None
    purchasing_response: Optional[str] = None

    @field_validator("delivery_date", mode="before")
    @classmethod
    def parse_delivery_date(cls, v: Optional[str | date]) -> Optional[date]:
        return _parse_date_string(v)


class StockInquiryResponse(StockInquiryBase):
    id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# Purchase Request / Sponsorship Form
class PurchaseRequestLineBase(BaseModel):
    item_code: Optional[str] = None
    quantity: Optional[Decimal] = None
    remark: Optional[str] = None


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
    request_date: Optional[date] = None
    customer_name: Optional[str] = None
    project_title: Optional[str] = None
    purpose: Optional[str] = None
    expected_delivery_date: Optional[date] = None
    expected_po_date: Optional[date] = None
    expected_po_date_text: Optional[str] = None
    requested_by: Optional[str] = None
    requested_at: Optional[date] = None
    status: Optional[str] = None
    source: Optional[str] = None
    external_reference: Optional[str] = None


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


class PurchaseRequestHeaderUpdate(BaseModel):
    request_type: Optional[str] = None
    request_date: Optional[date] = None
    customer_name: Optional[str] = None
    project_title: Optional[str] = None
    purpose: Optional[str] = None
    expected_delivery_date: Optional[date] = None
    expected_po_date: Optional[date] = None
    expected_po_date_text: Optional[str] = None
    requested_by: Optional[str] = None
    requested_at: Optional[date] = None
    status: Optional[str] = None
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


class PurchaseRequestHeaderListResponse(PurchaseRequestHeaderBase):
    """Response for list endpoint (no lines)."""
    id: str
    request_number: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PurchaseRequestHeaderResponse(PurchaseRequestHeaderBase):
    id: str
    request_number: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    lines: Optional[List[PurchaseRequestLineResponse]] = []

    class Config:
        from_attributes = True
