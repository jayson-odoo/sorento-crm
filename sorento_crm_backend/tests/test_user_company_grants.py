"""UserService company-grant tests (multi-company follow-up).

Covers the user_companies grant wiring added to the Add/Edit User flow:
 - create_user(company_ids=[SRT, MCH]) → two user_companies rows; a SINGLE
    company also becomes the user's last_active_company_id landing default.
 - invite_user(company_ids=[...]) → same grant behaviour.
 - set_user_companies() replaces the whole grant set and repoints
    last_active_company_id when the previous active grant is revoked.
 - Unknown company ids are silently skipped.

Runs against an in-memory sqlite bind (CLAUDE.md "sqlite pytest fixtures" gotcha):
pg ``UUID(as_uuid=False)`` works as-is; JSONB/ARRAY columns are swapped to JSON.
``lookup_bindings`` is created so a globally-registered lookup-validator listener
(fired when the whole suite runs) doesn't error on our inserts.

Run: venv/bin/pytest tests/test_user_company_grants.py -q
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.company import Company, RespondContactCompany, UserCompany
from app.models.lookup import LookupBinding
from app.models.user import User, UserRole, UserRoleAssignment
from app.schemas.user import UserCreate
from app.services.user_service import UserService


@pytest.fixture
def db():
    # Postgres blank schema (the suite is Postgres-only; no sqlite, no shared-
    # metadata mutation which leaks column types into other tests' blank schema).
    from tests._pg_fixture import blank_session

    with blank_session() as s:
        yield s


@pytest.fixture
def companies(db):
    srt = Company(id=str(uuid.uuid4()), name="Sorento", code="ZZSRT")
    mch = Company(id=str(uuid.uuid4()), name="Mocha", code="ZZMCH")
    db.add_all([srt, mch])
    db.commit()
    return {"srt": srt.id, "mch": mch.id}


def _grant_ids(db, user_id: str) -> set[str]:
    return {
        str(r[0])
        for r in db.query(UserCompany.company_id)
        .filter(UserCompany.user_id == user_id)
        .all()
    }


# --------------------------------------------------------------------------- #
# create_user                                                                  #
# --------------------------------------------------------------------------- #
def test_create_user_grants_two_companies_no_landing_default(db, companies):
    svc = UserService(db)
    user = svc.create_user(
        UserCreate(
            email="two@t.com",
            name="Two",
            company_ids=[companies["srt"], companies["mch"]],
        )
    )
    assert _grant_ids(db, user.id) == {companies["srt"], companies["mch"]}
    # Two companies -> no single landing default.
    assert user.last_active_company_id is None


def test_create_user_single_company_sets_landing_default(db, companies):
    svc = UserService(db)
    user = svc.create_user(
        UserCreate(email="one@t.com", name="One", company_ids=[companies["srt"]])
    )
    assert _grant_ids(db, user.id) == {companies["srt"]}
    assert str(user.last_active_company_id) == companies["srt"]


def test_create_user_skips_unknown_company_id(db, companies):
    svc = UserService(db)
    ghost = str(uuid.uuid4())
    user = svc.create_user(
        UserCreate(
            email="ghost@t.com",
            name="Ghost",
            company_ids=[companies["srt"], ghost],
        )
    )
    assert _grant_ids(db, user.id) == {companies["srt"]}


def test_create_user_no_company_ids_grants_nothing(db, companies):
    svc = UserService(db)
    user = svc.create_user(UserCreate(email="none@t.com", name="None"))
    assert _grant_ids(db, user.id) == set()
    assert user.last_active_company_id is None


# --------------------------------------------------------------------------- #
# invite_user                                                                  #
# --------------------------------------------------------------------------- #
def test_invite_user_grants_companies(db, companies):
    svc = UserService(db)
    inviter = str(uuid.uuid4())
    user = svc.invite_user(
        UserCreate(
            email="inv@t.com",
            name="Inv",
            company_ids=[companies["srt"], companies["mch"]],
        ),
        invited_by_user_id=inviter,
    )
    assert _grant_ids(db, user.id) == {companies["srt"], companies["mch"]}
    assert user.last_active_company_id is None


def test_invite_user_single_company_sets_landing_default(db, companies):
    svc = UserService(db)
    user = svc.invite_user(
        UserCreate(email="inv1@t.com", name="Inv1", company_ids=[companies["mch"]]),
        invited_by_user_id=str(uuid.uuid4()),
    )
    assert str(user.last_active_company_id) == companies["mch"]


# --------------------------------------------------------------------------- #
# set_user_companies                                                           #
# --------------------------------------------------------------------------- #
def test_set_user_companies_replaces_set(db, companies):
    svc = UserService(db)
    user = svc.create_user(
        UserCreate(email="set@t.com", name="Set", company_ids=[companies["srt"]])
    )
    assert _grant_ids(db, user.id) == {companies["srt"]}

    svc.set_user_companies(user.id, [companies["mch"]])
    assert _grant_ids(db, user.id) == {companies["mch"]}


def test_set_user_companies_repoints_last_active_when_revoked(db, companies):
    svc = UserService(db)
    user = svc.create_user(
        UserCreate(email="repoint@t.com", name="Repoint", company_ids=[companies["srt"]])
    )
    assert str(user.last_active_company_id) == companies["srt"]

    # Revoke SRT (the active grant), grant MCH instead -> last_active must repoint.
    svc.set_user_companies(user.id, [companies["mch"]])
    db.refresh(user)
    assert _grant_ids(db, user.id) == {companies["mch"]}
    assert str(user.last_active_company_id) == companies["mch"]


def test_set_user_companies_empty_nulls_last_active(db, companies):
    svc = UserService(db)
    user = svc.create_user(
        UserCreate(email="empty@t.com", name="Empty", company_ids=[companies["srt"]])
    )
    svc.set_user_companies(user.id, [])
    db.refresh(user)
    assert _grant_ids(db, user.id) == set()
    assert user.last_active_company_id is None


def test_set_user_companies_keeps_last_active_when_still_granted(db, companies):
    svc = UserService(db)
    user = svc.create_user(
        UserCreate(email="keep@t.com", name="Keep", company_ids=[companies["srt"]])
    )
    # Widen to both; SRT (the active grant) is still present -> unchanged.
    svc.set_user_companies(user.id, [companies["srt"], companies["mch"]])
    db.refresh(user)
    assert _grant_ids(db, user.id) == {companies["srt"], companies["mch"]}
    assert str(user.last_active_company_id) == companies["srt"]
