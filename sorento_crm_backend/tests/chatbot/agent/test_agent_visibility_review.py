"""AGENTIC-P3 slice 6 review round: the formatter leaves identifiers alone, and no id reaches the
console through a tool detail or a step error."""
from __future__ import annotations

import re
import uuid

import pytest

import app.main  # noqa: F401  register every model and the app's listeners
from app.audit_context import clear_actor
from app.models.chatbot_agent import AgentAction
from app.services.audit_service import register_audit_listeners
from app.services.company_scope import register_company_scope_listeners
from tests.chatbot.agent.test_agent_writes import make_world as ask_world, proposal_script
from tests.chatbot.agent.test_agent_writes_round1 import client, console, go  # noqa: F401 - fixtures + helper
from tests._pg_fixture import blank_session

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
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


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Codes A**B and C**D", "Codes A**B and C**D"),
        ("HX__200__B", "HX__200__B"),
        ("call obj.__init__ here", "call obj.__init__ here"),
        ("## Heading **x**", "*Heading x*"),
        ("a **bold** word", "a *bold* word"),
        ("an __italic__ word", "an _italic_ word"),
        ("**Total**: 5", "*Total*: 5"),
    ],
)
def test_the_converter_does_not_touch_identifiers(raw, expected):
    from app.services.chatbot.agent.formatting import to_whatsapp

    assert to_whatsapp(raw) == expected


def test_a_uuid_in_a_query_argument_or_a_refusal_message_never_reaches_the_detail():
    from app.services.chatbot.agent.loop import tool_detail
    from app.services.chatbot.agent.tools import ToolResult

    ident = str(uuid.uuid4())

    asked = tool_detail("crm_customer_asks_list", {"query": f"look for {ident}"}, ToolResult("ok", data={"open": []}), {})
    refused = tool_detail(
        "crm_customer_ask_update", {"state": "done"}, ToolResult("invalid", message=f"Unknown id {ident} here."), {}
    )

    assert "look for" in asked and "Unknown id" in refused  # the text is there, the id is not
    assert not UUID_RE.search(asked) and not UUID_RE.search(refused)


def test_a_uuid_in_a_step_error_is_scrubbed_from_the_outcome_and_the_reload(console, db, session_factory):
    from app.services.chatbot.agent import actions

    ident = str(uuid.uuid4())
    steps = [{"summary": "Mark done", "status": "failed", "error": f"Stock ask {ident} not found.", "changes": []}]
    assert not UUID_RE.search(str(actions._out_steps(steps)))

    s = session_factory()
    w = ask_world(s)
    first, _ = go(s, w, proposal_script(w.asks))
    row = s.get(AgentAction, first.pending_action["id"])
    row.status, row.steps = "partial", steps
    s.commit()

    body = console.get(CONVERSATION, params={"contact_respond_id": w.respond_id}).json()

    shown = body["turns"][0]["actions"][0]["steps"][0]["error"]
    assert "not found" in shown and not UUID_RE.search(shown)


def test_a_link_with_no_known_code_is_worded_as_a_customer():
    from app.services.chatbot.agent import writes

    assert writes._link_words([str(uuid.uuid4())], {}) == "a customer"
