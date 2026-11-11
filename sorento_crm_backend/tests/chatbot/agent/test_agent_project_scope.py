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


def test_d_dispatch_hands_the_model_one_project_name(world):
    """Crew re-pass (d): the Projects list's name (short name, else title), never the long title beside it."""
    from app.services.chatbot.agent import tools as agent_tools
    from tests.chatbot.agent._ported_reads_support import Recorder

    rows = [{"id": "p1", "project_code": "PPF2611010", "title": "ZZT Long Legal Title Phase 2", "name": "ZZT Melur",
             "owner_name": "ZZT A"}]
    rec = Recorder(result={"data": rows, "pagination": {"total": 1}})
    with panel_turn(world.sales):
        out = agent_tools.dispatch(world.db, make_ctx(world.sales), LIST, {}, call=rec, catalog=_list_catalog(), timeout=5.0)
    assert out.data["data"][0]["name"] == "ZZT Melur" and "title" not in out.data["data"][0]


def test_d_the_finder_names_a_project_as_the_projects_list_does(world):
    world.mine.name = "ZZT Melur Short"
    world.db.flush()
    with panel_turn(world.sales):
        out = writes._projects_find(world.db, make_ctx(world.sales), {"query": world.mine.project_code})
    row = out.data["projects"][0]
    assert row["name"] == "ZZT Melur Short" and "title" not in row


@pytest.mark.parametrize("principal", ["user", "contact"])
def test_a_the_prompt_the_agent_gets_carries_the_answer_scope_rule(world, principal):
    from app.services.chatbot.agent import loop

    assert "ANSWER ONLY WHAT WAS ASKED" in loop._system_prompt(world.db, "ZZT User", (), principal)


# --- crew pass on 6aef629d: a "my projects" ask with the Projects page open --------------------------
# S owns 0 projects. The "me" read returned 0 rows; the model then listed all 16 unfiltered and presented another
# owner's rows (and count) as S's own. The fix is in the data, not in words: every row says whether the viewer owns
# it, a complete read says how many are the asker's, an empty "me" read says that is the answer, and an
# owner-filtered read carries no per-owner breakdown to repeat.
def test_e_every_project_row_says_whether_the_viewer_owns_it(world):
    rows = {r["id"]: r for r in _list(world, world.owner)["data"]}
    assert rows[world.mine.id]["owner_is_viewer"] is False
    assert all(rows[p.id]["owner_is_viewer"] is True for p in world.theirs)


def test_e_the_detail_says_it_too(world):
    body = world.client.get(f"{BASE}/projects/{world.mine.id}", headers=world.ident(world.sales)).json()
    assert body["owner_is_viewer"] is True


def _dispatch_rows(world, args, rows, total=None):
    from app.services.chatbot.agent import tools as agent_tools
    from tests.chatbot.agent._ported_reads_support import Recorder

    rec = Recorder(result={"data": rows, "pagination": {"total": len(rows) if total is None else total}})
    with panel_turn(world.sales):
        return agent_tools.dispatch(world.db, make_ctx(world.sales), LIST, dict(args), call=rec,
                                    catalog=_list_catalog(), timeout=5.0)


def _row(i, owner, mine=False):
    return {"id": f"p{i}", "project_code": f"PPF{i}", "name": f"ZZT P{i}", "owner_name": owner, "owner_is_viewer": mine}


def test_e_a_complete_read_says_how_many_are_the_askers_own(world):
    rows = [_row(i, "ZZT Oscar") for i in range(8)] + [_row(9, "ZZT Sally", True)]
    out = _dispatch_rows(world, {}, rows)
    assert out.data["your_projects"] == 1


def test_e_a_complete_read_says_zero_when_none_is_theirs(world):
    out = _dispatch_rows(world, {}, [_row(i, "ZZT Oscar") for i in range(8)])
    assert out.data["your_projects"] == 0


def test_e_an_owner_filtered_read_carries_no_per_owner_breakdown(world):
    out = _dispatch_rows(world, {"owner_user_ids": "me"}, [_row(1, "ZZT Sally", True)])
    assert "count_by_owner" not in out.data


def test_e_an_empty_me_read_says_it_is_the_answer(world):
    from app.services.chatbot.agent import tools as agent_tools
    from tests.chatbot.agent._ported_reads_support import Recorder

    rec = Recorder(result={"data": [], "pagination": {"total": 0}, "empty": True})
    with panel_turn(world.sales):
        out = agent_tools.dispatch(world.db, make_ctx(world.sales), LIST, {"owner_user_ids": "me"}, call=rec,
                                   catalog=_list_catalog(), timeout=5.0)
    assert out.status == "empty"
    assert out.message == agent_tools.NONE_OF_YOURS


def test_e_an_empty_read_of_someone_else_keeps_the_plain_message(world):
    from app.services.chatbot.agent import tools as agent_tools
    from tests.chatbot.agent._ported_reads_support import Recorder

    seen = {world.owner.lower()}
    rec = Recorder(result={"data": [], "pagination": {"total": 0}, "empty": True})
    with panel_turn(world.sales):
        out = agent_tools.dispatch(world.db, make_ctx(world.sales), LIST, {"owner_user_ids": world.owner}, call=rec,
                                   catalog=_list_catalog(), timeout=5.0, seen_ids=seen)
    assert out.status == "empty" and out.message == agent_tools.NO_ROWS_MESSAGE


def test_e_the_page_note_says_screen_rows_are_not_the_users_own(world):
    from app.schemas.ai_assistant import PageSnapshotPayload
    from app.services.chatbot import panel_service

    snap = PageSnapshotPayload(title="Projects", path="/project-sales/projects", visible_text="PPF1 Oscar Owner")
    _, note = panel_service._page_context(world.db, world.sales, snap)
    assert panel_service.SCREEN_NOT_YOURS in note


def test_f_a_project_row_says_how_many_quotation_documents_it_has(world):
    """Crew case A: "do any of my projects have quotations?" was answered with every scope's total nobody asked for.
    The list itself now says how many quotation documents each project has, so the question needs no totals read."""
    from app.models.projects import ProjectQuotationDocument

    for i in range(2):
        world.db.add(ProjectQuotationDocument(
            id=str(uuid.uuid4()), company_id=SORENTO, project_id=world.mine.id, document_no=f"ZZT-QD-{i}-{uuid.uuid4().hex[:4]}",
        ))
    world.db.flush()
    rows = {r["id"]: r for r in _list(world, world.owner)["data"]}
    assert rows[world.mine.id]["quotation_document_count"] == 2
    assert rows[world.theirs[0].id]["quotation_document_count"] == 0


@pytest.mark.parametrize("extra", [{"outcome": "won"}, {"status_key": "final_negotiation"}, {"only_critical": "true"}])
def test_e_an_empty_me_read_with_another_filter_never_says_they_own_none(world, extra):
    """Review round 6: "which of my projects are won?" emptied by `outcome` is not "you own none"."""
    from app.services.chatbot.agent import tools as agent_tools
    from tests.chatbot.agent._ported_reads_support import Recorder

    catalog = _list_catalog()
    catalog[LIST]["inputSchema"]["properties"].update({k: {"type": "string"} for k in ("outcome", "status_key", "only_critical", "page", "sort", "dir")})
    rec = Recorder(result={"data": [], "pagination": {"total": 0}, "empty": True})
    with panel_turn(world.sales):
        out = agent_tools.dispatch(world.db, make_ctx(world.sales), LIST, {"owner_user_ids": "me", **extra, "limit": "50"},
                                   call=rec, catalog=catalog, timeout=5.0)
    assert out.status == "empty"
    assert out.message == agent_tools.NONE_OF_YOURS_MATCH


def test_e_paging_and_sorting_are_not_filters(world):
    from app.services.chatbot.agent import tools as agent_tools
    from tests.chatbot.agent._ported_reads_support import Recorder

    catalog = _list_catalog()
    catalog[LIST]["inputSchema"]["properties"].update({k: {"type": "string"} for k in ("page", "sort", "dir")})
    rec = Recorder(result={"data": [], "pagination": {"total": 0}, "empty": True})
    with panel_turn(world.sales):
        out = agent_tools.dispatch(world.db, make_ctx(world.sales), LIST,
                                   {"owner_user_ids": "me", "limit": "100", "page": "1", "sort": "title", "dir": "asc"},
                                   call=rec, catalog=catalog, timeout=5.0)
    assert out.message == agent_tools.NONE_OF_YOURS
