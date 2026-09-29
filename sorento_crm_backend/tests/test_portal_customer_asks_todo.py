"""Sales asks to-do, the portal routes: AC-ST111, AC-ST112 (plus the AC-ST104 field pin).

`GET /api/v1/public/portal/customer-asks/todo` and the #1333 PATCH now stamping `done_by`.
Dependency-override pattern of `test_portal_customer_asks.py`.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.base import set_company_scope
from app.models.price_tag import ContactPortalFormOverride

from . import _ask_todo_seed as seed
from ._ask_todo_seed import SORENTO
from ._pg_fixture import blank_session

BASE = "/api/v1/public/portal/customer-asks"


@pytest.fixture
def w():
    with blank_session() as db:
        set_company_scope(db, frozenset({SORENTO}))
        world = seed.world(db)
        world["stranger"] = seed.contact(db, "Not An Agent")
        world["off_contact"] = seed.contact(db, "Agent Off")
        seed.agent(db, world["off_contact"], "OFF")
        for cid, on in ((world["ca"], True), (world["stranger"], True), (world["off_contact"], False)):
            db.add(ContactPortalFormOverride(contact_id=cid, form_type="customer_asks", is_enabled=on))
        db.flush()
        now = datetime.utcnow()
        world["x_open"] = seed.ask(db, world["x"], world["dealer"], "SRT-X", created_at=now - timedelta(minutes=5))
        world["z_open"] = seed.ask(db, world["z"], world["dealer"], "SRT-Z", created_at=now - timedelta(minutes=5))
        world["done"] = seed.ask(
            db, world["y"], world["dealer"], "SRT-DONE", state="done", done_at=now,
            done_by_contact_id=world["ca"]
        )
        world["db"] = db
        db.commit()
        yield world


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _client(w, contact_id: str) -> TestClient:
    from app.api.v1.public.portal import get_portal_token
    from app.database import get_db
    from app.models.portal import PortalToken
    from app.services.company_scope_resolver import apply_company_scope

    db = w["db"]

    def _override_get_db():
        yield db

    async def _override_scope():
        set_company_scope(db, frozenset({SORENTO}))
        return frozenset({SORENTO})

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[apply_company_scope] = _override_scope
    app.dependency_overrides[get_portal_token] = lambda: PortalToken(
        id=seed.uid(), contact_id=contact_id, space_id="zzt-space"
    )
    return TestClient(app, headers={"X-Portal-Token": "zzt-token"}, raise_server_exceptions=False)


def test_todo_route_gate_and_shape(w):
    resp = _client(w, w["ca"]).get(f"{BASE}/todo")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) >= {"today_start", "open", "done_today", "truncated"}
    assert body["today_start"].endswith("Z")
    assert body["truncated"] is False
    assert [r["id"] for r in body["open"]] == [w["x_open"].id]
    assert [r["id"] for r in body["done_today"]] == [w["done"].id]
    done = body["done_today"][0]
    assert done["done_by"] == "Agent Alpha" and done["done_at"]
    for key in ("customer_id", "contact_id", "product_id"):
        assert key not in done

    stranger = _client(w, w["stranger"]).get(f"{BASE}/todo")
    assert stranger.status_code == 403
    assert stranger.json().get("code") == "NOT_A_SALES_AGENT", stranger.text

    off = _client(w, w["off_contact"]).get(f"{BASE}/todo")
    assert off.status_code == 403
    assert off.json().get("code") == "FORM_TYPE_NOT_VISIBLE", off.text


def _row(w, ask_id):
    from app.models.stock_ask import StockAsk

    w["db"].expire_all()
    return w["db"].get(StockAsk, ask_id)


def test_portal_patch_done_stamps_contact_label(w):
    client = _client(w, w["ca"])
    resp = client.patch(f"{BASE}/{w['x_open'].id}", json={"state": "done"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["done_by"] == "Agent Alpha"
    assert body["done_at"]
    assert not [k for k in body if k.endswith("_id") and k != "id"], body.keys()
    row = _row(w, w["x_open"].id)
    assert row.done_by_contact_id == w["ca"]
    assert row.done_by_user_id is None

    reopened = client.patch(f"{BASE}/{w['x_open'].id}", json={"state": "open"}).json()
    assert reopened["done_at"] is None and reopened["done_by"] is None
    row = _row(w, w["x_open"].id)
    assert (row.done_at, row.done_by_user_id, row.done_by_contact_id) == (None, None, None)

    assert client.patch(f"{BASE}/{w['z_open'].id}", json={"state": "done"}).status_code == 404


def test_portal_patch_with_a_user_linked_to_the_contact_stamps_the_user_too(w):
    from app.models.user import User

    db = w["db"]
    uid = seed.uid()
    db.add(User(id=uid, email=f"{uid}@zzt.test", name="Alpha Person", status="ACTIVE", respond_contact_id=w["ca"]))
    db.commit()
    resp = _client(w, w["ca"]).patch(f"{BASE}/{w['x_open'].id}", json={"state": "done"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["done_by"] == "Alpha Person"
    row = _row(w, w["x_open"].id)
    assert (row.done_by_user_id, row.done_by_contact_id) == (uid, w["ca"])
