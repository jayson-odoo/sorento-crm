"""Complaint management schemas."""
from pydantic import BaseModel, field_validator
from typing import Optional, Any
from datetime import datetime, date
from decimal import Decimal
from app.schemas.resources import AttachmentResponse


def _parse_date_string(v: Any) -> Optional[date]:
    """Parse date from string; accept yyyy-MM-dd, dd/mm/yyyy, dd-mm-yyyy, ISO datetime."""
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
    try:
        return dt.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _coerce_scope_id(v: Any) -> Optional[str]:
    """Accept int/string identifiers and normalize to non-empty string."""
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s if s else None
    if isinstance(v, (int, float, Decimal)):
        return str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)
    s = str(v).strip()
    return s if s else None


def _coerce_within_warranty(v: Any) -> Optional[str]:
    """Accept bool, str, or None for within_warranty. bool -> 'Yes'/'No'."""
    if v is None:
        return None
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, str):
        s = v.strip()
        return s if s else None
    return str(v)


class ComplaintAttachmentBase(BaseModel):
    complaint_id: str
    file_name: Optional[str] = None
    file_url: Optional[str] = None
    file_size_bytes: Optional[Decimal] = None


class ComplaintAttachmentCreate(ComplaintAttachmentBase):
    pass


class ComplaintAttachmentResponse(ComplaintAttachmentBase):
    id: str
    attachment_id: Optional[str] = None
    original_filename: Optional[str] = None  # Human-readable name for display
    uploaded_at: datetime
    created_at: datetime
    link_type: Optional[str] = None  # "complaint_attachment" | "response_attachment"
    # Uploader attribution (UAC B2/B5). A response_model that omits these silently
    # drops what serialize_link already computes, so the panel renders "Unknown".
    mime_type: Optional[str] = None
    uploader_kind: Optional[str] = None
    uploaded_by_name: Optional[str] = None
    uploaded_by_role: Optional[str] = None
    can_unlink: Optional[bool] = None

    class Config:
        from_attributes = True


class ComplaintAttachmentLinkRequest(BaseModel):
    """Body for linking an existing attachment to a complaint."""
    attachment_id: str


class BulkDeleteComplaintsRequest(BaseModel):
    """Request body for bulk delete: { ids: list[str] }."""
    ids: list[str]


class ComplaintRejectRequest(BaseModel):
    """Request body for rejecting a complaint; reason is mandatory."""
    rejection_reason: str


class ComplaintFinalizeRequest(BaseModel):
    """Request body for resolve / close; optional note sent to the contact."""
    note: Optional[str] = None


class ComplaintProductLineBase(BaseModel):
    product_code: str
    quantity: Optional[str] = None
    product_type: Optional[str] = None


class ComplaintProductLineResponse(ComplaintProductLineBase):
    id: Optional[str] = None
    sort_order: Optional[int] = None
    # The consumer half of a line. A retail complaint arrives as words on a phone, so
    # `product_code` is frequently a guess and `claimed_text` is the only verbatim
    # record of what the person actually said. Names, never ids: a CS agent reading
    # this screen cannot act on a UUID (see the cursor rules).
    claimed_text: Optional[str] = None
    fault_description: Optional[str] = None
    defect_type_name: Optional[str] = None
    kind_name: Optional[str] = None
    product_name: Optional[str] = None
    # The purchase this line's cover is computed from (AC-L16). Absent on most lines:
    # the complaint routinely arrives before any receipt does.
    purchase_number: Optional[str] = None
    purchase_date: Optional[date] = None

    class Config:
        from_attributes = True


class ComplaintBase(BaseModel):
    complaint_number: Optional[str] = None
    delivery_order_number: Optional[str] = None
    complaint_date: Optional[date] = None
    customer_type: Optional[str] = None

    @field_validator("complaint_date", mode="before")
    @classmethod
    def parse_complaint_date(cls, v: Any) -> Optional[date]:
        return _parse_date_string(v)

    @field_validator("contact_id", "space_id", mode="before")
    @classmethod
    def coerce_scope_ids(cls, v: Any) -> Optional[str]:
        return _coerce_scope_id(v)

    @field_validator("within_warranty", mode="before")
    @classmethod
    def coerce_within_warranty(cls, v: Any) -> Optional[str]:
        return _coerce_within_warranty(v)
    customer_type_others: Optional[str] = None
    within_warranty: Optional[Any] = None
    product_type: Optional[str] = None
    defects_discovered: Optional[str] = None
    complaint_type: Optional[str] = None
    defect_description: Optional[str] = None
    product_code: Optional[str] = None
    quantity: Optional[str] = None
    salesperson: Optional[str] = None
    customer_name: Optional[str] = None
    contact_person: Optional[str] = None
    contact_number: Optional[str] = None
    customer_address: Optional[str] = None
    project_title: Optional[str] = None
    contact_id: Optional[str] = None
    space_id: Optional[str] = None
    technical_team_response: Optional[str] = None
    status: Optional[str] = None
    last_responded_by: Optional[str] = None
    last_responded_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    assigned_to: Optional[str] = None
    assigned_to_name: Optional[str] = None
    root_cause_id: Optional[str] = None
    resolution_id: Optional[str] = None
    required_on_site_support: Optional[bool] = None


class ComplaintCreate(ComplaintBase):
    attachments: Optional[list[ComplaintAttachmentCreate]] = None
    product_lines: Optional[list[ComplaintProductLineBase]] = None


class ComplaintUpdate(BaseModel):
    complaint_number: Optional[str] = None
    delivery_order_number: Optional[str] = None
    complaint_date: Optional[date] = None
    customer_type: Optional[str] = None

    @field_validator("complaint_date", mode="before")
    @classmethod
    def parse_complaint_date(cls, v: Any) -> Optional[date]:
        return _parse_date_string(v)

    @field_validator("contact_id", "space_id", mode="before")
    @classmethod
    def coerce_scope_ids(cls, v: Any) -> Optional[str]:
        return _coerce_scope_id(v)

    @field_validator("within_warranty", mode="before")
    @classmethod
    def coerce_within_warranty(cls, v: Any) -> Optional[str]:
        return _coerce_within_warranty(v)
    customer_type_others: Optional[str] = None
    within_warranty: Optional[Any] = None
    product_type: Optional[str] = None
    defects_discovered: Optional[str] = None
    complaint_type: Optional[str] = None
    defect_description: Optional[str] = None
    product_code: Optional[str] = None
    quantity: Optional[str] = None
    salesperson: Optional[str] = None
    customer_name: Optional[str] = None
    contact_person: Optional[str] = None
    contact_number: Optional[str] = None
    customer_address: Optional[str] = None
    project_title: Optional[str] = None
    contact_id: Optional[str] = None
    space_id: Optional[str] = None
    technical_team_response: Optional[str] = None
    status: Optional[str] = None
    last_responded_by: Optional[str] = None
    last_responded_at: Optional[datetime] = None
    root_cause_id: Optional[str] = None
    resolution_id: Optional[str] = None
    required_on_site_support: Optional[bool] = None
    product_lines: Optional[list[ComplaintProductLineBase]] = None


class ComplaintResponse(ComplaintBase):
    id: str
    system_id: Optional[str] = None
    form_type: Optional[str] = None
    view_url: Optional[str] = None
    respond_inbox_url: Optional[str] = None
    print_count: Optional[int] = None
    status: Optional[str] = None
    last_responded_by: Optional[str] = None
    last_responded_by_name: Optional[str] = None
    last_responded_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    rejected_at: Optional[datetime] = None
    rejected_by: Optional[str] = None
    rejected_by_name: Optional[str] = None  # resolved rejecter display name (banner)
    rejected_by_wa_phone: Optional[str] = None  # rejecter's wa.me digits (banner link)
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    # Void banner (BAN-1). voided_by is exposed as a resolved display name only (no UUID).
    void_reason: Optional[str] = None
    voided_at: Optional[datetime] = None
    voided_by_name: Optional[str] = None
    voided_by_wa_phone: Optional[str] = None
    assigned_to_name: Optional[str] = None
    handled_by_name: Optional[str] = None
    handled_by_wa_phone: Optional[str] = None  # holder's wa.me digits (banner link)
    root_cause_id: Optional[str] = None
    resolution_id: Optional[str] = None
    root_cause_name: Optional[str] = None
    resolution_name: Optional[str] = None
    root_cause_notified_at: Optional[datetime] = None
    resolution_notified_at: Optional[datetime] = None
    attachments: Optional[list[ComplaintAttachmentResponse]] = []
    product_lines: Optional[list[ComplaintProductLineResponse]] = []

    # --- Who reported it, and where the fault is -----------------------------
    #
    # These columns have existed on `complaints` since the after-sales S1 slice, and
    # the serializer has always put them in its dict - this response model simply never
    # declared them, so every one was dropped on the way out. The effect was a retail
    # complaint that rendered as a page of dashes: no site address, no pin, and a
    # Products table that fell back to splitting a CSV column the consumer journey
    # never writes.
    #
    # `reported_by_role` is the discriminator the detail screen branches on. A retail
    # case and a project case are the same entity handled by the same team through the
    # same status graph and the same SLA stages; what differs is which fields mean
    # anything, and that is a rendering decision, not a storage one.
    reported_by_role: Optional[str] = None
    site_address: Optional[str] = None
    site_address_line1: Optional[str] = None
    site_address_line2: Optional[str] = None
    site_postcode: Optional[str] = None
    site_city: Optional[str] = None
    site_state: Optional[str] = None
    site_country: Optional[str] = None
    site_contact_name: Optional[str] = None
    site_contact_phone: Optional[str] = None
    # Decimal, not float: the pin is what a technician navigates to and a float does
    # not round-trip a coordinate copied between systems.
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None
    # The WhatsApp burst verbatim. What a human reads when the extraction is wrong.
    intake_transcript: Optional[str] = None

    class Config:
        from_attributes = True
