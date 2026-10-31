"""AGENTIC-KNOWLEDGE P2 W1, slice S1: the contact principal (UAC AC-W1 .. AC-W10).

Red tests, written before the coder touches `agent/access.py`, `agent/tools.py`,
`agent/writes.py`, `agent/loop.py` or `chatbot/router.py`. A contact with the Agent switch on and
no active linked user runs as itself: `principal == "contact"`, no user id, and the tools it may
see are decided by `tools.CONTACT_TOOLS` (tool -> reveal key it must hold, None = open), never by
a user slug. Postgres only, through the blank schema; every test seeds its own chain.
"""
from __future__ import annotations

import pytest

from tests._pg_fixture import blank_session, unique_code
from tests.chatbot.agent._seed import seed_contact, seed_user

#: The plan's S1 table, spelled out so a drift in `CONTACT_TOOLS` fails here.
PLAN_TABLE: dict[str, str | None] = {
    "crm_knowledge_search": None,
    "crm_products_find": None,
    "crm_resolve": None,
    "crm_inventory_stock_balance_list": "inventory.sellable",
    "crm_incoming_stock_by_product": None,
    "crm_incoming_stock_shipments": None,
    "crm_procurement_po_placed_list": "purchase_orders.placed",
    "crm_procurement_grn_summary": "purchase_orders.placed",
    "crm_procurement_spo_allocations_last_receipt_list": "purchase_orders.placed",
    "crm_procurement_po_last_cost_list": "purchase_orders.cost",
    "crm_report_ask": "sales_orders.sales_report",
    "crm_order_management_orders_by_product_list": "sales_orders.sales_report",
}
OPEN_TOOLS = {n for n, k in PLAN_TABLE.items() if k is None}
ALL_KEYS = frozenset(k for k in PLAN_TABLE.values() if k)


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def forbidden_call(name, args):
    raise AssertionError(f"the MCP `call` must not be reached for {name}")


class Recorder:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, name, args):
        self.calls.append((name, dict(args)))
        return {"items": [{"title": "a row"}]}


def _catalog(*names: str) -> dict:
    schema = {
        "type": "object",
        "properties": {
            "contact_id": {"type": "string"},
            "space_id": {"type": "string"},
            "basis": {"type": "string"},
            "dataset": {"type": "string"},
            "query": {"type": "string"},
        },
    }
    return {n: {"description": n, "inputSchema": schema} for n in names}


def _contact_ctx(grants=(), *, stock_allowed=True, codes=("dealer",)):
    from app.services.chatbot.agent.access import AgentContext

    return AgentContext(
        contact_pk="pk-1",
        contact_respond_id="ZZT-RESPOND-1",
        space_id="364817",
        user_id="",
        user_name="",
        grants=frozenset(grants),
        stock_allowed=stock_allowed,
        principal="contact",
        access_codes=frozenset(codes),
    )


def _dispatch(db, ctx, name, args, call):
    from app.services.chatbot.agent import tools

    return tools.dispatch(db, ctx, name, args, call=call, catalog=_catalog(name), timeout=5.0)


def _give_codes(db, contact_pk: str, *, active=(), inactive=()):
    """Assign access codes to a contact; `inactive` codes are catalogue rows with is_active False."""
    from app.models.access import ContactAccessType, respond_contact_access_types

    for code, is_active in [(c, True) for c in active] + [(c, False) for c in inactive]:
        row = db.get(ContactAccessType, code)
        if row is None:
            db.add(ContactAccessType(code=code, name=f"ZZT {code}", is_active=is_active))
        else:
            row.is_active = is_active
    db.flush()
    for code in (*active, *inactive):
        db.execute(respond_contact_access_types.insert().values(contact_id=contact_pk, access_type_code=code))
    db.flush()


# ================================================================ AC-W1: the contact is eligible


def test_ac_w1_the_context_defaults_are_a_user_principal_with_no_codes():
    from app.services.chatbot.agent.access import AgentContext

    ctx = AgentContext(
        contact_pk="p", contact_respond_id="r", space_id=None, user_id="u", user_name="n", grants=frozenset()
    )

    assert ctx.principal == "user"
    assert ctx.access_codes == frozenset()


def test_ac_w1_an_unlinked_contact_is_eligible_with_no_user(db):
    from app.services.chatbot.agent.access import eligible_contact

    contact = seed_contact(db)

    row, user, refusal = eligible_contact(db, contact["respond_id"])

    assert refusal is None
    assert user is None
    assert str(row.id) == contact["pk"]


def test_ac_w1_an_inactive_linked_user_leaves_the_contact_a_contact_principal(db):
    from app.services.chatbot.agent.access import agent_eligibility, eligible_contact

    contact = seed_contact(db)
    seed_user(db, contact_pk=contact["pk"], status="INACTIVE")

    _, user, refusal = eligible_contact(db, contact["respond_id"])

    assert (user, refusal) == (None, None)
    assert agent_eligibility(db, contact["respond_id"]) is None


def test_ac_w1_build_context_for_an_unlinked_contact_is_a_contact_principal(db):
    from app.services.chatbot.agent.access import AgentContext, build_context

    contact = seed_contact(db)

    ctx = build_context(db, contact["respond_id"])

    assert isinstance(ctx, AgentContext)
    assert ctx.principal == "contact"
    assert ctx.user_id == ""
    assert ctx.user_name == ""
    assert ctx.contact_pk == contact["pk"]
    assert ctx.contact_respond_id == contact["respond_id"]
    assert isinstance(ctx.grants, frozenset)


def test_ac_w1_the_context_carries_the_contacts_grants_and_only_its_active_codes(db):
    from app.services.chatbot.agent.access import build_context
    from app.services.contact_field_reveal_service import set_granted_keys

    contact = seed_contact(db)
    set_granted_keys(db, contact["pk"], ["inventory.sellable"], actor_id=None, commit=False)
    _give_codes(db, contact["pk"], active=("dealer", "end_user"), inactive=("zzt_retired",))

    ctx = build_context(db, contact["respond_id"])

    assert "inventory.sellable" in ctx.grants
    assert ctx.access_codes == frozenset({"dealer", "end_user"}), "the inactive code does not count (AC-W17)"


def test_ac_w1_a_contact_with_no_codes_has_an_empty_set(db):
    from app.services.chatbot.agent.access import build_context

    contact = seed_contact(db)

    assert build_context(db, contact["respond_id"]).access_codes == frozenset()


def test_ac_w1_the_contact_context_stamps_the_session_scopes_and_lists_its_tools(db):
    from app.models.base import get_company_scope
    from app.services.chatbot.agent.access import build_context, permitted_tools

    contact = seed_contact(db)

    ctx = build_context(db, contact["respond_id"])

    assert isinstance(get_company_scope(db), frozenset), "the contact's company scope is stamped, fail closed"
    assert ctx.tool_names == tuple(t.name for t in permitted_tools(db, ctx))
    assert "crm_knowledge_search" in ctx.tool_names


# ================================================================ AC-W2: a linked user runs as the user


def test_ac_w2_a_contact_with_a_linked_active_user_still_runs_as_that_user(db):
    from app.services.chatbot.agent.access import build_context, eligible_contact

    contact = seed_contact(db)
    user_id = seed_user(db, contact_pk=contact["pk"], slugs=["inventory.stock.view"])

    _, user, refusal = eligible_contact(db, contact["respond_id"])
    ctx = build_context(db, contact["respond_id"])

    assert refusal is None and str(user.id) == user_id
    assert ctx.principal == "user"
    assert ctx.user_id == user_id
    assert ctx.user_name == "ZZT Agent User"


# ================================================================ AC-W3: refusals unchanged


@pytest.mark.parametrize("reason", ["contact_not_found", "ai_replies_off", "switch_off"])
def test_ac_w3_the_other_refusals_are_unchanged(db, reason):
    from app.services.chatbot.agent.access import AgentRefused, build_context, eligible_contact

    if reason == "contact_not_found":
        respond_id = unique_code("nobody")
    elif reason == "ai_replies_off":
        respond_id = seed_contact(db, chatbot_allowed=False, agent_enabled=False)["respond_id"]
    else:
        respond_id = seed_contact(db, agent_enabled=False)["respond_id"]

    assert eligible_contact(db, respond_id)[2] == reason
    with pytest.raises(AgentRefused) as exc:
        build_context(db, respond_id)
    assert exc.value.reason == reason


# ================================================================ AC-W4: the tools a contact is offered


def test_ac_w4_contact_tools_is_exactly_the_plan_table():
    from app.services.chatbot.agent import tools

    assert tools.CONTACT_TOOLS == PLAN_TABLE
    assert "user_guides_read" not in tools.CONTACT_TOOLS


def test_ac_w4_every_contact_tool_is_a_registry_tool():
    from app.services.chatbot.agent import tools

    assert set(tools.CONTACT_TOOLS) <= set(tools.REGISTRY)


def test_ac_w4_a_contact_with_no_reveal_key_is_offered_only_the_open_tools(db):
    from app.services.chatbot.agent.access import permitted_tools

    offered = {t.name for t in permitted_tools(db, _contact_ctx(grants=()))}

    assert offered == OPEN_TOOLS - {"crm_inventory_stock_balance_list"}
    assert "user_guides_read" not in offered


def test_ac_w4_a_contact_holding_every_key_is_offered_every_planned_tool_and_nothing_else(db):
    from app.services.chatbot.agent.access import permitted_tools

    offered = {t.name for t in permitted_tools(db, _contact_ctx(grants=ALL_KEYS))}

    assert offered == set(PLAN_TABLE)


@pytest.mark.parametrize(
    "key,tools_it_opens",
    [
        ("purchase_orders.placed", {
            "crm_procurement_po_placed_list",
            "crm_procurement_grn_summary",
            "crm_procurement_spo_allocations_last_receipt_list",
        }),
        ("purchase_orders.cost", {"crm_procurement_po_last_cost_list"}),
        ("sales_orders.sales_report", {"crm_report_ask", "crm_order_management_orders_by_product_list"}),
    ],
)
def test_ac_w4_each_reveal_key_opens_exactly_its_tools(db, key, tools_it_opens):
    from app.services.chatbot.agent.access import permitted_tools

    without = {t.name for t in permitted_tools(db, _contact_ctx(grants=()))}
    with_key = {t.name for t in permitted_tools(db, _contact_ctx(grants=(key,)))}

    assert tools_it_opens.isdisjoint(without)
    assert with_key - without == tools_it_opens


def test_ac_w4_a_contact_is_offered_no_user_permission_check_at_all(db, monkeypatch):
    from app.services.chatbot.agent import tools
    from app.services.chatbot.agent.access import permitted_tools

    def boom(*a, **k):
        raise AssertionError("a contact principal must not consult a user permission")

    monkeypatch.setattr(tools, "_permitted", boom)

    offered = {t.name for t in permitted_tools(db, _contact_ctx(grants=ALL_KEYS))}

    assert offered == set(PLAN_TABLE)


def test_ac_w4_a_contact_is_offered_no_write_and_no_user_read(db, monkeypatch):
    from app.services.chatbot.agent import writes

    def boom(*a, **k):
        raise AssertionError("holds must not be asked for a contact principal")

    monkeypatch.setattr(writes, "holds_ctx", boom)
    monkeypatch.setattr(writes, "holds", boom, raising=False)
    ctx = _contact_ctx(grants=ALL_KEYS)

    assert writes.permitted_writes(db, ctx) == []
    assert writes.permitted_user_reads(db, ctx) == []


def test_ac_w4_a_user_principal_still_gets_its_writes_and_reads_from_slugs(db):
    """Positive control for the guard above: a user principal is not emptied."""
    import dataclasses

    from app.services.chatbot.agent import writes

    user_id = seed_user(db, contact_pk=None, slugs=())
    ctx = dataclasses.replace(_contact_ctx(), principal="user", user_id=user_id, user_name="ZZT")

    # No slug held: the lists are computed from slugs, not blanket-emptied or blanket-filled.
    assert isinstance(writes.permitted_writes(db, ctx), list)
    assert isinstance(writes.permitted_user_reads(db, ctx), list)


# ================================================================ AC-W5: dispatch denies outside the gate


def test_ac_w5_an_open_tool_runs_for_a_contact_with_no_grants(db):
    rec = Recorder()

    out = _dispatch(db, _contact_ctx(), "crm_incoming_stock_by_product", {}, rec)

    assert out.status == "ok", out.message
    assert [n for n, _ in rec.calls] == ["crm_incoming_stock_by_product"]
    assert rec.calls[0][1]["contact_id"] == "ZZT-RESPOND-1"


def test_ac_w5_user_guides_read_is_denied_for_a_contact(db):
    out = _dispatch(db, _contact_ctx(grants=ALL_KEYS), "user_guides_read", {"query": "how do I"}, forbidden_call)

    assert out.status == "denied"


@pytest.mark.parametrize("name", ["crm_order_cancel", "crm_customer_ask_update", "not_a_tool"])
def test_ac_w5_a_write_or_unknown_tool_the_model_names_is_denied(db, name):
    out = _dispatch(db, _contact_ctx(grants=ALL_KEYS), name, {}, forbidden_call)

    assert out.status == "denied"


@pytest.mark.parametrize(
    "name,held",
    [
        ("crm_procurement_po_placed_list", ()),
        ("crm_procurement_po_placed_list", ("purchase_orders.cost",)),
        ("crm_procurement_grn_summary", ("sales_orders.sales_report",)),
        ("crm_procurement_spo_allocations_last_receipt_list", ()),
        ("crm_procurement_po_last_cost_list", ("purchase_orders.placed",)),
        ("crm_report_ask", ("purchase_orders.placed",)),
        ("crm_order_management_orders_by_product_list", ()),
    ],
)
def test_ac_w5_a_tool_whose_reveal_key_is_not_held_is_denied(db, name, held):
    out = _dispatch(db, _contact_ctx(grants=held), name, {"basis": "invoiced"}, forbidden_call)

    assert out.status == "denied"


@pytest.mark.parametrize(
    "name,key",
    [
        ("crm_procurement_po_placed_list", "purchase_orders.placed"),
        ("crm_procurement_po_last_cost_list", "purchase_orders.cost"),
        ("crm_order_management_orders_by_product_list", "sales_orders.sales_report"),
    ],
)
def test_ac_w5_positive_control_the_held_key_lets_the_call_through(db, name, key):
    rec = Recorder()

    out = _dispatch(db, _contact_ctx(grants=(key,)), name, {}, rec)

    assert out.status == "ok", out.message
    assert len(rec.calls) == 1


def test_ac_w5_dispatch_asks_no_user_permission_for_a_contact(db, monkeypatch):
    from app.services.chatbot.agent import tools

    def boom(*a, **k):
        raise AssertionError("a contact principal must not consult a user permission")

    monkeypatch.setattr(tools, "_permitted", boom)
    rec = Recorder()

    out = _dispatch(db, _contact_ctx(grants=ALL_KEYS), "crm_incoming_stock_shipments", {}, rec)

    assert out.status == "ok", out.message


# ================================================================ AC-W6: crm_report_ask arguments


def test_ac_w6_basis_unpaid_is_denied_for_a_contact_even_with_the_sales_key(db):
    out = _dispatch(
        db, _contact_ctx(grants=("sales_orders.sales_report",)), "crm_report_ask", {"basis": "unpaid"}, forbidden_call
    )

    assert out.status == "denied"


def test_ac_w6_positive_control_a_sales_basis_runs_with_the_sales_key(db):
    rec = Recorder()

    out = _dispatch(db, _contact_ctx(grants=("sales_orders.sales_report",)), "crm_report_ask", {"basis": "invoiced"}, rec)

    assert out.status == "ok", out.message
    assert len(rec.calls) == 1


def test_ac_w6_dataset_chat_needs_the_analytics_grant(db):
    denied = _dispatch(
        db, _contact_ctx(grants=("sales_orders.sales_report",)), "crm_report_ask", {"dataset": "chat"}, forbidden_call
    )
    rec = Recorder()
    allowed = _dispatch(
        db,
        _contact_ctx(grants=("sales_orders.sales_report", "chatbot.analytics")),
        "crm_report_ask",
        {"dataset": "chat"},
        rec,
    )

    assert denied.status == "denied"
    assert allowed.status == "ok", allowed.message
    assert len(rec.calls) == 1


# ================================================================ AC-W7: crm_resolve kinds


def test_ac_w7_a_contact_may_search_only_product_brand_and_category(db):
    from app.services.chatbot.agent import tools

    assert tools.CONTACT_KINDS == frozenset({"product", "brand", "category"})
    ctx = _contact_ctx(grants=ALL_KEYS | {"purchase_orders.supplier"})

    allowed, skipped = tools.searchable_kinds(db, ctx, list(tools.KIND_SLUGS))

    assert set(allowed) == {"product", "brand", "category"}
    assert {"customer", "supplier", "sales_agent"} <= set(skipped)


def test_ac_w7_resolve_is_offered_to_a_contact_through_those_kinds(db):
    from app.services.chatbot.agent import tools

    assert tools.user_may_use(db, _contact_ctx(), tools.REGISTRY["crm_resolve"]) is True


# ================================================================ AC-W8: stock needs the key AND the switch


@pytest.mark.parametrize(
    "grants,stock_allowed,offered",
    [
        (("inventory.sellable",), True, True),
        (("inventory.sellable",), False, False),
        ((), True, False),
        ((), False, False),
    ],
)
def test_ac_w8_the_stock_tool_needs_sellable_and_the_stock_switch(db, grants, stock_allowed, offered):
    from app.services.chatbot.agent.access import permitted_tools

    ctx = _contact_ctx(grants=grants, stock_allowed=stock_allowed)

    names = {t.name for t in permitted_tools(db, ctx)}

    assert ("crm_inventory_stock_balance_list" in names) is offered


@pytest.mark.parametrize("grants,stock_allowed", [(("inventory.sellable",), False), ((), True)])
def test_ac_w8_dispatch_denies_the_stock_tool_when_either_half_is_missing(db, grants, stock_allowed):
    out = _dispatch(
        db, _contact_ctx(grants=grants, stock_allowed=stock_allowed), "crm_inventory_stock_balance_list", {}, forbidden_call
    )

    assert out.status == "denied"


def test_ac_w8_positive_control_both_halves_let_the_stock_call_through(db):
    rec = Recorder()

    out = _dispatch(
        db, _contact_ctx(grants=("inventory.sellable",), stock_allowed=True), "crm_inventory_stock_balance_list", {}, rec
    )

    assert out.status == "ok", out.message
    assert len(rec.calls) == 1


# ================================================================ AC-W9: the system prompt


def test_ac_w9_a_contact_prompt_never_says_working_for_and_names_the_whatsapp_customer(db):
    from app.services.chatbot.agent.loop import _system_prompt

    prompt = _system_prompt(db, "", ("crm_knowledge_search",), principal="contact")

    assert "You are working for" not in prompt
    assert "whatsapp" in prompt.lower()
    assert "customer" in prompt.lower()


def test_ac_w9_a_user_prompt_is_unchanged(db):
    from app.services.chatbot.agent.loop import _system_prompt

    prompt = _system_prompt(db, "Ann Tester", ("crm_knowledge_search",), principal="user")
    default = _system_prompt(db, "Ann Tester", ("crm_knowledge_search",))

    assert "You are working for Ann Tester." in prompt
    assert prompt == default


# ================================================================ AC-W10: the router lets the contact through


def _fake_jev(monkeypatch):
    from app.services.chatbot import jev_client
    from tests.chatbot.agent.test_router import FakeJev

    fake = FakeJev()
    monkeypatch.setattr(jev_client, "classify", fake)
    return fake


def test_ac_w10_an_unlinked_contact_is_no_longer_refused_with_no_linked_user(db, monkeypatch):
    from app.services.chatbot.router import decide_route

    _fake_jev(monkeypatch)
    contact = seed_contact(db)

    decision = decide_route(
        db, contact_respond_id=contact["respond_id"], text="hello", session_vars=None, has_media=False
    )

    assert decision.reason != "not_eligible:no_linked_user"
    assert not decision.reason.startswith("not_eligible")


def test_ac_w10_the_unlinked_contact_reaches_the_next_gate(db, monkeypatch):
    from app.services.chatbot.router import decide_route

    _fake_jev(monkeypatch)
    contact = seed_contact(db)

    decision = decide_route(
        db, contact_respond_id=contact["respond_id"], text="hello", session_vars=None, has_media=True
    )

    assert (decision.side, decision.reason) == ("chat", "media")


def test_ac_w10_an_armed_router_can_send_an_unlinked_contact_to_the_agent(db, monkeypatch):
    from app.services.chatbot.router import decide_route
    from tests.chatbot.agent.test_router import arm

    fake = _fake_jev(monkeypatch)
    arm(db)
    contact = seed_contact(db)

    decision = decide_route(
        db, contact_respond_id=contact["respond_id"], text="why did sales drop", session_vars=None, has_media=False
    )

    assert (decision.side, decision.reason) == ("agent", "classified")
    assert len(fake.calls) == 1


def test_ac_w10_a_switch_off_contact_is_still_refused(db, monkeypatch):
    """Positive control for the unlinked path above: the switch still gates."""
    from app.services.chatbot.router import decide_route

    _fake_jev(monkeypatch)
    contact = seed_contact(db, agent_enabled=False)

    decision = decide_route(
        db, contact_respond_id=contact["respond_id"], text="hello", session_vars=None, has_media=False
    )

    assert (decision.side, decision.reason) == ("chat", "not_eligible:switch_off")
