"""Marketing management schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_serializer, field_validator
from typing import Optional
from datetime import date, datetime

from app.schemas.promotion_dates import (
    normalize_promotion_start_end,
    normalize_promotion_start_end_optional,
    promotion_date_to_api_iso,
)
from decimal import Decimal
import uuid


class PromotionBase(BaseModel):
    promo_code: str
    name: str
    promo_type: str
    description: Optional[str] = None
    start_date: date
    end_date: date
    is_active: bool = True
    access_levels: Optional[list[str]] = None


class PromotionCreate(PromotionBase):
    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def _normalize_promotion_dates(cls, v):
        return normalize_promotion_start_end(v)


class PromotionUpdate(BaseModel):
    promo_code: Optional[str] = None  # editable; unique together with access_levels set
    name: Optional[str] = None
    promo_type: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_active: Optional[bool] = None
    access_levels: Optional[list[str]] = None

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def _normalize_promotion_dates_optional(cls, v):
        return normalize_promotion_start_end_optional(v)


class FocTier(BaseModel):
    """One buy-N paid units, get M free combination within a group."""

    purchase_quantity: int = Field(ge=1, description="Paid units purchased (e.g. 10)")
    foc_quantity: int = Field(ge=0, description="Free units (e.g. 1)")


class PromotionGroupResponse(BaseModel):
    """FOC / bundle group within a promotion."""

    id: str
    promotion_id: str
    group_name: str
    sort_order: int = 0
    foc_tiers: Optional[list[FocTier]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    promotion_products: Optional[list["PromotionProductResponse"]] = None

    @field_validator("id", "promotion_id", mode="before")
    @classmethod
    def convert_uuid_to_string(cls, v):
        if v is None:
            return None
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v)

    class Config:
        from_attributes = True


class PromotionGroupCreate(BaseModel):
    """Create a bundle / FOC group under a promotion."""

    group_name: str
    sort_order: Optional[int] = None
    foc_tiers: Optional[list[FocTier]] = None

    @field_validator("group_name", mode="before")
    @classmethod
    def strip_name(cls, v):
        if v is None:
            return ""
        return str(v).strip()


class PromotionGroupUpdate(BaseModel):
    """Update group name, sort order, or FOC tiers."""

    group_name: Optional[str] = None
    sort_order: Optional[int] = None
    foc_tiers: Optional[list[FocTier]] = None

    @field_validator("group_name", mode="before")
    @classmethod
    def strip_name(cls, v):
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None


class PromotionResponse(PromotionBase):
    id: str
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    products_count: Optional[int] = 0
    products: Optional[list["PromotionProductResponse"]] = None
    promotion_groups: Optional[list["PromotionGroupResponse"]] = None
    attachments: list["PromotionAttachmentResponse"] = []

    @field_serializer("start_date", "end_date")
    def _serialize_promotion_boundary_dates(self, v: date) -> str:
        return promotion_date_to_api_iso(v)

    @field_validator('id', 'created_by', mode='before')
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


class PromotionListItemResponse(PromotionBase):
    id: str
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    products_count: Optional[int] = 0
    attachments: list["PromotionAttachmentResponse"] = []

    @field_serializer("start_date", "end_date")
    def _serialize_promotion_boundary_dates_list(self, v: date) -> str:
        return promotion_date_to_api_iso(v)

    @field_validator('id', 'created_by', mode='before')
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


class PromotionProductBase(BaseModel):
    promotion_id: str
    product_id: str
    promo_selling_price: Optional[Decimal] = None
    discount_amount: Optional[Decimal] = None
    discount_percent: Optional[Decimal] = None


class PromotionProductCreate(PromotionProductBase):
    promotion_group_id: Optional[str] = None
    dealer_discount_percent: Optional[Decimal] = None


class PromotionProductUpdate(BaseModel):
    promo_selling_price: Optional[Decimal] = None
    discount_amount: Optional[Decimal] = None
    discount_percent: Optional[Decimal] = None
    dealer_discount_percent: Optional[Decimal] = None
    list_price: Optional[Decimal] = Field(
        default=None,
        description="Updates the linked product master list price; recomputes line discount and dealer fields.",
    )


def _uuid_to_str(v):
    """ORM often returns uuid.UUID; API fields are str for JSON."""
    if v is None:
        return None
    if isinstance(v, uuid.UUID):
        return str(v)
    return str(v)


class ProductSimple(BaseModel):
    """Simple product reference."""
    id: str
    product_code: str
    product_name: str
    list_price: Optional[Decimal] = None
    is_discontinued: bool = False

    @field_validator("id", mode="before")
    @classmethod
    def _id_uuid(cls, v):
        return _uuid_to_str(v)

    class Config:
        from_attributes = True


class PromotionSimple(BaseModel):
    """Simple promotion reference."""
    id: str
    promo_code: str
    name: str
    promo_type: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("id", mode="before")
    @classmethod
    def _id_uuid(cls, v):
        return _uuid_to_str(v)

    class Config:
        from_attributes = True


class PromotionProductResponse(BaseModel):
    id: str
    promotion_id: str
    promotion_group_id: Optional[str] = None
    product_id: str
    promotion_price: Optional[Decimal] = None  # Maps from promo_selling_price
    discount_amount: Optional[Decimal] = None
    discount_percent: Optional[Decimal] = None
    dealer_discount_percent: Optional[Decimal] = None
    dealer_cost: Optional[Decimal] = None
    list_to_dealer_margin_amount: Optional[Decimal] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    product: Optional[ProductSimple] = None
    promotion: Optional[PromotionSimple] = None
    promotion_attachments: list["PromotionAttachmentResponse"] = []
    display_order: int = 0  # Default for compatibility

    @field_validator("id", "promotion_id", "promotion_group_id", "product_id", mode="before")
    @classmethod
    def _uuid_id_fields(cls, v):
        """Nested from_attributes (e.g. under promotion_groups) bypasses custom model_validate."""
        return _uuid_to_str(v)

    class Config:
        from_attributes = True

    @classmethod
    def model_validate(cls, obj, **kwargs):
        """Custom validation to map promo_selling_price to promotion_price."""
        # If obj is a SQLAlchemy model, map promo_selling_price to promotion_price
        if hasattr(obj, 'promo_selling_price'):
            # Create a dict with all attributes
            data = {}
            for key in [
                'id', 'promotion_id', 'promotion_group_id', 'product_id', 'discount_amount', 'discount_percent',
                'dealer_discount_percent', 'dealer_cost', 'list_to_dealer_margin_amount',
                'created_at', 'updated_at', 'product', 'promotion', 'promotion_attachments',
            ]:
                if hasattr(obj, key):
                    value = getattr(obj, key)
                    if key in ('id', 'promotion_id', 'promotion_group_id', 'product_id') and isinstance(
                        value, uuid.UUID
                    ):
                        value = str(value)
                    data[key] = value
            # Map promo_selling_price to promotion_price
            data['promotion_price'] = getattr(obj, 'promo_selling_price', None)
            data['display_order'] = getattr(obj, 'display_order', 0)
            return cls(**data)
        return super().model_validate(obj, **kwargs)


class CampaignTypeBase(BaseModel):
    type_code: str
    type_name: str
    description: Optional[str] = None


class CampaignTypeCreate(CampaignTypeBase):
    pass


class CampaignTypeUpdate(BaseModel):
    type_name: Optional[str] = None
    description: Optional[str] = None


class CampaignTypeResponse(CampaignTypeBase):
    id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class CampaignTypeSimple(BaseModel):
    id: str
    type_code: str
    type_name: str
    
    class Config:
        from_attributes = True


class MarketingCampaignBase(BaseModel):
    campaign_code: str
    campaign_name: str
    campaign_type_id: str
    description: Optional[str] = None
    start_date: datetime
    end_date: Optional[datetime] = None
    budget: Optional[Decimal] = None
    target_audience: Optional[str] = None
    status: str = "PLANNING"


class MarketingCampaignCreate(MarketingCampaignBase):
    pass


class MarketingCampaignUpdate(BaseModel):
    campaign_name: Optional[str] = None
    campaign_type_id: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    budget: Optional[Decimal] = None
    target_audience: Optional[str] = None
    status: Optional[str] = None


class MarketingCampaignResponse(MarketingCampaignBase):
    id: str
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    campaign_type: Optional[CampaignTypeSimple] = None
    
    class Config:
        from_attributes = True


# Import Attachment schemas for PromotionAttachment
from app.schemas.resources import AttachmentTypeSimple


class AttachmentSimple(BaseModel):
    """Simple attachment reference for PromotionAttachment."""
    id: str
    original_filename: str
    stored_filename: str
    file_path: str
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    uploaded_at: datetime
    created_at: datetime
    attachment_type: Optional[AttachmentTypeSimple] = None
    access_levels: Optional[list[str]] = None
    directory_id: Optional[str] = None  # for "Open in folder" link
    
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


class PromotionAttachmentBase(BaseModel):
    promotion_id: str
    attachment_id: str
    is_primary: Optional[bool] = False
    sort_order: Optional[int] = None


class PromotionAttachmentCreate(PromotionAttachmentBase):
    pass


class PromotionAttachmentUpdate(BaseModel):
    is_primary: Optional[bool] = None
    sort_order: Optional[int] = None


class PromotionAttachmentResponse(PromotionAttachmentBase):
    id: str
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None
    synced_to_excel: Optional[bool] = False
    last_synced_to_excel: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    promotion: Optional[PromotionSimple] = None
    attachment: Optional[AttachmentSimple] = None
    
    @field_validator('id', 'promotion_id', 'attachment_id', 'created_by', mode='before')
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


PromotionResponse.model_rebuild()
PromotionListItemResponse.model_rebuild()
PromotionProductResponse.model_rebuild()
