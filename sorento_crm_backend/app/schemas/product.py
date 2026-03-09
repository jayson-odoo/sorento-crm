"""Product schemas."""
from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
import uuid


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
    product_count: Optional[int] = None

    class Config:
        from_attributes = True


class UnitOfMeasureBase(BaseModel):
    uom_code: str
    uom_name: str
    base_uom_id: Optional[str] = None
    conversion_factor: Optional[Decimal] = None
    description: Optional[str] = None
    is_active: bool = True


class UnitOfMeasureCreate(UnitOfMeasureBase):
    pass


class UnitOfMeasureUpdate(BaseModel):
    uom_name: Optional[str] = None
    base_uom_id: Optional[str] = None
    conversion_factor: Optional[Decimal] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class UnitOfMeasureResponse(UnitOfMeasureBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    product_count: Optional[int] = None
    base_uom: Optional["UnitOfMeasureSimple"] = None

    class Config:
        from_attributes = True


class ProductBase(BaseModel):
    product_code: str
    product_name: str

    @field_validator("product_code", "product_name", mode="before")
    @classmethod
    def strip_string_fields(cls, v):
        """Trim leading/trailing whitespace to avoid dirty data."""
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("list_price", "cost_price", "invoice_price", mode="after")
    @classmethod
    def prices_non_negative(cls, v):
        """Reject negative prices."""
        if v is not None and v < 0:
            raise ValueError("Price cannot be negative")
        return v

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

    @field_validator("product_name", "description", mode="before")
    @classmethod
    def strip_optional_strings(cls, v):
        """Trim leading/trailing whitespace when provided."""
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("list_price", "cost_price", "invoice_price", mode="after")
    @classmethod
    def prices_non_negative(cls, v):
        """Reject negative prices."""
        if v is not None and v < 0:
            raise ValueError("Price cannot be negative")
        return v


class ProductCategorySimple(BaseModel):
    id: str
    category_code: str
    category_name: str
    
    class Config:
        from_attributes = True


class ProductSimple(BaseModel):
    """Simple product reference for ProductAttachment."""
    id: str
    product_code: str
    product_name: str
    
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

    @field_validator('created_by', 'updated_by', mode='before')
    @classmethod
    def convert_uuid_to_str(cls, v):
        """Convert UUID objects to strings for created_by/updated_by."""
        if v is None:
            return None
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v else None

    class Config:
        from_attributes = True


# Import Attachment schemas for ProductAttachment
from app.schemas.resources import AttachmentResponse, AttachmentTypeSimple


class AttachmentSimple(BaseModel):
    """Simple attachment reference for ProductAttachment."""
    id: str
    original_filename: str
    stored_filename: str
    file_path: str
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    uploaded_at: datetime
    attachment_type: Optional[AttachmentTypeSimple] = None
    full_directory_path: Optional[str] = None  # e.g. "SORENTO CABANA (DEALER) --> SORENTO --> Product Photo --> Angle Valve"
    access_levels: Optional[list[str]] = None  # e.g. ["dealer", "end_user"]; source of truth at attachment level

    @field_validator('id', mode='before')
    @classmethod
    def convert_uuid_to_string(cls, v):
        """Convert UUID objects to strings."""
        if v is None:
            return None
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v)
    
    class Config:
        from_attributes = True


class ProductAttachmentBase(BaseModel):
    product_id: str
    attachment_id: str
    is_primary: Optional[bool] = False
    sort_order: Optional[int] = None
    access_levels: Optional[list[str]] = None


class ProductAttachmentCreate(ProductAttachmentBase):
    pass


class ProductAttachmentUpdate(BaseModel):
    is_primary: Optional[bool] = None
    sort_order: Optional[int] = None
    access_levels: Optional[list[str]] = None


# Max rows per product import (queued job); kept reasonable to avoid huge request payloads
BULK_IMPORT_MAX_ROWS_PER_REQUEST = 50_000


class BulkDeleteProductsRequest(BaseModel):
    """Request schema for bulk delete. Body: { ids: string[] }."""
    ids: List[str]


class BulkImportProductsRequest(BaseModel):
    """Request schema for product bulk import. Each item is a row (Excel headers as keys). Processed in background as an import job."""
    products: List[dict]
    validate_only: Optional[bool] = False  # If True, run validation only (no import); return errors/warnings.

    @field_validator("products")
    @classmethod
    def products_batch_limit(cls, v: List[dict]) -> List[dict]:
        if len(v) > BULK_IMPORT_MAX_ROWS_PER_REQUEST:
            raise ValueError(
                f"Maximum {BULK_IMPORT_MAX_ROWS_PER_REQUEST} rows per import. Reduce the file size and try again."
            )
        return v


class BulkImportProductsResponse(BaseModel):
    """Response schema for product bulk import."""
    created: int = 0
    updated: int = 0
    errors: List[str] = []


class ProductAttachmentResponse(ProductAttachmentBase):
    id: str
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None
    synced_to_excel: Optional[bool] = False
    last_synced_to_excel: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    product: Optional[ProductSimple] = None
    attachment: Optional[AttachmentSimple] = None
    
    @field_validator('id', 'product_id', 'attachment_id', 'created_by', mode='before')
    @classmethod
    def convert_uuid_to_string(cls, v):
        """Convert UUID objects to strings."""
        if v is None:
            return None
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v)
    
    class Config:
        from_attributes = True
