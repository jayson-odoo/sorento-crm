"""Owner console pass 4, item 1b (7 Sep 2026): a bare "marketing" clarifies over ALL EIGHT
teams instead of just the three marketing ones.

Production turns 9a40182a-e24b-49ec-abe5-0c436ff744ea and 8b3a3b80-6ad3-421c-9f4d-197fc70b26c5
(pending-offer shape, n8n execs 15447117 / 15456862, `turns-lane3`) and 08e74db8 (the cold
shape, same lane, item 1a's turn 1) all show "escalate to marketing" reaching the escalation
lane. In the two pending-offer captures the parser's raw routing team came back `null`
(ambiguous) and the STALE offered team (`warehouse` / `purchasing`) silently swallowed the
customer's word - a DIFFERENT, already-covered defect (D1's clarify arm). This file targets
the sibling gap the plan's own D11 inventory calls out: nothing in `escalation.py` narrows a
clarify by what the parser's raw team WORD actually matches in the team catalogue.

`_team_clarify_gate`/`_person_routing` (`escalation.py` ~:692-762) only asks "did the parser
name ANY team" (`jsc.truthy(_parser_team(ctx, team))`) - a non-null, non-empty string skips
the clarify outright and is used AS THE ASSIGNMENT TEAM, valid catalogue member or not. So a
raw team word of `"marketing"` (not itself one of the eight `SUGGESTED_TEAMS` - the three
marketing teams are `marketing_product`, `marketing_form`, `marketing_promotion`) is currently
assigned to a team literally called `marketing`, which does not exist, instead of asking which
of the three the customer means. `_team_clarify_options` (escalation.py ~:764-778), the only
place a clarify's team list is built, has no code path that narrows to catalogue members whose
CODE contains the parser's raw word - it either lists the STAFF hits' own teams (a person
lookup) or every one of the eight `SUGGESTED_TEAMS` verbatim. Grep `"team_clarify"` in
`app/services/chatbot/`: no narrowing exists.

D11-safe: the ambiguity is decided from the PARSER's raw team WORD against the TEAM CATALOGUE
(`app.services.chatbot.contracts.SUGGESTED_TEAMS`), never from the customer's own message
text - `ctx.text` is never read here.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from app.services.chatbot import engine as engine_mod
from tests.chatbot.conftest import set_chatbot_switches
from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output
from tests.chatbot._shared_turn_helpers import _stub_parser


@pytest.fixture()
def seeded(session_factory):
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {"cid": CONTACT_ID, "phone": "+60000000009", "sv": json.dumps({"variables": {}})},
    )
    db.commit()
    set_chatbot_switches(session_factory)
    db.execute(
        text("UPDATE system_settings SET chatbot_completed_lanes = CAST(:l AS jsonb)"),
        {"l": '["out_of_scope"]'},
    )
    db.commit()
    return db


def _run_escalation_ask(session_factory, monkeypatch, *, raw_team: str, text_body: str):
    qf = _parser_output(
        message_type="request_for_help",
        intent_hint=None,
        domain_hint=None,
        entities=[],
        is_affirmative=True,
        user_goal=f"trying to escalate to {text_body}",
        routing={"suggested_team": raw_team, "suggested_agent": None},
        escalation={"is_escalation_confirmation": False, "company_pick": None},
    )
    _stub_parser(monkeypatch, qf)
    envelope = _envelope(is_test=True)
    envelope.contact["phone"] = "+60000000009"
    envelope.message["contact"]["phone"] = "+60000000009"
    envelope.message["message"]["messageId"] = f"ZZT-marketing-ambiguous-{raw_team}"
    envelope.message["message"]["message"]["text"] = f"escalate to {text_body}"
    return engine_mod.run_turn(envelope, session_factory=session_factory)


class TestABareMarketingWordClarifiesOverOnlyTheThreeMarketingTeams:
    def test_marketing_clarifies_with_the_three_marketing_teams_only(
        self, seeded, session_factory, monkeypatch
    ):
        head = _run_escalation_ask(session_factory, monkeypatch, raw_team="marketing", text_body="marketing")

        assert head.branch_kind == "out_of_scope", (head.branch_kind, head.error)

        # A clarify (`_clarify_actions`, escalation.py ~:929) is ONLY a `send_message` - no
        # `add_comment` / `assign_conversation`. Their PRESENCE is proof the lane assigned
        # instead of asking (measured: today it assigns to a team literally called
        # "marketing", which is not in `SUGGESTED_TEAMS`).
        comments = [a for a in (head.actions or []) if a.get("kind") == "add_comment"]
        assert not comments, (
            "an ambiguous team word must ask, never assign to a team that does not exist "
            f"in the catalogue: {comments!r}"
        )

        sends = [a for a in (head.actions or []) if a.get("kind") == "send_message"]
        send_text = " ".join((s.get("text") or "") for s in sends)
        for team_word in ("marketing product", "marketing form", "marketing promotion"):
            assert team_word in send_text, f"{team_word!r} missing from the clarify: {send_text!r}"
        for other_team in (
            "purchasing",
            "purchasing certification",
            "customer service",
            "warehouse",
            "it admin",
        ):
            assert other_team not in send_text, (
                f"an ambiguous 'marketing' must clarify over ONLY the three marketing teams, "
                f"not the whole catalogue - {other_team!r} leaked into: {send_text!r}"
            )

    def test_an_explicit_unambiguous_team_word_still_assigns_directly(
        self, seeded, session_factory, monkeypatch
    ):
        """Control case: a REAL catalogue team must keep assigning directly, with no
        clarify - the fix must narrow an AMBIGUOUS word, not turn every escalation into a
        clarify."""
        head = _run_escalation_ask(session_factory, monkeypatch, raw_team="warehouse", text_body="warehouse")

        assert head.branch_kind == "out_of_scope", (head.branch_kind, head.error)
        comments = [a for a in (head.actions or []) if a.get("kind") == "add_comment"]
        assert any("Team: warehouse" in (a.get("text") or "") for a in comments), (
            f"an unambiguous, valid team word must still assign directly: {comments!r}"
        )


# --------------------------------------------------------------------------- #
# Opus review of #713, blocker B2. `_catalogue_teams` narrowed the word only
# INSIDE `_person_routing`, and the raw word went on flowing through the routing
# chain into `variables.routing.suggested_team` and onto the `pending` marker's
# `team`. On the FOLLOW-UP turn (parser team null, carried "marketing") the lane
# assigned it verbatim: `next_assignee` called with `team_code: "marketing"` and
# a comment reading "Team: marketing" - a team that does not exist. The ask was
# right and the answer to it was still wrong.
# --------------------------------------------------------------------------- #

from app.services.chatbot.contracts import SUGGESTED_TEAMS  # noqa: E402
from tests.chatbot._shared_turn_helpers import _session_of  # noqa: E402
from tests.chatbot.test_s5_escalation_lane import _services  # noqa: E402


@pytest.fixture()
def stub_assignment_seams(monkeypatch):
    """The round-robin draw and the SLA write, stubbed - see the same fixture in
    `test_pass4_item1a_team_clarify_consumed.py` for why both turns run live."""
    from app.services.chatbot.lanes import escalation_services

    monkeypatch.setattr(escalation_services, "build", lambda db: _services())


def _run_live(session_factory, monkeypatch, *, qf, text_body, msg_id):
    _stub_parser(monkeypatch, qf)
    envelope = _envelope(is_test=False)
    envelope.contact["phone"] = "+60000000009"
    envelope.message["contact"]["phone"] = "+60000000009"
    envelope.message["message"]["messageId"] = msg_id
    envelope.message["message"]["message"]["text"] = text_body
    return engine_mod.run_turn(envelope, session_factory=session_factory)


class TestANonCatalogueTeamWordIsNeverPersistedOrAssigned:
    def test_a_later_turn_is_assigned_to_a_real_team_never_to_marketing(
        self, seeded, session_factory, monkeypatch, stub_assignment_seams
    ):
        # -- turn 1: "escalate to marketing" -> the three-team menu ------------------- #
        head1 = _run_live(
            session_factory,
            monkeypatch,
            qf=_parser_output(
                message_type="request_for_help",
                intent_hint=None,
                domain_hint=None,
                entities=[],
                is_affirmative=True,
                user_goal="trying to escalate to marketing",
                routing={"suggested_team": "marketing", "suggested_agent": None},
                escalation={"is_escalation_confirmation": False, "company_pick": None},
            ),
            text_body="escalate to marketing",
            msg_id="ZZT-b2-t1",
        )
        assert head1.branch_kind == "out_of_scope", (head1.branch_kind, head1.error)
        assert "Which team should I pass this to" in ((head1.reply or {}).get("text") or "")

        stored1 = _session_of(session_factory)["variables"]
        persisted = (stored1.get("routing") or {}).get("suggested_team")
        assert persisted in SUGGESTED_TEAMS, (
            "a team word the catalogue does not hold must never reach the persisted "
            f"routing - the next turn assigns whatever is there: {persisted!r}"
        )
        marker_team = (stored1.get("pending") or {}).get("team")
        assert marker_team is None or marker_team in SUGGESTED_TEAMS, (
            f"nor the pending marker's own team: {marker_team!r}"
        )
        # The S1 SEAM, graded on a REAL ask turn rather than on a seeded marker: the teams
        # this ask offered must actually reach `pending.options`, or the tap path in
        # `output_exchange._team_clarify_pick` has nothing to resolve against and its own
        # test would be grading a fixture it wrote itself. Blanking the list in
        # `pending.derive` must redden HERE, on the turn that composes the ask.
        assert (stored1.get("pending") or {}).get("options"), (
            "the ask must persist the teams it offered, slug beside label, or a tap on a "
            f"quick reply resolves to nothing: {stored1.get('pending')!r}"
        )
        assert {o["team"] for o in stored1["pending"]["options"]} == {
            "marketing_product",
            "marketing_form",
            "marketing_promotion",
        }, stored1["pending"]["options"]

        # -- turn 2: the customer gives up on the menu and asks for anyone ------------ #
        # Parser team null, so the routing chain falls back to what turn 1 carried. That
        # is exactly the shape that assigned "Team: marketing" before the fix.
        head2 = _run_live(
            session_factory,
            monkeypatch,
            qf=_parser_output(
                message_type="request_for_help",
                intent_hint=None,
                domain_hint=None,
                entities=[],
                is_affirmative=None,
                user_goal="trying to talk to a human",
                routing={"suggested_team": None, "suggested_agent": None},
                escalation={"is_escalation_confirmation": False, "company_pick": None},
            ),
            text_body="I need a human",
            msg_id="ZZT-b2-t2",
        )
        assert head2.branch_kind == "out_of_scope", (head2.branch_kind, head2.error)
        comments = [a for a in (head2.actions or []) if a.get("kind") == "add_comment"]
        assert comments, f"the turn must assign, not ask again: {head2.actions!r}"
        assigned = [a.get("text") or "" for a in comments]
        assert not any("Team: marketing\n" in t for t in assigned), (
            f"'marketing' is not one of the eight teams and must never be assigned: {assigned!r}"
        )
        assert any(
            any(f"Team: {t}\n" in text for t in SUGGESTED_TEAMS) for text in assigned
        ), f"the turn must be assigned to a REAL catalogue team: {assigned!r}"
