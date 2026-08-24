"""External marketing schemas."""

from __future__ import annotations

from datetime import date
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.marketing import PromotionResponse


class PromotionHeader(BaseModel):
    description: Optional[str] = None
    start_date: Optional[str | date] = None
    end_date: Optional[str | date] = None
    is_active: Optional[bool] = None
    attachment_id: Optional[List[str]] = None

    @field_validator("is_active", mode="before")
    @classmethod
    def coerce_is_active(cls, v: Any) -> Optional[bool]:
        if v is None:
            return None
        if isinstance(v, bool):
            return v
        return None


class PromotionProductItem(BaseModel):
    product_code: str
    selling_price: Optional[float] = None
    discount_amount: Optional[float] = None
    discount_percent: Optional[float] = None
    dealer_discount: Optional[float] = Field(
        None,
        description="Fraction off list for dealer cost, e.g. 0.37 -> dealer_cost = list * (1 - 0.37).",
    )


class PromotionGroupProductItem(BaseModel):
    product_code: str
    selling_price: Optional[float] = None
    discount_amount: Optional[float] = None
    discount_percent: Optional[float] = None
    dealer_discount: Optional[float] = None


class PromotionGroupFocTierItem(BaseModel):
    purchase_quantity: int = Field(ge=1)
    foc_quantity: int = Field(ge=0)


class PromotionGroupFocRuleItem(BaseModel):
    purchase_quantity_for_foc: int = Field(ge=1)
    foc_quantity: int = Field(ge=0)


class PromotionGroupItem(BaseModel):
    group_name: str
    dealer_discount: Optional[float] = Field(
        None,
        description=(
            "Default fraction off list for every product line in this group (e.g. 0.37). "
            "Omitted on a line uses this value; line-level dealer_discount overrides."
        ),
    )
    foc_tiers: Optional[List[PromotionGroupFocTierItem]] = None
    foc_rules: Optional[List[PromotionGroupFocRuleItem]] = None
    promotion_products: List[PromotionGroupProductItem]


class PromotionRequest(BaseModel):
    promotions: PromotionHeader
    promotion_products: Optional[List[PromotionProductItem]] = None
    promotion_groups: Optional[List[PromotionGroupItem]] = None
    access_levels: Optional[List[str]] = None
    attachment_id: Optional[str] = None
    notify_user_id: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _accept_n8n_shape(cls, data: Any) -> Any:
        """Canonicalise three incoming shapes into the internal `promotions` object:

        1. Flat root (preferred): `start_date`, `end_date`, `is_active`,
           `description` live at the root. We hoist them into `promotions`.
        2. n8n table mirror: `promotions` arrives as a single-element list  - 
           unwrap to the object.
        3. Strict legacy: `promotions` already an object - passthrough.

        Root `description` always wins over an empty header `description`
        (the integration sends the source filename at the root).
        Unknown root keys like `promo_type` are silently dropped by Pydantic.
        """
        if not isinstance(data, dict):
            return data
        promos = data.get("promotions")
        if isinstance(promos, list) and len(promos) == 1 and isinstance(promos[0], dict):
            promos = promos[0]
            data["promotions"] = promos
        if not isinstance(promos, dict):
            promos = {}
            data["promotions"] = promos
        for header_key in ("start_date", "end_date", "is_active"):
            if header_key in data and promos.get(header_key) is None:
                promos[header_key] = data[header_key]
        root_desc = data.get("description")
        if (
            isinstance(root_desc, str)
            and root_desc.strip()
            and not (promos.get("description") or "").strip()
        ):
            promos["description"] = root_desc
        return data

    @model_validator(mode="after")
    def require_products_or_groups(self):
        has_flat = bool(self.promotion_products and len(self.promotion_products) > 0)
        has_groups = bool(self.promotion_groups and len(self.promotion_groups) > 0)
        if not has_flat and not has_groups:
            raise ValueError("Either promotion_products or promotion_groups must be provided and non-empty")
        if has_flat and has_groups:
            raise ValueError("Provide either promotion_products or promotion_groups, not both")
        return self


class PromotionCreateResponse(BaseModel):
    promotion: PromotionResponse
    already_existed: bool = False
    message: Optional[str] = None
    warnings: List[dict] = []
    # TCK-2026-000019: flat list mirror of missing product codes captured in `warnings`,
    # for n8n / portal echo without parsing the structured warnings list.
    unknown_product_codes: List[str] = []

