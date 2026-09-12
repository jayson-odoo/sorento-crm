"""The tail's contract tests: the rules replay cannot reach (AC-203, AC-204, AC-205, AC-302).

Node replay proves the port agrees with 1,300 captured executions. It cannot prove three
things, and each has its own class here:

* **AC-205 / H29** is a FIX, so no capture can show it - the only fixture that exercises
  the shape records the DEFECT (`b56-roster-turn`, a registered divergence). The rule has
  to be pinned by a written case or the divergence is an unfalsifiable excuse.
* **AC-204** is about ORDER. Eight dym-offer rules, first match wins; a capture exercises
  whichever rule its own turn hit, so only a written case can show that rule 1 beats rule
  5 on a turn where both apply.
* **AC-203** is about what must NEVER be written. `extra = "forbid"` cannot be proven by a
  fixture that happens not to carry a stray key.

Plus the two `escalate-catalog` arms with no vendored capture (`demand_qty` is dead by
vocabulary, `access_choice` was dropped to keep the vendored subset under 3 MB), because
an arm nobody grades is an arm that can be reworded by accident.
"""
from __future__ import annotations

from app.services.chatbot import copy as copy_mod
from app.services.chatbot.tail.compile_state import compile_current_state
from app.services.chatbot.tail.member_offer import build_cs_member_offer, cs_roster_plan
from app.services.chatbot.tail.outcome import build_outcome, cs_offer_gate, escalate_catalog


def _ctx(**qf_overrides):
    qf = {
        "message_type": "business_query",
        "intent_hint": "check_order",
        "domain_hint": "order",
        "user_goal": "checking an order",
        "entities": [],
        "routing": {"suggested_team": "customer_service", "suggested_agent": "order_enquiries"},
        "escalation": {"is_escalation_confirmation": False},
        "requested_attributes": [],
    }
    qf.update(qf_overrides)
    return {
        "contact": {"id": "ZZT-unit"},
        "text": {"message": {"message": {"text": "hello"}}},
        "session": {"session_vars": {"variables": {}}},
        "parse": {"output": qf, "_parser_raw": {"entities": []}},
        "access": {"allowed": True},
        "media": None,
    }


def _compile(item, ctx, **kwargs):
    return compile_current_state(item, ctx, **kwargs).item["reply"]["session_patch"]



# TestSessionVarsIsAWall, TestDymOfferLifecycle, TestTierMenuDomainCarry,
# TestBornRosterWins, TestTierAndPromoOffersCarryUntilOverwritten,
# TestTheMemberOfferCarryStopsAtTheAnswer and TestTheMemberOfferHasTheSameTtlAsTheDymOffer
# retired here (AC-1033 / D9, owner 12 Sep 2026: no persisted mirrors, no counter, no
# TTL, anywhere). Each pinned a piece of compile_current_state's did-you-mean /
# member-offer TTL ladder against the 36-key SessionVars wall (SESSION_VAR_KEYS) -
# both retired with the ladder itself in the coder's next slice. Ported coverage:
# tests/chatbot/test_session_shape.py (the five-key wall),
# tests/chatbot/test_open_question_shape.py and test_open_question.py's kept classes
# (the six handlers, including member_offer, follow the SAME clearing rule now).

# --------------------------------------------------------------------------- #
# AC-302: the canned copy, including the two arms with no vendored capture
# --------------------------------------------------------------------------- #


class TestCannedCopy:
    def test_every_registered_key_has_a_registry_spec_and_todays_text(self) -> None:
        from app.services.ai_prompt_registry import PROMPT_KEYS

        for short_name, key in copy_mod.REPLY_KEYS.items():
            assert key in PROMPT_KEYS, f"{key} is not registered in the prompt registry"
            assert PROMPT_KEYS[key].fallback() == copy_mod.FALLBACKS[short_name]

    def test_the_demand_qty_arm_renders_todays_sentence(self) -> None:
        """Dead by vocabulary (H1), so no capture can grade it - and R1 turns it on."""
        out = escalate_catalog({"branch_kind": "demand_qty"}, _ctx(), copy_mod.fallback_copy())
        assert out["response"] == "Please specify your demand quantity"
        assert out["manualResponse"] is True and out["is_escalate_offer"] is False

    def test_the_access_choice_arm_reads_the_upstream_message(self) -> None:
        out = escalate_catalog(
            {"branch_kind": "access_choice"},
            _ctx(),
            copy_mod.fallback_copy(),
            access_choice={"escalate_message": "Which access level?"},
        )
        assert out["response"] == "Which access level?"
        assert out["manualResponse"] is True

    def test_the_clarify_menu_interpolates_the_parser_goal(self) -> None:
        out = escalate_catalog(
            {"branch_kind": "clarify_menu"}, _ctx(user_goal="asking about stock"), copy_mod.fallback_copy()
        )
        assert out["response"].startswith("I see you're asking about stock, Let me understand more.")

    def test_the_escalate_offer_keeps_the_frozen_prefix_with_and_without_a_team(self) -> None:
        """`output_exchange.offer_is_open` matches this prefix. Reword it and ladder rank
        2 dies silently on every accepted offer."""
        with_team = escalate_catalog({"branch_kind": "escalate_offer"}, _ctx(), copy_mod.fallback_copy())
        assert "Would you like me to escalate to customer service team?" in with_team["response"]
        no_team = escalate_catalog(
            {"branch_kind": "escalate_offer"},
            _ctx(routing={"suggested_team": None, "suggested_agent": "order_enquiries"}),
            copy_mod.fallback_copy(),
        )
        assert "Would you like me to escalate this to our team?" in no_team["response"]
        assert with_team["is_escalate_offer"] is True and no_team["is_escalate_offer"] is True

    def test_the_resolved_company_team_beats_the_parsers_guess(self) -> None:
        """Issue #9. The gate saw the real entity; the parser guessed from access levels."""
        out = escalate_catalog(
            {"branch_kind": "escalate_offer"},
            _ctx(),
            copy_mod.fallback_copy(),
            gate={"company_team": "purchasing_certification"},
        )
        assert "escalate to purchasing certification team?" in out["response"]

    def test_an_unrecognised_branch_kind_falls_through_the_switch(self) -> None:
        """`access_denied` is a route-turn arm with no catalog case, and reproducing the
        fall-through is what keeps S3 free to give it real copy."""
        out = escalate_catalog({"branch_kind": "access_denied"}, _ctx(), copy_mod.fallback_copy())
        assert out["response"] == ""
        assert out["manualResponse"] is False
        assert out["includeResponse"] is True
        assert out["is_escalate_offer"] is False

    def test_a_published_edit_reaches_the_reply(self) -> None:
        """Journey B: the owner edits the not-supported reply and the next turn uses it."""
        edited = copy_mod.CannedCopy(templates={**copy_mod.FALLBACKS, "not_supported": "New words."})
        out = escalate_catalog({"branch_kind": "not_supported"}, _ctx(), edited)
        assert out["response"] == "New words."



# TestPendingMarker retired here (AC-1033, owner 12 Sep 2026: no persisted mirrors).
# pending (R3's escalation-offer marker) is one of the five keys SessionVars no longer
# declares; the equivalent behaviour - the engine reading and writing an open
# escalation offer - is dialogue/open_question.py's team_pick kind, tested in
# tests/chatbot/test_open_question.py and test_open_question_clearing.py.

# --------------------------------------------------------------------------- #
# The outcome hub and the CS member offer
# --------------------------------------------------------------------------- #


class TestOutcomeHub:
    def test_an_absent_producer_is_null_and_a_fragment_key_is_taken_verbatim(self) -> None:
        items = build_outcome(
            [{"json": {"branch_kind": "x", "outcome_fragment": {"central-exchange": {"response": "from the sub"}}}}],
            {"escalate-catalog": {"response": "from the graph"}},
        )
        outcome = items[0]["json"]["outcome"]
        assert outcome["central-exchange"] == {"response": "from the sub"}
        assert outcome["escalate-catalog"] == {"response": "from the graph"}
        assert outcome["promo-picker"] is None

    def test_the_fragment_key_never_rides_into_the_persisted_item(self) -> None:
        """It was never part of this item's shape, and ccs's own fallback reads the item
        wholesale - a stray key here is a key in a real customer's session."""
        items = build_outcome([{"json": {"a": 1, "outcome_fragment": {"validator": {}}}}], {})
        assert "outcome_fragment" not in items[0]["json"]
        assert items[0]["json"]["a"] == 1


class TestCsMemberOffer:
    ROSTER = [
        {"user_id": "u1", "name": "Ms Bay", "respond_user_id": "r1"},
        {"user_id": "u2", "name": "Nurain", "respond_user_id": "r2"},
        {"user_id": "u3", "name": "No Respond Id"},
    ]

    def test_the_gate_needs_all_four_conditions(self) -> None:
        catalog = {"is_escalate_offer": True}
        assert cs_offer_gate(catalog, _ctx(), None) is True
        assert cs_offer_gate({"is_escalate_offer": False}, _ctx(), None) is False
        assert cs_offer_gate(catalog, _ctx(routing={"suggested_team": "warehouse", "suggested_agent": "order_enquiries"}), None) is False
        assert cs_offer_gate(catalog, _ctx(), {"require_specific": True}) is False, (
            "a turn that already raised a picker must not raise a second one"
        )

    def test_a_member_without_a_respond_user_id_is_excluded(self) -> None:
        """respond.io assign cannot reach them, so offering them assigns nobody."""
        plan = cs_roster_plan(None)
        offer = build_cs_member_offer({"response": "Would you like me to escalate to customer service team?"}, plan, [{"body": self.ROSTER}])
        assert [row["label"] for row in offer["cs_last_result_set"]] == ["Ms Bay", "Nurain"]
        assert "No Respond Id" not in offer["response"]

    def test_an_empty_roster_falls_back_to_the_generic_offer(self) -> None:
        offer = build_cs_member_offer({"response": "generic"}, cs_roster_plan(None), [{"body": []}])
        assert offer["member_offer"] is False
        assert offer["selection_context"] is None
        assert offer["response"] == "generic"

    def test_a_failed_roster_read_degrades_to_an_empty_company_not_a_failed_turn(self) -> None:
        gate = {
            "routing_companies": [
                {"company_id": "c1", "company_name": "Sorento", "brand_code": "sorento", "codes": []},
                {"company_id": "c2", "company_name": "Mocha", "brand_code": "mocha", "codes": []},
            ]
        }
        plan = cs_roster_plan(gate)
        offer = build_cs_member_offer(
            {"response": "Would you like me to escalate to customer service team?"},
            plan,
            [{"body": self.ROSTER}, {"error": "500"}],
        )
        assert offer["member_offer"] is True
        assert "Mocha: no customer-service members are configured - omitted." in offer["response"]

    def test_a_single_company_offer_names_the_company_inside_the_frozen_phrase(self) -> None:
        gate = {"routing_companies": [{"company_id": "c1", "company_name": "Sorento", "brand_code": "sorento", "codes": []}]}
        offer = build_cs_member_offer(
            {"response": "Would you like me to escalate to customer service team?"},
            cs_roster_plan(gate),
            [{"body": self.ROSTER}],
        )
        assert "Would you like me to escalate to *Sorento* customer service team?" in offer["response"]
        assert offer["cs_offer_company"] == "Sorento"

    def test_a_shared_member_keeps_one_number_and_appears_under_each_company(self) -> None:
        gate = {
            "routing_companies": [
                {"company_id": "c1", "company_name": "Sorento", "brand_code": None, "codes": []},
                {"company_id": "c2", "company_name": "Mocha", "brand_code": None, "codes": []},
            ]
        }
        shared = [{"user_id": "u1", "name": "Ms Bay", "respond_user_id": "r1"}]
        offer = build_cs_member_offer({"response": "x"}, cs_roster_plan(gate), [{"body": shared}, {"body": shared}])
        assert offer["response"].count("1. Ms Bay") == 2, "listed under each company"
        assert len(offer["cs_last_result_set"]) == 1, "one number, so a reply of 1 is unambiguous"
        assert offer["cs_last_result_set"][0]["companies"] == ["Sorento", "Mocha"]


# --------------------------------------------------------------------------- #
# R3 / D11: `answered_domain` replaces `crossdomain-compose`'s regex, and the
# substitution is graded against the whole corpus rather than asserted.
# --------------------------------------------------------------------------- #


class TestAnsweredDomainEquivalence:
    """The port swapped a REGEX for a VALUE, and node replay cannot see the swap.

    `crossdomain-compose.js` decides between its PARTIAL and its TOTAL-MISS branch with
    `/^Previous turn \\(/` over the state it has just written. The port takes
    `CompiledState.answered_domain` instead (D11: no reading a reply back), and
    `test_replay.py`'s compose runner DERIVES `answered` with that same regex off the
    fixture - which is correct for grading compose, and means the substitution itself is
    never compared to anything.

    So it is compared here, over every `compile-current-state` capture the corpus holds:
    the port's `answered_domain is not None` against the JS predicate applied to the
    variables the port persisted. A single disagreement is a turn where the cross-domain
    block would land in the wrong half of the reply.
    """

    def test_the_value_agrees_with_the_regex_on_every_capture(self) -> None:
        from tests.chatbot import _corpus
        from tests.chatbot.test_replay import _ctx_of, _execution_id, _ran

        fixtures = list(_corpus.vendored("compile-current-state")) + list(
            _corpus.full_corpus("compile-current-state")
        )
        assert fixtures, "no compile-current-state captures: this test would be vacuous"

        mismatches = []
        for fixture in fixtures:
            compiled = compile_current_state(
                (fixture.input[0] or {}).get("json") or {},
                _ctx_of(fixture),
                resolved=_ran(fixture, "resolve-entity"),
                gate=_ran(fixture, "disallowed-entity-gate"),
                execution_id=_execution_id(fixture),
            )
            response = (
                (compiled.item["reply"]["session_patch"].get("variables") or {}).get("response")
            )
            by_regex = isinstance(response, str) and response.startswith("Previous turn (")
            by_value = compiled.answered_domain is not None
            if by_regex != by_value:
                mismatches.append(
                    f"{fixture.name}: regex={by_regex} value={by_value} "
                    f"domain={compiled.answered_domain!r} response={str(response)[:60]!r}"
                )
        assert not mismatches, (
            f"{len(mismatches)} of {len(fixtures)} captures disagree - the cross-domain "
            "block would land in the wrong half of the reply on each:\n"
            + "\n".join(mismatches[:10])
        )


# --------------------------------------------------------------------------- #
# The filter header on a PICK-RESOLVED order list (prod turn 1c175a0a, 6 Sep 2026).
# --------------------------------------------------------------------------- #


class TestThePickResolvedOrderListStatesItsScope:
    """"customer a craft delivery order" -> "1" answered with no header at all.

    The reply opened straight at `1. *Company:* Sorento *Order Number:* REP202608-0514`,
    while the DIRECT form of the same question stamps
    `Customer: ... / Product: ... / Order: ... / Dates: ...` above the list. The customer
    is then reading a scoped answer with nothing saying what it was scoped to - the exact
    ambiguity `_search_scope_header` exists to remove ("1 order" reads equally as "1 order
    ever" and "1 order this month").

    The composer is not missing and is not duplicated: it is
    `compile_state._search_scope_header`, and the pick turn falls out of it on ONE guard.
    A positional pick names a ROW, so the parser emits `domain_hint: null` (AC-816 rule 4
    says so explicitly, which is why the bare-entity inheritance excludes a pick), and the
    guard tests THIS turn's domain against `_DATE_SCOPE_DOMAINS`. The old spine never hit
    it because its own parser body inherited the domain onto the pick turn - capture
    `compile-current-state/b56-pick-turn`, whose expected reply opens
    `Customer: CHIN CHUN HARDWARE SDN BHD\nProduct: srtwc286\nDates: all dates\n\nHere
    are the orders I found.`, is the same turn shape with `domain_hint: order` on it.

    The fix is at the arm: a turn that names NO domain is a continuation of the carried
    one, which is `topic.changed`'s own rule and the same one the offer carry uses.
    """

    ROSTER = [
        {"idx": 1, "label": "A CRAFT IDEA SDN BHD [A/C I]", "uuid": "cust-1", "entity_type": "customer"},
        {"idx": 2, "label": "A CRAFT IDEA SDN BHD (SRT)", "uuid": "cust-2", "entity_type": "customer"},
    ]

    ORDER_ROWS = [
        {
            "title": "REP202608-0514",
            "fields": [
                {"key": "company_name", "label": "Company", "value": "Sorento"},
                {"key": "order_number", "label": "Order Number", "value": "REP202608-0514"},
                {"key": "customer", "label": "Customer", "value": "A CRAFT IDEA SDN BHD [A/C I]"},
            ],
        }
    ]

    GATE = {
        "gate_passed": True,
        "gate_reason": "ok",
        "compatible_entities": [
            {
                "uuid": "cust-1",
                "entity_type": "customer",
                "code": "300-A011",
                "display_name": "A CRAFT IDEA SDN BHD [A/C I]",
            }
        ],
    }

    RESOLVED = {
        "resolutions": [
            {
                # The PICKER RESOLUTION rewrites the entity to the row the customer
                # picked, so this is the token the resolver saw - exactly the shape
                # `compile-current-state/b56-pick-turn` carries (`customer` /
                # `CHIN CHUN HARDWARE SDN BHD` / `ordinal: 1`). The ONE difference from
                # that capture, and the whole defect, is `domain_hint`.
                "token": "A CRAFT IDEA SDN BHD [A/C I]",
                "matches": [
                    {
                        "entity_type": "customer",
                        "canonical_code": "300-A011",
                        "uuid": "cust-1",
                        "match_field": "customer_name",
                        "display": {"customer_name": "A CRAFT IDEA SDN BHD [A/C I]"},
                    }
                ],
            }
        ]
    }

    def _pick_ctx(self):
        """The turn the customer sent: the bare digit "1", so NO domain and NO intent."""
        ctx = _ctx(
            message_type="business_query",
            intent_hint=None,
            domain_hint=None,
            entities=[
                {"hint": "customer", "raw": "A CRAFT IDEA SDN BHD [A/C I]", "ordinal": 1}
            ],
            reference_positions=[1],
            positions_resolved=1,
        )
        ctx["text"] = {"message": {"message": {"text": "1"}}}
        ctx["session"] = {
            "session_vars": {
                "variables": {
                    "domain_hint": "order",
                    "selection_context": "disambiguation",
                    "last_result_set": self.ROSTER,
                }
            }
        }
        return ctx

    def _answered(self):
        return {
            "outcome": {
                "central-exchange": {
                    "response": (
                        "1. *Company:* Sorento\n*Order Number:* REP202608-0514\n"
                        "*Customer:* A CRAFT IDEA SDN BHD [A/C I]"
                    ),
                    "items": self.ORDER_ROWS,
                }
            }
        }

    def _reply(self):
        return compile_current_state(
            self._answered(), self._pick_ctx(), resolved=self.RESOLVED, gate=self.GATE
        ).item["reply"]["text"]

    def test_the_header_is_stamped_above_the_list(self) -> None:
        text = self._reply()
        first = text.split("\n")[0]
        assert first.startswith("Customer: "), (
            "a pick-resolved order list must state its scope like the direct path does, "
            f"and this reply opens at {first!r}"
        )
        assert "\nDates: all dates\n" in text, (
            f"the date line is what makes '1 order' unambiguous: {text!r}"
        )
        assert text.index("Customer: ") < text.index("1. *Company:*"), (
            "the header goes ABOVE the list, not after it"
        )

    def test_the_header_names_the_customer_the_pick_resolved(self) -> None:
        text = self._reply()
        assert "A CRAFT IDEA SDN BHD" in text.split("Here")[0].split("1. *Company:*")[0], (
            f"the header must name the customer the pick resolved to: {text!r}"
        )
        assert "300-A011" not in text, (
            f"an internal debtor code must never reach the header: {text!r}"
        )


# --------------------------------------------------------------------------- #
# AC-816 rule 1: an offer that is carried carries its SUBJECT (prod exec 15445325).
# --------------------------------------------------------------------------- #


class TestACarriedOfferKeepsTheSubjectItWasMadeAbout:
    """"promotion 7445" -> a three-tier picker -> "9" -> "all" answered nothing.

    The out-of-range "9" re-prompted correctly and rule 1 kept the tier list, but the
    session patch it wrote had `entities: []` and `domain_hint: null` - the model reads a
    bare digit as `casual` with no positions extracted (exec 15445325), and the variables
    object is built FROM SCRATCH from this turn's parse. So the next reply, a perfectly
    valid "all", arrived with no product in scope and fell to the generic "I need at least
    one filter" instead of every tier's promotions for 7445 (exec 15445363).

    An offer whose subject is gone is an offer nobody can answer, so the carry takes the
    subject with it: when the ladder produced no domain and no entities of its own, the
    carried ones stand. Narrow by construction - this only runs on the turns
    `_offer_carry` already carries (the ladder was silent AND the topic did not change),
    and a turn that names its own domain or entities keeps them.
    """

    TIERS = [
        {"idx": 1, "label": "Dealer", "value": "Dealer"},
        {"idx": 2, "label": "End User", "value": "End User"},
        {"idx": 3, "label": "Contractor", "value": "Contractor"},
    ]
    ENTITY = {
        "raw": "7445",
        "hint": "product",
        "canonical_code": "SRTWC7445",
        "current_message": False,
        "confident": True,
    }

    def _out_of_range_ctx(self):
        """The "9" turn as the model really emits it: casual, no positions, no entities."""
        ctx = _ctx(
            message_type="casual",
            intent_hint=None,
            domain_hint=None,
            entities=[],
        )
        ctx["text"] = {"message": {"message": {"text": "9"}}}
        ctx["session"] = {
            "session_vars": {
                "variables": {
                    "message_type": "business_query",
                    "domain_hint": "promotion",
                    "intent_hint": "check_promotion",
                    "selection_context": "tier_offer",
                    "last_result_set": self.TIERS,
                    "entities": [self.ENTITY],
                    "response": "Which access level?",
                }
            }
        }
        return ctx

    def test_the_tier_list_survives_an_out_of_range_digit(self) -> None:
        variables = _compile({"outcome": {}}, self._out_of_range_ctx())["variables"]
        assert variables["selection_context"] == "tier_offer"
        assert variables["last_result_set"] == self.TIERS

    def test_the_product_and_the_domain_survive_with_it(self) -> None:
        variables = _compile({"outcome": {}}, self._out_of_range_ctx())["variables"]
        assert variables["domain_hint"] == "promotion", (
            "the next reply resolves against the offer's own domain, and the re-prompt "
            f"turn named none: {variables!r}"
        )
        raws = [str(e.get("raw")) for e in (variables.get("entities") or [])]
        assert raws == ["7445"], (
            "the product the offer was made about must ride with it, or the next 'all' "
            f"has nothing to be all OF: {variables!r}"
        )
        assert all(
            e.get("current_message") is False for e in (variables.get("entities") or [])
        ), "a carried entity is not one the customer typed this turn"

    def test_a_turn_that_names_its_own_subject_keeps_it(self) -> None:
        """The guard: the carry FILLS a gap, it never overwrites."""
        ctx = self._out_of_range_ctx()
        ctx["parse"]["output"]["domain_hint"] = "promotion"
        ctx["parse"]["output"]["entities"] = [
            {"raw": "8899", "hint": "product", "current_message": True, "confident": True}
        ]
        variables = _compile({"outcome": {}}, ctx)["variables"]
        assert [str(e.get("raw")) for e in variables["entities"]] == ["8899"]
