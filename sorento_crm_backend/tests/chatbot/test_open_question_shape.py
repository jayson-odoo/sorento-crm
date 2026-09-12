"""AC-1013, AC-1019: the six open-question kinds, no TTL, `idx` from 1 across the roster.

Lane 1 folds `escalate_yes_no` into `team_pick` (D5: one team is today's yes/no, two or
more is a numbered `team_pick`) and drops every kind's TTL (D9: no counter, no TTL,
anywhere - `member_offer`'s TTL 3 goes the same way as the rest).

RED: `OPEN_QUESTION_KINDS` still has 7 members (including `escalate_yes_no`) and
`OpenQuestion` / `dialogue.open_question.ask()` still carry `ttl_turns`.
"""
from __future__ import annotations

from app.services.chatbot.contracts import OPEN_QUESTION_KINDS, OpenQuestion
from app.services.chatbot.dialogue import open_question as oq

EXPECTED_KINDS = {
    "product_pick",
    "customer_pick",
    "tier_pick",
    "team_pick",
    "company_pick",
    "member_offer",
}


class TestOpenQuestionShape:
    def test_kinds_are_exactly_six(self) -> None:
        assert set(OPEN_QUESTION_KINDS) == EXPECTED_KINDS, (
            f"OPEN_QUESTION_KINDS is {sorted(OPEN_QUESTION_KINDS)}, expected the six "
            f"{sorted(EXPECTED_KINDS)} - escalate_yes_no folds into team_pick (D5)"
        )

    def test_no_ttl_turns_field_on_the_contract(self) -> None:
        assert "ttl_turns" not in OpenQuestion.model_fields, (
            f"OpenQuestion still declares ttl_turns (fields={sorted(OpenQuestion.model_fields)})"
        )

    def test_option_idx_numbered_from_one_and_carries_domain(self) -> None:
        built = oq.ask(
            "product_pick",
            options=[
                {"code": "ZZT-A", "label": "ZZT product A", "domain": "inventory"},
                {"code": "ZZT-B", "label": "ZZT product B", "domain": "inventory"},
            ],
            turn_no=1,
        )
        assert "ttl_turns" not in built, (
            "dialogue/open_question.py::ask must not emit ttl_turns any more"
        )
        idxs = [row["idx"] for row in built["options"]]
        assert idxs == [1, 2]
        assert all(row.get("domain") == "inventory" for row in built["options"])


class TestMemberOfferHasNoTtl:
    def test_member_offer_has_no_ttl(self) -> None:
        built = oq.ask("member_offer", options=[{"code": "ZZT-M1"}], turn_no=1)
        assert "ttl_turns" not in built, (
            "member_offer must follow the same clearing rule as every other kind - "
            "its TTL 3 is gone (AC-1019)"
        )
