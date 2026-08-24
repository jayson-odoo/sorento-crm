"""ContactService company-grant tests (multi-company isolation).

Covers the respond-contact half of the company grant management that mirrors the
user-side ``set_user_companies`` / ``list_user_companies``:
 - set_contact_companies([Sorento, Mocha]) creates two respond_contact_companies rows.
 - replacing with [Mocha] leaves exactly one (delete-all-then-reinsert).
 - list_contact_companies returns the granted companies ordered by name.
 - unknown company ids are skipped; duplicates are collapsed.

Runs against an in-memory sqlite bind (CLAUDE.md "sqlite pytest fixtures" gotcha):
pg ``UUID(as_uuid=False)`` works as-is; JSONB columns are swapped to JSON.

Run: venv/bin/pytest tests/test_contact_company_grants.py -q
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.access import RespondContact
from app.models.company import Company, RespondContactCompany
from app.services.contact_service import ContactService


@pytest.fixture
def db():
    # Postgres blank schema (the suite is Postgres-only; no sqlite, no shared-
    # metadata mutation which leaks column types into other tests' blank schema).
    from tests._pg_fixture import blank_session

    with blank_session() as s:
        yield s


@pytest.fixture
def seed(db):
    # The shared blank schema is seeded with the incumbent Sorento company (code
    # SRT). This suite asserts exact codes, so clear companies inside this rolled-
    # back transaction first, then use the real SRT/MCH codes.
    db.query(RespondContactCompany).delete()
    db.query(Company).delete()
    srt = Company(id=str(uuid.uuid4()), name="Sorento", code="SRT")
    mch = Company(id=str(uuid.uuid4()), name="Mocha", code="MCH")
    db.add_all([srt, mch])
    contact = RespondContact(
        id=str(uuid.uuid4()), phone_number="+60111", name="Ken", session_vars={}
    )
    db.add(contact)
    db.commit()
    return {"srt": srt.id, "mch": mch.id, "contact": contact.id}


def _grant_count(db, contact_id: str) -> int:
    return (
        db.query(RespondContactCompany)
        .filter(RespondContactCompany.respond_contact_id == contact_id)
        .count()
    )


def test_set_creates_two_rows(db, seed):
    ContactService(db).set_contact_companies(seed["contact"], [seed["srt"], seed["mch"]])
    assert _grant_count(db, seed["contact"]) == 2


def test_replace_leaves_one_row(db, seed):
    svc = ContactService(db)
    svc.set_contact_companies(seed["contact"], [seed["srt"], seed["mch"]])
    svc.set_contact_companies(seed["contact"], [seed["mch"]])
    assert _grant_count(db, seed["contact"]) == 1
    listed = svc.list_contact_companies(seed["contact"])
    assert [c["code"] for c in listed] == ["MCH"]


def test_list_returns_granted_ordered_by_name(db, seed):
    svc = ContactService(db)
    svc.set_contact_companies(seed["contact"], [seed["srt"], seed["mch"]])
    listed = svc.list_contact_companies(seed["contact"])
    # Ordered by Company.name asc -> Mocha before Sorento.
    assert [c["name"] for c in listed] == ["Mocha", "Sorento"]
    assert all(set(c.keys()) == {"id", "name", "code"} for c in listed)


def test_unknown_ids_and_dupes_skipped(db, seed):
    svc = ContactService(db)
    svc.set_contact_companies(
        seed["contact"], [seed["srt"], seed["srt"], str(uuid.uuid4())]
    )
    assert _grant_count(db, seed["contact"]) == 1
    assert [c["code"] for c in svc.list_contact_companies(seed["contact"])] == ["SRT"]
