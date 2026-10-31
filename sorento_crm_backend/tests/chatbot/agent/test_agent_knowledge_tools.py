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
