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

from tests._forms_chain_support import (
    CX_BASE,
    MARKER,
    user,
    world,  # noqa: F401  (fixture)
)

ZZT_KEY = "zzt-external-key"


def _staff_body(**over):
    body = {
        "complaint_date": "2026-11-12",
        "customer_name": f"{MARKER} customer",
        "product_code": f"{MARKER}-P1",
        "defect_description": "cracked edge on delivery",
        "quantity": "2",
    }
    body.update(over)
    return body


def test_staff_user_creates_a_complaint_with_the_standard_body(world):
    w = world
    staff = user(w.db, "complaint creator")
    res = w.as_user(staff).post(f"{CX_BASE}/", json=_staff_body())
    assert res.status_code == 201, res.text
    created = res.json()
    assert created["customer_name"] == f"{MARKER} customer"
    assert created["product_code"] == f"{MARKER}-P1"


def test_staff_create_does_not_notify_handlers_as_external(world, monkeypatch):
    """Line :1175 path: a staff create without an API key is not an external create."""
    from app.services.complaints_service import ComplaintService

    calls: list[str] = []
    monkeypatch.setattr(
        ComplaintService,
        "notify_team_complaint_external_created",
        lambda self, complaint_id, **kw: calls.append(complaint_id),
    )
    w = world
    staff = user(w.db, "complaint creator")
    res = w.as_user(staff).post(f"{CX_BASE}/", json=_staff_body())
    assert res.status_code == 201, res.text
    assert calls == []


def test_external_api_key_request_needs_confirmation_then_notifies(world, monkeypatch):
    """Both call sites with the key present: :1102 asks for user confirmation, :1175 notifies."""
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

    unconfirmed = c.post(f"{CX_BASE}/", json=_staff_body(), headers=headers)
    assert unconfirmed.status_code == 400, unconfirmed.text
    assert "Explicit user confirmation" in unconfirmed.text

    confirmed = c.post(f"{CX_BASE}/", json=_staff_body(user_confirmed=True), headers=headers)
    assert confirmed.status_code == 201, confirmed.text
    assert calls == [confirmed.json()["id"]]


def test_do_lookup_date_range_annotations_resolve():
    """complaints.py:791/795 annotate with "datetime", which must be a name the module holds."""
    from app.api.v1.complaints import complaints

    hints = typing.get_type_hints(complaints._resolve_do_lookup_date_range)
    assert "return" in hints
