"""AGENT-REPORTS: sales / outstanding report asks and their follow-ups on the agent (switch off by default).

Plan: `documentation/plans/chatbot/PLAN-agent-reports-5nov.md`. Postgres via the blank schema; no live model
(a scripted provider), no MCP (a recording fake that answers the presenter's report envelope), no Jev (a
monkeypatched classifier). The model's choice of arguments is the eval's job; these tests pin what CODE
guarantees: the switch, the routing of every follow-up, the held report each turn sees, the held ids, the card
reply, and the asker's scope.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

import app.main  # noqa: F401  register every model and the app's listeners
from app.models.chatbot_turn import ChatbotTurn
from app.models.user import SystemSetting
from tests._pg_fixture import blank_session
from tests.chatbot.agent._seed import seed_agent_contact, seed_contact, seed_user
from tests.chatbot.agent.test_agent_loop import Mcp, ScriptedProvider, answer, asks
from tests.chatbot.agent.test_router import OPEN_QUESTION_VARS, arm, jev, route  # noqa: F401  (jev is a fixture)

REPORT = "crm_report_ask"
BRAND = "6b0c4a3e-1111-4c1e-9b1a-0000000000a1"
CATEGORY = "6b0c4a3e-2222-4c1e-9b1a-0000000000c1"

CATALOG = {
    REPORT: {
        "description": "Sales and outstanding figures",
        "inputSchema": {
            "type": "object",
            "properties": {
                "contact_id": {"type": "string"},
                "space_id": {"type": "string"},
                "view": {"type": "string"},
                "basis": {"type": "string"},
                "measure": {"type": "string"},
                "date_from": {"type": "string"},
                "date_to": {"type": "string"},
                "group_by": {"type": "string"},
                "top_n": {"type": "integer"},
                "company": {"type": "string"},
                "channel": {"type": "string"},
                "brand_ids": {"type": "array", "items": {"type": "string"}},
                "category_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["contact_id", "space_id"],
        },
    },
}

T1_ARGS = {
    "basis": "invoiced", "measure": "qty", "date_from": "2026-09-01", "date_to": "2026-09-30",
    "company": "Sorento", "brand_ids": [BRAND], "category_ids": [CATEGORY],
}
T1_CARD = (
    "Sales by invoiced sales\nCompany: Sorento\nBrand: SORENTO\nCategory: Kitchen Sink\n"
    "Period: 01/09/2026 - 30/09/2026\nTotal 2,270 pcs · RM 1,066,977.87"
)
T2_CARD = (
    "Sales by invoiced sales by channel\nCompany: Sorento\nBrand: SORENTO\nCategory: Kitchen Sink\n"
    "Period: 01/09/2026 - 30/09/2026\n1. Dealer 1,900 pcs\n2. Project team 370 pcs\nTotal 2,270 pcs"
)
T3_CARD = "Sales by invoiced sales\nPeriod: 01/09/2026 - 30/09/2026\nTotal 9,000 pcs · RM 4,000,000.00"


def card(text_):
    return {"result_type": "report_ask", "response": text_, "has_result": True, "drill_rows": None, "not_applied": []}


class CardMcp(Mcp):
    """Answers each report call with the next card."""

    def __init__(self, *cards):
        super().__init__()
        self.cards = list(cards)

    def __call__(self, name, args):
        self.calls.append((name, dict(args)))
        return card(self.cards.pop(0))


def report_call(args, cid="call-1"):
    return {"id": cid, "name": REPORT, "arguments": dict(args)}


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


def switch(db, on: bool):
    row = db.query(SystemSetting).first()
    if row is None:
        row = SystemSetting(id=str(uuid.uuid4()), name="ZZT agent reports co")
        db.add(row)
    row.chatbot_agent_reports_enabled = on
    db.commit()


def run(db, contact, provider, mcp, text):
    from app.services.chatbot.agent.loop import run_agent_turn

    return run_agent_turn(
        db, contact_respond_id=contact["respond_id"], text=text, provider=provider, mcp_call=mcp, catalog=CATALOG,
    )


def row_of(db, result) -> ChatbotTurn:
    return db.query(ChatbotTurn).filter(ChatbotTurn.id == result.turn_id).one()


def system_text(provider) -> str:
    return provider.seen[0]["messages"][0]["content"]


def seed_held(db, contact, state, *, minutes_ago=5, reply="earlier"):
    """A finished agent turn of the contact's newest conversation that holds `state`."""
    from app.services.chatbot.agent import memory
    from app.services.chatbot.agent.access import build_context, grants_hash

    # The conversation the next turn continues: the same user and grant set (`loop.run_agent_turn`).
    ctx = build_context(db, contact["respond_id"])
    conv = memory.current_conversation(db, contact["respond_id"], user_id=ctx.user_id or None, grants_hash=grants_hash(ctx))
    turn = ChatbotTurn(
        id=str(uuid.uuid4()),
        contact_respond_id=contact["respond_id"],
        ingress="agent",
        is_test=True,
        status="done",
        envelope={"text": "earlier", "agent_conversation_id": str(conv.id)},
        response={"reply_text": reply, "tool_digest": [], "status": "answered", "report_state": state},
        created_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
    )
    db.add(turn)
    db.commit()
    return conv


# ================================================================== the switch and the loop


def test_switch_defaults_off_on_a_new_settings_row(db):
    row = SystemSetting(id=str(uuid.uuid4()), name="ZZT default")
    db.add(row)
    db.commit()
    db.refresh(row)
    assert row.chatbot_agent_reports_enabled is False


def test_off_the_loop_is_unchanged_no_protocol_no_state_no_card_swap(db):
    contact = seed_agent_contact(db)
    switch(db, False)
    provider = ScriptedProvider([asks(report_call(T1_ARGS | {"brand_ids": None, "category_ids": None})), answer("Done.")])
    result = run(db, contact, provider, CardMcp(T1_CARD), "Total quantity sale for Sorento brand kitchen sink on September 2026")

    assert "SALES AND OUTSTANDING REPORTS" not in system_text(provider)
    assert "report_state" not in row_of(db, result).response
    assert result.reply_text == "Done."


def test_T1_on_the_reply_is_the_card_and_the_full_args_are_held(db):
    contact = seed_agent_contact(db)
    switch(db, True)
    args = {k: v for k, v in T1_ARGS.items() if not k.endswith("_ids")}
    provider = ScriptedProvider([asks(report_call(args)), answer("Here is September.")])
    mcp = CardMcp(T1_CARD)
    result = run(db, contact, provider, mcp, "Total quantity sale for Sorento brand kitchen sink on September 2026")

    system = system_text(provider)
    assert "SALES AND OUTSTANDING REPORTS" in system and "Held report: none yet." in system
    assert mcp.calls[0][0] == REPORT and mcp.calls[0][1]["basis"] == "invoiced"
    assert "Total 2,270 pcs" in result.reply_text and "Company: Sorento" in result.reply_text
    state = row_of(db, result).response["report_state"]
    assert state["args"] == args  # never contact_id, space_id or view
    assert state["head"].startswith("Sales by invoiced sales\nCompany: Sorento")
    assert "Total" not in state["head"]


def test_a_reply_that_already_carries_the_card_is_kept(db):
    contact = seed_agent_contact(db)
    switch(db, True)
    provider = ScriptedProvider([asks(report_call({"basis": "invoiced", "date_from": "2026-09-01", "date_to": "2026-09-30"})),
                                 answer(f"Cleared every filter.\n\n{T3_CARD}", figures=[{"value": "9,000", "call_id": "call-1"}])])
    result = run(db, contact, provider, CardMcp(T3_CARD), "clear all")
    assert result.reply_text.startswith("Cleared every filter.")


def test_T2_the_held_report_is_in_the_system_prompt_and_its_ids_may_be_reused(db):
    contact = seed_agent_contact(db)
    switch(db, True)
    seed_held(db, contact, {"args": T1_ARGS, "head": "Sales by invoiced sales\nCompany: Sorento\nBrand: SORENTO"})
    provider = ScriptedProvider([asks(report_call(T1_ARGS | {"group_by": "channel", "top_n": 10})), answer("By channel.")])
    mcp = CardMcp(T2_CARD)
    result = run(db, contact, provider, mcp, "sorento total slaes delaer and proejct")

    system = system_text(provider)
    assert "Held report arguments:" in system and BRAND in system and CATEGORY in system
    assert "Brand: SORENTO" in system
    assert [s["status"] for s in result.tool_calls] == ["ok"]
    assert mcp.calls[0][1]["brand_ids"] == [BRAND] and mcp.calls[0][1]["group_by"] == "channel"
    assert "Project team" in result.reply_text
    assert row_of(db, result).response["report_state"]["args"]["group_by"] == "channel"


def test_kill_off_the_held_ids_are_not_seeded(db):
    """The same call with the switch off: the ids were never shown this turn, so the tool refuses them."""
    contact = seed_agent_contact(db)
    switch(db, False)
    seed_held(db, contact, {"args": T1_ARGS, "head": ""})
    provider = ScriptedProvider([asks(report_call(T1_ARGS | {"group_by": "channel", "top_n": 10})), answer("No.")])
    mcp = CardMcp(T2_CARD)
    result = run(db, contact, provider, mcp, "by dealer and project")
    assert [s["status"] for s in result.tool_calls] == ["invalid"]
    assert mcp.calls == []


def test_a_turn_without_a_report_call_keeps_the_held_report(db):
    contact = seed_agent_contact(db)
    switch(db, True)
    seed_held(db, contact, {"args": T1_ARGS, "head": "Sales by invoiced sales"})
    provider = ScriptedProvider([answer("Which period?")])
    result = run(db, contact, provider, Mcp(), "and the period?")
    assert row_of(db, result).response["report_state"]["args"] == T1_ARGS
    assert result.reply_text == "Which period?"


def test_a_user_without_the_report_tool_gets_no_protocol_and_no_state(db):
    contact = seed_agent_contact(db, slugs=("inventory.stock.view",))
    switch(db, True)
    seed_held(db, contact, {"args": T1_ARGS, "head": ""})
    provider = ScriptedProvider([answer("Hello.")])
    result = run(db, contact, provider, Mcp(), "total sales")
    names = {t["function"]["name"] for t in provider.seen[0]["tools"]}
    assert REPORT not in names
    assert "SALES AND OUTSTANDING REPORTS" not in system_text(provider)
    assert BRAND not in system_text(provider)
    assert "report_state" not in row_of(db, result).response


# ================================================================== the router


def test_router_off_a_held_report_changes_nothing(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    switch(db, False)
    seed_held(db, contact, {"args": T1_ARGS, "head": ""})
    decision = route(db, contact["respond_id"], "clear all")
    assert decision.reason == "classified" and len(jev.calls) == 1
    assert "reports" not in jev.calls[0]["criteria"]["agent"]


def test_router_on_a_held_report_keeps_the_follow_up_on_the_agent_without_jev(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    switch(db, True)
    seed_held(db, contact, {"args": T1_ARGS, "head": ""})
    decision = route(db, contact["respond_id"], "clear all")
    assert (decision.side, decision.reason) == ("agent", "report_held")
    assert jev.calls == []


def test_router_on_a_held_report_beats_an_older_bot_question(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    switch(db, True)
    seed_held(db, contact, {"args": T1_ARGS, "head": ""})
    decision = route(db, contact["respond_id"], "all", session_vars=OPEN_QUESTION_VARS)
    assert (decision.side, decision.reason) == ("agent", "report_held")


def test_router_on_the_daily_cap_still_holds(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    switch(db, True)
    db.query(SystemSetting).first().chatbot_agent_daily_turns = 1
    db.commit()
    seed_held(db, contact, {"args": T1_ARGS, "head": ""})
    decision = route(db, contact["respond_id"], "all")
    assert (decision.side, decision.reason) == ("chat", "daily_cap")


def test_router_on_a_report_held_over_an_hour_ago_goes_back_to_jev(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    switch(db, True)
    seed_held(db, contact, {"args": T1_ARGS, "head": ""}, minutes_ago=61)
    decision = route(db, contact["respond_id"], "all")
    assert decision.reason == "classified" and len(jev.calls) == 1


def test_router_on_jev_is_told_report_asks_are_the_agents(db, jev):
    contact = seed_agent_contact(db)
    arm(db)
    switch(db, True)
    route(db, contact["respond_id"], "Total quantity sale for Sorento brand kitchen sink on September 2026")
    criteria = jev.calls[0]["criteria"]
    assert "sales figures" in criteria["agent"]["reports"]
    assert "sales and outstanding figures" in criteria["agent"]["tools"]


def test_router_on_but_no_report_tool_for_this_user_is_todays_routing(db, jev):
    contact = seed_agent_contact(db, slugs=("inventory.stock.view",))
    arm(db)
    switch(db, True)
    seed_held(db, contact, {"args": T1_ARGS, "head": ""})
    decision = route(db, contact["respond_id"], "all")
    assert decision.reason == "classified"
    assert "reports" not in jev.calls[0]["criteria"]["agent"]


def test_router_on_a_whatsapp_contact_with_its_own_agent_switch_off_stays_on_the_bot(db, jev):
    """The two controls combine: the admin switch AND the contact's `chatbot_agent_enabled`."""
    contact = seed_contact(db, agent_enabled=False)
    seed_user(db, contact_pk=contact["pk"], slugs=("order_management.orders.view",))
    arm(db)
    switch(db, True)
    decision = route(db, contact["respond_id"], "total sales September")
    assert (decision.side, decision.reason) == ("chat", "not_eligible:switch_off")


def test_router_leaves_the_session_scope_as_it_found_it(db, jev):
    from app.models import base as model_base

    contact = seed_agent_contact(db)
    arm(db)
    switch(db, True)
    company, brands = frozenset({"zzt-company-sentinel"}), frozenset({"zzt-brand-sentinel"})
    db.info[model_base._SCOPE_KEY] = company
    db.info[model_base._BRAND_SCOPE_KEY] = brands
    route(db, contact["respond_id"], "total sales")
    assert db.info[model_base._SCOPE_KEY] == company and db.info[model_base._BRAND_SCOPE_KEY] == brands


# ================================================================== T1 to T7, chained


def test_T1_to_T7_every_follow_up_routes_to_the_agent_and_the_held_report_evolves(db, jev):
    """The prod transcript of 5 Nov. The scripted model plays what the protocol asks; code must route every
    follow-up to the agent, show each turn the report held after the turn before, and reply with the card."""
    contact = seed_agent_contact(db)
    arm(db)
    switch(db, True)
    t1 = {k: v for k, v in T1_ARGS.items() if not k.endswith("_ids")}
    steps = [
        ("Total quantity sale for Sorento brand kitchen sink on September 2026", t1, T1_CARD),
        ("sorento total slaes delaer and proejct", t1 | {"group_by": "channel", "top_n": 10}, T2_CARD),
        ("clear all", {"basis": "invoiced", "measure": "qty", "date_from": "2026-09-01", "date_to": "2026-09-30"}, T3_CARD),
        ("sorento total slaes by delaer and proejct",
         {"basis": "invoiced", "measure": "qty", "date_from": "2026-09-01", "date_to": "2026-09-30", "company": "Sorento",
          "group_by": "channel", "top_n": 10}, T2_CARD),
        ("all", {"basis": "invoiced", "measure": "qty", "date_from": "2026-09-01", "date_to": "2026-09-30",
                 "group_by": "channel", "top_n": 10}, T2_CARD),
        ("all brand all category", {"basis": "invoiced", "measure": "qty", "date_from": "2026-09-01",
                                    "date_to": "2026-09-30", "group_by": "channel", "top_n": 10}, T2_CARD),
        ("for all brands and categories", {"basis": "invoiced", "measure": "qty", "date_from": "2026-09-01",
                                           "date_to": "2026-09-30", "group_by": "channel", "top_n": 10}, T2_CARD),
    ]
    previous = None
    for i, (text_, args, card_text) in enumerate(steps):
        if i:
            decision = route(db, contact["respond_id"], text_)
            assert (decision.side, decision.reason) == ("agent", "report_held"), text_
        provider = ScriptedProvider([asks(report_call(args)), answer("Here it is.")])
        result = run(db, contact, provider, CardMcp(card_text), text_)
        # One test transaction gives every row the same now(); in production each turn commits apart.
        row_of(db, result).created_at = datetime.now(timezone.utc) - timedelta(minutes=30 - i)
        db.commit()
        system = system_text(provider)
        if previous is None:
            assert "Held report: none yet." in system
        else:
            for key, value in previous.items():
                assert f'"{key}": ' in system and str(value if not isinstance(value, list) else value[0]) in system
        assert result.reply_text == card_text.replace("·", "·")
        state = row_of(db, result).response["report_state"]
        assert state["args"] == args
        previous = args
    assert jev.calls == []  # T2 to T7 never reached Jev; T1 ran the loop directly
