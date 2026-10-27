"""FILTER-MULTISELECT PR2 slice A: Users Role and Status, Onboarding requests Status take several
values (OR within a filter, AND across). Red first; Postgres only; rows seeded here.
"""
from __future__ import annotations

import pytest

from app.models.company import Company  # noqa: F401  (mapper registry)
from app.models.onboarding import OnboardingRequest
from app.models.user import User, UserRole, UserRoleAssignment
from tests._multi_filter_client import SORENTO, get, ok_ids, open_client
from tests._pg_fixture import blank_session, unique_code

USERS = "/api/v1/user-management/users/"
REQUESTS = "/api/v1/user-management/onboarding/requests"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    with open_client(db, monkeypatch) as (c, _actor):
        yield c


def _user(db, tag, label, status, roles=()):
    user = User(id=unique_code("user"), email=f"{unique_code(label)}@example.com".lower(),
                name=f"ZZT {tag} {label}", status=status)
    db.add(user)
    db.flush()
    for role in roles:
        db.add(UserRoleAssignment(user_id=user.id, role_id=role.id))
    db.flush()
    return user


def _role(db):
    role = UserRole(id=unique_code("role"), slug=unique_code("role").lower(), name=unique_code("Role"))
    db.add(role)
    db.flush()
    return role


@pytest.fixture
def users(db):
    tag = unique_code("U", alpha=True)
    r1, r2, r3 = _role(db), _role(db), _role(db)
    a = _user(db, tag, "a", "ACTIVE", [r1])
    b = _user(db, tag, "b", "INACTIVE", [r2])
    c = _user(db, tag, "c", "SUSPENDED", [r3])
    d = _user(db, tag, "d", "ACTIVE", [r1, r2])
    return dict(tag=tag, r1=r1, r2=r2, r3=r3, a=a, b=b, c=c, d=d)


def _list(client, tag, pairs):
    return ok_ids(get(client, USERS, [("limit", 100), ("query", tag), *pairs]))


def test_status_two_values_are_the_union(client, users):
    u = users
    assert _list(client, u["tag"], [("status", "INACTIVE,SUSPENDED")]) == {u["b"].id, u["c"].id}


def test_status_single_and_repeated(client, users):
    u = users
    assert _list(client, u["tag"], [("status", "ACTIVE")]) == {u["a"].id, u["d"].id}
    assert _list(client, u["tag"], [("status", "INACTIVE"), ("status", "SUSPENDED")]) == {u["b"].id, u["c"].id}


def test_status_all_is_no_filter(client, users):
    u = users
    assert _list(client, u["tag"], [("status", "all")]) == {u["a"].id, u["b"].id, u["c"].id, u["d"].id}


def test_role_two_values_are_the_union_without_duplicates(client, users):
    u = users
    resp = get(client, USERS, [("limit", 100), ("query", u["tag"]), ("roleId", f"{u['r1'].id},{u['r2'].id}")])
    rows = resp.json()["data"]
    ids = [r["id"] for r in rows]
    assert sorted(ids) == sorted({u["a"].id, u["b"].id, u["d"].id})  # d holds both roles, listed once
    assert resp.json()["pagination"]["total"] == 3


def test_role_single_and_repeated(client, users):
    u = users
    assert _list(client, u["tag"], [("roleId", u["r3"].id)]) == {u["c"].id}
    assert _list(client, u["tag"], [("roleId", u["r1"].id), ("roleId", u["r3"].id)]) == {u["a"].id, u["c"].id, u["d"].id}


def test_role_and_status_and_together(client, users):
    u = users
    got = _list(client, u["tag"], [("roleId", f"{u['r1'].id},{u['r2'].id}"), ("status", "ACTIVE,SUSPENDED")])
    assert got == {u["a"].id, u["d"].id}


# --- Onboarding requests ------------------------------------------------------------------


@pytest.fixture
def requests_(db):
    from app.services import onboarding_service
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "360_onboarding_slice1.py"
    spec = importlib.util.spec_from_file_location("onboarding_migration_multi", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._seed_graph(db.connection())
    module._mark_system(db.connection())
    tag = unique_code("OB", alpha=True)
    out = {"tag": tag}
    for key, status in (("a", "zzt_draft"), ("b", "zzt_sent"), ("c", "zzt_review")):
        row = onboarding_service.create_request(
            db, company_id=SORENTO, title=f"ZZT {tag} {key}", requester_name="ZZT Req",
            requester_email="zzt@example.com", requester_phone=None, expiry_days=7, user_id=None,
        )
        row.status_key = status
        out[key] = row
    db.flush()
    return out


def test_onboarding_status_two_values_are_the_union(client, requests_):
    r = requests_
    got = ok_ids(get(client, REQUESTS, [("query", r["tag"]), ("status_key", "zzt_draft,zzt_review")]))
    assert got == {str(r["a"].id), str(r["c"].id)}


def test_onboarding_status_single_and_repeated(client, requests_):
    r = requests_
    assert ok_ids(get(client, REQUESTS, [("query", r["tag"]), ("status_key", "zzt_sent")])) == {str(r["b"].id)}
    got = ok_ids(get(client, REQUESTS, [("query", r["tag"]), ("status_key", "zzt_draft"), ("status_key", "zzt_sent")]))
    assert got == {str(r["a"].id), str(r["b"].id)}
