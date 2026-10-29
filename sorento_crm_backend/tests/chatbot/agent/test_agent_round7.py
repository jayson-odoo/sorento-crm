"""AGENTIC-P1 round 7 (eval run 3 passed 40/45; S1 4/9): red tests.

1 the figure check with the REAL report presenter output and the turn's real call ids, 2 the sales basis
is never defaulted, 3 a refused domain stays refused.
"""
from __future__ import annotations

import json

import pytest

from app.services.user_service import UserPermissionService
from tests._pg_fixture import blank_session
from tests.chatbot.agent._seed import seed_agent_contact
from tests.chatbot.agent.test_agent_round5 import KIND_SLUGS, Provider as _P5  # noqa: F401
from tests.chatbot.agent.test_agent_round6 import (  # noqa: F401
    answer6,
    asks,
    call,
)

REPORT = "crm_report_ask"
BY_PRODUCT = "crm_order_management_orders_by_product_list"
STOCK = "crm_inventory_stock_balance_list"

_PROPS = {
    "contact_id": {"type": "string"},
    "space_id": {"type": "string"},
    "query": {"type": "string"},
    "view": {"type": "string"},
    "basis": {"type": "string"},
    "dataset": {"type": "string"},
    "group_by": {"type": "string"},
}
CATALOG = {
    n: {"description": n, "inputSchema": {"type": "object", "properties": dict(_PROPS), "required": ["contact_id"]}}
    for n in (REPORT, BY_PRODUCT, STOCK)
}


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture()
def contact(db):
    return seed_agent_contact(db, slugs=("inventory.stock.view", "order_management.orders.view"))


class Mcp:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def __call__(self, name, args):
        self.calls.append((name, dict(args)))
        item = self.results[min(len(self.calls) - 1, len(self.results) - 1)]
        return item(name, args) if callable(item) else item


class Provider:
    def __init__(self, script):
        self.script = list(script)
        self.seen = []

    def chat(self, messages, *, tools=None, reasoning_effort=None, **kw):
        import copy

        self.seen.append({"messages": copy.deepcopy(messages), "tools": tools})
        return self.script.pop(0)


def run(db, contact, provider, mcp, text="sales for 2026?"):
    from app.services.chatbot.agent.loop import run_agent_turn

    return run_agent_turn(
        db, contact_respond_id=contact["respond_id"], text=text, provider=provider, mcp_call=mcp, catalog=CATALOG
    )


def _tool_payloads(messages):
    return [json.loads(m["content"]) for m in messages if m.get("role") == "tool"]


# ------------------------------------------------------------------ 1. the real presenter output


def _real_envelope(basis="delivered", scale=1):
    """The backend's report-ask body for ~25 sales agents, through the MCP presenter with view=render.

    The backend CI job does not install `sorento_crm_mcp`, so the package next to this checkout is put
    on `sys.path` (the same way `tests/chatbot/test_field_reveal_keys_pinned_to_catalog.py` reads it)."""
    import sys
    from pathlib import Path

    mcp_root = Path(__file__).resolve().parents[4] / "sorento_crm_mcp"
    if str(mcp_root) not in sys.path:
        sys.path.append(str(mcp_root))
    from sorento_crm_mcp.presenters import present_response

    names = ["FANNY I", "YMH I", "LONG I"] + [f"AGENT {chr(65 + i)} I" for i in range(22)]
    qtys = [51 * scale, 48 * scale, 30 * scale] + [20 - i // 2 for i in range(22)]
    rows = [
        {"rank": i + 1, "name": n, "keys": [f"k{i}"], "qty": q, "amount": q * 123.45}
        for i, (n, q) in enumerate(zip(names, qtys))
    ]
    body = {
        "status": "ok", "dataset": "sales", "basis": basis, "basis_label": basis, "group_by": "sales_agent",
        "group_label": "Sales agent", "measure": "qty", "sort": "desc", "date_from": "2026-01-01",
        "date_to": "2026-10-30", "filters": [], "rows": rows, "total_count": 25, "more": 0,
        "total": {"qty": 2822 * scale, "amount": 2822 * 123.45},
    }
    return json.loads(present_response(REPORT, json.dumps(body)))


REPLY = "Delivered 2,822 in 2026; FANNY I 51, YMH I 48, LONG I 30"


def test_the_real_presenter_output_backs_the_four_figures_through_dispatch():
    from app.services.chatbot.agent import tools
    from app.services.chatbot.agent.access import AgentContext
    from app.services.chatbot.agent.loop import verify_answer

    held = UserPermissionService.check_user_has_permission
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: True
    try:
        ctx = AgentContext(contact_pk="pk", contact_respond_id="ZZT-R7", space_id="1", user_id="u", user_name="n", grants=frozenset())
        env = _real_envelope()
        out = tools.dispatch(None, ctx, REPORT, {"basis": "delivered"}, call=lambda n, a: env, catalog=CATALOG, timeout=5.0)
    finally:
        UserPermissionService.check_user_has_permission = held
    assert out.status == "ok"
    ledger = {"c1": {"name": REPORT, "status": out.status, "args": {}, "data": out.data}}
    assert verify_answer({"text": REPLY}, ledger, "sales for 2026?") == ([], [])


def test_the_real_report_through_a_turn_keeps_the_reply(db, contact):
    provider = Provider(
        [asks(call(REPORT, {"basis": "delivered", "group_by": "sales_agent"}, "c1")), answer6(REPLY)]
    )
    result = run(db, contact, provider, Mcp(_real_envelope()))
    assert result.reply_text == REPLY
    assert len(provider.seen) == 2


def test_the_same_call_id_in_two_rounds_does_not_lose_the_first_result(db, contact):
    """Gemini names a call `gemini_<index>_<tool>`, so the same tool in two rounds repeats the id."""
    same = "gemini_0_crm_report_ask"
    provider = Provider(
        [
            asks(call(REPORT, {"basis": "delivered", "group_by": "sales_agent"}, same)),
            asks(call(REPORT, {"basis": "invoiced", "group_by": "customer"}, same)),
            answer6(REPLY),
        ]
    )
    other = {"result_type": "report_ask", "response": "Top 1 customers by invoiced\n1. ACME 7 pcs, RM 1.00", "has_result": True}
    result = run(db, contact, provider, Mcp(_real_envelope(), other))
    assert result.reply_text == REPLY, result.reply_text
    ids = [p["call_id"] for p in _tool_payloads(provider.seen[2]["messages"])]
    assert len(ids) == len(set(ids)) == 2


def test_a_result_the_cap_cut_is_verified_against_what_the_model_saw(db, contact):
    from app.services.chatbot.agent.tools import RESULT_CHAR_CAP

    rows = [{"qty": 1, "name": f"row {i}", "note": "x" * 300} for i in range(200)]
    provider = Provider(
        [asks(call(STOCK, {"query": "x"}, "c1")), answer6("There are 777 units."), answer6("There are 777 units.", cid="a2")]
    )
    result = run(db, contact, provider, Mcp({"items": rows + [{"qty": 777}], "has_result": True}))
    shown = _tool_payloads(provider.seen[1]["messages"])[0]
    assert len(json.dumps(shown["data"])) <= RESULT_CHAR_CAP
    # 777 sat in a row the model was never shown, so it cannot be backed
    assert "(not verified)" in result.reply_text


@pytest.mark.parametrize("key", ["display", "label", "title", "name"])
def test_a_figure_in_a_name_like_field_is_not_used_but_the_response_text_is(db, contact, key):
    env = {"result_type": "report_ask", "response": "1. FANNY I 51 pcs, RM 6,295.95", "has_result": True,
           key: "FANNY I: 99 pcs"}
    provider = Provider(
        [asks(call(REPORT, {"basis": "delivered"}, "c1")), answer6("FANNY I 51 pcs"), answer6("FANNY I 51 pcs", cid="a2")]
    )
    assert run(db, contact, provider, Mcp(env)).reply_text == "FANNY I 51 pcs"


# ------------------------------------------------------------------ 2. the sales basis


def _ctx():
    from app.services.chatbot.agent.access import AgentContext

    return AgentContext(contact_pk="pk", contact_respond_id="ZZT-R7", space_id="1", user_id="u", user_name="n", grants=frozenset())


@pytest.fixture()
def allowed(monkeypatch):
    monkeypatch.setattr(UserPermissionService, "check_user_has_permission", lambda self, uid, slug: True)
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())


def _dispatch(name, args, rec, **kw):
    from app.services.chatbot.agent import tools

    return tools.dispatch(None, kw.pop("ctx", None) or _ctx(), name, args, call=rec, catalog=CATALOG, timeout=5.0, **kw)


class Rec:
    def __init__(self, result=None):
        self.result = result or {"result_type": "report_ask", "response": "Total 5 pcs", "has_result": True}
        self.calls = []

    def __call__(self, name, args):
        self.calls.append((name, dict(args)))
        return self.result


BASIS_MESSAGE = (
    "Say which sales basis: ask the user (invoiced is the usual one) or call once per basis "
    "(invoiced, delivered, ordered) and label each."
)


@pytest.mark.parametrize("args", [{}, {"group_by": "sales_agent"}, {"basis": ""}, {"basis": "  "}, {"basis": None}, {"dataset": "sales"}])
def test_a_sales_ask_without_a_basis_is_invalid(allowed, args):
    rec = Rec()
    out = _dispatch(REPORT, args, rec)
    assert out.status == "invalid" and out.message == BASIS_MESSAGE
    assert rec.calls == []


@pytest.mark.parametrize("basis", ["invoiced", "delivered", "ordered", "outstanding", "pending_delivery"])
def test_an_explicit_basis_passes(allowed, basis):
    assert _dispatch(REPORT, {"basis": basis}, Rec()).status == "ok"


def test_unpaid_and_the_chat_dataset_need_no_sales_basis(allowed):
    ctx = _ctx()
    from dataclasses import replace

    ctx = replace(ctx, grants=frozenset({"chatbot.analytics"}))
    assert _dispatch(REPORT, {"basis": "unpaid"}, Rec(), ctx=ctx).status == "ok"
    assert _dispatch(REPORT, {"dataset": "chat"}, Rec(), ctx=ctx).status == "ok"


def test_the_prompt_never_defaults_the_basis():
    from app.services.ai_prompt_registry import _chatbot_agent_fallback

    low = _chatbot_agent_fallback().lower()
    assert "basis" in low and "invoiced" in low
    assert "labelled" in low or "labeled" in low
    assert "0 sold" in low or "no sales" in low


# ------------------------------------------------------------------ 3. refused stays refused


DENIED_TAIL = "Do not get this information another way."


def test_a_permission_denial_tells_the_model_not_to_go_around(monkeypatch):
    monkeypatch.setattr(UserPermissionService, "check_user_has_permission", lambda self, uid, slug: False)
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    out = _dispatch(REPORT, {"basis": "invoiced"}, Rec())
    assert out.status == "denied" and DENIED_TAIL in out.message


def test_a_route_403_is_a_denial_and_closes_the_sales_domain(allowed):
    refusal = {"status_code": 403, "detail": "Sales report is not enabled for your account.", "error": "GET x returned HTTP 403"}
    domains: set[str] = set()
    out = _dispatch(REPORT, {"basis": "delivered"}, Rec(refusal), denied_domains=domains)
    assert out.status == "denied" and DENIED_TAIL in out.message
    assert "Sales report is not enabled" in out.message
    again = Rec()
    out = _dispatch(BY_PRODUCT, {"query": "x"}, again, denied_domains=domains)
    assert out.status == "denied" and DENIED_TAIL in out.message
    assert again.calls == []
    # another domain is untouched
    assert _dispatch(STOCK, {"query": "x"}, Rec({"items": [{"qty": 1}], "has_result": True}), denied_domains=domains).status == "ok"


def test_outstanding_and_the_chat_dataset_are_their_own_domains(allowed):
    domains: set[str] = set()
    refusal = {"status_code": 403, "detail": "Outstanding is not enabled for your account.", "error": "GET x returned HTTP 403"}
    assert _dispatch(REPORT, {"basis": "unpaid"}, Rec(refusal), denied_domains=domains).status == "denied"
    # a sales ask is a different domain from receivables
    assert _dispatch(REPORT, {"basis": "invoiced"}, Rec(), denied_domains=domains).status == "ok"


def test_the_turn_keeps_the_denied_domain_across_rounds(db, contact):
    refusal = {"status_code": 403, "detail": "Sales report is not enabled for your account.", "error": "GET x returned HTTP 403"}
    ok = {"items": [{"qty": 1}], "has_result": True}
    mcp = Mcp(refusal, ok)
    provider = Provider(
        [
            asks(call(REPORT, {"basis": "delivered"}, "c1")),
            asks(call(BY_PRODUCT, {"query": "x"}, "c2")),
            answer6("I cannot read that."),
        ]
    )
    result = run(db, contact, provider, mcp)
    assert [c[0] for c in mcp.calls] == [REPORT]  # the second tool never ran
    payloads = _tool_payloads(provider.seen[2]["messages"])
    assert [p["status"] for p in payloads] == ["denied", "denied"]
    assert all(DENIED_TAIL in p["message"] for p in payloads)
    assert result.status == "answered"
