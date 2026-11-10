"""AGENT-QUOTE-COMPARE red tests (UAC sections A to E; F is a live run).

A  page ids seed `seen_ids` for a panel turn            (`panel_service._page_ids`, `run_agent_turn(seed_ids=)`)
B  refusals that teach the right call                    (`_check_ids`, RESOLVE_SCHEMA, `crm_resolve`, unknown args)
C  clean ids                                             (padded id forwarded bare, list refused for a single id)
D  never a bare failure after data was read              (`limited` + "What I read:", trace `agent_provider_failed`)
E  `crm_project_quotation_lines`                         (new local panel read)

Postgres only (`blank_session`); every row is seeded in the test. No live LLM: a scripted provider and a recording `call`.
The route half of AC-C3 is `tests/test_project_quotations_padded_id.py`.
"""
from __future__ import annotations

import copy
import json
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

import app.main  # noqa: F401  register every model and the app's listeners
from app.models.chatbot_turn import ChatbotTurn
from app.models.user import SystemSetting
from app.services.chatbot import principal as staff_principal
from app.services.chatbot.agent import tools as agent_tools
from app.services.company_scope import register_company_scope_listeners
from app.services.llm_provider import ChatResult
from tests._pg_fixture import blank_session, unique_code
from tests.chatbot.agent._ported_reads_support import (
    PROJECTS_VIEW,
    PROJECTS_VIEW_OWN,
    UNRELATED,
    Recorder,
    catalog,
    make_ctx,
    panel_ctx,
    panel_turn,
    tool,
)
from tests.chatbot.agent._seed import seed_user

QUOTES = "crm_project_quotations_list"
LINES = "crm_project_quotation_lines"
STOCK = "crm_inventory_stock_balance_list"


@pytest.fixture(autouse=True)
def _listeners():
    register_company_scope_listeners()
    yield


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def _uid() -> str:
    return str(uuid.uuid4())


# ------------------------------------------------------------------ scripted model


def _tc(name, args, cid):
    return {"id": cid, "name": name, "arguments": args}


def _round(*calls):
    return ChatResult(
        content="", prompt_tokens=100, completion_tokens=10, total_tokens=110, cached_tokens=0,
        tool_calls=list(calls),
    )


def _answer(text="Done."):
    return _round(_tc("answer", {"text": text, "figures": [], "not_found": [], "not_checked": []}, "ans"))


class Prov:
    """A callable item gets (messages, tools); an Exception item is raised; anything else is returned."""

    def __init__(self, script):
        self.script = list(script)
        self.seen: list[dict] = []

    def chat(self, messages, *, tools=None, reasoning_effort=None, **kw):
        if kw.get("json_schema") is not None:  # the dealer-access check: never a scripted round
            return ChatResult(content='{"dealer_access": false}', prompt_tokens=1, completion_tokens=1,
                              total_tokens=2, cached_tokens=0, tool_calls=[])
        snap = {"messages": copy.deepcopy(messages), "tools": copy.deepcopy(tools)}
        self.seen.append(snap)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item(snap["messages"], snap["tools"]) if callable(item) else item


def _last_tool(messages) -> dict:
    return json.loads([m for m in messages if m.get("role") == "tool"][-1]["content"])


def _panel_run(db, user_id, script, *, text="compare the two quotations", rec=None, cat=None, company_id=None, **kw):
    from app.services.chatbot.agent.loop import run_agent_turn

    prov = Prov(script)
    principal = staff_principal.StaffPrincipal(
        user_id=user_id, conversation_id=str(uuid.uuid4()), active_company_id=company_id
    )
    rec = rec if rec is not None else Recorder()
    with staff_principal.acting_as(principal):
        result = run_agent_turn(
            db, contact_respond_id=principal.key, text=text, provider=prov, mcp_call=rec,
            catalog=cat or catalog(), **kw,
        )
    return result, prov, rec


def _viewer(db, *extra):
    return seed_user(db, contact_pk=None, slugs=(PROJECTS_VIEW, *extra))


def _turn(db, result):
    return db.query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).one()


# ================================================================== A. page ids


def test_AC_A1_page_ids_reads_the_uuid_in_the_path_from_a_dict_and_a_payload():
    from app.schemas.ai_assistant import PageSnapshotPayload
    from app.services.chatbot.panel_service import _page_ids

    pid = _uid()
    assert _page_ids({"path": f"/project-sales/{pid}"}) == [pid]
    assert _page_ids(PageSnapshotPayload(path=f"/project-sales/{pid.upper()}")) == [pid]


def test_AC_A1_page_ids_is_empty_without_a_snapshot_or_a_uuid():
    from app.services.chatbot.panel_service import _page_ids

    assert _page_ids(None) == []
    assert _page_ids({}) == []
    assert _page_ids({"path": ""}) == []
    assert _page_ids({"path": "/project-sales"}) == []


def test_AC_A1_a_seeded_page_id_is_dispatched_in_round_one(db):
    user_id = _viewer(db)
    pid = _uid()
    seen_tool: dict = {}

    def after(messages, tools):
        seen_tool.update(_last_tool(messages))
        return _answer()

    result, _prov, rec = _panel_run(
        db, user_id, [_round(_tc(QUOTES, {"project_id": pid}, "c1")), after], seed_ids=[pid.upper()]
    )
    assert [c[0] for c in rec.calls] == [QUOTES], (seen_tool, rec.calls)
    assert seen_tool.get("status") == "ok", seen_tool


def test_AC_A2_a_uuid_neither_seeded_nor_in_a_result_is_still_unknown(db):
    user_id = _viewer(db)
    page, other = _uid(), _uid()
    seen_tool: dict = {}

    def after(messages, tools):
        seen_tool.update(_last_tool(messages))
        return _answer()

    _result, _prov, rec = _panel_run(
        db, user_id, [_round(_tc(QUOTES, {"project_id": other}, "c1")), after], seed_ids=[page]
    )
    assert rec.calls == []
    assert seen_tool.get("status") == "invalid" and "Unknown id" in seen_tool.get("message", ""), seen_tool


def test_AC_A3_seeding_grants_nothing_a_view_own_user_who_does_not_own_the_page_project_is_refused(db):
    from app.models.base import company_scope

    world = _seed_world(db)
    user_id = seed_user(db, contact_pk=None, slugs=(PROJECTS_VIEW_OWN,))
    seen_tool: dict = {}

    def after(messages, tools):
        seen_tool.update(_last_tool(messages))
        return _answer()

    with company_scope(db, frozenset({world.company_id})):
        _panel_run(
            db, user_id, [_round(_tc(LINES, {"project_id": world.project_id}, "c1")), after],
            seed_ids=[world.project_id], company_id=world.company_id,
        )
    assert seen_tool.get("status") == "invalid", seen_tool


def test_AC_A1_the_panel_hands_the_page_ids_to_the_agent_as_seed_ids(db, monkeypatch):
    from app.services.chatbot import panel_service

    pid = _uid()
    captured: dict = {}

    def fake_run(db_, **kw):
        captured.update(kw)
        return SimpleNamespace(turn_id=_uid(), reply_text="ok", status="answered")

    monkeypatch.setattr(panel_service.agent_loop, "run_agent_turn", fake_run)
    monkeypatch.setattr(panel_service.agent_loop, "enforce_agent_rate_limit", lambda key: None)
    monkeypatch.setattr(panel_service, "_quoted_bot_replies", lambda db_, cid: ("", ""))
    monkeypatch.setattr(panel_service, "_stamp_route", lambda *a, **k: None)
    monkeypatch.setattr(panel_service, "agent_view", lambda *a, **k: None)
    decision = SimpleNamespace(as_response=lambda: {})
    principal = staff_principal.StaffPrincipal(
        user_id=_uid(), conversation_id=_uid(), page={"title": "Project", "path": f"/project-sales/{pid}"}
    )
    panel_service._run_agent_side(db, principal, "compare", decision)
    assert [s.lower() for s in captured.get("seed_ids") or []] == [pid], captured


# ================================================================== B. refusals


@pytest.mark.parametrize(
    "arg,value,named,not_named",
    [
        ("project_id", None, "crm_projects_find", "crm_resolve"),
        ("complaint_id", None, "crm_complaints_find", None),
        ("product_id", None, "crm_resolve", None),
        ("brand_ids", None, "crm_resolve", None),
    ],
)
def test_AC_B1_an_unknown_id_names_the_find_that_can_supply_it(arg, value, named, not_named):
    unknown = _uid()
    out = agent_tools._check_ids({arg: [unknown] if arg.endswith("_ids") else unknown}, set())
    assert out is not None and out.status == "invalid"
    assert named in out.message, out.message
    if not_named:
        assert not_named not in out.message, out.message


def test_AC_B2_the_resolver_description_points_projects_and_complaints_to_their_finds():
    desc = agent_tools.RESOLVE_SCHEMA["function"]["description"]
    assert "crm_projects_find" in desc and "crm_complaints_find" in desc, desc


@pytest.mark.parametrize("args", [{"term": "PPF2611004"}, {"kind": "project", "text": "PPF2611004"}])
def test_AC_B3_a_wrong_shaped_resolve_call_is_told_the_accepted_shape(db, args):
    user_id = seed_user(db, contact_pk=None, slugs=(PROJECTS_VIEW,))
    ctx = make_ctx(user_id)
    out = agent_tools.dispatch(db, ctx, "crm_resolve", dict(args), call=Recorder(), catalog=catalog(), timeout=5.0)
    assert out.status == "invalid", (out.status, out.message)
    assert "terms" in out.message and "kinds" in out.message, out.message
    for slug in agent_tools.KIND_SLUGS:
        assert slug in out.message, (slug, out.message)


def test_AC_B4_an_unknown_argument_on_a_catalogue_tool_lists_the_accepted_names(db):
    user_id = seed_user(db, contact_pk=None, slugs=("inventory.stock.view",))
    cat = {
        STOCK: {
            "description": "stock",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "contact_id": {"type": "string"}, "space_id": {"type": "string"},
                    "view": {"type": "string"}, "query": {"type": "string"}, "product_code": {"type": "string"},
                },
            },
        }
    }
    ctx = make_ctx(user_id)
    with panel_turn(user_id):
        out = agent_tools.dispatch(db, ctx, STOCK, {"bogus": 1}, call=Recorder(), catalog=cat, timeout=5.0)
    assert out.status == "invalid", (out.status, out.message)
    assert "query" in out.message and "product_code" in out.message, out.message
    for hidden in ("contact_id", "space_id", "view"):
        assert hidden not in out.message, (hidden, out.message)


# ================================================================== C. clean ids


def _quotes_dispatch(db, user_id, args, seen, cat=None):
    rec = Recorder()
    ctx = panel_ctx(db, user_id)
    with panel_turn(user_id):
        out = agent_tools.dispatch(
            db, ctx, QUOTES, args, call=rec, catalog=cat or catalog(), timeout=5.0, seen_ids=seen
        )
    return out, rec


def test_AC_C1_a_padded_id_is_forwarded_as_the_bare_uuid(db):
    user_id = _viewer(db)
    pid = _uid()
    out, rec = _quotes_dispatch(db, user_id, {"project_id": f"  {pid} "}, {pid})
    assert out.status == "ok", (out.status, out.message)
    assert rec.calls[0][1]["project_id"] == pid, rec.calls


@pytest.mark.parametrize("shape", ["list", "json_string"])
def test_AC_C2_a_list_for_a_single_id_argument_is_refused_before_any_call(db, shape):
    user_id = _viewer(db)
    pid = _uid()
    value = [pid] if shape == "list" else json.dumps([pid])
    out, rec = _quotes_dispatch(db, user_id, {"project_id": value}, {pid})
    assert out.status == "invalid", (out.status, out.message)
    assert "one id" in out.message, out.message
    assert rec.calls == []


def test_AC_C2_a_plural_id_argument_still_takes_a_list(db):
    user_id = _viewer(db)
    pid, brand = _uid(), _uid()
    cat = catalog()
    cat[QUOTES]["inputSchema"]["properties"]["brand_ids"] = {"type": "array"}
    out, rec = _quotes_dispatch(db, user_id, {"project_id": pid, "brand_ids": [brand]}, {pid, brand}, cat)
    assert out.status == "ok", (out.status, out.message)
    assert len(rec.calls) == 1


# ================================================================== D. degrade


def _reads_then_fails(db, user_id, failure, *, path):
    """One ok read, then the model fails. `rounds`: the limit is hit and the forced final fails.
    `error`: the next round fails, then the forced final fails."""
    from app.services.chatbot.agent.loop import run_agent_turn  # noqa: F401  (import error is its own red)

    if path == "rounds":
        row = db.query(SystemSetting).first() or SystemSetting()
        db.add(row)
        row.chatbot_agent_max_rounds = 1
        db.flush()
        script = [_round(_tc(QUOTES, {}, "c1")), failure]
    else:
        script = [_round(_tc(QUOTES, {}, "c1")), failure, failure]
    return _panel_run(db, user_id, script, text="SECRET-PROMPT-TEXT compare quotations")


def _timeouts():
    from app.services.chatbot.llm_call import TimedOut

    return [TimedOut("slow"), TimeoutError("slow")]


@pytest.mark.parametrize("path", ["rounds", "error"])
@pytest.mark.parametrize("kind", ["provider", "timeout_llm", "timeout_builtin"])
def test_AC_D1_D2_a_failed_final_call_after_a_read_is_limited_and_says_what_was_read(db, path, kind):
    user_id = _viewer(db)
    failure = {
        "provider": RuntimeError("401 key sk-LEAK123 rejected"),
        "timeout_llm": _timeouts()[0],
        "timeout_builtin": _timeouts()[1],
    }[kind]
    result, _prov, rec = _reads_then_fails(db, user_id, failure, path=path)
    assert rec.calls, "the read never ran"
    assert result.status == "limited", (result.status, result.reply_text)
    reply = result.reply_text
    assert reply.startswith("I could not finish the answer"), reply
    if kind == "provider":
        assert "the model provider returned an error" in reply, reply
    else:
        assert "the model did not respond in time" in reply, reply
    assert "What I read:" in reply, reply
    assert agent_tools.TOOL_LABELS[QUOTES] in reply.split("What I read:", 1)[1], reply
    assert "could not answer: the model provider failed" not in reply
    assert "sk-LEAK123" not in reply


@pytest.mark.parametrize("kind", ["provider", "timeout_llm"])
def test_AC_D4_the_trace_records_the_exception_class_and_no_prompt(db, kind):
    user_id = _viewer(db)
    failure = RuntimeError("boom sk-LEAK123") if kind == "provider" else _timeouts()[0]
    result, _prov, _rec = _reads_then_fails(db, user_id, failure, path="rounds")
    entries = [e for e in _turn(db, result).trace if e.get("kind") == "agent_provider_failed"]
    assert entries, "no agent_provider_failed trace entry"
    assert entries[-1].get("error_class") == type(failure).__name__, entries
    blob = json.dumps(entries)
    assert "SECRET-PROMPT-TEXT" not in blob and "sk-LEAK123" not in blob


def test_AC_D3_a_provider_failure_before_any_tool_result_stays_failed_with_the_fixed_text(db):
    user_id = _viewer(db)
    result, _prov, _rec = _panel_run(db, user_id, [RuntimeError("down"), RuntimeError("down")])
    assert result.status == "failed", (result.status, result.reply_text)
    assert result.reply_text == "The agent could not answer: the model provider failed."


# ================================================================== E. crm_project_quotation_lines


def test_AC_E1_the_tool_is_registered_labelled_panel_only_non_render_and_gated_by_the_read_slugs():
    row = tool(LINES)
    assert row.user_permission == PROJECTS_VIEW
    assert row.own_permission == PROJECTS_VIEW_OWN
    assert row.render is False
    assert LINES in agent_tools.TOOL_LABELS and agent_tools.TOOL_LABELS[LINES]
    assert LINES in agent_tools.PANEL_ONLY_TOOLS
    assert LINES in agent_tools.NON_RENDER_TOOLS
    assert agent_tools.REGISTRY[QUOTES].user_permission == row.user_permission
    assert agent_tools.REGISTRY[QUOTES].own_permission == row.own_permission


def test_AC_E1_a_user_with_neither_slug_is_not_offered_it_and_is_denied(db):
    from app.services.chatbot.agent.access import permitted_tools

    tool(LINES)
    user_id = seed_user(db, contact_pk=None, slugs=(UNRELATED,))
    ctx = panel_ctx(db, user_id)
    rec = Recorder()
    with panel_turn(user_id):
        assert LINES not in [t.name for t in permitted_tools(db, ctx)]
        out = agent_tools.dispatch(db, ctx, LINES, {"project_id": _uid()}, call=rec, catalog=catalog(), timeout=5.0)
    assert out.status == "denied", (out.status, out.message)
    assert rec.calls == []


@pytest.mark.parametrize("slug", [PROJECTS_VIEW, PROJECTS_VIEW_OWN])
def test_AC_E1_either_read_slug_offers_it_on_a_panel_turn(db, slug):
    from app.services.chatbot.agent.access import permitted_tools

    tool(LINES)
    user_id = seed_user(db, contact_pk=None, slugs=(slug,))
    ctx = panel_ctx(db, user_id)
    with panel_turn(user_id):
        assert LINES in [t.name for t in permitted_tools(db, ctx)]


def test_AC_E1_it_is_closed_outside_a_panel_turn(db):
    tool(LINES)
    user_id = _viewer(db)
    out = agent_tools.dispatch(
        db, panel_ctx(db, user_id), LINES, {"project_id": _uid()}, call=Recorder(), catalog=catalog(), timeout=5.0
    )
    assert out.status == "denied", (out.status, out.message)


# ---- seeded world

class World(SimpleNamespace):
    pass


def _seed_world(db) -> World:
    """A project with document A (two scopes: one with two versions and an issued revision B pinning v1, one with
    a single version) and document B (one scope with no lines)."""
    from app.models.base import company_scope
    from app.models.projects import (
        ProjectQuotation,
        ProjectQuotationDocument,
        ProjectQuotationIssue,
        ProjectQuotationIssueScope,
        ProjectQuotationLine,
        ProjectQuotationVersion,
    )
    from app.models.user import User
    from app.services import project_seed_service
    from app.services.project_service import register_project
    from sqlalchemy import text

    company_id = str(db.execute(text("select id from companies where code = 'SRT'")).scalar())
    project_seed_service.run(db, company_id=company_id)
    actor = _uid()
    db.add(User(id=actor, email=f"{actor}@zzt.test", name="ZZT Quoter"))
    db.flush()
    with company_scope(db, frozenset({company_id})):
        project = register_project(
            db, company_id=company_id, actor_user_id=actor, developer_party_id=None,
            title=f"ZZT Compare {unique_code('p')}",
        )
        doc_a_no, doc_b_no = unique_code("PRJQ-A"), unique_code("PRJQ-B")
        doc_a = ProjectQuotationDocument(company_id=company_id, project_id=project.id, document_no=doc_a_no)
        doc_b = ProjectQuotationDocument(company_id=company_id, project_id=project.id, document_no=doc_b_no)
        db.add_all([doc_a, doc_b])
        db.flush()

        def scope(doc, label, order):
            row = ProjectQuotation(
                company_id=company_id, project_id=project.id, document_id=doc.id, scope_label=label,
                sort_order=order,
            )
            db.add(row)
            db.flush()
            return row

        def version(q, no, total):
            row = ProjectQuotationVersion(company_id=company_id, quotation_id=q.id, version_no=no,
                                          total_amount=Decimal(total))
            db.add(row)
            db.flush()
            return row

        def line(v, code, desc, qty, list_price, unit, total, order, rate_only=False):
            db.add(ProjectQuotationLine(is_rate_only=rate_only,
                company_id=company_id, version_id=v.id, product_code_snapshot=code, description_snapshot=desc,
                list_price_snapshot=None if list_price is None else Decimal(list_price), unit_price=Decimal(unit),
                quantity=Decimal(qty), uom="pcs", line_total=Decimal(total), sort_order=order,
            ))

        units = scope(doc_a, "Units", 0)
        v1, v2 = version(units, 1, "590.00"), version(units, 2, "300.00")
        line(v1, "C1", "Basin", "2", "300.00", "270.00", "540.00", 0)
        line(v1, "C2", "Tap", "1", None, "50.00", "50.00", 1)
        line(v2, "C3", "Mixer", "3", "100.00", "100.00", "300.00", 0)
        common = scope(doc_a, "Common", 1)
        c1 = version(common, 1, "40.00")
        line(c1, "C4", "Drain", "4", "10.00", "10.00", "40.00", 0)
        line(c1, "C5", "Alternate drain", "1", "20.00", "20.00", "20.00", 1, rate_only=True)
        empty = scope(doc_b, "Showroom", 0)
        version(empty, 1, "0.00")

        issue = ProjectQuotationIssue(
            company_id=company_id, document_id=doc_a.id, issue_no=1, revision_label="B", issued_by=actor,
            grand_total=Decimal("777.00"),  # deliberately not the 590 + 40 of its pinned scopes
        )
        db.add(issue)
        db.flush()
        db.add_all([
            ProjectQuotationIssueScope(company_id=company_id, issue_id=issue.id, quotation_id=units.id,
                                       version_id=v1.id, scope_total=Decimal("590.00"), sort_order=0),
            ProjectQuotationIssueScope(company_id=company_id, issue_id=issue.id, quotation_id=common.id,
                                       version_id=c1.id, scope_total=Decimal("40.00"), sort_order=1),
        ])
        db.flush()
    return World(company_id=company_id, project_id=str(project.id), actor=actor, doc_a=doc_a_no, doc_b=doc_b_no)


def _lines(db, world, args, *, user_id=None, seen=None, scope_company=None):
    from app.models.base import company_scope

    tool(LINES)
    user_id = user_id or _viewer(db)
    ctx = panel_ctx(db, user_id)
    rec = Recorder()
    with company_scope(db, frozenset({scope_company or world.company_id})), panel_turn(user_id):
        out = agent_tools.dispatch(
            db, ctx, LINES, args, call=rec, catalog=catalog(), timeout=5.0,
            seen_ids={world.project_id} if seen is None else seen,
        )
    assert rec.calls == [], "a local read must not go through the MCP call"
    return out


def _doc(out, ref):
    return next(d for d in out.data["documents"] if d["ref"] == ref)


def test_AC_E2_no_refs_returns_every_document_with_each_scopes_current_version(db):
    world = _seed_world(db)
    out = _lines(db, world, {"project_id": world.project_id})
    assert out.status == "ok", (out.status, out.message)
    assert {d["ref"] for d in out.data["documents"]} == {world.doc_a, world.doc_b}
    assert out.data["not_found"] == []
    a = _doc(out, world.doc_a)
    assert a["document_no"] == world.doc_a and a["revision"] is None
    units = next(s for s in a["scopes"] if s["scope"] == "Units")
    assert units["version"] == 2 and float(units["total"]) == 300.0
    assert len(units["lines"]) == 1
    mixer = units["lines"][0]
    assert mixer["code"] == "C3" and mixer["description"] == "Mixer" and mixer["uom"] == "pcs"
    assert float(mixer["qty"]) == 3 and float(mixer["list_price"]) == 100 and float(mixer["unit_price"]) == 100
    assert float(mixer["discount_pct"]) == 0.0 and float(mixer["line_total"]) == 300
    assert float(a["total"]) == 340.0  # 300 + 40: the document total is the sum of its scopes


def test_AC_E2_a_line_priced_below_list_carries_the_discount_percent_and_no_list_gives_none(db):
    world = _seed_world(db)
    out = _lines(db, world, {"project_id": world.project_id, "refs": [f"{world.doc_a}-B"]})
    units = next(s for s in _doc(out, f"{world.doc_a}-B")["scopes"] if s["scope"] == "Units")
    by_code = {ln["code"]: ln for ln in units["lines"]}
    assert float(by_code["C1"]["discount_pct"]) == 10.0
    assert by_code["C2"]["list_price"] is None and by_code["C2"]["discount_pct"] is None


def test_AC_E3_a_document_ref_narrows_to_that_document(db):
    world = _seed_world(db)
    out = _lines(db, world, {"project_id": world.project_id, "refs": [world.doc_a]})
    assert out.status == "ok", (out.status, out.message)
    assert [d["ref"] for d in out.data["documents"]] == [world.doc_a]
    assert out.data["not_found"] == []


def test_AC_E3_a_revision_ref_returns_the_versions_that_issue_pinned(db):
    world = _seed_world(db)
    ref = f"{world.doc_a}-B"
    out = _lines(db, world, {"project_id": world.project_id, "refs": [ref]})
    assert out.status == "ok", (out.status, out.message)
    doc = _doc(out, ref)
    assert doc["revision"] == "B" and doc["document_no"] == world.doc_a
    units = next(s for s in doc["scopes"] if s["scope"] == "Units")
    assert units["version"] == 1 and float(units["total"]) == 590.0
    assert sorted(ln["code"] for ln in units["lines"]) == ["C1", "C2"]
    common = next(s for s in doc["scopes"] if s["scope"] == "Common")
    assert common["version"] == 1 and float(common["total"]) == 40.0


def test_AC_E3_a_ref_that_matches_nothing_is_listed_not_found_never_an_error(db):
    world = _seed_world(db)
    out = _lines(db, world, {"project_id": world.project_id, "refs": [world.doc_a, "NOPE-0001", f"{world.doc_a}-Z"]})
    assert out.status == "ok", (out.status, out.message)
    assert [d["ref"] for d in out.data["documents"]] == [world.doc_a]
    assert sorted(out.data["not_found"]) == sorted(["NOPE-0001", f"{world.doc_a}-Z"])


def test_AC_E4_a_document_whose_scope_has_no_lines_says_so(db):
    world = _seed_world(db)
    out = _lines(db, world, {"project_id": world.project_id, "refs": [world.doc_b]})
    assert out.status == "ok", (out.status, out.message)
    scope = _doc(out, world.doc_b)["scopes"][0]
    assert scope["scope"] == "Showroom" and scope["lines"] == [] and float(scope["total"]) == 0


def test_AC_E5_an_unknown_project_is_invalid_never_an_error(db):
    world = _seed_world(db)
    ghost = _uid()
    out = _lines(db, world, {"project_id": ghost}, seen={ghost})
    assert out.status == "invalid", (out.status, out.message)


def test_AC_E5_another_companys_project_is_invalid_never_an_error(db):
    from app.models.company import Company

    world = _seed_world(db)
    other = Company(id=_uid(), name="ZZT Other Co", code=unique_code("ZO")[:20])
    db.add(other)
    db.flush()
    out = _lines(db, world, {"project_id": world.project_id}, scope_company=other.id)
    assert out.status == "invalid", (out.status, out.message)


def test_AC_E1_a_view_own_only_user_who_is_not_owner_or_collaborator_is_refused_like_the_route(db):
    world = _seed_world(db)
    user_id = seed_user(db, contact_pk=None, slugs=(PROJECTS_VIEW_OWN,))
    out = _lines(db, world, {"project_id": world.project_id}, user_id=user_id)
    assert out.status == "invalid", (out.status, out.message)
    assert out.data is None


def test_AC_E1_a_view_own_only_user_who_owns_the_project_reads_the_lines(db):
    from app.models.base import company_scope
    from app.models.projects import Project

    world = _seed_world(db)
    user_id = seed_user(db, contact_pk=None, slugs=(PROJECTS_VIEW_OWN,))
    with company_scope(db, frozenset({world.company_id})):
        db.query(Project).filter(Project.id == world.project_id).update({"owner_user_id": user_id})
        db.flush()
    out = _lines(db, world, {"project_id": world.project_id}, user_id=user_id)
    assert out.status == "ok", (out.status, out.message)
    assert {d["ref"] for d in out.data["documents"]} == {world.doc_a, world.doc_b}


def test_AC_E1_a_view_own_only_collaborator_reads_the_lines(db):
    from app.models.base import company_scope
    from app.models.projects import ProjectCollaborator

    world = _seed_world(db)
    user_id = seed_user(db, contact_pk=None, slugs=(PROJECTS_VIEW_OWN,))
    with company_scope(db, frozenset({world.company_id})):
        db.add(ProjectCollaborator(project_id=world.project_id, user_id=user_id))
        db.flush()
    out = _lines(db, world, {"project_id": world.project_id}, user_id=user_id)
    assert out.status == "ok", (out.status, out.message)


def test_module_guard_a_disabled_projects_module_denies_a_non_admin_slug_holder(db, monkeypatch):
    from app.config import settings as app_settings
    from app.models.app_modules import AppModuleCatalog, TenantModule
    from app.modules.runtime.installer import DEFAULT_TENANT_ID

    world = _seed_world(db)
    db.add(AppModuleCatalog(module_key="projects", display_name="Projects"))
    db.add(AppModuleCatalog(module_key="base", display_name="Base"))
    db.flush()
    db.add(TenantModule(tenant_id=DEFAULT_TENANT_ID, module_key="base", enabled=True))
    db.add(TenantModule(tenant_id=DEFAULT_TENANT_ID, module_key="projects", enabled=False))
    db.flush()
    monkeypatch.setattr(app_settings, "module_guard_strict", True, raising=False)
    out = _lines(db, world, {"project_id": world.project_id})
    assert out.status == "denied", (out.status, out.message)


def test_AC_E3_the_revisions_document_total_is_the_issues_grand_total(db):
    world = _seed_world(db)
    out = _lines(db, world, {"project_id": world.project_id, "refs": [f"{world.doc_a}-B"]})
    assert float(_doc(out, f"{world.doc_a}-B")["total"]) == 777.0


def test_AC_E2_a_rate_only_line_is_flagged_and_others_are_not(db):
    world = _seed_world(db)
    out = _lines(db, world, {"project_id": world.project_id, "refs": [world.doc_a]})
    common = next(s for s in _doc(out, world.doc_a)["scopes"] if s["scope"] == "Common")
    by_code = {ln["code"]: ln for ln in common["lines"]}
    assert by_code["C5"]["rate_only"] is True
    assert by_code["C4"]["rate_only"] is False


# ---- the model is offered the tool, and one whole scripted turn uses it


def test_the_model_is_offered_the_tool_on_a_staff_panel_turn_for_a_slug_holder(db):
    user_id = _viewer(db)
    result, prov, _rec = _panel_run(db, user_id, [_answer()])
    offered = {t["function"]["name"]: t["function"] for t in prov.seen[0]["tools"]}
    assert LINES in offered, sorted(offered)
    props = offered[LINES]["parameters"]["properties"]
    assert "project_id" in props and "refs" in props, props
    assert "contact_id" not in props and "space_id" not in props


def test_a_whole_turn_reads_the_quotation_lines_from_the_page_project_and_answers(db):
    from app.models.base import company_scope

    world = _seed_world(db)
    user_id = _viewer(db)
    seen_tool: dict = {}

    def after(messages, tools):
        seen_tool.update(_last_tool(messages))
        return _answer("Two documents compared.")

    with company_scope(db, frozenset({world.company_id})):
        result, _prov, rec = _panel_run(
            db, user_id, [_round(_tc(LINES, {"project_id": world.project_id}, "c1")), after],
            seed_ids=[world.project_id], company_id=world.company_id,
        )
    assert seen_tool.get("status") == "ok", seen_tool
    assert rec.calls == []
    assert result.status == "answered", (result.status, result.reply_text)
    digest = _turn(db, result).response["tool_digest"]
    assert [(d["name"], d["status"]) for d in digest] == [(LINES, "ok")]


# ---- D, wider


def _fail_stage(db, user_id, failures, script_head, *, limit_rounds=False):
    if limit_rounds:
        row = db.query(SystemSetting).first() or SystemSetting()
        db.add(row)
        row.chatbot_agent_max_rounds = 1
        db.flush()
    return _panel_run(db, user_id, [*script_head, *failures], text="SECRET-PROMPT-TEXT compare quotations")


def _entries(db, result):
    return [e for e in _turn(db, result).trace if e.get("kind") == "agent_provider_failed"]


def test_AC_D4_the_trace_entry_is_also_written_when_the_provider_fails_before_any_tool_result(db):
    user_id = _viewer(db)
    boom = RuntimeError("down sk-LEAK123")
    result, _p, _r = _fail_stage(db, user_id, [boom, boom], [])
    assert result.status == "failed"
    entries = _entries(db, result)
    assert entries and entries[-1].get("error_class") == "RuntimeError", entries
    assert "sk-LEAK123" not in json.dumps(entries) and "SECRET-PROMPT-TEXT" not in json.dumps(entries)


def test_AC_D4_the_trace_entry_is_written_for_a_failed_round_too(db):
    user_id = _viewer(db)
    boom = RuntimeError("down")
    result, _p, _r = _fail_stage(db, user_id, [boom, boom], [_round(_tc(QUOTES, {}, "c1"))])
    entries = _entries(db, result)
    assert len(entries) >= 1 and all(e.get("error_class") == "RuntimeError" for e in entries), entries


@pytest.mark.parametrize("path", ["rounds", "error"])
def test_AC_D1_a_timeout_found_through_the_cause_chain_reads_as_did_not_respond_in_time(db, path):
    import httpx

    user_id = _viewer(db)
    wrapped = RuntimeError("provider wrapper")
    wrapped.__cause__ = httpx.ReadTimeout("read timed out")
    failures = [wrapped] if path == "rounds" else [wrapped, wrapped]
    result, _p, _r = _fail_stage(
        db, user_id, failures, [_round(_tc(QUOTES, {}, "c1"))], limit_rounds=path == "rounds"
    )
    assert result.status == "limited", (result.status, result.reply_text)
    assert "the model did not respond in time" in result.reply_text, result.reply_text


@pytest.mark.parametrize("path", ["rounds", "error"])
def test_AC_D3_tools_ran_but_none_returned_ok_then_a_failed_final_call_is_failed(db, path):
    user_id = _viewer(db)
    refused = _round(_tc(QUOTES, {"project_id": _uid()}, "c1"))  # an unknown id: an `invalid` refusal
    boom = RuntimeError("down")
    failures = [boom] if path == "rounds" else [boom, boom]
    result, _p, rec = _fail_stage(db, user_id, failures, [refused], limit_rounds=path == "rounds")
    assert rec.calls == []
    assert result.status == "failed", (result.status, result.reply_text)
    assert "What I read" not in result.reply_text
    assert result.reply_text == "The agent could not answer: the model provider failed."


def test_a_contact_turn_that_read_data_then_lost_the_model_stays_failed_with_no_what_i_read(db):
    from app.services.chatbot.agent.loop import run_agent_turn
    from tests.chatbot.agent._seed import seed_agent_contact

    contact = seed_agent_contact(db)
    cat = {
        STOCK: {
            "description": "stock",
            "inputSchema": {"type": "object", "properties": {
                "contact_id": {"type": "string"}, "space_id": {"type": "string"}, "query": {"type": "string"}}},
        }
    }
    prov = Prov([_round(_tc(STOCK, {"query": "SRTWT7445"}, "c1")), RuntimeError("a"), RuntimeError("b")])
    result = run_agent_turn(
        db, contact_respond_id=contact["respond_id"], text="stock?", provider=prov,
        mcp_call=lambda name, args: {"items": [{"qty": 12}], "has_result": True}, catalog=cat,
    )
    assert result.status == "failed", (result.status, result.reply_text)
    assert "What I read" not in result.reply_text


def test_AC_E2_a_line_priced_above_list_has_no_discount_and_no_negative_value(db):
    from app.models.base import company_scope
    from app.models.projects import ProjectQuotation, ProjectQuotationLine, ProjectQuotationVersion

    world = _seed_world(db)
    with company_scope(db, frozenset({world.company_id})):
        showroom = db.query(ProjectQuotation).filter(
            ProjectQuotation.project_id == world.project_id, ProjectQuotation.scope_label == "Showroom"
        ).one()
        version = db.query(ProjectQuotationVersion).filter(ProjectQuotationVersion.quotation_id == showroom.id).one()
        db.add(ProjectQuotationLine(
            company_id=world.company_id, version_id=version.id, product_code_snapshot="ABOVE1",
            description_snapshot="Priced above list", list_price_snapshot=Decimal("600.00"),
            unit_price=Decimal("1200.00"), quantity=Decimal("1"), uom="pcs", line_total=Decimal("1200.00"),
            sort_order=0,
        ))
        db.flush()
    out = _lines(db, world, {"project_id": world.project_id, "refs": [world.doc_b]})
    assert out.status == "ok", (out.status, out.message)
    line = next(ln for ln in _doc(out, world.doc_b)["scopes"][0]["lines"] if ln["code"] == "ABOVE1")
    assert line["discount_pct"] is None, line
    assert not [k for k, v in line.items() if isinstance(v, (int, float)) and not isinstance(v, bool) and v < 0], line


def _add_showroom_line(db, world, code, list_price, unit, qty="1", total=None):
    from app.models.base import company_scope
    from app.models.projects import ProjectQuotation, ProjectQuotationLine, ProjectQuotationVersion

    with company_scope(db, frozenset({world.company_id})):
        showroom = db.query(ProjectQuotation).filter(
            ProjectQuotation.project_id == world.project_id, ProjectQuotation.scope_label == "Showroom"
        ).one()
        version = db.query(ProjectQuotationVersion).filter(ProjectQuotationVersion.quotation_id == showroom.id).one()
        db.add(ProjectQuotationLine(
            company_id=world.company_id, version_id=version.id, product_code_snapshot=code,
            description_snapshot=code, list_price_snapshot=Decimal(list_price), unit_price=Decimal(unit),
            quantity=Decimal(qty), uom="pcs", line_total=Decimal(total or unit), sort_order=0,
        ))
        db.flush()


def test_AC_E2_above_list_pct_is_positive_above_list_and_none_otherwise(db):
    world = _seed_world(db)
    _add_showroom_line(db, world, "ABOVE1", "600.00", "1200.00")
    _add_showroom_line(db, world, "BELOW1", "600.00", "540.00")
    _add_showroom_line(db, world, "EQUAL1", "600.00", "600.00")
    out = _lines(db, world, {"project_id": world.project_id, "refs": [world.doc_b]})
    by_code = {ln["code"]: ln for ln in _doc(out, world.doc_b)["scopes"][0]["lines"]}
    assert by_code["ABOVE1"].get("above_list_pct") == 100.0, by_code["ABOVE1"]
    assert by_code["ABOVE1"]["discount_pct"] is None
    assert "above_list_pct" in by_code["BELOW1"] and by_code["BELOW1"]["above_list_pct"] is None, by_code["BELOW1"]
    assert "above_list_pct" in by_code["EQUAL1"] and by_code["EQUAL1"]["above_list_pct"] is None, by_code["EQUAL1"]


def test_a_whole_turn_quoting_an_above_list_line_keeps_its_percent_verified(db):
    from app.models.base import company_scope

    world = _seed_world(db)
    _add_showroom_line(db, world, "ABOVE1", "600.00", "1200.00", qty="5", total="6000.00")
    user_id = _viewer(db)
    text = "5 x RM 1,200 (100% above list, list RM 600.00) = RM 6,000.00"
    figures = [
        {"value": "5", "call_id": "c1"}, {"value": "1,200", "call_id": "c1"}, {"value": "100", "call_id": "c1"},
        {"value": "600.00", "call_id": "c1"}, {"value": "6,000.00", "call_id": "c1"},
    ]
    final = _round(_tc("answer", {"text": text, "figures": figures, "not_found": [], "not_checked": []}, "ans"))
    with company_scope(db, frozenset({world.company_id})):
        result, _prov, _rec = _panel_run(
            db, user_id, [_round(_tc(LINES, {"project_id": world.project_id, "refs": [world.doc_b]}, "c1")), final, final, final],
            seed_ids=[world.project_id], company_id=world.company_id,
        )
    assert "100% above list" in result.reply_text, result.reply_text
    assert "not verified" not in result.reply_text, result.reply_text
