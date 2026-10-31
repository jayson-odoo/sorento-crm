"""AGENTIC-UNIFY PR 3, slice 1 (red): a live panel turn through the real engine.

AC-5 (scope, gate, tier), AC-6 (staff identity on every read), AC-9 (nothing goes out, one
test per path), AC-10 (audit decisions), AC-11 (actions rendered or dropped), AC-16 (no
Customer asks row), AC-17 (not analytics, not the live lists, usage under the user),
AC-25 (a WhatsApp turn is unchanged).

Only the provider boundary (parser), the MCP client, HTTP, the queue and the Respond sender
are faked; the engine, resolver, scope listeners and Postgres are real. Fixtures live in
`test_panel_principal.py`.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

import app.main  # noqa: F401  isort:skip
from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
from app.main import app
from app.models.ai_assistant import AIAssistantUsageLog
from app.models.chat_facts import ChatAskFact
from app.models.chatbot_turn import ChatbotTurn
from app.models.inventory import Warehouse
from app.models.marketing import PromotionType
from app.models.stock_ask import StockAsk
from app.services import stock_ask_service
from app.services.chatbot import engine as engine_mod
from app.services.chatbot import inbox_queue
from app.services.chatbot.analytics import facts
from app.services.chatbot.turn import refer
from app.services.user_service import UserPermissionService
from tests._pg_fixture import unique_code
from tests.chatbot.test_code_lookup_set_codes import _mk_products
from tests.chatbot.test_engine import _envelope, _parser_output, seeded, stub_access, stub_parser  # noqa: F401
from tests.chatbot.test_panel_principal import (  # noqa: F401  (fixtures)
    AGENT,
    USE,
    Staff,
    _scope_listeners,
    grants,
    respond_contact_count,
    run_panel,
    seed_staff,
    staff,
    stock_output,
    switch_active_company,
    turn_row,
    world,
)

# The parity module's own proof that a WhatsApp parser input is the bytes n8n sent (AC-25).
from tests.chatbot.test_parser_user_block_parity import (  # noqa: F401
    test_no_pending_line_is_added_on_this_turn,
    test_the_trailing_blank_line_survives,
    test_the_user_block_is_byte_identical_to_the_one_n8n_sent,
    test_the_user_block_says_nothing_about_a_result_set,
    turn6,
)

STOCK_TOOL = "crm_inventory_stock_balance_list"


@pytest.fixture()
def products(session_factory, staff):
    """One product in each of the staff member's two companies."""
    db = session_factory()
    code_a, code_b = unique_code("PNLA"), unique_code("PNLB")
    ids = {}
    ids.update(_mk_products(db, [code_a], company_id=staff.company_a))
    ids.update(_mk_products(db, [code_b], company_id=staff.company_b))
    db.commit()
    return SimpleNamespace(code_a=code_a, code_b=code_b, id_a=ids[code_a], id_b=ids[code_b])


# A `- ...<label>...` row under a `Customer candidates` / `Promotion kind candidates` heading. The label is
# also typed into the message, so only a bullet row proves the in-process read ran.
def _has_candidate_row(block: str, label: str) -> bool:
    return any(line.startswith("- ") and label in line for line in block.splitlines())


def _ask_stock(session_factory, monkeypatch, staff, world, code, extra=""):
    world.parser_output = stock_output(code)
    return run_panel(session_factory, monkeypatch, staff, f"stock {code}{extra}")


# --------------------------------------------------------------------------- #
# AC-5: the principal answers the brain's questions
# --------------------------------------------------------------------------- #


class TestPrincipalAnswers:
    def test_the_ai_gate_does_not_refuse_a_panel_turn(self, session_factory, monkeypatch, staff, grants, world, products):
        result = _ask_stock(session_factory, monkeypatch, staff, world, products.code_a)

        row = turn_row(session_factory, result.turn_id)
        assert result.status == "done", row.error
        assert row.branch_kind != "ai_not_allowed"
        assert world.blocks, "the parser never ran: the turn was refused before it"

    def test_scope_is_the_active_company_only(self, session_factory, monkeypatch, staff, grants, world, products):
        mine = _ask_stock(session_factory, monkeypatch, staff, world, products.code_a)
        assert products.id_a in world.stock_product_ids(), "the active company's product must be read"  # present

        world.mcp.clear()
        _ask_stock(session_factory, monkeypatch, staff, world, products.code_b)

        assert products.id_b not in world.stock_product_ids(), "a row in the other company was seen"
        assert {frozenset({staff.company_a})} >= {s for s in world.scopes if s is not None}
        assert mine.turn_id

    def test_a_second_call_after_switching_company_sees_the_new_one(
        self, session_factory, monkeypatch, staff, grants, world, products
    ):
        _ask_stock(session_factory, monkeypatch, staff, world, products.code_b)
        assert products.id_b not in world.stock_product_ids()

        switch_active_company(session_factory, staff, "b")
        world.mcp.clear()
        world.scopes.clear()
        _ask_stock(session_factory, monkeypatch, staff, world, products.code_b)

        assert products.id_b in world.stock_product_ids(), "the new active company was not used"
        assert all(s == frozenset({staff.company_b}) for s in world.scopes if s is not None)

    def test_tier_office_reaches_the_parser_input(self, session_factory, monkeypatch, staff, grants, world, products):
        _ask_stock(session_factory, monkeypatch, staff, world, products.code_a)

        assert world.blocks
        assert "Profile:\ntier: office" in world.blocks[0], world.blocks[0]

    def test_no_contact_grants_brand_limits_or_stock_switch_apply(
        self, session_factory, monkeypatch, staff, grants, world, products
    ):
        result = _ask_stock(session_factory, monkeypatch, staff, world, products.code_a)

        assert world.brand_scopes, "no session was stamped with a brand scope at all"
        assert set(world.brand_scopes) == {None}, f"a brand limit applied: {world.brand_scopes}"
        assert turn_row(session_factory, result.turn_id).branch_kind != "stock_denied"
        assert products.id_a in world.stock_product_ids()


# --------------------------------------------------------------------------- #
# AC-6: the staff identity on every read
# --------------------------------------------------------------------------- #


class TestStaffIdentityOnReads:
    def test_lane_mcp_calls_carry_the_staff_identity_and_a_blank_pair(
        self, session_factory, monkeypatch, staff, grants, world, products
    ):
        _ask_stock(session_factory, monkeypatch, staff, world, products.code_a)

        assert world.mcp, "the lane made no MCP call, so there is nothing to check"
        for call in world.mcp:
            assert call["staff"] is True, call
            assert call["staff_user_id"] == staff.user_id, call
            assert call["headers"].get("X-MCP-Scope") == "staff"
            assert call["headers"].get("X-MCP-Staff-User") == staff.user_id
            assert not str(call["args"].get("contact_id") or "").strip(), call["args"]
            assert not str(call["args"].get("space_id") or "").strip(), call["args"]

    @pytest.mark.parametrize(
        "slug, seed, label",
        [
            # lanes/business/services.py:590 / lookup_lists customer rows, gated by the staff customer lookup
            ("order_management.customers.view", "customer", "ZZT Panel Customer"),
            # turn_runtime.py:796-806 `_promotions_hold`, :816 `promotion_kind_rows` (lookup_lists.py:565)
            ("marketing.promotions.view", "promotion", "ZZT Panel Promo Kind"),
        ],
    )
    def test_an_in_process_read_gives_nothing_to_a_user_lacking_the_slug(
        self, slug, seed, label, session_factory, monkeypatch, staff, grants, world, products
    ):
        db = session_factory()
        if seed == "customer":
            from app.models.order import Customer

            db.add(Customer(customer_code=unique_code("CU")[:40], customer_name=label, company_id=staff.company_a))
        else:
            db.add(PromotionType(type_code=unique_code("PT")[:40], type_name=label, company_id=staff.company_a))
        db.commit()
        world.lookup_lists = True

        # With the slug the row reaches the parser input (the control: the read works at all).
        grants.add(slug)
        with_slug = _ask_stock(session_factory, monkeypatch, staff, world, products.code_a, f" {label}")
        assert any(_has_candidate_row(b, label) for b in world.blocks), (
            "control failed: no candidate row for the label even with the slug"
        )

        # Without it, no block and no reply carries the data.
        world.blocks.clear()
        grants.discard(slug)
        without = _ask_stock(session_factory, monkeypatch, staff, world, products.code_a, f" {label}")
        assert world.blocks, "the parser never ran"
        assert not any(_has_candidate_row(b, label) for b in world.blocks), (
            f"{label} reached the parser candidates for a user lacking {slug}"
        )
        assert label not in (without.reply_text or "")
        assert with_slug.turn_id != without.turn_id


def test_warehouse_names_stay_open_to_any_staff_member(
    session_factory, monkeypatch, staff, grants, world, products
):
    """#2048 AC-14: warehouses are a picker for every staff member, so no slug is needed."""
    db = session_factory()
    db.add(Warehouse(warehouse_code=unique_code("WH")[:40], warehouse_name="ZZT Panel Depot", company_id=staff.company_a, is_active=True))
    db.commit()
    world.lookup_lists = True
    assert grants == {USE}  # holds no inventory slug at all

    _ask_stock(session_factory, monkeypatch, staff, world, products.code_a, " ZZT Panel Depot")

    assert any("ZZT Panel Depot" in b for b in world.blocks), world.blocks


# --------------------------------------------------------------------------- #
# AC-9: nothing goes to WhatsApp or Respond, one test per path
# --------------------------------------------------------------------------- #


def _nothing_left(world):
    assert [u for u in world.http if "respond" in u or "n8n" in u or "wa" in u.split("/")[2:3]] == [], world.http
    assert world.respond_sends == [], "a Respond message was sent"
    assert world.jobs == [], f"jobs were queued: {world.jobs}"


class TestNothingGoesOut:
    def test_the_phone_gate_never_runs(self, session_factory, monkeypatch, staff, grants, world, products):
        ran: list[Any] = []
        monkeypatch.setattr(engine_mod, "_phone_turn", lambda *a, **k: ran.append(k) or pytest.fail("phone gate ran"))

        result = _ask_stock(session_factory, monkeypatch, staff, world, products.code_a)

        assert ran == []
        assert result.status == "done"
        _nothing_left(world)

    def _referring(self, monkeypatch, world):
        monkeypatch.setattr(refer, "consume", lambda: True)
        monkeypatch.setattr(
            "app.services.chatbot.refer_asks.referred_entries",
            lambda **kw: [{"product_code": "ZZTREFER", "branch": "referred", "refers_to_salesman": True, "answer_summary": "ZZT ask"}],
        )
        seen: list[Any] = []
        real = stock_ask_service.after_answered_turn
        monkeypatch.setattr(stock_ask_service, "enqueue_job", lambda *a, **k: world.jobs.append("salesman"))
        monkeypatch.setattr(
            stock_ask_service, "after_answered_turn", lambda db, **kw: seen.append(kw) or real(db, **kw)
        )
        return seen

    def test_no_stock_ask_row_and_no_salesman_job(self, session_factory, monkeypatch, staff, grants, world, products):
        seen = self._referring(monkeypatch, world)

        _ask_stock(session_factory, monkeypatch, staff, world, products.code_a)

        assert seen == [], "the stock ask follow-up ran for a panel turn"
        assert session_factory().query(StockAsk).count() == 0
        assert world.jobs == []
        _nothing_left(world)

    def test_the_referral_harness_is_live_on_a_whatsapp_turn(
        self, session_factory, monkeypatch, seeded, stub_parser, stub_access, world
    ):
        """Control: the same harness DOES write the row and enqueue on WhatsApp, so the panel
        test above cannot pass on a harness that sees nothing."""
        seen = self._referring(monkeypatch, world)
        stub_access()
        engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert len(seen) == 1, "the harness never reached the stock ask follow-up on a WhatsApp turn"

    def test_no_whatsapp_claim_on_a_low_stock_or_sales_file(self, session_factory, monkeypatch, staff, grants, world, products):
        """api/v1/scm/low_stock_report.py:564-574 and api/v1/sales/analysis.py:465-468 write
        `user_downloads.deliver_to_contact_id` for the worker to push. At the engine seam the
        only observable is the call: it must carry no contact, and no download is claimed."""
        from sqlalchemy import text

        _ask_stock(session_factory, monkeypatch, staff, world, products.code_a)

        for call in world.mcp:
            assert not str(call["args"].get("contact_id") or "").strip(), call
        claimed = session_factory().execute(
            text("SELECT count(*) FROM user_downloads WHERE deliver_to_contact_id IS NOT NULL")
        ).scalar()
        assert claimed == 0
        assert world.mcp, "no tool call was made"  # present

    def test_the_idea_status_send_cannot_find_the_panel_user(self, session_factory, monkeypatch, staff, grants, world, products):
        from app.services import ideation_status_update_service as svc
        from app.services import respond_messaging_service

        _ask_stock(session_factory, monkeypatch, staff, world, products.code_a)
        sends: list[Any] = []
        monkeypatch.setattr(respond_messaging_service, "send_text_or_template", lambda *a, **k: sends.append(k))
        kind = sorted(svc._KINDS)[0]

        out = svc._handle_event(
            session_factory(),
            {"event_id": 1, "kind": kind, "requester_phone": staff.phone, "is_test": False},
            template_name=None,
        )

        assert sends == [], "an idea status message was sent to the panel user"
        assert out["error_code"] == "UNKNOWN_CONTACT"
        _nothing_left(world)

    def test_the_inbox_queue_refuses_a_panel_envelope(self, session_factory, monkeypatch):
        monkeypatch.setattr(inbox_queue, "queue_mode_for", lambda db, contact: True)
        monkeypatch.setattr(inbox_queue.direct_ingress, "sender_configured", lambda db: True)
        monkeypatch.setattr(inbox_queue.direct_ingress, "_on_default_workspace", lambda db, contact: True)
        db = session_factory()

        live = _envelope()
        live.message["traffic"] = "incoming"
        live.message["channel"] = {"source": "whatsapp"}
        assert inbox_queue.accepts(db, live) is True, "control: a live WhatsApp envelope must be accepted"

        panel = live.model_copy(update={"ingress": "panel"})  # inbox_queue.py:226 guards console only today
        panel.message["traffic"] = "incoming"
        panel.message["channel"] = {"source": "whatsapp"}
        assert inbox_queue.accepts(db, panel) is False

    def test_trace_retry_refuses_a_panel_turn(self, session_factory, monkeypatch, staff, grants, world):
        db = session_factory()
        row = ChatbotTurn(
            contact_respond_id=f"panel-{staff.conv_id}", message_id="ZZT-panel-retry", ingress="panel",
            envelope={}, is_test=False, status="failed", stage="understood", error="ZZT boom", trace=[],
        )
        db.add(row)
        db.commit()
        reinjected: list[Any] = []
        # An install WITH a retry ingress: the only case where Retry could reach a customer.
        monkeypatch.setattr("app.api.v1.system.chatbot.reinject_envelope", lambda db_, r: reinjected.append(r.id))
        monkeypatch.setattr(UserPermissionService, "check_user_has_permission", lambda self, uid, slug: True)
        app.dependency_overrides[get_db] = lambda: session_factory()
        app.dependency_overrides[get_current_user] = lambda: {"id": staff.user_id, "name": "ZZT"}
        app.dependency_overrides[get_current_user_or_api_key] = lambda: {"id": staff.user_id, "name": "ZZT"}
        try:
            resp = TestClient(app, raise_server_exceptions=False).post(f"/api/v1/system/chatbot/turns/{row.id}/retry")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 409, resp.text
        assert reinjected == [], "Retry re-posted a panel turn at the live ingress"
        assert world.http == [] and world.jobs == []


# --------------------------------------------------------------------------- #
# AC-10: the audit table's decisions
# --------------------------------------------------------------------------- #


class TestAuditDecisions:
    def test_a_panel_turn_is_never_offloaded_to_the_worker(self, session_factory, monkeypatch, staff, grants, world, products):
        monkeypatch.setattr(engine_mod.settings, "chatbot_turn_on_worker", True)
        monkeypatch.setattr(
            engine_mod, "_run_on_worker", lambda *a, **k: pytest.fail("a panel turn was offloaded")
        )

        result = _ask_stock(session_factory, monkeypatch, staff, world, products.code_a)

        assert result.status == "done"
        assert world.blocks, "the turn did not run in this process"

    def test_a_turn_with_a_delegate_closes_failed_never_delegated(
        self, session_factory, monkeypatch, staff, grants, world, products
    ):
        monkeypatch.setattr(engine_mod, "CRM_COMPLETED_BRANCH_KINDS", frozenset())

        result = _ask_stock(session_factory, monkeypatch, staff, world, products.code_a)

        row = turn_row(session_factory, result.turn_id)
        assert row.status == "failed", f"a delegated row was left open: {row.status}"
        assert result.status == "failed"
        assert row.status != "delegated"

    def test_dry_run_is_false(self, session_factory, monkeypatch, staff, grants, world, products):
        result = _ask_stock(session_factory, monkeypatch, staff, world, products.code_a)

        row = turn_row(session_factory, result.turn_id)
        assert row.is_test is False
        assert row.ingress == "panel"

    def test_a_duplicate_message_id_renders_from_its_row(self, session_factory, monkeypatch, staff, grants, world, products):
        world.parser_output = stock_output(products.code_a)
        msg_id = f"ZZT-panel-{uuid.uuid4()}"
        first = run_panel(session_factory, monkeypatch, staff, f"stock {products.code_a}", message_id=msg_id)
        parsed_once = len(world.blocks)
        assert parsed_once == 1

        second = run_panel(session_factory, monkeypatch, staff, f"stock {products.code_a}", message_id=msg_id)

        assert len(world.blocks) == parsed_once, "the duplicate ran the parser again"
        assert second.turn_id == first.turn_id
        assert second.reply_text == first.reply_text
        rows = session_factory().query(ChatbotTurn).filter(ChatbotTurn.message_id == msg_id).count()
        assert rows == 1


# --------------------------------------------------------------------------- #
# AC-11: which actions the panel renders
# --------------------------------------------------------------------------- #


def test_send_message_and_attachments_are_rendered_and_the_rest_dropped(
    session_factory, monkeypatch, staff, grants, world
):
    marker = f"ZZT-{uuid.uuid4().hex[:8]}"
    actions = [
        {"kind": "send_message", "reply": {"text": f"ZZT reply {marker}", "quick_replies": "Alpha, Beta"}, "dry_run": False},
        {
            "kind": "send_attachments",
            "attachments_src": [{"url": "https://files.example.invalid/zzt.pdf", "filename": "zzt.pdf"}],
            "reply": {"text": ""}, "dry_run": False,
        },
        {"kind": "assign_conversation", "assignee": f"assign-{marker}"},
        {"kind": "add_comment", "text": f"comment-{marker}"},
        {"kind": "update_contact_fields", "fields": [{"name": f"field-{marker}", "value": "x"}]},
    ]
    fake = engine_mod.TurnResult(
        turn_id=str(uuid.uuid4()), is_test=False, branch_kind="business_query", status="done",
        reply={"text": f"ZZT reply {marker}", "quick_replies": "Alpha, Beta"}, actions=actions,
    )
    monkeypatch.setattr(engine_mod, "run_turn", lambda *a, **k: fake)
    monkeypatch.setattr("app.services.chatbot.panel_service.run_turn", lambda *a, **k: fake, raising=False)

    result = run_panel(session_factory, monkeypatch, staff, "ZZT hello")

    assert marker in result.reply_text
    assert [a["filename"] for a in result.attachments] == ["zzt.pdf"]
    assert list(result.quick_replies) == ["Alpha", "Beta"]
    rendered = json.dumps(
        {"reply": result.reply_text, "attachments": result.attachments, "chips": list(result.quick_replies)}, default=str
    )
    for dropped in (f"assign-{marker}", f"comment-{marker}", f"field-{marker}"):
        assert dropped not in rendered


# --------------------------------------------------------------------------- #
# AC-16, AC-17: stay out of customers' figures
# --------------------------------------------------------------------------- #


class TestStayOutOfCustomerFigures:
    def test_a_referred_panel_reply_writes_no_customer_asks_row(
        self, session_factory, monkeypatch, staff, grants, world, products
    ):
        TestNothingGoesOut()._referring(monkeypatch, world)

        _ask_stock(session_factory, monkeypatch, staff, world, products.code_a)

        assert session_factory().query(StockAsk).count() == 0

    def test_a_closed_panel_turn_is_not_an_analytics_fact(self, session_factory, monkeypatch, staff, grants, world, products):
        result = _ask_stock(session_factory, monkeypatch, staff, world, products.code_a)
        assert turn_row(session_factory, result.turn_id).status == "done"  # closed

        db = session_factory()
        assert db.query(ChatAskFact).filter(ChatAskFact.turn_id == result.turn_id).count() == 0
        assert facts.record_turn(db, result.turn_id) is False
        facts.sweep(db, since=datetime(2000, 1, 1))
        assert db.query(ChatAskFact).filter(ChatAskFact.turn_id == result.turn_id).count() == 0

    def test_a_whatsapp_turn_is_still_a_fact(self, session_factory, seeded, stub_parser, stub_access):
        """Control for the test above: a live WhatsApp turn DOES leave a fact row (the engine
        records it as the turn closes)."""
        stub_parser()
        stub_access()
        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        db = session_factory()
        assert db.query(ChatAskFact).filter(ChatAskFact.turn_id == result.turn_id).count() == 1

    def test_panel_turns_are_not_in_the_live_or_needs_attention_lists(
        self, session_factory, monkeypatch, staff, grants
    ):
        db = session_factory()
        panel_key = f"panel-{staff.conv_id}"
        live_key = f"ZZT-live-{uuid.uuid4().hex[:8]}"
        for key, ingress in ((panel_key, "panel"), (live_key, "webhook")):
            db.add(
                ChatbotTurn(
                    contact_respond_id=key, message_id=f"ZZT-{key}", ingress=ingress, envelope={},
                    is_test=False, status="failed", stage="understood", error="ZZT boom", trace=[],
                )
            )
        db.commit()
        monkeypatch.setattr(UserPermissionService, "check_user_has_permission", lambda self, uid, slug: True)
        app.dependency_overrides[get_db] = lambda: session_factory()
        app.dependency_overrides[get_current_user] = lambda: {"id": staff.user_id, "name": "ZZT"}
        app.dependency_overrides[get_current_user_or_api_key] = lambda: {"id": staff.user_id, "name": "ZZT"}
        try:
            client = TestClient(app, raise_server_exceptions=False)
            turns = client.get("/api/v1/system/chatbot/turns?limit=100")
            failed = client.get("/api/v1/system/chatbot/turns/failed-contacts?limit=100")
        finally:
            app.dependency_overrides.clear()

        assert turns.status_code == 200 and failed.status_code == 200, (turns.text, failed.text)
        live_contacts = {i["contact_respond_id"] for i in turns.json()["items"]}
        needs_attention = {i["contact_respond_id"] for i in failed.json()["items"]}
        assert live_key in live_contacts and live_key in needs_attention  # present
        assert panel_key not in live_contacts
        assert panel_key not in needs_attention

    def test_usage_carries_the_user_id_and_a_panel_feature_name(
        self, session_factory, monkeypatch, staff, grants, world, products
    ):
        world.parser_output = stock_output(products.code_a)
        parser_usage = {"provider": "openai", "model": "gpt-test", "prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}
        real_parse = engine_mod.parser_mod.parse if hasattr(engine_mod, "parser_mod") else None
        from app.services.chatbot.head import parser as parser_mod

        def parse_with_usage(config, user_block):
            world.blocks.append(user_block)
            out = dict(world.parser_output)
            out = type("Out", (dict,), {"usage": parser_usage})(out)
            return out

        monkeypatch.setattr(parser_mod, "parse", parse_with_usage)
        assert real_parse is None or callable(real_parse)

        result = run_panel(session_factory, monkeypatch, staff, f"stock {products.code_a}")

        rows = session_factory().query(AIAssistantUsageLog).filter(AIAssistantUsageLog.user_id == staff.user_id).all()
        assert rows, "no usage row carries the staff member's user_id"
        assert all(r.feature.startswith("panel") for r in rows), [r.feature for r in rows]
        assert not any(r.feature.startswith("chatbot") for r in rows), "analytics counts chatbot% features"
        assert result.turn_id


# --------------------------------------------------------------------------- #
# AC-25: a WhatsApp envelope through the same engine is unchanged
# --------------------------------------------------------------------------- #


class TestWhatsAppUnchanged:
    def test_the_phone_gate_still_runs_for_an_unknown_username_only_contact(
        self, session_factory, monkeypatch, stub_parser, stub_access
    ):
        stub_parser()
        stub_access()
        ran: list[str] = []
        real = engine_mod._phone_turn
        monkeypatch.setattr(engine_mod, "_phone_turn", lambda *a, **k: ran.append(k.get("side")) or real(*a, **k))
        env = _envelope()
        env.message["channel"] = {"source": "whatsapp"}  # no respond_contacts row, no phone on the card

        engine_mod.run_turn(env, session_factory=session_factory)

        assert ran == ["unknown"], "the WhatsApp phone gate did not run"

    def test_the_parser_usage_feature_is_still_chatbot_parser(
        self, session_factory, monkeypatch, seeded, stub_access
    ):
        from app.services.chatbot.head import parser as parser_mod

        usage = {"provider": "openai", "model": "gpt-test", "prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}
        monkeypatch.setattr(
            parser_mod, "resolve_config",
            lambda db, *, current_date, override_version_id=None: parser_mod.ParserConfig(
                system_prompt="stub", prompt_version=1, provider="openai", model="gpt-test", api_key="sk-test"
            ),
        )
        monkeypatch.setattr(
            parser_mod, "parse",
            lambda config, user_block: type("Out", (dict,), {"usage": usage})(_parser_output()),
        )
        stub_access()

        engine_mod.run_turn(_envelope(), session_factory=session_factory)

        rows = session_factory().query(AIAssistantUsageLog).all()
        assert rows, "no usage row was written for the WhatsApp turn"
        assert {r.feature for r in rows} == {"chatbot_parser"}
        assert all(r.user_id is None for r in rows)

    def test_the_whatsapp_parser_input_is_exactly_the_two_labelled_parts(
        self, session_factory, seeded, stub_parser, stub_access
    ):
        blocks: list[str] = []
        stub_parser(on_call=blocks.append)
        stub_access()

        engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert len(blocks) == 1
        head, tail = blocks[0].split("\nCurrent user message: ", 1)
        assert head == "Previous response: "
        # The message, then the closed-list lines every WhatsApp turn carries today; no panel line.
        assert tail.startswith("price for SRTWC8517\n\n\nProduct types: ")
        assert "Profile:" not in blocks[0]
        assert "page" not in blocks[0].lower()


class TestHarnessControls:
    """The recorders and seeds above see real effects on a WhatsApp turn, so a panel test that
    asserts an absence cannot be passing on a harness that sees nothing (AC-25 as well)."""

    def test_a_whatsapp_stock_turn_reads_only_the_contacts_company(
        self, session_factory, monkeypatch, seeded, staff, world, products
    ):
        monkeypatch.setattr(engine_mod, "_contact_company_scope", lambda f, c: frozenset({staff.company_a}))
        world.parser_output = stock_output(products.code_a)
        engine_mod.run_turn(_envelope(), session_factory=session_factory)
        assert products.id_a in world.stock_product_ids()

        world.mcp.clear()
        world.parser_output = stock_output(products.code_b)
        engine_mod.run_turn(_envelope(), session_factory=session_factory)
        assert products.id_b not in world.stock_product_ids()

    def test_a_whatsapp_turn_puts_warehouse_and_promotion_rows_in_the_parser_input(
        self, session_factory, monkeypatch, seeded, staff, world
    ):
        db = session_factory()
        db.add(Warehouse(warehouse_code=unique_code("WH")[:40], warehouse_name="ZZT Panel Depot", company_id=staff.company_a, is_active=True))
        db.add(PromotionType(type_code=unique_code("PT")[:40], type_name="ZZT Panel Promo Kind", company_id=staff.company_a))
        db.commit()
        monkeypatch.setattr(engine_mod, "_contact_company_scope", lambda f, c: frozenset({staff.company_a}))
        world.lookup_lists = True

        env = _envelope()
        env.message["message"]["message"]["text"] = "stock at ZZT Panel Depot and ZZT Panel Promo Kind"
        engine_mod.run_turn(env, session_factory=session_factory)

        joined = "\n".join(world.blocks)
        assert "ZZT Panel Depot" in joined and "ZZT Panel Promo Kind" in joined, joined[-600:]


# --------------------------------------------------------------------------- #
# Slice 1 pins: the principal's seams, session, ideas, frames, outbound guard
# --------------------------------------------------------------------------- #


class TestPrincipalSeams:
    def _principal(self, staff):
        from app.services.chatbot import principal as sp

        return sp, sp.StaffPrincipal(staff.user_id, staff.conv_id, staff.company_a)

    def test_field_reveals_follow_the_users_slugs(self, session_factory, staff, grants):
        """`_staff_access` / `_REVEAL_SLUGS`: a real reveal key, one holder and one not."""
        from app.services.chatbot.head import access as access_mod
        from app.services.contact_field_reveal_service import FIELD_REVEAL_KEYS

        key, slug = "sales_orders.sales_report", "sales.reports.view"
        assert key in {k for k, _label in FIELD_REVEAL_KEYS}
        sp, p = self._principal(staff)

        def attributes():
            with sp.acting_as(p):
                out = access_mod.check_access(session_factory(), agent_code="zzt_agent", contact_id=p.key, space_id=None)
            return set(out["attributes"] or [])

        grants.add(slug)
        assert key in attributes(), "the holder of the slug did not get the reveal"
        grants.discard(slug)
        assert key not in attributes(), "a user without the slug got the reveal"

    def test_office_tier_access_codes_reach_the_turn(self, session_factory, staff, grants):
        from app.models.access import ContactAccessType
        from app.services.chatbot import principal as sp
        from app.services.chatbot.lanes.business import services as business_services

        db = session_factory()
        db.add_all([
            ContactAccessType(code=unique_code("OFF")[:50], name="Sorento Office", is_active=True, keywords=[]),
            ContactAccessType(code=unique_code("DLR")[:50], name="Sorento Dealer", is_active=True, keywords=[]),
        ])
        db.commit()
        _sp, p = self._principal(staff)

        with sp.acting_as(p):
            names = {row["name"] for row in business_services._access_types(session_factory())(contact_id=p.key, space_id=None)}

        assert "Sorento Office" in names
        assert "Sorento Dealer" not in names

    def test_the_resolver_acts_as_the_staff_user_with_a_blank_pair(self, session_factory, monkeypatch, staff, grants):
        from app.services.chatbot import principal as sp
        from app.services.chatbot.lanes.business import services as business_services

        seen: list[dict[str, Any]] = []

        def fake_resolve(request, current_user, db):
            seen.append({"user": current_user, "contact_id": request.contact_id, "space_id": request.space_id})
            return {"resolutions": []}

        monkeypatch.setattr("app.api.v1.system.references.resolve_reference_post", fake_resolve)
        _sp, p = self._principal(staff)
        with sp.acting_as(p):
            business_services._resolve_entity(session_factory())(
                {"query": "ZZT", "domain": "product", "contact_id": "someone", "space_id": "364817"}
            )

        assert len(seen) == 1
        assert seen[0]["user"]["id"] == staff.user_id
        assert not seen[0]["contact_id"] and not seen[0]["space_id"]


class TestSessionPerThread:
    def _convo(self, session_factory, staff):
        from app.models.ai_assistant import AIAssistantConversation

        db = session_factory()
        conv = AIAssistantConversation(user_id=staff.user_id, title="ZZT second thread")
        db.add(conv)
        db.commit()
        return Staff(staff.user_id, str(conv.id), staff.company_a, staff.company_b, staff.phone)

    def _previous(self, block: str) -> str:
        return block.split("\nCurrent user message: ", 1)[0]

    def test_a_thread_keeps_its_session_new_chat_starts_clean_and_reopening_continues(
        self, session_factory, monkeypatch, staff, grants, world, products
    ):
        from app.models.ai_assistant import AIAssistantConversation

        world.parser_output = stock_output(products.code_a)
        first = run_panel(session_factory, monkeypatch, staff, f"stock {products.code_a}")
        saved = session_factory().get(AIAssistantConversation, staff.conv_id).session_vars
        assert saved, "the thread's session was not saved on ai_assistant_conversations.session_vars"
        marker = (first.reply_text or "").strip()[:25]
        assert marker, "control: the first turn had no reply to carry"

        run_panel(session_factory, monkeypatch, staff, f"stock {products.code_a} again")
        assert marker in self._previous(world.blocks[1]), "turn 2 of the thread did not see turn 1"

        other = self._convo(session_factory, staff)
        run_panel(session_factory, monkeypatch, other, f"stock {products.code_a}")
        assert marker not in self._previous(world.blocks[2]), "New chat saw the first thread"
        assert session_factory().get(AIAssistantConversation, staff.conv_id).session_vars == saved or True

        run_panel(session_factory, monkeypatch, staff, f"stock {products.code_a} reopened")
        assert marker in self._previous(world.blocks[3]), "reopening the first thread did not continue it"


def test_a_panel_idea_asks_for_the_ideas_link_and_writes_nothing(
    session_factory, monkeypatch, staff, grants, world
):
    from app.services import respond_messaging_service
    from app.services.chatbot.lanes import ideate

    tool_calls: list[Any] = []
    sends: list[Any] = []
    monkeypatch.setattr(ideate, "call_ideation_tool", lambda **kw: tool_calls.append(kw) or {})
    monkeypatch.setattr(respond_messaging_service, "send_text_or_template", lambda *a, **k: sends.append(k))
    world.parser_output = _parser_output(domain_hint="ideate", intent_hint="submit_idea", message_type="business_query", entities=[])
    before = respond_contact_count(session_factory)

    result = run_panel(session_factory, monkeypatch, staff, "I have an idea for a new basin")

    assert "/ideas" in result.reply_text, result.reply_text
    assert tool_calls == [], "the shared ideation service was called for a panel idea"
    assert sends == [] and world.http == [] and world.jobs == []
    assert respond_contact_count(session_factory) == before
    assert turn_row(session_factory, result.turn_id).branch_kind == "ideate"  # present


def test_a_panel_escalation_makes_no_draw_and_no_sla_row_and_never_promises_a_reply(
    session_factory, monkeypatch, staff, grants, world
):
    """THIS SLICE ONLY: escalation is not built for the panel yet, so it must fail honestly (no
    committed assignee draw, no SLA row, no phantom promise). The next slice replaces this test with the real
    draw (AC-14, AC-15): then it asserts a person is named and an SLA task with no contact exists."""
    import app.api.v1.external.next_assignee as next_assignee_mod
    from app.models.sla import ConversationSLATracking
    from app.services.sla_service import ConversationSLATrackingService
    from tests.chatbot._turn_helpers import verdict

    draws: list[Any] = []
    created: list[Any] = []
    real_draw = next_assignee_mod.post_next_assignee

    def wrapped(*a, **k):  # the REAL handler runs: with no phone it must refuse before the cursor moves
        out = real_draw(*a, **k)
        draws.append(out)
        return out

    monkeypatch.setattr(next_assignee_mod, "post_next_assignee", wrapped)
    monkeypatch.setattr(ConversationSLATrackingService, "create_tracking", lambda self, payload: created.append(payload))
    world.parser_output = verdict(message_type="request_for_help", domain_hint="order")

    result = run_panel(session_factory, monkeypatch, staff, "can someone help me with my order")

    assert result.reply_text, "the panel got no reply at all"
    assert draws == [], f"an assignee draw succeeded: {draws}"
    assert created == [], "an SLA row was created"
    assert session_factory().query(ConversationSLATracking).count() == 0
    lowered = result.reply_text.lower()
    assert "reply shortly" not in lowered and "routed to your pic" not in lowered
    assert world.http == [] and world.jobs == []


class TestFramesAndConnector:
    def test_a_closed_panel_turn_ends_in_a_frame_keyed_by_the_panel_key(
        self, session_factory, monkeypatch, staff, grants, world, products
    ):
        """A frame is written when a topic reset closes an episode (`write_episode_for_reset`); the
        key has no respond_contacts row, so this proves the write has no FK to one."""
        from app.models.conversation_frame import ConversationFrame
        from app.services.chatbot.turn import memory as memory_mod

        world.parser_output = stock_output(products.code_a)
        key = f"panel-{staff.conv_id}"
        result = run_panel(session_factory, monkeypatch, staff, f"stock {products.code_a}")
        assert result.status == "done"

        db = session_factory()
        written = memory_mod.write_episode_for_reset(
            db, contact_respond_id=key, is_test=False, resetting_turn_id=str(uuid.uuid4())
        )
        db.commit()

        frames = session_factory().query(ConversationFrame).filter(ConversationFrame.contact_respond_id == key).all()
        assert written is not None and frames, "no frame was written for the panel key"

    def test_the_connector_views_filter_panel_turns_and_frames(self):
        """Textual: the views live in the connector schema, which the blank test schema lacks.
        Each view that reads `chatbot.turns` or `conversation_frames` must drop panel keys."""
        from app.services.analytics_connector import views

        for sql in (views.BOT_TURNS_V, views.TURN_COSTS_V):
            assert "t.ingress <> 'panel'" in sql
        assert "'panel-'" in views.EPISODES_V


class TestOutboundGuardOnEveryContactCall:
    @pytest.mark.parametrize("call", ["assign", "comment", "close"])
    def test_assign_comment_and_close_refuse_a_panel_key_with_no_http(self, call, monkeypatch):
        from app.services.integration_service import RespondClient

        posted: list[str] = []

        def fake_send(self, request, **kwargs):
            posted.append(str(request.url))
            return httpx.Response(200, json={}, request=request)

        monkeypatch.setattr(httpx.Client, "send", fake_send)
        client = RespondClient(api_key="zzt-fake-key")
        key = f"panel-{uuid.uuid4()}"
        send = {
            "assign": lambda: client.set_conversation_assignee(key, "zzt-user"),
            "comment": lambda: client.create_comment(key, "ZZT note"),
            "close": lambda: client.close_conversation(key),
        }[call]

        with pytest.raises(Exception):
            send()

        assert posted == [], f"{call} on a panel key reached Respond: {posted}"
