"""TRACE-ENTITY-TOOL: every chatbot turn trace shows the matched entity and the tool used.

Owner, 11 Nov 2026, on turn #8322 ("srtwc286", a stock check on the business lane): the drawer
showed "Tool: -" and no entity. Plan: documentation/plans/chatbot/PLAN-trace-entity-tool-11nov.md.

Pure unit tests over hand-built trace records: no database, no LLM.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from app.services.chatbot import trace as trace_mod
from app.services.chatbot.analytics import outcome as analytics_outcome
from app.services.chatbot.trace_detail import compose_trace_detail

NOW = datetime(2026, 11, 11, tzinfo=timezone.utc)

#: What the business lane writes (lanes/business/__init__.py, the A9 `trace.add("tool", ...)`).
NAMED = {
    "kind": "tool",
    "at": NOW.isoformat(),
    "name": "crm_inventory_stock_balance_list",
    "args": {"product_codes": ["SRTWC286"], "contact_id": "x"},
    "envelope": {"rows": []},
    "ms": 157,
}
#: What `turn/fetch.py::_fetch_one` writes AFTER it, for the same call.
BARE = {"kind": "tool", "at": NOW.isoformat(), "domain": "stock"}


def _row(*extra: dict[str, Any]) -> SimpleNamespace:
    trace = [{"stage": "received", "status": "ok", "ms": 1, "summary": "", "facts": {}, "raw": {}}, *extra]
    return SimpleNamespace(
        id="zzt-turn", created_at=NOW, trace=trace, contact_respond_id="ZZT-c", is_test=True, envelope={}
    )


# --- 1. one rule for every reader: the last tool event WITH a name -------------------------------


def test_drawer_tool_is_the_named_event_when_a_bare_domain_event_follows():
    detail = compose_trace_detail(_row(NAMED, BARE))
    assert detail["tool"] is not None
    assert detail["tool"]["name"] == "crm_inventory_stock_balance_list"
    assert detail["tool"]["ms"] == 157


def test_drawer_tool_is_none_when_only_a_bare_domain_event_exists():
    assert compose_trace_detail(_row(BARE))["tool"] is None


def test_named_tool_event_takes_the_last_named_one():
    later = {**NAMED, "name": "crm_promotion_list", "ms": 9}
    assert trace_mod.named_tool_event([NAMED, BARE, later, BARE])["name"] == "crm_promotion_list"
    assert trace_mod.named_tool_event([BARE]) is None
    assert trace_mod.named_tool_event([]) is None


def test_named_tool_event_reads_the_nested_payload_shape_too():
    nested = {"kind": "tool", "payload": {"name": "crm_report_ask", "args": {}}}
    assert trace_mod.named_tool_event([nested, BARE])["name"] == "crm_report_ask"


def test_index_match_looked_up_reads_the_named_tool():
    index_event = {"kind": "closed_lists_index", "at": NOW.isoformat(), "words": ["srtwc286"], "matches": []}
    looked = compose_trace_detail(_row(index_event, NAMED, BARE))["index_match"]["looked_up"]
    assert looked is not None
    assert looked["what"].lower().startswith("crm inventory stock balance list")


def test_analytics_tools_lists_the_named_tool_not_the_domain_beside_it():
    turn = {"trace": [NAMED, BARE]}
    assert analytics_outcome._tools(turn) == ["crm_inventory_stock_balance_list"]


def test_analytics_tools_still_counts_a_domain_only_fetch():
    assert analytics_outcome._tools({"trace": [BARE]}) == ["stock"]


def test_console_trace_summary_reads_the_flat_tool_event():
    from app.services.chatbot import console_service

    summary = console_service._summarise_trace_events([NAMED, BARE])
    assert summary["tool"] == "crm_inventory_stock_balance_list"
    assert "contact_id" not in (summary["args_short"] or {})


# --- 2. the resolve event: what each typed word matched ------------------------------------------


def _resolved(*resolutions: dict[str, Any]) -> dict[str, Any]:
    return {"resolved": {"resolutions": list(resolutions)}}


def _m(code: str, tier: str = "exact", kind: str = "product") -> dict[str, Any]:
    return {"entity_type": kind, "canonical_code": code, "match_tier": tier, "uuid": "u-" + code}


def test_resolve_event_lists_each_word_with_codes_and_tier():
    event = trace_mod.resolve_event(
        _resolved({"token": "srtwc286", "matches": [_m("SRTWC286")], "ambiguous": False}),
        unplaced={"zzq": "zzq"},
        not_checked={},
    )
    assert event == {
        "words": [
            {"word": "srtwc286", "codes": ["SRTWC286"], "more": 0, "tiers": ["exact"], "kinds": ["product"],
             "ambiguous": False}
        ],
        "unplaced": ["zzq"],
        "not_checked": [],
    }


def test_resolve_event_caps_codes_at_ten_and_counts_the_rest():
    matches = [_m(f"SRTW{i:04d}", "prefix") for i in range(14)]
    event = trace_mod.resolve_event(_resolved({"token": "srtw", "matches": matches}), unplaced={}, not_checked={})
    word = event["words"][0]
    assert len(word["codes"]) == 10
    assert word["more"] == 4
    assert word["tiers"] == ["prefix"]


def test_resolve_event_has_no_uuid_in_it():
    event = trace_mod.resolve_event(_resolved({"token": "a1", "matches": [_m("A1")]}), unplaced={}, not_checked={})
    assert "u-A1" not in repr(event)


def test_resolve_event_reads_the_and_mode_shape():
    """AND mode (what a live stock check on one code answers): `tokens` + `intersection`."""
    payload = {"resolved": {"match_mode": "and", "tokens": ["srtwc286"], "intersection": [_m("SRTWC286", "and")]}}
    event = trace_mod.resolve_event(payload, unplaced={}, not_checked={})
    assert event["words"] == [
        {"word": "srtwc286", "codes": ["SRTWC286"], "more": 0, "tiers": ["and"], "kinds": ["product"], "ambiguous": False}
    ]


def test_resolve_event_is_none_with_nothing_to_say():
    assert trace_mod.resolve_event(None, unplaced={}, not_checked={}) is None
    assert trace_mod.resolve_event({"resolved": {"resolutions": []}}, unplaced={}, not_checked={}) is None


def test_drawer_renders_the_resolve_event_as_entity_match():
    event = {
        "kind": "resolve",
        "at": NOW.isoformat(),
        **trace_mod.resolve_event(
            _resolved({"token": "srtwc286", "matches": [_m("SRTWC286")]}), unplaced={"zzq": "zzq"}, not_checked={}
        ),
    }
    entity = compose_trace_detail(_row(event))["entity_match"]
    assert entity["words"][0]["word"] == "srtwc286"
    assert entity["words"][0]["codes"] == ["SRTWC286"]
    assert entity["words"][0]["tiers"] == ["exact"]
    assert entity["unplaced"] == ["zzq"]


def test_drawer_entity_match_is_none_without_a_resolve_event():
    assert compose_trace_detail(_row(NAMED))["entity_match"] is None


# --- 3. Ran after / Next: say why there is no neighbour -------------------------------------------


def test_order_says_neighbours_were_checked_only_with_a_session():
    queued = {"stage": "queued", "status": "ok", "ms": 1, "summary": "", "facts": {"ticket": 3, "wait_ms": 5}, "raw": {}}
    order = compose_trace_detail(_row(queued))["order"]
    assert order["neighbours_checked"] is False
