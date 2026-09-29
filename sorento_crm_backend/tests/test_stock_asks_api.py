"""Chatbot stock ask v2 S5, the CRM half: AC-SA505 to AC-SA507.

`GET /api/v1/order-management/customers/{id}/asks` and
`PATCH /api/v1/order-management/customers/{id}/asks/{ask_id}` at route level, so the
permission gate and the company scope are part of what is tested.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from app.models.base import company_scope
from app.models.order import Customer
from app.models.stock_ask import StockAsk

from ._mc_lookup_seed import seed_mocha
from ._pg_fixture import blank_session

VIEW = "order_management.customers.view"
EDIT = "order_management.customers.edit"
SORENTO = "00000000-0000-0000-0000-000000000001"


def _uid() -> str:
    return str(uuid.uuid4())


def _client(db, permissions):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    user_id = _uid()
    actor = {"id": user_id, "email": f"{user_id}@zzt.test", "role": "user"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    app.dependency_overrides[apply_company_scope] = lambda: None
    originals = (
        UserPermissionService.check_user_has_permission,
        UserPermissionService.get_user_permission_slugs,
    )
    granted = list(permissions)
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: slug in granted
    UserPermissionService.get_user_permission_slugs = lambda self, uid: list(granted)
    return TestClient(app, raise_server_exceptions=False), originals


def _restore(originals) -> None:
    from app.main import app
    from app.services.user_service import UserPermissionService

    UserPermissionService.check_user_has_permission = originals[0]
    UserPermissionService.get_user_permission_slugs = originals[1]
    app.dependency_overrides.clear()


def _contact(db, name: str) -> str:
    cid = _uid()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, name, session_vars) "
            "VALUES (:id, :rid, :phone, :name, CAST('{}' AS jsonb))"
        ),
        {"id": cid, "rid": f"ZZT-{_uid()[:8]}", "phone": f"+6004{uuid.uuid4().int % 10**7:07d}", "name": name},
    )
    return cid


def _customer(db, name="Hock Lee Trading", company_id=SORENTO) -> Customer:
    row = Customer(id=_uid(), customer_code=f"ZZT-C-{_uid()[:6]}", customer_name=name, company_id=company_id)
    db.add(row)
    db.flush()
    return row


def _ask(db, customer: Customer | None, contact_id: str | None, *, code="SRT5674", minutes_ago=0, **over) -> StockAsk:
    fields = {"notified_agent": True, **over}
    row = StockAsk(
        id=_uid(),
        company_id=customer.company_id if customer else SORENTO,
        customer_id=customer.id if customer else None,
        contact_id=contact_id,
        product_code=code,
        quantity=50,
        branch="in_stock",
        answer_summary=f"{code} x 50: yes, we have stock, please refer to your salesman to proceed.",
        created_at=datetime.utcnow() - timedelta(minutes=minutes_ago),
        **fields,
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def world():
    with blank_session() as db:
        with company_scope(db, frozenset({SORENTO})):
            contact = _contact(db, "Ah Seng")
            customer = _customer(db)
            other = _customer(db, "Other Trading")
            older = _ask(db, customer, contact, code="SRT-OLD", minutes_ago=30)
            newer = _ask(db, customer, contact, code="SRT-NEW", minutes_ago=1, notified_agent=False, notify_skip_reason="toggle_off")
            foreign = _ask(db, other, contact, code="SRT-OTHER")
            db.commit()
            yield {
                "db": db,
                "customer": customer,
                "other": other,
                "older": older,
                "newer": newer,
                "foreign": foreign,
            }


def _api(world, permissions):
    client, originals = _client(world["db"], permissions)
    # A PATCH to done stamps `done_by_user_id`, an FK on users.id: the actor must be a real row.
    from app.dependencies import get_current_user
    from app.main import app
    from app.models.user import User

    actor = app.dependency_overrides[get_current_user]()
    world["db"].add(User(id=actor["id"], email=actor["email"], name="Office Olive", status="ACTIVE"))
    world["db"].flush()
    return client, originals


def test_ac_sa505_get_lists_newest_first_with_names_not_ids(world):
    client, originals = _api(world, [VIEW])
    try:
        resp = client.get(f"/api/v1/order-management/customers/{world['customer'].id}/asks?page=1&limit=10")
    finally:
        _restore(originals)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [r["product_code"] for r in body["data"]] == ["SRT-NEW", "SRT-OLD"]
    assert body["pagination"]["total"] == 2
    row = body["data"][0]
    assert row["contact_name"] == "Ah Seng"
    assert row["customer_name"] == "Hock Lee Trading"
    assert row["notify_skip_reason"] == "toggle_off"
    assert row["state"] == "open"
    for key in ("contact_id", "product_id", "customer_id", "company_id"):
        assert key not in row, key


def test_ac_sa505_get_is_paged(world):
    client, originals = _api(world, [VIEW])
    try:
        resp = client.get(f"/api/v1/order-management/customers/{world['customer'].id}/asks?page=2&limit=1")
    finally:
        _restore(originals)
    assert resp.status_code == 200
    assert [r["product_code"] for r in resp.json()["data"]] == ["SRT-OLD"]


def test_ac_sa505_get_without_view_is_403(world):
    client, originals = _api(world, [])
    try:
        resp = client.get(f"/api/v1/order-management/customers/{world['customer'].id}/asks")
    finally:
        _restore(originals)
    assert resp.status_code == 403


def test_ac_sa505_a_user_scoped_to_another_company_sees_none(world):
    db = world["db"]
    mocha = seed_mocha(db)
    client, originals = _api(world, [VIEW])
    try:
        with company_scope(db, frozenset({mocha.id})):
            resp = client.get(f"/api/v1/order-management/customers/{world['customer'].id}/asks")
    finally:
        _restore(originals)
    assert resp.status_code == 404
    assert "SRT-NEW" not in resp.text


def test_ac_sa506_patch_persists_state_and_note_and_done_reopens(world):
    client, originals = _api(world, [VIEW, EDIT])
    url = f"/api/v1/order-management/customers/{world['customer'].id}/asks/{world['older'].id}"
    try:
        resp = client.patch(url, json={"state": "done", "note": "Called Ah Seng, quoted 50."})
        assert resp.status_code == 200, resp.text
        assert resp.json()["state"] == "done"
        assert resp.json()["note"] == "Called Ah Seng, quoted 50."
        back = client.patch(url, json={"state": "open"})
        assert back.status_code == 200
        assert back.json()["state"] == "open"
        assert back.json()["note"] == "Called Ah Seng, quoted 50."
    finally:
        _restore(originals)
    world["db"].expire_all()
    row = world["db"].get(StockAsk, world["older"].id)
    assert (row.state, row.note) == ("open", "Called Ah Seng, quoted 50.")


def test_ac_sa506_patch_without_edit_is_403(world):
    client, originals = _api(world, [VIEW])
    try:
        resp = client.patch(
            f"/api/v1/order-management/customers/{world['customer'].id}/asks/{world['older'].id}",
            json={"state": "done"},
        )
    finally:
        _restore(originals)
    assert resp.status_code == 403


def test_ac_sa506_an_ask_of_another_customer_is_404(world):
    client, originals = _api(world, [VIEW, EDIT])
    try:
        resp = client.patch(
            f"/api/v1/order-management/customers/{world['customer'].id}/asks/{world['foreign'].id}",
            json={"state": "done"},
        )
    finally:
        _restore(originals)
    assert resp.status_code == 404


def test_ac_sa506_a_state_outside_open_done_is_422(world):
    client, originals = _api(world, [VIEW, EDIT])
    try:
        resp = client.patch(
            f"/api/v1/order-management/customers/{world['customer'].id}/asks/{world['older'].id}",
            json={"state": "closed"},
        )
    finally:
        _restore(originals)
    assert resp.status_code == 422


def test_ac_sa507_the_list_query_registry_entry_serializes_a_row(world):
    from app.services.list_query_registry import ADAPTERS

    adapter = ADAPTERS["stock_asks"]
    assert adapter.model is StockAsk
    assert adapter.view_slug == VIEW
    # No export (plan "Simplest thing, not built"): a slug no role holds.
    assert adapter.export_slug == "order_management.customers.export"
    from app.rbac.permission_registry import PERMISSION_REGISTRY

    assert adapter.export_slug not in {p["slug"] for p in PERMISSION_REGISTRY}
    out = adapter.serializer([world["older"]])
    assert len(out) == 1
    dumped = out[0].model_dump()
    assert dumped["product_code"] == "SRT-OLD"
    assert dumped["contact_name"] == "Ah Seng"
    assert dumped["customer_name"] == "Hock Lee Trading"


def test_ac_sa507_stock_asks_has_a_uuid_id():
    from sqlalchemy.dialects.postgresql import UUID as PGUUID

    assert isinstance(StockAsk.__table__.c.id.type, PGUUID)
