"""`route.decide`, at the two places the port does NOT simply reproduce n8n.

The replay suite already proves every captured turn routes the same way. This file covers
the two properties a fixture cannot show, because n8n has never exhibited them:

* **R1 / H1 - the corrected vocabulary behind a flag.** Live tests
  `intent_hint === 'stock_check'` while the parser emits `check_stock`, so the
  `stock_denied` / `demand_qty` lanes are dead by typo (0 of 150 live fixtures). The port
  uses the right word, and `chatbot_stock_denial_enabled` decides whether the predicate is
  evaluated at all. OFF is the default and OFF is byte-identical to today.
* **the ladder's laziness.** `_is_stock_check_denied` reads
  `custom_fields.find(...).value` with no guard and THROWS when the contact has no
  `is_allowed_stock` field. That throw is live's own expression and must stay unreachable
  for every turn that leaves the ladder earlier - which is a property of the ORDER, not of
  any single predicate, and would go unnoticed until a real contact hit it.
"""
from __future__ import annotations

import pytest

from app.services.chatbot.head.route import decide, route_turn


def _ctx(qf: dict, *, allowed: bool = True, custom_fields=None, variables=None, text=""):
    return {
        "contact": {"id": "ZZT-1", "custom_fields": custom_fields if custom_fields is not None else []},
        "text": {"message": {"message": {"type": "text", "text": text}}},
        "session": {"session_vars": {"variables": variables or {}}},
        "parse": {"output": qf},
        "access": {"allowed": allowed, "decision": "allow" if allowed else "deny_no_access"},
        "media": None,
    }


def _stock_qf():
    return {
        "message_type": "business_query",
        "intent_hint": "check_stock",
        "domain_hint": "inventory",
        "entities": [{"raw": "SRTWC8517", "hint": "product", "current_message": True}],
        "demand_qty": None,
    }


class TestStockDenialGate:
    def test_off_by_default_the_lane_is_unreachable(self) -> None:
        ctx = _ctx(_stock_qf(), custom_fields=[{"name": "is_allowed_stock", "value": "false"}])
        branch, _ = decide(ctx)
        assert branch == "business_query"

    def test_off_the_predicate_is_never_even_evaluated(self) -> None:
        """The contact has NO is_allowed_stock field, so evaluating it would THROW."""
        ctx = _ctx(_stock_qf(), custom_fields=[])
        branch, _ = decide(ctx, stock_denial_enabled=False)
        assert branch == "business_query"

    def test_on_a_contact_without_stock_access_is_denied(self) -> None:
        """AC-306's behaviour half: the corrected `check_stock` vocabulary."""
        qf = _stock_qf()
        qf["demand_qty"] = 5
        ctx = _ctx(qf, custom_fields=[{"name": "is_allowed_stock", "value": "false"}])
        branch, _ = decide(ctx, stock_denial_enabled=True)
        assert branch == "stock_denied"

    def test_on_a_missing_quantity_asks_for_one(self) -> None:
        ctx = _ctx(_stock_qf(), custom_fields=[{"name": "is_allowed_stock", "value": "false"}])
        branch, _ = decide(ctx, stock_denial_enabled=True)
        assert branch == "demand_qty"

    def test_on_a_contact_WITH_stock_access_is_answered_normally(self) -> None:
        ctx = _ctx(_stock_qf(), custom_fields=[{"name": "is_allowed_stock", "value": "true"}])
        branch, _ = decide(ctx, stock_denial_enabled=True)
        assert branch == "business_query"

    def test_on_a_missing_field_still_throws_exactly_as_live_does(self) -> None:
        """Live's own expression has no optional chaining. Reproduced, not smoothed over."""
        ctx = _ctx(_stock_qf(), custom_fields=[])
        with pytest.raises(TypeError):
            decide(ctx, stock_denial_enabled=True)


class TestLadderLaziness:
    @pytest.mark.parametrize(
        ("qf", "expected"),
        [
            ({"message_type": "casual"}, "low_signal"),
            ({"message_type": "clarification"}, "clarify_menu"),
            ({"message_type": "business_query", "domain_hint": "goods_receive"}, "not_supported"),
            (
                {"message_type": "request_for_help", "domain_hint": None},
                "out_of_scope",
            ),
            (
                {
                    "message_type": "business_query",
                    "intent_hint": "check_promotion",
                    "domain_hint": "promotion",
                },
                "check_promotion",
            ),
        ],
    )
    def test_a_turn_that_leaves_the_ladder_earlier_never_reaches_the_throwing_predicate(
        self, qf, expected
    ) -> None:
        # No `is_allowed_stock` field at all: reaching the stock predicate would throw.
        ctx = _ctx(qf, custom_fields=[])
        branch, _ = decide(ctx, stock_denial_enabled=True)
        assert branch == expected

    def test_access_denied_short_circuits_before_everything(self) -> None:
        ctx = _ctx(_stock_qf(), allowed=False, custom_fields=[])
        branch, _ = decide(ctx, stock_denial_enabled=True)
        assert branch == "access_denied"


class TestItemShape:
    def test_a_tag_only_arm_emits_only_the_branch_kind(self) -> None:
        """Those five arms began with a STRIPPING Set node; the fan-in must not move."""
        ctx = _ctx({"message_type": "clarification"})
        assert route_turn(ctx) == [{"json": {"branch_kind": "clarify_menu"}}]

    def test_every_other_arm_keeps_the_access_response_and_gains_one_key(self) -> None:
        ctx = _ctx({"message_type": "casual"})
        assert route_turn(ctx) == [
            {"json": {"allowed": True, "decision": "allow", "branch_kind": "low_signal"}}
        ]


class TestTierRePick:
    def _tier_ctx(self, text: str, **overrides):
        variables = {
            "tier_menu": [
                {"idx": 1, "label": "Office", "value": "office"},
                {"idx": 2, "label": "Dealer", "value": "dealer"},
                {"idx": 3, "label": "End user", "value": "end_user"},
            ]
        }
        variables.update(overrides)
        return _ctx(
            {"message_type": "casual", "domain_hint": None},
            variables=variables,
            text=text,
            custom_fields=[],
        )

    def test_a_bare_digit_in_range_picks_that_tier(self) -> None:
        branch, stamp = decide(self._tier_ctx("2"))
        assert branch == "check_promotion"
        assert stamp == {"tier_pick": "dealer", "tier_pick_domain": "promotion"}

    def test_an_out_of_range_digit_re_asks_rather_than_reusing_a_stale_tier(self) -> None:
        branch, stamp = decide(self._tier_ctx("9"))
        assert branch == "check_promotion"
        assert stamp == {"tier_pick_invalid": True, "tier_pick_domain": "promotion"}

    def test_a_menu_word_matches_EXACTLY_never_by_substring(self) -> None:
        """H42: a substring match mis-mapped menu words. The owner's rule is exact match."""
        assert decide(self._tier_ctx("dealer"))[1]["tier_pick"] == "dealer"
        # "dealership" contains "dealer" and must NOT map to it.
        assert decide(self._tier_ctx("dealership"))[0] == "low_signal"

    def test_a_live_member_roster_outranks_the_tier_intercept(self) -> None:
        """A CS-member pick can fire a real assignment; the tier menu must not steal it."""
        branch, stamp = decide(self._tier_ctx("2", selection_context="member_offer"))
        assert branch == "low_signal"
        assert stamp == {}

    def test_a_thread_that_never_offered_a_menu_is_untouched(self) -> None:
        ctx = _ctx({"message_type": "casual"}, variables={}, text="2", custom_fields=[])
        branch, stamp = decide(ctx)
        assert branch == "low_signal"
        assert stamp == {}
