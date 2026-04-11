"""External attachment-link schemas."""

from typing import List, Optional

from pydantic import BaseModel, field_validator, model_validator


class ProductAttachmentLinkRequest(BaseModel):
    product_code: str
    attachment_id: str
    sort_order: Optional[int] = None
    is_primary: Optional[bool] = None
    access_levels: Optional[List[str]] = None


class ProductAttachmentBulkLinkRequest(BaseModel):
    attachment_id: str
    products: List[str]
    access_levels: Optional[List[str]] = None
    notify_user_id: Optional[str] = None


class ProductAttachmentLinkRequestAny(BaseModel):
    attachment_id: str
    product_code: Optional[str] = None
    products: Optional[List[str]] = None
    sort_order: Optional[int] = None
    is_primary: Optional[bool] = None
    access_levels: Optional[List[str]] = None
    notify_user_id: Optional[str] = None

    @field_validator("products", mode="after")
    @classmethod
    def coerce_empty_list_to_none(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is not None and len(v) == 0:
            return None
        return v

    @model_validator(mode="after")
    def require_product_code_or_products(self):
        has_single = self.product_code is not None and (self.product_code or "").strip() != ""
        has_bulk = self.products is not None and len(self.products) > 0
        if not has_single and not has_bulk:
            raise ValueError("Either product_code or products must be provided")
        if has_single and has_bulk:
            raise ValueError("Provide either product_code or products, not both")
        return self

    def get_use_bulk(self) -> bool:
        return self.products is not None and len(self.products) > 0


class ProductAttachmentBulkLinkItem(BaseModel):
    product_id: str
    product_code: str


class ProductAttachmentBulkLinkResponse(BaseModel):
    attachment_id: str
    linked: List[ProductAttachmentBulkLinkItem] = []
    skipped_product_codes: List[str] = []
    already_linked: List[str] = []


class ComplaintAttachmentLinkRequest(BaseModel):
    complaint_id: str
    file_url: str
    file_name: Optional[str] = None
    file_size_bytes: Optional[int] = None


class ComplaintAttachmentLinkResponse(BaseModel):
    attachment_id: str
    complaint_attachment_id: str
    message: str = "Attachment created and linked to complaint."


class EntityAttachmentLinkRequest(BaseModel):
    entity_type: str
    entity_id: str
    file_url: str
    file_name: Optional[str] = None
    file_size_bytes: Optional[int] = None
    attachment_type_code: Optional[str] = None


class EntityAttachmentLinkResponse(BaseModel):
    attachment_id: str
    link_id: str
    entity_type: str
    entity_id: str
    message: str = "Attachment created and linked successfully."


class StockInquiryAttachmentLinkRequest(BaseModel):
    inquiry_id: str
    file_url: str
    file_name: Optional[str] = None
    file_size_bytes: Optional[int] = None


class StockInquiryAttachmentLinkResponse(BaseModel):
    attachment_id: str
    stock_inquiry_attachment_id: str
    message: str = "Attachment created and linked to stock inquiry."

