"""AC-9 (PLAN-broaden-domain-switch): "check stock srtwc286" then "Any incoming" ends in the
incoming domain, through the real resolve+gate+answer lane, never `needs_scope`.

Follows the wiring `test_pass4_item2_last_month_keeps_customer_scope.py` established: the
real `resolve_entity` seam (`_wire_real_resolve_entity`), a recording MCP stub standing in
for the tool call, and a stubbed parser feeding the model's own two-turn emission. TWO real
`run_turn` calls on the SAME contact, business lane + ordering (S7, "the CRM owns the tail")
both on, so turn 1's answer is what persists to `respond_contacts.session_vars` for turn 2
to read - no hand-seeded `previous_conversation_state`.

The fetch stub answers with a proper `{items, has_result: True}` render envelope (measured
via `fetch._extract_envelope`, which needs a top-level `items` list to recognise the payload
at all) - a bare `{"answers": [...]}` degrades to `has_result: False` and drives both turns
into the miss/cross-domain ladder, which reaches for the REAL production MCP seam
(`answer_services_for` is not stubbed here, only `fetch_services` is) and times out against
nothing listening on `ai_assistant_mcp_url`.

Postgres only (`tests/_pg_fixture.py` via `tests/chatbot/conftest.py`'s `session_factory`).
No em or en dashes.
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import text

from app.models.company import Company
from app.services.chatbot import engine as engine_mod
from tests._pg_fixture import unique_code
from tests.chatbot.conftest import set_chatbot_switches
from tests.chatbot.test_engine import CONTACT_ID, _envelope
from tests.chatbot.test_engine_company_scope import _seed_product
from tests.chatbot._shared_turn_helpers import _stub_parser


@pytest.fixture()
def seeded(session_factory):
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {"cid": CONTACT_ID, "phone": "+60000000009", "sv": json.dumps({"variables": {}})},
    )
    db.commit()
    return db


def _turn1_qf(**overrides: Any) -> dict[str, Any]:
    """"check stock srtwc286": inventory / check_stock, the product named this turn."""
    base = {
        "message_type": "business_query",
        "intent_hint": "check_stock",
        "domain_hint": "inventory",
        "scope_intent": "specific",
        "is_affirmative": None,
        "user_goal": "checking stock for a product",
        "access_levels": [],
        "broaden_axis": None,
        "date_mode": None,
        "date_filter_start": None,
        "date_filter_end": None,
        "match_mode": "and",
        "demand_qty": None,
        "entities": [
            {
                "raw": "srtwc286",
                "hint": "product",
                "canonical_code": None,
                "current_message": True,
                "confident": True,
            }
        ],
        "entity_op": "replace_combine",
        "scope_exclusive": False,
        "requested_attributes": [],
        "contains_flyer": False,
        "reference_positions": [],
        "reference_target": None,
        "person_mention": None,
        "is_active": None,
        "order_status": None,
        "correction": False,
        "routing": {"suggested_team": None, "suggested_agent": None},
        "escalation": {"is_escalation_confirmation": False, "company_pick": None},
    }
    base.update(overrides)
    return base


def _turn2_qf(**overrides: Any) -> dict[str, Any]:
    """"Any incoming": exec 15121180's own raw parser shape - a coherent (incoming,
    check_incoming) pair beside `broaden_axis: all`, not the "all products" wander the
    restore block exists for."""
    base = {
        "message_type": "business_query",
        "intent_hint": "check_incoming",
        "domain_hint": "incoming",
        "scope_intent": "broaden",
        "is_affirmative": None,
        "user_goal": "trying to broaden the incoming shipment search to all records",
        "access_levels": [],
        "broaden_axis": "all",
        "date_mode": None,
        "date_filter_start": None,
        "date_filter_end": None,
        "match_mode": "and",
        "demand_qty": None,
        "entities": [],
        "entity_op": "clear",
        "scope_exclusive": False,
        "requested_attributes": [],
        "contains_flyer": False,
        "reference_positions": [],
        "reference_target": None,
        "person_mention": None,
        "is_active": None,
        "order_status": None,
        "correction": False,
        "routing": {"suggested_team": "purchasing", "suggested_agent": "incoming_stock_enquiries"},
        "escalation": {"is_escalation_confirmation": False, "company_pick": None},
    }
    base.update(overrides)
    return base


def _wire_with_a_real_render_envelope(session_factory, monkeypatch) -> list[tuple[str, dict]]:
    """`_wire`'s own real-resolve-entity wiring, plus a fetch stub that answers with a
    proper render envelope (`items` + `has_result: True`) instead of `_wire`'s bare
    `{"answers": [...]}, "has_result": True}` - which `fetch._extract_envelope` does not
    recognise (it needs a top-level `items` list), so it degrades to `has_result: False`
    and both turns fall into the miss/cross-domain ladder."""
    from app.services.chatbot.lanes.business import services as business_services_mod

    db = session_factory()
    db.execute(
        text("UPDATE system_settings SET chatbot_completed_lanes = CAST(:l AS jsonb)"),
        {"l": '["business_query"]'},
    )
    db.commit()
    from tests.chatbot.test_engine_company_scope import _wire_real_resolve_entity

    _wire_real_resolve_entity(monkeypatch)

    calls: list[tuple[str, dict]] = []

    def recording_mcp_call(name: str, args: dict) -> str:
        calls.append((name, dict(args)))
        return json.dumps(
            {
                "items": [{"product_code": "SRTWC286", "note": "ZZT stub row"}],
                "has_result": True,
                "intro": "Found it.",
            }
        )

    def fake_fetch_services(db: Any):
        FetchServices = business_services_mod.FetchServices
        return FetchServices(mcp_call=recording_mcp_call)

    monkeypatch.setattr(engine_mod.business_services, "fetch_services", fake_fetch_services)
    return calls


class TestBroadenBesideANewDomainReachesIncomingNotNeedsScope:
    def test_any_incoming_after_check_stock_ends_in_incoming_never_needs_scope(
        self, seeded, session_factory, monkeypatch
    ):
        company = Company(name=unique_code("BDS"), code=unique_code("BDS")[:50])
        db = session_factory()
        db.add(company)
        db.commit()
        company_id = str(company.id)
        product_id = _seed_product(session_factory, company_id=company_id, code="SRTWC286")

        set_chatbot_switches(session_factory, business_lane=True, ordering=True)
        calls = _wire_with_a_real_render_envelope(session_factory, monkeypatch)
        monkeypatch.setattr(
            engine_mod, "_contact_company_scope", lambda factory, cid: frozenset({company_id})
        )

        # -- turn 1: "check stock srtwc286" ------------------------------------------- #
        _stub_parser(monkeypatch, _turn1_qf(), space_id="ZZT-bds-space")
        envelope1 = _envelope(is_test=False)
        envelope1.message["message"]["messageId"] = "ZZT-bds-turn-1"
        envelope1.message["message"]["message"]["text"] = "check stock srtwc286"
        head1 = engine_mod.run_turn(envelope1, session_factory=session_factory)
        assert head1.status == "done", head1.error

        # -- turn 2: "Any incoming" ---------------------------------------------------- #
        _stub_parser(monkeypatch, _turn2_qf(), space_id="ZZT-bds-space")
        envelope2 = _envelope(is_test=False)
        envelope2.message["message"]["messageId"] = "ZZT-bds-turn-2"
        envelope2.message["message"]["message"]["text"] = "Any incoming"
        head2 = engine_mod.run_turn(envelope2, session_factory=session_factory)
        assert head2.status == "done", head2.error

        assert head2.ctx["parse"]["output"]["domain_hint"] == "incoming"
        # The lane resolved and answered - never `needs_scope` (a bare positive check, not
        # `!= "needs_scope"`, which would also pass on a KeyError-shaped missing branch_kind).
        assert head2.item.get("branch_kind") == "business_query"

        incoming_calls = [c for c in calls if c[0].startswith("crm_incoming_stock")]
        assert incoming_calls, f"no incoming-domain tool was ever called: {calls!r}"
        _, args = incoming_calls[0]
        assert args.get("product_ids") == [product_id], (
            "the carried SRTWC286 product must reach the incoming tool call, not go out "
            f"unscoped: {args!r}"
        )
