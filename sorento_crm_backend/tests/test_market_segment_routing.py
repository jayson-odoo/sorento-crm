"""Market-segment CS routing — service + endpoints (PLAN/UAC cs-team-market-segment-routing).

Runs against the live Postgres test DB (retail/project seeded by migration 263). Seeds an
isolated agent/team/members/contacts with a unique prefix, asserts, cleans up.

Covers: D (team-members filter), E (next-assignee regression + opt-in), G (match semantics),
plus the catalog + assignment endpoints (B/C/F).
"""
from __future__ import annotations

import uuid
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.main import app
from app.dependencies import get_current_user, get_db, get_external_api_user
from app.models.access import (
    AccessAgent,
    AgentTeam,
    MarketSegment,
    RespondContact,
    Team,
    TeamMember,
)
from app.models.user import User, UserStatus
from app.services.market_segment_service import MarketSegmentService, segment_key_for
from app.services.user_service import AccessAgentService

PFX = "MSEG-"
AGENT_CODE = f"{PFX}order_enquiries"
TEAM_SET = "customer_service"


def _cleanup() -> None:
    with engine.connect() as conn:
        try:
            conn.execute(text(
                "DELETE FROM agent_team_round_robin_cursors WHERE agent_id IN "
                "(SELECT id FROM access_agents WHERE code LIKE 'MSEG-%')"
            ))
            conn.execute(text(
                "DELETE FROM team_member_market_segments WHERE team_member_id IN "
                "(SELECT tm.id FROM team_members tm JOIN teams t ON t.id=tm.team_id WHERE t.name LIKE 'MSEG-%')"
            ))
            conn.execute(text(
                "DELETE FROM respond_contact_market_segments WHERE contact_id IN "
                "(SELECT id FROM respond_contacts WHERE phone_number LIKE '+999MSEG%')"
            ))
            conn.execute(text(
                "DELETE FROM agent_teams WHERE agent_id IN "
                "(SELECT id FROM access_agents WHERE code LIKE 'MSEG-%')"
            ))
            conn.execute(text(
                "DELETE FROM team_members WHERE team_id IN (SELECT id FROM teams WHERE name LIKE 'MSEG-%')"
            ))
            conn.execute(text("DELETE FROM access_agents WHERE code LIKE 'MSEG-%'"))
            conn.execute(text("DELETE FROM teams WHERE name LIKE 'MSEG-%'"))
            conn.execute(text("DELETE FROM respond_contacts WHERE phone_number LIKE '+999MSEG%'"))
            conn.execute(text("DELETE FROM users WHERE id LIKE 'MSEG-%'"))
            conn.execute(text("DELETE FROM market_segments WHERE code LIKE 'mseg_%'"))
            conn.commit()
        except Exception:
            conn.rollback()


@pytest.fixture(autouse=True)
def _clean():
    _cleanup()
    yield
    _cleanup()


@pytest.fixture
def db() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def client(db) -> Iterator[TestClient]:
    def _user():
        return {"id": "system", "email": "t@t"}

    def _db():
        yield db

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_external_api_user] = _user
    app.dependency_overrides[get_db] = _db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _mk_user(db, uid, name):
    u = User(id=uid, email=f"{uid}@t.co", name=name, status=UserStatus.ACTIVE.value)
    db.add(u)
    return u


def _scenario(db, member_segments: dict[str, list[str]]):
    """Agent + tier-1 team + members with given segments. Returns (agent_id, team_id, members)."""
    agent = AccessAgent(id=str(uuid.uuid4()), code=AGENT_CODE, name="MSEG order enquiries")
    team = Team(id=str(uuid.uuid4()), name=f"{PFX}CS tier1")
    db.add_all([agent, team])
    db.flush()
    db.add(AgentTeam(id=str(uuid.uuid4()), agent_id=agent.id, code=TEAM_SET, team_id=team.id, tier=1))
    seg_by_code = {s.code: s for s in db.query(MarketSegment).all()}
    members = {}
    for i, (key, segs) in enumerate(member_segments.items()):
        u = _mk_user(db, f"{PFX}{key}", key)
        db.flush()
        tm = TeamMember(id=str(uuid.uuid4()), team_id=team.id, user_id=u.id, sort_order=i)
        tm.market_segments = [seg_by_code[c] for c in segs]
        db.add(tm)
        members[key] = u.id
    db.commit()
    return agent.id, team.id, members


def _contact(db, suffix, segments: list[str]) -> RespondContact:
    c = RespondContact(
        id=str(uuid.uuid4()),
        phone_number=f"+999MSEG{suffix}",
        respond_io_id=f"RIO-MSEG-{suffix}",
        name=f"MSEG contact {suffix}",
    )
    seg_by_code = {s.code: s for s in db.query(MarketSegment).all()}
    c.market_segments = [seg_by_code[x] for x in segments]
    db.add(c)
    db.commit()
    return c


# ---------------------------------------------------------------- G: match semantics (service)

def test_roster_filter_retail_project_both_none(db):
    _, team_id, m = _scenario(db, {"A": ["retail"], "B": ["project"], "C": []})
    svc = AccessAgentService(db)

    def names(contact_segments):
        return {r["user_id"] for r in svc.list_active_team_members_detail(team_id, contact_segments)}

    assert names({"retail"}) == {m["A"], m["C"]}              # G1 untagged serves all, G3
    assert names({"project"}) == {m["B"], m["C"]}
    assert names({"retail", "project"}) == {m["A"], m["B"], m["C"]}  # D3 union
    assert names(None) == {m["A"], m["B"], m["C"]}             # G2 no filter
    assert names(set()) == {m["A"], m["B"], m["C"]}


def test_roster_empty_match_falls_back_to_all(db):
    # D8: retail contact, only a project member, no untagged -> fall back to all.
    _, team_id, m = _scenario(db, {"B": ["project"]})
    svc = AccessAgentService(db)
    got = {r["user_id"] for r in svc.list_active_team_members_detail(team_id, {"retail"})}
    assert got == {m["B"]}


# ---------------------------------------------------------------- D: team-members endpoint

def _tm(client, agent_code, **q):
    return client.get("/api/v1/external/team-members", params={"agent_code": agent_code, "team_code": TEAM_SET, "tier": 1, **q})


def test_team_members_endpoint_segment_filter(client, db):
    _, _, m = _scenario(db, {"A": ["retail"], "B": ["project"], "C": []})
    retail_c = _contact(db, "R", ["retail"])
    proj_c = _contact(db, "P", ["project"])
    both_c = _contact(db, "BOTH", ["retail", "project"])
    none_c = _contact(db, "NONE", [])

    def ids(**q):
        r = _tm(client, AGENT_CODE, **q)
        assert r.status_code == 200, r.text
        return {row["user_id"] for row in r.json()}

    assert ids(contact_id=retail_c.respond_io_id) == {m["A"], m["C"]}       # D1
    assert ids(contact_id=proj_c.respond_io_id) == {m["B"], m["C"]}         # D2
    assert ids(contact_id=both_c.respond_io_id) == {m["A"], m["B"], m["C"]}  # D3
    assert ids(contact_id=none_c.respond_io_id) == {m["A"], m["B"], m["C"]}  # D4 untagged contact -> all
    assert ids() == {m["A"], m["B"], m["C"]}                                 # D5 omitted -> all
    assert ids(contact_id="RIO-DOES-NOT-EXIST") == {m["A"], m["B"], m["C"]}  # D6 unknown -> all, 200


def test_team_members_response_shape_unchanged(client, db):
    _scenario(db, {"A": ["retail"]})
    r = _tm(client, AGENT_CODE)
    assert r.status_code == 200
    row = r.json()[0]
    assert set(row.keys()) == {"user_id", "name", "respond_user_id", "email", "sort_order"}


# ---------------------------------------------------------------- E: next-assignee

def _seq(client, agent_code, n, **body):
    # Single CS team per agent in these scenarios -> team_code resolves without tier.
    # (Passing tier here would trip next-assignee's SLA policy_code+tier co-validation.)
    out = []
    for _ in range(n):
        r = client.post("/api/v1/external/next-assignee", json={
            "contact_phone_number": "+60123456789",
            "agent_code": agent_code, "team_code": TEAM_SET, **body,
        })
        assert r.status_code == 200, r.text
        out.append(r.json()["assignee_id"])
    return out


def test_next_assignee_regression_no_contact_id(client, db):
    # E1: no contact_id -> RR over full team, deterministic, '' cursor.
    _, _, m = _scenario(db, {"A": ["retail"], "B": ["project"], "C": []})
    seq = _seq(client, AGENT_CODE, 6)
    # rotates over all three in sort order, wrapping
    assert seq == [m["A"], m["B"], m["C"], m["A"], m["B"], m["C"]]
    key = db.execute(text(
        "SELECT segment_key FROM agent_team_round_robin_cursors c "
        "JOIN access_agents a ON a.id=c.agent_id WHERE a.code=:code"
    ), {"code": AGENT_CODE}).scalars().all()
    assert key == [""]  # only the legacy cursor was touched


def test_next_assignee_segment_scoped(client, db):
    # E3: retail contact -> pool {A,C}, segment-scoped cursor.
    _, _, m = _scenario(db, {"A": ["retail"], "B": ["project"], "C": []})
    retail_c = _contact(db, "R", ["retail"])
    seq = _seq(client, AGENT_CODE, 4, contact_id=retail_c.respond_io_id)
    assert set(seq) == {m["A"], m["C"]}
    assert m["B"] not in seq
    keys = set(db.execute(text(
        "SELECT segment_key FROM agent_team_round_robin_cursors c "
        "JOIN access_agents a ON a.id=c.agent_id WHERE a.code=:code"
    ), {"code": AGENT_CODE}).scalars().all())
    assert "retail" in keys


def test_next_assignee_both_contact_key(client, db):
    _, _, m = _scenario(db, {"A": ["retail"], "B": ["project"], "C": []})
    both_c = _contact(db, "BOTH", ["retail", "project"])
    _seq(client, AGENT_CODE, 2, contact_id=both_c.respond_io_id)
    keys = set(db.execute(text(
        "SELECT segment_key FROM agent_team_round_robin_cursors c "
        "JOIN access_agents a ON a.id=c.agent_id WHERE a.code=:code"
    ), {"code": AGENT_CODE}).scalars().all())
    assert segment_key_for({"retail", "project"}) == "project|retail"
    assert "project|retail" in keys  # E4


def test_next_assignee_untagged_contact_uses_legacy_cursor(client, db):
    # E6: contact with no segment passed -> treated as all -> '' cursor, no separate cursor.
    _, _, m = _scenario(db, {"A": ["retail"], "B": ["project"], "C": []})
    none_c = _contact(db, "NONE", [])
    _seq(client, AGENT_CODE, 3, contact_id=none_c.respond_io_id)
    keys = set(db.execute(text(
        "SELECT segment_key FROM agent_team_round_robin_cursors c "
        "JOIN access_agents a ON a.id=c.agent_id WHERE a.code=:code"
    ), {"code": AGENT_CODE}).scalars().all())
    assert keys == {""}


def test_next_assignee_empty_pool_falls_back(client, db):
    # E5: retail contact but only a project member -> pool empty -> fall back full team, '' cursor.
    _, _, m = _scenario(db, {"B": ["project"]})
    retail_c = _contact(db, "R", ["retail"])
    seq = _seq(client, AGENT_CODE, 2, contact_id=retail_c.respond_io_id)
    assert seq == [m["B"], m["B"]]
    keys = set(db.execute(text(
        "SELECT segment_key FROM agent_team_round_robin_cursors c "
        "JOIN access_agents a ON a.id=c.agent_id WHERE a.code=:code"
    ), {"code": AGENT_CODE}).scalars().all())
    assert keys == {""}


def test_next_assignee_preferred_unchanged(client, db):
    # E2: preferred_assignee_id returns directly, no cursor advance.
    _, _, m = _scenario(db, {"A": ["retail"], "B": ["project"], "C": []})
    r = client.post("/api/v1/external/next-assignee", json={
        "contact_phone_number": "+60123456789", "agent_code": AGENT_CODE,
        "team_code": TEAM_SET, "preferred_assignee_id": m["B"],
    })
    assert r.status_code == 200
    assert r.json()["assignee_id"] == m["B"]


# ---------------------------------------------------------------- B/C/F: assignment + catalog

def test_catalog_crud(client):
    # F1 list seed
    r = client.get("/api/v1/user-management/market-segments/")
    assert r.status_code == 200
    codes = {s["code"] for s in r.json()}
    assert {"retail", "project"} <= codes
    # F2 create
    r = client.post("/api/v1/user-management/market-segments/", json={"code": "mseg_wholesale", "name": "Wholesale"})
    assert r.status_code == 201
    # F2 duplicate -> 409
    r = client.post("/api/v1/user-management/market-segments/", json={"code": "mseg_wholesale", "name": "Dup"})
    assert r.status_code == 409
    # F3 rename
    r = client.put("/api/v1/user-management/market-segments/mseg_wholesale", json={"name": "Wholesale 2"})
    assert r.status_code == 200 and r.json()["name"] == "Wholesale 2"
    # F4 delete (unused) ok
    r = client.delete("/api/v1/user-management/market-segments/mseg_wholesale")
    assert r.status_code == 200


def test_catalog_delete_blocked_when_in_use(client, db):
    _contact(db, "R", ["retail"])
    r = client.delete("/api/v1/user-management/market-segments/retail")
    assert r.status_code == 409  # F4 in-use guard


def test_contact_segment_assignment_endpoints(client, db):
    c = _contact(db, "R", [])
    # B1 empty
    r = client.get(f"/api/v1/user-management/contacts/{c.id}/market-segments")
    assert r.status_code == 200 and r.json()["codes"] == []
    # B2 set both
    r = client.put(f"/api/v1/user-management/contacts/{c.id}/market-segments", json={"codes": ["retail", "project"]})
    assert r.status_code == 200 and set(r.json()["codes"]) == {"retail", "project"}
    # idempotent clear
    r = client.put(f"/api/v1/user-management/contacts/{c.id}/market-segments", json={"codes": []})
    assert r.status_code == 200 and r.json()["codes"] == []


def test_member_segment_assignment_endpoints(client, db):
    _, team_id, m = _scenario(db, {"A": []})
    uid = m["A"]
    r = client.get(f"/api/v1/user-management/teams/{team_id}/members/{uid}/market-segments")
    assert r.status_code == 200 and r.json()["codes"] == []
    r = client.put(f"/api/v1/user-management/teams/{team_id}/members/{uid}/market-segments", json={"codes": ["retail"]})
    assert r.status_code == 200 and r.json()["codes"] == ["retail"]
