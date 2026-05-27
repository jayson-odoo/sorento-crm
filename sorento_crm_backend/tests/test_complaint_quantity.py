"""Complaint quantity field plumbing.

The complaint form was missing a quantity field. It must be accepted by the
create/update schemas and carried through from the external integration payload
(which already accepted but silently dropped it).
"""
from __future__ import annotations

from app.schemas.complaints import ComplaintCreate, ComplaintUpdate


def test_complaint_create_accepts_quantity():
    c = ComplaintCreate(customer_name="ACME", quantity="5")
    assert c.quantity == "5"


def test_complaint_update_accepts_quantity():
    u = ComplaintUpdate(quantity="12 boxes")
    assert "quantity" in u.model_dump(exclude_unset=True)
    assert u.quantity == "12 boxes"


def test_external_complaint_payload_maps_quantity():
    from app.schemas.external.complaints import ComplaintIntegrationCreate

    payload = ComplaintIntegrationCreate.model_validate(
        {"customer_name": "ACME", "quantity": 7, "contact_id": "c1", "space_id": "s1"}
    )
    created = payload.to_complaint_create()
    assert created.quantity == "7"
