"""`sales.targets.view_own` (owner ruling 5 Nov 23:2x, lane AI-TOOLS-WAVE2): a holder without `sales.targets.view`
sees only the agent targets of their OWN sales agents (`own_scope.me().agent_ids`, the user's linked contact), with
their commission, on the Sales targets screen and in `crm_query`, and the two agree. `sales.targets.view` still
sees everything. Written red-first against the plan's "Own-only targets" section.

Seeds and fixtures are the S1 file's: blank schema, the SRT company in scope, today pinned to 20 Oct 2026.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from tests import _own_scope_support as own
from tests.test_dealer_targets_api import _customer, _dealer_body, _product_id
from tests.test_sales_targets_s1 import BASE, _agent, _restore, _so_line, world  # noqa: F401  (fixture)

VIEW = "sales.targets.view"
VIEW_OWN = "sales.targets.view_own"
YEAR = {"field": "period", "op": "between", "value": ["01/07/2026", "31/12/2026"]}


def _client_as(db, user_id, permissions):
    """`test_sales_targets_s1._client` for a real user row (own_scope reads the user's linked contact)."""
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    actor = {"id": user_id, "email": f"{user_id}@zzt.test", "role": "user"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    app.dependency_overrides[apply_company_scope] = lambda: None
    originals = (UserPermissionService.check_user_has_permission, UserPermissionService.get_user_permission_slugs)
    granted = list(permissions)
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: slug in granted
    UserPermissionService.get_user_permission_slugs = lambda self, uid: list(granted)
    return TestClient(app), originals


def _agent_target(client, agent, tiers=None):
    res = client.post(BASE, json={
        "subject_kind": "agent", "sales_agent_id": agent.id, "name": f"ZZT {agent.sales_agent}",
        "metric": "amount", "basis": "ordered", "product_scope": "all",
        "start_date": "2026-07-01", "end_date": "2026-12-31", "split_every": 1, "split_unit": "month",
        "target_value": 10000, "commission_method": "retroactive" if tiers else "none", "tiers": tiers or [],
    })
    assert res.status_code == 201, res.text
    return res.json()


@pytest.fixture
def scene(world):
    """Me (a user linked to contact C, which is sales agent MINE) and another agent OTHER, each with an agent
    target with commission; a team target and a dealer target. Created by an admin holding every slug."""
    db, company_id = world
    me_contact = own.contact(db, "Me")
    me_user = own.user(db, "Me", me_contact.id)
    mine = own.agent(db, company_id, "MINE", me_contact.id)
    other = _agent(db, "OTHER", "Other Agent")
    admin, originals = _client_as(
        db, own.uid(), [VIEW, "sales.targets.add", "sales.targets.edit", "sales.teams.view", "sales.teams.add"]
    )
    try:
        tiers = [{"from_pct": 80, "rate": 2}, {"from_pct": 100, "rate": 3}]
        t_mine, t_other = _agent_target(admin, mine, tiers), _agent_target(admin, other, tiers)
        pid = _product_id(db, company_id)
        for agent in (mine, other):
            _so_line(db, company_id, agent_id=agent.id, order_date=date(2026, 9, 10), line_total=Decimal("12000"), product_id=pid)
        dealer = _customer(db, company_id, "ZZT OWN DEALER", level=1)
        t_dealer = admin.post(BASE, json=_dealer_body([dealer])).json()
        # A team target with MY agent as a member: the plausible leak to an own-only holder.
        team = admin.post("/api/v1/sales/teams", json={"name": f"ZZT Own Team {own.uid()[:6]}", "sales_agent_ids": [mine.id, other.id]}).json()
        t_team = admin.post(BASE, json={
            "subject_kind": "team", "sales_team_id": team["id"], "name": "ZZT own team target", "metric": "amount",
            "basis": "ordered", "product_scope": "all", "start_date": "2026-10-01", "end_date": "2026-10-31",
            "agent_figures": [{"sales_agent_id": mine.id, "target_value": 600}, {"sales_agent_id": other.id, "target_value": 400}],
        })
        assert t_team.status_code == 201, t_team.text
        # Sales with no agent this month: the company-wide "unassigned" figure of the dated list.
        _so_line(db, company_id, agent_id=None, order_date=date(2026, 10, 3), line_total=Decimal("500"), product_id=pid)
    finally:
        _restore(originals)
    # The team target's child for MY agent is an agent target of mine: an own holder sees it (Oct only).
    my_child = next(c["target_id"] for c in t_team.json()["children"] if c["sales_agent_id"] == mine.id)
    return db, me_user, {
        "mine": t_mine, "other": t_other, "dealer": t_dealer, "team": t_team.json(), "agent_mine": mine,
        "my_child": my_child,
    }


@pytest.fixture
def as_own(scene):
    db, me_user, t = scene
    client, originals = _client_as(db, me_user, [VIEW_OWN])
    try:
        yield client, db, me_user, t
    finally:
        _restore(originals)


def _ids(body) -> set[str]:
    return {r["target_id"] for r in body["rows"] if r.get("target_id")}


# ------------------------------------------------------------------ the screen


def test_O1_list_agent_tab_shows_only_my_agents_targets(as_own):
    client, _db, _u, t = as_own
    res = client.get(BASE, params={"all": "true", "subject": "agent"})
    assert res.status_code == 200, res.text
    assert _ids(res.json()) == {t["mine"]["id"], t["my_child"]}


def test_O2_team_and_dealer_tabs_are_empty_for_an_own_holder(as_own):
    client, _db, _u, t = as_own
    for subject in ("team", "dealer"):
        for params in ({"all": "true", "subject": subject}, {"subject": subject}):
            res = client.get(BASE, params=params)
            assert res.status_code == 200, res.text
            assert _ids(res.json()) == set(), params
            assert all(r.get("sales_team_id") is None for r in res.json()["rows"]), params
            # The company-wide figures are not theirs to see.
            assert res.json()["unassigned_amount"] == 0 and res.json()["no_team_count"] == 0, params
    res = client.get(BASE, params={"subject": "agent"})  # the dated view too
    assert res.status_code == 200
    assert {r.get("sales_agent_id") for r in res.json()["rows"]} <= {t["agent_mine"].id}
    assert res.json()["unassigned_amount"] == 0
    assert client.get(f"{BASE}/{t['team']['id']}").status_code == 404


def test_O3_detail_of_my_target_with_commission_others_are_not_found(as_own):
    client, _db, _u, t = as_own
    res = client.get(f"{BASE}/{t['mine']['id']}")
    assert res.status_code == 200, res.text
    sep = next(p for p in res.json()["periods"] if p["period_start"] == "2026-09-01")
    assert sep["commission_earned"] == 360.0
    for key in ("other", "dealer"):
        assert client.get(f"{BASE}/{t[key]['id']}").status_code == 404, key


def test_O4_commission_statement_only_for_my_targets(as_own):
    client, _db, _u, t = as_own
    res = client.post(f"{BASE}/commission-statement", json={"ids": [t["other"]["id"]]})
    assert res.status_code == 404, res.text


def test_O5_no_targets_slug_is_still_refused(scene):
    db, me_user, _t = scene
    client, originals = _client_as(db, me_user, ["sales.opportunities.view_own"])
    try:
        assert client.get(BASE, params={"all": "true", "subject": "agent"}).status_code == 403
    finally:
        _restore(originals)


def test_O6_view_holder_still_sees_everything(scene):
    db, me_user, t = scene
    client, originals = _client_as(db, me_user, [VIEW, VIEW_OWN])
    try:
        assert _ids(client.get(BASE, params={"all": "true", "subject": "agent"}).json()) >= {t["mine"]["id"], t["other"]["id"]}
        assert client.get(f"{BASE}/{t['other']['id']}").status_code == 200
        dated = client.get(BASE, params={"subject": "team"}).json()
        assert dated["unassigned_amount"] > 0
        assert t["team"]["id"] in _ids(dated)
    finally:
        _restore(originals)


def test_O12_the_period_cap_counts_only_my_periods(as_own, monkeypatch):
    """7 periods are mine (6 months and the team child's October), far more are the company's: an own holder under
    a cap of 8 is answered."""
    from app.services.assistant_registry import computed

    _client_, db, me_user, t = as_own
    monkeypatch.setattr(computed, "MAX_COMPUTED_ROWS", 8)
    out = _query(db, me_user, {VIEW_OWN}, {"entity": "sales_target", "filters": [YEAR], "limit": 50})
    assert len(out["rows"]) == 7


# ------------------------------------------------------------------ crm_query, and the two agree


def _query(db, user_id, slugs, spec):
    from app.services.assistant_registry import query

    original = query._slugs
    query._slugs = lambda _db, _uid: set(slugs)
    try:
        return query.run_query(db, user_id, spec)
    finally:
        query._slugs = original


def test_O7_crm_query_own_holder_reads_only_their_targets_and_the_screen_agrees(as_own):
    client, db, me_user, t = as_own
    out = _query(db, me_user, {VIEW_OWN}, {"entity": "sales_target", "filters": [YEAR], "fields": ["payout"], "limit": 50})
    links = {r["link"] for r in out["rows"]}
    assert links == {f"/sales/targets/{t['mine']['id']}", f"/sales/targets/{t['my_child']}"}
    assert len(out["rows"]) == 6 + 1
    sep = next(r for r in out["rows"] if r["payout"])
    assert sep["payout"] == 360.0
    screen = _ids(client.get(BASE, params={"all": "true", "subject": "agent"}).json())
    assert {link.rsplit("/", 1)[1] for link in links} == screen


def test_O8_crm_query_view_holder_reads_all_and_own_flag_in_describe(as_own):
    _client, db, me_user, t = as_own
    out = _query(db, me_user, {VIEW}, {"entity": "sales_target", "filters": [YEAR], "fields": ["payout"], "limit": 50})
    assert {f"/sales/targets/{t[k]['id']}" for k in ("mine", "other", "dealer")} <= {r["link"] for r in out["rows"]}
    from app.services.assistant_registry import query

    original = query._slugs
    query._slugs = lambda _db, _uid: {VIEW_OWN}
    try:
        assert query.describe(db, me_user, "sales_target")["only_own_rows"] is True
    finally:
        query._slugs = original


def test_O9_own_holder_with_no_linked_agent_reads_nothing(scene):
    db, _me, _t = scene
    lonely = own.user(db, "Lonely")
    out = _query(db, lonely, {VIEW_OWN}, {"entity": "sales_target", "filters": [YEAR]})
    assert out["rows"] == []


def test_O10_the_slug_is_registered_and_seeded_to_no_role():
    import importlib.util
    import pathlib

    from app.rbac.permission_registry import PERMISSION_REGISTRY

    assert VIEW_OWN in {p["slug"] for p in PERMISSION_REGISTRY}
    found = [p for p in pathlib.Path("alembic/versions").glob("*.py") if VIEW_OWN in p.read_text()]
    assert len(found) == 1, found
    source = found[0].read_text()
    assert "user_role_permissions" not in source.split("def downgrade")[0], "granted to nobody by default"
    spec = importlib.util.spec_from_file_location("m", found[0])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert len(module.revision) <= 32


def test_O11_writes_follow_the_own_rule(scene):
    """Security review round 2: with `.edit` / `.add` / `.delete` beside `view_own`, a write on another agent's
    target is a 404 (it never answers with that target's figures), creating one for another agent is refused,
    and the deferred delete repeats the rule."""
    from app.services import own_scope
    from app.services.error_handler import AppException

    db, me_user, t = scene
    perms = [VIEW_OWN, "sales.targets.add", "sales.targets.edit", "sales.targets.delete"]
    client, originals = _client_as(db, me_user, perms)
    try:
        other = t["other"]["id"]
        assert client.patch(f"{BASE}/{other}", json={"name": "ZZT renamed"}).status_code == 404
        assert client.post(f"{BASE}/{other}/duplicate").status_code == 404
        assert client.delete(f"{BASE}/{other}").status_code == 404
        assert client.patch(f"{BASE}/{t['mine']['id']}", json={"name": "ZZT mine renamed"}).status_code == 200
        body = {
            "subject_kind": "agent", "name": "ZZT new", "metric": "amount", "basis": "ordered",
            "product_scope": "all", "start_date": "2026-11-01", "end_date": "2026-11-30", "target_value": 1,
        }
        other_agent = db.get(type(t["agent_mine"]), next(iter([t["other"]["sales_agent_id"]])))
        assert client.post(BASE, json={**body, "sales_agent_id": other_agent.id}).status_code == 403
        assert client.post(BASE, json={**body, "sales_agent_id": t["agent_mine"].id}).status_code == 201
        with pytest.raises(AppException) as info:
            own_scope.assert_pending_action_allowed(db, "sales_target.delete", other, me_user)
        assert info.value.status_code == 404
        own_scope.assert_pending_action_allowed(db, "sales_target.delete", t["mine"]["id"], me_user)
    finally:
        _restore(originals)
