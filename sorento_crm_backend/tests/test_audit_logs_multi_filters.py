"""FILTER-MULTISELECT PR2: Audit logs (entity type, action, user) and Activity (action, user) take
several values (OR within a filter, AND across). Activity's entity type already takes a list and is
kept as a guard. Red first; Postgres only; rows seeded here and isolated by a unique trace id.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.models.audit import AuditLog
from app.models.user import User
from app.services.user_service import UserPermissionService
from tests._multi_filter_client import get, open_client
from tests._pg_fixture import blank_session, unique_code

LOGS = "/api/v1/audit/logs/"
ACTIVITY = "/api/v1/audit/activity"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: {"admin"})
    with open_client(db, monkeypatch) as (c, _actor):
        yield c


def _user(db, label):
    row = User(id=str(uuid.uuid4()), email=f"{unique_code(label)}@example.com".lower(),
               name=f"ZZT {label}", status="ACTIVE")
    db.add(row)
    db.flush()
    return row


def _row(db, trace, entity_type, action, user, minutes):
    row = AuditLog(
        id=str(uuid.uuid4()), entity_type=entity_type, entity_id=str(uuid.uuid4()), action=action,
        user_id=user.id, trace_id=trace, changed_at=datetime(2026, 6, 30, 9, 0, 0) - timedelta(minutes=minutes),
        new_values={"name": "x"},
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def seeded(db):
    trace = unique_code("tr")
    u1, u2, u3 = _user(db, "a"), _user(db, "b"), _user(db, "c")
    a = _row(db, trace, "zzt_alpha", "INSERT", u1, 1)
    b = _row(db, trace, "zzt_beta", "UPDATE", u2, 2)
    c = _row(db, trace, "zzt_gamma", "DELETE", u3, 3)
    d = _row(db, trace, "zzt_alpha", "UPDATE", u1, 4)
    return dict(trace=trace, u1=u1, u2=u2, u3=u3, a=a, b=b, c=c, d=d)


def _logs(client, s, pairs):
    resp = get(client, LOGS, [("limit", 200), ("trace_id", s["trace"]), *pairs])
    assert resp.status_code == 200, resp.text
    return {r["id"] for r in resp.json()["data"]}


def _activity(client, s, pairs):
    resp = get(client, ACTIVITY, [("limit", 200), ("trace_id", s["trace"]), *pairs])
    assert resp.status_code == 200, resp.text
    return {r["id"] for r in resp.json()["items"]}


# ---- Audit logs ---------------------------------------------------------------------------------

def test_logs_entity_type_union(client, seeded):
    s = seeded
    assert _logs(client, s, [("entity_type", "zzt_alpha,zzt_beta")]) == {s["a"].id, s["b"].id, s["d"].id}


def test_logs_entity_type_single_and_repeated(client, seeded):
    s = seeded
    assert _logs(client, s, [("entity_type", "zzt_gamma")]) == {s["c"].id}
    got = _logs(client, s, [("entity_type", "zzt_beta"), ("entity_type", "zzt_gamma")])
    assert got == {s["b"].id, s["c"].id}


def test_logs_action_union(client, seeded):
    s = seeded
    assert _logs(client, s, [("action", "INSERT,DELETE")]) == {s["a"].id, s["c"].id}


def test_logs_action_single_and_repeated(client, seeded):
    s = seeded
    assert _logs(client, s, [("action", "UPDATE")]) == {s["b"].id, s["d"].id}
    assert _logs(client, s, [("action", "INSERT"), ("action", "DELETE")]) == {s["a"].id, s["c"].id}


def test_logs_user_union(client, seeded):
    s = seeded
    got = _logs(client, s, [("user_id", f"{s['u2'].id},{s['u3'].id}")])
    assert got == {s["b"].id, s["c"].id}


def test_logs_user_single_and_repeated(client, seeded):
    s = seeded
    assert _logs(client, s, [("user_id", s["u1"].id)]) == {s["a"].id, s["d"].id}
    got = _logs(client, s, [("user_id", s["u2"].id), ("user_id", s["u3"].id)])
    assert got == {s["b"].id, s["c"].id}


def test_logs_malformed_user_id_is_never_a_500_and_matches_nothing(client, seeded):
    s = seeded
    resp = get(client, LOGS, [("trace_id", s["trace"]), ("user_id", f"{s['u1'].id},not-a-uuid")])
    assert resp.status_code in (200, 422), resp.text
    resp = get(client, LOGS, [("trace_id", s["trace"]), ("user_id", "not-a-uuid")])
    assert resp.status_code in (200, 422), resp.text
    if resp.status_code == 200:
        assert resp.json()["data"] == []


def test_logs_filters_and_across_each_other(client, seeded):
    s = seeded
    got = _logs(client, s, [("entity_type", "zzt_alpha,zzt_beta"), ("action", "UPDATE,DELETE"),
                            ("user_id", f"{s['u1'].id},{s['u2'].id}")])
    assert got == {s["b"].id, s["d"].id}


# ---- Activity ------------------------------------------------------------------------------------

def test_activity_action_union(client, seeded):
    s = seeded
    assert _activity(client, s, [("action", "created,deleted")]) == {s["a"].id, s["c"].id}


def test_activity_action_single_and_repeated(client, seeded):
    s = seeded
    assert _activity(client, s, [("action", "updated")]) == {s["b"].id, s["d"].id}
    assert _activity(client, s, [("action", "created"), ("action", "deleted")]) == {s["a"].id, s["c"].id}


def test_activity_user_union(client, seeded):
    s = seeded
    got = _activity(client, s, [("user_id", f"{s['u2'].id},{s['u3'].id}")])
    assert got == {s["b"].id, s["c"].id}


def test_activity_user_single_and_repeated(client, seeded):
    s = seeded
    assert _activity(client, s, [("user_id", s["u1"].id)]) == {s["a"].id, s["d"].id}
    got = _activity(client, s, [("user_id", s["u2"].id), ("user_id", s["u3"].id)])
    assert got == {s["b"].id, s["c"].id}


def test_activity_malformed_user_id_is_never_a_500(client, seeded):
    s = seeded
    resp = get(client, ACTIVITY, [("trace_id", s["trace"]), ("user_id", f"{s['u1'].id},not-a-uuid")])
    assert resp.status_code in (200, 422), resp.text


def test_activity_entity_type_already_takes_several_values(client, seeded):
    s = seeded
    assert _activity(client, s, [("entity_type", "zzt_alpha,zzt_beta")]) == {s["a"].id, s["b"].id, s["d"].id}
    got = _activity(client, s, [("entity_type", "zzt_beta"), ("entity_type", "zzt_gamma")])
    assert got == {s["b"].id, s["c"].id}


def test_activity_filters_and_across_each_other(client, seeded):
    s = seeded
    got = _activity(client, s, [("action", "updated,deleted"), ("user_id", f"{s['u1'].id},{s['u3'].id}")])
    assert got == {s["c"].id, s["d"].id}
