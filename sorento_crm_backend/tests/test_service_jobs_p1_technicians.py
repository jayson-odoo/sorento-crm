"""AFTER-SALES-P1 red tests: technicians API (UAC F1-F3).

List sort keys: name, phone, employment_type, is_active. Body: {name, phone?, employment_type
(employee|contractor), is_active?}. DELETE answers 200 or 204; 409 with "in use" when any job
references the technician.
"""
from __future__ import annotations

import pytest

from ._pg_fixture import unique_code
from ._service_jobs_p1_support import (
    MANAGE,
    TECHS,
    VIEW,
    api,
    env,  # noqa: F401
    make_complaint,
    make_job,
    make_tech,
)


def _names(resp):
    assert resp.status_code == 200, resp.text
    return [r["name"] for r in resp.json()["data"]]


def test_f2_create_get_update(env):
    n = unique_code("Tech")
    with api(env) as client:
        r = client.post(TECHS, json={"name": n, "phone": "+60111111111", "employment_type": "contractor"})
        assert r.status_code in (200, 201), r.text
        body = r.json()
        assert body["name"] == n and body["employment_type"] == "contractor" and body["is_active"] is True
        up = client.put(f"{TECHS}/{body['id']}", json={"name": n + "x", "employment_type": "employee", "phone": "+60170000501"})
        assert up.status_code == 200, up.text
        assert up.json()["name"] == n + "x" and up.json()["employment_type"] == "employee"
        assert n + "x" in _names(client.get(TECHS, params={"query": n}))


@pytest.mark.parametrize(
    "payload",
    [{"phone": "1"}, {"name": "   ", "employment_type": "employee"}, {"name": "X", "employment_type": "wizard"}],
)
def test_f2_validation_is_422(env, payload):
    with api(env) as client:
        assert client.post(TECHS, json=payload).status_code == 422


def test_f2_auth_denial(env):
    with api(env, {VIEW}) as client:
        assert client.post(TECHS, json={"name": "X", "employment_type": "employee"}).status_code == 403
        assert client.get(TECHS).status_code == 200
    with api(env, set()) as client:
        assert client.get(TECHS).status_code == 403
    with api(env, {MANAGE}) as client:
        assert client.post(TECHS, json={"name": unique_code("T"), "employment_type": "employee"}).status_code in (200, 201)


@pytest.mark.parametrize("direction", ["asc", "desc"])
@pytest.mark.parametrize("column", ["name", "phone", "employment_type", "is_active"])
def test_f1_every_column_sorts_on_the_server(env, column, direction):
    tag = unique_code("TS", alpha=True)
    spec = [  # (name, phone, kind, active) ranked 1..3 on every column
        (f"{tag} c", "+60333", "employee", True),
        (f"{tag} a", "+60111", "contractor", False),
        (f"{tag} b", "+60222", "employee", True),
    ]
    rows = []
    for name, phone, kind, active in spec:
        t = make_tech(env, name, active=active, kind=kind)
        t.phone = phone
        rows.append(t)
    env.db.flush()
    with api(env) as client:
        r = client.get(TECHS, params={"query": tag, "sort": column, "dir": direction, "limit": 50})
    assert r.status_code == 200, r.text
    got = [x[column] for x in r.json()["data"]]
    assert got == sorted(got, reverse=(direction == "desc")), got
    assert len(got) == 3


def test_f1_search_by_name(env):
    tag = unique_code("TQ", alpha=True)
    make_tech(env, f"{tag} one")
    make_tech(env, "ZZT other person")
    with api(env) as client:
        assert _names(client.get(TECHS, params={"query": tag})) == [f"{tag} one"]


def test_f1_list_limit_cap(env):
    with api(env) as client:
        assert client.get(TECHS, params={"limit": 1000000}).status_code == 422


def test_f3_delete_unused_technician(env):
    t = make_tech(env)
    with api(env) as client:
        r = client.delete(f"{TECHS}/{t.id}")
        assert r.status_code in (200, 204), r.text
        assert client.get(f"{TECHS}/{t.id}").status_code == 404


def test_f3_delete_of_a_technician_on_a_job_is_409_in_use(env):
    t = make_tech(env)
    make_job(env, make_complaint(env, "f3"), "confirmed", technician=t)
    with api(env) as client:
        r = client.delete(f"{TECHS}/{t.id}")
        assert r.status_code == 409, r.text
        assert "in use" in r.text.lower()
        # archive instead
        up = client.put(f"{TECHS}/{t.id}", json={"is_active": False})
        assert up.status_code == 200 and up.json()["is_active"] is False


def test_f3_delete_needs_manage(env):
    t = make_tech(env)
    with api(env, {VIEW}) as client:
        assert client.delete(f"{TECHS}/{t.id}").status_code == 403


# ------------------------------------------------------------------ phone (same check as project sales)

@pytest.mark.parametrize("bad", ["abc", "123"])
def test_a_bad_phone_is_422_on_create_and_update(env, bad):
    with api(env) as client:
        r = client.post(TECHS, json={"name": unique_code("T"), "employment_type": "employee", "phone": bad})
        assert r.status_code == 422 and "Enter a valid phone number" in r.text
        good = client.post(TECHS, json={"name": unique_code("T"), "employment_type": "employee"}).json()
        assert client.put(f"{TECHS}/{good['id']}", json={"phone": bad}).status_code == 422


def test_a_good_phone_is_stored_e164_and_displayed_local(env):
    with api(env) as client:
        body = client.post(
            TECHS, json={"name": unique_code("T"), "employment_type": "employee", "phone": "012-345 6789"}
        ).json()
        assert body["phone"] == "+60123456789" and body["phone_display"] == "012-345 6789"
        up = client.put(f"{TECHS}/{body['id']}", json={"phone": ""})
        assert up.status_code == 200 and up.json()["phone"] is None


# ------------------------------------------------------------------ round 6 (R6-3)

@pytest.mark.parametrize("key", ["proposed", "confirmed", "verified", "cancelled"])
def test_in_use_counts_a_job_in_any_status(env, key):
    tag = unique_code("IU", alpha=True)
    used = make_tech(env, f"{tag} used")
    free = make_tech(env, f"{tag} free")
    make_job(env, None, key, technician=used)
    with api(env) as client:
        rows = {r["name"]: r for r in client.get(TECHS, params={"query": tag}).json()["data"]}
    assert rows[f"{tag} used"]["in_use"] is True
    assert rows[f"{tag} free"]["in_use"] is False


def test_get_one_technician_also_says_whether_it_is_in_use(env):
    used = make_tech(env)
    make_job(env, None, "verified", technician=used)
    with api(env) as client:
        assert client.get(f"{TECHS}/{used.id}").json()["in_use"] is True
        assert client.put(f"{TECHS}/{used.id}", json={"phone": ""}).json()["in_use"] is True


def test_deleting_a_technician_on_a_job_is_refused_when_parked_not_after_the_countdown(env):
    from app.models.user import User

    used = make_tech(env)
    free = make_tech(env)
    make_job(env, None, "verified", technician=used)
    with api(env) as client:
        env.db.merge(User(id=env.actor_id, email=f"{env.actor_id}@zzt.test", name="ZZT Actor", status="ACTIVE"))
        env.db.flush()
        body = {"action_key": "technician.delete", "entity_type": "technician", "payload": {}}
        refused = client.post("/api/v1/pending-actions", json={**body, "entity_id": used.id})
        assert refused.status_code == 409, refused.text
        assert "Archive instead" in refused.text
        assert client.post("/api/v1/pending-actions", json={**body, "entity_id": free.id}).status_code == 202


@pytest.mark.parametrize("direction", ["asc", "desc"])
@pytest.mark.parametrize("column", ["phone", "employment_type"])
def test_empty_values_sort_last_both_ways(env, column, direction):
    tag = unique_code("TE", alpha=True)
    full = make_tech(env, f"{tag} full")
    none = make_tech(env, f"{tag} none")
    blank = make_tech(env, f"{tag} blank")
    setattr(full, column, "+60123456789" if column == "phone" else "employee")
    setattr(none, column, None)
    setattr(blank, column, "")
    env.db.flush()
    with api(env) as client:
        rows = client.get(TECHS, params={"query": tag, "sort": column, "dir": direction, "limit": 50}).json()["data"]
    ids = [r["id"] for r in rows]
    assert ids[0] == full.id and set(ids[1:]) == {none.id, blank.id}, (column, direction, ids)
