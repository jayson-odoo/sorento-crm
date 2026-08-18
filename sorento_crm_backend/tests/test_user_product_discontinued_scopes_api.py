"""AC-12, AC-13: the user API's product-discontinued scopes CRUD.

Rides the existing ``GET /user-management/users/{id}`` and
``PUT /user-management/users/{id}`` routes, gated on the same permission the
notification toggles already use (``user_management.users.view`` /
``user_management.users.edit`` - no new slug).

Dependency-override + permission-monkeypatch pattern copied from
tests/test_user_management_read_gates.py.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app.database import get_db
from app.dependencies import get_current_user
from app.main import app
from app.models.base import set_company_scope
from app.models.company import Company
from app.models.product import Brand
from app.models.user import User, UserProductDiscontinuedScope, UserStatus
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.company_scope_resolver import apply_company_scope
from tests._pg_fixture import blank_session, unique_code

SORENTO = DEFAULT_COMPANY_ID
USERS_VIEW = "user_management.users.view"
USERS_EDIT = "user_management.users.edit"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


def _install_overrides(db, caller: dict):
    def _override_db():
        yield db

    def _override_scope(_db=Depends(get_db)):
        set_company_scope(_db, None)
        return None

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: caller
    app.dependency_overrides[apply_company_scope] = _override_scope


def _clear_overrides():
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(apply_company_scope, None)


@pytest.fixture
def api(db, monkeypatch):
    """A caller whose permission set is controlled by the returned `allow` set."""
    from app.services.user_service import UserPermissionService

    allow: set[str] = set()
    caller = {"id": str(uuid.uuid4()), "email": "scopes-caller@zzt.test"}

    _install_overrides(db, caller)
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in allow,
    )
    client = TestClient(app)
    try:
        yield client, allow, caller
    finally:
        _clear_overrides()


def _target_user(db, *, email_pref=True) -> str:
    # A real UUID: /{user_id} routes 404 a non-UUID-shaped path param before the
    # service is ever reached (app.services.uuid_path_param.validate_uuid_path).
    u = User(
        id=str(uuid.uuid4()),
        email=f"{unique_code('target')}@zzt.test",
        name="ZZT Target",
        status=UserStatus.ACTIVE.value,
        notify_email_on_product_discontinued=email_pref,
    )
    db.add(u)
    db.flush()
    return str(u.id)


def _second_company(db) -> str:
    cid = str(uuid.uuid4())
    db.add(Company(id=cid, name="ZZT Mocha", code=unique_code("mch")[:20]))
    db.flush()
    return cid


def _brand(db, *, company_id: str, name: str = "Brand") -> str:
    b = Brand(
        id=str(uuid.uuid4()),
        brand_code=unique_code(name[:4]),
        brand_name=f"ZZT {name}",
        is_active=True,
        company_id=company_id,
    )
    db.add(b)
    db.flush()
    return str(b.id)


# --------------------------------------------------------------------------- #
# AC-13: auth denial - same gate as the toggles
# --------------------------------------------------------------------------- #


def test_get_user_denied_without_users_view(api, db):
    client, allow, _caller = api
    uid = _target_user(db)
    db.commit()

    resp = client.get(f"/api/v1/user-management/users/{uid}")

    assert resp.status_code == 403
    assert USERS_VIEW in resp.json()["detail"]


def test_put_user_scopes_denied_without_users_edit(api, db):
    client, allow, _caller = api
    uid = _target_user(db)
    db.commit()

    resp = client.put(
        f"/api/v1/user-management/users/{uid}",
        json={"product_discontinued_scopes": [{"company_id": None, "brand_id": None}]},
    )

    assert resp.status_code == 403
    assert USERS_EDIT in resp.json()["detail"]


# --------------------------------------------------------------------------- #
# AC-12: GET round-trip - company id+name, brand id+code+name, nulls for all-*
# --------------------------------------------------------------------------- #


def test_get_user_includes_scopes_with_names_not_uuids(api, db):
    client, allow, _caller = api
    allow.add(USERS_VIEW)
    uid = _target_user(db)
    brand_id = _brand(db, company_id=SORENTO, name="Mocha")
    db.add(
        UserProductDiscontinuedScope(
            id=str(uuid.uuid4()), user_id=uid, company_id=SORENTO, brand_id=brand_id
        )
    )
    db.add(
        UserProductDiscontinuedScope(id=str(uuid.uuid4()), user_id=uid, company_id=None, brand_id=None)
    )
    db.commit()

    resp = client.get(f"/api/v1/user-management/users/{uid}")

    assert resp.status_code == 200
    scopes = resp.json()["product_discontinued_scopes"]
    assert len(scopes) == 2
    all_all = next(s for s in scopes if s["company_id"] is None)
    assert all_all["brand_id"] is None
    assert all_all["company_name"] is None
    specific = next(s for s in scopes if s["company_id"] is not None)
    assert specific["company_id"] == SORENTO
    assert specific["company_name"]
    assert specific["brand_id"] == brand_id
    assert specific["brand_name"] == "ZZT Mocha"
    assert "brand_code" in specific


# --------------------------------------------------------------------------- #
# AC-12: PUT replace-all semantics
# --------------------------------------------------------------------------- #


def test_put_omitted_scopes_leaves_existing_untouched(api, db):
    client, allow, _caller = api
    allow.update({USERS_VIEW, USERS_EDIT})
    uid = _target_user(db)
    db.add(
        UserProductDiscontinuedScope(id=str(uuid.uuid4()), user_id=uid, company_id=None, brand_id=None)
    )
    db.commit()

    resp = client.put(f"/api/v1/user-management/users/{uid}", json={"name": "Renamed"})

    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed"
    assert len(resp.json()["product_discontinued_scopes"]) == 1


def test_put_empty_list_clears_every_scope(api, db):
    client, allow, _caller = api
    allow.update({USERS_VIEW, USERS_EDIT})
    uid = _target_user(db)
    db.add(
        UserProductDiscontinuedScope(id=str(uuid.uuid4()), user_id=uid, company_id=None, brand_id=None)
    )
    db.commit()

    resp = client.put(
        f"/api/v1/user-management/users/{uid}",
        json={"product_discontinued_scopes": []},
    )

    assert resp.status_code == 200
    assert resp.json()["product_discontinued_scopes"] == []


def test_put_replaces_the_whole_set_and_dedupes(api, db):
    client, allow, _caller = api
    allow.update({USERS_VIEW, USERS_EDIT})
    uid = _target_user(db)
    brand_id = _brand(db, company_id=SORENTO, name="Mocha")
    db.commit()

    resp = client.put(
        f"/api/v1/user-management/users/{uid}",
        json={
            "product_discontinued_scopes": [
                {"company_id": SORENTO, "brand_id": brand_id},
                {"company_id": SORENTO, "brand_id": brand_id},  # duplicate
            ]
        },
    )

    assert resp.status_code == 200
    scopes = resp.json()["product_discontinued_scopes"]
    assert len(scopes) == 1
    assert scopes[0]["brand_id"] == brand_id


def test_put_all_companies_forces_brand_null_even_if_one_was_sent(api, db):
    client, allow, _caller = api
    allow.update({USERS_VIEW, USERS_EDIT})
    uid = _target_user(db)
    brand_id = _brand(db, company_id=SORENTO, name="Mocha")
    db.commit()

    resp = client.put(
        f"/api/v1/user-management/users/{uid}",
        json={"product_discontinued_scopes": [{"company_id": None, "brand_id": brand_id}]},
    )

    assert resp.status_code == 200
    scopes = resp.json()["product_discontinued_scopes"]
    assert len(scopes) == 1
    assert scopes[0]["company_id"] is None
    assert scopes[0]["brand_id"] is None


# --------------------------------------------------------------------------- #
# AC-12: validation (422) - unknown company, unknown brand, brand/company mismatch
# --------------------------------------------------------------------------- #


def test_put_unknown_company_id_is_422(api, db):
    client, allow, _caller = api
    allow.update({USERS_VIEW, USERS_EDIT})
    uid = _target_user(db)
    db.commit()
    ghost = str(uuid.uuid4())

    resp = client.put(
        f"/api/v1/user-management/users/{uid}",
        json={"product_discontinued_scopes": [{"company_id": ghost, "brand_id": None}]},
    )

    assert resp.status_code == 422


def test_put_unknown_brand_id_is_422(api, db):
    client, allow, _caller = api
    allow.update({USERS_VIEW, USERS_EDIT})
    uid = _target_user(db)
    db.commit()
    ghost = str(uuid.uuid4())

    resp = client.put(
        f"/api/v1/user-management/users/{uid}",
        json={"product_discontinued_scopes": [{"company_id": SORENTO, "brand_id": ghost}]},
    )

    assert resp.status_code == 422


def test_put_brand_outside_the_named_company_is_422(api, db):
    client, allow, _caller = api
    allow.update({USERS_VIEW, USERS_EDIT})
    uid = _target_user(db)
    mocha = _second_company(db)
    brand_in_mocha = _brand(db, company_id=mocha, name="MochaOnly")
    db.commit()

    resp = client.put(
        f"/api/v1/user-management/users/{uid}",
        json={"product_discontinued_scopes": [{"company_id": SORENTO, "brand_id": brand_in_mocha}]},
    )

    assert resp.status_code == 422


def test_put_a_rejected_scope_list_leaves_the_profile_update_unapplied(api, db):
    """The scopes are validated before the shared commit, so a bad scope list
    does not leave a half-applied name change behind."""
    client, allow, _caller = api
    allow.update({USERS_VIEW, USERS_EDIT})
    uid = _target_user(db)
    db.commit()
    ghost = str(uuid.uuid4())

    resp = client.put(
        f"/api/v1/user-management/users/{uid}",
        json={"name": "Should Not Stick", "product_discontinued_scopes": [{"company_id": ghost}]},
    )

    assert resp.status_code == 422
    # Nothing was committed, so the failed request's own uncommitted setattr on
    # the shared test session's identity-mapped object would otherwise leak into
    # the read below even though the DB itself was never touched - roll it back
    # the way a fresh per-request session (production's real shape) would never
    # have seen it in the first place.
    db.rollback()
    check = client.get(f"/api/v1/user-management/users/{uid}")
    assert check.status_code == 200
    assert check.json()["name"] != "Should Not Stick"
