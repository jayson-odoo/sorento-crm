"""TARGET-ACHIEVED-PERF UAC 14 (`documentation/plans/sales/target-achieved-perf-14nov-acceptance-criteria.md`):
"my dealers" from an asker with no sales agent of their own.

Crew trace f0c0f4c8: the model read "my dealers" as an agent filter on the asker's own name, who has no sales agent,
so every target query came back empty or partial. `query_tools.query_as_asker` keeps the asker's own name when the
model says the question is about them (`about_self`, never a word match on the message); when
`own_scope.me(...).agent_ids` is empty, "my" cannot mean an agent, so an own-name filter that finds nothing is left
out even then and the tool reply says so. An asker WITH an agent keeps the "my" reading.

Through the loop (`loop.run_agent_turn`): a scripted model sends the crm_query, a spy on `query_tools.run_query`
records the args that reach the registry, and the tool message the model reads next is recorded. No LLM.
"""
from __future__ import annotations

import json
import uuid

import pytest

import app.main  # noqa: F401
from app.models.company import UserCompany
from app.models.user import User
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners
from app.services.llm_provider import ChatResult
from tests._pg_fixture import blank_session
from tests.chatbot.agent._ported_reads_support import panel_turn
from tests.chatbot.agent._seed import seed_agent_contact

ASKER = "Jayson Teh"
ENTITY = "agent_target_summary"
MY_DEALERS = "how are my dealers sales this year against their targets?"


@pytest.fixture
def db():
    register_company_scope_listeners()
    with blank_session() as session:
        yield session


@pytest.fixture
def asker(db):
    """A staff user named ASKER holding the targets screen, with no sales agent of their own."""
    contact = seed_agent_contact(db, slugs=("sales.targets.view",))
    db.get(User, contact["user_id"]).name = ASKER
    db.add(UserCompany(user_id=contact["user_id"], company_id=DEFAULT_COMPANY_ID))
    db.flush()
    return contact


def _own_agent(db, contact, name=ASKER):
    """A sales agent linked to the asker the way `own_scope.me` finds it (`SalesAgent.contact_id`)."""
    from app.models.sales_agent import SalesAgent
    from app.services import own_scope

    agent = SalesAgent(
        id=str(uuid.uuid4()), sales_agent=f"ZZTME-{uuid.uuid4().hex[:6]}".upper(), description=name,
        is_active=True, contact_id=contact["pk"],
    )
    db.add(agent)
    db.flush()
    assert own_scope.me(db, contact["user_id"]).agent_ids == (agent.id,)
    return agent


def _ask(db, contact, query: dict, text: str, monkeypatch, rows=lambda spec: []):
    """One panel turn: the model sends `query`, then answers. Every crm_query args that reached the registry (the
    asker's own name that finds nothing is dropped and the call runs again, `query_tools.query_as_asker`) and the tool
    message the model reads back. `rows(spec)`: what the registry finds for that call."""
    from app.services.chatbot.agent import loop, query_tools

    reached: list[dict] = []

    def spy(db_, user_id, spec):
        # What reaches the registry (`query_tools._query`): crm_query is a user read (`writes.USER_READS`), so the
        # spy sits where every route to the query meets.
        reached.append(json.loads(json.dumps(spec)))
        found = rows(spec)
        return {"entity": ENTITY, "rows": found, "total": len(found)}

    monkeypatch.setattr(query_tools, "run_query", spy)
    seen: list[list[dict]] = []

    class Provider:
        def __init__(self):
            self.steps = [
                ChatResult(content="", prompt_tokens=10, completion_tokens=5, total_tokens=15,
                           tool_calls=[{"id": "q1", "name": "crm_query", "arguments": query}]),
                ChatResult(content="", prompt_tokens=10, completion_tokens=5, total_tokens=15, tool_calls=[
                    {"id": "ans-1", "name": "answer",
                     "arguments": {"text": "Done.", "figures": [], "not_found": [], "not_checked": []}}]),
            ]

        def chat(self, messages, **kw):
            seen.append([m for m in messages if m.get("role") == "tool"])
            return self.steps.pop(0)

    with panel_turn(contact["user_id"]):
        loop.run_agent_turn(db, contact_respond_id=contact["respond_id"], text=text, provider=Provider(),
                            mcp_call=lambda n, a: {}, catalog={})
    assert reached, seen[-1] if seen else None
    replies = {m["tool_call_id"]: json.loads(m["content"]) for m in seen[-1]}
    return reached, replies["q1"]


def _names(args: dict) -> list[str]:
    values = [args.get("agent")] + [f.get("value") for f in args.get("filters") or [] if isinstance(f, dict)]
    return [v for v in values if isinstance(v, str)]


@pytest.mark.parametrize("about_self", [None, True], ids=["plain", "about_self"])
@pytest.mark.parametrize("form", ["agent", "owner_filter"])
def test_M1_my_dealers_from_an_asker_with_no_agent_drops_the_own_name(db, asker, monkeypatch, form, about_self):
    """UAC 14: "my" cannot mean an agent when the asker has none: the own name that finds nothing is left out of the
    call that answers (even when the model says the question is about the asker), the other filters stay, and the
    tool reply says the own name was left out."""
    query = {"entity": ENTITY, "period": "this_year",
             "filters": [{"field": "owner_kind", "op": "eq", "value": "dealer"}]}
    if about_self:
        query["about_self"] = True
    if form == "agent":
        query["agent"] = ASKER
    else:
        query["filters"].append({"field": "owner", "op": "eq", "value": ASKER})
    reached, reply = _ask(db, asker, query, MY_DEALERS, monkeypatch)
    args = reached[-1]

    assert ASKER not in _names(args), f"the asker's own name stayed in the answering call: {reached}"
    assert {"field": "owner_kind", "op": "eq", "value": "dealer"} in args["filters"]
    assert ASKER in (reply.get("message") or ""), reply
    assert "no sales agent of your own" in (reply.get("message") or ""), reply


def test_M2_my_dealers_from_an_asker_with_an_agent_keeps_the_own_name(db, asker, monkeypatch):
    """Guard: an asker WITH an agent of their own keeps the "my" reading (the model's `about_self`, never a word
    match on the message): the filter on their name stays, even when it finds nothing."""
    _own_agent(db, asker)
    query = {"entity": ENTITY, "period": "this_year", "agent": ASKER, "about_self": True,
             "filters": [{"field": "owner_kind", "op": "eq", "value": "dealer"}]}
    reached, reply = _ask(db, asker, query, MY_DEALERS, monkeypatch)

    assert len(reached) == 1 and reached[0].get("agent") == ASKER, reached
    assert "Left out" not in (reply.get("message") or ""), reply


def test_M3_an_asker_with_no_agent_naming_someone_else_keeps_that_filter(db, asker, monkeypatch):
    """Guard: another agent named by the asker is never dropped."""
    query = {"entity": ENTITY, "period": "this_year", "agent": "Agent B"}
    reached, reply = _ask(db, asker, query, "how is Agent B doing against target this year?", monkeypatch)

    assert len(reached) == 1 and reached[0].get("agent") == "Agent B", reached
    assert "Left out" not in (reply.get("message") or ""), reply


# ------------------------------------------------------------------ review round 6: an asker with an agent is untouched


@pytest.mark.parametrize("text,form", [
    ("am I on target this year?", "agent"),
    ("am I on target this year?", "owner_filter"),
], ids=["agent", "owner_filter"])
def test_M4_an_asker_with_an_agent_asking_am_i_on_target_keeps_the_own_name(db, asker, monkeypatch, text, form):
    """Lead decision (review round 6): "am I on target" says no "my", yet an agent asking it means themself, which
    the model says as `about_self`: the filter on their own name reaches the query unchanged even when it finds
    nothing (dropping it gave a full-view user everyone's rows), and no "Left out" note."""
    _own_agent(db, asker)
    query = {"entity": ENTITY, "period": "this_year", "about_self": True}
    if form == "agent":
        query["agent"] = ASKER
    else:
        query["filters"] = [{"field": "owner", "op": "eq", "value": ASKER}]
    reached, reply = _ask(db, asker, query, text, monkeypatch)

    assert len(reached) == 1 and ASKER in _names(reached[0]), f"the asker's own name was dropped: {reached}"
    assert "Left out" not in (reply.get("message") or ""), reply


def test_M5_an_asker_with_an_agent_whose_own_name_the_model_adds_keeps_it_when_it_finds_rows(db, asker, monkeypatch):
    """An asker with an agent: a name the model adds to "payout per dealer" is kept when the call finds their rows
    (the data decides, `query_tools.query_as_asker`); one that finds nothing is dropped (AGENT-COMMISSION-WA S9)."""
    _own_agent(db, asker)
    query = {"entity": ENTITY, "period": "this_year", "agent": ASKER,
             "filters": [{"field": "owner_kind", "op": "eq", "value": "dealer"}]}
    reached, reply = _ask(db, asker, query, "payout per dealer this year", monkeypatch,
                          rows=lambda spec: [{"id": "1", "owner": "D1"}])
    args = reached[0]

    assert len(reached) == 1 and args.get("agent") == ASKER, reached
    assert {"field": "owner_kind", "op": "eq", "value": "dealer"} in args["filters"]
    assert "Left out" not in (reply.get("message") or ""), reply
