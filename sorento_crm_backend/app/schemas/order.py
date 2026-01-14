"""Order management schemas."""
from pydantic import BaseModel, field_validator
from typing import Optional
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
    promised_delivery_date: Optional[datetime] = None
    actual_delivery_date: Optional[datetime] = None
    customer_id: Optional[str] = None
    order_status_id: Optional[str] = None
    billing_address_id: Optional[str] = None
    shipping_address_id: Optional[str] = None
    subtotal_amount: Decimal = Decimal("0")
    discount_amount: Decimal = Decimal("0")
    tax_amount: Decimal = Decimal("0")
    total_amount: Decimal = Decimal("0")
    remarks: Optional[str] = None


class OrderCreate(OrderBase):
    pass


class OrderUpdate(BaseModel):
    order_date: Optional[datetime] = None
    promised_delivery_date: Optional[datetime] = None
    actual_delivery_date: Optional[datetime] = None
    customer_id: Optional[str] = None
    order_status_id: Optional[str] = None
    billing_address_id: Optional[str] = None
    shipping_address_id: Optional[str] = None
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
