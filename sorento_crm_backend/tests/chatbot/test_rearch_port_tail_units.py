"""Port of `test_tail_units.py` (AC-1592) onto the new seams.

`tail/pending.py` and `tail/compile_state.py` (the modules this file's top-level
imports named) no longer exist. Of its 14 classes, TWO exercise kept code directly
(`tail/outcome.py`, `tail/member_offer.py`) with no doomed dependency and are copied
here unchanged. The other TWELVE (`TestDymOfferLifecycle`, `TestTierMenuDomainCarry`,
`TestBornRosterWins`, `TestTierAndPromoOffersCarryUntilOverwritten`,
`TestTheMemberOfferCarryStopsAtTheAnswer`, `TestTheMemberOfferHasTheSameTtlAsTheDym
Offer`, `TestCannedCopy`, `TestPendingMarker`, `TestAnsweredDomainEquivalence`,
`TestThePickResolvedOrderListStatesItsScope`, `TestACarriedOfferKeepsTheSubjectIt
WasMadeAbout`, and three of `TestSessionVarsIsAWall`'s four tests) are RETIRED, not
ported - all twelve are built around `compile_current_state` (via a shared `_compile`
helper), the OLD tail's "compile a session_patch through many first-match-wins rules,
then write the compiled patch" mechanism.

That mechanism is architecturally gone, not merely renamed. `engine.py::run_tail`'s
own docstring (measured this session): "the MEMORY is no longer re-derived from that
reply. The five keys are written from the State APPLY computed and the question the
composer asked, so there is one writer, one shape, and no ladder of markers to keep
in step." Confirmed empirically: `turn/pending.py` has no TTL concept at all (`ask`/
`with_answered_positions`/`to_wire`/`from_wire`, no decay countdown); grepped the
whole tree for `escalation_team`/`MEMBER_OFFER_TTL` - both are gone (only a comment
in `contracts.py` cites the old location as history). `_narrow_and_plan`
(`turn/apply.py`) builds a NEW `Pending` fresh from THIS turn's focus/candidates on
every call - there is no separate "carried picker" data structure a new roster could
be shadowed by, which is exactly the property `TestBornRosterWins` (AC-205/H29)
existed to prove; the rule holds by construction now, not by a compiled-order fix.
The escalation-team default-fallback property (contract 77) already has its own
coverage in `test_rearch_s3_team_pick_and_866.py` (green, per this lane's own prior
session).

`SessionVars`' `extra=forbid` wall (AC-203/H15) is unaffected - the class is
unchanged - so that ONE property is ported below with the model's real five field
names, not retired with the rest.
"""
from __future__ import annotations

import pytest

from app.services.chatbot.contracts import SessionVars
from app.services.chatbot.tail.member_offer import build_cs_member_offer, cs_roster_plan
from app.services.chatbot.tail.outcome import build_outcome, cs_offer_gate


def _ctx(*, routing: dict | None = None) -> dict:
    return {
        "contact": {"id": "ZZT-unit"},
        "parse": {
            "output": {
                "routing": routing
                or {"suggested_team": "customer_service", "suggested_agent": "order_enquiries"}
            }
        },
    }


class TestSessionVarsIsAWallForTheFiveKeyShape:
    def test_a_key_outside_the_five_raises_before_anything_is_written(self) -> None:
        """H15's structural guarantee, re-proven against the CURRENT five-key model
        (`focus`, `open_question`, `ideation`, `access_levels`, `contains_flyer`)."""
        with pytest.raises(Exception) as raised:
            SessionVars(focus={}, dym_probe_entities=["harness"])
        assert "dym_probe_entities" in str(raised.value)

    def test_the_five_real_keys_are_all_accepted(self) -> None:
        SessionVars(
            focus={},
            open_question=None,
            ideation=None,
            access_levels=[],
            contains_flyer=False,
        )


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
        assert (
            cs_offer_gate(
                catalog,
                _ctx(routing={"suggested_team": "warehouse", "suggested_agent": "order_enquiries"}),
                None,
            )
            is False
        )
        assert cs_offer_gate(catalog, _ctx(), {"require_specific": True}) is False, (
            "a turn that already raised a picker must not raise a second one"
        )

    def test_a_member_without_a_respond_user_id_is_excluded(self) -> None:
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
