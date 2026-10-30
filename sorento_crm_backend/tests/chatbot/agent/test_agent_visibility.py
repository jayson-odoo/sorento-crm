"""AGENTIC-P3 slice 6 (PLAN-agentic-p3-writes-30oct.md, "Slice 6: visibility and chat formatting"), red first.

V1 changes in words, stored. V2 kept across reloads. V3 steps in plain words. V4 the audit view.
V5 WhatsApp formatting. Postgres only; every test seeds its own chain, and every test that needs the
feature carries a control so it cannot pass because something is missing.

Assumptions (the plan names fields, not every label or path):
- A stored step gains `changes: [{record, field, before, after}]`; `ActionOutcome.steps[]` and the confirm /
  cancel responses carry the same key. Field labels: ask `State` (or `Status`) and `Note`; opportunity
  `Stage` (or `Status`) and `Customer`; contact `Role` and `AI replies`, links under a label containing "link".
  Values: `Open` / `Done`, stage labels, customer codes, role words `Employee` / `Business owner`, `On` / `Off`.
- `GET agent/conversation` turns carry `actions: [{id, status, decided_at, decided_by_name, steps}]`.
- A tool call in `memory.steps_for_turn(...)["tool_calls"]` carries `detail`.
- The audit description is `Agent change for <phone as stored> by <operator name>`.
- The WhatsApp normaliser is `app.services.chatbot.agent.formatting.to_whatsapp(text: str) -> str`
  (the plan gives no import path; this is an assumption).
"""
from __future__ import annotations

import dataclasses
import json
import re
import uuid

import pytest

import app.main  # noqa: F401  register every model and the app's listeners
from app.audit_context import clear_actor
from app.models.audit import AuditLog
from app.models.base import company_scope
from app.models.chatbot_agent import AgentAction
from app.models.chatbot_turn import ChatbotTurn
from app.models.stock_ask import StockAsk
from app.models.user import User
from app.services.audit_service import register_audit_listeners
from app.services.company_scope import register_company_scope_listeners
from tests._ask_todo_seed import customer as seed_customer
from tests._pg_fixture import blank_session, unique_code
from tests.chatbot.agent.test_agent_writes import (  # noqa: F401 - helpers, not tests
    LIST as LIST_ASKS,
    NOTE,
    UPDATE as UPDATE_ASK,
    action_row,
    answer_,
    make_world as ask_world,
    proposal_script,
    round_of,
    tc,
)
from tests.chatbot.agent.test_agent_writes_contacts import (  # noqa: F401 - helpers, not tests
    EDIT,
    UPDATE as UPDATE_CONTACT,
    dealer,
    make_world as contact_world,
    seen_for,
)
from tests.chatbot.agent.test_agent_writes_opportunity import (  # noqa: F401 - helpers, not tests
    UPDATE as UPDATE_OPP,
    make_opp,
    make_world as opp_world,
    stage,
)
from tests.chatbot.agent.test_agent_writes_opportunity import propose_and_store
from tests.chatbot.agent.test_agent_writes_round1 import (  # noqa: F401 - helpers, fixtures
    _ACTOR,
    URL,
    chat_confirm,
    client,
    console,
    go,
)
from tests.chatbot.agent.test_agent_writes_round2 import console_confirm, make_operator, store

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
AUDIT_EVENT = "contact.access_agent"
CONVERSATION = "/api/v1/system/chatbot/agent/conversation"


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


def by_field(changes, *names):
    return next((c for c in changes if str(c["field"]).lower() in names), None)


def dump(value) -> str:
    return json.dumps(value, default=str)


def stored_and_outcome_changes(db, w, action, outcome):
    stored = action_row(db, action.id).steps
    return [s.get("changes") or [] for s in stored], [s.get("changes") or [] for s in outcome.steps]


# ------------------------------------------------------------------ V1: changes in words, stored


def test_v1_an_ask_step_stores_state_and_note_in_words_and_lists_only_what_changed(db):
    w = ask_world(db)
    ask = w.asks[0]
    with company_scope(db, None):
        db.query(StockAsk).filter(StockAsk.id == ask.id).one().note = NOTE  # the note already reads this
        db.commit()
    action = _store_ask(db, w, ask, state="done", note=NOTE)
    other = ask_world(db)  # the second ask has no note yet: the note really changes
    action2 = _store_ask(db, other, other.asks[0], state="done", note=NOTE)

    same = chat_confirm(db, w, action.id)
    changed = chat_confirm(db, other, action2.id)

    for outcome, act in ((same, action), (changed, action2)):
        stored, shown = stored_and_outcome_changes(db, w, act, outcome)
        assert stored == shown and stored[0], "the stored and the returned changes must match and not be empty"
    unchanged_note = same.steps[0]["changes"]
    state = by_field(unchanged_note, "state", "status")
    assert state and (state["before"], state["after"]) == ("Open", "Done")
    assert state["record"] and ask.product_code in state["record"] and w.customer.customer_name in state["record"]
    assert by_field(unchanged_note, "note") is None  # the note did not change: not listed
    both = changed.steps[0]["changes"]
    assert by_field(both, "note")["after"] == NOTE  # control: a real note change is listed
    assert not UUID_RE.search(dump([unchanged_note, both]))


def _store_ask(db, w, ask, **args):
    return store(db, w, None, [(UPDATE_ASK, {"ask_id": str(ask.id), **args})], {str(ask.id)})


def test_v1_an_opportunity_step_stores_the_stage_by_label_and_the_customer_by_code(db):
    w = opp_world(db)
    opp = make_opp(db, w)
    other = seed_customer(db, unique_code("Other"), w.me)
    db.commit()
    new, qualified = stage(db, "new"), stage(db, "qualified")
    _, action = propose_and_store(
        db, w, [(UPDATE_OPP, {"opportunity_id": opp.id, "status_id": qualified.id, "customer_id": other.id})],
        {opp.id, qualified.id, other.id},
    )

    outcome = chat_confirm(db, w, action.id)

    assert outcome.status == "executed"
    changes = outcome.steps[0]["changes"]
    stage_change = by_field(changes, "stage", "status")
    assert (stage_change["before"], stage_change["after"]) == (new.label, qualified.label)
    customer = by_field(changes, "customer")
    assert (customer["before"], customer["after"]) == (w.mine.customer_code, other.customer_code)
    assert all(c["record"] == opp.title for c in changes)
    assert by_field(changes, "title") is None
    assert not UUID_RE.search(dump(changes))
    assert action_row(db, action.id).steps[0]["changes"] == changes


def test_v1_a_contact_step_stores_role_ai_replies_and_links_in_words(db):
    w = contact_world(db)
    row = dealer(db, w, customers=(w.mine,), ai=True)
    _, action = propose_and_store(
        db, w,
        [(UPDATE_CONTACT, {"contact_id": row.id, "role": "owner", "chatbot_allowed": False, "unlink_customer_ids": [w.mine.id]})],
        seen_for(row, w.mine),
    )

    outcome = chat_confirm(db, w, action.id)

    assert outcome.status == "executed"
    changes = outcome.steps[0]["changes"]
    role = by_field(changes, "role")
    assert role["before"] == "Employee" and "Business owner" in role["after"]
    ai = by_field(changes, "ai replies")
    assert (ai["before"], ai["after"]) == ("On", "Off")
    links = [c for c in changes if "link" in str(c["field"]).lower()]
    assert links and w.mine.customer_code in dump(links)
    assert all(row.phone_number in c["record"] and row.name in c["record"] for c in changes)
    assert not UUID_RE.search(dump(changes))
    assert action_row(db, action.id).steps[0]["changes"] == changes


def test_v1_failed_skipped_and_rejected_steps_store_no_changes(db, monkeypatch):
    from app.services.chatbot.agent import writes
    from app.services.error_handler import AppException

    w = ask_world(db, n_asks=3)
    action = store(
        db, w, None, [(UPDATE_ASK, {"ask_id": str(a.id), "state": "done"}) for a in w.asks], {str(a.id) for a in w.asks}
    )
    original = writes.WRITES[UPDATE_ASK]
    calls = {"n": 0}

    def flaky(db_, user, args):
        calls["n"] += 1
        if calls["n"] == 2:
            raise AppException(status_code=400, message="boom from the route", code="BOOM")
        return original.execute(db_, user, args)

    monkeypatch.setitem(writes.WRITES, UPDATE_ASK, dataclasses.replace(original, execute=flaky))

    outcome = chat_confirm(db, w, action.id)

    assert [s["status"] for s in outcome.steps] == ["done", "failed", "skipped"]
    assert outcome.steps[0]["changes"], "the executed step lists its change"
    assert not outcome.steps[1].get("changes") and not outcome.steps[2].get("changes")
    stored = action_row(db, action.id).steps
    assert stored[0]["changes"] and not stored[1].get("changes") and not stored[2].get("changes")


def test_v1_a_rejected_action_stores_no_changes(db):
    w = ask_world(db)
    ask = w.asks[0]
    control = ask_world(db)
    ok = _store_ask(db, control, control.asks[0], state="done")
    action = _store_ask(db, w, ask, state="done", note=NOTE)
    with company_scope(db, None):
        db.query(StockAsk).filter(StockAsk.id == ask.id).one().note = "edited on screen"
        db.commit()

    done = chat_confirm(db, control, ok.id)
    outcome = chat_confirm(db, w, action.id)

    assert done.steps[0]["changes"]  # control: the same flow without the screen edit lists its change
    assert outcome.status == "rejected"
    assert all(not s.get("changes") for s in outcome.steps)


# ------------------------------------------------------------------ V2: kept across reloads


def test_v2_a_fresh_read_after_confirm_shows_the_action_with_its_changes_and_not_another_users(console, session_factory):
    db = session_factory()
    w = ask_world(db)
    first, _ = go(db, w, proposal_script(w.asks))
    pending_id = first.pending_action["id"]
    proposed_view = console.get(CONVERSATION, params={"contact_respond_id": w.respond_id}).json()
    assert [a["status"] for a in proposed_view["turns"][0]["actions"]] == ["proposed"]  # control: shown while waiting

    chat_confirm(db, w, pending_id)
    foreign = AgentAction(
        id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()), turn_id=first.turn_id,
        contact_respond_id=w.respond_id, user_id=str(uuid.uuid4()), status="executed",
        steps=[{"tool": UPDATE_ASK, "summary": "FOREIGN-MARKER", "status": "done", "changes": []}],
    )
    db.add(foreign)
    db.commit()

    body = console.get(CONVERSATION, params={"contact_respond_id": w.respond_id}).json()

    actions = body["turns"][0]["actions"]
    assert [a["id"] for a in actions] == [pending_id]
    one = actions[0]
    assert one["status"] == "executed" and one["decided_at"] and one["decided_by_name"] == "ZZT Agent User"
    step = one["steps"][0]
    assert {"summary", "status", "error", "changes"} <= set(step) and step["status"] == "done"
    assert by_field(step["changes"], "state", "status")["after"] == "Done"
    assert "FOREIGN-MARKER" not in dump(body) and not UUID_RE.search(dump(step["changes"]))


def test_v2_the_confirm_response_carries_the_changes(console, session_factory):
    from tests.chatbot.agent.test_agent_writes_round1 import pending_ask_action

    db, w, row = pending_ask_action(session_factory)
    _ACTOR["id"] = w.user_id

    resp = console.post(URL.format(row.id, "confirm"), json={"contact_respond_id": w.respond_id})

    assert resp.status_code == 200, resp.text
    changes = resp.json()["steps"][0]["changes"]
    assert by_field(changes, "state", "status")["after"] == "Done"


# ------------------------------------------------------------------ V3: steps in plain words


def tool_details(db, result) -> dict[str, list[str]]:
    from app.services.chatbot.agent import memory

    calls = memory.steps_for_turn(db, result.turn_id)["tool_calls"]
    out: dict[str, list[str]] = {}
    for call in calls:
        out.setdefault(call["name"], []).append(call.get("detail"))
    return out


def test_v3_a_list_a_refused_call_and_a_proposal_each_carry_a_plain_detail_without_uuids(db):
    w = ask_world(db, n_asks=2)
    script = [
        round_of(tc(LIST_ASKS, {}, "l1")),
        round_of(
            tc(UPDATE_ASK, {"ask_id": str(w.asks[0].id), "state": "done"}, "u1"),
            tc(UPDATE_ASK, {"ask_id": str(uuid.uuid4()), "state": "done"}, "u2"),
        ),
        answer_("I have prepared one change."),
    ]

    result, _ = go(db, w, script)

    details = tool_details(db, result)
    listed = details[LIST_ASKS][0]
    proposed, refused = details[UPDATE_ASK]
    assert listed and "2 rows" in listed and LIST_ASKS not in listed
    assert proposed and "proposed" in proposed
    assert w.asks[0].product_code in proposed or w.customer.customer_name in proposed  # ids shown as names
    assert refused and "refused" in refused
    assert not UUID_RE.search(dump(details))


def test_v3_an_empty_read_says_nothing_found(db):
    w = ask_world(db, n_asks=0)

    result, _ = go(db, w, [round_of(tc(LIST_ASKS, {}, "l1")), answer_("There is nothing to do.")])

    assert "nothing found" in tool_details(db, result)[LIST_ASKS][0]


# ------------------------------------------------------------------ V4: the audit view


def contact_audit(db, contact_id):
    rows = db.query(AuditLog).filter(AuditLog.event == AUDIT_EVENT, AuditLog.entity_id == contact_id).all()
    assert rows, "the contact change left no audit row"
    return rows[-1]


def test_v4_the_audit_row_holds_readable_old_and_new_values(db):
    w = contact_world(db)
    row = dealer(db, w, customers=(w.mine,), ai=True)
    _, action = propose_and_store(
        db, w,
        [(UPDATE_CONTACT, {"contact_id": row.id, "role": "owner", "chatbot_allowed": False, "unlink_customer_ids": [w.mine.id]})],
        seen_for(row, w.mine),
    )
    chat_confirm(db, w, action.id)

    audit = contact_audit(db, row.id)

    old, new = dump(audit.old_values), dump(audit.new_values)
    assert "Employee" in old and "Business owner" in new
    assert "On" in old and "Off" in new
    assert w.mine.customer_code in old + new
    assert not UUID_RE.search(old + new.replace(row.id, ""))
    assert str(audit.user_id) == w.user_id and audit.auth_method == "agent"


def test_v4_the_audit_description_names_the_contact_and_the_operator(db):
    w = contact_world(db, slugs=(EDIT,))
    operator = make_operator(db, (EDIT,))
    db.query(User).filter(User.id == operator.user_id).one().name = "Fake Operator Name"
    db.commit()
    row = dealer(db, w, customers=(w.mine,))
    action = store(db, w, operator.user_id, [(UPDATE_CONTACT, {"contact_id": row.id, "role": "owner"})], {row.id})

    outcome = console_confirm(db, w, action, operator.user_id)

    assert outcome.status == "executed"
    audit = contact_audit(db, row.id)
    assert audit.description == f"Agent change for {row.phone_number} by Fake Operator Name"
    assert str(audit.real_user_id) == operator.user_id and str(audit.user_id) == w.user_id


# ------------------------------------------------------------------ V5: WhatsApp formatting


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("a **bold** word", "a *bold* word"),
        ("an __italic__ word", "an _italic_ word"),
        ("# Heading", "*Heading*"),
        ("### Deep heading", "*Deep heading*"),
        ("* first\n* second", "- first\n- second"),
        ("1. one\n2. two", "1. one\n2. two"),
        ("line one\n\nline two", "line one\n\nline two"),
        ("already *bold* and _italic_", "already *bold* and _italic_"),
        ("- kept\n- bullets", "- kept\n- bullets"),
        ("# Stock\n**SRT** on hand\n* item", "*Stock*\n*SRT* on hand\n- item"),
    ],
)
def test_v5_the_normaliser_turns_markdown_into_whatsapp_markup(raw, expected):
    from app.services.chatbot.agent.formatting import to_whatsapp

    assert to_whatsapp(raw) == expected


def test_v5_a_stored_reply_is_normalised(db):
    w = ask_world(db)
    script = [answer_("Here is the **summary**\n# Heading\n* first item\n* second item")]

    result, _ = go(db, w, script)

    expected = "Here is the *summary*\n*Heading*\n- first item\n- second item"
    assert result.reply_text == expected
    row = db.query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).one()
    assert row.response["reply_text"] == expected


def test_v5_the_prompt_fallback_asks_for_whatsapp_formatting(db):
    from app.services import ai_prompt_registry

    text = ai_prompt_registry.get_prompt(db, "chatbot_agent").text

    assert "WhatsApp" in text and "*bold*" in text and "- " in text
