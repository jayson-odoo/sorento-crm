"""AI-TOOLS-WAVE2 crew live rerun on 53908030 (round 10): answers right, Q1-Q4 and Q7 in 2 calls; "active customers
of LONG I / SEAN I" still took crm_resolve + crm_query (3 calls, ~35k). The agent's name resolved among customer
look-alikes, so the resolve round neither pointed at crm_query nor narrowed. No LLM."""
from __future__ import annotations

AGENT = {"id": "a1", "kind": "sales_agent", "code": "LI", "name": "LONG I"}
LOOK_ALIKE = {"id": "c1", "kind": "customer", "code": "300-L001", "name": "LONG I TRADING"}


def test_F1_an_agent_named_exactly_among_customer_look_alikes_is_found():
    from app.services.chatbot.agent.loop import found_agents

    data = {"results": [{"term": "LONG I", "status": "ambiguous", "matches": [LOOK_ALIKE, AGENT]}]}
    assert found_agents(data) == ["LI - LONG I"]
    by_code = {"results": [{"term": "li", "status": "ambiguous", "matches": [LOOK_ALIKE, AGENT]}]}
    assert found_agents(by_code) == ["LI - LONG I"]


def test_F2_a_term_that_is_not_the_agents_own_name_or_code_names_no_agent():
    from app.services.chatbot.agent.loop import found_agents

    assert found_agents({"results": [{"term": "LONG", "status": "ambiguous", "matches": [LOOK_ALIKE, AGENT]}]}) == []
    assert found_agents({"results": [{"term": "LONG I", "status": "found", "matches": [LOOK_ALIKE]}]}) == []
    twin = {**LOOK_ALIKE, "name": "LONG I"}
    assert found_agents({"results": [{"term": "LONG I", "status": "ambiguous", "matches": [twin, AGENT]}]}) == []
    # Every term must name an agent: a customer term beside it keeps the full tool set.
    two = {"results": [{"term": "LONG I", "status": "found", "matches": [AGENT]},
                       {"term": "LONG I TRADING", "status": "found", "matches": [LOOK_ALIKE]}]}
    assert found_agents(two) == []


def _schema(name, description=""):
    return {"type": "function", "function": {"name": name, "description": description}}


def test_R1_crm_resolve_says_agent_names_go_to_crm_query_when_both_are_offered():
    from app.services.chatbot.agent.loop import RESOLVE_AGENT_LINE, resolve_beside_query

    both = [_schema("crm_resolve", "Turn names into ids."), _schema("crm_query")]
    out = resolve_beside_query(both)
    assert out[0]["function"]["description"] == "Turn names into ids." + RESOLVE_AGENT_LINE
    assert both[0]["function"]["description"] == "Turn names into ids."  # the shared schema is not changed
    alone = [_schema("crm_resolve", "Turn names into ids.")]
    assert resolve_beside_query(alone) == alone


def test_R2_the_loop_applies_it_to_every_turns_schemas():
    import inspect

    import app.main  # noqa: F401
    from app.services.chatbot.agent import loop

    source = inspect.getsource(loop._run)
    built = source.index("schemas = tool_schemas(offered, catalog)")
    assert source.index("schemas = resolve_beside_query(schemas)", built) > built


def test_H1_the_index_names_the_agent_argument_for_customers_and_payouts():
    from app.services.chatbot.agent import query_tools

    lines = {line.split(" ", 1)[0]: line for line in query_tools.entity_index().splitlines()}
    assert "agent=<code or name as said>" in lines["customer"]
    assert "agent=<code or name as said>" in lines["agent_target_summary"]
