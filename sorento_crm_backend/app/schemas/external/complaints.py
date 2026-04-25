"""External complaint integration schemas."""

from __future__ import annotations

from datetime import date
from typing import Any, List, Optional

from pydantic import BaseModel


def _parse_complaint_date(v: Optional[str | date]) -> Optional[date]:
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
    response: Optional[str] = None
    attachments: Optional[List[Any]] = None
    complete: Optional[bool] = None
    end: Optional[bool] = None
    validation_errors: Optional[List[Any]] = None
    missing_mandatory_fields: Optional[List[Any]] = None
    human_intervention: Optional[bool] = None
    team: Optional[str] = None
    user_confirmed: Optional[bool] = None

    def to_complaint_create(self):
        from app.schemas.complaints import ComplaintCreate

        complaint_date = _parse_complaint_date(self.date_of_complaint)
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

