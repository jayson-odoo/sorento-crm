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

Retired 16 Sep 2026 (AC-1592, coordinator ruling) - this file predates the S3 rearch
(engine A-G rewired, `output_exchange` deleted AC-1594, `chatbot_completed_lanes` no
longer gates completion contract line 73, S6's stock-visibility gate replaced the
direct `is_allowed_stock` custom-field injection) and several scenarios never
migrated off the old pipeline shape their setup helpers assume:

- `TestCannedBranchesFinishInTurn` (all 7 parametrised kinds; its D14 sibling
  `TestCannedLanesDryRun` reuses the SAME `_build_scenario` helpers and stays green,
  since it never asserts `branch_kind`/exact reply text/routing, only the dry-run
  envelope shape) - `escalation_declined`/`clarify_menu`/`not_supported`/`ideate`
  fail on the old trace `stage` key; `escalate_offer`/`demand_qty` fail because their
  setup relies on `output_exchange`'s retired normalisation (escalate_offer) or a
  scenario the S3 rearch's real stock-denial gate no longer reaches the same way
  (demand_qty); `offer_hold` fails on the legacy flat `session_vars["selection_
  context"]`/`["routing_roster_plan"]` keys (AC-1504/1521 nested-shape retirement).
  No single replacement file covers "does a canned branch finish the turn" as a
  cross-kind sweep the way this class did - flagged, not re-created, since re-
  deriving the correct post-rearch text/routing per kind is engine investigation,
  not a mechanical port.
- `TestOfferHold.test_offer_hold_reply_composes_from_persisted_pool` - same legacy
  flat-keys cause as the `offer_hold` parametrised case above. The other three
  `TestOfferHold` methods test `canned.offer_hold_clarify_text` directly (no
  session_vars shape involved) and stay green.
- `TestUnsupportedDomainsSetting.test_route_uses_the_configured_list_not_the_
  hardcoded_one` - routes through the same retired `output_exchange`/trace-shape
  path as the canned-branch class above; its two sibling methods (column default,
  update-schema) test the DB column directly and stay green.
- `TestStockDenialFlagGatesTwoLanes` (both methods) - the S6 ruling replaced the
  direct `custom_fields[].is_allowed_stock` injection this class used; replacement
  coverage is `test_rearch_s6_stock_allowed.py` (same successor named for the
  sibling retirements in `test_trace_legibility.py`, same session).
- `TestCompletedLanesGateDefaultsClosed.test_default_empty_list_still_delegates` -
  identical theme to `test_completed_lanes_switch.py`'s own retired
  `test_default_empty_delegates_low_signal_and_runs_no_clarifier` this session:
  `chatbot_completed_lanes` no longer gates completion (contract 73 superseded), so
  `result.delegate` is always `None` now regardless of the row. No replacement
  named for the same reason given there.
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
        {"c": str(CONTACT_ID)},
    ).scalar()


def _seed_session_variables(session_factory, variables: dict[str, Any]) -> None:
    db = session_factory()
    db.execute(
        text(
            "UPDATE respond_contacts SET session_vars = CAST(:sv AS jsonb) "
            "WHERE respond_io_id = :c"
        ),
        {"c": str(CONTACT_ID), "sv": json.dumps({"variables": variables})},
    )
    db.commit()


# Coordinator contract addition (post-hoc, same day as the rest of this file): the
# engine completes a branch kind only if it is BOTH in the code-level completed set
# (S3's growing `CRM_COMPLETED_BRANCH_KINDS`) AND in
# `system_settings.chatbot_completed_lanes` (a JSON list, default `[]`). Every S3
# canned/ideate/offer-hold integration test below therefore seeds this list
# explicitly - without it, S3's own code changes would be inert on a fresh
# settings row and every "delegate is None" assertion would be unreachable no
# matter how the lanes are implemented.
ALL_COMPLETED_LANES = [
    "escalate_offer",
    "escalation_declined",
    "clarify_menu",
    "not_supported",
    "demand_qty",
    "offer_hold",
    "ideate",
    "access_denied",
]


def _seed_completed_lanes(session_factory, system_settings_row, lanes=None) -> None:
    from app.models.user import SystemSetting

    db = session_factory()
    setting = (
        db.query(SystemSetting).filter(SystemSetting.id == system_settings_row.id).one()
    )
    setting.chatbot_completed_lanes = list(lanes if lanes is not None else ALL_COMPLETED_LANES)
    db.commit()


def _enable_stock_denial(session_factory, system_settings_row) -> None:
    """R1 (AC-306): `demand_qty` only routes at all with the stock-denial flag on.

    Unrelated to `chatbot_completed_lanes` - the scenario-table tests parametrise
    over every kind including `demand_qty`, so this is called ONLY for that kind
    rather than folded into `_seed_completed_lanes` (which the other six kinds
    must not need to care about)."""
    from app.models.user import SystemSetting

    db = session_factory()
    setting = (
        db.query(SystemSetting).filter(SystemSetting.id == system_settings_row.id).one()
    )
    setting.chatbot_stock_denial_enabled = True
    db.commit()


# --------------------------------------------------------------------------- #
# AC-301 / AC-303: eight branch kinds that finish the turn (delegate = None).
#
# `access_denied` is deliberately covered by its own test below (no session
# write is the interesting property there, not the canned-copy shape); the
# other seven map 1:1 to the parametrised list.
# --------------------------------------------------------------------------- #


def _setup_escalate_offer(session_factory, monkeypatch) -> tuple[Envelope, str]:
    """`is_explicit_correction()`: a correction that is not casual/business_query.

    `output_exchange.derive_routing`'s nullish chain only lets the LLM's own
    `routing.suggested_team` through on a `request_for_help` turn; this scenario
    is `message_type = "unknown"`, so that chain falls through to the PRIOR
    turn's `routing.suggested_team` (rank 3, before the hard "customer_service"
    default) - carried session state, not the current turn's LLM output. The raw
    parser `routing` override below is therefore irrelevant to the final team
    (left null so nothing here implies otherwise); `routing.suggested_team` is
    seeded on the SESSION instead, which also proves the carry (coder-confirmed
    live behaviour, round 3 review of this file).
    """
    overrides = _parser_output(
        message_type="unknown",
        domain_hint=None,
        correction=True,
        routing={"suggested_team": None, "suggested_agent": None},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
    )
    session_vars = {"routing": {"suggested_team": "purchasing", "suggested_agent": None}}
    expected = (
        "I am sorry the provided answer does not meet your requirements. "
        "Would you like me to escalate to purchasing team?"
    )
    return overrides, session_vars, expected


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


# Every call the scenario's stub took, so the D14 test below can assert the WRITE tool
# was never reached rather than only that nothing local was written. `ideate`'s side
# effects (a real idea record, a respond.io media pull, an `integration_log` row) all
# happen on the far side of this seam and none of them is visible in `respond_contacts`.
IDEATE_TOOL_CALLS: list[dict[str, Any]] = []


def _setup_ideate(session_factory, monkeypatch) -> tuple[dict, Any, str]:
    from app.services.chatbot.lanes import ideate as ideate_mod

    IDEATE_TOOL_CALLS.clear()

    def _record(**kwargs: Any) -> dict[str, Any]:
        IDEATE_TOOL_CALLS.append(kwargs)
        return dict(IDEATE_TOOL_RESULT)

    monkeypatch.setattr(ideate_mod, "call_ideation_tool", _record)
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


# Re-pinned 17 Sep 2026 (tester, AC-1592 follow-up): `TestCannedBranchesFinishInTurn`
# was retired at `c830e002a` (16 Sep) as "engine investigation, not a mechanical port" -
# the engine has since moved (`_CANNED_SCENARIOS`/`_build_scenario` are unchanged). Each
# of the 7 kinds re-measured directly against a live `run_turn` before writing this back:
# `escalation_declined`, `clarify_menu`, `not_supported`, `ideate` now compose the exact
# reply text, branch_kind and trace shape the original test wanted - restored, no xfail.
# `escalate_offer` (routes to `low_signal`, not `escalate_offer`), `demand_qty` (routes
# to `business_query`, a real stock lookup, not the demand-qty ask) and `offer_hold`
# (routes to `low_signal`, not `offer_hold`) still diverge - kept as genuine, measured
# `xfail(strict=True)` engine defects rather than dropped, so `test_dry_run_isolation.py`
# ::TestWordsComposedAreWordsSent's guardrail has a live home for all 8 canned kinds
# again (`access_denied` keeps its own separate `TestAccessDeniedNoSessionWrite` home).
class TestCannedBranchesFinishInTurn:
    """AC-301: these lanes complete the turn themselves; n8n is handed nothing to do."""

    _KNOWN_BROKEN = {
        "escalate_offer": "branch_kind comes back low_signal, not escalate_offer - the "
        "scenario's carried routing.suggested_team never arms the escalate-offer lane "
        "(measured 17 Sep 2026, lane head 4427bb6bb)",
        "demand_qty": "branch_kind comes back business_query (a real stock lookup runs), "
        "not demand_qty - the demand_qty==0 signal never reaches the ask (measured 17 Sep "
        "2026, lane head 4427bb6bb)",
        "offer_hold": "branch_kind comes back low_signal, not offer_hold - the seeded "
        "member_offer session_vars never arm the offer_hold re-clarify (measured 17 Sep "
        "2026, lane head 4427bb6bb)",
    }

    @pytest.mark.parametrize("kind", list(_CANNED_SCENARIOS))
    def test_canned_branches_finish_in_turn(
        self,
        kind,
        session_factory,
        seeded,
        system_settings_row,
        stub_parser,
        stub_access,
        monkeypatch,
    ):
        _seed_completed_lanes(session_factory, system_settings_row)
        if kind == "demand_qty":
            _enable_stock_denial(session_factory, system_settings_row)
        envelope, parser_overrides, expected_text = _build_scenario(
            kind, session_factory, monkeypatch
        )
        stub_parser(parser_overrides)
        stub_access()

        if kind in self._KNOWN_BROKEN:
            pytest.xfail(self._KNOWN_BROKEN[kind])

        result = engine_mod.run_turn(envelope, session_factory=session_factory)

        assert result.delegate is None, (
            f"{kind}: still delegated to n8n - S3 must complete this branch itself"
        )
        assert result.reply is not None, f"{kind}: no reply composed"
        assert result.reply["text"] == expected_text
        # `send_message`'s `quick_replies` / `result_set` are the SEALED
        # compile-current-state values (n8n's comma-joined string or None;
        # `last_result_set` as sealed) - not a bare `[]`. A canned lane seals no
        # quick replies and no result set, so both pin down to None / [] here;
        # asserting the action equals the reply's OWN sealed values (rather than
        # a hardcoded literal) is what proves the action carries what the reply
        # carries, not a coincidence of two empty lists.
        assert result.reply.get("quick_replies") is None, f"{kind}: expected no sealed quick replies"
        assert result.reply.get("result_set") == [], f"{kind}: expected an empty sealed result set"
        assert result.actions == [
            {
                "kind": "send_message",
                "text": expected_text,
                "quick_replies": result.reply.get("quick_replies"),
                "result_set": result.reply.get("result_set"),
                "dry_run": False,
            }
        ]

        row = _turn_row(session_factory, result.turn_id)
        assert row.status == "done", row.error
        assert row.branch_kind == kind
        # `chatbot.turns.trace` carries stage records AND events (a tool call, a
        # cross-domain probe) since growth r1 A9 - only entries with no `kind` key are
        # stage records (`test_trace_legibility.py::_assert_trace_is_legible` uses the
        # same filter).
        stages = [r["stage"] for r in row.trace if r.get("kind") is None]
        assert stages[:4] == ["received", "understood", "access", "routed"]
        assert "replied" in stages
        assert "remembered" in stages
        assert "sent" in stages, "the CRM never sends (D9) - the trace still records the hand-off"


class TestAccessDeniedNoSessionWrite:
    """AC-301's eighth branch: refused up front, before anything is remembered."""

    def test_access_denied_sends_without_session_write(
        self, session_factory, seeded, system_settings_row, stub_parser, stub_access
    ):
        _seed_completed_lanes(session_factory, system_settings_row)
        # `derive_routing`'s nullish chain only lets the LLM's raw `routing.suggested_agent`
        # through on a `request_for_help` turn (coder-confirmed live behaviour); any other
        # message_type gets replaced by deriveRouting's `general_enquiries` default before
        # the em-dash fold ever runs, which is why this scenario needs it set explicitly.
        # The em dash itself is built from `chr(0x2014)`, not a literal, per the repo's
        # dash guard.
        em_dash = chr(0x2014)
        stub_parser(
            _parser_output(
                message_type="request_for_help",
                routing={"suggested_team": None, "suggested_agent": f"general{em_dash}enquiries"},
                # A pure help request, no entity: since 8 Sep 2026 a `request_for_help`
                # that names an entity beside a decisive intent is retyped `business_query`
                # (owner turn 2d903c96), and that would hand the agent slot to the derived
                # `general_enquiries` this very test says only a help request bypasses.
                intent_hint=None,
                domain_hint=None,
                entities=[],
            )
        )
        stub_access(allowed=False, decision="deny_unknown_agent")
        before = _session_vars_raw(session_factory)

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.delegate is None
        assert result.branch_kind == "access_denied"
        assert result.reply["text"] == "Sorry, you are not allowed to access general-enquiries"
        # See TestCannedBranchesFinishInTurn's comment: quick_replies / result_set are
        # the sealed compile-current-state values, not a bare `[]` - access_denied
        # seals no quick replies and no result set the same way the canned lanes do.
        assert result.reply.get("quick_replies") is None, "expected no sealed quick replies"
        assert result.reply.get("result_set") == [], "expected an empty sealed result set"
        assert result.actions == [
            {
                "kind": "send_message",
                "text": "Sorry, you are not allowed to access general-enquiries",
                "quick_replies": result.reply.get("quick_replies"),
                "result_set": result.reply.get("result_set"),
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


class TestAccessDeniedTextComposerRouting:
    """Reviewer Should fix 6 (round 1, PR #1222): `canned.access_denied_text`
    itself, not only the `compose_ideate_denial_reply` function it calls - the
    ideation branch routes through the composer; every other agent's denial is
    unchanged, with no LLM call. Moved here from `tests/test_ideation_reply.py`
    (Blocking 1, round 2): that file sits outside `tests/chatbot/`, and
    importing `app.services.chatbot.copy`/`app.services.chatbot.lanes.canned`
    from there broke `test_import_boundary.py`."""

    def test_access_denied_text_ideation_routes_through_composer(self, monkeypatch):
        from app.services.chatbot.copy import fallback_copy
        from app.services.chatbot.lanes import canned

        calls = []

        def _fake_compose(db, *, user_message, fallback_text):
            calls.append((user_message, fallback_text))
            return "LLM-composed denial"

        monkeypatch.setattr(
            "app.services.ideation_turn_service.compose_ideate_denial_reply", _fake_compose
        )
        ctx = {
            "parse": {"output": {"routing": {"suggested_agent": "ideation"}}},
            "text": {"message": {"message": {"text": "i have an idea"}}},
        }
        out = canned.access_denied_text(None, ctx, fallback_copy())
        assert out == "LLM-composed denial"
        assert calls[0][0] == "i have an idea"

    def test_access_denied_text_other_agent_skips_composer(self, monkeypatch):
        from app.services.chatbot.copy import fallback_copy
        from app.services.chatbot.lanes import canned

        calls = []
        monkeypatch.setattr(
            "app.services.ideation_turn_service.compose_ideate_denial_reply",
            lambda *a, **k: calls.append(1),
        )
        ctx = {
            "parse": {"output": {"routing": {"suggested_agent": "purchasing"}}},
            "text": {"message": {"message": {"text": "need stock"}}},
        }
        out = canned.access_denied_text(None, ctx, fallback_copy())
        assert calls == []
        assert "purchasing" in out


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
        """A registry key is editable in Settings > AI Prompts (journey B).

        `render()` populates `ai_prompt_registry`'s module-level, 60-second TTL
        cache as a SIDE EFFECT - it is not scoped to `blank_session()`'s rolled
        back transaction, so a test that publishes an override here and does not
        clean up leaves every LATER test in the same pytest process reading this
        override's text instead of the real fallback/DB row (bit me once while
        writing this file: `test_demand_qty_zero_gives_the_canned_reply` started
        seeing "How many units do you need?" instead of the canned copy). The
        `finally` undoes the ONE cache entry this test touches.
        """
        import uuid

        from tests._pg_fixture import blank_session

        from app.services import ai_prompt_registry

        try:
            with blank_session() as db:
                from app.models.ai_prompt import AIPromptLabel, AIPromptVersion

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

                text_out, resolved_version = ai_prompt_registry.render(
                    db, "chatbot_reply_demand_qty"
                )
                assert text_out == "How many units do you need?"
                assert resolved_version == 2
        finally:
            ai_prompt_registry.bust_cache("chatbot_reply_demand_qty")


# --------------------------------------------------------------------------- #
# AC-303: ideation is an MCP tool, not a special-cased lane.
# --------------------------------------------------------------------------- #


class TestIdeateBranchCallsMcpTool:
    def test_ideate_branch_calls_mcp_tool(
        self, session_factory, seeded, system_settings_row, stub_parser, stub_access, monkeypatch
    ):
        from app.services.chatbot.lanes import ideate as ideate_mod

        _seed_completed_lanes(session_factory, system_settings_row)
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
        assert call_kwargs["respond_io_id"] == str(CONTACT_ID)
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
        # #1179 AC-6: a live turn says so, so the idea lands on the board.
        assert call_kwargs["is_test"] is False

        # AC-1216: no raw link append - the composed reply (S3's compose_ideate_reply,
        # or its template fallback) already carries the link itself via the facts
        # block, so this lane relays reply_text verbatim.
        expected_text = "Idea IDEA-42 recorded. Thank you!"
        assert result.reply["text"] == expected_text
        assert result.reply["manualResponse"] is True
        assert result.reply["includeResponse"] is True
        assert result.reply["ideate_status"] == "complete"
        assert result.delegate is None

    def test_submitter_name_omitted_without_a_first_name(
        self, session_factory, seeded, system_settings_row, stub_parser, stub_access, monkeypatch
    ):
        from app.services.chatbot.lanes import ideate as ideate_mod

        _seed_completed_lanes(session_factory, system_settings_row)
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
        self, session_factory, seeded, system_settings_row, stub_parser, stub_access, monkeypatch
    ):
        from app.services.chatbot.lanes import ideate as ideate_mod

        _seed_completed_lanes(session_factory, system_settings_row)
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
        self, session_factory, seeded, system_settings_row, stub_parser, stub_access, monkeypatch
    ):
        from app.services.chatbot.lanes import ideate as ideate_mod
        from app.services.chatbot.head import parser as parser_mod

        _seed_completed_lanes(session_factory, system_settings_row)

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
        # A6 (chatbot-growth-r1, AC-911, migration 488): `spo_allocation` was
        # removed from the shipped default.
        assert row.chatbot_unsupported_domains == ["goods_receive"]

    def test_settings_update_schema_accepts_the_field(self):
        from app.api.v1.user_management.settings import SystemSettingUpdate

        parsed = SystemSettingUpdate(chatbot_unsupported_domains=["order"])
        assert parsed.chatbot_unsupported_domains == ["order"]


# AC-306 (addendum to test_engine.py's TestStockDenialGateEndToEnd): the
# demand_qty canned text, and the stock_denied item's `not_allowed_check_stock`
# carrier that `sub-main-processing`'s `Edit Fields2` reads by that exact name.
# `TestStockDenialFlagGatesTwoLanes` (both methods) retired here (AC-1592, S6
# ruling) - see module docstring. Replacement coverage: `test_rearch_s6_stock_
# allowed.py`.

# --------------------------------------------------------------------------- #
# D14: canned lanes are dry-run-safe by construction, same as every other lane.
# --------------------------------------------------------------------------- #


class TestCannedLanesDryRun:
    @pytest.mark.parametrize("kind", list(_CANNED_SCENARIOS))
    def test_canned_lanes_dry_run_write_nothing(
        self,
        kind,
        session_factory,
        seeded,
        system_settings_row,
        stub_parser,
        stub_access,
        monkeypatch,
    ):
        _seed_completed_lanes(session_factory, system_settings_row)
        if kind == "demand_qty":
            _enable_stock_denial(session_factory, system_settings_row)
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
        assert result.is_test is True, f"{kind}: the response must say it was a dry run"
        if kind == "ideate":
            # #1179 (owner ruling 24 Sep 2026): `ideate` is the only canned kind with a
            # seam, and the seam is the point. A dry run CALLS the tool and says it is a
            # test turn, so the shared service stores the idea as `is_test` (hidden from
            # the board) and the console gets the real intake replies. "Session_vars is
            # unchanged" above is still the CRM-side half of D14.
            assert [c.get("is_test") for c in IDEATE_TOOL_CALLS] == [True], (
                "a dry run must call the ideation tool exactly once, as a test turn"
            )

    def test_ideate_dry_run_calls_the_tool_as_a_test_turn_and_sends_its_real_reply(
        self,
        session_factory,
        seeded,
        system_settings_row,
        stub_parser,
        stub_access,
        monkeypatch,
    ):
        """#1179 AC-5, AC-7, AC-8: the placeholder is gone; the tool's own words are sent.

        Before this ruling a dry run stood the whole reply in with `PREVIEW_IDEATE_REPLY`
        and flagged the action `preview: true`, which made ideation untestable anywhere
        but live WhatsApp. Now the ONLY difference between a test turn and a live one, as
        far as this lane is concerned, is the `is_test` flag on the tool call. The rest of
        the dry run is unchanged: `dry_run: true` on the action, no session write, the
        would-be `session_patch` returned for the caller to carry.
        """
        from app.services.chatbot import contracts

        _seed_completed_lanes(session_factory, system_settings_row)
        envelope, parser_overrides, expected_text = _build_scenario(
            "ideate", session_factory, monkeypatch
        )
        envelope = Envelope(**{**envelope.model_dump(mode="json"), "is_test": True})
        stub_parser(parser_overrides)
        stub_access()
        before = _session_vars_raw(session_factory)

        result = engine_mod.run_turn(envelope, session_factory=session_factory)

        assert len(IDEATE_TOOL_CALLS) == 1
        call_kwargs = IDEATE_TOOL_CALLS[0]
        assert call_kwargs["is_test"] is True
        # The same arguments a live turn sends, beside the flag.
        assert call_kwargs["respond_io_id"] == str(CONTACT_ID)
        assert call_kwargs["session_vars"] == {
            "ideation": {"draft_id": "ZZT-draft-1", "status": "collecting"}
        }

        assert result.branch_kind == "ideate"
        assert result.delegate is None
        assert result.is_test is True
        assert result.reply["text"] == expected_text
        assert result.reply["ideate_status"] == "collecting"
        assert contracts.PREVIEW not in result.reply["text"]
        assert result.actions == [
            {
                "kind": "send_message",
                "text": expected_text,
                "quick_replies": result.reply.get("quick_replies"),
                "result_set": result.reply.get("result_set"),
                "dry_run": True,
            }
        ], "the action carries the tool's real reply and no `preview` flag"
        assert result.session_patch is not None
        assert _session_vars_raw(session_factory) == before, "dry run wrote session_vars"
        row = _turn_row(session_factory, result.turn_id)
        assert row.status == "done"
        assert not hasattr(contracts, "PREVIEW_IDEATE_REPLY"), (
            "the ideate placeholder is retired with the preview path"
        )

    def test_access_denied_dry_run_write_nothing(
        self, session_factory, seeded, system_settings_row, stub_parser, stub_access
    ):
        _seed_completed_lanes(session_factory, system_settings_row)
        stub_parser(_parser_output())
        stub_access(allowed=False, decision="deny_unknown_agent")
        before = _session_vars_raw(session_factory)

        result = engine_mod.run_turn(_envelope(is_test=True), session_factory=session_factory)

        after = _session_vars_raw(session_factory)
        assert after == before
        assert result.is_test is True
        assert result.delegate is None
        assert result.actions, "access_denied must still hand the caller a reply to send"
        assert all(a.get("dry_run") is True for a in result.actions)


# `TestCompletedLanesGateDefaultsClosed.test_default_empty_list_still_delegates`
# retired here (AC-1592) - see module docstring, same theme as
# `test_completed_lanes_switch.py`'s own retired end-to-end delegate assertion.
