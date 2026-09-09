"""`companies.so_feed_live` round-trip through the admin API (PLAN
company-so-feed-flag, AC-6): `CompanyForm` defaults it true when omitted,
create/update write it, list/detail serialise it.

TestClient wiring copied from `test_companies_api.py` (same injected-principal
pattern); not imported from there so this file stays runnable on its own.

Run: venv/bin/pytest tests/test_companies_so_feed_live.py -q
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.v1.system.companies import CompanyForm, _serialize_company
from app.models.company import Company, RespondContactCompany, UserCompany
from app.models.user import User

BASE = "/api/v1/system/companies"


@pytest.fixture
def db():
    from tests._pg_fixture import blank_session

    with blank_session() as s:
        yield s


@pytest.fixture
def seed(db):
    """One superadmin; the shared blank schema's incumbent Sorento company is
    cleared first (this suite asserts exact company sets)."""
    db.query(UserCompany).delete()
    db.query(RespondContactCompany).delete()
    db.query(Company).delete()
    superadmin = User(id=str(uuid.uuid4()), email="super@t.com", name="Super", status="ACTIVE")
    db.add(superadmin)
    db.commit()
    return {"superadmin": superadmin.id}


_ACTOR: dict = {"id": None}


@pytest.fixture(autouse=True)
def _patch_roles(monkeypatch, seed):
    from app.services.user_service import UserPermissionService

    superadmin_id = seed["superadmin"]
    monkeypatch.setattr(
        UserPermissionService,
        "get_user_role_slugs",
        lambda self, uid: ({"superadmin"} if str(uid) == superadmin_id else set()),
    )
    yield


@pytest.fixture
def client(db):
    from app.database import get_db
    from app.dependencies import get_current_user
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(_ACTOR)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _as(user_id: str) -> None:
    _ACTOR["id"] = user_id


# ----------------------------------------------------------------- unit level


def test_company_form_defaults_so_feed_live_true_when_omitted():
    form = CompanyForm(name="Third Co", code="TRD")
    assert form.so_feed_live is True


def test_company_form_accepts_so_feed_live_false():
    form = CompanyForm(name="Mocha", code="MCH", so_feed_live=False)
    assert form.so_feed_live is False


def test_serialize_company_emits_the_flag(db):
    company = Company(
        id=str(uuid.uuid4()), name="Mocha", code="MCH-" + uuid.uuid4().hex[:6], so_feed_live=False
    )
    db.add(company)
    db.commit()
    out = _serialize_company(db, company, with_counts=False)
    assert out["so_feed_live"] is False


# ------------------------------------------------------------------ route level


def test_create_with_flag_false(client, seed):
    _as(seed["superadmin"])
    res = client.post(BASE, json={"name": "Mocha", "code": "MCH", "so_feed_live": False})
    assert res.status_code == 201, res.text
    assert res.json()["so_feed_live"] is False


def test_create_omitting_the_flag_defaults_true(client, seed):
    _as(seed["superadmin"])
    res = client.post(BASE, json={"name": "Sorento", "code": "SRT"})
    assert res.status_code == 201, res.text
    assert res.json()["so_feed_live"] is True


def test_update_flips_the_flag(client, seed):
    _as(seed["superadmin"])
    created = client.post(BASE, json={"name": "Mocha", "code": "MCH", "so_feed_live": False}).json()
    res = client.put(
        f"{BASE}/{created['id']}",
        json={"name": "Mocha", "code": "MCH", "so_feed_live": True},
    )
    assert res.status_code == 200, res.text
    assert res.json()["so_feed_live"] is True


def test_list_serialises_the_flag(client, seed):
    _as(seed["superadmin"])
    client.post(BASE, json={"name": "Mocha", "code": "MCH", "so_feed_live": False})
    res = client.get(BASE)
    assert res.status_code == 200, res.text
    row = next(c for c in res.json()["data"] if c["code"] == "MCH")
    assert row["so_feed_live"] is False
