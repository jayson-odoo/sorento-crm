"""PR 4 round 3 (red): G1 computed floats rounded, G4 ticket proposal note.

Plan: documentation/plans/chatbot/PLAN-agentic-unify-tools-1nov.md, "Round 3 after crew's re-pass, 3 Nov".
G1: in an MCP read result a float with more than 5 decimal places is computed noise, rounded to 2 places
before the model and the figure check see it; stored precision (5 places or fewer) is untouched.
G4: the ticket's proposed result carries a note (data), the shared `message` stays.
"""
from __future__ import annotations

import uuid

import pytest

import app.main  # noqa: F401  register every model and the app's listeners
from app.audit_context import clear_actor
from app.services.audit_service import register_audit_listeners
from app.services.chatbot.agent import loop
from app.services.chatbot.agent.loop import verify_answer
from app.services.company_scope import register_company_scope_listeners
from tests._pg_fixture import blank_session
from tests.chatbot.agent import _ported_reads_support as support
from tests.chatbot.agent._ported_reads_support import AC1, Recorder, panel_ctx, panel_turn, slugs_for
from tests.chatbot.agent._seed import seed_user
from tests.chatbot.agent.test_ported_writes import (
    CLOSE,
    TICKET,
    TICKET_SLUG,
    CLOSE_SLUG,
    args_for,
    ctx_of,
    make_world,
    panel,
)

NAME = "crm_projects_list"
SLUG = {n: s for n, s, _own in AC1}[NAME]
PROPOSED_MESSAGE = "Proposed, not done. The user must confirm in a later message."
SLA = {"average_response_time": 28.0395454545455, "average_resolution_time": 439.234541726966,
       "escalation_rate": 12.52408477842, "total_trackings": 81}


@pytest.fixture(autouse=True)
def _listeners():
    register_company_scope_listeners()
    register_audit_listeners()
    yield
    clear_actor()


@pytest.fixture(scope="module")
def db():
    with blank_session() as session:
        yield session


def _read(db, body):
    ctx = panel_ctx(db, seed_user(db, contact_pk=None, slugs=slugs_for(NAME, SLUG)))
    with panel_turn(ctx.user_id):
        out = support.dispatch(db, ctx, NAME, None, rec=Recorder(body))
    assert out.status == "ok", (out.status, out.message)
    return out


# ------------------------------------------------------------------ G1


def _sent(out) -> dict:
    """What the model is sent: the ToolResult's JSON, parsed."""
    import json

    return json.loads(out.to_json("c1"))["data"]


def test_G1_computed_floats_are_rounded_to_two_places_in_what_the_model_is_sent(db):
    out = _read(db, dict(SLA))
    data = _sent(out)
    assert data["average_response_time"] == 28.04
    assert data["average_resolution_time"] == 439.23
    assert data["escalation_rate"] == 12.52
    assert data["total_trackings"] == 81
    # the ledger keeps the raw float
    assert out.data["average_response_time"] == 28.0395454545455


def test_G1_nested_floats_in_rows_and_dicts_are_rounded_in_what_the_model_is_sent(db):
    body = {"data": [{"ref": "A", "avg": 28.0395454545455}, {"ref": "B", "avg": 439.234541726966}],
            "summary": {"rate": 12.52408477842, "nested": {"x": 0.123456789}}}
    data = _sent(_read(db, body))
    assert [r["avg"] for r in data["data"]] == [28.04, 439.23]
    assert data["summary"]["rate"] == 12.52
    assert data["summary"]["nested"]["x"] == 0.12


def test_G1_stored_precision_is_untouched(db):
    body = {"data": [{"ref": "A"}], "a": 12.3456, "b": 0.00125, "c": 1234.5, "d": 3, "e": "28.0395454545455"}
    data = _sent(_read(db, body))
    assert data["a"] == 12.3456 and data["b"] == 0.00125 and data["c"] == 1234.5
    assert data["d"] == 3 and data["e"] == "28.0395454545455"


@pytest.mark.parametrize("text", ["28.04 hours", "28.0 hours", "28 hours", "12.5%"])
def test_G1_the_figure_check_backs_roundings_of_the_raw_ledger_float(db, text):
    out = _read(db, dict(SLA))
    ledger = {"c1": {"name": NAME, "args": {}, "status": "ok", "data": out.data}}
    assert verify_answer({"text": f"It took {text}."}, ledger, "show")[0] == []


def test_G1_a_turn_answering_with_roundings_of_the_raw_float_keeps_its_reply():
    """End to end through the loop: the model is sent 28.04, the ledger holds 28.0395..., the reply keeps 28.0 and 12.5%."""
    from tests.chatbot.agent import test_agent_round7 as r7

    reply = "Average response 28.0 hours, escalation 12.5%."
    env = {"items": [{"avg": 28.0395454545455, "rate": 12.52408477842}], "has_result": True}
    with blank_session() as session:
        contact = r7.seed_agent_contact(session, slugs=("inventory.stock.view", "order_management.orders.view"))
        provider = r7.Provider(
            [r7.asks(r7.call(r7.STOCK, {"query": "x"}, "c1")), r7.answer6(reply), r7.answer6(reply, cid="a2")]
        )
        result = r7.run(session, contact, provider, r7.Mcp(env))
    assert "(not verified)" not in result.reply_text, result.reply_text
    assert result.reply_text == reply


# ------------------------------------------------------------------ G4


def _propose(db, w, name, args):
    with panel(db, w):
        return loop._propose(db, ctx_of(db, w), name, args, [], set(w.seen), str(uuid.uuid4()))


def test_G4_the_ticket_proposal_carries_a_note_saying_nothing_exists_and_it_is_a_draft(db):
    w = make_world(db, TICKET_SLUG)
    out = _propose(db, w, TICKET, {"title": "Printer on level 2", "priority": "high",
                                   "description": "The printer on level 2 is not printing."})
    assert out.status == "proposed", (out.status, out.message)
    note = " ".join(str(v) for k, v in out.data.items() if k not in ("action_id", "step", "summary")).lower()
    assert "draft" in note, out.data
    assert "not submitted" in note or "not yet submitted" in note, out.data
    assert "nothing" in note or "not created" in note, out.data


def test_G4_the_proposed_message_stays_and_another_write_has_no_note(db):
    w = make_world(db, TICKET_SLUG, CLOSE_SLUG)
    ticket = _propose(db, w, TICKET, {"title": "Printer on level 2"})
    args, _row = args_for(db, w, CLOSE)
    other = _propose(db, w, CLOSE, args)
    assert ticket.message == PROPOSED_MESSAGE
    assert other.status == "proposed" and other.message == PROPOSED_MESSAGE
    assert set(other.data) == {"action_id", "step", "summary"}
