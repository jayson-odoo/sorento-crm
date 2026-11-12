"""ASSIGNED-FILTER-ALL-STAFF (owner, 12 Nov 2026): the Complaints "Assigned to" filter lists every
staff member and takes their CRM user id. `complaints.assigned_to` holds either a CRM user id or a
Respond.io agent id, so a chosen person matches rows stored under either. A Respond.io id value (a
filter saved before this change) still matches. Postgres only; rows seeded here, fake names.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.complaints import Complaint
from app.models.user import User, UserStatus
from app.services.user_service import UserPermissionService
from tests._multi_filter_client import get, open_client
from tests._pg_fixture import blank_session, unique_code

COMPLAINTS = "/api/v1/complaints-management/complaints/"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: {"admin"})
    with open_client(db, monkeypatch) as (c, _actor):
        yield c


def _user(db, name, respond_user_id=None):
    uid = str(uuid.uuid4())
    db.add(User(id=uid, email=f"{uid}@zzt.test", name=name, status=UserStatus.ACTIVE.value,
                respond_user_id=respond_user_id,
                respond_synced="successful" if respond_user_id else None))
    db.flush()
    return uid


def _complaint(db, tag, label, assignee):
    row = Complaint(id=str(uuid.uuid4()), complaint_number=f"{tag}-{label}", status="new",
                    assigned_to=assignee, complaint_date=date(2026, 6, 1))
    db.add(row)
    db.flush()
    return row.id


@pytest.fixture
def seeded(db):
    tag = unique_code("AF", alpha=True)
    resp_id = f"zzt-resp-{uuid.uuid4().hex[:8]}"
    plain = _user(db, "ZZT Plain Staff")             # never synced to Respond.io
    synced = _user(db, "ZZT Synced Staff", resp_id)  # synced
    nobody = _user(db, "ZZT Idle Staff")             # no complaints
    return dict(
        tag=tag, plain=plain, synced=synced, nobody=nobody, resp_id=resp_id,
        c_plain=_complaint(db, tag, "1", plain),
        c_synced_resp=_complaint(db, tag, "2", resp_id),
        c_synced_crm=_complaint(db, tag, "3", synced),
        c_none=_complaint(db, tag, "4", None),
    )


def _cp(client, s, value):
    resp = get(client, COMPLAINTS, [("limit", 200), ("query", s["tag"]), ("assigned_to", value)])
    assert resp.status_code == 200, resp.text
    return {r["id"] for r in resp.json()["data"]}


def test_non_synced_staff_filters_by_crm_id(client, seeded):
    s = seeded
    assert _cp(client, s, s["plain"]) == {s["c_plain"]}


def test_synced_staff_by_crm_id_matches_rows_stored_under_either_id(client, seeded):
    s = seeded
    assert _cp(client, s, s["synced"]) == {s["c_synced_resp"], s["c_synced_crm"]}


def test_saved_respond_id_value_still_matches_both(client, seeded):
    s = seeded
    assert _cp(client, s, s["resp_id"]) == {s["c_synced_resp"], s["c_synced_crm"]}


def test_staff_with_no_complaints_returns_empty_list(client, seeded):
    s = seeded
    assert _cp(client, s, s["nobody"]) == set()


def test_unknown_value_returns_empty_list_not_an_error(client, seeded):
    s = seeded
    assert _cp(client, s, f"zzt-unknown-{uuid.uuid4().hex[:6]}") == set()


def test_unassigned_plus_two_people_or_combine(client, seeded):
    s = seeded
    got = _cp(client, s, f"__unassigned__,{s['plain']},{s['synced']}")
    assert got == {s["c_none"], s["c_plain"], s["c_synced_resp"], s["c_synced_crm"]}
