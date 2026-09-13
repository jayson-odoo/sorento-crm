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
