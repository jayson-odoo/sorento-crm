"""AGENT-PROJECT-SCOPE: the AI panel answers only about projects the asker can see in the app.

UAC: documentation/plans/ai-assistant/agent-project-scope-11nov-acceptance-criteria.md.

The panel's project reads reach the CRM two ways: the MCP catalog tools (`crm_projects_list`,
`crm_project_detail`, `crm_project_quotations_list`) arrive as an API-key read naming the staff
member in `X-Staff-User`, and `crm_projects_find` calls `list_projects` in process as the user. Both
must apply the Projects list's own access filter (`projects.py` `_visible_to`, the `_own_scope`
router guard). Every user and project here is fictional.
"""
from __future__ import annotations

import uuid

import pytest

from tests.test_staff_read_identity import SORENTO, env, mk_user  # noqa: F401  (env is a fixture)

from app.models.projects import Project
from app.services.chatbot.agent import writes
from tests.chatbot.agent._ported_reads_support import make_ctx, panel_turn

BASE = "/api/v1/project-sales"
VIEW = "projects.projects.view"
VIEW_OWN = "projects.projects.view_own"


def _project(db, owner: str, title: str) -> Project:
    tag = uuid.uuid4().hex[:6].upper()
    row = Project(
        id=str(uuid.uuid4()),
        company_id=SORENTO,
        project_code=f"ZZT-{tag}",
        title=f"ZZT {title} {tag}",
        normalised_title=f"zzt {title.lower()} {tag.lower()}",
        owner_user_id=owner,
        approval_state="approved",
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def world(env):  # noqa: F811
    db = env.db
    member = dict(companies=(SORENTO,), last_active=SORENTO)
    env.sales = mk_user(db, "Sally Sales", perms=(VIEW_OWN,), **member)
    env.owner = mk_user(db, "Oscar Owner", perms=(VIEW,), **member)
    env.admin = mk_user(db, "Ada Admin", roles=("admin",), **member)
    env.mine = _project(db, env.sales, "Residensi Melur")
    env.theirs = [_project(db, env.owner, "Taman Kenanga"), _project(db, env.owner, "Menara Cempaka")]
    env.all_ids = {env.mine.id, *(p.id for p in env.theirs)}
    return env


def _list(env, staff_id: str, **params) -> dict:
    """`crm_projects_list` as the MCP server sends it for a panel turn."""
    query = {"limit": 100, **params}
    resp = env.client.get(f"{BASE}/projects/", params=query, headers=env.ident(staff_id))
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ours(body: dict, ids: set) -> list[dict]:
    return [row for row in body["data"] if row["id"] in ids]


# --- AC-1: count, list and owners are the salesperson's own --------------------------------------
def test_ac1_a_salesperson_listing_projects_gets_only_their_own(world):
    rows = _ours(_list(world, world.sales), world.all_ids)
    assert [r["id"] for r in rows] == [world.mine.id]


def test_ac1_the_count_the_agent_reads_is_the_salespersons_own(world):
    body = _list(world, world.sales, project_ids=",".join(world.all_ids))
    assert body["pagination"]["total"] == 1


def test_ac1_owner_names_the_agent_reads_are_only_their_own(world):
    rows = _ours(_list(world, world.sales), world.all_ids)
    assert {r["owner_name"] for r in rows} == {"ZZT Sally Sales"}


def test_ac1_asking_for_another_owners_pipeline_answers_nothing(world):
    body = _list(world, world.sales, owner_user_ids=world.owner)
    assert _ours(body, world.all_ids) == []


def test_ac1_the_in_process_finder_answers_only_their_own(world):
    ctx = make_ctx(world.sales)
    with panel_turn(world.sales):
        out = writes._projects_find(world.db, ctx, {"query": "ZZT"})
    found = {row["id"] for row in (out.data or {}).get("projects", [])} & world.all_ids
    assert found == {world.mine.id}


# --- AC-2: another owner's project is not found ---------------------------------------------------
@pytest.mark.parametrize("suffix", ["", "/quotations"])
def test_ac2_another_owners_project_is_not_found(world, suffix):
    resp = world.client.get(f"{BASE}/projects/{world.theirs[0].id}{suffix}", headers=world.ident(world.sales))
    assert resp.status_code == 404, resp.text


def test_ac2_their_own_project_still_opens(world):
    resp = world.client.get(f"{BASE}/projects/{world.mine.id}", headers=world.ident(world.sales))
    assert resp.status_code == 200, resp.text


def test_ac2_finding_another_owners_project_by_its_code_finds_nothing(world):
    ctx = make_ctx(world.sales)
    with panel_turn(world.sales):
        out = writes._projects_find(world.db, ctx, {"query": world.theirs[0].project_code})
    assert out.status == "empty"


def test_ac2_the_forecast_stays_closed_to_a_salesperson(world):
    resp = world.client.get(f"{BASE}/reports/forecast", headers=world.ident(world.sales))
    assert resp.status_code == 403


# --- AC-3: admin and full-view holders unchanged --------------------------------------------------
@pytest.mark.parametrize("who", ["admin", "owner"])
def test_ac3_admin_and_full_view_holders_see_every_project(world, who):
    staff = getattr(world, who)
    assert {r["id"] for r in _ours(_list(world, staff), world.all_ids)} == world.all_ids
    resp = world.client.get(f"{BASE}/projects/{world.mine.id}", headers=world.ident(staff))
    assert resp.status_code == 200


# --- AC-4: kill test ------------------------------------------------------------------------------
def test_ac4_without_the_list_filter_the_salesperson_would_see_everything(world, monkeypatch):
    """Proves AC-1 tests the filter: switched off, the same read returns every project."""
    from app.api.v1.projects import projects as route

    monkeypatch.setattr(route, "_visible_to", lambda db, user: None)
    assert {r["id"] for r in _ours(_list(world, world.sales), world.all_ids)} == world.all_ids


# --- AC-5: "my projects" needs no resolve round ---------------------------------------------------
# Crew trace 282dec26 (11 Nov): "which of my projects have quotations" sent `owner_user_ids: "Eric Ng"`, was
# refused ("takes ids from crm_resolve"), and crm_resolve was not among the tools offered, so the agent listed
# every project instead. `"me"` names the asker; the seam swaps in their own user id before the call.
LIST = "crm_projects_list"


def _list_catalog() -> dict:
    props = {k: {"type": "string"} for k in ("contact_id", "space_id", "limit", "owner_user_ids", "project_ids")}
    props["owner_user_ids"]["description"] = "Owner user UUIDs."
    return {LIST: {"description": LIST, "inputSchema": {"type": "object", "properties": props}}}


def _dispatch(world, args, *, seen=None, result=None):
    from app.services.chatbot.agent import tools as agent_tools
    from tests.chatbot.agent._ported_reads_support import Recorder

    rec = Recorder(result=result or {"data": [], "pagination": {"total": 0}})
    with panel_turn(world.sales):
        out = agent_tools.dispatch(
            world.db, make_ctx(world.sales), LIST, dict(args), call=rec, catalog=_list_catalog(), timeout=5.0,
            seen_ids=seen,
        )
    return out, rec


@pytest.mark.parametrize("value", ["me", "Me", ["me"], '["me"]'])
def test_ac5_owner_me_is_sent_as_the_askers_own_user_id(world, value):
    out, rec = _dispatch(world, {"owner_user_ids": value})
    assert out.status != "invalid", out.message
    assert len(rec.calls) == 1
    assert rec.calls[0][1]["owner_user_ids"] == [world.sales]


def test_ac5_me_beside_an_id_never_shown_is_still_refused(world):
    out, rec = _dispatch(world, {"owner_user_ids": ["me", world.owner]})
    assert out.status == "invalid"
    assert rec.calls == []


def test_ac5_a_name_is_still_refused(world):
    out, rec = _dispatch(world, {"owner_user_ids": "Eric Ng"})
    assert out.status == "invalid"
    assert rec.calls == []


def test_ac5_the_model_is_told_it_may_write_me(world):
    from app.services.chatbot.agent import tools as agent_tools

    schema = agent_tools.tool_schemas([agent_tools.REGISTRY[LIST]], _list_catalog())[0]
    hint = schema["function"]["parameters"]["properties"]["owner_user_ids"]["description"]
    assert '"me"' in hint


def test_ac5_the_ids_a_me_listing_returns_stay_usable_for_the_next_call(world):
    """The follow-up of "which of my projects have quotations" is a call per returned project id."""
    seen: set[str] = set()
    out, _ = _dispatch(
        world, {"owner_user_ids": "me"}, seen=seen,
        result={"data": [{"id": world.mine.id, "title": "x"}], "pagination": {"total": 1}},
    )
    assert out.status == "ok", out.message
    assert world.mine.id.lower() in seen
    follow, rec = _dispatch(world, {"project_ids": world.mine.id}, seen=seen)
    assert follow.status != "invalid", follow.message
    assert len(rec.calls) == 1


def test_ac5_the_id_me_is_sent_as_reads_only_the_askers_projects(world):
    """End to end: the owner filter the swap sends, read through the route as a full-view holder."""
    from app.services.chatbot.agent import tools as agent_tools
    from tests.chatbot.agent._ported_reads_support import Recorder

    rec = Recorder(result={"data": [], "pagination": {"total": 0}})
    with panel_turn(world.owner):
        agent_tools.dispatch(
            world.db, make_ctx(world.owner), LIST, {"owner_user_ids": "me"}, call=rec, catalog=_list_catalog(),
            timeout=5.0,
        )
    sent = rec.calls[0][1]["owner_user_ids"]
    body = _list(world, world.owner, owner_user_ids=",".join(sent))
    assert {r["id"] for r in _ours(body, world.all_ids)} == {p.id for p in world.theirs}


def test_ac5_the_tool_description_says_names_are_refused_here(world):
    from app.services.chatbot.agent import tools as agent_tools

    schema = agent_tools.tool_schemas([agent_tools.REGISTRY[LIST]], _list_catalog())[0]
    assert '"me"' in schema["function"]["description"]


def test_ac5_the_hint_is_added_once_and_the_catalogue_is_untouched(world):
    from app.services.chatbot.agent import tools as agent_tools

    cat = _list_catalog()
    for _ in range(2):
        schema = agent_tools.tool_schemas([agent_tools.REGISTRY[LIST]], cat)[0]
    assert schema["function"]["parameters"]["properties"]["owner_user_ids"]["description"].count('"me"') == 1
    assert cat[LIST]["inputSchema"]["properties"]["owner_user_ids"]["description"] == "Owner user UUIDs."


def test_s3_dispatch_keeps_the_owner_counts_after_the_cap(world):
    """Crew pass on 2343: 16 full rows exceed the result cap; the counts are added before it, in dispatch."""
    from app.services.chatbot.agent import tools as agent_tools
    from tests.chatbot.agent._ported_reads_support import Recorder

    owners = ["ZZT A"] * 8 + ["ZZT B"] * 8
    rows = [{"id": f"p{i}", "title": f"P{i}", "owner_name": o, "notes": "x" * 2000} for i, o in enumerate(owners)]
    rec = Recorder(result={"data": rows, "pagination": {"total": 16}})
    with panel_turn(world.sales):
        out = agent_tools.dispatch(
            world.db, make_ctx(world.sales), LIST, {}, call=rec, catalog=_list_catalog(), timeout=5.0
        )
    assert out.status == "ok", out.message
    assert out.more > 0
    assert out.data["count_by_owner"] == [{"owner": "ZZT A", "projects": 8}, {"owner": "ZZT B", "projects": 8}]
