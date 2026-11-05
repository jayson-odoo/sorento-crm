"""AI-GAP-SIGNAL (PLAN-ai-tools-standard-5nov.md phase 0, AC-8): the agent flags an ask no tool could do.

The answer tool's optional `no_tool` list is saved on the turn's trace as one `agent_no_tool` event, and the
Wishlist screen lists the last 30 days of them behind the Wishlist's own slug. No OpenAI key, no clustering.
Uses the scripted-provider harness of test_agent_loop.py: no live LLM, no network.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.models.chatbot_turn import ChatbotTurn
from app.services.ai_wishlist_service import NO_TOOL_EVENT, AiWishlistService
from app.services.llm_provider import ChatResult
from tests._ai_usage_client import VIEW, api_client
from tests.chatbot.agent.test_agent_loop import (  # noqa: F401
    ScriptedProvider,
    _set_budgets,
    _turn_row,
    answer,
    asks,
    call,
    contact,
    db,
    run,
)

ROUTE = "/api/v1/system/ai-assistant/wishlist/no-tool"


def answer_with_gaps(text, no_tool, cid="ans-1"):
    return ChatResult(
        content="", prompt_tokens=100, completion_tokens=10, total_tokens=110,
        tool_calls=[
            {
                "id": cid,
                "name": "answer",
                "arguments": {"text": text, "figures": [], "not_found": [], "not_checked": [], "no_tool": no_tool},
            }
        ],
    )


def _events(row):
    return [e for e in (row.trace or []) if isinstance(e, dict) and e.get("kind") == NO_TOOL_EVENT]


def test_the_answer_schema_declares_no_tool_as_optional():
    from app.services.chatbot.agent import tools

    params = tools.ANSWER_SCHEMA["function"]["parameters"]
    prop = params["properties"]["no_tool"]
    assert prop["type"] == "array"
    assert prop["items"]["required"] == ["ask"]
    assert set(prop["items"]["properties"]) == {"ask", "area"}
    assert "no_tool" not in params["required"]


def test_an_answer_with_no_tool_saves_it_on_the_turn_trace(db, contact):
    gaps = [{"ask": "approve purchase order PO-1001", "area": "purchasing"}]
    result = run(db, contact, ScriptedProvider([answer_with_gaps("I cannot approve purchase orders.", gaps)]),
                 text="approve PO-1001")
    events = _events(_turn_row(db, result))
    assert len(events) == 1
    assert events[0]["items"] == [{"ask": "approve purchase order PO-1001", "area": "purchasing"}]
    assert events[0]["user_id"] == str(contact["user_id"])
    assert events[0]["channel"] == "console"  # a test run with no panel principal and no live WhatsApp


def test_an_answer_without_no_tool_saves_nothing(db, contact):
    result = run(db, contact, ScriptedProvider([answer("Hello.")]), text="hello")
    assert _events(_turn_row(db, result)) == []


def test_an_empty_or_malformed_no_tool_saves_nothing(db, contact):
    bad = [{"ask": "   "}, {"area": "stock"}, "free text", {"ask": 12}]
    result = run(db, contact, ScriptedProvider([answer_with_gaps("Hello.", bad)]), text="hello")
    assert _events(_turn_row(db, result)) == []


def test_no_tool_is_trimmed_and_capped_at_five():
    from app.services.chatbot.agent.loop import no_tool_items

    items = no_tool_items({"no_tool": [{"ask": f"  ask {i} " + "x" * 400, "area": "  "} for i in range(8)]})
    assert len(items) == 5
    assert all(len(i["ask"]) == 300 and i["ask"].startswith("ask ") for i in items)
    assert all(i["area"] is None for i in items)


def test_a_forced_final_at_a_limit_still_saves_its_no_tool(db, contact):
    _set_budgets(db, chatbot_agent_max_rounds=2)
    provider = ScriptedProvider([
        asks(call(cid="c1")), asks(call(cid="c2")),
        answer_with_gaps("I could only check part.", [{"ask": "send the quotation by email", "area": "quotations"}]),
    ])
    result = run(db, contact, provider)
    row = _turn_row(db, result)
    assert row.response["status"] == "limited"
    assert _events(row)[0]["items"] == [{"ask": "send the quotation by email", "area": "quotations"}]


def test_a_live_whatsapp_turn_is_labelled_whatsapp(db, contact):
    gaps = [{"ask": "change my delivery address", "area": "orders"}]
    result = run(db, contact, ScriptedProvider([answer_with_gaps("I cannot change that.", gaps)]),
                 text="change my address", is_test=False)
    assert _events(_turn_row(db, result))[0]["channel"] == "whatsapp"


# ------------------------------------------------------------------ the Wishlist list


def _seed_turn(db, *, created_at, items, user_id=None, channel="panel", contact_id=None):
    turn = ChatbotTurn(
        id=str(uuid.uuid4()),
        contact_respond_id=contact_id or f"zzt-{uuid.uuid4().hex[:8]}",
        ingress="agent",
        envelope={"text": "x"},
        status="done",
        trace=[
            {"stage": "received", "status": "ok", "summary": "s", "why": "w"},
            {"kind": NO_TOOL_EVENT, "at": created_at.isoformat(), "items": items, "user_id": user_id,
             "channel": channel},
        ],
        created_at=created_at,
    )
    db.add(turn)
    db.flush()
    return turn


def test_the_list_holds_the_last_30_days_newest_first_with_user_and_channel(db, contact):
    now = datetime.now(timezone.utc)
    _seed_turn(db, created_at=now - timedelta(days=2), items=[{"ask": "ZZT older ask", "area": "stock"}],
               user_id=contact["user_id"], channel="panel")
    _seed_turn(db, created_at=now - timedelta(hours=1), items=[{"ask": "ZZT newer ask", "area": None}],
               user_id=contact["user_id"], channel="whatsapp")
    _seed_turn(db, created_at=now - timedelta(days=31), items=[{"ask": "ZZT too old", "area": "stock"}])
    # A turn with no no_tool event is not listed.
    db.add(ChatbotTurn(id=str(uuid.uuid4()), contact_respond_id="zzt-x", ingress="agent", envelope={},
                       status="done", trace=[{"kind": "agent_answer"}], created_at=now))
    db.flush()

    rows = [r for r in AiWishlistService(db).list_no_tool() if r["ask"].startswith("ZZT")]
    assert [r["ask"] for r in rows] == ["ZZT newer ask", "ZZT older ask"]
    assert rows[0]["channel"] == "whatsapp" and rows[1]["channel"] == "panel"
    assert rows[0]["who"] == "ZZT Agent User"
    assert rows[1]["area"] == "stock" and rows[0]["area"] is None


def test_a_contact_without_a_linked_user_is_named_by_the_contact(db):
    from sqlalchemy import text

    rid = f"zzt-{uuid.uuid4().hex[:8]}"
    db.execute(text("INSERT INTO respond_contacts (id, respond_io_id, name, session_vars) "
                    "VALUES (:id, :rid, 'ZZT Dealer', '{}'::jsonb)"), {"id": str(uuid.uuid4()), "rid": rid})
    _seed_turn(db, created_at=datetime.now(timezone.utc), items=[{"ask": "ZZT dealer ask"}], channel="whatsapp",
               contact_id=rid)
    rows = [r for r in AiWishlistService(db).list_no_tool() if r["ask"] == "ZZT dealer ask"]
    assert rows[0]["who"] == "ZZT Dealer"


def test_the_route_answers_for_the_wishlist_slug(db, contact):
    _seed_turn(db, created_at=datetime.now(timezone.utc), items=[{"ask": "ZZT route ask", "area": "orders"}],
               user_id=contact["user_id"], channel="panel")
    with api_client(db, [VIEW]) as client:
        res = client.get(ROUTE)
    assert res.status_code == 200, res.text
    row = next(r for r in res.json() if r["ask"] == "ZZT route ask")
    assert row["area"] == "orders" and row["channel"] == "panel" and row["who"] == "ZZT Agent User"
    assert row["asked_at"] and row["turn_id"]


def test_the_route_refuses_a_user_without_the_wishlist_slug(db):
    with api_client(db, ["system.ai_assistant_chat.agent"]) as client:
        res = client.get(ROUTE)
    assert res.status_code == 403
