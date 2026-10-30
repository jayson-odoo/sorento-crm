"""FILTER-MULTISELECT PR2: the permissions list's Role filter (``roleId``) takes several values and,
unlike before, actually filters. A permission is granted to a role by a user_role_permissions row.
Red first; Postgres only; rows seeded here.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.user import UserPermission, UserRole, UserRolePermission
from tests._multi_filter_client import get, open_client
from tests._pg_fixture import blank_session, unique_code

PERMS = "/api/v1/user-management/permissions/"


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    with open_client(db, monkeypatch) as (c, _actor):
        yield c


def _role(db):
    code = unique_code("role")
    row = UserRole(id=str(uuid.uuid4()), slug=code.lower(), name=code)
    db.add(row)
    db.flush()
    return row


def _perm(db, label):
    code = unique_code(label)
    row = UserPermission(slug=code.lower(), name=code)
    db.add(row)
    db.flush()
    return row


def _grant(db, role, perm):
    db.add(UserRolePermission(role_id=role.id, permission_id=perm.id))
    db.flush()


@pytest.fixture
def seeded(db):
    r1, r2, r3 = _role(db), _role(db), _role(db)
    p1, p2, pboth, pnone = _perm(db, "p1"), _perm(db, "p2"), _perm(db, "pboth"), _perm(db, "pnone")
    _grant(db, r1, p1)
    _grant(db, r2, p2)
    _grant(db, r1, pboth)
    _grant(db, r2, pboth)
    return dict(r1=r1, r2=r2, r3=r3, p1=p1, p2=p2, pboth=pboth, pnone=pnone)


def _rows(client, pairs):
    resp = get(client, PERMS, [("limit", 200), *pairs])
    assert resp.status_code == 200, resp.text
    return [row["id"] for row in resp.json()["data"]]


def _mine(s, ids):
    keys = ("p1", "p2", "pboth", "pnone")
    mine = {s[k].id for k in keys}
    return [i for i in ids if i in mine]


def test_single_role_returns_only_its_permissions(client, seeded):
    s = seeded
    got = _mine(s, _rows(client, [("roleId", s["r1"].id)]))
    assert set(got) == {s["p1"].id, s["pboth"].id}


def test_role_with_no_grants_returns_nothing_of_mine(client, seeded):
    s = seeded
    assert _mine(s, _rows(client, [("roleId", s["r3"].id)])) == []


def test_two_roles_comma_joined_are_the_union_without_duplicates(client, seeded):
    s = seeded
    got = _mine(s, _rows(client, [("roleId", f"{s['r1'].id},{s['r2'].id}")]))
    assert sorted(got) == sorted([s["p1"].id, s["p2"].id, s["pboth"].id])


def test_two_roles_repeated_param_are_the_union_without_duplicates(client, seeded):
    s = seeded
    got = _mine(s, _rows(client, [("roleId", s["r1"].id), ("roleId", s["r2"].id)]))
    assert sorted(got) == sorted([s["p1"].id, s["p2"].id, s["pboth"].id])


def test_pagination_total_counts_distinct_permissions(client, seeded):
    s = seeded
    resp = get(client, PERMS, [("limit", 200), ("roleId", f"{s['r1'].id},{s['r2'].id}")])
    assert resp.status_code == 200, resp.text
    assert resp.json()["pagination"]["total"] == 3


def test_no_role_filter_is_unfiltered(client, seeded):
    s = seeded
    got = _mine(s, _rows(client, []))
    assert set(got) == {s["p1"].id, s["p2"].id, s["pboth"].id, s["pnone"].id}


def test_malformed_role_id_is_422(client):
    # role ids are uuids; a non-uuid value is rejected, as multi_uuids does elsewhere
    assert get(client, PERMS, [("roleId", "not-a-uuid")]).status_code == 422
    assert get(client, PERMS, [("roleId", "not-a-uuid,also-bad")]).status_code == 422
