"""Complaint management schemas."""
from pydantic import BaseModel, field_validator
from typing import Optional, Any
from datetime import datetime, date
from decimal import Decimal
from app.schemas.resources import AttachmentResponse


def _parse_date_string(v: Any) -> Optional[date]:
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
    link_type: Optional[str] = None  # "complaint_attachment"

    class Config:
        from_attributes = True


class ComplaintAttachmentLinkRequest(BaseModel):
    """Body for linking an existing attachment to a complaint."""
    attachment_id: str


class BulkDeleteComplaintsRequest(BaseModel):
    """Request body for bulk delete: { ids: list[str] }."""
    ids: list[str]


class ComplaintBase(BaseModel):
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
    customer_type_others: Optional[str] = None
    within_warranty: Optional[str] = None
    product_type: Optional[str] = None
    defects_discovered: Optional[str] = None
    complaint_type: Optional[str] = None
    defect_description: Optional[str] = None
    product_code: Optional[str] = None
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


class ComplaintCreate(ComplaintBase):
    attachments: Optional[list[ComplaintAttachmentCreate]] = None


class ComplaintUpdate(BaseModel):
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
    customer_type_others: Optional[str] = None
    within_warranty: Optional[str] = None
    product_type: Optional[str] = None
    defects_discovered: Optional[str] = None
    complaint_type: Optional[str] = None
    defect_description: Optional[str] = None
    product_code: Optional[str] = None
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


class ComplaintResponse(ComplaintBase):
    id: str
    system_id: Optional[str] = None
    form_type: Optional[str] = None
    view_url: Optional[str] = None
    respond_inbox_url: Optional[str] = None
    status: Optional[str] = None
    last_responded_by: Optional[str] = None
    last_responded_by_name: Optional[str] = None
    last_responded_at: Optional[datetime] = None
    assigned_to_name: Optional[str] = None
    attachments: Optional[list[ComplaintAttachmentResponse]] = []

    class Config:
        from_attributes = True
