"""Port of two `test_growth_r1_review_fixes.py` classes (AC-1592, queue item 2,
chatbot-turn-rearch, 16 Sep 2026) onto the real APPLY/ROUTE seam - the same
`apply()`/`route()` pair `test_rearch_port_route_unit.py` already uses for this file's
sibling port, chosen because both defects are DECISIONS `turn/apply.py::_lane()` /
`_answer_offer` make, not string post-processing `head/output_exchange.py` used to do.

Both ports are RED for a measured, real reason - a confirmed regression, not a fixture
bug. Flagged for the coder/captain, not silently worked around.

* **Defect 2** (`TestOwner8SepANewAskIsNeverAnEscalationYes`, owner report 8 Sep 2026):
  "PO for SRTWC8517" over an open escalation offer, with the parser ALSO (wrongly)
  stamping `is_escalation_confirmation: true`, used to be DEFUSED by
  `output_exchange`'s own code-side check (a decisive intent plus a current entity
  outranks the model's own confirmation flag). Measured this session:
  `turn/apply.py::_answer_offer` reads `escalation.get("is_escalation_confirmation")
  is True` with NO defusing check anywhere in the function or its caller
  (`_answer_pending`) - grepped `is_escalation_confirmation` across the whole
  `app/services/chatbot/` tree, the only three hits outside `apply.py` are
  `trace.py` (display only), `lanes/escalation.py` (reads the already-decided flag)
  and `head/parser.py` (the JSON schema declaring it) - nothing between the parser
  and `_answer_offer` ever second-guesses it. A fresh business ask that happens to
  ride a hallucinated confirmation flag is swallowed by the escalation lane exactly
  as the owner reported.

* **Defect 3** (`TestOwner8SepADeliveryWordPlusANameIsAnOrderAsk` +
  `TestReviewRound2B2TheRetypeIsTheMeasuredArmOnly`, folded together - both exercise
  the SAME switch-word-widened-guard mechanism, the review class only narrowing its
  gating): "delivery to hanlim" (`message_type: request_for_help`, both `domain_hint`
  and `intent_hint` null, one customer entity) used to be RETYPED to a
  `business_query`/`order` ask when the message's own content carried a domain's
  switch word (`_switch_word_domain`, `contracts.DOMAIN_SWITCH_WORDS`) beside a
  CURRENT entity - the widened guard from review round 2. Measured this session:
  `turn/apply.py` has zero references to `switch_word` or `DOMAIN_SWITCH_WORDS`
  anywhere (grepped) - `_lane()` reads `message_type == "request_for_help"` and
  routes straight to the escalation lane whenever `domain_hint` is not in
  `_HELP_EXEMPT_DOMAINS` (`{"portal_link", "ideate"}` - `order` is not a member), with
  no widened-guard exception at all. Confirmed via direct `apply()`/`route()` calls,
  both with and without an open offer: neither ever reaches `business_query`.

Everything else in `test_growth_r1_review_fixes.py`'s six-class "Owner report" section
is RETIRED, not ported here - see that file's own replacement comment block (queue
item 2) for `TestD10AnIncomingAskTypesTheCodeAsAProduct` (duplicate of
`test_resolve_gate_unit.py`), `TestOwner8SepPOAskTypesTheCodeAsAProduct` (structurally
obsolete - the gate's `compatible_entities` is resolver-truth-typed, never the
parser's hint, so a mis-hinted entity no longer reaches the wrong tool), and
`TestSwitchWordDomainOfThisMessage` (direct unit test of a deleted function, its gap
covered by the defect-3 tests below instead).
"""
from __future__ import annotations

import pytest

from tests.chatbot._turn_helpers import build_policy, verdict


def _decide(v: dict, *, pending=None) -> tuple[str, str | None]:
    """`(branch_kind, trace.lane)` off the real `apply()` + `route()` seam - no stock-
    denial short-circuit needed here (neither defect touches it), unlike
    `test_rearch_port_route_unit.py::_decide`, which also has to seed
    `respond_contacts` for that unrelated concern."""
    from app.services.chatbot.turn.apply import apply
    from app.services.chatbot.turn.route import route
    from app.services.chatbot.turn.state import Focus, Profile, State

    state = State(focus=Focus(), pending=pending, profile=Profile())
    _state2, plan = apply(state, v, build_policy())
    return route(plan), plan.trace.lane


def _team_pick_offer(team: str = "warehouse"):
    from app.services.chatbot.turn.pending import ask

    return ask("team_pick", options=[], team=team, payload={})


def _member_offer(team: str = "customer_service", domain: str = "order"):
    from app.services.chatbot.turn.pending import ask

    return ask("member_offer", options=[], team=team, payload={"domain": domain})


class TestOwner8SepANewAskIsNeverAnEscalationYes:
    """Defect 2. After a stock answer offering to escalate, "PO for SRTWC8517" came
    back `request_for_help` with `is_escalation_confirmation: true`, so a fresh
    product question confirmed an offer the customer had ignored."""

    def test_a_business_ask_over_an_open_offer_is_not_a_confirmation(self) -> None:
        v = verdict(
            message_type="request_for_help",
            intent_hint="check_order",
            domain_hint="order",
            entities=[{"raw": "SRTWC8517", "hint": "product", "confident": True, "current_message": True}],
            escalation={"is_escalation_confirmation": True, "escalation_declined": None, "company_pick": None},
        )
        branch, lane = _decide(v, pending=_team_pick_offer())
        assert branch == "business_query", (
            "a decisive intent plus a current entity must defuse a hallucinated "
            f"is_escalation_confirmation flag; got branch={branch!r} lane={lane!r}. "
            "turn/apply.py::_answer_offer has no defusing check at all (grepped this "
            "session) - owner report 8 Sep 2026's fix has no equivalent in the rearch."
        )

    def test_a_bare_yes_is_still_a_confirmation(self) -> None:
        """The half that must NOT move: an acceptance names no entity, which is what
        lets the flag carry it. Stays green - the defusing rule above must not break
        this."""
        v = verdict(
            message_type="request_for_help",
            entities=[],
            is_affirmative=True,
            escalation={"is_escalation_confirmation": True, "escalation_declined": None, "company_pick": None},
        )
        branch, lane = _decide(v, pending=_team_pick_offer())
        assert lane == "escalation" and branch == "out_of_scope"

    def test_a_carried_entity_alone_does_not_defuse_the_confirmation(self) -> None:
        """Both halves are required: a confirmation turn often still carries the
        previous product, and that carried (not current) entity must not read as a
        new ask."""
        v = verdict(
            message_type="request_for_help",
            intent_hint="check_stock",
            entities=[{"raw": "srtwc286", "hint": "product", "current_message": False}],
            is_affirmative=True,
            escalation={"is_escalation_confirmation": True, "escalation_declined": None, "company_pick": None},
        )
        branch, lane = _decide(v, pending=_team_pick_offer())
        assert lane == "escalation" and branch == "out_of_scope"

    def test_a_bare_no_still_declines(self) -> None:
        v = verdict(
            message_type="clarification",
            is_affirmative=False,
            entities=[],
            escalation={"is_escalation_confirmation": False, "escalation_declined": True, "company_pick": None},
        )
        branch, lane = _decide(v, pending=_team_pick_offer())
        assert branch == "escalation_declined" and lane == "escalation_declined"


class TestOwner8SepADeliveryWordPlusANameIsAnOrderAsk:
    """Defect 3 (owner turns 2d903c96 / 17d38019 / 3a56a48c), folded with review round
    2's `TestReviewRound2B2TheRetypeIsTheMeasuredArmOnly` - the SAME switch-word
    mechanism, that class only narrowing its gating (the retype fires on the measured
    "switch word beside a current entity" arm alone, not on a decisive intent that
    already names a person)."""

    def _hanlim(self, **over):
        return verdict(
            message_type="request_for_help",
            intent_hint=None,
            domain_hint=None,
            entities=[{"raw": "hanlim", "hint": "customer", "confident": True, "current_message": True}],
            **over,
        )

    def test_the_2d903c96_shape_is_an_order_ask_not_a_help_request(self) -> None:
        """The core reproduction, cold turn: a switch word ("delivery") beside a
        current entity ("hanlim") with no decisive intent of its own must be read as
        an order ask, not a help request."""
        branch, lane = _decide(self._hanlim())
        assert branch == "business_query", (
            "'delivery to hanlim' with no decisive intent must retype to a business "
            f"order ask; got branch={branch!r} lane={lane!r}. turn/apply.py has zero "
            "switch_word/DOMAIN_SWITCH_WORDS references anywhere (grepped this "
            "session) - review round 2's widened guard has no equivalent in the "
            "rearch, so _lane() falls straight to its request_for_help->escalation "
            "rule instead."
        )

    def test_the_same_shape_over_an_open_offer_still_asks_which_team(self) -> None:
        """The SAME reproduction, but over an open escalation offer: the fix is not
        gated on an open offer either - a help request that names a customer beside a
        delivery word is an order ask whether or not one is already pending."""
        branch, lane = _decide(self._hanlim(), pending=_member_offer())
        assert branch == "business_query", (
            f"got branch={branch!r} lane={lane!r} - the same missing switch-word "
            "guard re-asks 'which team' instead of answering the order question."
        )

    def test_a_help_request_about_my_order_with_no_entity_is_unchanged(self) -> None:
        """The negative that keeps the guard narrow: a switch word ALONE, with no
        entity named this turn, is not an ask - "can someone help me with my order"
        stays a help request, and this one must stay green."""
        v = verdict(message_type="request_for_help", intent_hint=None, domain_hint=None, entities=[])
        branch, lane = _decide(v)
        assert lane == "escalation" and branch == "out_of_scope"

    def test_a_carried_entity_alone_is_not_a_current_one(self) -> None:
        """The negative that keeps the guard narrow: only a CURRENT entity counts - a
        carried one from an earlier turn must not retype a bare "someone handle the
        delivery". Must stay green."""
        v = verdict(
            message_type="request_for_help",
            intent_hint=None,
            domain_hint=None,
            entities=[{"raw": "hanlim", "hint": "customer", "current_message": False}],
        )
        branch, lane = _decide(v)
        assert lane == "escalation" and branch == "out_of_scope"

    def test_a_decisive_intent_plus_a_name_with_no_switch_word_stays_a_help_request(self) -> None:
        """Review round 2's own narrowing: "I need someone to look into HANLIM" parses
        a DECISIVE intent (`check_order`) plus a name, but the message's own words
        carry no switch word - the reviewer's ruling is that this shape is the
        parser's to classify, not the gate's, and it stays `request_for_help`. This
        negative holds regardless of the missing guard (it was never in the widened
        arm to begin with), so it stays green today."""
        v = verdict(
            message_type="request_for_help",
            intent_hint="check_order",
            domain_hint="order",
            entities=[{"raw": "HANLIM", "hint": "customer", "confident": True, "current_message": True}],
        )
        branch, lane = _decide(v)
        assert lane == "escalation" and branch == "out_of_scope"
