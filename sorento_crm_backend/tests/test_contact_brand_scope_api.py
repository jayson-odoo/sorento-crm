"""Phase 2 RED tests - `GET|PUT /user-management/contacts/{id}/brands` and list rows (AC-2, AC-3).

`PLAN-contact-brand-scope-4oct.md` Slice 3 and test item 8. Same permission harness as
`tests/test_user_management_read_gates.py` (an `allow` set decides the caller's slugs).
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import get_db
from app.dependencies import get_current_user
from app.main import app
from app.models.base import set_company_scope
from app.services.company_scope_resolver import apply_company_scope

from tests._brand_scope_seed import brand, contact, db  # noqa: F401  (db fixture by name)

VIEW = "user_management.contacts.view"
EDIT = "user_management.contacts.edit"
BASE = "/api/v1/user-management/contacts"


@pytest.fixture
def caller(db, monkeypatch):
    """`(client, allow)`: the caller holds exactly the slugs placed in `allow`."""
    from app.services.user_service import UserPermissionService

    allow: set[str] = set()
    principal = {"id": str(uuid.uuid4()), "email": "cbs-caller@zzt.test"}

    def _override_db():
        yield db

    def _override_scope(_db=Depends(get_db)):
        set_company_scope(_db, None)
        return None

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[apply_company_scope] = _override_scope
    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, uid, slug: slug in allow
    )
    try:
        yield TestClient(app), allow
    finally:
        app.dependency_overrides.clear()


def _stored(db, contact_id: str):
    return db.execute(text("SELECT brand_ids FROM respond_contacts WHERE id = :i"), {"i": contact_id}).scalar()


def test_get_returns_ids_and_named_brands(db, caller) -> None:
    """AC-2: `{brand_ids, brands: [{id, brand_name}]}`."""
    client, allow = caller
    allow.add(VIEW)
    b = brand(db, "MOCHA")
    c = contact(db, brand_ids=[b.id])
    db.commit()
    resp = client.get(f"{BASE}/{c.id}/brands")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["brand_ids"] == [str(b.id)], body
    assert body["brands"] == [{"id": str(b.id), "brand_name": b.brand_name}], body


def test_get_unscoped_contact_is_empty(db, caller) -> None:
    client, allow = caller
    allow.add(VIEW)
    c = contact(db)
    db.commit()
    resp = client.get(f"{BASE}/{c.id}/brands")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert {k: body[k] for k in ("brand_ids", "brands", "allowed_item_class_codes")} == {
        "brand_ids": [], "brands": [], "allowed_item_class_codes": []
    }
    assert body["item_class_options"][0] == {"code": "__NONE__", "name": "No class"}
    assert "brand_class_ids" not in body


def test_put_replaces_the_list(db, caller) -> None:
    """AC-2: PUT replaces; the response has the GET shape; the column holds the ids."""
    client, allow = caller
    allow.update({VIEW, EDIT})
    m, s = brand(db, "MOCHA"), brand(db, "SORENTO")
    c = contact(db, brand_ids=[m.id])
    db.commit()
    resp = client.put(f"{BASE}/{c.id}/brands", json={"brand_ids": [s.id]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["brand_ids"] == [str(s.id)]
    assert [str(x) for x in _stored(db, c.id)] == [str(s.id)]


def test_put_empty_list_stores_null(db, caller) -> None:
    """AC-2: `[]` clears to NULL (all brands), not an empty array."""
    client, allow = caller
    allow.update({VIEW, EDIT})
    m = brand(db, "MOCHA")
    c = contact(db, brand_ids=[m.id])
    db.commit()
    resp = client.put(f"{BASE}/{c.id}/brands", json={"brand_ids": []})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert {k: body[k] for k in ("brand_ids", "brands", "allowed_item_class_codes")} == {
        "brand_ids": [], "brands": [], "allowed_item_class_codes": []
    }
    assert body["item_class_options"][0] == {"code": "__NONE__", "name": "No class"}
    assert "brand_class_ids" not in body
    assert _stored(db, c.id) is None


def test_put_unknown_brand_id_is_422_and_changes_nothing(db, caller) -> None:
    client, allow = caller
    allow.update({VIEW, EDIT})
    m = brand(db, "MOCHA")
    c = contact(db, brand_ids=[m.id])
    db.commit()
    resp = client.put(f"{BASE}/{c.id}/brands", json={"brand_ids": [str(uuid.uuid4())]})
    assert resp.status_code == 422, resp.text
    assert [str(x) for x in _stored(db, c.id)] == [str(m.id)]


def test_put_needs_edit_permission(db, caller) -> None:
    """AC-2: view alone is 403 on PUT."""
    client, allow = caller
    allow.add(VIEW)
    m = brand(db, "MOCHA")
    c = contact(db)
    db.commit()
    resp = client.put(f"{BASE}/{c.id}/brands", json={"brand_ids": [m.id]})
    assert resp.status_code == 403, resp.text
    assert _stored(db, c.id) is None


def test_get_needs_view_permission(db, caller) -> None:
    client, allow = caller
    c = contact(db)
    db.commit()
    assert client.get(f"{BASE}/{c.id}/brands").status_code == 403


def test_put_unknown_contact_is_404(db, caller) -> None:
    client, allow = caller
    allow.update({VIEW, EDIT})
    resp = client.put(f"{BASE}/{uuid.uuid4()}/brands", json={"brand_ids": []})
    assert resp.status_code == 404, resp.text
    # the router's bare "Not Found" is a missing ROUTE, which would pass this for the wrong reason
    assert resp.json() != {"detail": "Not Found"}, resp.text


def test_put_malformed_body_is_422(db, caller) -> None:
    client, allow = caller
    allow.update({VIEW, EDIT})
    c = contact(db)
    db.commit()
    assert client.put(f"{BASE}/{c.id}/brands", json={"brand_ids": "nope"}).status_code == 422


def test_list_rows_carry_brands(db, caller) -> None:
    """AC-3: the contacts list rows carry `brands` (response_model must declare it, or it is
    silently dropped); an unscoped contact's row carries an empty list."""
    client, allow = caller
    allow.add(VIEW)
    m = brand(db, "MOCHA")
    scoped = contact(db, brand_ids=[m.id])
    plain = contact(db)
    db.commit()
    resp = client.get(f"{BASE}/", params={"limit": 1000})
    assert resp.status_code == 200, resp.text
    rows = {r["id"]: r for r in resp.json()["data"]}
    assert rows[scoped.id]["brands"] == [{"id": str(m.id), "brand_name": m.brand_name}], rows[scoped.id]
    assert rows[plain.id]["brands"] == [], rows[plain.id]


def test_put_allowed_item_classes_round_trip(db, caller) -> None:
    """TAG-BRAND-CLASS AC-6: the card PUT stores codes upper-cased; a brands-only PUT keeps them;
    an unknown code is a 422 and changes nothing."""
    from app.models.product import ItemClass
    from app.services.company_scope import DEFAULT_COMPANY_ID
    from tests._pg_fixture import unique_code

    client, allow = caller
    allow.update({VIEW, EDIT})
    code = unique_code("DIY", alpha=True).upper()[:50]
    db.add(ItemClass(id=str(uuid.uuid4()), item_class_code=code, item_class_name="ZZT DIY",
                     company_id=DEFAULT_COMPANY_ID))
    c = contact(db)
    db.commit()
    resp = client.put(f"{BASE}/{c.id}/brands", json={"brand_ids": [], "allowed_item_class_codes": [code.lower(), "__NONE__"]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["allowed_item_class_codes"] == ["__NONE__", code]
    m = brand(db, "MOCHA")
    db.commit()
    resp = client.put(f"{BASE}/{c.id}/brands", json={"brand_ids": [m.id]})
    assert resp.json()["allowed_item_class_codes"] == ["__NONE__", code]
    resp = client.put(f"{BASE}/{c.id}/brands", json={"brand_ids": [], "allowed_item_class_codes": ["ZZT-NOPE"]})
    assert resp.status_code == 422, resp.text
    stored = db.execute(text("SELECT allowed_item_class_codes FROM respond_contacts WHERE id = :i"), {"i": c.id}).scalar()
    assert stored == ["__NONE__", code]
