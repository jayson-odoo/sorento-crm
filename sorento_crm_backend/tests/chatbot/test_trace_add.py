"""A9 - `TurnTrace.add` and the three call sites that use it: `tool`, `crossdomain`,
`reveals`.

`documentation/plans/chatbot/PLAN-chatbot-growth-r1.md` Slice A.

`trace.add`'s entries live on `TurnTrace.events` - a SEPARATE list from `.records`
(what `record()` writes and what gets persisted to `chatbot.turns.trace`), because
`tests/chatbot/test_trace_legibility.py::_assert_trace_is_legible` walks EVERY entry
of that persisted array demanding a plain-language `summary`/`why`/`raw`, and a tool
call's raw args/envelope is not prose. See `trace.py::TurnTrace.__init__`'s own
comment for the full reason. Not yet persisted anywhere - Slice D (a later lane) is
what decides where `events` lives in `chatbot.turns` and exposes it; these tests
exercise the real production functions (`run_fetch`, `run_crossdomain`) with a real
`TurnTrace()`, which is as close to "a real turn through the engine" as this slice's
scope reaches without that Slice D decision.
"""
from __future__ import annotations

from typing import Any

from app.services.chatbot import trace as trace_mod
from app.services.chatbot.lanes import business
from app.services.chatbot.lanes.business.answer import run_crossdomain
from app.services.chatbot.lanes.business.services import AnswerServices, FetchServices


def _fetch_services(mcp_result: str) -> FetchServices:
    return FetchServices(
        embed=lambda query: [0.1],
        tool_search=lambda embedding, *, query, domain: [
            {"name": "crm_master_products_list", "similarity": 0.9}
        ],
        mcp_call=lambda name, args: mcp_result,
    )


def test_turn_trace_add_appends_to_events_not_records():
    t = trace_mod.TurnTrace()
    t.add("tool", {"name": "crm_master_products_list", "args": {}, "ms": 5})
    assert len(t.events) == 1
    assert t.events[0]["kind"] == "tool"
    assert t.events[0]["payload"]["name"] == "crm_master_products_list"
    assert t.records == [], "add() must never touch the persisted stage list"


def test_run_fetch_records_a_tool_event():
    t = trace_mod.TurnTrace()
    payload = {
        "_exit_kind": "continue",
        "gate": {
            "compatible_entities": [
                {"uuid": "6136ea6b-1699-46ec-8e8e-f60c8bb64310", "entity_type": "product", "code": "SRTWB7096"}
            ]
        },
    }
    services = _fetch_services('{"answers": [], "has_result": false}')

    business.run_fetch(payload, services=services, dry_run=False, trace=t)

    tool_events = [e for e in t.events if e["kind"] == "tool"]
    assert len(tool_events) == 1
    ev = tool_events[0]["payload"]
    assert ev["name"] == "crm_master_products_list"
    assert "args" in ev and "envelope" in ev
    assert isinstance(ev["ms"], int)


def test_run_fetch_records_a_reveals_event_when_restricted_fields_present():
    t = trace_mod.TurnTrace()
    payload = {
        "_exit_kind": "continue",
        "gate": {
            "compatible_entities": [
                {"uuid": "6136ea6b-1699-46ec-8e8e-f60c8bb64310", "entity_type": "product", "code": "SRTWB7096"}
            ]
        },
    }
    envelope = {
        "result_type": "stock",
        "intro": "Stock details found for the requested products.",
        "items": [{"title": "SRTWB7096", "fields": [
            {"key": "sellable", "label": "Sellable (on hand minus open SO)", "value": 13},
        ]}],
        "restricted_fields": {"sellable": "inventory.sellable"},
        "has_result": True,
    }
    import json

    services = _fetch_services(json.dumps(envelope))

    business.run_fetch(payload, services=services, dry_run=False, trace=t)

    reveals = [e for e in t.events if e["kind"] == "reveals"]
    assert len(reveals) == 1
    ev = reveals[0]["payload"]
    assert ev["restricted_fields_seen"] == ["sellable"]
    assert ev["granted"] == []
    assert ev["dropped"] == ["sellable"]


def test_run_fetch_records_no_reveals_event_when_no_restricted_fields():
    t = trace_mod.TurnTrace()
    payload = {
        "_exit_kind": "continue",
        "gate": {
            "compatible_entities": [
                {"uuid": "6136ea6b-1699-46ec-8e8e-f60c8bb64310", "entity_type": "product", "code": "SRTWB7096"}
            ]
        },
    }
    services = _fetch_services('{"answers": [], "has_result": false}')

    business.run_fetch(payload, services=services, dry_run=False, trace=t)

    assert [e for e in t.events if e["kind"] == "reveals"] == []


def test_run_crossdomain_records_a_crossdomain_event():
    t = trace_mod.TurnTrace()
    calls: list[tuple[str, dict]] = []

    def mcp_probe(name: str, args: dict) -> Any:
        calls.append((name, args))
        return {"answers": [], "has_result": False}

    services = AnswerServices(mcp_probe=mcp_probe, family_fetch=lambda q: {"data": []})

    run_crossdomain(
        {
            "answers": [{"fields": [{"label": "Product Code", "value": "SRTOTHER"}]}],
            "response": "Some other stock line.",
        },
        parser={
            "message_type": "business_query",
            "intent_hint": "check_stock",
            "domain_hint": "inventory",
            "user_goal": "check stock for SRTWC8517",
            "access_levels": [],
        },
        resolved={
            "resolutions": [
                {
                    "token": "SRTWC8517",
                    "matches": [
                        {
                            "entity_type": "product",
                            "canonical_code": "SRTWC8517",
                            "uuid": "prod-uuid-1",
                            "match_tier": "exact",
                        }
                    ],
                }
            ]
        },
        session_block={"session_vars": {"variables": {}}},
        entities_names=None,
        services=services,
        contact_id="164838271",
        space_id="900001",
        trace=t,
    )

    crossdomain_events = [e for e in t.events if e["kind"] == "crossdomain"]
    assert len(crossdomain_events) == 1
    ev = crossdomain_events[0]["payload"]
    assert ev["tool"] == "crm_incoming_stock_list"
    assert "args" in ev
    assert "rendered" in ev
