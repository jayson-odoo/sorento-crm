"""PLAN-chatbot-escalation-routing.md, "Team (lane, `_person_routing`)". AC-1111 to AC-1118.

RED, written before the coder's slice S2 (Phase 2, test-first). Lane-unit level
(`escalation.run` / `_person_routing`), the fast and precise reproduction the sibling files
(`test_s5_escalation_lane.py`, `test_pass4_item5_...py`) already use - `_ctx`/`_item`/
`_services` are imported from `test_s5_escalation_lane.py` rather than redefined, so a
fixture drift between the two files cannot happen.

D2's ladder (plan "Team" section):

    1. exactly one catalogue team -> that team, no question (AC-1111)
    2. a family word: open offer's team is a member -> that team (AC-1113);
                       else previous turn's team is a member -> that team (AC-1114);
                       else ask over the family only (AC-1112, AC-1115)
    3. no word: unchanged 8 Sep ruling (AC-1117)
    4. the team-word check runs BEFORE `is_escalation_confirmation` (AC-1116)

`ctx`'s `routing=` kwarg is the DERIVED, already-inherited routing (`ctx.parse.output.
routing`) - the same convention `test_pass4_item5_...py` uses to stand in for "what the
previous turn carried", since the routing chain inherits it forward whenever this turn names
no domain of its own.
"""
from __future__ import annotations

from app.services.chatbot.contracts import SUGGESTED_TEAMS
from app.services.chatbot.lanes.escalation import run
from tests.chatbot.test_s5_escalation_lane import _ctx, _item, _services

MARKETING_FAMILY = ["marketing_product", "marketing_form", "marketing_promotion"]


def _comment_text(result: dict) -> str:
    comment = next(a for a in result["actions"] if a["kind"] == "add_comment")
    return comment["text"]


# --------------------------------------------------------------------------- #
# AC-1111: an exact catalogue team word assigns directly, no question
# --------------------------------------------------------------------------- #


def test_ac1111_an_exact_catalogue_team_word_assigns_with_no_question() -> None:
    """Guard, not a defect: `_catalogue_teams` already narrows an EXACT member to itself
    (R-c). Kept here as a guard against D2's ladder rewrite regressing it."""
    ctx = _ctx(
        routing={"suggested_team": "warehouse", "suggested_agent": "general_enquiries"},
        parser_raw={"routing": {"suggested_team": "warehouse", "suggested_agent": None}},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
    )
    item = _item(team="warehouse")
    services = _services()

    result = run(ctx, item, services=services)

    assert result["arm"] == "human-intervention", result
    assert result["pending"] is None
    services.next_assignee.assert_called_once()
    body = services.next_assignee.call_args[0][0]
    assert body["team_code"] == "warehouse", body


# --------------------------------------------------------------------------- #
# AC-1112 / AC-1116: a family word with an open confirmation flag and a previous
# team OUTSIDE the family must still ASK, never fall through the flag short-circuit
# --------------------------------------------------------------------------- #


def test_ac1112_a_family_word_with_no_offer_and_an_outside_prior_team_asks_over_the_family_only() -> None:
    """AC-1112 (the 11 Sep 12:56 turn, turn_3): family word `marketing`, NO open offer,
    previous team `purchasing` (outside the family) - must ask over exactly the three
    marketing teams. RED today: `_person_routing` checks `is_escalation_confirmation`
    BEFORE the team word (D2 point 4 / AC-1116), so this turn's `True` flag short-circuits
    to `None` and the lane falls through to the INHERITED team `purchasing`, never asking."""
    ctx = _ctx(
        routing={"suggested_team": "purchasing", "suggested_agent": "general_enquiries"},
        parser_raw={"routing": {"suggested_team": "marketing", "suggested_agent": None}},
        escalation={"is_escalation_confirmation": True, "company_pick": None},
    )
    item = _item(team="purchasing")
    services = _services()

    result = run(ctx, item, services=services)

    assert result["arm"] == "clarify", (
        f"a family word must ask over its members even with the confirmation flag set and "
        f"an outside prior team, not fall through to an assignment: {result!r}"
    )
    assert result["pending"]["kind"] == "team_clarify", result["pending"]
    assert [p["team"] for p in result["pending"]["options"]] == MARKETING_FAMILY, (
        f"the clarify must offer exactly the three marketing teams, in catalogue order: "
        f"{result['pending']['options']!r}"
    )
    services.next_assignee.assert_not_called()


def test_ac1116_a_named_team_beats_the_confirmation_flag() -> None:
    """AC-1116: the team-word check runs BEFORE the flag check. An EXACT catalogue word
    (`marketing_product`) with `is_escalation_confirmation: true` and a previous team
    OUTSIDE it (`purchasing`) must assign the NAMED team, never the carried one. RED today:
    the flag-first check swallows the word entirely."""
    ctx = _ctx(
        routing={"suggested_team": "purchasing", "suggested_agent": "general_enquiries"},
        parser_raw={"routing": {"suggested_team": "marketing_product", "suggested_agent": None}},
        escalation={"is_escalation_confirmation": True, "company_pick": None},
    )
    item = _item(team="purchasing")
    services = _services()

    result = run(ctx, item, services=services)

    assert result["arm"] == "human-intervention", (
        f"a named exact team must assign, not ask: {result!r}"
    )
    assert _comment_text(result).startswith("Team: marketing_product\n"), (
        f"the NAMED team must win over the confirmation flag's carried team: "
        f"{_comment_text(result)!r}"
    )


# --------------------------------------------------------------------------- #
# AC-1113 / AC-1114: a family word narrows silently when the conversation already
# points at one member - the open offer, or the previous turn's own team
# --------------------------------------------------------------------------- #


def test_ac1113_a_family_word_over_an_open_offer_for_one_of_its_members_assigns_that_member() -> None:
    """AC-1113 (journey step 5): an open one-team `team_pick` offer for `marketing_product`
    plus the family word `marketing` assigns `marketing_product` directly - no question.
    RED today: `_person_routing`'s family branch (`len(matched) > 1`) always clarifies,
    with no read of what offer is open."""
    prev = {
        "routing": {"suggested_team": "customer_service"},
        "open_question": {
            "kind": "team_pick",
            "options": [{"team": "marketing_product", "label": "Marketing Product"}],
            "expects": "yes_no",
            "asked_at_turn": 1,
            "asked_at": None,
            "payload": {"team": "marketing_product"},
        },
    }
    ctx = _ctx(
        routing={"suggested_team": "customer_service", "suggested_agent": "general_enquiries"},
        parser_raw={"routing": {"suggested_team": "marketing", "suggested_agent": None}},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
        prev_variables=prev,
    )
    item = _item(team="customer_service")
    services = _services()

    result = run(ctx, item, services=services)

    assert result["arm"] == "human-intervention", (
        f"the open offer already names one family member - no question: {result!r}"
    )
    assert _comment_text(result).startswith("Team: marketing_product\n"), _comment_text(result)


def test_ac1114_a_family_word_when_the_previous_turn_already_sat_on_one_member_assigns_it() -> None:
    """AC-1114 (journey step 4): the previous turn already sat on `marketing_product` (a
    photo turn), so `marketing` narrows to it with no question. RED today: the family
    branch always clarifies."""
    ctx = _ctx(
        routing={"suggested_team": "marketing_product", "suggested_agent": "general_enquiries"},
        parser_raw={"routing": {"suggested_team": "marketing", "suggested_agent": None}},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
    )
    item = _item(team="marketing_product")
    services = _services()

    result = run(ctx, item, services=services)

    assert result["arm"] == "human-intervention", (
        f"the previous turn's own team already narrows the family - no question: {result!r}"
    )
    assert _comment_text(result).startswith("Team: marketing_product\n"), _comment_text(result)


def test_ac1115_a_family_word_over_an_offer_outside_the_family_asks_over_the_family_only() -> None:
    """AC-1115: an open offer for `warehouse` (outside the `marketing` family) plus the
    family word must still ask, over the family only - never the offered team, never the
    whole catalogue. Not a defect on today's code (the family branch always asks with no
    read of the offer), so this is a guard against the D2 rewrite narrowing wrongly."""
    prev = {
        "routing": {"suggested_team": "warehouse"},
        "open_question": {
            "kind": "team_pick",
            "options": [{"team": "warehouse", "label": "Warehouse"}],
            "expects": "yes_no",
            "asked_at_turn": 1,
            "asked_at": None,
            "payload": {"team": "warehouse"},
        },
    }
    ctx = _ctx(
        routing={"suggested_team": "warehouse", "suggested_agent": "general_enquiries"},
        parser_raw={"routing": {"suggested_team": "marketing", "suggested_agent": None}},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
        prev_variables=prev,
    )
    item = _item(team="warehouse")
    services = _services()

    result = run(ctx, item, services=services)

    assert result["arm"] == "clarify", result
    assert [p["team"] for p in result["pending"]["options"]] == MARKETING_FAMILY, (
        f"the offered team is outside the family; the ask must stay over the family only: "
        f"{result['pending']['options']!r}"
    )
    services.next_assignee.assert_not_called()


# --------------------------------------------------------------------------- #
# AC-1117: the 8 Sep ruling, unchanged - a bare escalate keeps the carried team
# --------------------------------------------------------------------------- #


def test_ac1117_a_bare_escalate_with_no_team_and_no_offer_keeps_the_carried_team() -> None:
    """AC-1117: existing behaviour, re-asserted at the lane-unit level (the full chain is
    already pinned in `test_pass4_item5_no_team_named_keeps_default_routing.py`)."""
    ctx = _ctx(
        routing={"suggested_team": "purchasing", "suggested_agent": "general_enquiries"},
        parser_raw={"routing": {"suggested_team": None, "suggested_agent": None}},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
    )
    item = _item(team="purchasing")
    services = _services()

    result = run(ctx, item, services=services)

    assert result["arm"] == "human-intervention", result
    assert _comment_text(result).startswith("Team: purchasing\n"), _comment_text(result)


# --------------------------------------------------------------------------- #
# AC-1118: an answered team_pick lands on the lane and assigns the picked team
# --------------------------------------------------------------------------- #


def test_ac1118_the_picked_team_from_an_answered_team_pick_is_assigned_with_no_further_question() -> None:
    """AC-1118, re-asserted on the stacked branch (existing R-b behaviour): once a
    `team_pick` is answered, the DERIVED routing for this turn IS the picked team and no
    `_parser_raw` snapshot narrows it further (a picked-team turn carries no raw team word
    of its own) - `_person_routing` must resolve it as "already the team the chain
    resolved" and assign, never re-ask."""
    ctx = _ctx(
        routing={"suggested_team": "marketing_product", "suggested_agent": "general_enquiries"},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
    )
    item = _item(team="marketing_product")
    services = _services()

    result = run(ctx, item, services=services)

    assert result["arm"] == "human-intervention", result
    assert result["pending"] is None
    assert _comment_text(result).startswith("Team: marketing_product\n"), _comment_text(result)


def test_suggested_teams_catalogue_is_the_expected_eight() -> None:
    """A cheap guard on the fixture data above: if the catalogue ever changes shape, the
    family-order assertions above should fail loudly here first."""
    assert list(SUGGESTED_TEAMS) == [
        "purchasing",
        "purchasing_certification",
        "customer_service",
        "marketing_product",
        "marketing_form",
        "warehouse",
        "marketing_promotion",
        "it_admin",
    ]
