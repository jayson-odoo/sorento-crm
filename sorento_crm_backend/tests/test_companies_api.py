"""Companies admin + my-context/switch endpoint tests (multi-company isolation).

Phase-2 route-layer coverage for app/api/v1/system/companies.py — the backend half
of UAC groups A/B:
  - AC-A: list (superadmin sees ALL; a regular user sees only granted).
  - AC-A4: create → 403 for a non-superadmin.
  - AC-B4/B5: switch validates the grant (403 when not granted) + persists
    users.last_active_company_id.
  - AC-B8: my-context shape ({ companies, active_company_id, last_active_company_id }).

Runs against an in-memory sqlite bind (CLAUDE.md "sqlite pytest fixtures" gotcha):
pg ``UUID(as_uuid=False)`` works as-is; JSONB/ARRAY columns are swapped to JSON.
``UserPermissionService.get_user_role_slugs`` is monkeypatched (no role tables are
seeded); the request principal is injected via ``get_current_user`` override.

Run: venv/bin/pytest tests/test_companies_api.py -q
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.access import RespondContact
from app.models.company import Company, RespondContactCompany, UserCompany
from app.models.user import User

BASE = "/api/v1/system/companies"


# --------------------------------------------------------------------------- #
# sqlite fixture                                                               #
# --------------------------------------------------------------------------- #
@pytest.fixture
def db():
    # Postgres blank schema (the suite is Postgres-only; no sqlite, no shared-
    # metadata mutation which leaks column types into other tests' blank schema).
    from tests._pg_fixture import blank_session

    with blank_session() as s:
        yield s


@pytest.fixture
def seed(db):
    """Two companies (Sorento, Mocha); a superadmin; a regular user granted Sorento
    only, with last_active = Sorento; one respond contact."""
    # The shared blank schema is seeded with the incumbent Sorento company (so
    # other suites' owned inserts satisfy the FK). This suite asserts exact company
    # counts/codes, so clear it inside this rolled-back transaction first.
    db.query(UserCompany).delete()
    db.query(RespondContactCompany).delete()
    db.query(Company).delete()
    srt = Company(id=str(uuid.uuid4()), name="Sorento", code="SRT")
    mch = Company(id=str(uuid.uuid4()), name="Mocha", code="MCH")
    db.add_all([srt, mch])

    superadmin = User(id=str(uuid.uuid4()), email="super@t.com", name="Super", status="ACTIVE")
    regular = User(
        id=str(uuid.uuid4()),
        email="reg@t.com",
        name="Reg",
        status="ACTIVE",
        last_active_company_id=srt.id,
    )
    db.add_all([superadmin, regular])
    db.flush()

    db.add(UserCompany(id=str(uuid.uuid4()), user_id=regular.id, company_id=srt.id))
    db.add(
        RespondContact(id=str(uuid.uuid4()), phone_number="+60111", name="Ken", session_vars={})
    )
    db.commit()
    return {
        "srt": srt.id,
        "mch": mch.id,
        "superadmin": superadmin.id,
        "regular": regular.id,
    }


# --------------------------------------------------------------------------- #
# TestClient wiring — injected principal + patched role slugs                  #
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# AC-A — list                                                                  #
# --------------------------------------------------------------------------- #
def test_list_superadmin_sees_all(client, seed):
    _as(seed["superadmin"])
    res = client.get(BASE)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["pagination"]["total"] == 2
    codes = {c["code"] for c in body["data"]}
    assert codes == {"SRT", "MCH"}
    # Derived counts present for the admin list.
    srt = next(c for c in body["data"] if c["code"] == "SRT")
    assert srt["user_count"] == 1 and srt["contact_count"] == 0


def test_list_regular_user_sees_only_granted(client, seed):
    _as(seed["regular"])
    res = client.get(BASE)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["pagination"]["total"] == 1
    assert [c["code"] for c in body["data"]] == ["SRT"]


# --------------------------------------------------------------------------- #
# AC-A4 — create authorization                                                 #
# --------------------------------------------------------------------------- #
def test_create_forbidden_for_non_superadmin(client, seed):
    _as(seed["regular"])
    res = client.post(BASE, json={"name": "New Co", "code": "NEW"})
    assert res.status_code == 403, res.text


def test_create_ok_for_superadmin(client, seed):
    _as(seed["superadmin"])
    res = client.post(BASE, json={"name": "Third Co", "code": "TRD"})
    assert res.status_code == 201, res.text
    assert res.json()["code"] == "TRD"


def test_create_duplicate_code_conflicts(client, seed):
    _as(seed["superadmin"])
    res = client.post(BASE, json={"name": "Dup", "code": "SRT"})
    assert res.status_code == 409, res.text


# --------------------------------------------------------------------------- #
# AC-B4/B5 — switch validates grant + persists last_active                     #
# --------------------------------------------------------------------------- #
def test_switch_to_granted_persists_last_active(client, seed, db):
    _as(seed["regular"])
    res = client.post(f"{BASE}/switch", json={"company_id": seed["srt"]})
    assert res.status_code == 200, res.text
    assert res.json()["active_company_id"] == seed["srt"]
    db.expire_all()
    user = db.query(User).filter(User.id == seed["regular"]).first()
    assert str(user.last_active_company_id) == seed["srt"]


def test_switch_to_non_granted_forbidden(client, seed, db):
    _as(seed["regular"])
    res = client.post(f"{BASE}/switch", json={"company_id": seed["mch"]})
    assert res.status_code == 403, res.text


def test_superadmin_switch_to_any_company(client, seed, db):
    _as(seed["superadmin"])
    res = client.post(f"{BASE}/switch", json={"company_id": seed["mch"]})
    assert res.status_code == 200, res.text
    assert res.json()["active_company_id"] == seed["mch"]


# --------------------------------------------------------------------------- #
# AC-B8 — my-context shape                                                      #
# --------------------------------------------------------------------------- #
def test_my_context_regular_user_shape(client, seed):
    _as(seed["regular"])
    res = client.get(f"{BASE}/my-context")
    assert res.status_code == 200, res.text
    body = res.json()
    assert set(body.keys()) == {"companies", "active_company_id", "last_active_company_id"}
    assert [c["code"] for c in body["companies"]] == ["SRT"]
    assert body["active_company_id"] == seed["srt"]
    assert body["last_active_company_id"] == seed["srt"]


def test_my_context_superadmin_sees_all_companies(client, seed):
    _as(seed["superadmin"])
    res = client.get(f"{BASE}/my-context")
    assert res.status_code == 200, res.text
    body = res.json()
    assert {c["code"] for c in body["companies"]} == {"SRT", "MCH"}


# --------------------------------------------------------------------------- #
# H1 — a STALE last_active (not in grants) must NEVER resolve as active         #
# --------------------------------------------------------------------------- #
def test_my_context_stale_last_active_never_resolves_non_granted(client, seed, db):
    """A user with >1 grants whose last_active points at a company they are NOT
    granted (e.g. left over after a revoke) must resolve to a GRANTED company —
    never the stale one. Before the H1 fix the `elif last_active` fallback picked
    the non-granted company; after, it deterministically picks a granted id."""
    third = Company(id=str(uuid.uuid4()), name="Third", code="TRD")
    db.add(third)
    stale_user = User(
        id=str(uuid.uuid4()),
        email="stale@t.com",
        name="Stale",
        status="ACTIVE",
        last_active_company_id=seed["srt"],  # granted to mch+third, NOT srt
    )
    db.add(stale_user)
    db.flush()
    db.add(UserCompany(id=str(uuid.uuid4()), user_id=stale_user.id, company_id=seed["mch"]))
    db.add(UserCompany(id=str(uuid.uuid4()), user_id=stale_user.id, company_id=third.id))
    db.commit()

    _as(stale_user.id)
    res = client.get(f"{BASE}/my-context")
    assert res.status_code == 200, res.text
    body = res.json()
    granted = {seed["mch"], third.id}
    assert body["active_company_id"] in granted
    assert body["active_company_id"] != seed["srt"]  # never the stale, non-granted co
    assert body["active_company_id"] == sorted(granted)[0]  # deterministic lowest


# --------------------------------------------------------------------------- #
# H1 — removing a grant that is the user's last_active repoints/nulls it        #
# --------------------------------------------------------------------------- #
def test_remove_company_user_clears_stale_last_active(client, seed, db):
    user = User(
        id=str(uuid.uuid4()),
        email="revoke@t.com",
        name="Revoke",
        status="ACTIVE",
        last_active_company_id=seed["mch"],
    )
    db.add(user)
    db.flush()
    db.add(UserCompany(id=str(uuid.uuid4()), user_id=user.id, company_id=seed["srt"]))
    db.add(UserCompany(id=str(uuid.uuid4()), user_id=user.id, company_id=seed["mch"]))
    db.commit()

    _as(seed["superadmin"])
    res = client.delete(f"{BASE}/{seed['mch']}/users/{user.id}")
    assert res.status_code == 200, res.text

    db.expire_all()
    refreshed = db.query(User).filter(User.id == user.id).first()
    # last_active (mch) was revoked -> repointed to the remaining grant (srt).
    assert str(refreshed.last_active_company_id) == seed["srt"]

    _as(user.id)
    ctx = client.get(f"{BASE}/my-context").json()
    assert ctx["active_company_id"] == seed["srt"]
    assert ctx["active_company_id"] != seed["mch"]


def test_remove_last_grant_nulls_last_active(client, seed, db):
    user = User(
        id=str(uuid.uuid4()),
        email="onlygrant@t.com",
        name="Only",
        status="ACTIVE",
        last_active_company_id=seed["mch"],
    )
    db.add(user)
    db.flush()
    db.add(UserCompany(id=str(uuid.uuid4()), user_id=user.id, company_id=seed["mch"]))
    db.commit()

    _as(seed["superadmin"])
    res = client.delete(f"{BASE}/{seed['mch']}/users/{user.id}")
    assert res.status_code == 200, res.text

    db.expire_all()
    refreshed = db.query(User).filter(User.id == user.id).first()
    assert refreshed.last_active_company_id is None  # no grants left -> null
