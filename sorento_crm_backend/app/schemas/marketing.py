"""Marketing management schemas."""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from decimal import Decimal


class PromotionBase(BaseModel):
    promo_code: str
    name: str
    promo_type: str
    description: Optional[str] = None
    start_date: datetime
    end_date: datetime
    is_active: bool = True


class PromotionCreate(PromotionBase):
    pass


class PromotionUpdate(BaseModel):
    name: Optional[str] = None
    promo_type: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_active: Optional[bool] = None


class PromotionResponse(PromotionBase):
    id: str
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    products_count: Optional[int] = 0
    products: Optional[list[PromotionProductResponse]] = None
    
    class Config:
        from_attributes = True


class PromotionProductBase(BaseModel):
    promotion_id: str
    product_id: str
    promo_selling_price: Optional[Decimal] = None
    discount_amount: Optional[Decimal] = None
    discount_percent: Optional[Decimal] = None


class PromotionProductCreate(PromotionProductBase):
    pass


class PromotionProductUpdate(BaseModel):
    promo_selling_price: Optional[Decimal] = None
    discount_amount: Optional[Decimal] = None
    discount_percent: Optional[Decimal] = None


class ProductSimple(BaseModel):
    """Simple product reference."""
    id: str
    product_code: str
    product_name: str
    list_price: Optional[Decimal] = None
    
    class Config:
        from_attributes = True


class PromotionSimple(BaseModel):
    """Simple promotion reference."""
    id: str
    promo_code: str
    name: str
    promo_type: Optional[str] = None
    is_active: Optional[bool] = None
    
    class Config:
        from_attributes = True


class PromotionProductResponse(BaseModel):
    id: str
    promotion_id: str
    product_id: str
    promotion_price: Optional[Decimal] = None  # Maps from promo_selling_price
    discount_amount: Optional[Decimal] = None
    discount_percent: Optional[Decimal] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    product: Optional[ProductSimple] = None
    promotion: Optional[PromotionSimple] = None
    display_order: int = 0  # Default for compatibility
    
    class Config:
        from_attributes = True
    
    @classmethod
    def model_validate(cls, obj, **kwargs):
        """Custom validation to map promo_selling_price to promotion_price."""
        # If obj is a SQLAlchemy model, map promo_selling_price to promotion_price
        if hasattr(obj, 'promo_selling_price'):
            # Create a dict with all attributes
            data = {}
            for key in ['id', 'promotion_id', 'product_id', 'discount_amount', 'discount_percent', 
                       'created_at', 'updated_at', 'product', 'promotion']:
                if hasattr(obj, key):
                    value = getattr(obj, key)
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
