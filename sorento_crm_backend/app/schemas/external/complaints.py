"""External complaint integration schemas."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
import re
from typing import Any, List, Optional

from pydantic import BaseModel, field_validator, model_validator


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
    delivery_order_numbers: Optional[str | list[str]] = None
    date_of_complaint: Optional[str] = None
    defect_discovered_when: Optional[str] = None
    sales_person: Optional[str] = None
    address: Optional[str] = None
    customer_type: Optional[str] = None
    within_warranty: Optional[str] = None
    product_type: Optional[str] = None
    product_code: Optional[str] = None
    quantity: Optional[str | int | float | Decimal] = None
    complaint_type: Optional[str] = None
    defect_description: Optional[str] = None
    customer_name: Optional[str] = None
    contact_person: Optional[str] = None
    contact_number: Optional[str] = None
    project_title: Optional[str] = None
    contact_id: str
    space_id: str
    response: Optional[str] = None
    attachments: Optional[List[Any]] = None
    complete: Optional[bool] = None
    end: Optional[bool] = None
    validation_errors: Optional[List[Any]] = None
    missing_mandatory_fields: Optional[List[Any]] = None
    human_intervention: Optional[bool] = None
    team: Optional[str] = None
    user_confirmed: Optional[bool] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_alias_keys(cls, data: Any) -> Any:
        """Accept common natural-language key variants from LLM payloads."""
        if not isinstance(data, dict):
            return data

        def _norm_key(raw: Any) -> str:
            s = str(raw or "").strip().lower()
            s = re.sub(r"[^a-z0-9]+", "_", s)
            return re.sub(r"_+", "_", s).strip("_")

        alias_to_canonical = {
            "delivery_order_number": "delivery_order_numbers",
            "delivery_order_no": "delivery_order_numbers",
            "delivery_order_nos": "delivery_order_numbers",
            "do_number": "delivery_order_numbers",
            "date_complaint": "date_of_complaint",
            "complaint_date": "date_of_complaint",
            "date_defect_discovered": "defect_discovered_when",
            "defects_discovered": "defect_discovered_when",
            "defect_discovered_date": "defect_discovered_when",
            "salesperson": "sales_person",
            "customer_address": "address",
            "warranty_status": "within_warranty",
            "product_within_warranty": "within_warranty",
            "within_warranty_status": "within_warranty",
            "qty": "quantity",
            "quantity_involved": "quantity",
            "product_qty": "quantity",
            "contact_name": "contact_person",
            "person_in_charge": "contact_person",
            "project_name": "project_title",
        }

        normalized_items: dict[str, Any] = {}
        for key, value in data.items():
            nk = _norm_key(key)
            canonical = alias_to_canonical.get(nk, nk)
            normalized_items[canonical] = value

        return normalized_items

    @field_validator("quantity", mode="before")
    @classmethod
    def coerce_quantity_to_string(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s if s else None
        if isinstance(v, (int, float, Decimal)):
            return str(v)
        return None

    @field_validator("delivery_order_numbers", mode="before")
    @classmethod
    def coerce_delivery_order_numbers_to_string(cls, v: Any) -> Optional[str]:
        """Accept string OR array and normalize to comma-separated DO numbers."""
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s if s else None
        if isinstance(v, (list, tuple, set)):
            values: list[str] = []
            seen: set[str] = set()
            for item in v:
                token = str(item or "").strip()
                if not token:
                    continue
                key = token.lower()
                if key in seen:
                    continue
                seen.add(key)
                values.append(token)
            return ", ".join(values) if values else None
        token = str(v).strip()
        return token or None

    @field_validator("contact_id", "space_id", mode="before")
    @classmethod
    def validate_non_empty_scope_ids(cls, v: Any, info) -> str:
        s = str(v or "").strip()
        if not s:
            raise ValueError(f"{info.field_name} is required")
        return s

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

