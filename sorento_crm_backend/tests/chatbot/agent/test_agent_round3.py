"""AGENTIC-P1 round 3: fixes from the security and code reviews (red first).

Groups: B1 (restricted fields must not reach the model), H1/H2 (contact grants and argument
level permissions), H3 (conversation routes), M1 to M3, L1, S1, S2 and the nits.
"""
from __future__ import annotations

import copy
import json
import threading

import pytest
from sqlalchemy import text

from app.models.chatbot_turn import ChatbotTurn
from app.models.user import SystemSetting
from app.services.chatbot.lanes.business.fetch import ToolNotAllowed  # noqa: F401
from app.services.llm_provider import ChatResult
from app.services.user_service import UserPermissionService
from tests._pg_fixture import blank_session, unique_code
from tests.chatbot.agent._seed import seed_agent_contact, seed_contact, seed_user
from tests.chatbot.agent._turns import seed_turn

STOCK = "crm_inventory_stock_balance_list"
REPORT = "crm_report_ask"
COST = "crm_procurement_po_last_cost_list"

_HELD: set[str] = set()


def _catalog(*names, extra_props=None):
    props = {
        "contact_id": {"type": "string"},
        "space_id": {"type": "string"},
        "query": {"type": "string"},
        "view": {"type": "string"},
        "include_sellable": {"type": "boolean"},
        "basis": {"type": "string"},
        "dataset": {"type": "string"},
    }
    props.update(extra_props or {})
    return {
        n: {"description": n, "inputSchema": {"type": "object", "properties": dict(props), "required": ["contact_id", "view"]}}
        for n in names
    }


ALL_TOOLS = (
    "crm_report_ask", "crm_inventory_stock_balance_list", "crm_incoming_stock_by_product",
    "crm_incoming_stock_shipments", "crm_procurement_grn_summary", "crm_procurement_po_last_cost_list",
    "crm_procurement_po_placed_list", "crm_procurement_spo_allocations_last_receipt_list",
    "crm_order_management_orders_by_product_list", "crm_lookup_resolve",
)
CATALOG = _catalog(*ALL_TOOLS)


@pytest.fixture()
def held(monkeypatch):
    """The linked user holds exactly what is put in `_HELD`."""
    _HELD.clear()
    monkeypatch.setattr(
        UserPermissionService, "check_user_has_permission", lambda self, uid, slug: slug in _HELD
    )
    monkeypatch.setattr(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
    yield _HELD
    _HELD.clear()


def _ctx(grants=(), stock_allowed=True):
    from app.services.chatbot.agent.access import AgentContext

    return AgentContext(
        contact_pk="pk-1", contact_respond_id="ZZT-R-1", space_id="364817", user_id="user-1",
        user_name="ZZT User", grants=frozenset(grants), stock_allowed=stock_allowed,
    )


class Rec:
    def __init__(self, result=None, exc=None):
        self.result = {"items": [], "has_result": True} if result is None else result
        self.exc = exc
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, name, args):
        self.calls.append((name, dict(args)))
        if self.exc:
            raise self.exc
        return self.result


def _dispatch(name, args, rec, ctx=None, catalog=None):
    from app.services.chatbot.agent import tools

    return tools.dispatch(None, ctx or _ctx(), name, args, call=rec, catalog=catalog or CATALOG, timeout=5.0)


# ------------------------------------------------------------------ B1


def test_view_render_is_always_sent_and_not_model_controllable(held):
    held.update({"inventory.stock.view"})
    rec = Rec()
    out = _dispatch(STOCK, {"query": "x", "view": "raw"}, rec)
    assert out.status == "ok"
    assert rec.calls[0][1]["view"] == "render"
    rec2 = Rec()
    _dispatch(STOCK, {"query": "x"}, rec2)
    assert rec2.calls[0][1]["view"] == "render"


def test_view_is_not_in_the_model_facing_schema():
    from app.services.chatbot.agent.tools import REGISTRY, tool_schemas

    params = tool_schemas([REGISTRY[STOCK]], CATALOG)[0]["function"]["parameters"]
    assert "view" not in params["properties"]
    assert "view" not in params["required"]


def test_a_raw_shape_result_is_an_error_and_nothing_leaks(held):
    held.update({"scm.purchase_orders.view"})
    rec = Rec(result={"data": [{"supplier": "ZZT SECRET SUPPLIER", "unit_cost": 1}]})
    out = _dispatch("crm_procurement_po_placed_list", {"query": "x"}, rec, ctx=_ctx({"purchase_orders.placed"}))
    assert out.status == "error"
    assert out.data is None
    assert "ZZT SECRET SUPPLIER" not in json.dumps(out.__dict__, default=str)


def test_a_non_dict_result_is_an_error(held):
    held.update({"inventory.stock.view"})
    out = _dispatch(STOCK, {"query": "x"}, Rec(result=["a", "b"]))
    assert out.status == "error" and out.data is None


def test_include_sellable_is_stripped_without_the_grant_and_kept_with_it(held):
    held.update({"inventory.stock.view"})
    rec = Rec()
    _dispatch(STOCK, {"query": "x", "include_sellable": True}, rec, ctx=_ctx())
    assert "include_sellable" not in rec.calls[0][1]
    rec2 = Rec()
    _dispatch(STOCK, {"query": "x", "include_sellable": True}, rec2, ctx=_ctx({"inventory.sellable"}))
    assert rec2.calls[0][1]["include_sellable"] is True


# ------------------------------------------------------------------ H1


EXPECTED_GRANTS = {
    "crm_report_ask": None,
    "crm_inventory_stock_balance_list": None,
    "crm_incoming_stock_by_product": None,
    "crm_incoming_stock_shipments": None,
    "crm_procurement_grn_summary": "purchase_orders.placed",
    "crm_procurement_po_last_cost_list": "purchase_orders.cost",
    "crm_procurement_po_placed_list": "purchase_orders.placed",
    "crm_procurement_spo_allocations_last_receipt_list": "purchase_orders.placed",
    "crm_order_management_orders_by_product_list": None,
    "crm_lookup_resolve": None,
}


def test_registry_carries_the_contact_grants():
    from app.services.chatbot.agent.tools import REGISTRY

    assert {n: d.contact_grant for n, d in REGISTRY.items()} == EXPECTED_GRANTS


def test_dispatch_denies_a_tool_whose_contact_grant_is_missing(held):
    held.update({"scm.purchase_orders.view"})
    rec = Rec()
    out = _dispatch(COST, {"query": "x"}, rec, ctx=_ctx())
    assert out.status == "denied" and rec.calls == []
    out = _dispatch(COST, {"query": "x"}, rec, ctx=_ctx({"purchase_orders.cost"}))
    assert out.status == "ok"


def test_dispatch_denies_stock_when_the_contact_may_not_check_stock(held):
    held.update({"inventory.stock.view"})
    rec = Rec()
    assert _dispatch(STOCK, {"query": "x"}, rec, ctx=_ctx(stock_allowed=False)).status == "denied"
    assert rec.calls == []


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def test_permitted_tools_needs_the_contact_grant_too(db, held, monkeypatch):
    from app.services.chatbot.agent.access import build_context, permitted_tools

    held.update({"scm.purchase_orders.view", "procurement.grn.view"})
    contact = seed_contact(db)
    seed_user(db, contact_pk=contact["pk"])
    monkeypatch.setattr("app.services.contact_field_reveal_service.granted_keys", lambda d, c: [])
    ctx = build_context(db, contact["respond_id"])
    assert permitted_tools(db, ctx) == []

    monkeypatch.setattr(
        "app.services.contact_field_reveal_service.granted_keys", lambda d, c: ["purchase_orders.placed"]
    )
    ctx = build_context(db, contact["respond_id"])
    assert {t.name for t in permitted_tools(db, ctx)} == {
        "crm_procurement_po_placed_list", "crm_procurement_grn_summary",
    }


def test_a_contact_that_may_not_check_stock_is_not_offered_the_stock_tool(db, held):
    from app.services.chatbot.agent.access import build_context, permitted_tools

    held.update({"inventory.stock.view"})
    contact = seed_contact(db)
    seed_user(db, contact_pk=contact["pk"])
    db.execute(text("UPDATE respond_contacts SET chatbot_stock_allowed = false WHERE id = :i"), {"i": contact["pk"]})
    db.flush()
    ctx = build_context(db, contact["respond_id"])
    assert ctx.stock_allowed is False
    assert permitted_tools(db, ctx) == []


# ------------------------------------------------------------------ H2


def test_unpaid_basis_needs_the_billing_documents_permission(held):
    held.update({"order_management.orders.view"})
    rec = Rec()
    assert _dispatch(REPORT, {"basis": "unpaid"}, rec).status == "denied"
    assert _dispatch(REPORT, {"basis": " Unpaid "}, rec).status == "denied"
    assert rec.calls == []
    held.add("finance.billing_documents.view")
    assert _dispatch(REPORT, {"basis": "unpaid"}, rec).status == "ok"


def test_chat_dataset_needs_the_analytics_permission_and_the_contact_reveal(held):
    held.update({"order_management.orders.view"})
    rec = Rec()
    assert _dispatch(REPORT, {"dataset": "chat"}, rec, ctx=_ctx({"chatbot.analytics"})).status == "denied"
    held.add("chatbot.analytics.view")
    assert _dispatch(REPORT, {"dataset": "chat"}, rec, ctx=_ctx()).status == "denied"
    assert rec.calls == []
    assert _dispatch(REPORT, {"dataset": "chat"}, rec, ctx=_ctx({"chatbot.analytics"})).status == "ok"


def test_a_plain_sales_report_needs_neither(held):
    held.update({"order_management.orders.view"})
    assert _dispatch(REPORT, {"basis": "invoiced"}, Rec()).status == "ok"


# ------------------------------------------------------------------ S1 figure check


@pytest.mark.parametrize(
    "reply, sources, expected",
    [
        ("Total RM1,234.50 today", ["1234.5"], []),
        ("Total RM1,234.50 today", ["99"], ["RM1,234.50"]),
        ("There are 12pcs left", ["12"], []),
        ("There are 12pcs left", ["99"], ["12pcs"]),
        ("Ordered 3x", ["3"], []),
        ("Ordered 3x", ["4"], ["3x"]),
        ("Growth is 45%", ["45"], []),
        ("Growth is 45%", ["40"], ["45%"]),
        ("Code SRTWT7445 is fine", [], []),
        ("Code MWT5727SS-CR is fine", [], []),
        ("On 2026-10-29 only", [], []),
        ("USD 500 and 7", ["500"], ["7"]),
    ],
)
def test_figure_check_units_codes_and_dates(reply, sources, expected):
    from app.services.chatbot.agent.loop import unsupported_figures

    assert sorted(unsupported_figures(reply, sources)) == sorted(expected)


def test_redaction_uses_the_same_masks():
    from app.services.chatbot.agent.loop import _redact

    out = _redact("SRTWT7445 has 99pcs on 2026-10-29", ["12"])
    assert out == "SRTWT7445 has (not verified) on 2026-10-29"


# ------------------------------------------------------------------ loop helpers


def answer(txt, prompt=100):
    return ChatResult(content=txt, prompt_tokens=prompt, completion_tokens=10, total_tokens=prompt + 10)


def asks(*calls, prompt=100):
    return ChatResult(content="", prompt_tokens=prompt, completion_tokens=10, total_tokens=prompt + 10, tool_calls=list(calls))


def call(name=STOCK, args=None, cid="c1"):
    return {"id": cid, "name": name, "arguments": {"query": "SRTWT7445"} if args is None else args}


class Prov:
    def __init__(self, script, on_call=None):
        self.script = list(script)
        self.seen: list[dict] = []
        self.on_call = on_call

    def chat(self, messages, *, tools=None, reasoning_effort=None, **kw):
        self.seen.append({"messages": copy.deepcopy(messages), "tools": tools, "kw": kw})
        if self.on_call:
            self.on_call(len(self.seen))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class Mcp:
    def __init__(self, result=None):
        self.result = {"items": [{"qty": 12}], "has_result": True} if result is None else result
        self.calls = []

    def __call__(self, name, args):
        self.calls.append((name, dict(args)))
        return self.result


@pytest.fixture()
def contact(db):
    return seed_agent_contact(db)


def run(db, contact, provider, mcp=None, text_="stock?", **kw):
    from app.services.chatbot.agent.loop import run_agent_turn

    return run_agent_turn(
        db, contact_respond_id=contact["respond_id"], text=text_, provider=provider,
        mcp_call=mcp or Mcp(), catalog=_catalog(STOCK), **kw,
    )


def _row(db, result):
    return db.query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).one()


# ------------------------------------------------------------------ M1


def test_the_final_call_gets_a_small_grace_and_compaction_is_skipped_when_time_is_gone(db, contact):
    clock = {"t": 0.0}
    prov = Prov(
        [asks(call()), answer("Partial answer.")],
        on_call=lambda n: clock.__setitem__("t", clock["t"] + 100.0) if n == 1 else None,
    )
    result = run(db, contact, prov, clock=lambda: clock["t"])
    assert result.limit_hit == "seconds"
    assert prov.seen[-1]["kw"]["timeout"] == 10
    assert prov.seen[0]["kw"]["timeout"] <= 45


def test_a_repair_call_cannot_outlast_the_turn(db, contact):
    clock = {"t": 0.0}
    prov = Prov(
        [asks(call()), answer("There are 99 units."), answer("Fine.")],
        on_call=lambda n: clock.__setitem__("t", clock["t"] + 20.0),
    )
    result = run(db, contact, prov, clock=lambda: clock["t"])
    # 60 s used of 45: the repair round is skipped and the figure is redacted
    assert len(prov.seen) == 2
    assert "99" not in result.reply_text and "(not verified)" in result.reply_text


def test_a_second_turn_for_the_same_contact_is_busy(db, contact):
    from app.database import engine
    from app.services.chatbot.agent.loop import AgentBusy

    holder = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        holder.execute(
            text("SELECT pg_advisory_lock(hashtext(:k))"), {"k": f"agent:{contact['respond_id']}"}
        )
        with pytest.raises(AgentBusy):
            run(db, contact, Prov([answer("hi")]))
    finally:
        holder.execute(
            text("SELECT pg_advisory_unlock(hashtext(:k))"), {"k": f"agent:{contact['respond_id']}"}
        )
        holder.close()


def test_the_lock_is_released_after_a_turn(db, contact):
    run(db, contact, Prov([answer("hi")]))
    run(db, contact, Prov([answer("hi again")]))


def test_the_catalogue_is_cached_between_turns():
    from app.services.chatbot.agent import loop

    calls = []
    clock = {"t": 0.0}
    fetch = lambda: calls.append(1) or {"a": {}}  # noqa: E731
    loop.catalog_cached(fetch, now=lambda: clock["t"], key="t1")
    loop.catalog_cached(fetch, now=lambda: clock["t"], key="t1")
    assert len(calls) == 1
    clock["t"] = 301
    loop.catalog_cached(fetch, now=lambda: clock["t"], key="t1")
    assert len(calls) == 2


# ------------------------------------------------------------------ M2


def test_extra_calls_leave_one_note_in_digest_and_trace(db, contact):
    six = [call(cid=f"c{i}", args={"query": f"q{i}"}) for i in range(6)]
    prov = Prov([asks(*six), answer("There are 12 units.")])
    result = run(db, contact, prov)
    row = _row(db, result)
    digest = row.response["tool_digest"]
    assert len(digest) == 5
    assert digest[-1]["status"] == "denied"
    tools_traced = [e for e in row.trace if e.get("kind") == "agent_tool"]
    assert len(tools_traced) == 5
    assert len(result.tool_calls) == 5
    # the provider protocol still gets one tool message per requested call
    assert len([m for m in prov.seen[1]["messages"] if m["role"] == "tool"]) == 6


def test_long_arguments_are_clipped_in_digest_and_trace(db, contact):
    big = {"query": "x" * 5000}
    prov = Prov([asks(call(args=big)), answer("There are 12 units.")])
    result = run(db, contact, prov)
    row = _row(db, result)
    assert len(json.dumps(row.response["tool_digest"][0]["args"])) <= 600
    traced = [e for e in row.trace if e.get("kind") == "agent_tool"][0]
    assert len(json.dumps(traced["args"])) <= 600


# ------------------------------------------------------------------ M3


def test_a_change_of_user_or_grants_starts_a_new_conversation(db):
    from app.services.chatbot.agent import memory

    rid = unique_code("m3")
    a = memory.current_conversation(db, rid, user_id="u1", grants_hash="h1")
    assert a.user_id == "u1" and a.grants_hash == "h1"
    assert memory.current_conversation(db, rid, user_id="u1", grants_hash="h1").id == a.id
    b = memory.current_conversation(db, rid, user_id="u1", grants_hash="h2")
    assert b.id != a.id
    c = memory.current_conversation(db, rid, user_id="u2", grants_hash="h2")
    assert c.id != b.id


def test_grants_hash_is_stable_and_order_free():
    from app.services.chatbot.agent.access import grants_hash

    assert grants_hash(_ctx({"a", "b"})) == grants_hash(_ctx({"b", "a"}))
    assert grants_hash(_ctx({"a"})) != grants_hash(_ctx({"b"}))
    assert len(grants_hash(_ctx())) == 64


def test_a_grant_change_between_turns_hides_the_old_history(db, contact, monkeypatch):
    run(db, contact, Prov([answer("Hello there.")]), text_="first question")
    monkeypatch.setattr(
        "app.services.contact_field_reveal_service.granted_keys", lambda d, c: ["purchase_orders.cost"]
    )
    second = Prov([answer("Fresh.")])
    run(db, contact, second, text_="second question")
    contents = [m["content"] for m in second.seen[0]["messages"] if isinstance(m.get("content"), str)]
    assert "first question" not in contents


# ------------------------------------------------------------------ L1 / S2 / nits


def test_a_tool_failure_reaches_the_model_as_a_fixed_message(db, contact):
    class Boom(Mcp):
        def __call__(self, name, args):
            raise RuntimeError("secret internal host db-prod-7 refused")

    prov = Prov([asks(call()), answer("It failed.")])
    run(db, contact, prov, Boom())
    tool_msg = [m for m in prov.seen[1]["messages"] if m["role"] == "tool"][0]["content"]
    assert "db-prod-7" not in tool_msg
    assert "the tool failed" in tool_msg.lower()


def test_a_provider_failure_reply_is_fixed(db, contact):
    result = run(db, contact, Prov([RuntimeError("401 key sk-LEAK123 rejected")]))
    assert result.status == "failed"
    assert "sk-LEAK123" not in result.reply_text
    assert result.reply_text == "The agent could not answer: the model provider failed."
    assert "sk-LEAK123" not in (_row(db, result).error or "")


def test_a_failure_while_building_context_marks_the_row_failed_not_processing(db, contact, monkeypatch):
    from app.services.chatbot.agent import memory

    def boom(*a, **k):
        raise RuntimeError("history broke")

    monkeypatch.setattr(memory, "history_messages", boom)
    result = run(db, contact, Prov([answer("never")]))
    assert result.status == "failed"
    assert _row(db, result).status == "failed"


def test_usage_rows_of_a_failed_turn_are_not_answered(db, contact):
    from app.models.ai_assistant import AIAssistantUsageLog

    result = run(db, contact, Prov([asks(call()), RuntimeError("a"), RuntimeError("b")]))
    assert result.status == "failed"
    rows = db.query(AIAssistantUsageLog).filter(AIAssistantUsageLog.chatbot_turn_id == result.turn_id).all()
    assert rows and all(r.was_answered is False for r in rows)


def test_the_operator_is_recorded_on_the_turn(db, contact):
    result = run(db, contact, Prov([answer("hi")]), operator_user_id="op-1")
    assert _row(db, result).envelope["operator_user_id"] == "op-1"
    assert _row(db, result).response["rounds"] == 1


# ------------------------------------------------------------------ round 4: N1 render flag


LOOKUP = "crm_lookup_resolve"
GRN = "crm_procurement_grn_summary"


def test_only_lookup_and_grn_are_not_render_tools():
    from app.services.chatbot.agent.tools import REGISTRY

    assert {n for n, d in REGISTRY.items() if not d.render} == {LOOKUP, GRN}


def test_lookup_resolve_real_raw_shape_is_ok_and_gets_no_view(held):
    held.update({"master_data.products.view"})
    raw = {"value": "SRT", "label": "Sorento", "matched_keyword": None, "match_type": "exact_value", "score": 1.0}
    rec = Rec(result=raw)
    out = _dispatch(LOOKUP, {"query": "sorento"}, rec)
    assert out.status == "ok"
    assert out.data == raw
    assert "view" not in rec.calls[0][1]
    assert rec.calls[0][1]["contact_id"] == "ZZT-R-1"


def test_lookup_resolve_ignores_a_model_supplied_view(held):
    held.update({"master_data.products.view"})
    rec = Rec(result={"value": "a", "label": "b", "matched_keyword": None, "match_type": "normalized", "score": 0.5})
    _dispatch(LOOKUP, {"query": "x", "view": "render"}, rec)
    assert "view" not in rec.calls[0][1]


def test_grn_summary_real_raw_shape_is_ok(held):
    held.update({"procurement.grn.view"})
    raw = {"data": [{"product_id": "p1", "product_code": "SRTWT7445", "received_qty": 3}], "empty": False}
    out = _dispatch(GRN, {"query": "x"}, Rec(result=raw), ctx=_ctx({"purchase_orders.placed"}))
    assert out.status == "ok"
    assert out.data["data"][0]["received_qty"] == 3


# ------------------------------------------------------------------ round 4: N2 argument shapes


BAD_SHAPES = [["unpaid"], '["unpaid"]', ["invoiced", "unpaid"], {"v": "unpaid"}, '{"v": "unpaid"}', 5, True]


@pytest.mark.parametrize("bad", BAD_SHAPES)
@pytest.mark.parametrize("key", ["basis", "dataset"])
def test_a_gated_argument_that_is_not_a_plain_string_is_invalid(held, key, bad):
    held.update({"order_management.orders.view"})
    rec = Rec()
    out = _dispatch(REPORT, {key: bad}, rec, ctx=_ctx())
    assert out.status == "invalid"
    assert rec.calls == []


def test_a_null_gated_argument_is_treated_as_absent(held):
    held.update({"order_management.orders.view"})
    rec = Rec()
    out = _dispatch(REPORT, {"basis": None, "dataset": None}, rec)
    assert out.status == "ok"
    assert "basis" not in rec.calls[0][1] and "dataset" not in rec.calls[0][1]


# ------------------------------------------------------------------ round 4: M3 residual


def test_grants_hash_covers_the_tool_set_and_the_brand_scope():
    import dataclasses

    from app.services.chatbot.agent.access import grants_hash

    base = _ctx({"a"})
    assert grants_hash(dataclasses.replace(base, tool_names=("x",))) != grants_hash(base)
    assert grants_hash(dataclasses.replace(base, brand_scope=frozenset({"b1"}))) != grants_hash(base)
    assert grants_hash(dataclasses.replace(base, brand_scope=frozenset({"b1"}))) != grants_hash(
        dataclasses.replace(base, brand_scope=frozenset({"b1", "b2"}))
    )
    same = dataclasses.replace(base, tool_names=("x", "y"))
    assert grants_hash(same) == grants_hash(dataclasses.replace(base, tool_names=("x", "y")))


def test_build_context_carries_the_permitted_tool_names(db, held):
    from app.services.chatbot.agent.access import build_context

    held.update({"inventory.stock.view"})
    contact = seed_contact(db)
    seed_user(db, contact_pk=contact["pk"])
    ctx = build_context(db, contact["respond_id"])
    assert ctx.tool_names == (STOCK,)


def test_losing_a_user_permission_starts_a_new_conversation(db, contact, held):
    held.update({"inventory.stock.view"})
    run(db, contact, Prov([answer("Hello there.")]), text_="first question")
    held.clear()
    held.update({"order_management.orders.view"})
    second = Prov([answer("Fresh.")])
    run(db, contact, second, text_="second question")
    contents = [m["content"] for m in second.seen[0]["messages"] if isinstance(m.get("content"), str)]
    assert "first question" not in contents


def test_grants_hash_covers_the_argument_level_permissions():
    import dataclasses

    from app.services.chatbot.agent.access import grants_hash

    base = _ctx({"a"})
    held = dataclasses.replace(base, arg_permissions=("finance.billing_documents.view",))
    assert grants_hash(held) != grants_hash(base)


def test_build_context_carries_the_held_argument_permissions(db, held):
    from app.services.chatbot.agent.access import build_context

    held.update({"order_management.orders.view", "finance.billing_documents.view"})
    contact = seed_contact(db)
    seed_user(db, contact_pk=contact["pk"])
    ctx = build_context(db, contact["respond_id"])
    assert ctx.arg_permissions == ("finance.billing_documents.view",)


def test_the_production_client_calls_the_model_through_llm_call(monkeypatch):
    """The chatbot package's one model wrapper (`llm_call.chat`) carries every agent call."""
    from app.services.chatbot import llm_call
    from app.services.chatbot.agent import loop

    seen = {}

    def fake_chat(provider, api_key, model, messages, *, deadline_seconds, **kwargs):
        seen.update(provider=provider, model=model, deadline=deadline_seconds, kwargs=kwargs)
        return "ok"

    monkeypatch.setattr(llm_call, "chat", fake_chat)
    client = loop._WrappedProvider("gemini", "k-1", "gemini-3.5-flash")
    assert client.chat([{"role": "user", "content": "hi"}], tools=None, reasoning_effort="low", timeout=7) == "ok"
    assert seen["provider"] == "gemini" and seen["model"] == "gemini-3.5-flash"
    assert seen["deadline"] == 7 and seen["kwargs"]["timeout"] == 7
    assert seen["kwargs"]["reasoning_effort"] == "low"
