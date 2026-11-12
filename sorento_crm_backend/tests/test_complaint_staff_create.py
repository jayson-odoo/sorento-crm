"""COMPLAINT-CREATE-500: a staff user creates a complaint through the standard body.

The staff "Create complaint" modal posts a plain ComplaintCreate body to
POST /api/v1/complaints-management/complaints/. That path calls the "was this an external
API key request" check at two points (requires_user_confirm, should_notify_handlers); the
helper's definition was dropped from complaints.py on 20 May while both callers stayed, so
every staff create answered 500 with a NameError. Integration payloads short-circuit before
the call and were never affected.

Harness: tests/_forms_chain_support.py (real routes, blank Postgres scratch schema).
All names are invented.
"""
from __future__ import annotations

import typing
import uuid

from tests._forms_chain_support import (
    CX_BASE,
    MARKER,
    user,
    world,  # noqa: F401  (fixture)
)

ZZT_KEY = "zzt-external-key"


def _delivery_order(db) -> str:
    """The staff modal picks a real DO number; the route checks it against orders."""
    from app.models.order import Order

    number = f"ZZTDO-{uuid.uuid4().hex[:8]}"
    db.add(Order(id=str(uuid.uuid4()), order_number=number))
    db.commit()
    return number


def _staff_body(do_number: str, **over):
    """A complete standard ComplaintCreate body, the shape the staff Create modal posts."""
    body = {
        "delivery_order_number": do_number,
        "complaint_date": "2026-11-12",
        "customer_name": f"{MARKER} customer",
        "customer_type": "dealer",
        "customer_address": "1 Zzt Road",
        "contact_person": f"{MARKER} contact",
        "contact_number": "0000000",
        "product_code": f"{MARKER}-P1",
        "product_type": "basin",
        "complaint_type": "Broken",
        "defect_description": "cracked edge on delivery",
        "defects_discovered": "on delivery",
        "within_warranty": "Yes",
        "salesperson": f"{MARKER} salesperson",
        "project_title": f"{MARKER} project",
        "contact_id": "zzt-contact",
        "space_id": "zzt-space",
        "quantity": "2",
    }
    body.update(over)
    return body


def test_staff_user_creates_a_complaint_with_the_standard_body(world):
    w = world
    staff = user(w.db, "complaint creator")
    res = w.as_user(staff).post(f"{CX_BASE}/", json=_staff_body(_delivery_order(w.db)))
    assert res.status_code == 201, res.text
    created = res.json()
    assert created["customer_name"] == f"{MARKER} customer"
    assert created["product_code"] == f"{MARKER}-P1"


def test_staff_create_does_not_notify_handlers_as_external(world, monkeypatch):
    """should_notify_handlers: a staff create without an API key is not an external create."""
    from app.services.complaints_service import ComplaintService

    calls: list[str] = []
    monkeypatch.setattr(
        ComplaintService,
        "notify_team_complaint_external_created",
        lambda self, complaint_id, **kw: calls.append(complaint_id),
    )
    w = world
    staff = user(w.db, "complaint creator")
    res = w.as_user(staff).post(f"{CX_BASE}/", json=_staff_body(_delivery_order(w.db)))
    assert res.status_code == 201, res.text
    assert calls == []


def test_external_api_key_request_needs_confirmation_then_notifies(world, monkeypatch):
    """Both call sites with the key present: requires_user_confirm asks for confirmation, then
    should_notify_handlers notifies."""
    from app.config import settings
    from app.services.complaints_service import ComplaintService

    monkeypatch.setattr(settings, "external_api_key", ZZT_KEY, raising=False)
    calls: list[str] = []
    monkeypatch.setattr(
        ComplaintService,
        "notify_team_complaint_external_created",
        lambda self, complaint_id, **kw: calls.append(complaint_id),
    )
    w = world
    staff = user(w.db, "complaint creator")
    c = w.as_user(staff)
    headers = {"X-API-Key": ZZT_KEY}
    do_number = _delivery_order(w.db)

    unconfirmed = c.post(f"{CX_BASE}/", json=_staff_body(do_number), headers=headers)
    assert unconfirmed.status_code == 400, unconfirmed.text
    assert "Explicit user confirmation" in unconfirmed.text

    confirmed = c.post(f"{CX_BASE}/", json=_staff_body(do_number, user_confirmed=True), headers=headers)
    assert confirmed.status_code == 201, confirmed.text
    assert calls == [confirmed.json()["id"]]


def test_do_lookup_date_range_annotations_resolve():
    """_resolve_do_lookup_date_range annotates with "datetime", a name the module must hold."""
    from app.api.v1.complaints import complaints

    hints = typing.get_type_hints(complaints._resolve_do_lookup_date_range)
    assert "return" in hints
