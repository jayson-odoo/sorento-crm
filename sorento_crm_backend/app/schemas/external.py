"""External API request and response schemas."""
from __future__ import annotations

from pydantic import BaseModel, field_validator, model_validator, ConfigDict
from typing import Optional, List, Any, Union
from datetime import date
from decimal import Decimal

# Alias so response model field named "date" doesn't shadow the type in annotations
DateType = date

from app.schemas.procurement import InboundShipmentResponse
from app.schemas.marketing import PromotionResponse
from app.schemas.forms import FormResponse


class PackingListHeader(BaseModel):
    shipment_number: str
    supplier_id: Optional[str] = None
    shipment_date: str | date
    shipping_container_number: Optional[str] = None
    attachment_id: str
    # Estimated time of arrival → inbound_shipments.eta (parsed like other date fields)
    eta: Optional[str | date] = None
    expected_arrival_date: Optional[str | date] = None
    actual_arrival_date: Optional[str | date] = None
    bill_of_lading_number: Optional[str] = None
    invoice_number: Optional[str] = None
    shipment_status: Optional[str] = None
    total_items_shipped: Optional[int] = None
    total_cartons: Optional[int] = None
    notes: Optional[str] = None


class PackingListProduct(BaseModel):
    product_code: str
    quantity: int


class PackingListRequest(BaseModel):
    packing_list: PackingListHeader
    packing_list_products: List[PackingListProduct]


class PackingListCreateResponse(BaseModel):
    """Response for external packing list create; includes shipment, skipped product codes, and duplication detail."""
    shipment: InboundShipmentResponse
    skipped_product_codes: List[str] = []
    already_existed: bool = False
    message: Optional[str] = None  # e.g. "Shipment number already exists." when already_existed


class SPOAllocationItem(BaseModel):
    spo_number: Optional[str] = None
    spo_line_number: Optional[int] = None  # also accepts string "1" via validator
    inbound_shipment_lines_id: Optional[str] = None
    inbound_shipment_id: Optional[str] = None  # required if shipping_container_number not provided
    shipping_container_number: Optional[str] = None  # resolve inbound_shipment by container number
    warehouse_id: Optional[str] = None  # required if location not provided
    location: Optional[str] = None  # warehouse code or name, e.g. "BRW"
    storage_zone_id: Optional[str] = None
    allocated_quantity: Optional[int] = None  # required if quantity not provided
    quantity: Optional[int] = None  # alias for allocated_quantity
    uom_id: Optional[str] = None
    receipt_status: Optional[str] = None
    quantity_received: Optional[int] = None
    quantity_rejected: Optional[int] = None
    allocation_notes: Optional[str] = None
    product_code: str

    @field_validator("spo_line_number", "quantity", "allocated_quantity", mode="before")
    @classmethod
    def coerce_int(cls, v: Any) -> Optional[int]:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return int(s) if s else None
        return int(v) if v is not None else None


class SPOAllocationRequest(BaseModel):
    spo_allocations: List[SPOAllocationItem]


class GRNHeader(BaseModel):
    picking_number: str
    picking_type: Optional[str] = None
    picking_date: Optional[str | date] = None
    notes: Optional[str] = None


class GRNLine(BaseModel):
    """Match SPO by (spo_number, product_code, warehouse) or legacy (spo_allocation, spo_allocation_line)."""
    spo_allocation: Optional[str] = None  # SPO number (used with warehouse for match, or with spo_allocation_line for legacy)
    spo_allocation_line: Optional[int] = None  # Legacy: line number; prefer matching by spo + product + warehouse
    warehouse_id: Optional[str] = None  # Warehouse UUID for SPO match
    location: Optional[str] = None  # Warehouse code/name for SPO match (resolved to warehouse_id)
    product_code: str
    quantity: int
    uom_id: Optional[str] = None

    @field_validator("spo_allocation_line", "quantity", mode="before")
    @classmethod
    def coerce_int(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return int(s) if s else None
        return int(v) if v is not None else None


class GRNRequest(BaseModel):
    goods_receive_notes: GRNHeader
    grn_lines: List[GRNLine]


class ProductAttachmentLinkRequest(BaseModel):
    product_code: str
    attachment_id: str
    sort_order: Optional[int] = None
    is_primary: Optional[bool] = None
    access_levels: Optional[List[str]] = None


class ProductAttachmentBulkLinkRequest(BaseModel):
    """Link one attachment to many products by product code (spaces removed for matching)."""
    attachment_id: str
    products: List[str]
    access_levels: Optional[List[str]] = None


class ProductAttachmentLinkRequestAny(BaseModel):
    """
    Accept either single link (product_code) or bulk link (products) on the same endpoint.
    Exactly one of product_code or products must be provided.
    """
    attachment_id: str
    product_code: Optional[str] = None
    products: Optional[List[str]] = None
    sort_order: Optional[int] = None
    is_primary: Optional[bool] = None
    access_levels: Optional[List[str]] = None

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
    skipped_product_codes: List[str] = []  # requested but no matching product found
    already_linked: List[str] = []  # product codes that were already linked


class PromotionHeader(BaseModel):
    promo_code: str
    name: Optional[str] = None
    description: Optional[str] = None
    start_date: str | date
    end_date: str | date
    promo_type: str
    is_active: Optional[bool] = None
    attachment_id: Optional[List[str]] = None  # list of attachment UUIDs to link to this promotion

    @field_validator("is_active", mode="before")
    @classmethod
    def coerce_is_active(cls, v: Any) -> Optional[bool]:
        """Coerce non-bool (e.g. string) to None so date-based default is used."""
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


class PromotionRequest(BaseModel):
    promotions: PromotionHeader
    promotion_products: List[PromotionProductItem]
    access_levels: Optional[List[str]] = None  # e.g. ["end_user"], ["dealer", "end_user"]; if omitted, DB default applies
    attachment_id: Optional[str] = None  # single attachment UUID to link to the promotion (alternative to promotions.attachment_id list)


class PromotionCreateResponse(BaseModel):
    """Response for external promotion create; includes conflict detail when promo_code already exists, and warnings (e.g. missing product codes)."""
    promotion: PromotionResponse
    already_existed: bool = False
    message: Optional[str] = None  # e.g. "Promo code already exists." when already_existed
    warnings: List[dict] = []  # e.g. [{"message": "Missing product codes (exact match)", "product_codes": ["ABC", "DEF"]}]


class FormRequest(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    language: Optional[str] = None
    attachment_id: Optional[str] = None


class FormHeaderInput(BaseModel):
    """Form header for external create; only this is used to create the form."""
    code: str
    name: str
    description: Optional[str] = None
    language: Optional[str] = None
    attachment_id: Optional[str] = None


class FormSectionInput(BaseModel):
    """Section item in payload; accepted but ignored when creating form."""
    name: Optional[str] = None
    description: Optional[str] = None

    class Config:
        extra = "ignore"


class FormFieldInput(BaseModel):
    """Field item in payload; accepted but ignored when creating form."""
    name: Optional[str] = None
    section: Optional[str] = None
    label: Optional[str] = None
    type: Optional[str] = None
    options: Optional[List[str]] = None

    class Config:
        extra = "ignore"


class FormCreateRequest(BaseModel):
    """External form create: form (used), form_sections and form_fields (ignored). attachment_id can be at root or inside form."""
    form: FormHeaderInput
    form_sections: Optional[List[FormSectionInput]] = None
    form_fields: Optional[List[FormFieldInput]] = None
    attachment_id: Optional[str] = None  # root-level; used if form.attachment_id not set


class FormCreateResponse(BaseModel):
    """Response for external form create; includes duplication detail when form code already exists."""
    form: FormResponse
    already_existed: bool = False
    message: Optional[str] = None  # e.g. "Form code already exists." when already_existed


class ComplaintAttachmentLinkRequest(BaseModel):
    """Link a complaint to an attachment by creating the attachment (type complaint_document) and the link."""
    complaint_id: str
    file_url: str
    file_name: Optional[str] = None
    file_size_bytes: Optional[int] = None


class ComplaintAttachmentLinkResponse(BaseModel):
    """Response after linking complaint to attachment."""
    attachment_id: str
    complaint_attachment_id: str
    message: str = "Attachment created and linked to complaint."


class EntityAttachmentLinkRequest(BaseModel):
    """Create attachment then link it to a target entity."""
    entity_type: str
    entity_id: str
    file_url: str
    file_name: Optional[str] = None
    file_size_bytes: Optional[int] = None
    attachment_type_code: Optional[str] = None


class EntityAttachmentLinkResponse(BaseModel):
    """Response after creating and linking an attachment to an entity."""
    attachment_id: str
    link_id: str
    entity_type: str
    entity_id: str
    message: str = "Attachment created and linked successfully."


class StockInquiryAttachmentLinkRequest(BaseModel):
    """Link a stock inquiry to an attachment by creating the attachment."""
    inquiry_id: str
    file_url: str
    file_name: Optional[str] = None
    file_size_bytes: Optional[int] = None


class StockInquiryAttachmentLinkResponse(BaseModel):
    """Response after linking stock inquiry to attachment."""
    attachment_id: str
    stock_inquiry_attachment_id: str
    message: str = "Attachment created and linked to stock inquiry."


def _parse_complaint_date(v: Optional[str | date]) -> Optional[date]:
    """Parse date from string; accept yyyy-MM-dd, dd/mm/yyyy, dd-mm-yyyy."""
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
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return dt.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


class ComplaintIntegrationCreate(BaseModel):
    """Integration payload: uses date_of_complaint, defect_discovered_when, delivery_order_numbers, sales_person, address.
    Maps to internal ComplaintCreate when posting to POST /complaints-management/complaints/integration.
    """
    # Integration field names (snake_case as in payload)
    delivery_order_numbers: Optional[str] = None
    date_of_complaint: Optional[str] = None
    defect_discovered_when: Optional[str] = None
    sales_person: Optional[str] = None
    address: Optional[str] = None
    customer_type: Optional[str] = None
    within_warranty: Optional[str] = None
    product_type: Optional[str] = None
    product_code: Optional[str] = None
    quantity: Optional[str] = None
    complaint_type: Optional[str] = None
    defect_description: Optional[str] = None
    customer_name: Optional[str] = None
    contact_person: Optional[str] = None
    contact_number: Optional[str] = None
    project_title: Optional[str] = None
    contact_id: Optional[str] = None
    space_id: Optional[str] = None
    # Ignored by create (conversation/validation metadata)
    response: Optional[str] = None
    attachments: Optional[List[Any]] = None
    complete: Optional[bool] = None
    end: Optional[bool] = None
    validation_errors: Optional[List[Any]] = None
    missing_mandatory_fields: Optional[List[Any]] = None
    human_intervention: Optional[bool] = None
    team: Optional[str] = None

    def to_complaint_create(self):
        """Convert to ComplaintCreate for the service."""
        from app.schemas.complaints import ComplaintCreate
        complaint_date = _parse_complaint_date(self.date_of_complaint)
        # defect_discovered_when -> defects_discovered (store as text, e.g. date or description)
        defects_discovered = self.defect_discovered_when
        return ComplaintCreate(
            delivery_order_number=self.delivery_order_numbers,
            complaint_date=complaint_date,
            defects_discovered=defects_discovered,
            salesperson=self.sales_person,
            customer_address=self.address,
            customer_type=self.customer_type,
            within_warranty=self.within_warranty,
            product_type=self.product_type,
            product_code=self.product_code,
            complaint_type=self.complaint_type,
            defect_description=self.defect_description,
            customer_name=self.customer_name,
            contact_person=self.contact_person,
            contact_number=self.contact_number,
            project_title=self.project_title,
            contact_id=self.contact_id,
            space_id=self.space_id,
        )


class PurchaseRequestExternalLine(BaseModel):
    item_code: Optional[str] = None
    quantity: Optional[Decimal] = None
    remark: Optional[str] = None
    unit_price: Optional[Decimal] = None  # sponsorship form line
    total: Optional[Decimal] = None  # sponsorship form line (qty * unit_price)

    @field_validator("quantity", mode="before")
    @classmethod
    def coerce_quantity(cls, v: Any) -> Optional[Decimal]:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return Decimal(s) if s else None
        return Decimal(v)

    @field_validator("unit_price", "total", mode="before")
    @classmethod
    def coerce_decimal(cls, v: Any) -> Optional[Decimal]:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return Decimal(s) if s else None
        return Decimal(v)


class PurchaseRequestExternalCreate(BaseModel):
    """Create a purchase request or sponsorship form. Ask request_type first, then the relevant fields.

    Purchase request fields: date, customer_name, project_title, purpose (showroom/mock up/others:__),
    expected_delivery_date, expected_po_date, products (item_code, quantity, remark per line),
    requested_by, requested_at.

    Sponsorship form fields: date, customer_name, delivery_address, project_title, total_project_value
    (numeric or descriptive text e.g. "BULK ORDER EST RM1.6MIL"), sponsor_subject (showroom/mockup/others:__),
    expected_delivery_date or date_of_delivery, products (item_code, quantity, unit_price, total per line),
    requested_by, requested_at.
    """
    model_config = ConfigDict(extra="ignore")  # allow response, complete, team, etc. from Respond/n8n

    request_type: str
    date: Optional[str | DateType] = None
    customer_name: Optional[str] = None
    project_title: Optional[str] = None
    purpose: Optional[str] = None
    delivery_address: Optional[str] = None  # sponsorship form
    total_project_value: Optional[Union[Decimal, str]] = None  # numeric or descriptive text
    sponsor_subject: Optional[str] = None  # sponsorship: showroom/mockup/others
    expected_delivery_date: Optional[str | DateType] = None
    expected_po_date: Optional[str | DateType] = None
    date_of_delivery: Optional[str | DateType] = None  # alias for expected_delivery_date (sponsorship)
    products: List[PurchaseRequestExternalLine] = []
    requested_by: Optional[str] = None
    requested_at: Optional[str | DateType] = None
    external_reference: Optional[str] = None
    contact_id: Optional[str] = None
    space_id: Optional[str] = None
    base_url: Optional[str] = None  # Frontend app origin for notification email link

    @field_validator("request_type")
    @classmethod
    def validate_request_type(cls, v: str) -> str:
        normalized = (v or "").strip()
        if normalized not in {"purchase_request", "sponsorship_form"}:
            raise ValueError("request_type must be purchase_request or sponsorship_form")
        return normalized


class PurchaseRequestExternalResponse(BaseModel):
    id: str
    request_type: str
    date: Optional[DateType] = None
    customer_name: Optional[str] = None
    project_title: Optional[str] = None
    purpose: Optional[str] = None
    delivery_address: Optional[str] = None
    total_project_value: Optional[Decimal] = None
    total_project_value_text: Optional[str] = None  # descriptive e.g. "BULK ORDER EST RM1.6MIL"
    sponsor_subject: Optional[str] = None
    expected_delivery_date: Optional[DateType] = None
    expected_po_date: Optional[str | DateType] = None
    products: List[PurchaseRequestExternalLine] = []
    requested_by: Optional[str] = None
    requested_at: Optional[DateType] = None
    grand_total: Optional[Decimal] = None  # sponsorship form: sum of line totals
    already_existed: bool = False
    message: Optional[str] = None
    respond_inbox_url: Optional[str] = None


# --- Respond contact sync (n8n / Respond.io webhook) ---


class RespondContactSyncRequest(BaseModel):
    """Payload for external create/update of internal respond contact (e.g. from n8n when contact created/updated in Respond).
    Accepts Respond.io-style payload: id (respond.io contact id), phone/firstName/lastName, custom_fields, etc.
    """
    id: Optional[int] = None  # Respond.io contact id - stored as respond_io_id
    phone_number: Optional[str] = None  # E.164; also accept "phone" from payload
    phone: Optional[str] = None
    name: Optional[str] = None
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    user_type: Optional[str] = None
    email: Optional[str] = None
    language: Optional[str] = None
    countryCode: Optional[str] = None
    status: Optional[str] = None
    # custom_fields, tags, assignee, lifecycle, created_at can be sent but are not stored on respond_contacts


class RespondContactSyncResponse(BaseModel):
    """Response after upserting a respond contact via external API."""
    id: str
    phone_number: str
    name: Optional[str] = None
    user_type: Optional[str] = None
    respond_io_id: Optional[str] = None
    action: str  # "created" | "updated"


# --- N8N chat history (latest human messages by contact) ---


class ChatHistoryHumanMessagesRequest(BaseModel):
    """Request for latest n human messages from n8n_chat_histories for a contact (by respond_io_id)."""
    contact_id: str  # respond_io_id (maps to session_id in n8n_chat_histories)
    limit: int = 10  # number of latest human messages to return (1–100), clamped server-side


class ChatHistoryHumanMessagesResponse(BaseModel):
    """Response: list of human message content strings (oldest to newest, chronological order)."""
    content: List[str]
