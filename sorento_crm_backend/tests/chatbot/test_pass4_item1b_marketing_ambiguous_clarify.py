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
from tests.chatbot.test_r3_pending_end_to_end import _stub_parser


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
