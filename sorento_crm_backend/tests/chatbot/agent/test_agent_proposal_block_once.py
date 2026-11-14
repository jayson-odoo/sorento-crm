"""WA-COMPLAINT-INTAKE round 13: the agent writes the whole reply on a proposal turn.

Owner hand test (agent mode, Chat console): after the model proposed to log an issue (`crm_idea_create`, type
issue), the reply showed "I will make these changes when you confirm: ... Reply yes to go ahead, or tell me what to
change." twice: the loop appended `proposal_block(lines)` to a model text that already held a copy.

Owner ruling 14 Nov: the reply is written fully by the agent; the system appends no confirm block to the reply text
(the structured proposal and `pending` stay as they are).

(A') On a normal proposal turn (not dealer flow, not a table) `reply_text` is the model's final text, stripped. It
     holds neither fixed block line unless the model wrote it; what the model wrote is kept verbatim (no dedupe).
     The proposal is still stored (`proposed`) and returned as `pending`.
(B') The "proposed" tool result tells the model to ask the user to confirm in its own words.
(C)  Controls, unchanged for now (open question to crew): the dealer-flow card and a batch table reply.

Postgres only (blank schema); every test seeds its own chain. Names and phones are invented (public repo).
"""
from __future__ import annotations

import json

import pytest

import app.main  # noqa: F401  register every model and the app's listeners
from app.audit_context import clear_actor
from app.services.audit_service import register_audit_listeners
from app.services.company_scope import register_company_scope_listeners
from tests._pg_fixture import blank_session
from tests.chatbot.agent.test_agent_writes import answer_, round_of, run_turn, tc
from tests.chatbot.agent.test_agent_writes_ideas import CREATE, FIELDS, make_world, ss  # noqa: F401  (ss by name)
from tests.chatbot.agent.test_agent_writes_round1 import go

HEAD = "I will make these changes when you confirm:"
TAIL = "Reply yes to go ahead, or tell me what to change."
LEAD = "I have noted the problem with the stock list for you."
ISSUE = {**FIELDS, "type": "issue"}


@pytest.fixture(autouse=True)
def _listeners():
    register_company_scope_listeners()
    register_audit_listeners()
    yield
    clear_actor()


@pytest.fixture(autouse=True)
def _fresh_token_cache():
    from app.services import ideation_gateway_service

    ideation_gateway_service.clear_token_cache()
    yield
    ideation_gateway_service.clear_token_cache()


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def block(lines):
    from app.services.chatbot.agent import loop

    return loop.proposal_block(lines)


def _create_result(messages) -> dict:
    """The tool reply to the scripted create call (id c1), as the model reads it."""
    for m in messages:
        if m.get("role") == "tool" and m.get("tool_call_id") == "c1":
            return json.loads(m["content"])
    raise AssertionError("the model was never shown the create's tool result")


def _summary(messages) -> str:
    body = _create_result(messages)
    assert body.get("status") == "proposed", body
    return body["data"]["summary"]


def issue_turn(db, ss, final_text):
    """One turn: the model proposes an issue in round 1, then answers with `final_text(summary)`."""
    w = make_world(db)

    def answer(messages, tools):
        return answer_(final_text(_summary(messages)))

    result, prov = go(
        db, w, [round_of(tc(CREATE, dict(ISSUE), "c1")), answer], text_="the stock list will not scroll on my phone"
    )
    assert result.pending_action is not None, result.reply_text
    return result, prov


# ------------------------------------------------------------------ (A') the reply is the model's own text


def _assert_still_proposed(db, result):
    from tests.chatbot.agent.test_agent_writes import action_row

    assert result.pending_action is not None, result.reply_text
    assert result.pending_action["lines"], result.pending_action
    row = action_row(db, result.pending_action["id"])
    assert row is not None and row.status == "proposed", row


def test_A_the_reply_is_the_models_text_with_no_system_block(db, ss):
    result, _ = issue_turn(db, ss, lambda s: LEAD)
    reply = result.reply_text
    assert HEAD not in reply, reply
    assert TAIL not in reply, reply
    assert reply == LEAD, reply
    _assert_still_proposed(db, result)


def test_A_a_reply_of_several_sentences_is_kept_whole_and_stripped(db, ss):
    own = f"{LEAD}\n\nShall I log it? Say yes and I will."
    result, _ = issue_turn(db, ss, lambda s: f"\n  {own}  \n")
    reply = result.reply_text
    assert reply == own, repr(reply)
    assert HEAD not in reply and TAIL not in reply, reply
    _assert_still_proposed(db, result)


def test_A_a_confirm_question_the_model_wrote_itself_is_kept_verbatim(db, ss):
    """No dedupe and no removal: the model's text is the reply, even when it holds the old block wording."""
    written = {}

    def text_(s):
        written["text"] = f"{LEAD}\n\n{block([s])}"
        return written["text"]

    result, _ = issue_turn(db, ss, text_)
    reply = result.reply_text
    assert reply == written["text"], reply
    assert reply.count(HEAD) == 1, reply
    assert reply.count(TAIL) == 1, reply
    _assert_still_proposed(db, result)


# ------------------------------------------------------------------ (B') the model is told to ask in its own words


def test_B_the_proposed_tool_result_tells_the_model_to_ask_in_its_own_words(db, ss):
    _, prov = issue_turn(db, ss, lambda s: LEAD)
    body = _create_result(prov.seen[1]["messages"])
    message = (body.get("message") or "").lower()
    assert "ask the user to confirm" in message, body
    assert "in your own words" in message, body


# ------------------------------------------------------------------ (C) controls, unchanged for now


def test_C_a_dealer_flow_proposal_is_the_card_alone(db):
    from tests.chatbot.agent.test_dealer_access_agent import UPDATE, ai_on, dealer
    from tests.chatbot.agent.test_dealer_access_agent import make_world as dealer_world

    w = dealer_world(db)
    person = ai_on(db, dealer(db, w, customers=(w.cust_a,)))
    script = [
        round_of(tc("crm_contacts_find", {"phones": [person.phone_number]}, "f1")),
        answer_("Tell me the role and the company."),
        round_of(tc(UPDATE, {"contact_id": person.id, "unlink_customer_ids": [str(w.cust_a.id)]}, "u1")),
        answer_("ok"),
    ]
    result, _ = run_turn(db, w, script, text_=f"Update {person.phone_number} to no access", dealer_access=True)
    assert result.pending_action is not None, result.reply_text
    assert result.reply_text == block(result.pending_action["lines"]), result.reply_text


def test_C_a_batch_table_reply_is_unchanged(db):
    from tests.chatbot.agent.test_agent_bulk_grant import BATCH, dealer
    from tests.chatbot.agent.test_agent_bulk_grant import make_world as grant_world

    w = grant_world(db)
    person = dealer(db, w, name="ZZT Turn Old")
    rows = [{"phone": person.phone_number, "name": "ZZT Turn New", "row": 1}]
    script = [round_of(tc(BATCH, {"write": "crm_contact_edit", "rows": rows}, "b1")), answer_(LEAD)]
    result, _ = run_turn(db, w, script, text_="update these contacts")
    reply = result.reply_text
    assert result.pending_action is not None, reply
    assert reply.startswith("Rows from your table: 1 ready to confirm."), reply
    assert reply.count(HEAD) == 1, reply
    assert reply.rstrip().endswith(TAIL), reply
    assert LEAD not in reply, reply
