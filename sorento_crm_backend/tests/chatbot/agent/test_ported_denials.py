"""AGENTIC-UNIFY PR 4: a route's 403 on a panel turn is a plain denial, all the way to the closing reply.

An identity read needs both the staff user and the key's act-as user to hold the route's slug
(`user_service.gate_user_ids`), so a panel user holding every slug can still get a 403 if the act-as role lacks it.
`call` answers a 403 in the two real shapes it takes: a body carrying `status_code` (`_body_failure`) and a raised
error that `_HTTP_ERR` matches. The model must be told a plain no-access line (no URL, path, slug or status number),
nothing escapes, and the turn closes normally with the model's own answer.
"""
from __future__ import annotations

import json
import re
import uuid

import pytest

import app.main  # noqa: F401  register every model and the app's listeners
from app.services.chatbot import principal as staff_principal
from app.services.chatbot.agent import tools as agent_tools
from app.services.company_scope import register_company_scope_listeners
from tests._pg_fixture import blank_session
from tests.chatbot.agent._ported_reads_support import AC1, catalog, panel_ctx, panel_turn, slugs_for
from tests.chatbot.agent._seed import seed_user
from tests.chatbot.agent.test_agent_writes import answer_, round_of, tc
from tests.chatbot.agent.test_agent_writes_round1 import Prov

LEAKY = (
    "Forbidden: requires complaint_management.complaints.view for GET "
    "https://crm.example.test/api/v1/complaints-management/complaints (status 403)"
)
SHAPES = ["body", "raised"]
READS = [row[0] for row in AC1]
PLAIN_BAD = re.compile(r"https?:|/api/|/v1/|\b[a-z_]+\.[a-z_]+\.[a-z_]+\b|\b403\b")


@pytest.fixture(autouse=True)
def _listeners():
    register_company_scope_listeners()
    yield


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def refusing(shape: str):
    """A `call` that answers a 403 in one of its two real shapes."""
    def call(name, args):
        if shape == "body":
            return {"status_code": 403, "detail": LEAKY}
        raise RuntimeError(f"{name} returned HTTP 403: {json.dumps({'detail': LEAKY})}")

    return call


def holder(db, name):
    slug = next(r[1] for r in AC1 if r[0] == name)
    return seed_user(db, contact_pk=None, slugs=slugs_for(name, slug))


def assert_plain(message: str) -> None:
    assert message.strip(), "the model was told nothing"
    assert not PLAIN_BAD.search(message), f"the denial leaks a URL, path, slug or status: {message!r}"


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("name", READS)
def test_a_403_from_the_route_is_a_plain_denial_through_dispatch(db, name, shape):
    user_id = holder(db, name)
    ctx = panel_ctx(db, user_id)
    with panel_turn(user_id):
        out = agent_tools.dispatch(
            db, ctx, name, {}, call=refusing(shape), catalog=catalog(), timeout=5.0
        )
    assert out.status == "denied", (out.status, out.message)
    assert_plain(out.message)


@pytest.mark.parametrize("shape", SHAPES)
def test_a_403_closes_the_real_turn_normally_with_the_models_answer(db, shape):
    from app.services.chatbot.agent.loop import run_agent_turn

    name = "crm_complaints_list"
    user_id = holder(db, name)
    seen: dict = {}

    def after_call(messages, tools):
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        seen["tool"] = json.loads(tool_msgs[-1]["content"]) if tool_msgs else None
        return answer_("You do not have access to the complaints list.")

    prov = Prov([round_of(tc(name, {}, "c1")), after_call])
    principal = staff_principal.StaffPrincipal(user_id=user_id, conversation_id=str(uuid.uuid4()))
    with staff_principal.acting_as(principal):
        result = run_agent_turn(
            db, contact_respond_id=principal.key, text="list the complaints", provider=prov,
            mcp_call=refusing(shape), catalog=catalog(),
        )
    assert seen["tool"] is not None and seen["tool"]["status"] == "denied", seen
    assert_plain(seen["tool"]["message"])
    assert result.status == "answered", (result.status, result.limit_hit)
    assert "do not have access" in result.reply_text.lower(), result.reply_text
    assert not PLAIN_BAD.search(result.reply_text), result.reply_text
