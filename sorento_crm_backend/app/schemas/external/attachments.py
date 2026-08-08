"""External attachment-link schemas."""

from datetime import date, datetime
from typing import Any, List, Optional

from pydantic import BaseModel, field_validator, model_validator

# Date formats the document reader actually emits. Mirrors
# ``app/api/v1/external/utils.parse_date_value``; duplicated rather than
# imported so a schema module does not reach up into the API layer.
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%Y/%m/%d")


def _parse_loose_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Invalid date format: {value}")


# The certificate fields the document reader may return alongside the product
# codes. Every one is optional: a Technical Specifications sheet or a Product
# Photo simply sends none of them, which is what keeps ING-5 byte-identical.
CERTIFICATE_FIELD_NAMES = (
    "scheme",
    "certifying_body",
    "certificate_number",
    "issuer",
    "title",
    "issued_at",
    "valid_from",
    "valid_until",
)


class CertificateExtractionFields(BaseModel):
    """Optional certificate fields carried by a product-attachment link call.

    Supplying them is never enough on its own: they are honoured only when the
    attachment's type has ``is_certificate = true`` (ING-4). The guard lives in
    the route, server-side, so a prompt change can never mint a certificate off
    a spec sheet that happens to quote a certificate number.

    Dates arrive as free-text from the model, so they go through the same
    lenient parser the other external endpoints use rather than Pydantic's
    ISO-only coercion - "23/12/2026" is a date the reader really does emit.
    """

    scheme: Optional[str] = None
    certifying_body: Optional[str] = None
    certificate_number: Optional[str] = None
    issuer: Optional[str] = None
    # The scheme's own wording, e.g. "Product Certification Scheme - sanitary
    # ware". The service has always accepted it; without it here an AI-filed
    # certificate could never carry one, so the detail page read "Not recorded"
    # for every certificate n8n created.
    title: Optional[str] = None
    issued_at: Optional[date] = None
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None

    @field_validator(
        "scheme", "certifying_body", "certificate_number", "issuer", "title", mode="before"
    )
    @classmethod
    def _blank_string_is_null(cls, v: Any) -> Any:
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v

    @field_validator("issued_at", "valid_from", "valid_until", mode="before")
    @classmethod
    def _lenient_date(cls, v: Any) -> Any:
        return _parse_loose_date(v)

    def certificate_fields(self) -> dict:
        """The supplied cert fields, blanks dropped. Empty dict = none supplied."""
        out = {}
        for name in CERTIFICATE_FIELD_NAMES:
            value = getattr(self, name, None)
            if value is not None:
                out[name] = value
        return out

    def has_certificate_fields(self) -> bool:
        return bool(self.certificate_fields())


class ProductAttachmentLinkRequest(BaseModel):
    product_code: str
    attachment_id: str
    sort_order: Optional[int] = None
    is_primary: Optional[bool] = None
    access_levels: Optional[List[str]] = None
    # Field-linkage override. None = use the attachment's saved
    # `target_field_keys` template. Empty list = no per-field links.
    field_keys: Optional[List[str]] = None


class ProductAttachmentBulkLinkRequest(BaseModel):
    attachment_id: str
    products: List[str]
    access_levels: Optional[List[str]] = None
    notify_user_id: Optional[str] = None
    field_keys: Optional[List[str]] = None


class ProductAttachmentLinkRequestAny(CertificateExtractionFields):
    """Body of ``POST /api/v1/external/product-attachments``.

    Inherits the optional certificate fields (ING-2): same URL, same node, so
    the n8n workflow's HTTP node is unchanged whether or not the document turned
    out to be a certificate.
    """

    attachment_id: str
    product_code: Optional[str] = None
    products: Optional[List[str]] = None
    sort_order: Optional[int] = None
    is_primary: Optional[bool] = None
    access_levels: Optional[List[str]] = None
    notify_user_id: Optional[str] = None
    field_keys: Optional[List[str]] = None

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
    field_keys: Optional[List[str]] = None


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

