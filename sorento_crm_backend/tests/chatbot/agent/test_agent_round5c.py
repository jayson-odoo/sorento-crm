"""AGENTIC-P1 round 5c (re-reviews of 9a3931d647): red tests.

V1 numbers inside formatted strings back figures, V2 identifiers with digits are not figures,
S5-1 UUIDs seen in any ok result are known ids, M5 the resolver's code reader stays off, and the
low items (not-found matching, host:port stripping, UUIDs out of the reply).
"""
from __future__ import annotations

import copy
import json
import uuid

import pytest

from app.models.user import SystemSetting  # noqa: F401
from app.services.chatbot.lanes.business import services as business_services
from app.services.llm_provider import ChatResult
from app.services.user_service import UserPermissionService
from tests._pg_fixture import blank_session
from tests.chatbot.agent._seed import seed_agent_contact

STOCK = "crm_inventory_stock_balance_list"
REPORT = "crm_report_ask"
RESOLVE = "crm_resolve"
ANSWER = "answer"

_PROPS = {
    "contact_id": {"type": "string"},
    "space_id": {"type": "string"},
    "query": {"type": "string"},
    "view": {"type": "string"},
    "warehouse_ids": {"type": "array", "items": {"type": "string"}},
}
CATALOG = {
    n: {"description": n, "inputSchema": {"type": "object", "properties": dict(_PROPS), "required": ["contact_id"]}}
    for n in (STOCK, REPORT)
}


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture()
def contact(db):
    return seed_agent_contact(db, slugs=("inventory.stock.view", "order_management.orders.view"))


class Mcp:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def __call__(self, name, args):
        self.calls.append((name, dict(args)))
        return self.result


def call(name, args=None, cid="c1"):
    return {"id": cid, "name": name, "arguments": {} if args is None else args}


def asks(*calls):
    return ChatResult(content="", prompt_tokens=100, completion_tokens=10, total_tokens=110, tool_calls=list(calls))


def answer_call(text, *, figures=(), not_found=(), cid="a1"):
    return asks(
        call(ANSWER, {"text": text, "figures": [dict(f) for f in figures], "not_found": [dict(n) for n in not_found],
                      "not_checked": []}, cid)
    )


class Provider:
    def __init__(self, script):
        self.script = list(script)
        self.seen = []

    def chat(self, messages, *, tools=None, reasoning_effort=None, **kw):
        self.seen.append({"messages": copy.deepcopy(messages), "tools": tools})
        return self.script.pop(0)


def run(db, contact, provider, mcp, text="how is it?"):
    from app.services.chatbot.agent.loop import run_agent_turn

    return run_agent_turn(
        db, contact_respond_id=contact["respond_id"], text=text, provider=provider, mcp_call=mcp, catalog=CATALOG
    )


# ------------------------------------------------------------------ V1


def test_a_figure_inside_the_report_text_is_backed(db, contact):
    envelope = {
        "result_type": "report_ask",
        "response": "Sales, October 2026\nTotal: RM 2,000,000.00",
        "has_result": True,
    }
    provider = Provider(
        [
            asks(call(REPORT, {"query": "x"}, "c1")),
            answer_call("Total sales were RM 2,000,000.00.", figures=[{"value": "2,000,000.00", "call_id": "c1"}]),
        ]
    )
    result = run(db, contact, provider, Mcp(envelope))
    assert result.reply_text == "Total sales were RM 2,000,000.00."
    assert len(provider.seen) == 2


def test_numbers_inside_a_formatted_stock_field_are_backed(db, contact):
    envelope = {"items": [{"fields": [{"key": "total", "label": "Total", "value": "51 (O/S: 36)"}]}], "has_result": True}
    provider = Provider(
        [
            asks(call(STOCK, {"query": "x"}, "c1")),
            answer_call(
                "51 in total, 36 outstanding.",
                figures=[{"value": "51", "call_id": "c1"}, {"value": "36", "call_id": "c1"}],
            ),
        ]
    )
    result = run(db, contact, provider, Mcp(envelope))
    assert result.reply_text == "51 in total, 36 outstanding."


def test_a_uuid_with_digits_backs_nothing(db, contact):
    envelope = {"items": [{"id": "aaaa1234-0000-4000-8000-000000000000", "code": "x"}], "has_result": True}
    text = "There are 1234 units."
    figures = [{"value": "1234", "call_id": "c1"}]
    provider = Provider(
        [asks(call(STOCK, {"query": "x"}, "c1")), answer_call(text, figures=figures),
         answer_call(text, figures=figures, cid="a2")]
    )
    result = run(db, contact, provider, Mcp(envelope))
    assert "(not verified)" in result.reply_text


def test_an_all_digit_uuid_and_a_date_string_back_nothing(db, contact):
    envelope = {"items": [{"id": "12345678-1234-4234-8234-123456789012", "shipped": "on 2026-10-12"}], "has_result": True}
    for number in ("12345678", "12"):
        text = f"There are {number} units."
        figures = [{"value": number, "call_id": "c1"}]
        provider = Provider(
            [asks(call(STOCK, {"query": "x"}, "c1")), answer_call(text, figures=figures),
             answer_call(text, figures=figures, cid="a2")]
        )
        result = run(db, contact, provider, Mcp(envelope))
        assert "(not verified)" in result.reply_text, number


def test_a_key_that_is_a_number_still_backs_nothing(db, contact):
    text = "There are 12 units."
    figures = [{"value": "12", "call_id": "c1"}]
    provider = Provider(
        [asks(call(STOCK, {"query": "x"}, "c1")), answer_call(text, figures=figures),
         answer_call(text, figures=figures, cid="a2")]
    )
    result = run(db, contact, provider, Mcp({"items": [{"12": "label"}], "has_result": True}))
    assert "(not verified)" in result.reply_text


# ------------------------------------------------------------------ V2


@pytest.mark.parametrize(
    "reply",
    [
        "Code SRTWC8357-300-RL is fine",
        "Order SO2610-0127 is open",
        "Packing PS202609-0374 arrived",
        "Document SO-26-00981 is open",
        "See SRTWC8357-300-RL and SO2610-0127 and PS202609-0374 and SO-26-00981",
    ],
)
def test_identifiers_with_digits_are_not_figures(reply):
    from app.services.chatbot.agent.loop import unsupported_figures

    assert unsupported_figures(reply, []) == []


def test_a_plain_range_of_numbers_is_still_checked():
    from app.services.chatbot.agent.loop import unsupported_figures

    assert unsupported_figures("Between 12-15 units", []) == ["12", "15 units"]


def test_only_the_real_figure_is_checked_and_identifiers_stay_intact(db, contact):
    text = "SO2610-0127 has 4 of SRTWC8357-300-RL outstanding"
    provider = Provider(
        [
            asks(call(STOCK, {"query": "x"}, "c1")),
            answer_call(text, figures=[{"value": "4", "call_id": "c1"}]),
        ]
    )
    result = run(db, contact, provider, Mcp({"items": [{"qty": 4}], "has_result": True}))
    assert result.reply_text == text
    assert len(provider.seen) == 2


def test_redaction_leaves_identifiers_alone():
    from app.services.chatbot.agent.loop import _redact_written

    out = _redact_written("SO2610-0127 has 9 of SRTWC8357-300-RL", {"9"})
    assert out == "SO2610-0127 has (not verified) of SRTWC8357-300-RL"


# ------------------------------------------------------------------ S5-1


def _ctx():
    from app.services.chatbot.agent.access import AgentContext

    return AgentContext(
        contact_pk="pk-1", contact_respond_id="ZZT-R5C-1", space_id="364817", user_id="user-1",
        user_name="ZZT User", grants=frozenset(),
    )


def test_a_uuid_seen_in_an_ok_result_is_a_known_id_for_the_next_call(monkeypatch):
    from app.services.chatbot.agent import tools

    monkeypatch.setattr(UserPermissionService, "check_user_has_permission", lambda self, uid, slug: True)
    warehouse = str(uuid.uuid4())
    stranger = str(uuid.uuid4())
    seen: set[str] = set()
    first = Mcp({"items": [{"warehouse_id": warehouse, "qty": 3}], "has_result": True})
    out = tools.dispatch(None, _ctx(), STOCK, {"query": "x"}, call=first, catalog=CATALOG, timeout=5.0, seen_ids=seen)
    assert out.status == "ok"

    again = Mcp({"items": [{"qty": 1}], "has_result": True})
    ok = tools.dispatch(
        None, _ctx(), STOCK, {"warehouse_ids": [warehouse.upper()]}, call=again, catalog=CATALOG, timeout=5.0, seen_ids=seen
    )
    assert ok.status == "ok"
    bad = tools.dispatch(
        None, _ctx(), STOCK, {"warehouse_ids": [stranger]}, call=again, catalog=CATALOG, timeout=5.0, seen_ids=seen
    )
    assert bad.status == "invalid" and "Unknown id" in bad.message


# ------------------------------------------------------------------ M5


def test_the_resolver_body_turns_the_semantic_fallback_off(monkeypatch):
    from app.services.chatbot.agent import tools

    bodies = []

    def factory(db):
        def run_(body):
            bodies.append(dict(body))
            return {"tokens": body["tokens"], "resolutions": []}

        return run_

    monkeypatch.setattr(business_services, "_resolve_entity", factory)
    monkeypatch.setattr(UserPermissionService, "check_user_has_permission", lambda self, uid, slug: True)
    out = tools.dispatch(None, _ctx(), RESOLVE, {"terms": ["X"], "kinds": ["product"]}, call=Mcp({}), catalog={}, timeout=5.0)
    assert out.status == "ok"
    assert bodies[0]["semantic_fallback"] is False


# ------------------------------------------------------------------ low items


def test_a_not_found_claim_is_not_backed_by_a_term_that_only_shares_letters():
    from app.services.chatbot.agent.loop import _not_found_backed

    ledger = {
        "r1": {"name": RESOLVE, "status": "ok", "args": {}, "data": {"results": [
            {"term": "A1-X", "status": "not_found", "matches": []}]}}
    }
    assert _not_found_backed("A", "r1", ledger, set()) is False
    assert _not_found_backed("a1-x", "r1", ledger, set()) is True
    assert _not_found_backed("stock for A1-X", "r1", ledger, set()) is True
    assert _not_found_backed("A1-XL", "r1", ledger, set()) is False


@pytest.mark.parametrize("host", ["localhost:8000", "backend_blue:8000", "mcp:8765"])
def test_clean_detail_strips_host_and_port(host):
    from app.services.chatbot.agent.tools import clean_detail

    out = clean_detail(f"brand_id must be a valid UUID, could not reach {host} just now")
    assert host not in out and "8000" not in out and "8765" not in out
    assert "brand_id must be a valid UUID" in out


def test_uuids_are_removed_from_the_reply(db, contact):
    ident = str(uuid.uuid4())
    provider = Provider([answer_call(f"Warehouse {ident} is empty.")])
    result = run(db, contact, provider, Mcp({"items": [{"qty": 1}], "has_result": True}))
    assert ident not in result.reply_text
    assert "(id)" in result.reply_text
