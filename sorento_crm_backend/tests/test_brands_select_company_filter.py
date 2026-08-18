"""GET /api/v1/master-data/brands/select?company_id= (S2 note on the plan).

Exists for the product-discontinued scope editor: an admin sets a user's brand
scopes for companies they are not currently switched into, so the endpoint must
be able to widen WHICH company is read - but never WHO may read it. Mirrors
``system/companies.get_company``: superadmin/admin and the API-key principal
reach every company; everyone else only a company they hold a
``user_companies`` grant for. Omitting the param is unchanged (active-company
scope, the pre-existing default).
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app.database import get_db
from app.dependencies import get_current_user_or_api_key
from app.main import app
from app.models.base import set_company_scope
from app.models.company import Company, UserCompany
from app.models.product import Brand
from app.models.user import User, UserStatus
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.company_scope_resolver import apply_company_scope
from tests._pg_fixture import blank_session, unique_code

SORENTO = DEFAULT_COMPANY_ID
BRANDS_VIEW = "master_data.brands.view"


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
    app.dependency_overrides[get_current_user_or_api_key] = lambda: caller
    app.dependency_overrides[apply_company_scope] = _override_scope


def _clear_overrides():
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user_or_api_key, None)
    app.dependency_overrides.pop(apply_company_scope, None)


@pytest.fixture
def api(db, monkeypatch):
    from app.services.user_service import UserPermissionService

    allow = {BRANDS_VIEW}
    # A real users row: UserCompany.user_id is a NOT NULL FK, and the grant test
    # needs to insert one against this caller.
    user = User(
        id=str(uuid.uuid4()),
        email=f"{unique_code('brandscaller')}@zzt.test",
        name="ZZT Brands Caller",
        status=UserStatus.ACTIVE.value,
    )
    db.add(user)
    db.flush()
    caller = {"id": str(user.id), "email": user.email}

    _install_overrides(db, caller)
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in allow,
    )
    # No role grants unless a test adds one: superadmin/admin bypass is exercised
    # explicitly via monkeypatching get_user_role_slugs below.
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    client = TestClient(app)
    try:
        yield client, caller
    finally:
        _clear_overrides()


def _second_company(db, name="Mocha") -> str:
    cid = str(uuid.uuid4())
    db.add(Company(id=cid, name=f"ZZT {name}", code=unique_code(name[:3])[:20]))
    db.flush()
    return cid


def _brand(db, *, company_id: str, name: str) -> str:
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


def _grant(db, user_id: str, company_id: str):
    db.add(UserCompany(id=str(uuid.uuid4()), user_id=user_id, company_id=company_id))
    db.flush()


def test_omit_company_id_keeps_the_pre_existing_active_scope_default(api, db):
    """Session scope is pinned to Sorento by _override_scope's set_company_scope,
    but this route asks for None explicitly - so brands.py's own default (the
    caller's active-company read) is what governs, unchanged from before."""
    client, _caller = api
    _brand(db, company_id=SORENTO, name="Home")
    db.commit()

    resp = client.get("/api/v1/master-data/brands/select")

    assert resp.status_code == 200
    assert any(b["brand_name"] == "ZZT Home" for b in resp.json())


def test_company_id_widens_to_a_company_the_caller_is_granted(api, db):
    client, caller = api
    mocha = _second_company(db)
    _brand(db, company_id=mocha, name="MochaOnly")
    _grant(db, caller["id"], mocha)
    db.commit()

    resp = client.get(f"/api/v1/master-data/brands/select?company_id={mocha}")

    assert resp.status_code == 200
    names = {b["brand_name"] for b in resp.json()}
    assert "ZZT MochaOnly" in names


def test_company_id_the_caller_is_not_granted_reads_as_not_found(api, db):
    client, _caller = api
    mocha = _second_company(db)
    _brand(db, company_id=mocha, name="MochaOnly")
    db.commit()
    # No UserCompany grant for this caller.

    resp = client.get(f"/api/v1/master-data/brands/select?company_id={mocha}")

    assert resp.status_code == 404


def test_superadmin_reaches_a_company_with_no_grant(api, db, monkeypatch):
    from app.services.user_service import UserPermissionService

    client, _caller = api
    mocha = _second_company(db)
    _brand(db, company_id=mocha, name="MochaOnly")
    db.commit()

    monkeypatch.setattr(
        UserPermissionService,
        "get_user_role_slugs",
        lambda self, uid: {UserPermissionService.SUPERADMIN_ROLE_SLUG},
    )

    resp = client.get(f"/api/v1/master-data/brands/select?company_id={mocha}")

    assert resp.status_code == 200
    names = {b["brand_name"] for b in resp.json()}
    assert "ZZT MochaOnly" in names


def test_a_nonexistent_company_id_is_not_found_even_for_a_superadmin(api, db, monkeypatch):
    from app.services.user_service import UserPermissionService

    client, _caller = api
    monkeypatch.setattr(
        UserPermissionService,
        "get_user_role_slugs",
        lambda self, uid: {UserPermissionService.SUPERADMIN_ROLE_SLUG},
    )
    ghost = str(uuid.uuid4())

    resp = client.get(f"/api/v1/master-data/brands/select?company_id={ghost}")

    assert resp.status_code == 404


def test_api_key_principal_is_unscoped(api, db):
    client, caller = api
    mocha = _second_company(db)
    _brand(db, company_id=mocha, name="MochaOnly")
    db.commit()
    caller["auth_method"] = "api_key"

    resp = client.get(f"/api/v1/master-data/brands/select?company_id={mocha}")

    assert resp.status_code == 200
    names = {b["brand_name"] for b in resp.json()}
    assert "ZZT MochaOnly" in names
