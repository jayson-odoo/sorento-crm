"""AGENTIC-KNOWLEDGE P1, the Console agent's two document tools (UAC AC-K14, K15, K17).

`crm_knowledge_search` is a LOCAL tool (like `crm_products_find`): it runs in process with the
turn's linked user and never goes through the MCP `call`. `user_guides_read` is an MCP tool
open to every linked user, and its call carries only `query`.

Users, roles and permissions are real rows on the blank Postgres schema, so the permission
layer runs for real; only `knowledge_service.search` is replaced by a spy (the search itself
is tested in tests/test_agentic_knowledge_search.py).
"""
from __future__ import annotations

import json

import pytest

from tests._pg_fixture import blank_session
from tests.chatbot.agent._seed import seed_user

SEARCH = "crm_knowledge_search"
GUIDES = "user_guides_read"
VIEW = "resource.attachments.view"

CATALOG = {
    GUIDES: {
        "description": "Search the CRM user guides",
        "inputSchema": {
            "type": "object",
            "properties": {
                "contact_id": {"type": "string"},
                "space_id": {"type": "string"},
                "query": {"type": "string"},
            },
            "required": ["contact_id", "space_id", "query"],
        },
    }
}

HIT = {
    "status": "ok",
    "passages": [
        {
            "document": "Employee Handbook 2026",
            "page": 14,
            "heading": "Leave",
            "text": "Annual leave is 14 days after three years.",
            "similarity": 0.91,
        }
    ],
    "handoff_teams": ["HR"],
}


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


class Recorder:
    """A fake MCP `call(name, args)`."""

    def __init__(self, result=None):
        self.result = {"items": [{"title": "How to create an order"}]} if result is None else result
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, name, args):
        self.calls.append((name, dict(args)))
        return self.result


def forbidden_call(name, args):
    raise AssertionError(f"the MCP `call` must not be used for {name}")


def _ctx(user_id):
    from app.services.chatbot.agent.access import AgentContext

    return AgentContext(
        contact_pk="pk-1",
        contact_respond_id="ZZT-RESPOND-1",
        space_id="364817",
        user_id=user_id,
        user_name="ZZT User",
        grants=frozenset(),
    )


def _dispatch(db, user_id, name, args, call, catalog=None):
    from app.services.chatbot.agent import tools

    return tools.dispatch(db, _ctx(user_id), name, args, call=call, catalog=CATALOG if catalog is None else catalog, timeout=5.0)


@pytest.fixture
def search_spy(monkeypatch):
    from app.services import knowledge_service

    calls: list[dict] = []

    def spy(db, *, user_id, query, top_k=5, embed=None):
        calls.append({"user_id": user_id, "query": query, "top_k": top_k})
        return dict(HIT)

    monkeypatch.setattr(knowledge_service, "search", spy)
    return calls


# ---------------------------------------------------------------- registry and schemas


def test_registry_holds_both_document_tools():
    from app.services.chatbot.agent.tools import REGISTRY

    assert SEARCH in REGISTRY
    assert REGISTRY[SEARCH].user_permission == VIEW
    assert GUIDES in REGISTRY


def test_the_knowledge_schema_is_local_and_exists_with_an_empty_catalog():
    from app.services.chatbot.agent.tools import REGISTRY, tool_schemas

    schemas = tool_schemas([REGISTRY[SEARCH]], catalog={})

    assert len(schemas) == 1
    fn = schemas[0]["function"]
    assert schemas[0]["type"] == "function"
    assert fn["name"] == SEARCH
    assert "query" in fn["parameters"]["properties"]
    assert "query" in fn["parameters"].get("required", [])
    for guard in ("contact_id", "space_id"):
        assert guard not in fn["parameters"]["properties"]


def test_the_guides_schema_hides_the_server_injected_ids():
    from app.services.chatbot.agent.tools import REGISTRY, tool_schemas

    schemas = tool_schemas([REGISTRY[GUIDES]], CATALOG)

    assert len(schemas) == 1
    params = schemas[0]["function"]["parameters"]
    assert set(params["properties"]) == {"query"}
    assert params["required"] == ["query"]


# ---------------------------------------------------------------- exposure to the model


def test_a_user_with_the_view_slug_is_offered_the_knowledge_tool_and_one_without_is_not(db):
    from app.services.chatbot.agent.access import permitted_tools

    reader = seed_user(db, contact_pk=None, slugs=(VIEW,))
    outsider = seed_user(db, contact_pk=None, slugs=("inventory.stock.view",))

    assert SEARCH in {t.name for t in permitted_tools(db, _ctx(reader))}
    assert SEARCH not in {t.name for t in permitted_tools(db, _ctx(outsider))}


def test_every_linked_user_is_offered_the_guides_tool_even_with_no_permissions(db):
    from app.services.chatbot.agent.access import permitted_tools

    nobody = seed_user(db, contact_pk=None, slugs=())

    assert GUIDES in {t.name for t in permitted_tools(db, _ctx(nobody))}


# ---------------------------------------------------------------- crm_knowledge_search dispatch


def test_knowledge_search_runs_in_process_with_the_turns_user_and_never_uses_mcp(db, search_spy):
    reader = seed_user(db, contact_pk=None, slugs=(VIEW,))

    out = _dispatch(db, reader, SEARCH, {"query": "annual leave after 3 years"}, forbidden_call, catalog={})

    assert out.status == "ok", out.message
    assert len(search_spy) == 1
    assert search_spy[0]["user_id"] == reader
    assert search_spy[0]["query"] == "annual leave after 3 years"
    body = json.dumps(out.data, default=str)
    assert "Annual leave is 14 days after three years." in body
    assert "Employee Handbook 2026" in body
    assert "HR" in body, "the hand-off team travels back to the model"


def test_knowledge_search_is_denied_without_the_view_slug_and_searches_nothing(db, search_spy):
    outsider = seed_user(db, contact_pk=None, slugs=("inventory.stock.view",))

    out = _dispatch(db, outsider, SEARCH, {"query": "annual leave"}, forbidden_call, catalog={})

    assert out.status == "denied"
    assert search_spy == []


def test_knowledge_search_is_denied_when_the_slug_is_lost_after_exposure(db, search_spy):
    """Showing a tool to the model is not a guard: dispatch re-checks at call time."""
    reader = seed_user(db, contact_pk=None, slugs=(VIEW,))
    from app.services.chatbot.agent.access import permitted_tools

    assert SEARCH in {t.name for t in permitted_tools(db, _ctx(reader))}
    from app.models.user import UserRoleAssignment

    db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == reader).delete()
    db.flush()
    # The permission check is cached for 30 s; a real revocation invalidates it.
    from app.services.user_service import invalidate_rbac_cache

    invalidate_rbac_cache(reader)

    out = _dispatch(db, reader, SEARCH, {"query": "annual leave"}, forbidden_call, catalog={})

    assert out.status == "denied"
    assert search_spy == []


@pytest.mark.parametrize("bad", [None, "annual leave", ["annual leave"]])
def test_knowledge_search_arguments_must_be_an_object(db, search_spy, bad):
    reader = seed_user(db, contact_pk=None, slugs=(VIEW,))

    out = _dispatch(db, reader, SEARCH, bad, forbidden_call, catalog={})

    assert out.status == "invalid"
    assert search_spy == []


# ---------------------------------------------------------------- user_guides_read dispatch


def test_guides_read_is_allowed_for_a_user_with_no_permissions_and_carries_only_query(db):
    nobody = seed_user(db, contact_pk=None, slugs=())
    rec = Recorder()

    out = _dispatch(db, nobody, GUIDES, {"query": "how do I create an order"}, rec)

    assert out.status == "ok", out.message
    assert rec.calls == [(GUIDES, {"query": "how do I create an order"})], (
        "no contact_id / space_id / view key is injected into this call"
    )


def test_guides_read_drops_a_model_supplied_contact_or_space(db):
    nobody = seed_user(db, contact_pk=None, slugs=())
    rec = Recorder()

    out = _dispatch(db, nobody, GUIDES, {"query": "how do I create an order", "contact_id": "EVIL", "space_id": "EVIL"}, rec)

    assert out.status in ("ok", "invalid")
    for _, args in rec.calls:
        assert args == {"query": "how do I create an order"}


# ---------------------------------------------------------------- SB1: the console operator, not only the linked user


def _operator_ctx(linked_user, operator_user):
    import dataclasses

    return dataclasses.replace(_ctx(linked_user), operator_user_id=operator_user)


def test_an_operator_without_the_view_slug_is_denied_even_when_the_linked_user_holds_it(db, search_spy):
    """SB1: a console operator acts through the contact's linked user, so BOTH must hold the slug."""
    from app.services.chatbot.agent import tools

    linked = seed_user(db, contact_pk=None, slugs=(VIEW,))
    operator = seed_user(db, contact_pk=None, slugs=("inventory.stock.view",))
    ctx = _operator_ctx(linked, operator)

    assert tools.user_may_use(db, ctx, tools.REGISTRY[SEARCH]) is False
    out = tools.dispatch(db, ctx, SEARCH, {"query": "annual leave"}, call=forbidden_call, catalog={}, timeout=5.0)

    assert out.status == "denied"
    assert search_spy == []


def test_an_operator_who_holds_the_view_slug_is_allowed(db, search_spy):
    from app.services.chatbot.agent import tools

    linked = seed_user(db, contact_pk=None, slugs=(VIEW,))
    operator = seed_user(db, contact_pk=None, slugs=(VIEW,))
    ctx = _operator_ctx(linked, operator)

    assert tools.user_may_use(db, ctx, tools.REGISTRY[SEARCH]) is True
    out = tools.dispatch(db, ctx, SEARCH, {"query": "annual leave"}, call=forbidden_call, catalog={}, timeout=5.0)

    assert out.status == "ok", out.message
    assert len(search_spy) == 1


def test_the_search_runs_as_the_linked_user_when_both_may_read(db, search_spy):
    """The passages are scoped to the linked user (company scope, audience); the operator only has to be allowed."""
    from app.services.chatbot.agent import tools

    linked = seed_user(db, contact_pk=None, slugs=(VIEW,))
    operator = seed_user(db, contact_pk=None, slugs=(VIEW,))

    tools.dispatch(
        db, _operator_ctx(linked, operator), SEARCH, {"query": "annual leave"}, call=forbidden_call, catalog={}, timeout=5.0
    )

    assert search_spy[0]["user_id"] == linked


# ---------------------------------------------------------------- STrace: passage text never lands in the stored trace

PASSAGE_TEXT = "ZZT SECRET PASSAGE: annual leave is 14 days after three years of service."
HIT_WITH_TEXT = {
    "status": "ok",
    "passages": [
        {"document": "Employee Handbook 2026", "page": 14, "heading": "Leave", "text": PASSAGE_TEXT, "similarity": 0.91}
    ],
    "handoff_teams": ["HR"],
}


def test_trace_safe_drops_the_passage_text_and_keeps_document_and_page():
    """Seam: `tools.trace_safe(name, data)`, the form of a tool result that may be stored in a trace."""
    import copy

    from app.services.chatbot.agent import tools

    data = copy.deepcopy(HIT_WITH_TEXT)

    safe = tools.trace_safe(SEARCH, data)

    assert PASSAGE_TEXT not in json.dumps(safe)
    assert all("text" not in p for p in safe["passages"])
    assert safe["passages"][0]["document"] == "Employee Handbook 2026"
    assert safe["passages"][0]["page"] == 14
    assert data == HIT_WITH_TEXT, "the live result the model reads is not mutated"


def test_trace_safe_leaves_every_other_tool_unchanged():
    from app.services.chatbot.agent import tools

    data = {"items": [{"text": "a row that happens to carry a text field", "qty": 12}]}

    assert tools.trace_safe("crm_inventory_stock_balance_list", data) == data
    assert tools.trace_safe(GUIDES, {"text": "guide body"}) == {"text": "guide body"}


def test_a_turn_that_searched_the_documents_stores_no_passage_text(db, monkeypatch):
    """End to end: the turn row's trace and response, and the steps read back from it, carry no passage text."""
    import copy

    from app.models.chatbot_turn import ChatbotTurn
    from app.services import knowledge_service
    from app.services.chatbot.agent.loop import run_agent_turn
    from app.services.chatbot.agent.memory import steps_for_turn
    from app.services.llm_provider import ChatResult
    from tests.chatbot.agent._seed import seed_agent_contact

    monkeypatch.setattr(knowledge_service, "search", lambda db_, **kw: copy.deepcopy(HIT_WITH_TEXT))
    contact = seed_agent_contact(db, slugs=(VIEW,))

    class Provider:
        def __init__(self):
            self.script = [
                ChatResult(
                    content="", prompt_tokens=10, completion_tokens=1, total_tokens=11,
                    tool_calls=[{"id": "k1", "name": SEARCH, "arguments": {"query": "annual leave"}}],
                ),
                ChatResult(
                    content="", prompt_tokens=10, completion_tokens=1, total_tokens=11,
                    tool_calls=[{
                        "id": "a1", "name": "answer",
                        "arguments": {"text": "Fourteen days (Employee Handbook 2026, p.14).", "figures": [], "not_found": [], "not_checked": []},
                    }],
                ),
            ]
            self.seen_tool_results: list[str] = []

        def chat(self, messages, *, tools=None, **kw):
            for m in messages:
                if m.get("role") == "tool":
                    self.seen_tool_results.append(str(m.get("content")))
            return self.script.pop(0)

    provider = Provider()
    result = run_agent_turn(
        db, contact_respond_id=contact["respond_id"], text="annual leave after 3 years?",
        provider=provider, mcp_call=forbidden_call, catalog={},
    )

    assert any(PASSAGE_TEXT in c for c in provider.seen_tool_results), "the model itself still reads the passage"
    row = db.query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).one()
    stored = json.dumps([row.trace, row.response, row.envelope, steps_for_turn(db, result.turn_id)], default=str)
    assert PASSAGE_TEXT not in stored
    assert "annual leave is 14 days" not in stored


# ---------------------------------------------------------------- RS7: the protocol only where the tool is bound


def _first_system_prompt(db, slugs, monkeypatch):
    from app.services import knowledge_service
    from app.services.chatbot.agent.loop import run_agent_turn
    from app.services.llm_provider import ChatResult
    from tests.chatbot.agent._seed import seed_agent_contact

    monkeypatch.setattr(knowledge_service, "search", lambda db_, **kw: dict(HIT_WITH_TEXT))
    contact = seed_agent_contact(db, slugs=slugs)
    seen: list[list[dict]] = []

    class Provider:
        def chat(self, messages, *, tools=None, **kw):
            seen.append(list(messages))
            return ChatResult(
                content="", prompt_tokens=10, completion_tokens=1, total_tokens=11,
                tool_calls=[{"id": "a1", "name": "answer",
                             "arguments": {"text": "Hello.", "figures": [], "not_found": [], "not_checked": []}}],
            )

    run_agent_turn(
        db, contact_respond_id=contact["respond_id"], text="hello", provider=Provider(), mcp_call=forbidden_call, catalog={}
    )
    return seen[0][0]["content"]


def test_the_agent_prompt_carries_both_protocols_when_the_knowledge_tool_is_offered(db, monkeypatch):
    prompt = _first_system_prompt(db, (VIEW,), monkeypatch)

    assert "KNOWLEDGE PROTOCOL" in prompt
    assert "USER GUIDE PROTOCOL" in prompt
    assert SEARCH in prompt


def test_the_agent_prompt_has_no_knowledge_protocol_when_the_tool_is_not_offered(db, monkeypatch):
    prompt = _first_system_prompt(db, ("inventory.stock.view",), monkeypatch)

    assert "KNOWLEDGE PROTOCOL" not in prompt


# ================================================================ FIX ROUND 2: company scope (NB1)
#
# The user's own scope is `company_scope_resolver._scope_for_user(db, user_id, None)`, the helper
# `writes.run_as_user` uses: the user's `last_active_company_id` when granted, else the only grant,
# else the lowest granted id. The contact's mapping (set on the session by `build_context`) is the
# OUTER bound; the linked user's scope and the console operator's scope each narrow it further.


def _scoped_world(db, monkeypatch, *, linked_grants, operator_grants, linked_active=None, operator_active=None):
    from app.models.company import UserCompany
    from app.models.base import set_company_scope
    from app.models.user import User
    from app.services import knowledge_service
    from tests._knowledge_seed import (
        SORENTO_COMPANY_ID, query_embed, seed_attachment, seed_chunk, seed_company, seed_type, vec_with_similarity,
    )

    company_b = seed_company(db, "B")
    ids = {"A": SORENTO_COMPANY_ID, "B": company_b}
    linked = seed_user(db, contact_pk=None, slugs=(VIEW,))
    operator = seed_user(db, contact_pk=None, slugs=(VIEW,))
    for user, grants, active in ((linked, linked_grants, linked_active), (operator, operator_grants, operator_active)):
        for g in grants:
            db.add(UserCompany(user_id=user, company_id=ids[g]))
        if active:
            db.query(User).filter(User.id == user).update({"last_active_company_id": ids[active]})
    db.flush()
    att = seed_attachment(db, seed_type(db, audience="staff"), "B only.pdf", company_id=company_b)
    seed_chunk(db, att, vec_with_similarity(1.0), text="company B passage")
    monkeypatch.setattr(knowledge_service, "_default_embed", lambda db_, timeout=None: query_embed)
    set_company_scope(db, frozenset({ids["A"], ids["B"]}))  # the contact is mapped to both companies
    return linked, operator


def _passages(db, linked, operator=None):
    import dataclasses

    from app.services.chatbot.agent import tools

    ctx = _ctx(linked)
    if operator:
        ctx = dataclasses.replace(ctx, operator_user_id=operator)
    out = tools.dispatch(db, ctx, SEARCH, {"query": "annual leave"}, call=forbidden_call, catalog={}, timeout=5.0)
    assert out.status in ("ok", "empty"), out.message
    return [p["text"] for p in (out.data or {}).get("passages", [])]


def test_a_linked_user_whose_own_scope_is_company_a_gets_no_company_b_passage(db, monkeypatch):
    linked, _ = _scoped_world(db, monkeypatch, linked_grants=["A"], operator_grants=["A", "B"])

    assert _passages(db, linked) == []


def test_an_operator_whose_scope_is_company_a_gets_no_company_b_passage(db, monkeypatch):
    linked, operator = _scoped_world(
        db, monkeypatch, linked_grants=["A", "B"], operator_grants=["A"], linked_active="B"
    )

    assert _passages(db, linked, operator) == []


def test_when_the_user_and_the_operator_both_have_company_b_the_passage_is_returned(db, monkeypatch):
    linked, operator = _scoped_world(
        db, monkeypatch, linked_grants=["A", "B"], operator_grants=["A", "B"], linked_active="B", operator_active="B"
    )

    assert _passages(db, linked, operator) == ["company B passage"]


def test_the_session_scope_is_restored_after_the_search(db, monkeypatch):
    from app.models.base import get_company_scope

    linked, _ = _scoped_world(db, monkeypatch, linked_grants=["A", "B"], operator_grants=["A", "B"], linked_active="B")
    before = get_company_scope(db)

    _passages(db, linked)

    assert get_company_scope(db) == before
