"""Sales asks to-do, the CRM half (lane SALES-ASKS-TODO): AC-ST202 to AC-ST207.

`/api/v1/sales/customer-asks/{todo,agents,<id>}` at route level, so the permission gates and
the company scope are part of what is tested. A REAL `users` row carries `respond_contact_id`,
because the route resolves "me" from the database, not from the token dict.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.models.base import company_scope
from app.models.user import User

from . import _ask_todo_seed as seed
from ._ask_todo_seed import SORENTO
from ._mc_lookup_seed import seed_mocha
from ._pg_fixture import blank_session

VIEW = "sales.customer_asks.view"
EDIT = "sales.customer_asks.edit"
VIEW_ALL = "sales.customer_asks.view_all"
BASE = "/api/v1/sales/customer-asks"


def _today_start_now() -> datetime:
    """Malaysia midnight of the real now as naive UTC (the routes use the real clock)."""
    my = datetime.utcnow() + timedelta(hours=8)
    return my.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=8)


def _user(db, name: str, contact_id) -> User:
    uid = seed.uid()
    row = User(id=uid, email=f"{uid}@zzt.test", name=name, status="ACTIVE", respond_contact_id=contact_id)
    db.add(row)
    db.flush()
    return row


def _client(db, permissions, user: User):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    actor = {"id": user.id, "email": user.email, "name": user.name, "role": "user"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    app.dependency_overrides[apply_company_scope] = lambda: None
    originals = (
        UserPermissionService.check_user_has_permission,
        UserPermissionService.get_user_permission_slugs,
    )
    granted = list(permissions)
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: slug in granted
    UserPermissionService.get_user_permission_slugs = lambda self, uid: list(granted)
    return TestClient(app, raise_server_exceptions=False), originals


def _restore(originals) -> None:
    from app.main import app
    from app.services.user_service import UserPermissionService

    UserPermissionService.check_user_has_permission = originals[0]
    UserPermissionService.get_user_permission_slugs = originals[1]
    app.dependency_overrides.clear()


@pytest.fixture
def w():
    with blank_session() as db:
        with company_scope(db, frozenset({SORENTO})):
            world = seed.world(db)
            start = _today_start_now()
            old = start - timedelta(days=3)
            world.update(
                db=db,
                start=start,
                x_old=seed.ask(db, world["x"], world["dealer"], "SRT-XOLD", created_at=old),
                y_yday=seed.ask(db, world["y"], world["dealer"], "SRT-YYDAY", created_at=start - timedelta(hours=5)),
                x_today=seed.ask(db, world["x"], world["dealer"], "SRT-XTODAY", created_at=start + timedelta(seconds=1)),
                x_incoming=seed.ask(db, world["x"], world["dealer"], "SRT-XINC", created_at=old, branch="incoming"),
                x_done=seed.ask(
                    db, world["x"], world["dealer"], "SRT-XDONE", created_at=old, state="done",
                    done_at=datetime.utcnow(), done_by_contact_id=world["dealer"],
                ),
                z_old=seed.ask(db, world["z"], world["dealer"], "SRT-ZOLD", created_at=old),
                z_today=seed.ask(db, world["z"], world["dealer"], "SRT-ZTODAY", created_at=start + timedelta(seconds=1)),
            )
            world["me"] = _user(db, "Alpha Person", world["ca"])
            world["unlinked"] = _user(db, "No Contact", None)
            world["no_agent"] = _user(db, "Dealer Only", world["dealer"])
            db.commit()
            yield world


def _call(w, permissions, user_key, method, path, **kw):
    client, originals = _client(w["db"], permissions, w[user_key])
    try:
        return getattr(client, method)(f"{BASE}{path}", **kw)
    finally:
        _restore(originals)


# ---- AC-ST202 ---------------------------------------------------------------------------


def test_agent_for_user(w):
    from app.services.sales.portal_agent import agent_for_user

    db = w["db"]
    assert agent_for_user(db, w["me"].id).id == w["a"].id
    assert agent_for_user(db, w["unlinked"].id) is None
    assert agent_for_user(db, w["no_agent"].id) is None


# ---- AC-ST203 ---------------------------------------------------------------------------


def test_todo_mine_and_unlinked_and_403(w):
    resp = _call(w, [VIEW], "me", "get", "/todo")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert {r["id"] for r in body["open"]} == {w["x_old"].id, w["y_yday"].id, w["x_today"].id, w["x_incoming"].id}
    assert [r["id"] for r in body["done_today"]] == [w["x_done"].id]
    assert body["agent"]["code"] == w["a"].sales_agent
    assert "name" in body["agent"]
    assert body["today_start"].endswith("Z")
    for key in ("customer_id", "sales_agent_id"):
        assert key not in body["open"][0]

    for key in ("unlinked", "no_agent"):
        empty = _call(w, [VIEW], key, "get", "/todo")
        assert empty.status_code == 200, empty.text
        payload = empty.json()
        assert payload["open"] == [] and payload["done_today"] == []
        assert payload["agent"] is None

    assert _call(w, [], "me", "get", "/todo").status_code == 403


# ---- AC-ST204 ---------------------------------------------------------------------------


def test_todo_agent_id_scope(w):
    ok = _call(w, [VIEW, VIEW_ALL], "me", "get", f"/todo?agent_id={w['b'].id}")
    assert ok.status_code == 200, ok.text
    assert {r["id"] for r in ok.json()["open"]} == {w["z_old"].id, w["z_today"].id}
    assert ok.json()["agent"]["code"] == w["b"].sales_agent

    plain = _call(w, [VIEW], "me", "get", f"/todo?agent_id={w['b'].id}")
    assert plain.status_code == 403
    assert plain.json().get("code") == "NOT_YOUR_AGENT", plain.text
    assert _call(w, [VIEW, VIEW_ALL], "me", "get", f"/todo?agent_id={seed.uid()}").status_code == 404


def test_todo_all_agents_carries_agent_code(w):
    resp = _call(w, [VIEW, VIEW_ALL], "me", "get", "/todo?agent_id=all")
    assert resp.status_code == 200, resp.text
    rows = resp.json()["open"]
    assert {r["id"] for r in rows} == {w["x_old"].id, w["y_yday"].id, w["x_today"].id, w["x_incoming"].id, w["z_old"].id, w["z_today"].id}
    codes = {r["id"]: r["agent_code"] for r in rows}
    assert codes[w["x_old"].id] == w["a"].sales_agent
    assert codes[w["z_old"].id] == w["b"].sales_agent
    plain = _call(w, [VIEW], "me", "get", "/todo?agent_id=all")
    assert plain.status_code == 403
    assert plain.json().get("code") == "NOT_YOUR_AGENT", plain.text


# ---- AC-ST205 ---------------------------------------------------------------------------


def test_agents_list_counts(w):
    seed.agent(w["db"], seed.contact(w["db"], "Agent Idle"), "IDLE")
    resp = _call(w, [VIEW, VIEW_ALL], "me", "get", "/agents")
    assert resp.status_code == 200, resp.text
    by_code = {r["code"]: r for r in resp.json()}
    assert set(by_code) == {w["a"].sales_agent, w["b"].sales_agent}  # the idle agent has no open ask
    a = by_code[w["a"].sales_agent]
    assert a["agent_id"] == w["a"].id and "name" in a
    assert (a["open"], a["needs_attention"]) == (4, 3)  # the incoming row counts (Q5 (a)); done rows never do
    b = by_code[w["b"].sales_agent]
    assert (b["open"], b["needs_attention"]) == (2, 1)

    plain = _call(w, [VIEW], "me", "get", "/agents")
    assert plain.status_code == 200, plain.text
    assert plain.json() == []


# ---- AC-ST215 ---------------------------------------------------------------------------


def _team(db, name, leader, member_rows, *, is_active=True):
    """`member_rows`: [(agent, valid_to)]. The leader is set AFTER the memberships exist:
    `trg_sales_teams_leader_is_member` wants the leader to be a current member."""
    from app.models.sales import SalesTeam, SalesTeamMember

    team = SalesTeam(id=seed.uid(), company_id=SORENTO, name=f"ZZT {name} {seed.uid()[:6]}", is_active=is_active)
    db.add(team)
    db.flush()
    for agent, valid_to in member_rows:
        db.add(
            SalesTeamMember(
                id=seed.uid(), company_id=SORENTO, sales_team_id=team.id, sales_agent_id=agent.id, valid_to=valid_to
            )
        )
    db.flush()
    team.leader_sales_agent_id = leader.id
    db.flush()
    return team


@pytest.fixture
def led(w):
    """A leads active team T with current members A and B; C left T yesterday; D is in no team."""
    db = w["db"]
    w["c"] = seed.agent(db, seed.contact(db, "Agent Gamma"), "C")
    w["d"] = seed.agent(db, seed.contact(db, "Agent Delta"), "D")
    c_cust = seed.customer(db, "Customer C", w["c"])
    d_cust = seed.customer(db, "Customer D", w["d"])
    w["c_ask"] = seed.ask(db, c_cust, w["dealer"], "SRT-C", created_at=w["start"] + timedelta(seconds=1))
    w["d_ask"] = seed.ask(db, d_cust, w["dealer"], "SRT-D", created_at=w["start"] + timedelta(seconds=1))
    yesterday = (datetime.utcnow() - timedelta(days=1)).date()
    w["team"] = _team(db, "T", w["a"], [(w["a"], None), (w["b"], None), (w["c"], yesterday)])
    db.commit()
    return w


def test_team_leader_scope(led):
    w = led
    agents = _call(w, [VIEW], "me", "get", "/agents")
    assert agents.status_code == 200, agents.text
    by_code = {r["code"]: r for r in agents.json()}
    assert set(by_code) == {w["a"].sales_agent, w["b"].sales_agent}  # not C (left), not D (no team)
    assert by_code[w["a"].sales_agent]["open"] == 4

    b = _call(w, [VIEW], "me", "get", f"/todo?agent_id={w['b'].id}")
    assert b.status_code == 200, b.text
    assert {r["id"] for r in b.json()["open"]} == {w["z_old"].id, w["z_today"].id}

    for other in ("c", "d"):
        denied = _call(w, [VIEW], "me", "get", f"/todo?agent_id={w[other].id}")
        assert denied.status_code == 403, denied.text
        assert denied.json().get("code") == "NOT_YOUR_AGENT"

    everyone = _call(w, [VIEW], "me", "get", "/todo?agent_id=all")
    assert everyone.status_code == 200, everyone.text
    rows = everyone.json()["open"]
    assert {r["id"] for r in rows} == {
        w["x_old"].id, w["y_yday"].id, w["x_today"].id, w["x_incoming"].id, w["z_old"].id, w["z_today"].id
    }
    assert {r["agent_code"] for r in rows} == {w["a"].sales_agent, w["b"].sales_agent}


def test_team_leader_agents_list_counts_members_with_zero_open(led):
    w = led
    idle = seed.agent(w["db"], seed.contact(w["db"], "Agent Idle"), "IDLE")
    w["db"].add(
        __import__("app.models.sales", fromlist=["SalesTeamMember"]).SalesTeamMember(
            id=seed.uid(), company_id=SORENTO, sales_team_id=w["team"].id, sales_agent_id=idle.id
        )
    )
    w["db"].commit()
    by_code = {r["code"]: r for r in _call(w, [VIEW], "me", "get", "/agents").json()}
    assert (by_code[idle.sales_agent]["open"], by_code[idle.sales_agent]["needs_attention"]) == (0, 0)


def test_a_leader_of_an_inactive_team_is_nobodys_leader(w):
    db = w["db"]
    _team(db, "Off", w["a"], [(w["a"], None), (w["b"], None)], is_active=False)
    db.commit()
    assert _call(w, [VIEW], "me", "get", "/agents").json() == []
    denied = _call(w, [VIEW], "me", "get", f"/todo?agent_id={w['b'].id}")
    assert denied.status_code == 403
    assert denied.json().get("code") == "NOT_YOUR_AGENT"


def test_a_leader_row_in_another_company_grants_nothing(w):
    """A team of ANOTHER company led by agent A with member B never makes A their leader here."""
    from app.models.sales import SalesTeam, SalesTeamMember

    db = w["db"]
    mocha = seed_mocha(db)
    team = SalesTeam(id=seed.uid(), company_id=mocha.id, name=f"ZZT Foreign {seed.uid()[:6]}", is_active=True)
    db.add(team)
    db.flush()
    for agent in (w["a"], w["b"]):
        db.add(SalesTeamMember(id=seed.uid(), company_id=mocha.id, sales_team_id=team.id, sales_agent_id=agent.id))
    db.flush()
    team.leader_sales_agent_id = w["a"].id
    db.commit()

    assert _call(w, [VIEW], "me", "get", "/agents").json() == []
    denied = _call(w, [VIEW], "me", "get", f"/todo?agent_id={w['b'].id}")
    assert denied.status_code == 403, denied.text
    assert denied.json().get("code") == "NOT_YOUR_AGENT"


# ---- AC-ST216 ---------------------------------------------------------------------------


def test_team_leader_can_clear_a_members_ask(led):
    w = led
    ok = _call(w, [VIEW, EDIT], "me", "patch", f"/{w['z_old'].id}", json={"state": "done"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["done_by"] == "Alpha Person"
    w["db"].expire_all()
    assert w["db"].get(seed.StockAsk, w["z_old"].id).done_by_user_id == w["me"].id

    for key in ("c_ask", "d_ask"):  # C's membership ended; D is in no team
        denied = _call(w, [VIEW, EDIT], "me", "patch", f"/{w[key].id}", json={"state": "done"})
        assert denied.status_code == 404, denied.text


# ---- AC-ST206 ---------------------------------------------------------------------------


def test_patch_scope_and_stamps(w):
    resp = _call(w, [VIEW, EDIT], "me", "patch", f"/{w['x_old'].id}", json={"state": "done"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["done_by"] == "Alpha Person"
    assert resp.json()["done_at"]
    assert "done_by_user_id" not in resp.json()
    w["db"].expire_all()
    assert w["db"].get(seed.StockAsk, w["x_old"].id).done_by_user_id == w["me"].id

    assert _call(w, [VIEW, EDIT], "me", "patch", f"/{w['z_old'].id}", json={"state": "done"}).status_code == 404

    office = _call(w, [VIEW, EDIT, VIEW_ALL], "me", "patch", f"/{w['z_old'].id}", json={"state": "done"})
    assert office.status_code == 200, office.text
    assert office.json()["done_by"] == "Alpha Person"
    w["db"].expire_all()
    assert w["db"].get(seed.StockAsk, w["z_old"].id).done_by_user_id == w["me"].id

    assert _call(w, [VIEW], "me", "patch", f"/{w['y_yday'].id}", json={"state": "done"}).status_code == 403
    assert _call(w, [VIEW, EDIT], "me", "patch", f"/{w['y_yday'].id}", json={"state": "closed"}).status_code == 422


# ---- AC-ST207 ---------------------------------------------------------------------------


def test_company_scope_holds(w):
    db = w["db"]
    mocha = seed_mocha(db)
    client, originals = _client(db, [VIEW, EDIT, VIEW_ALL], w["me"])
    try:
        with company_scope(db, frozenset({mocha.id})):
            todo = client.get(f"{BASE}/todo")
            patched = client.patch(f"{BASE}/{w['x_old'].id}", json={"state": "done"})
            agents = client.get(f"{BASE}/agents")
    finally:
        _restore(originals)
    assert todo.status_code == 200, todo.text
    assert todo.json()["open"] == [] and todo.json()["done_today"] == []
    assert patched.status_code == 404
    assert "SRT-X" not in agents.text and "SRT-Z" not in agents.text
    assert all(r["open"] == 0 for r in agents.json()) if agents.status_code == 200 else True
