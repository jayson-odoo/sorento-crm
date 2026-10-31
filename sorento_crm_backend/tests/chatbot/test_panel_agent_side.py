"""AGENTIC-UNIFY PR 3, slice 2 (red): the agent side of the panel, writes, opportunity, escalation.

UAC: documentation/plans/chatbot/agentic-unify-panel-acceptance-criteria.md
AC-3 (agent side), AC-7, AC-8, AC-12, AC-13, AC-14, AC-15, AC-22 (backend half), AC-25.

Fakes sit at the provider boundary only: Jev (`jev_client.classify`), the agent's model client
(`agent.loop._resolve_provider`), the MCP client, the parser, HTTP and the queue. The router,
agent loop, tool dispatch, action store, engine, escalation lane and SLA service are real, on
Postgres, with every row seeded here.

Contract assumed (tell the captain if any does not fit):
- `run_panel_turn(...)` routes with panel history, and a Jev "agent" answer or a waiting proposal
  runs the agent as the staff user, keyed by the panel key (`agent_actions.contact_respond_id`,
  `chatbot.turns.contact_respond_id` = `panel-<conversation id>`). `PanelTurnResult.route` is
  "agent" or "chat"; `PanelTurnResult.agent` is the console's agent dict (steps, actions,
  pending_action, tool_calls) or None.
- `agent.loop._resolve_provider` and `agent.loop._fetch_catalog` stay the model and catalog seams.
- Panel routes: POST /api/v1/system/ai-assistant/agent/actions/{id}/confirm, /cancel and
  /steps/{index}/withdraw, empty JSON body, answered like the console's (`AgentActionResponse`).
- The `panel_service` agent path reads the daily cap from `system_settings.chatbot_agent_daily_turns`
  and counts `chatbot.turns` rows with `ingress="agent"` over every panel key of the user.
"""
from __future__ import annotations

import copy
import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.main  # noqa: F401  isort:skip
from app.audit_context import get_actor
from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.main import app
from app.models.ai_assistant import AIAssistantConversation, AIAssistantMessage
from app.models.base import get_company_scope
from app.models.chatbot_agent import AgentAction
from app.models.chatbot_turn import ChatbotTurn
from app.models.user import SystemSetting, User
from app.services.chatbot import jev_client
from app.services.chatbot.agent import loop as agent_loop
from app.services.chatbot.agent import writes
from app.services.chatbot.jev_client import JevError
from app.services.llm_provider import ChatResult
from app.services.user_service import UserPermissionService
from tests._pg_fixture import unique_code
from tests.chatbot.agent.test_router import FakeJev, arm, jev_answer
from tests.chatbot.test_engine import _envelope, _parser_output, seeded, stub_access, stub_parser  # noqa: F401
from tests.chatbot.test_panel_live_turn import products  # noqa: F401  (fixture)
from tests.chatbot.test_panel_principal import (  # noqa: F401  (fixtures and helpers)
    AGENT,
    USE,
    Staff,
    _scope_listeners,
    grants,
    run_panel,
    seed_staff,
    staff,
    stock_output,
    turn_row,
    world,
)

STOCK = "crm_inventory_stock_balance_list"
STOCK_SLUG = "inventory.stock.view"
CONFIRM_ACTION = "confirm_action"
NOTE_TOOL = "zzt_panel_note"
NOTE_SLUG = "zzt.panel.note.add"
CONSOLE_VIEW = "system.chat_history.view"
PANEL_ACTIONS = "/api/v1/system/ai-assistant/agent/actions"
CONSOLE_ACTIONS = "/api/v1/system/chatbot/agent/actions"

CATALOG = {
    STOCK: {
        "description": "Stock on hand",
        "inputSchema": {
            "type": "object",
            "properties": {"contact_id": {"type": "string"}, "space_id": {"type": "string"}, "query": {"type": "string"}},
            "required": ["contact_id", "space_id", "query"],
        },
    },
}


# --------------------------------------------------------------------------- #
# Fakes and seeds
# --------------------------------------------------------------------------- #


def tc(name: str, args: dict, cid: str) -> dict:
    return {"id": cid, "name": name, "arguments": args}


def round_of(*calls: dict) -> ChatResult:
    return ChatResult(
        content="", prompt_tokens=100, completion_tokens=10, total_tokens=110, cached_tokens=0, tool_calls=list(calls)
    )


def answer_(text_: str, cid: str = "ans-1") -> ChatResult:
    return round_of(tc("answer", {"text": text_, "figures": [], "not_found": [], "not_checked": []}, cid))


class Provider:
    def __init__(self, script):
        self.script = list(script)
        self.seen: list[dict] = []

    def chat(self, messages, *, tools=None, **kw):
        self.seen.append({"messages": copy.deepcopy(messages), "tools": copy.deepcopy(tools)})
        item = self.script.pop(0)
        return item(self.seen[-1]["messages"]) if callable(item) else item

    def tool_names(self, index: int = 0) -> set[str]:
        return {t["function"]["name"] for t in (self.seen[index]["tools"] or [])}


@pytest.fixture()
def audit_listeners():
    from app.audit_context import clear_actor
    from app.services.audit_service import register_audit_listeners

    register_audit_listeners()
    yield
    clear_actor()


@pytest.fixture()
def jev(monkeypatch, session_factory, system_settings_row):
    """Jev armed (key and router prompt present) and scripted."""
    arm(session_factory())
    fake = FakeJev()
    monkeypatch.setattr(jev_client, "classify", fake)
    return fake


@pytest.fixture()
def agent_model(monkeypatch):
    """The agent's model client, scripted. `agent_model.set([...])` installs the replies."""
    box = SimpleNamespace(provider=Provider([]))

    def set_script(script):
        box.provider = Provider(script)

    box.set = set_script
    monkeypatch.setattr(agent_loop, "_resolve_provider", lambda db: (box.provider, "openai", "gpt-test", None))
    monkeypatch.setattr(agent_loop, "_fetch_catalog", lambda: CATALOG)
    monkeypatch.setattr(agent_loop, "catalog_cached", lambda fetch, **kw: CATALOG)
    return box


def set_settings(session_factory, **columns) -> None:
    db = session_factory()
    row = db.query(SystemSetting).first()
    for k, v in columns.items():
        setattr(row, k, v)
    db.commit()


def panel_key(staff_: Staff) -> str:
    return f"panel-{staff_.conv_id}"


def new_thread(session_factory, staff_: Staff) -> Staff:
    db = session_factory()
    conv = AIAssistantConversation(user_id=staff_.user_id, title="ZZT other thread")
    db.add(conv)
    db.commit()
    return Staff(staff_.user_id, str(conv.id), staff_.company_a, staff_.company_b, staff_.phone)


def agent_turn_rows(session_factory, key: str) -> list[ChatbotTurn]:
    return session_factory().query(ChatbotTurn).filter(
        ChatbotTurn.contact_respond_id == key, ChatbotTurn.ingress == "agent"
    ).all()


def stock_then_answer(text_: str = "ZZT stock is fine."):
    return [round_of(tc(STOCK, {"query": "ZZTPRODUCT"}, "c1")), answer_(text_)]


# --------------------------------------------------------------------------- #
# AC-3: who answers, and as whom
# --------------------------------------------------------------------------- #


class TestRouting:
    def test_jev_agent_runs_the_agent_loop_as_the_staff_user(
        self, session_factory, monkeypatch, staff, grants, world, jev, agent_model
    ):
        grants.add(STOCK_SLUG)
        jev.answer = jev_answer("agent", 0.95)
        agent_model.set(stock_then_answer())

        result = run_panel(session_factory, monkeypatch, staff, "why did stock fall in the main warehouse")

        assert result.route == "agent"
        assert result.agent is not None and "ZZT stock is fine." in result.reply_text
        assert [(c["name"], c["status"]) for c in result.agent["tool_calls"]] == [(STOCK, "empty")]  # the fake MCP returns no items
        assert world.blocks == [], "the parser ran for an agent turn"
        rows = agent_turn_rows(session_factory, panel_key(staff))
        assert len(rows) == 1  # present: the agent turn is recorded under the panel key
        for call in [c for c in world.mcp if c["name"] == STOCK]:
            assert call["staff"] is True and call["staff_user_id"] == staff.user_id
            assert not str(call["args"].get("contact_id") or "").strip()
            assert not str(call["args"].get("space_id") or "").strip()
        assert [c for c in world.mcp if c["name"] == STOCK], "the stock tool never reached the MCP seam"

    def test_a_user_lacking_the_stock_slug_is_denied_by_dispatch_and_not_offered_the_tool(
        self, session_factory, monkeypatch, staff, grants, world, jev, agent_model
    ):
        assert STOCK_SLUG not in grants
        jev.answer = jev_answer("agent", 0.95)
        agent_model.set(stock_then_answer("ZZT nothing to show."))

        result = run_panel(session_factory, monkeypatch, staff, "why did stock fall in the main warehouse")

        assert result.route == "agent"
        assert STOCK not in agent_model.provider.tool_names(0), "a tool the user may not use was offered"
        assert [(c["name"], c["status"]) for c in result.agent["tool_calls"]] == [(STOCK, "denied")]
        assert [c for c in world.mcp if c["name"] == STOCK] == []

    def test_a_low_score_goes_to_chat(self, session_factory, monkeypatch, staff, grants, world, jev, agent_model):
        jev.answer = jev_answer("agent", 0.2)
        world.parser_output = stock_output("ZZTLOW")

        result = run_panel(session_factory, monkeypatch, staff, "stock ZZTLOW")

        assert result.route == "chat" and len(jev.calls) == 1  # Jev was asked
        assert world.blocks, "the bot did not answer"
        assert agent_model.provider.seen == []

    def test_a_jev_failure_goes_to_chat(self, session_factory, monkeypatch, staff, grants, world, jev, agent_model):
        jev.error = JevError("timeout", "ReadTimeout")
        world.parser_output = stock_output("ZZTFAIL")

        result = run_panel(session_factory, monkeypatch, staff, "stock ZZTFAIL")

        assert result.route == "chat" and len(jev.calls) == 1
        assert world.blocks and agent_model.provider.seen == []

    def test_an_open_chat_question_stays_on_chat_without_asking_jev(
        self, session_factory, monkeypatch, staff, grants, world, jev, agent_model
    ):
        db = session_factory()
        conv = db.get(AIAssistantConversation, staff.conv_id)
        conv.session_vars = {
            "focus": {"customers": []},
            "open_question": {
                "kind": "customer_pick",
                "options": [{"position": 1, "label": "ZZT Customer A", "entity_type": "customer"}],
                "expects": "pick", "team": None, "asked_at_turn": 1, "payload": {},
            },
            "ideation": None, "access_levels": [], "contains_flyer": False,
        }
        db.commit()
        world.parser_output = _parser_output(message_type="casual", reference_positions=[1], entities=[])

        result = run_panel(session_factory, monkeypatch, staff, "1")

        assert result.route == "chat"
        assert jev.calls == [], "Jev was asked while a chat question was open"
        assert agent_model.provider.seen == []

    def test_jev_reads_the_panel_threads_own_history(
        self, session_factory, monkeypatch, staff, grants, world, jev, agent_model
    ):
        db = session_factory()
        db.add_all([
            AIAssistantMessage(conversation_id=staff.conv_id, role="user", content="ZZT earlier question"),
            AIAssistantMessage(conversation_id=staff.conv_id, role="assistant", content="ZZT earlier answer"),
        ])
        other = new_thread(session_factory, staff)
        db.add(AIAssistantMessage(conversation_id=other.conv_id, role="assistant", content="ZZT OTHER THREAD REPLY"))
        db.commit()
        jev.answer = jev_answer("agent", 0.95)
        agent_model.set([answer_("ZZT ok.")])

        run_panel(session_factory, monkeypatch, staff, "and the month before")

        state = jev.calls[0]["state"]
        flat = json.dumps(state)
        assert "ZZT earlier question" in flat and "ZZT earlier answer" in flat
        assert "ZZT OTHER THREAD REPLY" not in flat, "another thread's history reached Jev"

    def test_a_waiting_proposal_goes_to_the_agent_without_asking_jev(
        self, session_factory, monkeypatch, staff, grants, world, jev, agent_model, note_write
    ):
        grants.add(NOTE_SLUG)
        seed_proposal(session_factory, staff)
        agent_model.set([answer_("ZZT still waiting.")])

        result = run_panel(session_factory, monkeypatch, staff, "hmm what was that again")

        assert result.route == "agent"
        assert jev.calls == []
        assert world.blocks == []


# --------------------------------------------------------------------------- #
# AC-8: caps, rate limit, one turn at a time
# --------------------------------------------------------------------------- #


class TestLimits:
    def test_the_daily_cap_counts_every_panel_thread_of_the_user(
        self, session_factory, monkeypatch, staff, grants, world, jev, agent_model
    ):
        set_settings(session_factory, chatbot_agent_daily_turns=2)
        t2, t3 = new_thread(session_factory, staff), new_thread(session_factory, staff)
        db = session_factory()
        for key in (panel_key(staff), panel_key(t2)):  # one agent turn today on each of two threads
            db.add(ChatbotTurn(
                contact_respond_id=key, message_id=f"ZZT-{key}", ingress="agent", envelope={"text": "q"},
                is_test=True, status="done", trace=[], response={"reply_text": "a", "status": "answered"},
            ))
        db.commit()
        jev.answer = jev_answer("agent", 0.95)
        world.parser_output = stock_output("ZZTCAP")

        result = run_panel(session_factory, monkeypatch, t3, "stock ZZTCAP")

        assert result.route == "chat", "the third thread was not held to the user's cap"
        assert jev.calls == [], "Jev was asked over the cap"
        assert agent_model.provider.seen == []

    def test_under_the_cap_jev_is_asked(self, session_factory, monkeypatch, staff, grants, world, jev, agent_model):
        """Control for the cap test: one agent turn today against a cap of two still reaches Jev."""
        set_settings(session_factory, chatbot_agent_daily_turns=2)
        db = session_factory()
        db.add(ChatbotTurn(
            contact_respond_id=panel_key(staff), message_id="ZZT-one", ingress="agent", envelope={"text": "q"},
            is_test=True, status="done", trace=[], response={"reply_text": "a", "status": "answered"},
        ))
        db.commit()
        jev.answer = jev_answer("agent", 0.95)
        agent_model.set([answer_("ZZT ok.")])

        result = run_panel(session_factory, monkeypatch, staff, "why did sales drop")

        assert len(jev.calls) == 1 and result.route == "agent"

    def test_one_rate_limit_per_user_across_threads(
        self, session_factory, monkeypatch, staff, grants, world, jev, agent_model
    ):
        seen: list[str] = []
        real = agent_loop.enforce_agent_rate_limit
        monkeypatch.setattr(agent_loop, "enforce_agent_rate_limit", lambda uid: seen.append(str(uid)) or real(uid))
        other = new_thread(session_factory, staff)
        jev.answer = jev_answer("agent", 0.95)
        agent_model.set([answer_("ZZT one.")])
        run_panel(session_factory, monkeypatch, staff, "first question")
        agent_model.set([answer_("ZZT two.")])
        run_panel(session_factory, monkeypatch, other, "second question")

        assert seen == [staff.user_id, staff.user_id], seen

    def test_over_the_rate_limit_the_agent_does_not_run(
        self, session_factory, monkeypatch, staff, grants, world, jev, agent_model
    ):
        from app.services import rate_limit

        monkeypatch.setattr(rate_limit, "hit", lambda *a, **k: SimpleNamespace(allowed=False))
        jev.answer = jev_answer("agent", 0.95)
        agent_model.set([answer_("ZZT never.")])

        try:
            result = run_panel(session_factory, monkeypatch, staff, "a question")
            said = (result.reply_text or "").lower()
        except Exception as exc:  # noqa: BLE001 - a 429 is the other allowed outcome
            said = f"{getattr(exc, 'status_code', '')} {exc}".lower()

        assert "429" in said or "too many" in said, said
        assert agent_model.provider.seen == []

    def test_one_turn_at_a_time_per_thread(
        self, session_factory, monkeypatch, staff, grants, world, jev, agent_model
    ):
        jev.answer = jev_answer("agent", 0.95)
        agent_model.set([answer_("ZZT never runs.")])

        with agent_loop.single_flight(panel_key(staff)):  # another turn of this thread is running
            result = run_panel(session_factory, monkeypatch, staff, "a second message")
            assert agent_model.provider.seen == [], "two agent turns ran in one thread"
            assert result.route == "agent" and result.reply_text, "the busy thread said nothing"

            elsewhere = new_thread(session_factory, staff)
            agent_model.set([answer_("ZZT other thread answers.")])
            other = run_panel(session_factory, monkeypatch, elsewhere, "a message in another thread")
            assert "ZZT other thread answers." in other.reply_text


# --------------------------------------------------------------------------- #
# AC-22: proposals, Confirm, Cancel, Withdraw, as the user
# --------------------------------------------------------------------------- #


@pytest.fixture()
def note_write(monkeypatch):
    """A registered write that records who ran it (the real executor, a fake route behind it)."""
    ran: list[dict[str, Any]] = []

    def execute(db, user, args):
        actor = get_actor(db)
        ran.append({
            "user_id": user.get("id"),
            "actor_user_id": getattr(actor, "user_id", None),
            "real_user_id": getattr(actor, "real_user_id", None),
            "auth_method": getattr(actor, "auth_method", None),
            "scope": get_company_scope(db),
        })
        return {"id": str(uuid.uuid4()), "after": {}}

    definition = writes.WriteDef(
        name=NOTE_TOOL, user_permission=NOTE_SLUG, schema={"type": "function", "function": {"name": NOTE_TOOL, "parameters": {"type": "object", "properties": {}}}},
        read_before=lambda db, user, args: {}, summary=lambda args, before: "ZZT write a note",
        execute=execute, record_key="",
    )
    monkeypatch.setitem(writes.WRITES, NOTE_TOOL, definition)
    return ran


def seed_proposal(session_factory, staff_: Staff, *, status: str = "proposed") -> str:
    db = session_factory()
    action_id = str(uuid.uuid4())
    db.add(AgentAction(
        id=action_id, conversation_id=str(uuid.uuid4()), turn_id=str(uuid.uuid4()),
        contact_respond_id=panel_key(staff_), user_id=staff_.user_id, status=status,
        steps=[{"tool": NOTE_TOOL, "args": {}, "before": {}, "shown": {}, "summary": "ZZT write a note", "status": "proposed"}],
    ))
    db.commit()
    return action_id


def action_status(session_factory, action_id: str) -> AgentAction:
    db = session_factory()
    db.expire_all()
    return db.get(AgentAction, action_id)


@pytest.fixture()
def as_user(session_factory):
    """A TestClient that acts as the given user id, on the test database."""

    def make(user_id: str) -> TestClient:
        app.dependency_overrides[get_db] = lambda: session_factory()
        app.dependency_overrides[get_current_user] = lambda: {"id": user_id, "name": "ZZT"}
        app.dependency_overrides[get_current_user_or_api_key] = lambda: {"id": user_id, "name": "ZZT"}
        return TestClient(app, raise_server_exceptions=False)

    yield make
    app.dependency_overrides.clear()


class TestProposalsAsTheUser:
    def test_confirm_through_the_panel_runs_as_the_user_with_an_atomic_claim(
        self, session_factory, staff, grants, as_user, note_write
    ):
        grants.add(NOTE_SLUG)
        action_id = seed_proposal(session_factory, staff)
        client = as_user(staff.user_id)

        first = client.post(f"{PANEL_ACTIONS}/{action_id}/confirm", json={})

        assert first.status_code == 200, first.text
        assert action_status(session_factory, action_id).status == "executed"
        assert len(note_write) == 1
        ran = note_write[0]
        assert ran["user_id"] == staff.user_id and ran["actor_user_id"] == staff.user_id
        assert ran["real_user_id"] == staff.user_id, "an operator was named on a panel write"
        assert ran["auth_method"] == "agent"
        assert ran["scope"] == frozenset({staff.company_a}), "the write ran outside the active company"
        assert action_status(session_factory, action_id).decided_by_user_id == staff.user_id

        second = client.post(f"{PANEL_ACTIONS}/{action_id}/confirm", json={})  # a double click
        assert second.status_code == 409 and len(note_write) == 1, "the change ran twice"

    def test_the_body_carries_no_contact(self, session_factory, staff, grants, as_user, note_write):
        grants.add(NOTE_SLUG)
        action_id = seed_proposal(session_factory, staff)

        resp = as_user(staff.user_id).post(
            f"{PANEL_ACTIONS}/{action_id}/confirm", json={"contact_respond_id": "someone-elses-contact"}
        )

        assert resp.status_code == 200, "a client-sent contact must be ignored, not required"
        assert action_status(session_factory, action_id).contact_respond_id == panel_key(staff)

    def test_the_use_gate_guards_the_panel_routes(self, session_factory, staff, grants, as_user, note_write):
        grants.discard(USE)
        action_id = seed_proposal(session_factory, staff)

        resp = as_user(staff.user_id).post(f"{PANEL_ACTIONS}/{action_id}/confirm", json={})

        assert resp.status_code == 403
        assert note_write == []

    @pytest.mark.parametrize("verb", ["confirm", "cancel", "steps/0/withdraw"])
    def test_another_staff_member_cannot_decide_a_proposal(
        self, verb, session_factory, staff, grants, as_user, note_write
    ):
        grants.add(NOTE_SLUG)
        action_id = seed_proposal(session_factory, staff)
        # control: the owner's own decision on another proposal works, so a 404 below is not a missing route
        control = seed_proposal(session_factory, staff)
        assert as_user(staff.user_id).post(f"{PANEL_ACTIONS}/{control}/cancel", json={}).status_code == 200
        intruder = seed_staff(session_factory)

        resp = as_user(intruder.user_id).post(f"{PANEL_ACTIONS}/{action_id}/{verb}", json={})

        assert resp.status_code in (403, 404), resp.text
        assert action_status(session_factory, action_id).status == "proposed"
        assert note_write == []

    @pytest.mark.parametrize("verb", ["confirm", "cancel", "steps/0/withdraw"])
    def test_a_console_operator_cannot_decide_a_panel_proposal(
        self, verb, session_factory, staff, grants, as_user, note_write
    ):
        grants.update({NOTE_SLUG, CONSOLE_VIEW})
        action_id = seed_proposal(session_factory, staff)
        control = seed_proposal(session_factory, staff)  # control: the panel route works for the owner
        assert as_user(staff.user_id).post(f"{PANEL_ACTIONS}/{control}/cancel", json={}).status_code == 200
        operator = seed_staff(session_factory)

        resp = as_user(operator.user_id).post(
            f"{CONSOLE_ACTIONS}/{action_id}/{verb}", json={"contact_respond_id": panel_key(staff)}
        )

        assert resp.status_code in (403, 404, 409), resp.text
        assert action_status(session_factory, action_id).status == "proposed", "the console decided a panel proposal"
        assert note_write == []

    def test_cancel_through_the_panel_drops_it_without_running_it(self, session_factory, staff, grants, as_user, note_write):
        grants.add(NOTE_SLUG)
        action_id = seed_proposal(session_factory, staff)

        resp = as_user(staff.user_id).post(f"{PANEL_ACTIONS}/{action_id}/cancel", json={})

        assert resp.status_code == 200, resp.text
        assert action_status(session_factory, action_id).status == "cancelled"
        assert note_write == []


class TestWaitingProposal:
    def test_no_quoted_bot_note_while_a_proposal_waits_and_a_yes_confirms(
        self, session_factory, monkeypatch, staff, grants, world, jev, agent_model, note_write
    ):
        grants.add(NOTE_SLUG)
        marker = f"ZZT-BOT-NOTE-{uuid.uuid4().hex[:8]}"
        db = session_factory()
        db.add(AIAssistantMessage(conversation_id=staff.conv_id, role="assistant", content=f"an earlier reply {marker}"))
        db.commit()
        action_id = seed_proposal(session_factory, staff)
        agent_model.set([
            round_of(tc(CONFIRM_ACTION, {"action_id": action_id}, "d1")),
            answer_("ZZT done."),
        ])

        result = run_panel(session_factory, monkeypatch, staff, "yes")

        sent = json.dumps(agent_model.provider.seen[0]["messages"])
        assert marker not in sent, "a quoted bot note reached the model while a change waited for a yes"
        assert action_status(session_factory, action_id).status == "executed"
        assert len(note_write) == 1 and note_write[0]["actor_user_id"] == staff.user_id
        assert result.agent["pending_action"] is None

    def test_the_bot_notes_are_quoted_when_nothing_waits(
        self, session_factory, monkeypatch, staff, grants, world, jev, agent_model
    ):
        """Control for the test above: with no proposal waiting the thread's earlier replies are quoted."""
        marker = f"ZZT-BOT-NOTE-{uuid.uuid4().hex[:8]}"
        db = session_factory()
        db.add(AIAssistantMessage(conversation_id=staff.conv_id, role="assistant", content=f"an earlier reply {marker}"))
        db.commit()
        jev.answer = jev_answer("agent", 0.95)
        agent_model.set([answer_("ZZT ok.")])

        run_panel(session_factory, monkeypatch, staff, "what did you just say")

        assert marker in json.dumps(agent_model.provider.seen[0]["messages"])

    def test_no_yes_in_the_latest_message_means_nothing_runs(
        self, session_factory, monkeypatch, staff, grants, world, jev, agent_model, note_write
    ):
        grants.add(NOTE_SLUG)
        action_id = seed_proposal(session_factory, staff)
        agent_model.set([answer_("ZZT still waiting for your yes.")])

        result = run_panel(session_factory, monkeypatch, staff, "maybe later")

        assert result.route == "agent"
        assert action_status(session_factory, action_id).status == "proposed"
        assert note_write == []


# --------------------------------------------------------------------------- #
# AC-7: report routes on the identity read
# --------------------------------------------------------------------------- #

from tests.test_staff_read_identity import env, mk_user, grant, mk_company  # noqa: E402,F401

REPORT = "/api/v1/order-management/report-ask"
RANGE = "date_from=2026-10-01&date_to=2026-10-31"


class TestStaffReadRoutes:
    def test_report_ask_runs_for_a_staff_identity_with_a_blank_pair(self, env):
        staff_id = mk_user(env.db, "holder", perms=("order_management.orders.view", "sales.reports.view"), companies=(env.co_a,), last_active=env.co_a)

        resp = env.client.get(f"{REPORT}?basis=invoiced&{RANGE}", headers=env.ident(staff_id))

        assert resp.status_code not in (403, 422), (resp.status_code, resp.text[:300])

    def test_a_plain_key_with_a_blank_pair_stays_422(self, env):
        resp = env.client.get(f"{REPORT}?basis=invoiced&{RANGE}", headers=env.plain())

        assert resp.status_code == 422 and "contact_identity_required" in resp.text

    def test_the_header_with_a_non_blank_pair_still_403s(self, env):
        staff_id = mk_user(env.db, "holder2", perms=("order_management.orders.view", "sales.reports.view"), companies=(env.co_a,), last_active=env.co_a)

        resp = env.client.get(
            f"{REPORT}?basis=invoiced&{RANGE}&contact_id=zzt-c&space_id=zzt-s", headers=env.ident(staff_id)
        )

        assert resp.status_code == 403, resp.text

    @pytest.mark.parametrize(
        "basis, slug, code",
        [
            ("invoiced", "sales.reports.view", "invoiced_needs_sales_reports"),
            ("unpaid", "finance.billing_documents.view", "unpaid_needs_finance_view"),
        ],
    )
    def test_the_invoiced_and_unpaid_gates_ask_both_users(self, env, basis, slug, code):
        base = ("order_management.orders.view",)
        query = f"basis={basis}" + ("" if basis == "unpaid" else f"&{RANGE}")

        # staff holds the slug, the act-as user lacks it
        env.use_actas(perms=base)
        staff_has = mk_user(env.db, "staff-has", perms=base + (slug,), companies=(env.co_a,), last_active=env.co_a)
        refused = env.client.get(f"{REPORT}?{query}", headers=env.ident(staff_has))
        assert refused.status_code == 403 and code in refused.text, refused.text[:300]

        # act-as holds the slug, the staff member lacks it
        env.use_actas(perms=base + (slug,))
        staff_lacks = mk_user(env.db, "staff-lacks", perms=base, companies=(env.co_a,), last_active=env.co_a)
        refused = env.client.get(f"{REPORT}?{query}", headers=env.ident(staff_lacks))
        assert refused.status_code == 403 and code in refused.text, refused.text[:300]

        # both hold it
        env.use_actas(perms=base + (slug,))
        both = mk_user(env.db, "staff-both", perms=base + (slug,), companies=(env.co_a,), last_active=env.co_a)
        ok = env.client.get(f"{REPORT}?{query}", headers=env.ident(both))
        assert ok.status_code not in (403, 422), (ok.status_code, ok.text[:300])

    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/sales/target-progress",
            "/api/v1/sales/analysis",
            "/api/v1/scm/low-stock-report",
        ],
    )
    def test_the_listed_chatbot_routes_accept_the_identity_read_with_a_blank_pair_and_a_plain_key_stays_422(
        self, env, path
    ):
        staff_id = mk_user(
            env.db, "holder3",
            perms=("sales.targets.view", "sales.reports.view", "scm.reorder.run", "order_management.orders.view"),
            companies=(env.co_a,), last_active=env.co_a,
        )

        plain = env.client.get(path, headers=env.plain())
        ident = env.client.get(path, headers=env.ident(staff_id))

        assert plain.status_code == 422, (plain.status_code, plain.text[:200])
        assert ident.status_code != 422, f"{path} still demands a contact pair for an identity read"
        assert ident.status_code != 403 or "contact" not in ident.text.lower(), ident.text[:200]


# --------------------------------------------------------------------------- #
# AC-13: files reach My Downloads, never a WhatsApp claim
# --------------------------------------------------------------------------- #


class TestFilesGoToMyDownloads:
    def test_a_staff_low_stock_report_lands_in_the_users_downloads_with_no_whatsapp_claim(self, env, monkeypatch):
        from sqlalchemy import text
        from app.services import queue_service

        queued: list[str] = []
        monkeypatch.setattr(queue_service, "enqueue_job", lambda f, *a, **k: queued.append(getattr(f, "__name__", "")) or SimpleNamespace(id="zzt"))
        staff_id = mk_user(env.db, "low", perms=("scm.reorder.run", "inventory.stock.view"), companies=(env.co_a,), last_active=env.co_a)

        resp = env.client.get("/api/v1/scm/low-stock-report", headers=env.ident(staff_id))

        assert resp.status_code in (200, 202), (resp.status_code, resp.text[:300])
        rows = env.db.execute(
            text("SELECT user_id, deliver_to_contact_id FROM user_downloads WHERE user_id = :u"), {"u": staff_id}
        ).all()
        assert rows, "no file was made for the staff member in My Downloads"
        assert all(r.deliver_to_contact_id is None for r in rows), "a WhatsApp delivery was claimed"

    def test_a_staff_sales_analysis_file_has_no_whatsapp_claim(self, env, monkeypatch):
        from sqlalchemy import text
        from app.services import queue_service

        monkeypatch.setattr(queue_service, "enqueue_job", lambda f, *a, **k: SimpleNamespace(id="zzt"))
        staff_id = mk_user(env.db, "sales", perms=("sales.reports.view", "order_management.orders.view"), companies=(env.co_a,), last_active=env.co_a)

        resp = env.client.get("/api/v1/sales/analysis", headers=env.ident(staff_id))

        assert resp.status_code not in (403, 422), (resp.status_code, resp.text[:300])
        claimed = env.db.execute(
            text("SELECT count(*) FROM user_downloads WHERE deliver_to_contact_id IS NOT NULL")
        ).scalar()
        assert claimed == 0


# --------------------------------------------------------------------------- #
# AC-12: logging an opportunity, as the user
# --------------------------------------------------------------------------- #

from tests.chatbot.test_opportunity_lane import _all_four, _yes  # noqa: E402


def seed_salesperson(session_factory, staff_: Staff, world_):
    """The user is a sales agent (through a linked contact) with one customer in the active company."""
    from sqlalchemy import text

    from app.models.order import Customer
    from app.models.sales_agent import SalesAgent
    from app.services.sales import sales_seed_service

    db = session_factory()
    sales_seed_service.run(db)
    contact_pk = str(uuid.uuid4())
    db.execute(
        text("INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) VALUES (:i, :r, :p, '{}'::jsonb)"),
        {"i": contact_pk, "r": unique_code("sp"), "p": "+6011" + uuid.uuid4().hex[:7]},
    )
    db.query(User).filter(User.id == staff_.user_id).update({"respond_contact_id": contact_pk})
    agent = SalesAgent(id=str(uuid.uuid4()), sales_agent=unique_code("AG"), contact_id=contact_pk, company_id=staff_.company_a, is_active=True)
    db.add(agent)
    db.flush()
    db.add(Customer(id=str(uuid.uuid4()), company_id=staff_.company_a, customer_code=unique_code("CU")[:40],
                    customer_name="Bath Idea", sales_agent_id=agent.id))
    db.commit()


class TestOpportunity:
    def test_a_user_with_the_slug_gets_a_real_row_with_their_name_on_it(
        self, session_factory, monkeypatch, staff, grants, world, audit_listeners
    ):
        from app.models.audit import AuditLog
        from app.models.base import company_scope
        from app.models.sales import SalesOpportunity

        grants.add("sales.opportunities.add")
        world.opportunity = True
        seed_salesperson(session_factory, staff, world)
        world.parser_output = _all_four()
        run_panel(session_factory, monkeypatch, staff, "log an opportunity for Bath Idea")
        world.parser_output = _yes()

        result = run_panel(session_factory, monkeypatch, staff, "yes")

        db = session_factory()
        with company_scope(db, None):  # this read is not the staff session: see every company's rows
            rows = db.query(SalesOpportunity).filter(SalesOpportunity.title == "condo job Taman X").all()
            assert len(rows) == 1, f"no opportunity row: {result.reply_text!r}"
            assert rows[0].created_by_user_id == staff.user_id
            assert str(rows[0].company_id) == staff.company_a
            assert "crm_sales_opportunity_log" not in [c["name"] for c in world.mcp], "the write went out through MCP, not as the user"
            audit = db.query(AuditLog).filter(AuditLog.entity_id == str(rows[0].id), AuditLog.action == "CREATE").all()
        assert audit and all(str(a.user_id) == staff.user_id for a in audit), "the audit row does not name the user"

    def test_a_user_with_agents_and_without_the_slug_is_refused_in_words_on_the_first_message(
        self, session_factory, monkeypatch, staff, grants, world
    ):
        from app.models.base import company_scope
        from app.models.sales import SalesOpportunity

        assert "sales.opportunities.add" not in grants
        world.opportunity = True
        seed_salesperson(session_factory, staff, world)
        world.parser_output = _all_four()

        result = run_panel(session_factory, monkeypatch, staff, "log an opportunity for Bath Idea")

        said = result.reply_text.lower()
        assert "opportunit" in said and ("not enabled" in said or "permission" in said or "not allowed" in said), result.reply_text
        assert "reply yes" not in said, "a read-back was offered to someone who may not log"
        with company_scope(session_factory(), None):
            assert session_factory().query(SalesOpportunity).count() == 0


# --------------------------------------------------------------------------- #
# AC-14, AC-15, AC-25: escalation
# --------------------------------------------------------------------------- #

from tests.chatbot._turn_helpers import verdict  # noqa: E402
from tests.chatbot.test_fail_triage_escalation import (  # noqa: E402,F401
    _assigned,
    _help,
    _observe,
    _reply_text,
    _say,
    _seed_company,
    _seed_contact,
    _seed_pair,
)

TEAM = "customer_service"
AGENT_CODE = "order_enquiries"


def add_member(session_factory, company_id: str, name: str) -> str:
    """A second active member on the team `_seed_pair` made, after the first (sort_order 2)."""
    from app.models.access import AgentTeam, TeamMember

    from tests.chatbot.test_fail_triage_escalation import _db

    db = _db(session_factory, company_id)
    team_id = db.query(AgentTeam.team_id).filter(AgentTeam.company_id == company_id, AgentTeam.code == TEAM).scalar()
    user = User(id=str(uuid.uuid4()), email=f"{unique_code('m').lower()}@zzt.test", name=name, status="ACTIVE",
                respond_user_id=str(uuid.uuid4().int)[:9])
    db.add(user)
    db.flush()
    db.add(TeamMember(id=str(uuid.uuid4()), team_id=team_id, user_id=user.id, sort_order=2))
    db.commit()
    return user.id


def bind_policy(session_factory, company_id: str) -> str:
    """Bind the company's NORMAL SLA policy to its agent_teams links. `_seed_pair` binds none, and a
    pair with no bound policy fails honestly (no fallback), on the panel as on WhatsApp."""
    from app.models.access import AgentTeam
    from app.models.sla import SLAPolicy
    from app.services.chatbot.lanes.escalation import NEXT_ASSIGNEE_POLICY_CODE
    from tests.chatbot.test_fail_triage_escalation import _db

    db = _db(session_factory, company_id)
    policy_id = db.query(SLAPolicy.id).filter(
        SLAPolicy.code == NEXT_ASSIGNEE_POLICY_CODE, SLAPolicy.company_id == company_id
    ).scalar()
    db.query(AgentTeam).filter(AgentTeam.company_id == company_id).update({"policy_id": policy_id})
    db.commit()
    return str(policy_id)


def panel_trackings(session_factory):
    from app.models.sla import ConversationSLATracking

    return session_factory().query(ConversationSLATracking).filter(
        ConversationSLATracking.respond_contact_id.is_(None)
    ).all()


class TestPanelEscalation:
    def _escalate(self, session_factory, monkeypatch, staff, world):
        world.parser_output = verdict(message_type="request_for_help", domain_hint="order")
        return run_panel(session_factory, monkeypatch, staff, "can someone help me with my order")

    def test_an_sla_row_with_no_contact_goes_to_the_round_robin_member_and_the_cursor_moves(
        self, session_factory, monkeypatch, staff, grants, world
    ):
        first = _seed_pair(session_factory, company_id=staff.company_a, agent_code=AGENT_CODE, team_code=TEAM)
        bind_policy(session_factory, staff.company_a)
        second = add_member(session_factory, staff.company_a, "ZZT Second PIC")

        one = self._escalate(session_factory, monkeypatch, staff, world)
        rows = panel_trackings(session_factory)
        assert len(rows) == 1, f"no contactless SLA row: {one.reply_text!r}"
        assert rows[0].assigned_to_id in (first, second) and str(rows[0].company_id) == staff.company_a
        assert rows[0].respond_contact_id is None

        self._escalate(session_factory, monkeypatch, new_thread(session_factory, staff), world)
        assigned = [r.assigned_to_id for r in sorted(panel_trackings(session_factory), key=lambda r: r.created_at)]
        assert len(assigned) == 2 and assigned[0] != assigned[1], "the shared cursor did not advance"
        assert {assigned[0], assigned[1]} == {first, second}

    def test_the_assignee_has_an_in_app_notification_a_my_pending_entry_and_no_whatsapp(
        self, session_factory, monkeypatch, staff, grants, world
    ):
        from app.models.notification import Notification
        from app.services.notification_service import NotificationService
        from app.services.sla_service import ConversationSLATrackingService

        member = _seed_pair(session_factory, company_id=staff.company_a, agent_code=AGENT_CODE, team_code=TEAM)
        bind_policy(session_factory, staff.company_a)
        db = session_factory()
        db.query(User).filter(User.id == member).update(
            {"notify_whatsapp_on_assignment": True, "notify_email_on_assignment": False}
        )
        db.commit()
        channels: list[dict[str, Any]] = []
        real = NotificationService.create_with_channel_preferences

        def spy(self, **kw):
            channels.append({k: kw.get(k) for k in ("user_id", "send_in_app", "send_email", "send_whatsapp")})
            return real(self, **kw)

        monkeypatch.setattr(NotificationService, "create_with_channel_preferences", spy)

        self._escalate(session_factory, monkeypatch, staff, world)

        rows = panel_trackings(session_factory)
        assert len(rows) == 1
        mine = [c for c in channels if c["user_id"] == member]
        assert mine, "the assignee was never notified"
        assert all(c["send_whatsapp"] is False for c in mine), "a WhatsApp message was asked for although the task has no contact"
        assert any(c["send_in_app"] for c in mine)
        notes = session_factory().query(Notification).filter(Notification.user_id == member, Notification.type == "conversation_sla").all()
        assert notes, "no in-app notification row"
        pending = ConversationSLATrackingService(session_factory()).list_my_pending(member)
        assert str(rows[0].id) in {str(p.get("id")) for p in pending}, "the task is not in My Pending"
        assert world.respond_sends == [] and not [u for u in world.http if "respond" in u]

    def test_the_reply_names_the_person_and_promises_nothing_it_cannot_keep(
        self, session_factory, monkeypatch, staff, grants, world
    ):
        _seed_pair(session_factory, company_id=staff.company_a, agent_code=AGENT_CODE, team_code=TEAM)
        bind_policy(session_factory, staff.company_a)

        result = self._escalate(session_factory, monkeypatch, staff, world)

        lowered = result.reply_text.lower()
        assert "zzt customer_service pic" in lowered, result.reply_text
        assert "follow up" in lowered
        assert "reply shortly" not in lowered and "routed to your pic" not in lowered
        kinds = {a.get("kind") for a in (turn_row(session_factory, result.turn_id).response or {}).get("actions", [])}
        assert not kinds & {"assign_conversation", "add_comment"}, kinds

    def test_an_unbound_pair_fails_honestly_with_no_row_and_no_draw(
        self, session_factory, monkeypatch, staff, grants, world
    ):
        """The pair links a team but no SLA policy is bound to it: no fallback, so no row and no
        promise, as on WhatsApp."""
        import app.api.v1.external.next_assignee as next_assignee_mod

        draws: list[Any] = []
        real = next_assignee_mod.post_next_assignee
        monkeypatch.setattr(next_assignee_mod, "post_next_assignee", lambda *a, **k: draws.append(1) or real(*a, **k))
        _seed_pair(session_factory, company_id=staff.company_a, agent_code=AGENT_CODE, team_code=TEAM)  # no policy bound

        result = self._escalate(session_factory, monkeypatch, staff, world)

        lowered = result.reply_text.lower()
        assert result.reply_text.strip() and "follow up" not in lowered
        assert "reply shortly" not in lowered and "routed to your pic" not in lowered
        assert panel_trackings(session_factory) == []

    def test_no_team_gives_an_honest_reply_no_row_and_the_cursor_unmoved(
        self, session_factory, monkeypatch, staff, grants, world
    ):
        import app.api.v1.external.next_assignee as next_assignee_mod
        from tests.chatbot.test_fail_triage_escalation import _unconfigured_company

        draws: list[Any] = []
        real = next_assignee_mod.post_next_assignee

        def wrapped(*a, **k):
            out = real(*a, **k)
            draws.append(out)
            return out

        monkeypatch.setattr(next_assignee_mod, "post_next_assignee", wrapped)
        # the company links nothing the topic map can reach
        _seed_pair(session_factory, company_id=staff.company_a, agent_code="it_support", team_code="it_admin")

        result = self._escalate(session_factory, monkeypatch, staff, world)

        assert result.reply_text.strip(), "the panel got no reply"
        lowered = result.reply_text.lower()
        assert "reply shortly" not in lowered and "routed to your pic" not in lowered
        assert "follow up" not in lowered, "a follow-up was promised with nobody to follow up"
        assert panel_trackings(session_factory) == []
        assert draws == [], f"the cursor moved: {draws}"


class TestWhatsAppEscalationUnchanged:
    """AC-25: a customer's escalation still needs the phone, a contact row and the cursor."""

    def test_a_whatsapp_escalation_still_draws_with_the_contacts_phone_and_a_contact_row(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ):
        from app.services.chatbot import engine as engine_mod

        company = _seed_company(session_factory, "ZZT Company Order")
        _seed_contact(session_factory, phone="+60970000002", company_id=company)
        _seed_pair(session_factory, company_id=company, agent_code=AGENT_CODE, team_code=TEAM)
        seams = _observe(monkeypatch)
        stub_parser(_help(domain_hint="order"))
        stub_access()

        result = engine_mod.run_turn(_say("ac25-1", "can someone help me with my order"), session_factory=session_factory)

        assert seams.pairs() == [(AGENT_CODE, TEAM)]
        assert seams.live_bodies()[0].get("contact_phone_number") == "+60970000002"
        assert len(seams.sla) == 1, "the SLA row was not created"
        payload = seams.sla[0]
        assert getattr(payload, "contact_phone_number", None) == "+60970000002"
        assert _assigned(result), result.actions


# --------------------------------------------------------------------------- #
# Escalation runner: contactless rows never starve a customer's escalation
# --------------------------------------------------------------------------- #


def _overdue_row(db, *, company_id: str, policy_id: str, contact_id: str | None):
    from datetime import timedelta

    from app.models.sla import ConversationSLATracking

    now = datetime.utcnow()
    row = ConversationSLATracking(
        id=str(uuid.uuid4()), respond_contact_id=contact_id, policy_id=policy_id, current_tier=1,
        initiated_at=now - timedelta(hours=30), current_tier_started_at=now - timedelta(hours=30),
        due_at=now - timedelta(hours=20), company_id=company_id, is_responded=False, is_resolved=False,
        message_id=uuid.uuid4().int % 10**12,
    )
    db.add(row)
    db.flush()
    return row


def test_list_due_escalations_skips_contactless_rows_and_still_returns_a_customers(session_factory, staff):
    """services/sla_service.py:3386. A null-contact row (a panel escalation) and a row whose contact was
    deleted (the FK sets it NULL) would answer 404 at the runner and block everything behind them."""
    from sqlalchemy import text

    from app.services.sla_service import ConversationSLATrackingService

    _seed_pair(session_factory, company_id=staff.company_a, agent_code=AGENT_CODE, team_code=TEAM)
    policy_id = bind_policy(session_factory, staff.company_a)
    db = session_factory()
    pks = []
    for tag in ("gone", "kept"):
        pk = str(uuid.uuid4())
        db.execute(
            text("INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) VALUES (:i, :r, :p, '{}'::jsonb)"),
            {"i": pk, "r": unique_code(tag), "p": "+6012" + uuid.uuid4().hex[:7]},
        )
        pks.append(pk)
    null_row = _overdue_row(db, company_id=staff.company_a, policy_id=policy_id, contact_id=None)
    deleted_row = _overdue_row(db, company_id=staff.company_a, policy_id=policy_id, contact_id=pks[0])
    customer_row = _overdue_row(db, company_id=staff.company_a, policy_id=policy_id, contact_id=pks[1])
    db.commit()
    db.execute(text("DELETE FROM respond_contacts WHERE id = :i"), {"i": pks[0]})
    db.commit()
    db.expire_all()
    assert db.get(type(deleted_row), deleted_row.id).respond_contact_id is None, "fixture: the delete did not null the contact"

    due = {item["tracking_id"] for item in ConversationSLATrackingService(session_factory()).list_due_escalations()}

    assert str(customer_row.id) in due, "a customer's overdue row was not returned"
    assert str(null_row.id) not in due and str(deleted_row.id) not in due


# --------------------------------------------------------------------------- #
# Notification channels on a contactless row: reassign, deadline extended, coverage copies
# --------------------------------------------------------------------------- #


class TestNoWhatsAppOnAContactlessRow:
    def test_reassign_extend_and_coverage_copies_never_ask_for_whatsapp(
        self, session_factory, monkeypatch, staff, grants, world
    ):
        from app.services import coverage_subscription_service
        from app.services.notification_service import NotificationService
        from app.services.sla_service import ConversationSLATrackingService

        member = _seed_pair(session_factory, company_id=staff.company_a, agent_code=AGENT_CODE, team_code=TEAM)
        bind_policy(session_factory, staff.company_a)
        db = session_factory()
        db.query(User).filter(User.id == member).update({
            "notify_whatsapp_on_assignment": True, "notify_whatsapp_on_escalation": True,
            "notify_whatsapp_on_deadline_extended": True,
        })
        db.commit()
        TestPanelEscalation()._escalate(session_factory, monkeypatch, staff, world)
        row = panel_trackings(session_factory)[0]

        asked: list[dict[str, Any]] = []
        real = NotificationService.create_with_channel_preferences
        monkeypatch.setattr(
            NotificationService, "create_with_channel_preferences",
            lambda self, **kw: asked.append({"event": kw.get("event_type"), "wa": kw.get("send_whatsapp")}) or real(self, **kw),
        )
        copies: list[Any] = []
        monkeypatch.setattr(
            coverage_subscription_service, "fan_out_coverage_copies",
            lambda *a, **kw: copies.append(kw.get("send_whatsapp")),
        )
        service = ConversationSLATrackingService(session_factory())
        other = seed_staff(session_factory)

        service._notify_reassignment(row, actor_id=other.user_id, new_assignee_id=member, old_assignee_id=None)
        service._notify_user_deadline_extended(row, recipient_user_id=member, reason="ZZT more time")
        service._fan_out_assignment_coverage(row)

        assert asked, "no notification was made at all"
        assert all(a["wa"] is False for a in asked), asked
        assert copies and all(c is False for c in copies), f"coverage copies asked for WhatsApp: {copies}"
        assert world.respond_sends == [] and not [u for u in world.http if "respond" in u]


# --------------------------------------------------------------------------- #
# AC-22: Withdraw, through the panel route, on a parked step
# --------------------------------------------------------------------------- #


def test_withdraw_through_the_panel_route_cancels_a_parked_step_as_the_user(
    session_factory, monkeypatch, staff, grants, as_user, note_write
):
    from datetime import timedelta

    import app.api.v1.sla.form_actions as form_actions

    grants.add(NOTE_SLUG)
    pending_id = str(uuid.uuid4())
    cancelled: list[dict[str, Any]] = []
    monkeypatch.setattr(
        form_actions, "cancel_form_action",
        lambda action_id, current_user, db: cancelled.append({"id": action_id, "user": current_user.get("id")}),
    )
    due = (datetime.utcnow() + timedelta(seconds=60)).isoformat()
    db = session_factory()
    action_id = str(uuid.uuid4())
    db.add(AgentAction(
        id=action_id, conversation_id=str(uuid.uuid4()), turn_id=str(uuid.uuid4()),
        contact_respond_id=panel_key(staff), user_id=staff.user_id, status="executed",
        steps=[{"tool": NOTE_TOOL, "args": {}, "before": {}, "shown": {}, "summary": "ZZT parked", "status": "done",
                "after": {"deferred": True, "commit_at": due, "window_seconds": 60, "pending_action_id": pending_id}}],
    ))
    db.commit()

    resp = as_user(staff.user_id).post(f"{PANEL_ACTIONS}/{action_id}/steps/0/withdraw", json={})

    assert resp.status_code == 200, resp.text
    assert cancelled == [{"id": pending_id, "user": staff.user_id}]
    db.expire_all()
    assert db.get(AgentAction, action_id).steps[0]["status"] == "withdrawn"


# --------------------------------------------------------------------------- #
# AC-8: a deleted thread still counts toward the cap
# --------------------------------------------------------------------------- #


def test_a_deleted_thread_still_counts_toward_the_daily_cap(
    session_factory, monkeypatch, staff, grants, world, jev, agent_model
):
    """Deleting a thread must not hand the user their turns back. The cap counts the user's agent turns
    today, not their surviving threads."""
    set_settings(session_factory, chatbot_agent_daily_turns=2)
    gone = new_thread(session_factory, staff)
    db = session_factory()
    for n in range(2):
        db.add(ChatbotTurn(
            contact_respond_id=panel_key(gone), message_id=f"ZZT-gone-{n}", ingress="agent", envelope={"text": "q", "user_id": staff.user_id},
            is_test=True, status="done", trace=[], response={"reply_text": "a", "status": "answered"},
        ))
    db.commit()
    db.delete(db.get(AIAssistantConversation, gone.conv_id))
    db.commit()
    jev.answer = jev_answer("agent", 0.95)
    world.parser_output = stock_output("ZZTGONE")

    result = run_panel(session_factory, monkeypatch, staff, "stock ZZTGONE")

    assert result.route == "chat", "deleting a thread reset the user's cap"
    assert jev.calls == []


# --------------------------------------------------------------------------- #
# AC-5/AC-7: staff reveals and the chat dataset
# --------------------------------------------------------------------------- #


def test_staff_reveal_keys_follow_the_users_slugs(env):
    """contact_field_reveal_service._STAFF_REVEAL_SLUGS: one real reveal, a holder and a non-holder."""
    from app.services.contact_field_reveal_service import staff_reveal_keys

    holder = mk_user(env.db, "rev-holder", perms=("sales.reports.view",))
    other = mk_user(env.db, "rev-other", perms=("inventory.stock.view",))

    assert "sales_orders.sales_report" in staff_reveal_keys(env.db, holder)
    assert "sales_orders.sales_report" not in staff_reveal_keys(env.db, other)
    assert "inventory.sellable" in staff_reveal_keys(env.db, other)  # present for the user who holds its slug


def test_report_ask_chat_dataset_has_a_staff_path_gated_by_the_analytics_reveal(env):
    perms = ("order_management.orders.view",)
    holder = mk_user(env.db, "chat-holder", perms=perms + ("chatbot.analytics.view",), companies=(env.co_a,), last_active=env.co_a)
    other = mk_user(env.db, "chat-other", perms=perms, companies=(env.co_a,), last_active=env.co_a)
    env.use_actas(perms=perms + ("chatbot.analytics.view",))
    query = f"dataset=chat&{RANGE}"

    ok = env.client.get(f"{REPORT}?{query}", headers=env.ident(holder))
    refused = env.client.get(f"{REPORT}?{query}", headers=env.ident(other))
    plain = env.client.get(f"{REPORT}?{query}", headers=env.plain())

    assert ok.status_code not in (403, 422), (ok.status_code, ok.text[:300])
    assert refused.status_code == 403, (refused.status_code, refused.text[:300])
    assert plain.status_code == 422
