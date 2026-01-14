"""Product schemas."""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from decimal import Decimal


class ProductCategoryBase(BaseModel):
    category_code: str
    category_name: str
    description: Optional[str] = None
    parent_category_id: Optional[str] = None
    is_active: bool = True
    display_order: Optional[int] = 0


class ProductCategoryCreate(ProductCategoryBase):
    pass


class ProductCategoryUpdate(BaseModel):
    category_name: Optional[str] = None
    description: Optional[str] = None
    parent_category_id: Optional[str] = None
    is_active: Optional[bool] = None
    display_order: Optional[int] = None


class ProductCategoryResponse(ProductCategoryBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class BrandBase(BaseModel):
    brand_code: str
    brand_name: str
    manufacturer: Optional[str] = None
    website: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None
    is_active: bool = True


class BrandCreate(BrandBase):
    pass


class BrandUpdate(BaseModel):
    brand_name: Optional[str] = None
    manufacturer: Optional[str] = None
    website: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None
    is_active: Optional[bool] = None


class BrandResponse(BrandBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class UnitOfMeasureBase(BaseModel):
    uom_code: str
    uom_name: str
    base_uom_id: Optional[str] = None
    conversion_factor: Optional[Decimal] = None
    description: Optional[str] = None


class UnitOfMeasureCreate(UnitOfMeasureBase):
    pass


class UnitOfMeasureUpdate(BaseModel):
    uom_name: Optional[str] = None
    base_uom_id: Optional[str] = None
    conversion_factor: Optional[Decimal] = None
    description: Optional[str] = None


class UnitOfMeasureResponse(UnitOfMeasureBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class ProductBase(BaseModel):
    product_code: str
    product_name: str
    description: Optional[str] = None
    category_id: str
    brand_id: Optional[str] = None
    base_uom_id: str
    item_type: Optional[str] = None
    list_price: Decimal
    cost_price: Optional[Decimal] = None
    invoice_price: Optional[Decimal] = None
    weight: Optional[Decimal] = None
    dimensions_length: Optional[Decimal] = None
    dimensions_width: Optional[Decimal] = None
    dimensions_height: Optional[Decimal] = None
    warranty_months: Optional[int] = None
    has_serial_tracking: bool = False
    has_batch_tracking: bool = False
    reorder_level: Optional[int] = None
    reorder_quantity: Optional[int] = None
    is_active: bool = True


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    product_name: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[str] = None
    brand_id: Optional[str] = None
    base_uom_id: Optional[str] = None
    item_type: Optional[str] = None
    list_price: Optional[Decimal] = None
    cost_price: Optional[Decimal] = None
    invoice_price: Optional[Decimal] = None
    weight: Optional[Decimal] = None
    dimensions_length: Optional[Decimal] = None
    dimensions_width: Optional[Decimal] = None
    dimensions_height: Optional[Decimal] = None
    warranty_months: Optional[int] = None
    has_serial_tracking: Optional[bool] = None
    has_batch_tracking: Optional[bool] = None
    reorder_level: Optional[int] = None
    reorder_quantity: Optional[int] = None
    is_active: Optional[bool] = None


class ProductCategorySimple(BaseModel):
    id: str
    category_code: str
    category_name: str
    
    class Config:
        from_attributes = True


class BrandSimple(BaseModel):
    id: str
    brand_code: str
    brand_name: str
    
    class Config:
        from_attributes = True


class UnitOfMeasureSimple(BaseModel):
    id: str
    uom_code: str
    uom_name: str
    
    class Config:
        from_attributes = True


class ProductResponse(ProductBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    category: Optional[ProductCategorySimple] = None
    brand: Optional[BrandSimple] = None
    base_uom: Optional[UnitOfMeasureSimple] = None
    
    class Config:
        from_attributes = True
