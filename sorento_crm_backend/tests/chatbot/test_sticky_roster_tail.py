"""D19: sticky roster, persisted (owner 13 Sep 2026, PLAN-chatbot-focus-multi-domain S6).

A pick does NOT consume its roster. `tail/compile_state.py`'s
`elif jsc.truthy(jsc.get(qf, "open_question_answered")): variables["open_question"] = None`
branch is today's CONSUMPTION - it clears whatever question was open the moment ANY kind
answers, roster or not. This restores owner ruling K rule 1 (6 Sep 2026, AC-816) and the
7 Sep deviation 5, and supersedes the close-on-answer clause of AC-1014 that the 12 Sep UAC
introduced.

The rule, in full (PLAN-chatbot-focus-multi-domain.md, D19):

1. A ROSTER question (`product_pick`, `customer_pick`, `tier_pick`) stays open after a pick,
   options frozen, `asked_at_turn` unchanged.
2. It clears only by the existing rules (a newer question of another kind, `topic_reset`, a
   message naming its own subject, conversation-closed).
3. The one-team yes/no escalate offer that a pick's rerun produces RIDES on the roster
   question: `kind`/`options`/`asked_at_turn` stay the roster's, `expects` becomes
   `"pick_or_yes_no"`, `payload.offer` carries `{team, domain, options}`. A number re-picks
   (rule 1); `yes` runs escalation and consumes the WHOLE question (None); `no` declines and
   the roster stays with the offer stripped (`expects` back to `"pick"`, no `payload.offer`).
4. Non-roster kinds (`team_pick` clarify, `company_pick`, `member_offer`) keep today's
   behaviour: consumed when answered.

RED: `compile_current_state` has no roster-stickiness at all today - `qf.open_question_answered`
truthy with nothing newly asked always clears to `None`, for every kind.

Driven the way `tests/chatbot/test_tail_units.py` drives `compile_current_state`: its own
`_ctx` / `_compile` helpers, reused by name rather than duplicated.
"""
from __future__ import annotations

from app.services.chatbot.dialogue import open_question as oq
from app.services.chatbot.tail import compile_state as compile_state_mod
from tests.chatbot.test_tail_units import _compile, _ctx


def _rows(*labels: str) -> list[dict]:
    return [
        {"idx": i, "label": label, "code": label, "uuid": f"uuid-{label}", "entity_type": "product"}
        for i, label in enumerate(labels, start=1)
    ]


def _tier_rows() -> list[dict]:
    return [
        {"idx": 1, "tier": "office", "label": "Office"},
        {"idx": 2, "tier": "dealer", "label": "Dealer"},
    ]


def _customer_rows() -> list[dict]:
    return [
        {"idx": 1, "label": "ABC Trading", "code": "ABC", "entity_type": "customer"},
        {"idx": 2, "label": "XYZ Hardware", "code": "XYZ", "entity_type": "customer"},
    ]


def _team_rows() -> list[dict]:
    return [
        {"idx": 1, "team": "warehouse", "label": "warehouse"},
        {"idx": 2, "team": "purchasing", "label": "purchasing"},
    ]


class TestARosterStaysWhenAPickAnswersAndNothingNewIsAsked:
    """Rule 1: `product_pick`, `customer_pick`, `tier_pick` all survive a plain pick."""

    def test_product_pick_stays(self) -> None:
        roster = oq.ask("product_pick", options=_rows("A", "B", "C"), turn_no=3)
        ctx = _ctx(message_type="casual", open_question_answered="product_pick")
        ctx["parse"]["_open_question_before"] = roster

        result = _compile({"outcome": {}}, ctx)

        after = result["variables"]["open_question"]
        assert after is not None, "the roster must survive a pick that answered it (D19)"
        assert after["kind"] == "product_pick"
        assert after["expects"] == "pick"
        assert not (after.get("payload") or {}).get("offer")
        assert after["asked_at_turn"] == 3
        assert after["options"] == roster["options"]

    def test_tier_pick_stays(self) -> None:
        roster = oq.ask("tier_pick", options=_tier_rows(), turn_no=2)
        ctx = _ctx(message_type="casual", open_question_answered="tier_pick")
        ctx["parse"]["_open_question_before"] = roster

        result = _compile({"outcome": {}}, ctx)

        after = result["variables"]["open_question"]
        assert after is not None
        assert after["kind"] == "tier_pick"
        assert after["asked_at_turn"] == 2

    def test_customer_pick_stays(self) -> None:
        roster = oq.ask("customer_pick", options=_customer_rows(), turn_no=1)
        ctx = _ctx(message_type="casual", open_question_answered="customer_pick")
        ctx["parse"]["_open_question_before"] = roster

        result = _compile({"outcome": {}}, ctx)

        after = result["variables"]["open_question"]
        assert after is not None
        assert after["kind"] == "customer_pick"


class TestNonRosterKindsStillConsumeOnAnswer:
    """Rule 4: a team_pick CLARIFY (expects pick) and member_offer keep today's behaviour."""

    def test_team_pick_clarify_is_consumed(self) -> None:
        roster = oq.ask("team_pick", options=_team_rows(), turn_no=1)
        ctx = _ctx(message_type="casual", open_question_answered="team_pick")
        ctx["parse"]["_open_question_before"] = roster

        result = _compile({"outcome": {}}, ctx)

        assert result["variables"]["open_question"] is None

    def test_member_offer_is_consumed(self) -> None:
        roster = oq.ask(
            "member_offer",
            options=[{"idx": 1, "label": "Ms Tan", "uuid": "user-1"}],
            turn_no=1,
        )
        ctx = _ctx(message_type="casual", open_question_answered="member_offer")
        ctx["parse"]["_open_question_before"] = roster

        result = _compile({"outcome": {}}, ctx)

        assert result["variables"]["open_question"] is None


class TestANewRosterReplaces:
    """A lane that asks a fresh question this turn always wins, answered or not."""

    def test_a_fresh_roster_from_the_lane_replaces_the_old_one(self) -> None:
        old_roster = oq.ask("product_pick", options=_rows("A", "B", "C"), turn_no=1)
        new_roster = oq.ask("product_pick", options=_rows("X", "Y"), turn_no=5)
        ctx = _ctx(message_type="casual", open_question_answered="product_pick")
        ctx["parse"]["_open_question_before"] = old_roster
        item = {
            "outcome": {
                "build-suggest-offer": {
                    "suggest_offer": True,
                    "suggest_response": "pick one",
                    "open_question": new_roster,
                }
            }
        }

        result = _compile(item, ctx)

        after = result["variables"]["open_question"]
        assert after is not None
        codes = [r["code"] for r in after["options"]]
        assert codes == ["X", "Y"], "the new roster must win, not the answered old one"


class TestTheOfferRidesOnTheRosterInsteadOfReplacingIt:
    """Rule 3: the one-team escalate offer a pick's rerun produces merges onto the roster
    that was just answered, rather than replacing it with a bare `team_pick`."""

    def test_the_offer_merges_onto_the_roster(self) -> None:
        roster = oq.ask("product_pick", options=_rows("A", "B", "C"), turn_no=3)
        ctx = _ctx(
            message_type="casual",
            open_question_answered="product_pick",
            domain_hint="inventory",
            routing={"suggested_team": "purchasing", "suggested_agent": "order_enquiries"},
        )
        ctx["parse"]["_open_question_before"] = roster
        item = {
            "outcome": {
                "escalate-catalog": {
                    "is_escalate_offer": True,
                    "response": "Would you like me to escalate to purchasing team?",
                    "manualResponse": True,
                    "includeResponse": True,
                }
            }
        }

        result = _compile(item, ctx)

        after = result["variables"]["open_question"]
        assert after is not None
        assert after["kind"] == "product_pick", (
            f"the offer must ride the roster, not replace it: got kind {after.get('kind')!r}"
        )
        assert after["expects"] == "pick_or_yes_no"
        assert after["options"] == roster["options"]
        assert after["asked_at_turn"] == 3
        offer = (after.get("payload") or {}).get("offer") or {}
        assert offer.get("team") == "purchasing"
        assert offer.get("options") == [{"idx": 1, "team": "purchasing", "label": "purchasing"}]


class TestTheMergedQuestionAnswered:
    """Rule 3's two answers: 'yes' consumes the whole question, 'no' strips the offer and
    leaves the roster exactly as rule 1 would."""

    def _merged(self) -> dict:
        offer = {
            "team": "purchasing",
            "domain": "inventory",
            "options": [{"idx": 1, "team": "purchasing", "label": "purchasing"}],
        }
        roster = oq.ask(
            "product_pick",
            options=_rows("A", "B", "C"),
            turn_no=3,
            expects="pick_or_yes_no",
            payload={"team": "purchasing", "domain": "inventory", "offer": offer},
        )
        return roster

    def test_yes_consumes_the_whole_question(self) -> None:
        merged = self._merged()
        ctx = _ctx(
            message_type="casual",
            open_question_answered="team_pick",
            escalation={"is_escalation_confirmation": True},
        )
        ctx["parse"]["_open_question_before"] = merged

        result = _compile({"outcome": {}}, ctx)

        assert result["variables"]["open_question"] is None, (
            "a 'yes' that runs the escalation must consume the merged question entirely"
        )

    def test_no_declines_and_the_roster_stays_without_the_offer(self) -> None:
        merged = self._merged()
        ctx = _ctx(
            message_type="casual",
            open_question_answered="team_pick",
            escalation={"is_escalation_confirmation": False},
        )
        ctx["parse"]["_open_question_before"] = merged

        result = _compile({"outcome": {}}, ctx)

        after = result["variables"]["open_question"]
        assert after is not None, "'no' declines the OFFER, not the roster"
        assert after["kind"] == "product_pick"
        assert after["expects"] == "pick", "expects reverts to a plain pick once declined"
        assert not (after.get("payload") or {}).get("offer"), "the offer must be stripped"
        assert after["options"] == merged["options"]
        assert after["asked_at_turn"] == 3


# --------------------------------------------------------------------------- #
# B1 (Opus S6 review, blocker): the empty re-arm rescue never fires once an offer
# has ridden the roster.
# --------------------------------------------------------------------------- #


class TestACasualTurnLeavesAMergedRosterIntact:
    """`_is_the_same_question_re_armed_empty` requires `asked.expects == previous.expects`.

    The LIVE question (merged) reads `pick_or_yes_no`; `_ask_for_turn` re-derives the
    re-armed menu with the plain default `pick` (`KIND_SPEC`'s default, since the re-arm
    carries no offer of its own). The two `expects` values can never match, so the rescue
    that is supposed to keep the live roster's rows never fires and the freshly (EMPTY)
    re-armed menu overwrites the live merged one - `tier_pick / pick / 0 rows / offer gone
    / asked_at_turn 0`, reproduced by the reviewer through `compile_current_state` on a
    casual turn where `_offer_carry` re-seats the `tier_offer` label onto a turn that built
    no roster of its own.
    """

    def test_merged_tier_roster_survives_a_casual_turn(self) -> None:
        offer = {
            "team": "purchasing",
            "domain": "promotion",
            "options": [{"idx": 1, "team": "purchasing", "label": "purchasing"}],
        }
        merged = oq.ask(
            "tier_pick",
            options=_tier_rows(),
            turn_no=9,
            expects="pick_or_yes_no",
            payload={"team": "purchasing", "domain": "promotion", "offer": offer},
        )
        ctx = _ctx(message_type="casual", domain_hint=None, intent_hint=None)
        ctx["session"]["session_vars"]["variables"]["open_question"] = merged
        ctx["parse"]["_open_question_before"] = merged

        result = _compile({"outcome": {}}, ctx)

        after = result["variables"]["open_question"]
        assert after is not None, "the merged tier roster must survive a casual turn"
        assert after["kind"] == "tier_pick"
        assert after["expects"] == "pick_or_yes_no"
        assert after["options"] == merged["options"]
        assert (after.get("payload") or {}).get("offer", {}).get("team") == "purchasing"
        assert after["asked_at_turn"] == 9

    def test_merged_product_roster_survives_a_casual_turn(self) -> None:
        offer = {
            "team": "purchasing",
            "domain": "inventory",
            "options": [{"idx": 1, "team": "purchasing", "label": "purchasing"}],
        }
        merged = oq.ask(
            "product_pick",
            options=_rows("A", "B", "C"),
            turn_no=9,
            expects="pick_or_yes_no",
            payload={"team": "purchasing", "domain": "inventory", "offer": offer},
        )
        ctx = _ctx(message_type="casual", domain_hint=None, intent_hint=None)
        ctx["session"]["session_vars"]["variables"]["open_question"] = merged
        ctx["parse"]["_open_question_before"] = merged

        result = _compile({"outcome": {}}, ctx)

        after = result["variables"]["open_question"]
        assert after is not None, "the merged product roster must survive a casual turn"
        assert after["kind"] == "product_pick"
        assert after["expects"] == "pick_or_yes_no"
        assert after["options"] == merged["options"]
        assert (after.get("payload") or {}).get("offer", {}).get("team") == "purchasing"
        assert after["asked_at_turn"] == 9


# --------------------------------------------------------------------------- #
# S1 (Opus S6 review, should-fix): `_live_roster` consults `previous` whenever
# `carried` is not itself a roster - even when the tail deliberately armed a
# different, non-roster question this turn.
# --------------------------------------------------------------------------- #


class TestArmCrossDomainOfferRespectsTheTailsOwnQuestion:
    def test_a_fresh_clarify_survives_the_cross_domain_offer_arm(self) -> None:
        from app.services.chatbot import engine as engine_mod

        clarify = oq.ask(
            "team_pick",
            options=[
                {"idx": 1, "team": "warehouse", "label": "warehouse"},
                {"idx": 2, "team": "purchasing", "label": "purchasing"},
            ],
            turn_no=5,
        )
        stale_roster = oq.ask("product_pick", options=_rows("A", "B", "C"), turn_no=1)
        sealed = {"session_patch": {"variables": {"open_question": clarify}}}
        ctx = {"parse": {"_turn_no": 5, "_open_question_before": stale_roster}}

        engine_mod._arm_cross_domain_offer(
            sealed, {"team": "warehouse"}, ctx=ctx, domain="inventory"
        )

        after = sealed["session_patch"]["variables"]["open_question"]
        assert after == clarify, (
            "a question the tail deliberately armed this turn must survive untouched, "
            f"not be replaced by a stale roster merged with the offer: got {after!r}"
        )


# --------------------------------------------------------------------------- #
# S4 (Opus S6 review, should-fix): `_offered_team` reads `payload.team`, but a
# merged roster carries the team at `payload.offer.team`.
# --------------------------------------------------------------------------- #


class TestOfferedTeamReadsTheRidingOffer:
    def test_offered_team_reads_the_offer_riding_a_roster(self) -> None:
        from app.services.chatbot.head import output_exchange as ox

        offer = {
            "team": "warehouse",
            "domain": "inventory",
            "options": [{"idx": 1, "team": "warehouse", "label": "warehouse"}],
        }
        merged = oq.ask(
            "product_pick",
            options=_rows("A", "B", "C"),
            turn_no=1,
            expects="pick_or_yes_no",
            payload={"offer": offer},
        )

        team = ox._offered_team({"open_question": merged}, {"suggested_team": "purchasing"})

        assert team == "warehouse", (
            "the D1 guard (names_other_team) reads the OFFER's team over a merged "
            f"roster, not the prior turn's routing - got {team!r}"
        )


# --------------------------------------------------------------------------- #
# Nit (Opus S6 review): `_offer_rides_on_roster` merges an offer with no team at
# all (`_ask_for_turn` arms it with `options: []` when the team is falsy).
# --------------------------------------------------------------------------- #


class TestAnOfferWithNoTeamDoesNotRide:
    def test_an_offer_with_no_team_does_not_ride(self) -> None:
        previous = oq.ask("product_pick", options=_rows("A", "B", "C"), turn_no=1)
        empty_offer_ask = {
            "kind": "team_pick",
            "expects": "yes_no",
            "options": [],
            "payload": {"team": None, "domain": "inventory"},
            "asked_at_turn": 2,
            "asked_at": None,
        }

        rides = compile_state_mod._offer_rides_on_roster(empty_offer_ask, previous)

        assert rides is False, (
            "an offer with no team is not a real offer - it must not ride the roster"
        )


# --------------------------------------------------------------------------- #
# B3 (owner-found on :3081): a survived roster must never take the CURRENT
# turn's ANSWER rows as its own options.
# --------------------------------------------------------------------------- #


class TestASurvivedRosterNeverTakesTheAnswersRows:
    """"promo for srtwc286" -> tier menu; "1" -> HIT, reply lists 3 promotions
    numbered 1..3; "2" -> tier menu asked again.

    Trace: after the "1" turn the persisted `open_question` kept `kind: tier_pick` but
    its `options` became the three promotion file names the reply printed, and
    `asked_at_turn` was re-stamped. The "2" turn then resolved `tier_pick` pick 2 to
    that file name (`access_levels` = the file name), the tier gate found no tier and
    re-asked. Cause under verification by the coder: `_picker_carry` re-seats the
    `tier_offer` label and `_ask_for_turn` re-arms `tier_pick` with
    `options=last_result_set` = THIS TURN's ANSWER rows, not the roster's own frozen
    tiers.
    """

    def test_tier_roster_keeps_its_tiers_when_the_reply_prints_rows(self) -> None:
        roster = oq.ask("tier_pick", options=_tier_rows(), turn_no=9)
        ctx = _ctx(
            message_type="casual",
            open_question_answered="tier_pick",
            domain_hint=None,
            intent_hint=None,
        )
        ctx["session"]["session_vars"]["variables"]["open_question"] = roster
        ctx["parse"]["_open_question_before"] = roster
        # The reply the promo lane printed THIS turn: three promotion file names, not
        # tiers - mirrors `test_tail_units._compile`'s way of seeding a fresh roster
        # (`access-level-choice-message`'s own `tier_offer` / `tier_last_result_set`
        # shape, which is what re-seats the `tier_offer` label and the printed rows).
        promo_rows = [
            {"idx": 1, "label": "UPDATED SORENTO WATER CLOSET PROMO_27082026.pdf"},
            {"idx": 2, "label": "SORENTO BASIN PROMO_27082026.pdf"},
            {"idx": 3, "label": "SORENTO SHOWER PROMO_27082026.pdf"},
        ]
        item = {
            "outcome": {
                "access-level-choice-message": {
                    "tier_offer": True,
                    "tier_last_result_set": promo_rows,
                }
            }
        }

        result = _compile(item, ctx)

        after = result["variables"]["open_question"]
        assert after is not None
        assert after["kind"] == "tier_pick"
        assert after["options"] == roster["options"], (
            "the survived roster's own frozen tiers must stand, not this turn's "
            f"printed rows: got {after['options']!r}"
        )
        assert after["asked_at_turn"] == 9
        assert after["expects"] == "pick"

    def test_product_roster_keeps_its_rows_when_the_reply_prints_rows(self) -> None:
        roster = oq.ask("product_pick", options=_rows("A", "B", "C"), turn_no=9)
        ctx = _ctx(
            message_type="casual",
            open_question_answered="product_pick",
            domain_hint=None,
            intent_hint=None,
        )
        ctx["session"]["session_vars"]["variables"]["open_question"] = roster
        ctx["parse"]["_open_question_before"] = roster
        # The did-you-mean lane's own re-seat shape: a fresh suggest-offer roster of
        # STOCK rows, unrelated to the survived product picker's own three options.
        stock_rows = [
            {"idx": 1, "label": "SRTWC8517", "code": "SRTWC8517"},
            {"idx": 2, "label": "SRTWC8518", "code": "SRTWC8518"},
        ]
        item = {
            "outcome": {
                "build-suggest-offer": {
                    "suggest_offer": True,
                    "suggest_response": "here is the stock",
                    "suggest_last_result_set": stock_rows,
                }
            }
        }

        result = _compile(item, ctx)

        after = result["variables"]["open_question"]
        assert after is not None
        assert after["kind"] == "product_pick"
        assert after["options"] == roster["options"], (
            "the survived roster's own frozen rows must stand, not this turn's "
            f"printed answer rows: got {after['options']!r}"
        )
        assert after["asked_at_turn"] == 9
        assert after["expects"] == "pick"


# --------------------------------------------------------------------------- #
# S7a (owner regression, lane-introduced at the five-key session): the
# "multiple matches" picker (`lanes/business/gate.py`'s `require_specific`
# ladder) composes a numbered reply and never calls `ask()`; `_ask_for_turn`
# has arms for team_clarify / company_clarify / member_offer / tier_offer and
# `offer_open`, but NO arm for the `disambiguation` label, so the escalate
# offer wins (or nothing at all) and the roster is dropped. Real evidence:
# turns 26b15a53-87a8-43be-8e55-5839b3ce3149 ("incoming wc286", persisted
# open_question = team_pick yes_no with ONE row, reply text has no escalate
# sentence) and 7528f2f4-84ce-4cdb-b9c4-92f32c95d013 ("8") on DB
# sorento_ai_automation_focus_full.
# --------------------------------------------------------------------------- #


def _compatible_entities(*codes: str, entity_type: str = "product") -> list[dict]:
    """The gate's own `compatible_entities` shape (`{uuid, entity_type, code}`,
    `lanes/business/gate.py`'s `exact_entities` / `compatible_entities` builders) -
    what a `require_specific` reply's `outcome["central-exchange"]` carries."""
    return [
        {"uuid": f"uuid-{code}", "entity_type": entity_type, "code": code}
        for code in codes
    ]


class TestADisambiguationTurnArmsItsRoster:
    def test_ten_product_rows_become_a_product_pick(self) -> None:
        codes = [f"SRTWC286-{i}" for i in range(1, 11)]
        ctx = _ctx(
            message_type="business_query",
            domain_hint="incoming",
            intent_hint="check_incoming",
        )
        ctx["parse"]["_turn_no"] = 4
        item = {
            "outcome": {
                "central-exchange": {
                    "require_specific": True,
                    "compatible_entities": _compatible_entities(*codes),
                }
            }
        }

        result = _compile(item, ctx)

        after = result["variables"]["open_question"]
        assert after is not None, "a disambiguation turn must arm its own roster"
        assert after["kind"] == "product_pick"
        assert after["expects"] == "pick"
        assert [r["idx"] for r in after["options"]] == list(range(1, 11))
        picked_codes = [r.get("product") or r.get("code") for r in after["options"]]
        assert picked_codes == codes
        assert after["asked_at_turn"] == 4

    def test_customer_rows_become_a_customer_pick(self) -> None:
        codes = [f"ABC-TRADING-{i}" for i in range(1, 4)]
        ctx = _ctx(
            message_type="business_query",
            domain_hint="order",
            intent_hint="check_order",
        )
        ctx["parse"]["_turn_no"] = 2
        item = {
            "outcome": {
                "central-exchange": {
                    "require_specific": True,
                    "compatible_entities": _compatible_entities(
                        *codes, entity_type="customer"
                    ),
                }
            }
        }

        result = _compile(item, ctx)

        after = result["variables"]["open_question"]
        assert after is not None, "a disambiguation turn must arm its own roster"
        assert after["kind"] == "customer_pick", (
            "the SAME rule miss_suggest._attach_question uses: all rows customer -> "
            "customer_pick"
        )
        assert after["expects"] == "pick"
        assert len(after["options"]) == 3


class TestTheOfferDoesNotReplaceABornDisambiguationRoster:
    def test_the_offer_does_not_replace_a_born_disambiguation_roster(self) -> None:
        codes = [f"SRTWC286-{i}" for i in range(1, 4)]
        ctx = _ctx(
            message_type="business_query",
            domain_hint="incoming",
            intent_hint="check_incoming",
            routing={"suggested_team": "purchasing", "suggested_agent": "order_enquiries"},
        )
        ctx["parse"]["_turn_no"] = 1
        item = {
            "outcome": {
                "central-exchange": {
                    "require_specific": True,
                    "compatible_entities": _compatible_entities(*codes),
                },
                # The reply ACTUALLY carries the escalate sentence this turn
                # (`escalate-catalog`'s own `is_escalate_offer` flag, which is what
                # `offer_open` is computed from) - a turn that both misses to a picker
                # AND appends an escalate offer must not let the offer win.
                "escalate-catalog": {
                    "is_escalate_offer": True,
                    "response": "Would you like me to escalate to purchasing team?",
                    "manualResponse": True,
                    "includeResponse": True,
                },
            }
        }

        result = _compile(item, ctx)

        after = result["variables"]["open_question"]
        assert after is not None
        assert after["kind"] == "product_pick", (
            f"the roster must win over the plain escalate offer: got {after.get('kind')!r}"
        )

    def test_no_offer_means_no_payload_offer(self) -> None:
        codes = [f"SRTWC286-{i}" for i in range(1, 4)]
        ctx = _ctx(
            message_type="business_query",
            domain_hint="incoming",
            intent_hint="check_incoming",
        )
        ctx["parse"]["_turn_no"] = 1
        item = {
            "outcome": {
                "central-exchange": {
                    "require_specific": True,
                    "compatible_entities": _compatible_entities(*codes),
                }
            }
        }

        result = _compile(item, ctx)

        after = result["variables"]["open_question"]
        assert after is not None
        assert after["kind"] == "product_pick"
        assert not (after.get("payload") or {}).get("offer"), (
            "the reply carried no escalate sentence this turn - there is nothing to ride"
        )


class TestACarriedDisambiguationLabelDoesNotReArmFromTheAnswer:
    """B3 shape for this kind (owner-found on :3081, same class as the tier-menu
    regression): once `_ask_for_turn` gains a `disambiguation` arm, the SAME carry
    that re-seats the label for a survived `product_pick` (`_picker_carry`) must not
    let that arm re-compose the roster from THIS TURN's answer rows."""

    def test_a_carried_disambiguation_label_does_not_re_arm_from_the_answer(self) -> None:
        roster = oq.ask("product_pick", options=_rows("A", "B", "C"), turn_no=9)
        ctx = _ctx(
            message_type="business_query",
            open_question_answered="product_pick",
            domain_hint=None,
            intent_hint=None,
        )
        ctx["session"]["session_vars"]["variables"]["open_question"] = roster
        ctx["parse"]["_open_question_before"] = roster
        # This turn's ANSWER: a plain hit reply naming ONE product - the shape a
        # pick's own rerun prints, not a fresh require_specific roster.
        item = {
            "outcome": {
                "central-exchange": {
                    "items": [{"title": "A", "fields": []}],
                }
            }
        }

        result = _compile(item, ctx)

        after = result["variables"]["open_question"]
        assert after is not None
        assert after["kind"] == "product_pick"
        assert after["options"] == roster["options"], (
            "the survived roster's own frozen rows must stand, not this turn's "
            f"printed answer row: got {after['options']!r}"
        )
        assert after["asked_at_turn"] == 9
        assert after["expects"] == "pick"
