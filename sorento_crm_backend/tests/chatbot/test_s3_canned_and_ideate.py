"""RED tests for S3 - canned lanes, offer-hold, ideation-as-MCP-tool, settings columns.

Contract: `documentation/plans/chatbot/chatbot-turn-engine-acceptance-criteria.md` S3
(AC-301 to AC-307), decisions D5, D6, D10, D14, hazards H13/H14; PLAN sections S3,
"Configuration (D5)", "Session state contract".

Written BEFORE the S3 implementation (Phase 2 test-first). The lane's own worktree
currently holds only S0 + S1 (this file's imports of `app.services.chatbot.lanes.*`
and `app.services.chatbot.copy` are therefore expected to fail until S3 lands, and
S2's tail + S6a arrive later by merge - some assertions here also depend on that
merge and are red for a second, unrelated reason until it lands too).

Source behaviour ported (read-only, `sorento_crm_n8n/n8n-workflows-init/export/`):
`spine-rs-1a/nodes/offer-hold-reply.js`, `spine-rs-1a/nodes/build-ideate-reply.js`,
the `ideate-turn-http` node's `jsonBody` and `sorento-sub-respond-sendmsg-respond5`'s
`message` expression (both in `spine-rs-1a/workflow.json`), and
`sub-output-live/nodes/escalate-catalog.js` (canned copy per `branch_kind`).

Nothing here reaches an LLM, n8n, respond.io or a live MCP server: the parser is
stubbed at `app.services.chatbot.head.parser`, access at
`app.services.chatbot.engine.check_access`, and the MCP call at the seam this slice
is expected to expose, `app.services.chatbot.lanes.ideate.call_ideation_tool`.
"""
from __future__ import annotations

import json
from typing import Any, Callable

import pytest
from sqlalchemy import text

from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.contracts import Envelope

from tests.chatbot.test_engine import (  # noqa: F401 - fixtures reused by name
    CONTACT_ID,
    _envelope,
    _parser_output,
    seeded,
    stub_access,
    stub_parser,
)


def _turn_row(session_factory, turn_id: str) -> ChatbotTurn:
    return session_factory().query(ChatbotTurn).filter(ChatbotTurn.id == turn_id).first()


def _session_vars_raw(session_factory) -> Any:
    return session_factory().execute(
        text("SELECT session_vars FROM respond_contacts WHERE respond_io_id = :c"),
        {"c": CONTACT_ID},
    ).scalar()


def _seed_session_variables(session_factory, variables: dict[str, Any]) -> None:
    db = session_factory()
    db.execute(
        text(
            "UPDATE respond_contacts SET session_vars = CAST(:sv AS jsonb) "
            "WHERE respond_io_id = :c"
        ),
        {"c": CONTACT_ID, "sv": json.dumps({"variables": variables})},
    )
    db.commit()


# --------------------------------------------------------------------------- #
# AC-301 / AC-303: eight branch kinds that finish the turn (delegate = None).
#
# `access_denied` is deliberately covered by its own test below (no session
# write is the interesting property there, not the canned-copy shape); the
# other seven map 1:1 to the parametrised list.
# --------------------------------------------------------------------------- #


def _setup_escalate_offer(session_factory, monkeypatch) -> tuple[Envelope, str]:
    """`is_explicit_correction()`: a correction that is not casual/business_query."""
    overrides = _parser_output(
        message_type="unknown",
        domain_hint=None,
        correction=True,
        routing={"suggested_team": "purchasing", "suggested_agent": None},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
    )
    expected = (
        "I am sorry the provided answer does not meet your requirements. "
        "Would you like me to escalate to purchasing team?"
    )
    return overrides, None, expected


def _setup_escalation_declined(session_factory, monkeypatch) -> tuple[dict, Any, str]:
    overrides = _parser_output(
        message_type="casual",
        domain_hint=None,
        correction=False,
        escalation={"is_escalation_confirmation": False, "escalation_declined": True},
    )
    expected = "Escalation declined."
    return overrides, None, expected


def _setup_clarify_menu(session_factory, monkeypatch) -> tuple[dict, Any, str]:
    overrides = _parser_output(
        message_type="clarification",
        domain_hint=None,
        user_goal="checking stock availability",
        escalation={"is_escalation_confirmation": False, "company_pick": None},
    )
    expected = (
        "I see you're checking stock availability, Let me understand more.\n\n"
        "Are you asking about any of these?\n\n"
        "- Product (List Price, Dimension)\n"
        "- Photos, Technical Specs, Cert\n"
        "- Promotion\n"
        "- Forms\n"
        "- Stock\n"
        "- Delivery order\n"
        "- Incoming\n"
        "- Catalogue, Warranty\n\n"
        "I can help with the topics listed above."
    )
    return overrides, None, expected


def _setup_not_supported(session_factory, monkeypatch) -> tuple[dict, Any, str]:
    """Default unsupported list (AC-304's own setting is tested separately)."""
    overrides = _parser_output(
        message_type="business_query",
        domain_hint="goods_receive",
        escalation={"is_escalation_confirmation": False, "company_pick": None},
    )
    expected = (
        "Sorry, we don't support direct goods receive & SPO at the moment. "
        "You may ask about incoming stock for a specific product or container"
    )
    return overrides, None, expected


def _setup_demand_qty(session_factory, monkeypatch) -> tuple[dict, Any, str]:
    overrides = _parser_output(
        message_type="business_query",
        intent_hint="check_stock",
        domain_hint="inventory",
        demand_qty=0,
        escalation={"is_escalation_confirmation": False, "company_pick": None},
    )
    expected = "Please specify your demand quantity"
    return overrides, "stock", expected


TWO_COMPANY_ROSTER = [{"company_name": "Alpha Corp"}, {"company_name": "Beta Corp"}]
OFFER_HOLD_CLARIFY_TEXT = (
    "Both *Alpha Corp* and *Beta Corp* teams are listed - reply a number, a name, "
    "or the company (*Alpha Corp* / *Beta Corp*) and I'll assign automatically."
)


def _setup_offer_hold(session_factory, monkeypatch) -> tuple[dict, Any, str]:
    """Tier-4 (junk/no-signal) re-offer on an open two-company member roster."""
    session_factory  # seeded by the caller via _seed_session_variables
    overrides = _parser_output(
        message_type="casual",
        domain_hint=None,
        person_mention=None,
        reference_positions=[],
        correction=False,
        entities=[],
        routing={"suggested_team": None, "suggested_agent": None},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
    )
    session_vars = {
        "selection_context": "member_offer",
        "routing_roster_plan": TWO_COMPANY_ROSTER,
        "routing_companies": TWO_COMPANY_ROSTER,
    }
    return overrides, session_vars, OFFER_HOLD_CLARIFY_TEXT, "not sure"


IDEATE_TOOL_RESULT = {
    "status": "collecting",
    "reply_text": "Got it - what department is this for?",
    "link": None,
    "session_vars": {"ideation": {"draft_id": "ZZT-draft-1", "status": "collecting"}},
}


def _setup_ideate(session_factory, monkeypatch) -> tuple[dict, Any, str]:
    from app.services.chatbot.lanes import ideate as ideate_mod

    monkeypatch.setattr(
        ideate_mod, "call_ideation_tool", lambda **kwargs: dict(IDEATE_TOOL_RESULT)
    )
    overrides = _parser_output(
        message_type="business_query",
        intent_hint="submit_idea",
        domain_hint="ideate",
        escalation={"is_escalation_confirmation": False, "company_pick": None},
    )
    session_vars = {"ideation": {"draft_id": "ZZT-draft-1", "status": "collecting"}}
    return overrides, session_vars, IDEATE_TOOL_RESULT["reply_text"]


_CANNED_SCENARIOS: dict[str, Callable] = {
    "escalate_offer": _setup_escalate_offer,
    "escalation_declined": _setup_escalation_declined,
    "clarify_menu": _setup_clarify_menu,
    "not_supported": _setup_not_supported,
    "demand_qty": _setup_demand_qty,
    "offer_hold": _setup_offer_hold,
    "ideate": _setup_ideate,
}


def _build_scenario(kind: str, session_factory, monkeypatch):
    """Normalises the per-kind setup functions above into one shape.

    Returns `(envelope, expected_reply_text)`. Session vars, stock custom fields
    and the MCP stub are all applied here so the two tests that share this table
    (the happy-path assertion and the D14 dry-run assertion) do it identically.
    """
    result = _CANNED_SCENARIOS[kind](session_factory, monkeypatch)
    if kind == "offer_hold":
        parser_overrides, session_vars, expected, message_text = result
        _seed_session_variables(session_factory, session_vars)
        envelope = _envelope()
        envelope.message["message"]["message"]["text"] = message_text
    elif kind == "ideate":
        parser_overrides, session_vars, expected = result
        _seed_session_variables(session_factory, session_vars)
        envelope = _envelope()
    elif kind == "demand_qty":
        parser_overrides, marker, expected = result
        envelope = _envelope()
        envelope.contact["custom_fields"] = [
            {"name": "is_human_intervened", "value": "false"},
            {"name": "is_allowed_stock", "value": "false"},
        ]
    else:
        parser_overrides, session_vars, expected = result
        envelope = _envelope()
        if session_vars:
            _seed_session_variables(session_factory, session_vars)

    return envelope, parser_overrides, expected


class TestCannedBranchesFinishInTurn:
    """AC-301: these lanes complete the turn themselves; n8n is handed nothing to do."""

    @pytest.mark.parametrize("kind", list(_CANNED_SCENARIOS))
    def test_canned_branches_finish_in_turn(
        self, kind, session_factory, seeded, stub_parser, stub_access, monkeypatch
    ):
        envelope, parser_overrides, expected_text = _build_scenario(
            kind, session_factory, monkeypatch
        )
        stub_parser(parser_overrides)
        stub_access()

        result = engine_mod.run_turn(envelope, session_factory=session_factory)

        assert result.delegate is None, (
            f"{kind}: still delegated to n8n - S3 must complete this branch itself"
        )
        assert result.reply is not None, f"{kind}: no reply composed"
        assert result.reply["text"] == expected_text
        assert result.actions == [
            {
                "kind": "send_message",
                "text": expected_text,
                "quick_replies": [],
                "dry_run": False,
            }
        ]

        row = _turn_row(session_factory, result.turn_id)
        assert row.status == "done", row.error
        assert row.branch_kind == kind
        stages = [r["stage"] for r in row.trace]
        assert stages[:4] == ["received", "understood", "access", "routed"]
        assert "replied" in stages
        assert "remembered" in stages
        assert "sent" in stages, "the CRM never sends (D9) - the trace still records the hand-off"


class TestAccessDeniedNoSessionWrite:
    """AC-301's eighth branch: refused up front, before anything is remembered."""

    def test_access_denied_sends_without_session_write(
        self, session_factory, seeded, stub_parser, stub_access
    ):
        stub_parser(
            _parser_output(
                routing={"suggested_team": None, "suggested_agent": "general—enquiries"}
            )
        )
        stub_access(allowed=False, decision="deny_unknown_agent")
        before = _session_vars_raw(session_factory)

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.delegate is None
        assert result.branch_kind == "access_denied"
        assert result.reply["text"] == "Sorry, you are not allowed to access general-enquiries"
        assert result.actions == [
            {
                "kind": "send_message",
                "text": "Sorry, you are not allowed to access general-enquiries",
                "quick_replies": [],
                "dry_run": False,
            }
        ]

        after = _session_vars_raw(session_factory)
        assert after == before, "access_denied must never write session_vars"

        row = _turn_row(session_factory, result.turn_id)
        assert row.status == "done"
        assert row.branch_kind == "access_denied"


# --------------------------------------------------------------------------- #
# AC-302: canned copy comes from the prompt registry, fallback = today's text.
# --------------------------------------------------------------------------- #


# (key, render_kwargs, expected_text). `chatbot_reply_offer_hold` only covers the
# closing clause here (`{{companies}}`) - the lead sentence ("Both X and Y teams
# are listed") is a function of the roster COUNT, composed in
# `lanes.canned.offer_hold_clarify_text` (see TestOfferHoldComposer below), not a
# single-token substitution; `test_offer_hold_reply_composes_from_persisted_pool`
# below proves the full byte-for-byte text end to end. `chatbot_reply_out_of_scope`
# is not one of S3's eight completed branches (it stays delegated until S5) but the
# brief calls for its registry key to exist now, for parity with escalate-catalog.js
# reusing the same team-name shape - documented here as the one speculative case.
_COPY_CASES = [
    (
        "chatbot_reply_access_denied",
        {"team": "general-enquiries"},
        "Sorry, you are not allowed to access general-enquiries",
    ),
    (
        "chatbot_reply_clarify_menu",
        {"user_goal": "checking stock availability"},
        (
            "I see you're checking stock availability, Let me understand more.\n\n"
            "Are you asking about any of these?\n\n"
            "- Product (List Price, Dimension)\n"
            "- Photos, Technical Specs, Cert\n"
            "- Promotion\n"
            "- Forms\n"
            "- Stock\n"
            "- Delivery order\n"
            "- Incoming\n"
            "- Catalogue, Warranty\n\n"
            "I can help with the topics listed above."
        ),
    ),
    (
        "chatbot_reply_not_supported",
        {},
        (
            "Sorry, we don't support direct goods receive & SPO at the moment. "
            "You may ask about incoming stock for a specific product or container"
        ),
    ),
    ("chatbot_reply_demand_qty", {}, "Please specify your demand quantity"),
    (
        "chatbot_reply_escalate_offer",
        {"team": "purchasing"},
        (
            "I am sorry the provided answer does not meet your requirements. "
            "Would you like me to escalate to purchasing team?"
        ),
    ),
    ("chatbot_reply_escalation_declined", {}, "Escalation declined."),
    (
        "chatbot_reply_offer_hold",
        {"companies": "*Alpha Corp* / *Beta Corp*"},
        " - reply a number, a name, or the company (*Alpha Corp* / *Beta Corp*) and I'll assign automatically.",
    ),
    (
        "chatbot_reply_out_of_scope",
        {"team": "purchasing"},
        "Informed the user that request is out of scope and will proceed to escalate to the purchasing team",
    ),
]


class TestCopyKeysRenderTodaysText:
    @pytest.mark.parametrize("key,render_kwargs,expected", _COPY_CASES, ids=[c[0] for c in _COPY_CASES])
    def test_copy_keys_render_todays_text(self, key, render_kwargs, expected):
        from tests._pg_fixture import blank_session

        with blank_session() as db:
            from app.services import ai_prompt_registry

            ai_prompt_registry.bust_cache()
            text_out, version = ai_prompt_registry.render(db, key, **render_kwargs)
            assert version is None, "no published override yet - must resolve to the fallback"
            assert text_out == expected

    def test_a_published_override_wins_after_bust_cache(self):
        """A registry key is editable in Settings > AI Prompts (journey B)."""
        import uuid

        from tests._pg_fixture import blank_session

        with blank_session() as db:
            from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
            from app.services import ai_prompt_registry

            ai_prompt_registry.bust_cache()
            version_row = AIPromptVersion(
                id=str(uuid.uuid4()),
                name="chatbot_reply_demand_qty",
                version=2,
                template="How many units do you need?",
            )
            db.add(version_row)
            db.flush()
            db.add(
                AIPromptLabel(
                    id=str(uuid.uuid4()),
                    name="chatbot_reply_demand_qty",
                    label="production",
                    version_id=version_row.id,
                )
            )
            db.commit()
            ai_prompt_registry.bust_cache("chatbot_reply_demand_qty")

            text_out, resolved_version = ai_prompt_registry.render(db, "chatbot_reply_demand_qty")
            assert text_out == "How many units do you need?"
            assert resolved_version == 2


# --------------------------------------------------------------------------- #
# AC-303: ideation is an MCP tool, not a special-cased lane.
# --------------------------------------------------------------------------- #


class TestIdeateBranchCallsMcpTool:
    def test_ideate_branch_calls_mcp_tool(
        self, session_factory, seeded, stub_parser, stub_access, monkeypatch
    ):
        from app.services.chatbot.lanes import ideate as ideate_mod

        captured: list[dict[str, Any]] = []

        def _fake_call(**kwargs: Any) -> dict[str, Any]:
            captured.append(kwargs)
            return {
                "status": "complete",
                "reply_text": "Idea IDEA-42 recorded. Thank you!",
                "link": "https://outline.example/IDEA-42",
                "session_vars": {"ideation": None},
            }

        monkeypatch.setattr(ideate_mod, "call_ideation_tool", _fake_call)
        stub_parser(
            _parser_output(
                message_type="business_query",
                intent_hint="submit_idea",
                domain_hint="ideate",
                reference_positions=[1, 2],
                escalation={"is_escalation_confirmation": False, "company_pick": None},
            )
        )
        stub_access()
        _seed_session_variables(
            session_factory,
            {
                "ideation": {
                    "draft_id": "ZZT-draft-9",
                    "status": "review",
                    "pending_media": [{"source_msg_id": "ZZT-m1"}],
                }
            },
        )
        envelope = _envelope()
        envelope.message["message"]["message"]["text"] = "the photos are of the leaking basin"

        result = engine_mod.run_turn(envelope, session_factory=session_factory)

        assert len(captured) == 1
        call_kwargs = captured[0]
        assert call_kwargs["respond_io_id"] == CONTACT_ID
        assert isinstance(call_kwargs["respond_io_id"], str)
        assert call_kwargs["message_text"] == "the photos are of the leaking basin"
        assert call_kwargs["session_vars"] == {
            "ideation": {
                "draft_id": "ZZT-draft-9",
                "status": "review",
                "pending_media": [{"source_msg_id": "ZZT-m1"}],
            }
        }
        # `contact.firstName` was set by the shared `_envelope()` helper ("ZZT").
        assert call_kwargs["submitter_name"] == "ZZT"
        # `ideation.pending_media` is set AND `reference_positions` is non-empty ->
        # media_selection is the joined positions, per `ideate-turn-http`'s own rule.
        assert call_kwargs["media_selection"] == "1,2"

        expected_text = "Idea IDEA-42 recorded. Thank you!\n\nhttps://outline.example/IDEA-42"
        assert result.reply["text"] == expected_text
        assert result.reply["manualResponse"] is True
        assert result.reply["includeResponse"] is True
        assert result.reply["ideate_status"] == "complete"
        assert result.delegate is None

    def test_submitter_name_omitted_without_a_first_name(
        self, session_factory, seeded, stub_parser, stub_access, monkeypatch
    ):
        from app.services.chatbot.lanes import ideate as ideate_mod

        captured: list[dict[str, Any]] = []
        monkeypatch.setattr(
            ideate_mod,
            "call_ideation_tool",
            lambda **kwargs: (captured.append(kwargs), dict(IDEATE_TOOL_RESULT))[1],
        )
        stub_parser(_parser_output(domain_hint="ideate", intent_hint="submit_idea"))
        stub_access()
        envelope = _envelope()
        envelope.contact.pop("firstName", None)

        engine_mod.run_turn(envelope, session_factory=session_factory)

        assert "submitter_name" not in captured[0]

    def test_media_selection_omitted_when_no_media_menu_is_open(
        self, session_factory, seeded, stub_parser, stub_access, monkeypatch
    ):
        from app.services.chatbot.lanes import ideate as ideate_mod

        captured: list[dict[str, Any]] = []
        monkeypatch.setattr(
            ideate_mod,
            "call_ideation_tool",
            lambda **kwargs: (captured.append(kwargs), dict(IDEATE_TOOL_RESULT))[1],
        )
        stub_parser(
            _parser_output(
                domain_hint="ideate", intent_hint="submit_idea", reference_positions=[1]
            )
        )
        stub_access()
        # No `ideation.pending_media` on the session -> no menu is open.
        _seed_session_variables(
            session_factory, {"ideation": {"draft_id": "ZZT-draft-1", "status": "collecting"}}
        )

        engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert "media_selection" not in captured[0]

    def test_ideate_tool_error_is_failed_stage(
        self, session_factory, seeded, stub_parser, stub_access, monkeypatch
    ):
        from app.services.chatbot.lanes import ideate as ideate_mod
        from app.services.chatbot.head import parser as parser_mod

        def _boom(**kwargs: Any):
            raise RuntimeError("MCP call failed")

        monkeypatch.setattr(ideate_mod, "call_ideation_tool", _boom)
        stub_parser(_parser_output(domain_hint="ideate", intent_hint="submit_idea"))
        stub_access()
        before = _session_vars_raw(session_factory)

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.branch_kind is None
        assert result.delegate is None
        assert result.reply["text"] == parser_mod.PARSER_ERROR_REPLY

        row = _turn_row(session_factory, result.turn_id)
        assert row.status == "failed"
        assert row.stage == "looked_up"
        assert "MCP call failed" in row.error

        after = _session_vars_raw(session_factory)
        assert after == before, "a failed ideate call must not write session_vars"


# --------------------------------------------------------------------------- #
# offer_hold: the composer function is shared with the (not-yet-ported)
# clarify-company-reply node, per offer-hold-reply.js's own header comment
# ("ONE body deployed to BOTH nodes"), so it is tested directly for the 1-name
# and 0-name shapes that route.decide's `is_offer_hold` gate (plan length > 1)
# cannot reach today, and through `run_turn` for the reachable 2-name shape.
# --------------------------------------------------------------------------- #


class TestOfferHold:
    def test_offer_hold_reply_composes_from_persisted_pool(
        self, session_factory, seeded, stub_parser, stub_access
    ):
        envelope, parser_overrides, expected_text = _build_scenario(
            "offer_hold", session_factory, monkeypatch=None
        )
        stub_parser(parser_overrides)
        stub_access()

        envelope = _envelope(test_run_id="ZZT-run-offer-hold")
        envelope.message["message"]["message"]["text"] = "not sure"
        result = engine_mod.run_turn(envelope, session_factory=session_factory)

        assert result.delegate is None
        assert result.branch_kind == "offer_hold"
        assert result.reply["text"] == OFFER_HOLD_CLARIFY_TEXT

        # D14: dry run, so the would-be persist is on `session_patch`, not written.
        patch = result.session_patch or {}
        variables = patch.get("variables", patch)
        assert variables.get("response") == OFFER_HOLD_CLARIFY_TEXT
        assert variables.get("routing_roster_plan") == TWO_COMPANY_ROSTER
        assert variables.get("routing_companies") == TWO_COMPANY_ROSTER
        assert variables.get("selection_context") == "member_offer"
        assert (variables.get("pending") or {}).get("kind") == "member_offer"

    def test_offer_hold_reply_one_company_name(self):
        from app.services.chatbot.lanes import canned

        text_out = canned.offer_hold_clarify_text(
            routing_roster_plan=[{"company_name": "Solo Co"}],
            routing_companies=[],
        )
        assert text_out == (
            "*Solo Co* teams are listed - reply a number, a name, or the company "
            "(*Solo Co*) and I'll assign automatically."
        )

    def test_offer_hold_reply_no_names(self):
        from app.services.chatbot.lanes import canned

        text_out = canned.offer_hold_clarify_text(
            routing_roster_plan=[{"company_name": None}],
            routing_companies=[],
        )
        assert text_out == (
            "More than one team is listed - reply a number or a name and I'll "
            "assign automatically."
        )

    def test_offer_hold_falls_back_to_routing_companies_when_roster_plan_is_empty(self):
        from app.services.chatbot.lanes import canned

        text_out = canned.offer_hold_clarify_text(
            routing_roster_plan=[],
            routing_companies=TWO_COMPANY_ROSTER,
        )
        assert text_out == OFFER_HOLD_CLARIFY_TEXT


# --------------------------------------------------------------------------- #
# AC-304: `system_settings.chatbot_unsupported_domains`.
# --------------------------------------------------------------------------- #


class TestUnsupportedDomainsSetting:
    def test_column_default_and_both_dict_builders(self, session_factory):
        from app.models.user import SystemSetting

        db = session_factory()
        row = SystemSetting()
        db.add(row)
        db.commit()
        db.refresh(row)
        assert row.chatbot_unsupported_domains == ["goods_receive", "spo_allocation"]

    def test_settings_update_schema_accepts_the_field(self):
        from app.api.v1.user_management.settings import SystemSettingUpdate

        parsed = SystemSettingUpdate(chatbot_unsupported_domains=["order"])
        assert parsed.chatbot_unsupported_domains == ["order"]

    def test_route_uses_the_configured_list_not_the_hardcoded_one(
        self, session_factory, seeded, system_settings_row, stub_parser, stub_access
    ):
        from app.models.user import SystemSetting

        db = session_factory()
        setting = (
            db.query(SystemSetting)
            .filter(SystemSetting.id == system_settings_row.id)
            .one()
        )
        setting.chatbot_unsupported_domains = ["order"]
        db.commit()

        stub_parser(_parser_output(domain_hint="order"))
        stub_access()
        order_result = engine_mod.run_turn(_envelope(), session_factory=session_factory)
        assert order_result.branch_kind == "not_supported"

        stub_parser(_parser_output(domain_hint="goods_receive"))
        stub_access()
        envelope2 = _envelope()
        envelope2.message["message"]["messageId"] = "ZZT-msg-unsupported-2"
        goods_receive_result = engine_mod.run_turn(envelope2, session_factory=session_factory)
        assert goods_receive_result.branch_kind != "not_supported"


# --------------------------------------------------------------------------- #
# AC-306 (addendum to test_engine.py's TestStockDenialGateEndToEnd): the
# demand_qty canned text, and the stock_denied item's `not_allowed_check_stock`
# carrier that `sub-main-processing`'s `Edit Fields2` reads by that exact name.
# --------------------------------------------------------------------------- #


class TestStockDenialFlagGatesTwoLanes:
    @staticmethod
    def _stock_envelope(message_id: str) -> Envelope:
        envelope = _envelope()
        envelope.message["message"]["messageId"] = message_id
        envelope.contact["custom_fields"] = [
            {"name": "is_human_intervened", "value": "false"},
            {"name": "is_allowed_stock", "value": "false"},
        ]
        return envelope

    def test_demand_qty_zero_gives_the_canned_reply(
        self, session_factory, seeded, system_settings_row, stub_parser, stub_access
    ):
        from app.models.user import SystemSetting

        db = session_factory()
        setting = (
            db.query(SystemSetting)
            .filter(SystemSetting.id == system_settings_row.id)
            .one()
        )
        setting.chatbot_stock_denial_enabled = True
        db.commit()

        stub_parser(
            _parser_output(intent_hint="check_stock", domain_hint="inventory", demand_qty=0)
        )
        stub_access()

        result = engine_mod.run_turn(
            self._stock_envelope("ZZT-msg-demand-qty"), session_factory=session_factory
        )
        assert result.branch_kind == "demand_qty"
        assert result.delegate is None
        assert result.reply["text"] == "Please specify your demand quantity"

    def test_stock_denied_item_carries_not_allowed_check_stock(
        self, session_factory, seeded, system_settings_row, stub_parser, stub_access
    ):
        from app.models.user import SystemSetting

        db = session_factory()
        setting = (
            db.query(SystemSetting)
            .filter(SystemSetting.id == system_settings_row.id)
            .one()
        )
        setting.chatbot_stock_denial_enabled = True
        db.commit()

        stub_parser(
            _parser_output(intent_hint="check_stock", domain_hint="inventory", demand_qty=5)
        )
        stub_access()

        result = engine_mod.run_turn(
            self._stock_envelope("ZZT-msg-stock-denied"), session_factory=session_factory
        )
        assert result.branch_kind == "stock_denied"
        # `stock_denied` still delegates to the business lane in S3 (S6 owns it).
        assert result.delegate == "stock_denied"
        assert result.item.get("not_allowed_check_stock") is True


# --------------------------------------------------------------------------- #
# D14: canned lanes are dry-run-safe by construction, same as every other lane.
# --------------------------------------------------------------------------- #


class TestCannedLanesDryRun:
    @pytest.mark.parametrize("kind", list(_CANNED_SCENARIOS))
    def test_canned_lanes_dry_run_write_nothing(
        self, kind, session_factory, seeded, stub_parser, stub_access, monkeypatch
    ):
        envelope, parser_overrides, expected_text = _build_scenario(
            kind, session_factory, monkeypatch
        )
        envelope = Envelope(**{**envelope.model_dump(mode="json"), "is_test": True})
        stub_parser(parser_overrides)
        stub_access()
        before = _session_vars_raw(session_factory)

        result = engine_mod.run_turn(envelope, session_factory=session_factory)

        after = _session_vars_raw(session_factory)
        assert after == before, f"{kind}: dry run wrote session_vars"
        assert result.session_patch is not None, f"{kind}: dry run must carry session_patch"
        assert result.actions, f"{kind}: no actions to inspect"
        assert all(a.get("dry_run") is True for a in result.actions), (
            f"{kind}: every action must carry dry_run true"
        )

    def test_access_denied_dry_run_write_nothing(
        self, session_factory, seeded, stub_parser, stub_access
    ):
        stub_parser(_parser_output())
        stub_access(allowed=False, decision="deny_unknown_agent")
        before = _session_vars_raw(session_factory)

        result = engine_mod.run_turn(_envelope(is_test=True), session_factory=session_factory)

        after = _session_vars_raw(session_factory)
        assert after == before
        assert result.delegate is None
        assert result.actions, "access_denied must still hand the caller a reply to send"
        assert all(a.get("dry_run") is True for a in result.actions)
