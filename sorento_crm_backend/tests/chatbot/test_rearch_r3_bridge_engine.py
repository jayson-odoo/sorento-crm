"""R3 RED tests, engine level - a real `engine.run_turn` through `_run_turn`
(`tests/chatbot/test_outstanding_lane.py`'s harness, reused per the captain's brief;
`tests/chatbot/test_sales_report_lane.py` re-exports the same name).

UAC: AC-1683 (turn/compose reached only outside the bridge's two arms), AC-1694's
pytest half (customer picker), AC-1697/AC-1698 (promotion tier picker + multi-select),
plus the coordinator's own add-on (a one-entitled-tier promotion ask never asks at all).

**Measured, live, on this branch (post R2 merge, `7c3ada3a5`), via a throwaway debug
probe run and deleted before this file was written - not guessed:**

1. A promotion ask that needs a tier pick (`access_types` returning ONE row, "Sorento
   Dealer") answers TODAY with `turn/compose.py`'s own entitlement-BLIND tier ask:
   `'Product: SRTWT7445\\nWhich price tier applies to you?\\n1. dealer\\n2. office\\n
   3. end user'`, quick_replies `'dealer, office, end user'`, zero tool calls
   (`captured == []`), lowercase option labels, EVERY canonical tier offered
   regardless of what the contact actually holds. Production (`answer.
   access_level_choice_message`, reached through `resolve_gate.run`'s real
   `access_check` entry R2 now wires up) would ask about ONLY the one entitled tier -
   in fact would not ask at all (see point 3).
2. An ambiguous customer order ask ("orders for hanlim", two same-named-family
   customer matches) answers TODAY with `turn/compose.py`'s own customer ask:
   `'Which customer do you mean?\\n1. 300-H070 - no DO\\n2. 300-H071 - no DO'` - the
   resolved CODE as the label, no "Please choose:", no company-code suffix. Production
   (`gate.run_gate` + `pickers.annotate_customer`) prints the CUSTOMER NAME with its
   company suffix ("HANLIM TRADING SDN BHD (SRT)") and the "Please choose:" line.
3. **The coordinator's add-on, measured**: with exactly ONE entitled tier
   (`tier_gate.needs_tier_ask` returns `False` when `len(entitled_tiers) <= 1`,
   `tier_gate.py:148`), production does not ask at all - it recomposes access_levels
   for that one tier and proceeds straight to the fetch. Today's engine still shows
   the SAME three-option, entitlement-blind ask as point 1 (asking is not gated on
   entitlement count at all on this path) - genuinely RED, not a green control.

Every test below either spies the seam it grades (`turn.compose.compose_question`,
`turn.compose.compose`, `tail.reply_ladder.compose_reply`, `engine.run_tail`) or
computes its expected text from the same production-function chain
`test_rearch_r3_answer_bridge.py` uses, so the assertion is never a retyped guess.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.chatbot import copy as copy_mod
from app.services.chatbot import engine as engine_mod
from app.services.chatbot.lanes.business import answer as answer_mod
from app.services.chatbot.lanes.business.services import ResolveGateServices
from app.services.chatbot.tail import outcome as outcome_mod
from app.services.chatbot.tail import reply_ladder
from app.services.chatbot.turn import compose as turn_compose
from tests.chatbot.test_engine import _parser_output
from tests.chatbot.test_outstanding_lane import (
    HANLIM_CODE_1,
    HANLIM_CODE_2,
    HANLIM_UUID_1,
    HANLIM_UUID_2,
    PRODUCT_CODE,
    PRODUCT_UUID,
    _ambiguous_hanlim_resolve_services,
    _run_turn,
    _seed_contact,
)


def _one_tier_resolve_services(*, access_names: list[str]) -> ResolveGateServices:
    def _resolve_entity(body: dict[str, Any]) -> dict[str, Any]:
        asked = list(body.get("tokens") or [])
        match = {
            "uuid": PRODUCT_UUID,
            "entity_type": "product",
            "canonical_code": PRODUCT_CODE,
            "match_tier": "exact",
        }
        return {
            "tokens": asked,
            "resolutions": [{"raw": raw, "token": raw, "matches": [match]} for raw in asked],
            "unresolved_tokens": [],
        }

    return ResolveGateServices(
        access_types=lambda **_: [{"name": n} for n in access_names],
        resolve_entity=_resolve_entity,
        probe=lambda **_: None,
    )


def _promo_qf() -> dict[str, Any]:
    return _parser_output(
        domain_hint="promotion",
        intent_hint="check_promotion",
        entities=[
            {
                "raw": PRODUCT_CODE,
                "hint": "product",
                "canonical_code": None,
                "current_message": True,
                "confident": True,
            }
        ],
    )


# --------------------------------------------------------------------------- #
# AC-1697 / AC-1698 - the promotion tier picker
# --------------------------------------------------------------------------- #


class TestPromotionAskUsesProductionCopy:
    def test_two_entitled_tiers_reply_starts_and_ends_per_production(
        self, session_factory, monkeypatch
    ) -> None:
        """AC-1697: 'Which access level do you need for {product}?' header, one
        stamped line per ENTITLED tier only, closing 'Reply with the number(s)...'
        line - never today's bare 'Which price tier applies to you?' listing every
        canonical tier regardless of entitlement."""
        _seed_contact(session_factory, variables={})
        result, captured = _run_turn(
            session_factory,
            monkeypatch,
            qf=_promo_qf(),
            text_body=f"promo for {PRODUCT_CODE}",
            msg_id="zzt-r3-promo-two-tier",
            resolve_services=_one_tier_resolve_services(
                access_names=["Sorento Dealer", "Sorento Office"]
            ),
            mcp_response={"has_result": False, "items": []},
        )
        reply = (result.reply or {}).get("text") or ""
        assert reply.startswith(f"Which access level do you need for {PRODUCT_CODE}?"), reply
        assert 'Reply with the number(s), e.g. "1", "1 and 2", or "all".' in reply, reply
        assert "Which price tier applies to you?" not in reply, (
            "must not be the entitlement-blind turn/compose.py tier ask"
        )
        # only the two entitled tiers, never the third (end_user)
        assert "End user" not in reply and "end user" not in reply, reply

    def test_pending_kind_tier_pick_entity_type_tier_not_access_tier(
        self, session_factory, monkeypatch
    ) -> None:
        from tests.chatbot.test_outstanding_lane import _session_of

        _seed_contact(session_factory, variables={})
        _run_turn(
            session_factory,
            monkeypatch,
            qf=_promo_qf(),
            text_body=f"promo for {PRODUCT_CODE}",
            msg_id="zzt-r3-promo-pending-shape",
            resolve_services=_one_tier_resolve_services(
                access_names=["Sorento Dealer", "Sorento Office"]
            ),
            mcp_response={"has_result": False, "items": []},
        )
        session = _session_of(session_factory)
        open_question = session.get("open_question") or {}
        assert open_question.get("kind") == "tier_pick", open_question
        options = open_question.get("options") or []
        assert len(options) == 2, options
        assert [o.get("entity_type") for o in options] == ["tier", "tier"], (
            "an option carrying entity_type == 'access_tier' never reaches "
            "focus.tier (apply._CODE_ONLY_FIELDS only recognises 'tier')"
        )


class TestPromotionAskMultiSelect:
    """AC-1698: '1', '1 and 2' and 'all' each settle one/two/every chosen tier and
    run the promotion fetch per chosen tier. Graded on the CAPTURED tool calls, not
    on reply text. The 'single' case is a MEASURED GREEN CONTROL: today's
    entitlement-blind tier_pick already uses entity_type == 'tier' on its own
    options (it is not the bridge's mechanism, but `apply._answer_pending`'s
    generic single-position handling already works for it), so answering '1' with
    one already runs one promotion fetch. 'one-and-two' and 'all' are genuinely
    RED: only one promotion call fires regardless of how many positions/broaden_axis
    named multiple tiers."""

    @pytest.mark.parametrize(
        "answer_text,answer_overrides,expected_tier_count",
        [
            ("1", {"reference_positions": [1]}, 1),
            ("1 and 2", {"reference_positions": [1, 2]}, 2),
            ("all", {"broaden_axis": "all"}, 2),
        ],
        ids=["single", "one-and-two", "all"],
    )
    def test_answering_the_tier_pick_runs_the_promotion_fetch_per_chosen_tier(
        self, session_factory, monkeypatch, answer_text: str, answer_overrides: dict, expected_tier_count: int
    ) -> None:
        _seed_contact(session_factory, variables={})
        resolve_services = _one_tier_resolve_services(
            access_names=["Sorento Dealer", "Sorento Office"]
        )
        _result1, captured1 = _run_turn(
            session_factory,
            monkeypatch,
            qf=_promo_qf(),
            text_body=f"promo for {PRODUCT_CODE}",
            msg_id="zzt-r3-promo-ms-ask",
            resolve_services=resolve_services,
            mcp_response={"has_result": False, "items": []},
        )
        assert captured1 == [], (
            "the tier ask itself must fire no tool call - a fetch happens only once "
            f"a tier is chosen: {captured1}"
        )
        answer_qf = _parser_output(
            domain_hint=None,
            intent_hint=None,
            entities=[],
            **answer_overrides,
        )
        _result2, captured2 = _run_turn(
            session_factory,
            monkeypatch,
            qf=answer_qf,
            text_body=answer_text,
            msg_id="zzt-r3-promo-ms-answer",
            resolve_services=resolve_services,
            mcp_response={"has_result": False, "items": []},
        )
        promo_calls = [c for c in captured2 if "promotion" in c[0]]
        assert len(promo_calls) == expected_tier_count, (
            f"{answer_text!r} must run the promotion fetch once per chosen tier: {captured2}"
        )


class TestOneEntitledTierNeverAsks:
    """Coordinator add-on: with exactly one entitled tier, production proceeds
    straight to the fetch (`tier_gate.needs_tier_ask` -> False for
    `len(entitled_tiers) <= 1`, `tier_gate.py:148`) - no tier_pick is ever opened.
    Measured RED today (see module docstring point 3): today's engine still shows
    the entitlement-blind three-option ask and makes no tool call at all."""

    def test_no_tier_pick_opens_and_the_fetch_runs_for_the_one_tier(
        self, session_factory, monkeypatch
    ) -> None:
        from tests.chatbot.test_outstanding_lane import _session_of

        _seed_contact(session_factory, variables={})
        _result, captured = _run_turn(
            session_factory,
            monkeypatch,
            qf=_promo_qf(),
            text_body=f"promo for {PRODUCT_CODE}",
            msg_id="zzt-r3-promo-one-tier",
            resolve_services=_one_tier_resolve_services(access_names=["Sorento Dealer"]),
            mcp_response={"has_result": False, "items": []},
        )
        session = _session_of(session_factory)
        open_question = session.get("open_question")
        assert open_question is None or open_question.get("kind") != "tier_pick", (
            f"a single-entitled-tier promotion ask must not raise a tier picker: {open_question}"
        )
        assert len(captured) >= 1, (
            "a single-entitled-tier promotion ask must proceed straight to the fetch, "
            f"but no tool call was made: {captured}"
        )


# --------------------------------------------------------------------------- #
# AC-1694 - the ambiguous customer picker (pytest half)
# --------------------------------------------------------------------------- #


def _expected_customer_picker_text(*, probe_rows: list[dict[str, Any]]) -> str:
    """The SAME production chain `test_rearch_r3_answer_bridge.py` computes from,
    fed the `_ambiguous_hanlim_resolve_services` fixture's own two rows so the two
    files cannot silently disagree about what "production text" means."""
    from app.services.chatbot.lanes.business import pickers

    gate = {
        "gate_clarification": (
            "Which customer do you mean? Please choose:\n"
            "1. HANLIM TRADING SDN BHD (SRT)\n"
            "2. HANLIM HARDWARE SDN BHD (SRT)"
        ),
        "compatible_entities": [
            {"uuid": HANLIM_UUID_1, "entity_type": "customer", "code": HANLIM_CODE_1,
             "title": "HANLIM TRADING SDN BHD (SRT)"},
            {"uuid": HANLIM_UUID_2, "entity_type": "customer", "code": HANLIM_CODE_2,
             "title": "HANLIM HARDWARE SDN BHD (SRT)"},
        ],
        "require_specific": False,
        "gate_debug": {"domain": "order"},
    }
    parser = _parser_output(
        domain_hint="order", intent_hint="check_order",
        entities=[{"raw": "hanlim", "hint": "customer", "current_message": True}],
    )
    annotated = pickers.annotate_customer(gate, probe={"answers": probe_rows}, parser=parser)
    lane_item = {**annotated, "branch_kind": "not_found"}
    ctx = {"parse": {"output": parser}}
    canned = copy_mod.fallback_copy()
    catalog = outcome_mod.escalate_catalog(lane_item, ctx, canned, incoming_picker=lane_item)
    built = outcome_mod.build_outcome([{"json": catalog}], {"escalate-catalog": catalog})
    return reply_ladder.compose_reply(built[0]["json"]["outcome"])["text"]


class TestCustomerAskUsesProductionCopy:
    def test_reply_matches_the_production_chain(self, session_factory, monkeypatch) -> None:
        def spy_probe(*, tool, contact_id, entities, semantic_input, user_prompt):
            return {"items": [], "has_result": False}

        _seed_contact(session_factory, variables={})
        result, captured = _run_turn(
            session_factory,
            monkeypatch,
            qf=_parser_output(
                domain_hint="order", intent_hint="check_order", order_status=None,
                entities=[
                    {"raw": "hanlim", "hint": "customer", "canonical_code": None,
                     "current_message": True, "confident": True},
                ],
            ),
            text_body="orders for hanlim",
            msg_id="zzt-r3-cust-ask",
            attributes=["sales_orders.outstanding"],
            resolve_services=_ambiguous_hanlim_resolve_services(spy_probe),
        )
        reply = (result.reply or {}).get("text") or ""
        expected = _expected_customer_picker_text(probe_rows=[])
        assert reply == expected, (reply, expected)
        assert reply.startswith("Which customer do you mean? Please choose:"), reply
        assert captured == []


# --------------------------------------------------------------------------- #
# AC-1683 - turn/compose reached only OUTSIDE the bridge's two arms
# --------------------------------------------------------------------------- #


class TestComposeQuestionIsNotReachedForTheBridgedArms:
    def test_compose_question_never_called_for_the_promotion_tier_ask(
        self, session_factory, monkeypatch
    ) -> None:
        calls: list[Any] = []
        real = turn_compose.compose_question

        def _spy(pending, state=None):
            calls.append(pending)
            return real(pending, state)

        monkeypatch.setattr(turn_compose, "compose_question", _spy)
        _seed_contact(session_factory, variables={})
        _run_turn(
            session_factory,
            monkeypatch,
            qf=_promo_qf(),
            text_body=f"promo for {PRODUCT_CODE}",
            msg_id="zzt-r3-spy-compose-question",
            resolve_services=_one_tier_resolve_services(
                access_names=["Sorento Dealer", "Sorento Office"]
            ),
            mcp_response={"has_result": False, "items": []},
        )
        assert calls == [], (
            "a single-domain business turn's access_ask must be composed by the "
            f"bridge + tail/reply_ladder, never turn/compose.compose_question: {calls}"
        )

    def test_compose_reply_is_called_once_for_the_promotion_tier_ask(
        self, session_factory, monkeypatch
    ) -> None:
        calls: list[Any] = []
        real = reply_ladder.compose_reply

        def _spy(outcome):
            calls.append(outcome)
            return real(outcome)

        monkeypatch.setattr(reply_ladder, "compose_reply", _spy)
        _seed_contact(session_factory, variables={})
        _run_turn(
            session_factory,
            monkeypatch,
            qf=_promo_qf(),
            text_body=f"promo for {PRODUCT_CODE}",
            msg_id="zzt-r3-spy-compose-reply",
            resolve_services=_one_tier_resolve_services(
                access_names=["Sorento Dealer", "Sorento Office"]
            ),
            mcp_response={"has_result": False, "items": []},
        )
        assert len(calls) == 1, (
            f"the bridge must produce this turn's text via tail/reply_ladder.compose_reply "
            f"exactly once: {len(calls)} calls"
        )

    def test_control_a_multi_domain_ask_still_reaches_turn_compose_compose(
        self, session_factory, monkeypatch
    ) -> None:
        """Control (documented, may already be green): a multi-domain fetch is out
        of R3's scope (single-domain plans only) and must keep using
        `turn/compose.compose` - a bridge that swallowed every business turn would
        be the over-correction the plan's own Hazards section warns against."""
        calls: list[Any] = []
        real = turn_compose.compose

        def _spy(envelopes, state, policy, ctx):
            calls.append(envelopes)
            return real(envelopes, state, policy, ctx)

        monkeypatch.setattr(turn_compose, "compose", _spy)
        _seed_contact(session_factory, variables={})
        _run_turn(
            session_factory,
            monkeypatch,
            qf=_parser_output(
                domain_hint=None,
                intent_hint=None,
                entities=[
                    {"raw": PRODUCT_CODE, "hint": "product", "canonical_code": None,
                     "current_message": True, "confident": True},
                ],
                asks=[{"domain": "inventory"}, {"domain": "incoming"}],
            ),
            text_body=f"stock and incoming for {PRODUCT_CODE}",
            msg_id="zzt-r3-multi-domain-control",
            mcp_response={"has_result": False, "items": []},
        )
        assert len(calls) >= 1, (
            "a multi-domain plan must still be composed by turn/compose.compose"
        )


class TestOneSessionWriter:
    def test_run_tail_is_not_entered_for_a_bridged_business_turn(
        self, session_factory, monkeypatch
    ) -> None:
        """Control (documented, likely already green): `engine.run_tail` is the
        CANNED-lane session writer (its own docstring: 'used by the canned lanes
        through engine.run_tail'); a business turn - bridged or not - has always
        gone through `_run_answer`'s own tail. Kept as a standing guard so a future
        change cannot silently route a bridged turn through the other writer."""
        calls: list[Any] = []
        real = engine_mod.run_tail

        def _spy(*args, **kwargs):
            calls.append((args, kwargs))
            return real(*args, **kwargs)

        monkeypatch.setattr(engine_mod, "run_tail", _spy)
        _seed_contact(session_factory, variables={})
        _run_turn(
            session_factory,
            monkeypatch,
            qf=_promo_qf(),
            text_body=f"promo for {PRODUCT_CODE}",
            msg_id="zzt-r3-spy-run-tail",
            resolve_services=_one_tier_resolve_services(
                access_names=["Sorento Dealer", "Sorento Office"]
            ),
            mcp_response={"has_result": False, "items": []},
        )
        assert calls == [], calls
