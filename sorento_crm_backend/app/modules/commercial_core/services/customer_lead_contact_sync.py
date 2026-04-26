"""Lead primary MAIN contact synced from Customer person fields."""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modules.commercial_core.models import CommercialLead
from app.models.order import Customer, CustomerContact


SYNC_MANUAL = "manual"
SYNC_LEAD_PRIMARY = "lead_primary"


def _trim(s: Optional[str]) -> str:
    return (s or "").strip()


def build_primary_display_name(cust: Customer) -> str:
    sal = _trim(getattr(cust, "salutation", None))
    fn = _trim(getattr(cust, "first_name", None))
    ln = _trim(getattr(cust, "last_name", None))
    inner = " ".join(x for x in (fn, ln) if x).strip()
    if sal and inner:
        return f"{sal} {inner}"
    if inner:
        return inner
    return _trim(cust.customer_name) or "Main contact"


def validate_customer_required_for_commercial_lead(cust: Customer) -> None:
    """Commercial leads require minimal company/contact fields on the linked Customer."""
    missing: list[str] = []
    if not _trim(cust.customer_name):
        missing.append("company (customer_name)")
    # Keep validation aligned with the actual customer edit form.
    # Name parts/salutation/mobile are optional because the primary contact sync
    # can derive display name from `customer_name` and preserve missing fields.
    if not _trim(cust.phone_number):
        missing.append("phone")
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Customer is missing required fields for commercial leads: {', '.join(missing)}",
        )


def customer_has_commercial_leads(db: Session, customer_id: str) -> bool:
    return (
        db.query(func.count(CommercialLead.id)).filter(CommercialLead.customer_id == customer_id).scalar() or 0
    ) > 0


def upsert_lead_primary_contact(db: Session, cust: Customer) -> None:
    """Ensure one MAIN contact exists, synced from Customer person fields (lead_primary)."""
    cid = str(cust.id)
    full_name = build_primary_display_name(cust)
    email = _trim(cust.email) or None
    phone = _trim(cust.phone_number) or None
    mobile = _trim(getattr(cust, "mobile_number", None)) or None

    row = (
        db.query(CustomerContact)
        .filter(
            CustomerContact.customer_id == cid,
            CustomerContact.contact_role == "main",
            CustomerContact.sync_source == SYNC_LEAD_PRIMARY,
        )
        .first()
    )
    if row:
        row.full_name = full_name or row.full_name
        row.email = email
        row.phone = phone
        row.mobile = mobile
        db.flush()
        return

    existing_main = (
        db.query(CustomerContact)
        .filter(CustomerContact.customer_id == cid, CustomerContact.contact_role == "main")
        .first()
    )
    if existing_main:
        existing_main.contact_role = "stakeholder"

    db.add(
        CustomerContact(
            customer_id=cid,
            full_name=full_name or "Main contact",
            job_title=None,
            email=email,
            phone=phone,
            mobile=mobile,
            contact_role="main",
            sync_source=SYNC_LEAD_PRIMARY,
            sort_order=0,
        )
    )
    db.flush()
