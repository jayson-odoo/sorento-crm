"""AGENTIC-P3 review round 1 (PLAN-agentic-p3-writes-30oct.md, "Review round 1: fixes, tester-first").

Red tests for rules R1 to R8 and the reviewers' extra cases. Postgres only (blank schema).

The two-turn tests (R2, R3) are real: they call `run_agent_turn` more than once, and the fake model of
a later turn learns the action id, the contact id and the customer id ONLY from the messages and tool
schemas it is sent (the system prompt, the `confirm_action` enum, the `crm_agent_actions_recent`
result). Nothing is handed to it by the test. What the model saw is captured and asserted after the
turn, because an assertion raised inside the fake provider is swallowed by the loop as a provider failure.

Names the plan fixes: `AgentAction.decided_by_user_id`; the system prompt line
`A change is waiting for the user's decision (action <id>): <lines joined by "; ">`; a step stores
`unlinked_customer_ids`; a console confirm by an operator lacking a step's slug is `rejected` ("You do not have permission for this change."); the audit row has user_id = linked user, real_user_id = operator.
"""
from __future__ import annotations

import copy
import dataclasses
import json
import re
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import update

import app.main  # noqa: F401  register every model and the app's listeners
from app.audit_context import clear_actor
from app.models.access import RespondContactCustomer
from app.models.base import company_scope
from app.models.chatbot_agent import AgentAction
from app.models.company import UserCompany
from app.services.audit_service import register_audit_listeners
from app.services.company_scope import register_company_scope_listeners
from app.services.llm_provider import ChatResult
from app.services.user_service import UserPermissionService
from tests._ask_todo_seed import SORENTO
from tests._ask_todo_seed import customer as seed_customer
from tests._pg_fixture import blank_session
from tests.chatbot.agent._seed import seed_user
from tests.chatbot.agent.test_agent_writes import (  # noqa: F401 - helpers, not tests
    EDIT as ASK_EDIT,
    LIST as LIST_ASKS,
    NOTE,
    UPDATE as UPDATE_ASK,
    VIEW as ASK_VIEW,
    action_row,
    action_rows,
    answer_,
    ask_now,
    make_world as ask_world,
    proposal_script,
    round_of,
    tc,
    tool_names,
)
from tests.chatbot.agent.test_agent_writes_contacts import (  # noqa: F401 - helpers, not tests
    EDIT,
    EDIT_OWN,
    FIND,
    UPDATE as UPDATE_CONTACT,
    dealer,
    entries,
    make_world as contact_world,
    seen_for,
    state,
)
from tests.chatbot.agent.test_agent_writes_opportunity import ctx_of, propose_and_store
from tests.chatbot.test_console_turn_endpoint import _ACTOR, VIEW, client  # noqa: F401 - fixtures

RECENT = "crm_agent_actions_recent"
CONFIRM = "confirm_action"
CANCEL = "cancel_action"
LINE = re.compile(r"A change is waiting for the user's decision \(action ([0-9a-f-]{36}), (\d+) change\(s\)\)\.")
REFERENCE = "Waiting change, for reference only:"
VIEW_ALL = "sales.customer_asks.view_all"


@pytest.fixture(autouse=True)
def _listeners():
    register_company_scope_listeners()
    register_audit_listeners()
    yield
    clear_actor()


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


# ------------------------------------------------------------------ scripted model that sees its inputs


class Prov:
    """A scripted model. A callable item receives (messages, tools) of this call and returns the result."""

    def __init__(self, script):
        self.script = list(script)
        self.seen: list[dict] = []

    def chat(self, messages, *, tools=None, reasoning_effort=None, **kw):
        snap = {"messages": copy.deepcopy(messages), "tools": copy.deepcopy(tools)}
        self.seen.append(snap)
        item = self.script.pop(0)
        return item(snap["messages"], snap["tools"]) if callable(item) else item


def _no_mcp(name, args):
    raise AssertionError(f"these tests never reach the MCP server (called {name})")


def go(db, w, script, text_="hello", operator=None):
    from app.services.chatbot.agent.loop import run_agent_turn

    prov = Prov(script)
    result = run_agent_turn(
        db, contact_respond_id=w.respond_id, text=text_, provider=prov, mcp_call=_no_mcp, catalog={},
        operator_user_id=operator,
    )
    return result, prov


def enum_of(tools, name):
    for t in tools or []:
        if t["function"]["name"] == name:
            return t["function"]["parameters"]["properties"]["action_id"].get("enum")
    return None


def decide_from_view(captured: dict, name: str = CONFIRM):
    """Confirm (or cancel) using only what the model is shown: the id in the system prompt line."""

    def item(messages, tools):
        m = LINE.search(messages[0]["content"])
        captured["line"] = m.group(0) if m else None
        captured["reference"] = next(
            (x["content"] for x in messages if x["role"] != "system" and REFERENCE in str(x.get("content"))), None
        )
        captured["enum"] = enum_of(tools, name)
        if m is None:
            return answer_("Nothing is waiting.")
        return round_of(tc(name, {"action_id": m.group(1)}, "d1"))

    return item


def last_tool_data(messages):
    for m in reversed(messages):
        if m.get("role") == "tool":
            return json.loads(m["content"]).get("data")
    return None


def dicts(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from dicts(v)
    elif isinstance(node, list):
        for v in node:
            yield from dicts(v)


def chat_confirm(db, w, action_id):
    from app.services.chatbot.agent import actions

    return actions.confirm(db, w.respond_id, str(action_id), via="chat", turn_id=str(uuid.uuid4()))


# ------------------------------------------------------------------ R2: chat confirm across turns


def test_r2_a_later_turn_confirms_using_only_the_id_in_its_prompt_and_schema(db):
    w = ask_world(db)
    first, first_prov = go(db, w, proposal_script(w.asks))
    row = action_row(db, first.pending_action["id"])
    assert not LINE.search(first_prov.seen[0]["messages"][0]["content"])  # nothing waiting on turn 1
    captured: dict = {}

    second, _ = go(db, w, [decide_from_view(captured), answer_("Done, the ask is updated.")], text_="yes go ahead")

    assert captured["line"] is not None, "the system prompt has no line naming the waiting change"
    assert str(row.id) in captured["line"] and "1 change(s)" in captured["line"]
    assert row.steps[0]["summary"] not in captured["line"]
    assert captured["reference"] and row.steps[0]["summary"] in captured["reference"]
    assert captured["enum"] == [str(row.id)], "confirm_action does not restrict action_id to the pending id"
    after = ask_now(db, w.asks[0].id)
    assert after.state == "done" and after.note == NOTE
    stored = action_row(db, row.id)
    assert stored.status == "executed" and stored.via == "chat"
    assert str(stored.confirm_turn_id) == second.turn_id
    assert str(stored.decided_by_user_id) == w.user_id


def test_r2_the_cancel_schema_is_restricted_to_the_pending_id_too(db):
    w = ask_world(db)
    first, _ = go(db, w, proposal_script(w.asks))
    captured: dict = {}

    go(db, w, [decide_from_view(captured, CANCEL), answer_("Cancelled it.")], text_="no, leave it")

    assert captured["enum"] == [first.pending_action["id"]]
    assert action_row(db, first.pending_action["id"]).status == "cancelled"
    assert ask_now(db, w.asks[0].id).state == "open"


def test_r2_confirming_the_previous_proposal_in_a_turn_that_also_proposes_is_allowed(db):
    w = ask_world(db, n_asks=2)
    first, _ = go(db, w, proposal_script([w.asks[0]]))
    old = action_row(db, first.pending_action["id"])
    captured: dict = {}
    # AGENT-CONFIRM-GATE: the confirm comes first, in the turn's first round; then the new proposal.
    script = [
        decide_from_view(captured),
        round_of(tc(LIST_ASKS, {}, "l1")),
        round_of(tc(UPDATE_ASK, {"ask_id": str(w.asks[1].id), "state": "done", "note": NOTE}, "u1")),
        answer_("Done, and I prepared the next one."),
    ]

    second, _ = go(db, w, script, text_="yes, and also the other ask")

    assert captured["enum"] == [str(old.id)]
    assert action_row(db, old.id).status == "executed"
    assert ask_now(db, w.asks[0].id).state == "done"
    assert second.pending_action is not None and second.pending_action["id"] != str(old.id)
    fresh = action_row(db, second.pending_action["id"])
    assert fresh.status == "proposed" and fresh.steps[0]["args"]["ask_id"] == str(w.asks[1].id)
    assert ask_now(db, w.asks[1].id).state == "open"


# ------------------------------------------------------------------ R3 and R4: undo in a later turn


def test_r3_a_resign_is_undone_two_turns_later_from_the_recent_actions_result_alone(db):
    from app.services.chatbot.agent import actions

    w = contact_world(db)
    row = dealer(db, w, types=("dealer", "end_user"), customers=(w.mine,))
    seen_by_model: dict = {}

    def resign(messages, tools):
        found = entries(last_tool_data(messages))
        if not found or found[0].get("status") != "found":
            return answer_("I could not find that contact.")
        seen_by_model["contact_id"] = found[0]["contact_id"]
        seen_by_model["customer_id"] = found[0]["accounts"][0]["customer_id"]
        return round_of(tc(UPDATE_CONTACT, {
            "contact_id": seen_by_model["contact_id"], "chatbot_allowed": False,
            "unlink_customer_ids": [seen_by_model["customer_id"]],
        }, "u1"))

    one, _ = go(
        db, w,
        [round_of(tc(FIND, {"phones": ["+" + row.phone_number]}, "f1")), resign, answer_("I have prepared the resign.")],
        text_="resign this dealer",
    )
    assert one.pending_action is not None
    go(db, w, [decide_from_view({}), answer_("Done, the contact is resigned.")], text_="yes")
    assert state(db, row.id) == {"types": ["dealer", "end_user"], "ai": False, "links": []}

    recovered: dict = {}

    def undo(messages, tools):
        steps = [
            d for d in dicts(last_tool_data(messages))
            if d.get("tool") == UPDATE_CONTACT and d.get("status") == "done"
        ]
        recovered["steps"] = steps
        if not steps:
            return answer_("I cannot see what was done.")
        args = steps[0]["args"]
        recovered["args"] = args
        return round_of(tc(UPDATE_CONTACT, {
            "contact_id": args["contact_id"], "chatbot_allowed": True,
            "link_customer_ids": list(args["unlink_customer_ids"]),
        }, "u2"))

    three, _ = go(
        db, w, [round_of(tc(RECENT, {}, "r1")), undo, answer_("I have prepared the undo.")], text_="undo that"
    )

    assert recovered.get("steps"), "crm_agent_actions_recent did not show the executed step"
    step = recovered["steps"][0]
    assert {"tool", "args", "result_id", "before", "after", "status"} <= set(step)
    assert step["result_id"] == row.id
    assert three.pending_action is not None, f"the undo was not proposed: {three.reply_text!r}"
    outcome = chat_confirm(db, w, three.pending_action["id"])
    assert outcome.status == "executed"
    assert state(db, row.id) == {"types": ["dealer", "end_user"], "ai": True, "links": [w.mine.id]}
    assert str(action_row(db, three.pending_action["id"]).decided_by_user_id) == w.user_id
    assert isinstance(actions.ACTION_TTL_MINUTES, int)


def test_r3_recent_actions_shows_only_this_users_actions_and_adds_their_ids_to_the_turn(db):
    from app.services.chatbot.agent import writes

    w = ask_world(db)
    first, _ = go(db, w, proposal_script(w.asks))
    chat_confirm(db, w, first.pending_action["id"])
    foreign = AgentAction(
        id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()), turn_id=str(uuid.uuid4()),
        contact_respond_id=w.respond_id, user_id=str(uuid.uuid4()), status="executed",
        steps=[{"tool": UPDATE_ASK, "summary": "FOREIGN-MARKER", "status": "done", "args": {}, "result_id": str(uuid.uuid4())}],
        created_at=datetime.now(timezone.utc),
    )
    db.add(foreign)
    db.commit()
    seen: set[str] = set()

    out = writes.run_user_read(db, ctx_of(db, w), RECENT, {}, seen)

    assert out.status == "ok"
    dump = json.dumps(out.data, default=str)
    assert "FOREIGN-MARKER" not in dump and foreign.id not in dump
    mine = [d for d in dicts(out.data) if d.get("tool") == UPDATE_ASK and d.get("status") == "done"]
    assert mine and {"tool", "args", "result_id", "before", "after", "status"} <= set(mine[0])
    assert mine[0]["result_id"] == str(w.asks[0].id)
    assert str(w.asks[0].id).lower() in seen


def test_r4_a_resign_step_records_the_links_it_actually_removed(db):
    w = contact_world(db)
    row = dealer(db, w, customers=(w.mine,))
    _, action = propose_and_store(
        db, w,
        [(UPDATE_CONTACT, {"contact_id": row.id, "chatbot_allowed": False, "unlink_customer_ids": [w.mine.id]})],
        seen_for(row, w.mine),
    )

    chat_confirm(db, w, action.id)

    assert action_row(db, action.id).steps[0]["unlinked_customer_ids"] == [w.mine.id]


def _propose_contact(db, w, args, *seen):
    from app.services.chatbot.agent import writes

    return writes.propose_step(
        db, ctx_of(db, w), UPDATE_CONTACT, args, seen_ids={s.lower() for s in seen}
    )


def test_r4_a_relink_is_bound_to_the_user_who_did_the_unlink(db):
    """Binding only: B owns the customer and the contact is out of B's scope, so the only thing that
    can refuse B is that A, not B, did the unlink. A may undo it."""
    broad = contact_world(db, slugs=(EDIT,))
    other = contact_world(db, slugs=(EDIT_OWN,))
    row = dealer(db, other, customers=(other.mine,))
    _, action = propose_and_store(
        db, broad,
        [(UPDATE_CONTACT, {"contact_id": row.id, "chatbot_allowed": False, "unlink_customer_ids": [other.mine.id]})],
        seen_for(row, other.mine),
    )
    assert chat_confirm(db, broad, action.id).status == "executed"
    args = {"contact_id": row.id, "chatbot_allowed": True, "link_customer_ids": [other.mine.id]}

    refused, step = _propose_contact(db, other, args, row.id, other.mine.id)
    undo, _ = _propose_contact(db, broad, args, row.id, other.mine.id)

    assert refused.status in ("denied", "invalid") and step is None
    assert undo.status == "proposed"


def test_r4_a_relink_is_refused_once_someone_else_has_relinked_and_unlinked_again(db):
    from tests.chatbot.agent.test_agent_writes_contacts import resign_and_confirm

    owner = contact_world(db, slugs=(EDIT_OWN,))
    row = dealer(db, owner, customers=(owner.mine,))
    resign_and_confirm(db, owner, row)
    args = {"contact_id": row.id, "chatbot_allowed": True, "link_customer_ids": [owner.mine.id]}
    control, _ = _propose_contact(db, owner, args, row.id, owner.mine.id)
    assert control.status == "proposed"  # nobody else has touched the link yet
    other = contact_world(db, slugs=(EDIT,))
    for change in ({"link_customer_ids": [owner.mine.id]}, {"unlink_customer_ids": [owner.mine.id]}):
        _, step_action = propose_and_store(
            db, other, [(UPDATE_CONTACT, {"contact_id": row.id, **change})], seen_for(row, owner.mine)
        )
        assert chat_confirm(db, other, step_action.id).status == "executed"

    refused, step = _propose_contact(db, owner, args, row.id, owner.mine.id)

    assert refused.status in ("denied", "invalid") and step is None


# ------------------------------------------------------------------ claim race


def test_a_row_claimed_by_another_session_between_the_recheck_and_the_claim_writes_nothing(session_factory, monkeypatch):
    from app.services.chatbot.agent import actions, writes

    mine = session_factory()
    w = ask_world(mine)
    ctx = ctx_of(mine, w)
    res, step = writes.propose_step(mine, ctx, UPDATE_ASK, {"ask_id": str(w.asks[0].id), "state": "done", "note": NOTE},
                                    seen_ids={str(w.asks[0].id).lower()})
    assert res.status == "proposed"
    row = actions.store_proposal(mine, ctx, conversation_id=str(uuid.uuid4()), turn_id=str(uuid.uuid4()), steps=[step])
    original = writes.WRITES[UPDATE_ASK]
    ran = {"n": 0}

    def counting(db_, user, args):
        ran["n"] += 1
        return original.execute(db_, user, args)

    monkeypatch.setitem(writes.WRITES, UPDATE_ASK, dataclasses.replace(original, execute=counting))
    real_recheck = actions._recheck

    def racing(db_, ctx_, step_):
        problem = real_recheck(db_, ctx_, step_)
        if problem is None:
            rival = session_factory()
            rival.execute(update(AgentAction).where(AgentAction.id == str(row.id)).values(status="executing"))
            rival.commit()
        return problem

    monkeypatch.setattr(actions, "_recheck", racing)

    with pytest.raises(actions.ActionRefused) as exc:
        actions.confirm(mine, w.respond_id, str(row.id), via="chat", turn_id=str(uuid.uuid4()))

    assert exc.value.reason == "not_proposed"
    assert ran["n"] == 0
    assert ask_now(mine, w.asks[0].id).state == "open"
    assert action_row(mine, row.id).status == "executing"


# ------------------------------------------------------------------ R1: who may write from the console


def operator_with(db, *slugs):
    """A console operator who is NOT the contact's linked user."""
    uid = seed_user(db, contact_pk=None, slugs=slugs)
    db.add(UserCompany(user_id=uid, company_id=SORENTO))  # the operator's own company scope, as a real staff user has
    db.commit()
    return uid


def test_r1_write_tools_are_offered_to_an_operator_only_when_they_hold_the_slugs(db):
    w = ask_world(db)
    stranger = operator_with(db)  # holds nothing
    holder = operator_with(db, ASK_VIEW, ASK_EDIT)
    first, _ = go(db, w, proposal_script(w.asks))  # a change is now waiting, so confirm / cancel exist

    _, as_stranger = go(db, w, [answer_("Hi.")], operator=stranger)
    _, as_holder = go(db, w, [answer_("Hi.")], operator=holder)
    _, as_linked = go(db, w, [answer_("Hi.")], operator=w.user_id)
    _, as_chat = go(db, w, [answer_("Hi.")], operator=None)

    assert not ({UPDATE_ASK, CONFIRM, CANCEL} & tool_names(as_stranger))
    for offered in (as_holder, as_linked, as_chat):
        assert {UPDATE_ASK, CONFIRM, CANCEL} <= tool_names(offered)
    assert first.pending_action is not None


def test_r1_a_write_called_in_a_turn_of_an_operator_without_the_slug_is_refused(db):
    w = ask_world(db)
    stranger = operator_with(db)

    result, _ = go(db, w, proposal_script(w.asks), operator=stranger)

    assert [c["status"] for c in result.tool_calls if c["name"] == UPDATE_ASK] in (["denied"], ["invalid"])
    assert action_rows(db, w.respond_id) == []
    assert result.pending_action is None
    assert ask_now(db, w.asks[0].id).state == "open"


def test_r1_an_operator_with_the_slug_proposes_in_a_turn_and_the_action_belongs_to_the_linked_user(db):
    # Both people hold view_all, so the all-agents list (their intersection) shows the ask to the model.
    w = ask_world(db, slugs=(ASK_VIEW, ASK_EDIT, VIEW_ALL))
    holder = operator_with(db, ASK_VIEW, ASK_EDIT, VIEW_ALL)
    script = [
        round_of(tc(LIST_ASKS, {"all_agents": True}, "l1")),
        round_of(tc(UPDATE_ASK, {"ask_id": str(w.asks[0].id), "state": "done", "note": NOTE}, "u1")),
        answer_("I have prepared the changes."),
    ]

    result, _ = go(db, w, script, operator=holder)

    assert result.pending_action is not None
    row = action_row(db, result.pending_action["id"])
    assert str(row.user_id) == w.user_id
    assert ask_now(db, w.asks[0].id).state == "open"


@pytest.fixture()
def console(client, monkeypatch):
    """The route harness with the console permission granted to whoever calls and real RBAC for the rest."""
    real = UserPermissionService.check_user_has_permission
    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission",
        lambda self, uid, slug: True if slug == VIEW else real(self, uid, slug),
    )
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    return client


def pending_ask_action(session_factory):
    from app.services.chatbot.agent import actions, writes

    db = session_factory()
    w = ask_world(db)
    ctx = ctx_of(db, w)
    ask_id = str(w.asks[0].id)
    res, step = writes.propose_step(db, ctx, UPDATE_ASK, {"ask_id": ask_id, "state": "done", "note": NOTE}, seen_ids={ask_id.lower()})
    assert res.status == "proposed"
    row = actions.store_proposal(db, ctx, conversation_id=str(uuid.uuid4()), turn_id=str(uuid.uuid4()), steps=[step])
    return db, w, row


URL = "/api/v1/system/chatbot/agent/actions/{}/{}"


def test_r1_a_console_confirm_by_an_operator_without_the_slug_is_rejected_and_writes_nothing(console, session_factory):
    db, w, row = pending_ask_action(session_factory)
    stranger = operator_with(db)
    _ACTOR["id"] = stranger

    resp = console.post(URL.format(row.id, "confirm"), json={"contact_respond_id": w.respond_id})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "rejected"
    assert "You do not have permission for this change." in (body["steps"][0]["error"] or "")
    assert ask_now(db, w.asks[0].id).state == "open"
    assert action_row(db, row.id).status == "rejected"


def test_r1_an_operator_with_the_slug_confirms_and_the_audit_names_both_people(console, session_factory):
    from app.models.audit import AuditLog

    db, w, row = pending_ask_action(session_factory)
    holder = operator_with(db, ASK_VIEW, ASK_EDIT, VIEW_ALL)  # reaches the ask the linked user's agent owns
    _ACTOR["id"] = holder

    resp = console.post(URL.format(row.id, "confirm"), json={"contact_respond_id": w.respond_id})

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "executed"
    assert ask_now(db, w.asks[0].id).state == "done"
    stored = action_row(db, row.id)
    assert stored.via == "console" and str(stored.decided_by_user_id) == holder
    audits = [
        a for a in db.query(AuditLog).filter(AuditLog.entity_id == str(w.asks[0].id), AuditLog.action == "UPDATE")
        if a.auth_method == "agent"
    ]
    assert audits, "no audit row with auth_method agent"
    last = audits[-1]
    assert str(last.user_id) == w.user_id  # whose permissions and scope ran
    assert str(last.real_user_id) == holder  # who actually acted
    assert str(last.contact_id) == w.contact["pk"]


def test_r1_the_linked_user_confirming_from_the_console_is_recorded_as_the_decider(console, session_factory):
    db, w, row = pending_ask_action(session_factory)
    _ACTOR["id"] = w.user_id

    resp = console.post(URL.format(row.id, "confirm"), json={"contact_respond_id": w.respond_id})

    assert resp.status_code == 200, resp.text
    stored = action_row(db, row.id)
    assert str(stored.decided_by_user_id) == w.user_id and stored.status == "executed"


def test_r1_an_operator_with_the_slug_cancels_and_is_recorded_as_the_decider(console, session_factory):
    db, w, row = pending_ask_action(session_factory)
    holder = operator_with(db, ASK_VIEW, ASK_EDIT)
    _ACTOR["id"] = holder

    resp = console.post(URL.format(row.id, "cancel"), json={"contact_respond_id": w.respond_id})

    assert resp.status_code == 200, resp.text
    stored = action_row(db, row.id)
    assert stored.status == "cancelled" and str(stored.decided_by_user_id) == holder
    assert ask_now(db, w.asks[0].id).state == "open"


def test_r3_the_pending_proposal_on_the_conversation_read_is_filtered_by_user(console, session_factory):
    from app.services.chatbot.agent import actions

    db = session_factory()
    w = ask_world(db)
    ctx = ctx_of(db, w)
    foreign = actions.store_proposal(
        db, dataclasses.replace(ctx, user_id=str(uuid.uuid4())), conversation_id=str(uuid.uuid4()),
        turn_id=str(uuid.uuid4()),
        steps=[{"tool": UPDATE_ASK, "args": {}, "before": {}, "summary": "FOREIGN-MARKER"}],
    )
    assert foreign.user_id != w.user_id
    url = "/api/v1/system/chatbot/agent/conversation"

    hidden = console.get(url, params={"contact_respond_id": w.respond_id})
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["pending_action"] is None

    mine = actions.store_proposal(
        db, ctx, conversation_id=str(uuid.uuid4()), turn_id=str(uuid.uuid4()),
        steps=[{"tool": UPDATE_ASK, "args": {}, "before": {}, "summary": "MINE-MARKER"}],
    )
    shown = console.get(url, params={"contact_respond_id": w.respond_id}).json()["pending_action"]
    assert shown is not None and shown["id"] == str(mine.id)


# ------------------------------------------------------------------ R5: edit_own links only for the undo


def test_r5_an_edit_own_holder_may_not_link_a_customer_to_an_in_scope_contact(db):
    w = contact_world(db, slugs=(EDIT_OWN,))
    row = dealer(db, w, customers=(w.mine,))

    role, _ = _propose_contact(db, w, {"contact_id": row.id, "role": "owner"}, row.id)
    link, step = _propose_contact(db, w, {"contact_id": row.id, "link_customer_ids": [w.mine2.id]}, row.id, w.mine2.id)

    assert role.status == "proposed"
    assert link.status in ("denied", "invalid") and step is None


def test_r5_an_edit_holder_keeps_the_right_to_link(db):
    w = contact_world(db, slugs=(EDIT,))
    row = dealer(db, w, customers=(w.mine,))

    link, step = _propose_contact(db, w, {"contact_id": row.id, "link_customer_ids": [w.mine2.id]}, row.id, w.mine2.id)

    assert link.status == "proposed" and step is not None


# ------------------------------------------------------------------ R6: company scope, nothing removed


def test_r6_an_unlink_that_removes_nothing_fails_the_step(db):
    from app.services.chatbot.agent import actions

    w = contact_world(db)
    row = dealer(db, w, customers=(w.mine,), ai=True)
    args = {"contact_id": row.id, "chatbot_allowed": False, "unlink_customer_ids": [w.mine2.id]}
    res, step = _propose_contact(db, w, args, row.id, w.mine2.id)
    if step is None:  # refusing at proposal is as good, as long as it says why
        assert "was not linked" in res.message
        return
    _, action = propose_and_store(db, w, [(UPDATE_CONTACT, args)], seen_for(row, w.mine2))

    outcome = chat_confirm(db, w, action.id)

    assert outcome.status == "partial" and outcome.steps[0]["status"] == "failed"
    assert f"{w.mine2.customer_code} was not linked" in (outcome.steps[0]["error"] or "")
    assert state(db, row.id)["ai"] is True  # the whole step rolled back
    assert isinstance(actions.MAX_STEPS, int)


def test_r6_a_customer_of_a_company_the_user_has_no_grant_for_is_not_usable(db):
    w = contact_world(db, slugs=(EDIT,))
    foreign_customer = seed_customer(db, "ZZT Mocha Dealer", w.me, company_id=w.mch)
    row_id = dealer(db, w, customers=(w.mine,)).id
    db.add(RespondContactCustomer(id=str(uuid.uuid4()), contact_id=row_id,
                                  customer_id=foreign_customer.id, company_id=w.mch))
    db.commit()

    control, _ = _propose_contact(db, w, {"contact_id": row_id, "unlink_customer_ids": [w.mine.id]}, row_id, w.mine.id)
    refused, step = _propose_contact(
        db, w, {"contact_id": row_id, "unlink_customer_ids": [foreign_customer.id]}, row_id, foreign_customer.id
    )

    assert control.status == "proposed"
    assert refused.status in ("denied", "invalid") and step is None


def test_r6_a_contact_linked_only_to_a_customer_outside_the_users_companies_is_not_theirs(db):
    from app.services.chatbot.agent import writes

    w = contact_world(db, slugs=(EDIT_OWN,))
    inside = dealer(db, w, customers=(w.mine,))
    foreign_customer = seed_customer(db, "ZZT Mocha Dealer", w.me, company_id=w.mch)
    outside = dealer(db, w)
    db.add(RespondContactCustomer(id=str(uuid.uuid4()), contact_id=outside.id, customer_id=foreign_customer.id, company_id=w.mch))
    db.commit()
    seen: set[str] = set()

    out = writes.run_user_read(db, ctx_of(db, w), FIND, {"phones": ["+" + inside.phone_number, "+" + outside.phone_number]}, seen)

    assert [e["status"] for e in entries(out.data)] == ["found", "not_yours"]


# ------------------------------------------------------------------ R7: summaries cannot be forged


def _ask_summary(db, w, **args):
    from app.services.chatbot.agent import writes

    ask_id = str(w.asks[0].id)
    res, step = writes.propose_step(
        db, ctx_of(db, w), UPDATE_ASK, {"ask_id": ask_id, **args}, seen_ids={ask_id.lower()}
    )
    assert res.status == "proposed", res.message
    return step["summary"]


def test_r7_a_contact_name_cannot_forge_a_second_proposal_line(db):
    w = contact_world(db)
    row = dealer(db, w, customers=(w.mine,), name="ZZT Dealer\n2. AI replies off -> on")

    res, step = _propose_contact(db, w, {"contact_id": row.id, "role": "owner"}, row.id)

    assert res.status == "proposed"
    summary = step["summary"]
    assert len(summary.splitlines()) == 1 and "\n" not in summary and "\r" not in summary
    assert "ZZT Dealer 2. AI replies off -> on" in summary


def test_r7_a_long_note_shows_its_first_200_characters_and_its_length(db):
    w = ask_world(db)
    note = "ab" * 150

    summary = _ask_summary(db, w, state="done", note=note)

    assert note[:200] in summary and note not in summary
    assert "(300 characters)" in summary


def test_r7_a_note_of_exactly_200_characters_is_shown_in_full(db):
    w = ask_world(db)
    note = "xy" * 100

    summary = _ask_summary(db, w, note=note)

    assert note in summary and "characters)" not in summary


def test_r7_the_note_keeps_its_case_and_collapses_whitespace(db):
    w = ask_world(db)

    summary = _ask_summary(db, w, state="done", note="Called The Customer\nthen\tWaited")

    assert "Called The Customer then Waited" in summary
    assert "\n" not in summary and "\t" not in summary
    assert summary == summary.strip()


# ------------------------------------------------------------------ R8: role per company


def test_r8_owner_is_not_nothing_to_change_while_a_company_still_lacks_its_owner_type(db):
    from app.services.chatbot.agent import actions  # noqa: F401

    w = contact_world(db)
    partial = dealer(db, w, types=("dealer", "cabana_dealer", "end_user"), companies=(SORENTO, w.mch), customers=(w.mine,))
    complete = dealer(
        db, w, types=("dealer", "cabana_dealer", "mocha_dealer", "end_user"), companies=(SORENTO, w.mch),
        customers=(w.mine,),
    )

    done, _ = _propose_contact(db, w, {"contact_id": complete.id, "role": "owner"}, complete.id)
    res, step = _propose_contact(db, w, {"contact_id": partial.id, "role": "owner"}, partial.id)

    assert done.status == "invalid" and "Nothing to change" in done.message
    assert res.status == "proposed" and step is not None
    _, action = propose_and_store(db, w, [(UPDATE_CONTACT, {"contact_id": partial.id, "role": "owner"})], seen_for(partial))
    assert chat_confirm(db, w, action.id).status == "executed"
    assert state(db, partial.id)["types"] == ["cabana_dealer", "dealer", "end_user", "mocha_dealer"]
