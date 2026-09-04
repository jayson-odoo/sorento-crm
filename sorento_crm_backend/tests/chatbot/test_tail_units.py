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

import pytest

from app.services.chatbot import copy as copy_mod
from app.services.chatbot.contracts import SESSION_VAR_KEYS, SessionVars
from app.services.chatbot.tail import pending as pending_mod
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


# --------------------------------------------------------------------------- #
# AC-203 / H15: the allowlist is a wall, not a suggestion
# --------------------------------------------------------------------------- #


class TestSessionVarsIsAWall:
    def test_every_key_compile_state_writes_is_on_the_allowlist(self) -> None:
        """R2: nothing is dropped, so the model must accept everything ccs can write."""
        patch = _compile({"outcome": {}}, _ctx())
        for key in patch["variables"]:
            assert key in SESSION_VAR_KEYS, (
                f"compile-current-state writes `{key}` and `SessionVars` does not declare "
                "it, so the write would raise on a real turn"
            )

    def test_a_key_outside_the_allowlist_raises_before_anything_is_written(self) -> None:
        """H15: the JS built a fresh object literal per writer, so a harness key a writer
        happened to set survived into a real customer's session. This is the structural
        version of that guarantee, and it has to raise on CONSTRUCTION - after the write
        it is just a log line."""
        with pytest.raises(Exception) as raised:
            SessionVars(message_type="business_query", dym_probe_entities=["harness"])
        assert "dym_probe_entities" in str(raised.value)

    def test_the_pending_marker_is_typed_and_its_kind_is_closed(self) -> None:
        SessionVars(pending={"kind": "escalation_offer", "team": "customer_service"})
        with pytest.raises(Exception):
            SessionVars(pending={"kind": "not_a_kind"})

    def test_a_compiled_patch_passes_the_allowlist_on_every_lane(self) -> None:
        """The write path's own precondition, exercised on each reply arm."""
        for outcome in (
            {},
            {"escalate-catalog": {"response": "x", "manualResponse": True, "includeResponse": True}},
            {"central-exchange": {"response": "y", "items": []}},
            {"build-suggest-offer": {"suggest_offer": True, "suggest_response": "z"}},
        ):
            patch = _compile({"outcome": outcome}, _ctx())
            SessionVars(**patch["variables"])


# --------------------------------------------------------------------------- #
# AC-204: the did-you-mean lifecycle, eight rules, first match wins
# --------------------------------------------------------------------------- #


def _offer(**over):
    base = {"id": "11", "domain": "inventory", "ttl": 3, "candidates": [{"code": "A"}], "picked": []}
    base.update(over)
    return base


def _ctx_with_offer(offer, **qf_overrides):
    qf_overrides.setdefault("domain_hint", "inventory")
    ctx = _ctx(**qf_overrides)
    ctx["session"] = {"session_vars": {"variables": {"dym_offer": offer}}}
    return ctx


class TestDymOfferLifecycle:
    """The eight rules IN ORDER. Each case makes a LATER rule true as well, so a test
    that passed by luck of ordering would go red the moment the ladder is reshuffled."""

    def test_rule_1_a_fresh_offer_replaces_even_when_the_turn_answered(self) -> None:
        """Rule 1 beats rule 5: the partial-miss offer must survive an answered turn, or
        the customer is shown suggestions the next turn cannot resolve."""
        fresh = _offer(id="new", candidates=[{"code": "B"}], ttl=1, picked=["old"])
        outcome = {"build-suggest-offer": {"suggest_offer": True, "suggest_response": "s", "dym_offer": fresh}}
        patch = _compile({"outcome": outcome}, _ctx_with_offer(_offer()))
        assert patch["variables"]["dym_offer"]["id"] == "new"
        assert patch["variables"]["dym_offer"]["ttl"] == 3
        assert patch["variables"]["dym_offer"]["picked"] == []

    def test_rule_2_a_domain_switch_kills_the_offer(self) -> None:
        patch = _compile({"outcome": {}}, _ctx_with_offer(_offer(domain="inventory"), domain_hint="order"))
        assert patch["variables"]["dym_offer"] is None

    def test_rule_2_a_null_domain_never_kills_it(self) -> None:
        """A bare-code pick emits no domain, and killing on that loses the offer the pick
        was about to resolve against."""
        patch = _compile({"outcome": {}}, _ctx_with_offer(_offer(), domain_hint=None))
        assert patch["variables"]["dym_offer"] is not None

    def test_rule_3_a_committed_escalation_kills_it_before_a_pick_could_retain_it(self) -> None:
        ctx = _ctx_with_offer(
            _offer(),
            escalation={"is_escalation_confirmation": True},
            dym_pick_applied=True,
        )
        patch = _compile({"outcome": {}}, ctx)
        assert patch["variables"]["dym_offer"] is None, "rule 3 must outrank rule 4"

    def test_rule_4_an_applied_pick_retains_the_offer_and_records_the_code(self) -> None:
        ctx = _ctx_with_offer(_offer(ttl=1), dym_pick_applied=True, dym_offer_pick_code="A")
        patch = _compile({"outcome": {}}, ctx)
        offer = patch["variables"]["dym_offer"]
        assert offer["ttl"] == 3 and offer["picked"] == ["A"]

    def test_rule_5_an_answered_turn_with_no_pick_kills_it(self) -> None:
        outcome = {"central-exchange": {"response": "rows", "items": [{"title": "row"}]}}
        patch = _compile({"outcome": outcome}, _ctx_with_offer(_offer(), domain_hint="inventory"))
        assert patch["variables"]["last_result_set"], "the fixture must actually answer"
        assert patch["variables"]["dym_offer"] is None

    def test_rule_6_an_exhausted_ttl_kills_it(self) -> None:
        patch = _compile({"outcome": {}}, _ctx_with_offer(_offer(ttl=1)))
        assert patch["variables"]["dym_offer"] is None

    def test_rule_7_otherwise_it_is_retained_with_the_ttl_decremented(self) -> None:
        patch = _compile({"outcome": {}}, _ctx_with_offer(_offer(ttl=3)))
        assert patch["variables"]["dym_offer"]["ttl"] == 2

    def test_dym_candidates_mirrors_the_offer_and_empties_with_it(self) -> None:
        patch = _compile({"outcome": {}}, _ctx_with_offer(_offer(ttl=3)))
        assert patch["variables"]["dym_candidates"] == [{"code": "A"}]
        cleared = _compile({"outcome": {}}, _ctx_with_offer(_offer(ttl=1)))
        assert cleared["variables"]["dym_candidates"] == []

    def test_rule_null_nothing_to_carry_stays_none(self) -> None:
        """AC-204's 8th named rule ("null"): no fresh offer AND no prior offer at all -
        the `elif not prev_offer` branch, distinct from rule 2 (a domain switch KILLING
        a LIVE offer) and from rule 6 (a TTL death, which also needs a prior offer)."""
        patch = _compile({"outcome": {}}, _ctx())
        assert patch["variables"]["dym_offer"] is None


# --------------------------------------------------------------------------- #
# RS-9 Fix 6: `tier_menu` persistence, keyed on the domain the customer named.
#
# Found by the tester's kill-test pass (S2): flipping `tm_domain_ok` in
# `compile_state.py` to a hardcoded `True` OR `False` leaves the entire corpus -
# 1,300+ node-replay fixtures and all 103 worlds - green. Neither direction of the
# rule was pinned by anything, so these three cases are what makes a regression here
# fail loudly instead of shipping silently.
# --------------------------------------------------------------------------- #


class TestTierMenuDomainCarry:
    PREV_MENU = [{"idx": 1, "label": "Tier A"}, {"idx": 2, "label": "Tier B"}]

    def _ctx_with_tier_menu(self, **qf_overrides):
        ctx = _ctx(**qf_overrides)
        ctx["session"] = {"session_vars": {"variables": {"tier_menu": self.PREV_MENU}}}
        return ctx

    def test_a_null_domain_carries_the_menu(self) -> None:
        """A bare digit reply names no domain, and the tier thread must still resolve."""
        patch = _compile({"outcome": {}}, self._ctx_with_tier_menu(domain_hint=None))
        assert patch["variables"]["tier_menu"] == self.PREV_MENU

    def test_the_promotion_domain_carries_the_menu(self) -> None:
        patch = _compile({"outcome": {}}, self._ctx_with_tier_menu(domain_hint="promotion"))
        assert patch["variables"]["tier_menu"] == self.PREV_MENU

    def test_an_explicit_different_domain_clears_the_menu(self) -> None:
        """The customer named a different domain outright - the tier thread is over,
        and the key must be ABSENT (never re-seated as an empty/null value)."""
        patch = _compile({"outcome": {}}, self._ctx_with_tier_menu(domain_hint="order"))
        assert "tier_menu" not in patch["variables"]


# --------------------------------------------------------------------------- #
# AC-205 / H29: a roster born THIS turn beats a carried picker
# --------------------------------------------------------------------------- #


class TestBornRosterWins:
    """The measured defect (clone execs 14400694 to 14400758): turn 3 rendered a
    nine-member CS roster and persisted the PREVIOUS turn's three-row customer picker with
    `selection_context: 'disambiguation'`, so turn 4's "1" resolved positionally against a
    list the customer could no longer see, re-ran the same order query, and the escalation
    was silently dropped. The picker is off the customer's screen, so it must be out of
    the session.
    """

    CARRIED = [{"idx": 1, "label": "CHIN CHUN HARDWARE", "uuid": "u1"}]
    ROSTER = [{"idx": 1, "label": "Ms Bay", "uuid": "u9", "respond_user_id": "r9"}]

    def _ctx_with_picker(self):
        ctx = _ctx()
        ctx["session"] = {
            "session_vars": {
                "variables": {
                    "picker_last_result_set": self.CARRIED,
                    "picker_selection_context": "disambiguation",
                    "picker_domain": "order",
                }
            }
        }
        return ctx

    def test_a_member_offer_born_this_turn_evicts_the_carried_picker(self) -> None:
        outcome = {
            "build-cs-member-offer": {
                "response": "choose",
                "manualResponse": True,
                "includeResponse": True,
                "selection_context": "member_offer",
                "cs_last_result_set": self.ROSTER,
            }
        }
        patch = _compile({"outcome": outcome}, self._ctx_with_picker())
        variables = patch["variables"]
        assert variables["selection_context"] == "member_offer"
        assert variables["last_result_set"] == self.ROSTER
        assert "picker_last_result_set" not in variables, (
            "the carried picker must not be re-seated under a roster the customer is not "
            "looking at (H29)"
        )

    def test_a_turn_that_builds_no_offer_still_carries_the_picker(self) -> None:
        """B56 is not a drop-on-consume: a PICK turn builds no offer of its own, so the
        "reply all" carry the block exists for is untouched."""
        patch = _compile({"outcome": {}}, self._ctx_with_picker())
        variables = patch["variables"]
        assert variables["picker_last_result_set"] == self.CARRIED
        assert variables["selection_context"] == "disambiguation"
        assert variables["last_result_set"] == self.CARRIED


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
        """`output_exchange._offer_is_open` matches this prefix. Reword it and ladder rank
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


# --------------------------------------------------------------------------- #
# R3: the pending marker
# --------------------------------------------------------------------------- #


class TestPendingMarker:
    def test_an_open_offer_records_the_marker_the_next_turn_reads(self) -> None:
        outcome = {
            "escalate-catalog": {
                "response": "Would you like me to escalate to customer service team?",
                "manualResponse": True,
                "includeResponse": True,
                "is_escalate_offer": True,
            }
        }
        patch = _compile({"outcome": outcome}, _ctx())
        assert patch["variables"]["pending"] == {
            "kind": "escalation_offer",
            "team": "customer_service",
            "domain": "order",
        }

    def test_the_marker_the_tail_writes_is_the_one_the_head_reads(self) -> None:
        """The two halves of R3 in one assertion: S2 writes it, S1's reader accepts it."""
        from app.services.chatbot.head.output_exchange import _offer_is_open

        outcome = {
            "escalate-catalog": {
                "response": "offer",
                "manualResponse": True,
                "includeResponse": True,
                "is_escalate_offer": True,
            }
        }
        variables = _compile({"outcome": outcome}, _ctx())["variables"]
        assert _offer_is_open(variables) is True

    def test_no_open_offer_writes_an_explicit_null(self) -> None:
        """Explicit, never left to key absence - the dym lifecycle's own lesson."""
        patch = _compile({"outcome": {}}, _ctx())
        assert patch["variables"]["pending"] is None

    def test_the_marker_names_the_same_team_the_copy_does(self) -> None:
        gate = {"company_team": "warehouse"}
        assert pending_mod.escalation_team(_ctx()["parse"]["output"], gate) == "warehouse"
        assert pending_mod.escalation_team(_ctx()["parse"]["output"], None) == "customer_service"


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
