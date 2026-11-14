"""AGENT-CONTEXT-BUDGET slice 2 red tests: the short tool menu and `crm_tools_load` (UAC T1-T11).

UAC: documentation/plans/agent/agent-tool-menu-14nov-acceptance-criteria.md (U1-U8, K1).
Plan: documentation/plans/agent/PLAN-agent-tool-menu-14nov.md, "Design".

A staff turn (panel, WhatsApp linked user) offers only the core set at step 1, plus confirm / cancel when a
change waits, plus (Q1 = (a)) the tools the previous agent turn of the conversation called. Every other tool
the user may use is a line in `crm_tools_load`'s description; loading one (argument `names`) adds its schema
after the core set from the next step on. A contact principal turn and the dealer flow keep today's list.

The provider is scripted (US$0): every assertion is on what it RECEIVED per call, on the tool replies and on
the trace. Postgres only (`blank_session`); every row is seeded here. The catalogue is the MCP catalogue the
backend image carries (`app/services/mcp_catalog_copy.py`), each tool's parameters typed as strings, so the
schema sizes are close to production without reaching the MCP server.

Trace field names this file fixes for U8 (the UAC names the content, not the keys):
- `agent_round.tools_loaded`: the names loaded so far this turn (a list), on every round.
- `agent_context.core_tools` and `agent_context.directory_tools`: the core set and directory sizes (counts).
"""
from __future__ import annotations

import copy
import json
import re
import uuid

import pytest

import app.main  # noqa: F401  register every model and the app's listeners
from app.models.chatbot_agent import AgentAction
from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot import principal as staff_principal
from app.services.company_scope import register_company_scope_listeners
from app.services.llm_provider import ChatResult
from tests._pg_fixture import blank_session
from tests.chatbot.agent._ported_reads_support import PROJECTS_VIEW, SALES_REPORT_SLUG, Recorder
from tests.chatbot.agent._seed import seed_contact, seed_user

LOAD = "crm_tools_load"
CONFIRM = "confirm_action"
CANCEL = "cancel_action"
#: U1: the core set of a staff turn, each only if the user may use it.
CORE = ("plan", "answer", LOAD, "crm_query", "crm_describe", "crm_resolve", "crm_knowledge_search", "user_guides_read")
STOCK = "crm_inventory_stock_balance_list"
COMPLAINTS = "crm_complaints_list"
#: What the MCP stock route answers (a render envelope, as `test_agent_loop.Mcp`).
STOCK_BODY = {"items": [{"qty": 12}], "has_result": True}
#: T2: tools a projects-only user must never see named in the directory (complaints, stock, cost).
NOT_FOR_PROJECTS_ONLY = (
    COMPLAINTS, "crm_complaint_analytics", "crm_complaints_find", "crm_complaint_close", STOCK,
    "crm_procurement_po_last_cost_list",
)


@pytest.fixture(autouse=True)
def _listeners():
    register_company_scope_listeners()
    yield


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


# ------------------------------------------------------------------ the world


def _catalog() -> dict[str, dict]:
    """The MCP catalogue as `tools/list` would return it: name -> {description, inputSchema}."""
    from app.services.mcp_catalog_copy import CATALOG

    out = {}
    for spec in CATALOG:
        params = (*spec.path_params, *spec.query_params, *spec.body_params, "contact_id", "space_id")
        out[spec.name] = {
            "description": spec.description,
            "inputSchema": {"type": "object", "properties": {p: {"type": "string"} for p in dict.fromkeys(params)}},
        }
    return out


def _all_slugs() -> tuple[str, ...]:
    """Every slug a tool of the agent needs: a user holding them may use every staff tool."""
    from app.services.chatbot.agent import tools, writes

    out: list[str] = []
    for definition in [*tools.REGISTRY.values(), *writes.WRITES.values(), *writes.USER_READS.values()]:
        for attr in ("user_permission", "own_permission"):
            value = getattr(definition, attr, None)
            out += [value] if isinstance(value, str) else list(value or ())
    out += [*tools.ARG_PERMISSIONS.values(), *writes.CONTACT_SLUGS, SALES_REPORT_SLUG]
    return tuple(dict.fromkeys(s for s in out if s))


def _universe() -> set[str]:
    """Every tool name the agent knows, permitted or not (to read the directory's lines)."""
    from app.services.chatbot.agent import batch, portal_writes, tools, writes

    return {
        *tools.REGISTRY, *writes.WRITES, *writes.USER_READS, *portal_writes.PORTAL_READS,
        *portal_writes.PORTAL_WRITES, batch.BATCH, tools.HANDOFF, CONFIRM, CANCEL, "plan", "answer",
    }


def _today_names(db, ctx, cat) -> list[str]:
    """Today's step-1 assembly (`loop.py` round-1 list, no change waiting), from the permission helpers the plan
    reuses as is. U6 pins a contact turn to exactly this; for a staff turn it is everything the user may use."""
    from app.services.chatbot.agent import batch, portal_writes, writes
    from app.services.chatbot.agent.access import permitted_tools
    from app.services.chatbot.agent.tools import HANDOFF, KNOWLEDGE, tool_schemas

    offered = permitted_tools(db, ctx)
    names = [s["function"]["name"] for s in tool_schemas(offered, cat)]
    dealer = portal_writes.offered(db, ctx)
    names += [r.name for r in writes.permitted_user_reads(db, ctx)]
    names += [n for n in dealer if n in portal_writes.PORTAL_READS]
    names += [w.name for w in writes.permitted_writes(db, ctx)]
    names += [n for n in dealer if n in portal_writes.PORTAL_WRITES]
    if batch.batch_tool_schema(db, ctx) is not None:
        names.append(batch.BATCH)
    if ctx.principal == "contact" and any(t.name == KNOWLEDGE for t in offered):
        names.append(HANDOFF)
    return [*names, "plan", "answer"]


def _staff_today(db, principal, cat) -> list[str]:
    """Today's step-1 list for a staff turn, built inside the staff principal as the turn itself runs (panel-only
    tools are closed outside it)."""
    from app.services.chatbot.agent.access import build_context

    with staff_principal.acting_as(principal):
        return _today_names(db, build_context(db, principal.key), cat)


# ------------------------------------------------------------------ the scripted model


def _tc(name, args, cid):
    return {"id": cid, "name": name, "arguments": args}


def _round(*calls):
    return ChatResult(
        content="", prompt_tokens=100, completion_tokens=10, total_tokens=110, cached_tokens=0,
        tool_calls=list(calls),
    )


def _answer(text="Done."):
    return _round(_tc("answer", {"text": text, "figures": [], "not_found": [], "not_checked": []}, "ans"))


def _load(*names, cid="load-1"):
    return _round(_tc(LOAD, {"names": list(names)}, cid))


class Prov:
    """Records every main call's tools and tool_choice; answers the dealer-access side call with `dealer`."""

    def __init__(self, script, *, dealer: bool = False):
        self.script = list(script)
        self.dealer = dealer
        self.seen: list[dict] = []

    def chat(self, messages, *, tools=None, reasoning_effort=None, **kw):
        if kw.get("json_schema") is not None:
            body = json.dumps({"dealer_access": self.dealer})
            return ChatResult(content=body, prompt_tokens=1, completion_tokens=1, total_tokens=2, cached_tokens=0,
                              tool_calls=[])
        self.seen.append({"messages": copy.deepcopy(messages), "tools": copy.deepcopy(tools),
                          "tool_choice": kw.get("tool_choice")})
        # A round past the script (a repair or nudge round) just answers: no assertion reads it.
        return self.script.pop(0) if self.script else _answer("Ok.")

    def names(self, step: int) -> list[str]:
        return [t["function"]["name"] for t in self.seen[step]["tools"] or []]

    def schema(self, step: int, name: str) -> dict:
        return next(t for t in self.seen[step]["tools"] if t["function"]["name"] == name)


def _panel(db, principal, script, *, text="how are we doing?", rec=None, dealer=False):
    from app.services.chatbot.agent.loop import run_agent_turn

    prov = Prov(script, dealer=dealer)
    rec = rec if rec is not None else Recorder()
    with staff_principal.acting_as(principal):
        result = run_agent_turn(db, contact_respond_id=principal.key, text=text, provider=prov, mcp_call=rec,
                                catalog=_catalog())
    return result, prov, rec


def _principal(user_id, conversation_id=None):
    return staff_principal.StaffPrincipal(user_id=user_id, conversation_id=conversation_id or str(uuid.uuid4()))


def _all_user(db):
    return seed_user(db, contact_pk=None, slugs=_all_slugs())


def _trace(db, result, kind):
    turn = db.query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).one()
    return [e for e in turn.trace or [] if e.get("kind") == kind]


def _tool_replies(prov, step) -> list[dict]:
    """The tool messages the model received at `step` (the replies to the step before)."""
    return [json.loads(m["content"]) for m in prov.seen[step]["messages"] if m.get("role") == "tool"]


def _directory(schema: dict) -> dict[str, str]:
    """`name: line` pairs of crm_tools_load's description, for names that are agent tools."""
    known = _universe()
    out: dict[str, str] = {}
    for line in str(schema["function"].get("description") or "").splitlines():
        m = re.match(r"^\s*(?:[-*]\s*)?([a-z][a-z0-9_]*):\s*(.+?)\s*$", line)
        if m and m.group(1) in known:
            out[m.group(1)] = m.group(2)
    return out


def _expected_core(today: list[str]) -> set[str]:
    return {n for n in CORE if n in today} | {LOAD}


# ================================================================== T1 (U1)


@pytest.mark.parametrize("channel", ["panel", "whatsapp_linked_user"])
def test_t1_an_all_permissions_staff_turn_offers_only_the_core_set_at_step_one(db, channel):
    from app.services.chatbot.agent.access import build_context
    from app.services.chatbot.agent.loop import run_agent_turn

    if channel == "panel":
        principal = _principal(_all_user(db))
        today = _staff_today(db, principal, _catalog())
        result, prov, _rec = _panel(db, principal, [_answer("Hello.")])
    else:
        contact = seed_contact(db)
        seed_user(db, contact_pk=contact["pk"], slugs=_all_slugs())
        today = _today_names(db, build_context(db, contact["respond_id"]), _catalog())
        prov = Prov([_answer("Hello.")])
        result = run_agent_turn(db, contact_respond_id=contact["respond_id"], text="how are we doing?",
                                provider=prov, mcp_call=Recorder(), catalog=_catalog())
    assert result.status == "answered", (result.status, result.reply_text)
    assert len(today) > 20, today  # the all-permissions user may use far more than the core set
    first = prov.names(0)
    assert len(first) == len(set(first)), first
    assert set(first) == _expected_core(today), sorted(set(first) ^ _expected_core(today))


# ================================================================== T2 (U2)


def test_t2_the_directory_lists_exactly_the_permitted_non_core_tools_one_short_line_each(db):
    principal = _principal(_all_user(db))
    today = _staff_today(db, principal, _catalog())
    _result, prov, _rec = _panel(db, principal, [_answer("Hello.")])
    assert LOAD in prov.names(0), prov.names(0)
    load = prov.schema(0, LOAD)
    lines = _directory(load)
    assert set(lines) == set(today) - set(CORE), sorted(set(lines) ^ (set(today) - set(CORE)))
    assert set(NOT_FOR_PROJECTS_ONLY) <= set(lines)  # the low-permission check below is not vacuous
    too_long = {n: t for n, t in lines.items() if len(t) > 100 or not t}
    assert not too_long, too_long
    props = load["function"]["parameters"]["properties"]
    assert props["names"]["type"] == "array", props


def test_t2_a_projects_only_users_directory_names_no_tool_it_lacks(db):
    principal = _principal(seed_user(db, contact_pk=None, slugs=(PROJECTS_VIEW,)))
    today = _staff_today(db, principal, _catalog())
    _result, prov, _rec = _panel(db, principal, [_answer("Hello.")])
    assert LOAD in prov.names(0), prov.names(0)
    lines = _directory(prov.schema(0, LOAD))
    assert not set(lines) & set(NOT_FOR_PROJECTS_ONLY), sorted(set(lines) & set(NOT_FOR_PROJECTS_ONLY))
    assert set(lines) == set(today) - set(CORE), sorted(set(lines) ^ (set(today) - set(CORE)))
    assert "crm_projects_list" in lines


# ================================================================== T3 (U3, U5)


def test_t3_loading_two_permitted_tools_adds_both_schemas_after_the_core_set_for_the_rest_of_the_turn(db):
    principal = _principal(_all_user(db))
    script = [_load(STOCK, COMPLAINTS), _round(_tc("plan", {"parts": ["stock", "complaints"]}, "p1")), _answer("Ok.")]
    result, prov, rec = _panel(db, principal, script)
    assert result.status == "answered", (result.status, result.reply_text)
    first, second, third = prov.names(0), prov.names(1), prov.names(2)
    assert STOCK not in first and COMPLAINTS not in first, first
    assert second[: len(first)] == first, (first, second)
    assert set(second[len(first):]) == {STOCK, COMPLAINTS}, second
    assert prov.schema(1, STOCK)["function"]["parameters"]["properties"], "the loaded schema is the full schema"
    assert third[: len(second)] == second, (second, third)  # still there one step later
    [reply] = _tool_replies(prov, 1)
    assert reply["status"] == "ok", reply
    blob = json.dumps(reply)
    assert STOCK in blob and COMPLAINTS in blob and "not available" not in blob.lower(), reply
    assert rec.calls == []  # loading runs no tool


# ================================================================== T4 (U3)


def test_t4_loading_a_forbidden_or_unknown_name_answers_not_available_and_adds_nothing(db):
    principal = _principal(seed_user(db, contact_pk=None, slugs=(PROJECTS_VIEW,)))
    result, prov, rec = _panel(db, principal, [_load(COMPLAINTS, "crm_no_such_tool"), _answer("Ok.")])
    assert result.status == "answered", (result.status, result.reply_text)
    assert LOAD in prov.names(0), prov.names(0)
    assert prov.names(1) == prov.names(0), (prov.names(0), prov.names(1))
    [reply] = _tool_replies(prov, 1)
    blob = json.dumps(reply)
    assert blob.lower().count("not available") >= 2, reply
    assert COMPLAINTS in blob and "crm_no_such_tool" in blob, reply
    assert rec.calls == []


def test_t4_a_load_of_one_permitted_and_one_forbidden_name_adds_only_the_permitted_one(db):
    principal = _principal(seed_user(db, contact_pk=None, slugs=(PROJECTS_VIEW,)))
    result, prov, _rec = _panel(db, principal, [_load("crm_projects_list", COMPLAINTS), _answer("Ok.")])
    assert result.status == "answered", (result.status, result.reply_text)
    first, second = prov.names(0), prov.names(1)
    assert "crm_projects_list" not in first, first
    assert second == [*first, "crm_projects_list"], (first, second)
    [reply] = _tool_replies(prov, 1)
    assert "not available" in json.dumps(reply).lower() and COMPLAINTS in json.dumps(reply), reply


# ================================================================== T5 (U4)


def test_t5_a_direct_call_to_a_permitted_unloaded_tool_runs_once_and_adds_the_tool(db):
    principal = _principal(_all_user(db))
    result, prov, rec = _panel(db, principal, [_round(_tc(STOCK, {"page": "1"}, "s1")), _answer("Ok.")],
                               rec=Recorder(result=STOCK_BODY))
    assert result.status == "answered", (result.status, result.reply_text)
    assert [name for name, _args in rec.calls] == [STOCK], rec.calls
    [reply] = _tool_replies(prov, 1)
    assert reply["status"] == "ok" and reply["data"], reply
    assert STOCK in prov.names(1), prov.names(1)
    # The precondition: the tool was not offered at step 1 (it is not core and was not loaded).
    assert STOCK not in prov.names(0), prov.names(0)


# ================================================================== T6 (U4)


def test_t6_a_direct_call_to_a_forbidden_tool_is_refused_as_today(db):
    principal = _principal(seed_user(db, contact_pk=None, slugs=(PROJECTS_VIEW,)))
    result, prov, rec = _panel(db, principal, [_round(_tc(COMPLAINTS, {"page": "1"}, "c1")), _answer("No access.")])
    assert result.status == "answered", (result.status, result.reply_text)
    assert rec.calls == []
    [reply] = _tool_replies(prov, 1)
    assert reply["status"] == "denied", reply
    assert reply["message"].startswith(f"{COMPLAINTS} is outside this user's access"), reply
    assert COMPLAINTS not in prov.names(1), prov.names(1)


# ================================================================== T7 (U6)


def test_t7_a_contact_principal_turn_offers_exactly_todays_list(db):
    from app.services.chatbot.agent.access import build_context
    from app.services.chatbot.agent.loop import run_agent_turn

    contact = seed_contact(db)
    ctx = build_context(db, contact["respond_id"])
    assert ctx.principal == "contact"
    today = _today_names(db, ctx, _catalog())
    prov = Prov([_answer("Hello.")])
    result = run_agent_turn(db, contact_respond_id=contact["respond_id"], text="do you have stock?",
                            provider=prov, mcp_call=Recorder(), catalog=_catalog())
    assert result.status == "answered", (result.status, result.reply_text)
    assert len(today) > 2, today
    assert prov.names(0) == today, (prov.names(0), today)
    assert LOAD not in prov.names(0)


# ================================================================== T8 (U6)


def test_t8_the_dealer_flow_offers_exactly_todays_dealer_list(db):
    from app.services.chatbot.agent.loop import CANCEL_ACTION, CONFIRM_ACTION, _dealer_tools

    principal = _principal(_all_user(db))
    today = _staff_today(db, principal, _catalog())
    expected = [n for n in today if n in {*_dealer_tools(), "answer", CONFIRM_ACTION, CANCEL_ACTION}]
    _result, prov, _rec = _panel(db, principal, [_answer("Ok.")],
                                 text="give 0123456789 dealer access to ZZT", dealer=True)
    assert prov.seen[0]["tool_choice"] == "required"
    assert prov.names(0) == expected, (prov.names(0), expected)
    assert LOAD not in prov.names(0)
    # Review S1: the dealer flow offers no crm_tools_load, so its system prompt does not name it.
    from app.services.chatbot.agent.loop import TOOLS_LOAD_LINE

    system = prov.seen[0]["messages"][0]["content"]
    assert TOOLS_LOAD_LINE not in system and LOAD not in system, system[-400:]


# ================================================================== T9 (U1, Q1 = (a))


def test_t9_the_previous_agent_turns_tools_are_preloaded_on_a_follow_up_and_absent_on_a_new_conversation(db):
    user_id = _all_user(db)
    principal = _principal(user_id)
    first, prov1, _rec = _panel(db, principal, [_round(_tc(STOCK, {"page": "1"}, "s1")), _answer("Read.")],
                                text="stock of ZZT-1?", rec=Recorder(result=STOCK_BODY))
    assert first.status == "answered", (first.status, first.reply_text)
    today = _staff_today(db, principal, _catalog())
    core = _expected_core(today)

    follow, prov2, _rec = _panel(db, principal, [_answer("Same.")], text="and last month?")
    assert follow.status == "answered", (follow.status, follow.reply_text)
    assert STOCK in prov2.names(0), prov2.names(0)
    assert set(prov2.names(0)) == core | {STOCK}, sorted(set(prov2.names(0)) ^ (core | {STOCK}))
    assert prov2.names(0).index(STOCK) > max(prov2.names(0).index(n) for n in core)  # after the core set

    fresh, prov3, _rec = _panel(db, _principal(user_id), [_answer("Hello.")], text="and last month?")
    assert fresh.status == "answered", (fresh.status, fresh.reply_text)
    assert STOCK not in prov3.names(0), prov3.names(0)


def _revoke(db, user_id, slug):
    """Take `slug` away from the user's roles (the permission row itself stays)."""
    from app.models.user import UserPermission, UserRoleAssignment, UserRolePermission

    roles = [r.role_id for r in db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == str(user_id)).all()]
    perm = db.query(UserPermission).filter(UserPermission.slug == slug).one()
    db.query(UserRolePermission).filter(
        UserRolePermission.role_id.in_(roles), UserRolePermission.permission_id == perm.id
    ).delete(synchronize_session=False)
    db.commit()
    from app.services.user_service import invalidate_rbac_cache

    invalidate_rbac_cache(user_id)  # as every RBAC write does


def test_t9b_a_tool_whose_permission_was_revoked_after_the_first_turn_is_neither_preloaded_nor_listed(db):
    """Review S2: the previous turn's tools are preloaded only while the user may still use them."""
    user_id = _all_user(db)
    principal = _principal(user_id)
    first, _prov1, _rec = _panel(db, principal, [_round(_tc(STOCK, {"page": "1"}, "s1")), _answer("Read.")],
                                 text="stock of ZZT-1?", rec=Recorder(result=STOCK_BODY))
    assert first.status == "answered", (first.status, first.reply_text)
    _revoke(db, user_id, "inventory.stock.view")

    follow, prov2, _rec = _panel(db, principal, [_answer("Same.")], text="and last month?")
    assert follow.status == "answered", (follow.status, follow.reply_text)
    assert STOCK not in prov2.names(0), prov2.names(0)
    assert STOCK not in _directory(prov2.schema(0, LOAD)), sorted(_directory(prov2.schema(0, LOAD)))


# ================================================================== T10 (U5)


def _waiting_change(db, principal, user_id) -> AgentAction:
    """A proposed change of this user in this panel thread, so confirm / cancel are offered."""
    from datetime import datetime, timezone

    row = AgentAction(
        id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()), turn_id=str(uuid.uuid4()),
        contact_respond_id=principal.key, user_id=str(user_id), status="proposed",
        steps=[{"tool": "crm_idea_create", "summary": "Create idea ZZT menu", "args": {}, "status": "proposed"}],
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    return row


def test_t10_the_offered_list_never_shrinks_across_steps_except_confirm(db):
    user_id = _all_user(db)
    principal = _principal(user_id)
    _waiting_change(db, principal, user_id)
    query = {"entity": "customer", "aggregates": [{"fn": "count"}]}
    script = [_round(_tc("crm_query", query, "q1")), _load(STOCK, cid="l1"), _answer("Ok.")]
    _result, prov, _rec = _panel(db, principal, script, text="how many customers do we have?")
    steps = [prov.names(i) for i in range(len(prov.seen))]
    assert len(steps) == 3, steps
    assert CONFIRM in steps[0] and CANCEL in steps[0], steps[0]
    for later in steps[1:]:
        assert CONFIRM not in later, later
    for before, after in zip(steps, steps[1:]):
        lost = [n for n in before if n != CONFIRM and n not in after]
        assert not lost, (lost, before, after)
    # The core set, not today's full list, opens the turn; and the loaded tool sits after it.
    assert LOAD in steps[0] and STOCK not in steps[0], steps[0]
    assert STOCK in steps[2] and steps[2].index(STOCK) == len(steps[2]) - 1, steps[2]


# ================================================================== T11 (K1, U8)


def test_t11_step_one_schema_chars_are_under_20000_for_all_permissions_and_the_trace_carries_loaded_names(db):
    principal = _principal(_all_user(db))
    result, prov, _rec = _panel(db, principal, [_load(STOCK, COMPLAINTS), _answer("Ok.")])
    assert result.status == "answered", (result.status, result.reply_text)
    sent = len(json.dumps(prov.seen[0]["tools"], default=str))
    rounds = [e for e in _trace(db, result, "agent_round") if e.get("kind_of_call") == "round"]
    assert len(rounds) == 2, rounds
    assert rounds[0]["tool_schema_chars"] == sent and rounds[0]["tools_offered"] == len(prov.names(0))
    assert rounds[1]["tools_offered"] == len(prov.names(1))
    assert sent < 20_000, f"step-1 tool schemas are {sent} chars ({len(prov.names(0))} tools)"
    assert rounds[0].get("tools_loaded") == [], rounds[0]
    assert sorted(rounds[1].get("tools_loaded") or []) == sorted([STOCK, COMPLAINTS]), rounds[1]
    [context] = _trace(db, result, "agent_context")
    lines = _directory(prov.schema(0, LOAD))
    assert context.get("core_tools") == len(prov.names(0)), context
    assert context.get("directory_tools") == len(lines), context
