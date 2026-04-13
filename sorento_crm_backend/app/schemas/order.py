"""Order management schemas."""
from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
import uuid


class OrderStatusBase(BaseModel):
    status_code: str
    status_name: str
    description: Optional[str] = None
    sequence: int = 0
    is_final_status: bool = False


class OrderStatusCreate(OrderStatusBase):
    pass


class OrderStatusUpdate(BaseModel):
    status_name: Optional[str] = None
    description: Optional[str] = None
    sequence: Optional[int] = None
    is_final_status: Optional[bool] = None


class OrderStatusResponse(OrderStatusBase):
    id: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class CustomerBase(BaseModel):
    customer_code: str
    customer_name: str
    email: Optional[str] = None
    phone_number: Optional[str] = None
    is_active: bool = True


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    customer_name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    is_active: Optional[bool] = None


class CustomerSimple(BaseModel):
    id: str
    customer_code: str
    customer_name: str
    
    class Config:
        from_attributes = True


class CustomerResponse(CustomerBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class OrderBase(BaseModel):
    order_number: str
    order_date: Optional[datetime] = None
    estimated_delivery_date: Optional[datetime] = None
    actual_delivery_date: Optional[datetime] = None
    customer_id: Optional[str] = None
    order_status_id: Optional[str] = None
    billing_address_id: Optional[str] = None
    shipping_address_id: Optional[str] = None
    created_time: Optional[datetime] = None
    debtor_code: Optional[str] = None
    debtor_name: Optional[str] = None
    agent: Optional[str] = None
    is_cancelled: bool = False
    remarks_cs: Optional[str] = None
    order_type: Optional[str] = None
    delivery_time: Optional[str] = None
    checker: Optional[str] = None
    transporter: Optional[str] = None
    driver_name: Optional[str] = None
    lorry_plate: Optional[str] = None
    customer_ref: Optional[str] = None
    delivery_remarks_cs: Optional[str] = None
    delivery_remarks: Optional[str] = None
    salesman: Optional[str] = None
    trips: Optional[int] = None
    warehouse: Optional[str] = None
    delivery_days: Optional[int] = None
    kpi_warning: bool = False
    subtotal_amount: Decimal = Decimal("0")
    discount_amount: Decimal = Decimal("0")
    tax_amount: Decimal = Decimal("0")
    total_amount: Decimal = Decimal("0")
    remarks: Optional[str] = None


class OrderCreate(OrderBase):
    pass


class OrderUpdate(BaseModel):
    order_date: Optional[datetime] = None
    estimated_delivery_date: Optional[datetime] = None
    actual_delivery_date: Optional[datetime] = None
    customer_id: Optional[str] = None
    order_status_id: Optional[str] = None
    billing_address_id: Optional[str] = None
    shipping_address_id: Optional[str] = None
    created_time: Optional[datetime] = None
    debtor_code: Optional[str] = None
    debtor_name: Optional[str] = None
    agent: Optional[str] = None
    is_cancelled: Optional[bool] = None
    remarks_cs: Optional[str] = None
    order_type: Optional[str] = None
    delivery_time: Optional[str] = None
    checker: Optional[str] = None
    transporter: Optional[str] = None
    driver_name: Optional[str] = None
    lorry_plate: Optional[str] = None
    customer_ref: Optional[str] = None
    delivery_remarks_cs: Optional[str] = None
    delivery_remarks: Optional[str] = None
    salesman: Optional[str] = None
    trips: Optional[int] = None
    warehouse: Optional[str] = None
    delivery_days: Optional[int] = None
    kpi_warning: Optional[bool] = None
    subtotal_amount: Optional[Decimal] = None
    discount_amount: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    total_amount: Optional[Decimal] = None
    remarks: Optional[str] = None


class OrderStatusSimple(BaseModel):
    id: str
    status_code: str
    status_name: str
    
    class Config:
        from_attributes = True


class OrderSimpleRef(BaseModel):
    id: str
    order_number: str
    order_date: Optional[datetime] = None
    actual_delivery_date: Optional[datetime] = None
    debtor_name: Optional[str] = None

    class Config:
        from_attributes = True


class OrderResponse(OrderBase):
    id: str
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    synced_to_excel: bool = False
    last_synced_to_excel: Optional[datetime] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    customer: Optional[CustomerSimple] = None
    order_status: Optional[OrderStatusSimple] = None
    lines: Optional[list["OrderLineResponse"]] = []
    
    @field_validator('created_by', mode='before')
    @classmethod
    def convert_created_by_uuid(cls, v):
        """Convert UUID objects to strings for created_by."""
        if v is None:
            return None
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v else None
    
    @field_validator('updated_by', mode='before')
    @classmethod
    def convert_updated_by_uuid(cls, v):
        """Convert UUID objects to strings for updated_by."""
        if v is None:
            return None
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v else None
    
    class Config:
        from_attributes = True


class BulkImportRequest(BaseModel):
    """Request schema for bulk import."""
    orders: list[dict]  # List of order dictionaries from Excel


class BulkImportResponse(BaseModel):
    """Response schema for bulk import."""
    created: int = 0
    updated: int = 0
    errors: list[str] = []


class BulkDeleteOrdersRequest(BaseModel):
    """Request body for bulk delete: { ids: list[str] }."""
    ids: list[str]


class BulkDeleteOrderLinesRequest(BaseModel):
    """Request body for bulk line delete: { ids: list[str] }."""
    ids: list[str]


# Order lines (delivery order detail)
class OrderLineBase(BaseModel):
    product_id: str
    warehouse_id: str
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    discount: Optional[Decimal] = None
    total: Optional[Decimal] = None
    tax: Optional[Decimal] = None
    total_excluding_tax: Optional[Decimal] = None
    total_including_tax: Optional[Decimal] = None


class OrderLineCreate(OrderLineBase):
    pass


class OrderLineUpdate(BaseModel):
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    discount: Optional[Decimal] = None
    total: Optional[Decimal] = None
    tax: Optional[Decimal] = None
    total_excluding_tax: Optional[Decimal] = None
    total_including_tax: Optional[Decimal] = None


class ProductSimpleRef(BaseModel):
    id: str
    product_code: Optional[str] = None
    product_name: Optional[str] = None

    class Config:
        from_attributes = True


class WarehouseSimpleRef(BaseModel):
    id: str
    warehouse_code: Optional[str] = None
    warehouse_name: Optional[str] = None

    class Config:
        from_attributes = True


class OrderLineResponse(OrderLineBase):
    id: str
    order_id: str
    line_sequence: int
    created_at: datetime
    updated_at: datetime
    product: Optional[ProductSimpleRef] = None
    warehouse: Optional[WarehouseSimpleRef] = None

    class Config:
        from_attributes = True


# Fix forward ref for OrderResponse.lines
OrderResponse.model_rebuild()
