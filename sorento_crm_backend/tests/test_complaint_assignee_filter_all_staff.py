"""ASSIGNED-FILTER-ALL-STAFF (owner, 12 Nov 2026; crew ruling (b) on dev-copy evidence): the Complaints "Assigned to" filter lists every
staff member and takes their CRM user id. `complaints.assigned_to` holds either a CRM user id or a
Respond.io agent id, so a chosen person matches rows stored under either. A Respond.io id value (a
filter saved before this change) still matches. Filter and sort follow the Assigned To column's
rule: the latest open SLA tracker's assignee, else `complaints.assigned_to` (on the dev copy every
assignee sits on a tracker and `complaints.assigned_to` is empty). Postgres only; rows seeded here, fake names.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest

from app.models.complaints import Complaint
from app.models.sla import ConversationSLATracking, SLAPolicy
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


# ---- the Assigned To column rule: latest open SLA tracker first ------------------------------------

def _tracker(db, policy_id, complaint_id, *, assigned_to_id=None, assigned_to=None, days=0,
             resolved=False, voided=False):
    db.add(ConversationSLATracking(
        id=str(uuid.uuid4()), policy_id=policy_id, current_tier=1,
        due_at=datetime.now() + timedelta(days=1), initiated_at=datetime(2026, 6, 1) + timedelta(days=days),
        source_entity_type="complaint", source_entity_id=complaint_id,
        assigned_to_id=assigned_to_id, assigned_to=assigned_to, is_resolved=resolved,
        voided_at=datetime(2026, 6, 2) if voided else None,
    ))
    db.flush()


@pytest.fixture
def tracked(db):
    tag = unique_code("AT", alpha=True)
    policy = SLAPolicy(id=str(uuid.uuid4()), code=f"ZZT-{uuid.uuid4().hex[:6]}", name="ZZT policy")
    db.add(policy)
    db.flush()
    amy = _user(db, "ZZT Amy Tracker")
    zed = _user(db, "ZZT Zed Tracker")
    old = _user(db, "ZZT Old Tracker")
    # Only assignee is on the open tracker; complaints.assigned_to empty (the dev-copy shape).
    c_amy = _complaint(db, tag, "1", None)
    _tracker(db, policy.id, c_amy, assigned_to_id=amy)
    c_zed = _complaint(db, tag, "2", "")
    _tracker(db, policy.id, c_zed, assigned_to_id=zed)
    # The latest open tracker wins over an older open one and over complaints.assigned_to.
    c_latest = _complaint(db, tag, "3", old)
    _tracker(db, policy.id, c_latest, assigned_to_id=old, days=0)
    _tracker(db, policy.id, c_latest, assigned_to_id=amy, days=1)
    # A resolved tracker does not count: falls back to complaints.assigned_to.
    c_resolved = _complaint(db, tag, "4", old)
    _tracker(db, policy.id, c_resolved, assigned_to_id=zed, resolved=True)
    # A voided tracker does not count either.
    c_voided = _complaint(db, tag, "6", old)
    _tracker(db, policy.id, c_voided, assigned_to_id=zed, voided=True)
    # Legacy: only the tracker's free-text `assigned_to` holds the person (a Respond id).
    resp = f"zzt-resp-{uuid.uuid4().hex[:8]}"
    legacy = _user(db, "ZZT Legacy Tracker", resp)
    c_legacy = _complaint(db, tag, "7", None)
    _tracker(db, policy.id, c_legacy, assigned_to=resp)
    # Nobody anywhere; a blank assigned_to is no assignee.
    c_none = _complaint(db, tag, "5", None)
    c_blank = _complaint(db, tag, "8", "  ")
    return dict(tag=tag, amy=amy, zed=zed, old=old, legacy=legacy, c_amy=c_amy, c_zed=c_zed,
                c_latest=c_latest, c_resolved=c_resolved, c_voided=c_voided, c_legacy=c_legacy,
                c_none=c_none, c_blank=c_blank)


def test_filter_finds_a_complaint_whose_only_assignee_is_on_its_open_tracker(client, tracked):
    s = tracked
    assert _cp(client, s, s["amy"]) == {s["c_amy"], s["c_latest"]}
    assert _cp(client, s, s["zed"]) == {s["c_zed"]}


def test_filter_skips_resolved_trackers_and_older_tracker_assignees(client, tracked):
    s = tracked
    assert _cp(client, s, s["old"]) == {s["c_resolved"], s["c_voided"]}


def test_legacy_tracker_text_assignee_is_matched_by_the_persons_crm_id(client, tracked):
    s = tracked
    assert _cp(client, s, s["legacy"]) == {s["c_legacy"]}


def test_unassigned_means_no_assignee_on_the_tracker_either(client, tracked):
    s = tracked
    assert _cp(client, s, "__unassigned__") == {s["c_none"], s["c_blank"]}


def test_filter_matches_what_the_column_shows(client, tracked):
    s = tracked
    resp = get(client, COMPLAINTS, [("limit", 200), ("query", s["tag"]), ("assigned_to", s["amy"])])
    assert {r["assigned_to_name"] for r in resp.json()["data"]} == {"ZZT Amy Tracker"}


@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_sort_by_assigned_to_orders_by_the_name_the_column_shows(client, tracked, direction):
    s = tracked
    resp = get(client, COMPLAINTS, [("limit", 200), ("query", s["tag"]), ("sort", "assigned_to"),
                                    ("dir", direction), ("assigned_to", f"{s['amy']},{s['zed']},{s['old']}")])
    assert resp.status_code == 200, resp.text
    names = [r["assigned_to_name"] for r in resp.json()["data"]]
    assert names == sorted(names, reverse=(direction == "desc"))
    assert set(names) == {"ZZT Amy Tracker", "ZZT Zed Tracker", "ZZT Old Tracker"}
