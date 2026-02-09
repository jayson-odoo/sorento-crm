"""Complaint management schemas."""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date
from decimal import Decimal
from app.schemas.resources import AttachmentResponse


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
    uploaded_at: datetime
    link_type: Optional[str] = None  # "complaint_attachment"

    class Config:
        from_attributes = True


class ComplaintAttachmentLinkRequest(BaseModel):
    """Body for linking an existing attachment to a complaint."""
    attachment_id: str


class ComplaintBase(BaseModel):
    delivery_order_number: Optional[str] = None
    complaint_date: Optional[date] = None
    customer_type: Optional[str] = None
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


class ComplaintCreate(ComplaintBase):
    attachments: Optional[list[ComplaintAttachmentCreate]] = None


class ComplaintUpdate(BaseModel):
    delivery_order_number: Optional[str] = None
    complaint_date: Optional[date] = None
    customer_type: Optional[str] = None
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


class ComplaintResponse(ComplaintBase):
    id: str
    respond_inbox_url: Optional[str] = None
    attachments: Optional[list[ComplaintAttachmentResponse]] = []

    class Config:
        from_attributes = True
