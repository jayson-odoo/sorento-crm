"""X-API-Key (MCP / n8n) company-scope resolver matrix — AC-F1/F2/F3 (backend half).

The MCP server and n8n call the CRM with ``X-API-Key`` and, for a contact-scoped
request, ``contact_id`` + ``space_id`` query params. ``resolve_company_scope``
turns those into the four-state scope the ``do_orm_execute`` filter enforces:

  - AC-F1: valid key, NO contact params            -> None  (all companies, back-compat)
  - AC-F2: contact params -> a Mocha-only contact   -> frozenset({mocha})
  - AC-F3: contact params that resolve to no contact / no membership -> frozenset() (0 rows)

Live-DB: seeds a throwaway Mocha company + a Respond workspace/contact/membership
via raw INSERT inside a rolled-back SAVEPOINT (``zzmcp`` marker), so it never
touches real data. The resolver is exercised directly against a synthetic
Starlette ``Request`` (no HTTP server needed).
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.config import settings
from app.database import SessionLocal
from app.models.base import UNSET
from app.models.company import Company
from app.services.company_scope_resolver import resolve_company_scope

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)

# Pin a known key: CI does not set EXTERNAL_API_KEY, so settings.external_api_key
# would be empty and the resolver's constant-time compare would reject every key
# (returning UNSET instead of the None / frozenset this suite asserts).
_API_KEY = "zzt-mcp-scope-test-key"


@pytest.fixture(autouse=True)
def _pin_api_key(monkeypatch):
    monkeypatch.setattr(settings, "external_api_key", _API_KEY)


def _request(*, api_key: str | None, query: str = "") -> Request:
    headers = []
    if api_key is not None:
        headers.append((b"x-api-key", api_key.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/anything",
        "headers": headers,
        "query_string": query.encode(),
    }
    return Request(scope)


@pytest.fixture()
def db() -> Session:
    session = SessionLocal()
    session.begin_nested()  # SAVEPOINT rolled back at teardown
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def mocha_contact(db: Session):
    """Throwaway Mocha company + a Respond workspace/contact that belongs ONLY to
    Mocha. Returns the (respond_io_id, space_id, mocha_company_id)."""
    suffix = uuid.uuid4().hex[:8]
    mocha = Company(id=str(uuid.uuid4()), name=f"ZZMCP Mocha {suffix}", code=f"ZMC{suffix}")
    db.add(mocha)
    db.flush()

    ws_id = str(uuid.uuid4())
    space_id = f"zzmcp-space-{suffix}"
    db.execute(
        text(
            "INSERT INTO respond_workspaces (id, space_id, name, api_key_ciphertext, created_at, updated_at) "
            "VALUES (:id, :sid, :name, :ck, now(), now())"
        ),
        {"id": ws_id, "sid": space_id, "name": f"zzmcp ws {suffix}", "ck": "zzmcp-cipher"},
    )
    contact_pk = str(uuid.uuid4())
    respond_io_id = f"zzmcp-rid-{suffix}"
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, phone_number, respond_io_id, workspace_id, created_at, updated_at) "
            "VALUES (:id, :phone, :rid, :ws, now(), now())"
        ),
        {"id": contact_pk, "phone": f"+60{suffix}", "rid": respond_io_id, "ws": ws_id},
    )
    db.execute(
        text(
            "INSERT INTO respond_contact_companies (id, respond_contact_id, company_id, created_at) "
            "VALUES (:id, :cid, :company, now())"
        ),
        {"id": str(uuid.uuid4()), "cid": contact_pk, "company": mocha.id},
    )
    db.flush()
    return {"respond_io_id": respond_io_id, "space_id": space_id, "mocha": mocha.id}


# --------------------------------------------------------------------------- #
# AC-F1 — valid key, no contact params -> None (all companies)                 #
# --------------------------------------------------------------------------- #
def test_api_key_no_contact_params_is_all_companies(db):
    scope = resolve_company_scope(_request(api_key=_API_KEY), db)
    assert scope is None


# --------------------------------------------------------------------------- #
# AC-F2 — contact params resolve to a Mocha-only contact -> {mocha}            #
# --------------------------------------------------------------------------- #
def test_contact_params_resolve_to_only_that_contacts_company(db, mocha_contact):
    q = f"contact_id={mocha_contact['respond_io_id']}&space_id={mocha_contact['space_id']}"
    scope = resolve_company_scope(_request(api_key=_API_KEY, query=q), db)
    assert scope == frozenset({mocha_contact["mocha"]})


# --------------------------------------------------------------------------- #
# AC-F3 — unresolvable contact params -> empty frozenset (0 rows, fail-closed) #
# --------------------------------------------------------------------------- #
def test_unresolvable_contact_params_is_empty_scope(db):
    q = "contact_id=zzmcp-nope-nobody&space_id=zzmcp-nope-space"
    scope = resolve_company_scope(_request(api_key=_API_KEY, query=q), db)
    assert scope == frozenset()  # empty -> 0 owned rows, never "all"


def test_contact_with_no_membership_is_empty_scope(db, mocha_contact):
    # Same real contact, but strip its company membership: contact matches, yet
    # has no company -> empty scope (0 rows), never a fall-through to all.
    db.execute(text("DELETE FROM respond_contact_companies WHERE respond_contact_id IN "
                    "(SELECT id FROM respond_contacts WHERE respond_io_id = :rid)"),
               {"rid": mocha_contact["respond_io_id"]})
    db.flush()
    q = f"contact_id={mocha_contact['respond_io_id']}&space_id={mocha_contact['space_id']}"
    scope = resolve_company_scope(_request(api_key=_API_KEY, query=q), db)
    assert scope == frozenset()


# --------------------------------------------------------------------------- #
# Guard — an INVALID key never resolves to data                                #
# --------------------------------------------------------------------------- #
def test_invalid_api_key_is_unset(db):
    scope = resolve_company_scope(_request(api_key="definitely-not-the-key"), db)
    assert scope is UNSET


# --------------------------------------------------------------------------- #
# H1 — a JWT/session user's STALE last_active (not granted) never leaks         #
# --------------------------------------------------------------------------- #
def _bearer_request(token: str) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/anything",
        "headers": [(b"authorization", f"Bearer {token}".encode())],
        "query_string": b"",
    }
    return Request(scope)


@pytest.fixture()
def stale_user(db: Session):
    """A regular (non-super) user granted TWO throwaway companies, whose
    ``last_active_company_id`` points at Sorento — a company they are NOT granted
    (models a grant that was revoked but left ``last_active`` stale). Returns the
    session token + the two granted ids."""
    from datetime import datetime, timedelta

    from app.models.user import User
    from app.models.user_session import UserSession

    suffix = uuid.uuid4().hex[:8]
    a = Company(id=str(uuid.uuid4()), name=f"ZZH1 A {suffix}", code=f"ZHA{suffix}")
    b = Company(id=str(uuid.uuid4()), name=f"ZZH1 B {suffix}", code=f"ZHB{suffix}")
    db.add_all([a, b])
    db.flush()

    user = User(
        id=str(uuid.uuid4()),
        email=f"zzh1-{suffix}@t.com",
        name=f"zzh1 {suffix}",
        status="ACTIVE",
        last_active_company_id="00000000-0000-0000-0000-000000000001",  # Sorento, NOT granted
    )
    db.add(user)
    db.flush()
    db.execute(
        text(
            "INSERT INTO user_companies (id, user_id, company_id, created_at) "
            "VALUES (:i1, :u, :a, now()), (:i2, :u, :b, now())"
        ),
        {"i1": str(uuid.uuid4()), "i2": str(uuid.uuid4()), "u": user.id, "a": a.id, "b": b.id},
    )
    token = f"zzh1-token-{suffix}"
    db.add(
        UserSession(
            id=str(uuid.uuid4()),
            token=token,
            user_id=user.id,
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
    )
    db.flush()
    return {"token": token, "granted": {a.id, b.id}}


def test_stale_last_active_resolves_to_granted_never_sorento(db, stale_user):
    scope = resolve_company_scope(_bearer_request(stale_user["token"]), db)
    assert isinstance(scope, frozenset) and len(scope) == 1
    (active,) = tuple(scope)
    assert active in stale_user["granted"]
    assert active != "00000000-0000-0000-0000-000000000001"  # never the stale, non-granted co
    assert active == sorted(stale_user["granted"])[0]  # deterministic lowest granted id
