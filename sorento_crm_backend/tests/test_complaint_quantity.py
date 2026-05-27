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


def test_complaint_create_accepts_product_lines():
    c = ComplaintCreate(
        customer_name="ACME",
        product_lines=[
            {"product_code": "A", "quantity": "5", "product_type": "T1"},
            {"product_code": "B", "quantity": "3"},
        ],
    )
    assert c.product_lines is not None
    assert [l.product_code for l in c.product_lines] == ["A", "B"]
    assert c.product_lines[0].quantity == "5"
    assert c.product_lines[1].product_type is None


def test_complaint_update_accepts_product_lines():
    u = ComplaintUpdate(product_lines=[{"product_code": "X", "quantity": "2"}])
    dumped = u.model_dump(exclude_unset=True)
    assert "product_lines" in dumped
    assert dumped["product_lines"][0]["product_code"] == "X"
    assert dumped["product_lines"][0]["quantity"] == "2"
