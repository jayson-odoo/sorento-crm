"""S3 - ideation reply composer: LLM reply from facts, template fallback.

Keys back to
``documentation/plans/ideation/ideation-intake-redesign-24sep-acceptance-criteria.md``:

- **AC-1301** - the LLM receives only the facts (status, title, captured, next_field,
  duplicate_candidate, idea_number, link) plus the user's message for language.
- **AC-1302** - a non-terminal reply ends with exactly one ``?``/``？``.
- **AC-1303** - ``complete`` contains ``idea_number`` verbatim and at most the one
  URL named by ``link``.
- **AC-1304** - ``duplicate_candidate`` contains the candidate title verbatim.
- **AC-1305** - any LLM failure or a rejected shape falls back to the
  shared-service ``reply_text`` unchanged.
- **AC-1306** - the language hint is taken from the user's message (Malay case).
- **AC-1307** - the access-denied reply for the ``ideation`` agent goes through
  the same composer, facts ``{denied: "ideation"}``, falling back to the existing
  ``access_denied`` template on failure.
- **AC-1310** - a recap reply is point form (title line, then present field
  lines in order Problem/Solution/Impact/Department, then the one question); a
  reply that packs fields into one sentence fails the check.
- **AC-1311** - ``complete`` is point form: title, idea number + WhatsApp-update
  line, ``Track it here: <link>``.

The LLM call is STUBBED; Postgres only (``tests/_pg_fixture.py``).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.services.ai_assistant_service import AIAssistantConfigService
from app.services.ideation_turn_service import (
    _format_ideate_reply,
    compose_ideate_denial_reply,
    compose_ideate_reply,
)
from app.services.llm_provider import ChatResult
from tests._pg_fixture import blank_session


@pytest.fixture
def db_session() -> Session:
    with blank_session() as session:
        yield session


@pytest.fixture
def configured(db_session: Session) -> Session:
    cfg = AIAssistantConfigService(db_session).get()
    cfg.api_key_ciphertext = "fake-key"
    cfg.provider = "openai"
    cfg.model = "gpt-4o-mini"
    cfg.is_enabled = True
    db_session.commit()
    return db_session


class _StubProvider:
    def __init__(self, text: str):
        self._text = text
        self.calls: list = []

    def chat(self, messages, *_a, **_k):
        self.calls.append(messages)
        return ChatResult(content=self._text, prompt_tokens=1, completion_tokens=1, total_tokens=2)


class _BoomProvider:
    def chat(self, *_a, **_k):
        raise RuntimeError("provider down")


def _patched(provider):
    return patch("app.services.ideation_turn_service.get_provider", return_value=provider)


# --------------------------------------------------------------------------- #
# AC-1301 / AC-1306 - facts + user message reach the model                    #
# --------------------------------------------------------------------------- #
def test_facts_and_language_reach_the_model(configured):
    stub = _StubProvider('"Idea title"\nProblem: x\nWhat next?')
    result = {
        "status": "collecting",
        "title": "Idea title",
        "captured": {"problem": "x"},
        "missing": [],
        "next_field": "proposed_solution",
        "duplicate_candidate": None,
        "idea_number": None,
        "link": None,
        "reply_text": "fallback",
    }
    with _patched(stub):
        compose_ideate_reply(
            configured,
            result=result,
            user_message="saya ada idea, tanda harga patut tunjuk harga promo warna merah",
        )
    user_block = stub.calls[0][1]["content"]
    assert "status: collecting" in user_block
    assert "Problem: x" in user_block
    assert "next_field" in user_block
    assert "proposed_solution" in user_block
    assert "saya ada idea" in user_block  # AC-1306: the user's own message rides along


# --------------------------------------------------------------------------- #
# AC-1302 - exactly one trailing question mark, non-terminal                  #
# --------------------------------------------------------------------------- #
def test_non_terminal_reply_with_one_question_is_accepted(configured):
    # #1277: the composed reply is accepted, but the FINAL text bolds the plain
    # label and drops the quoted-title line (non-terminal status) - it is no
    # longer `out == text` verbatim.
    text = '"Show promo price in red on price tags"\nProblem: the price tag should show promo price in red\nWhat\'s your proposed solution?'
    result = {
        "status": "collecting",
        "title": "Show promo price in red on price tags",
        "captured": {"problem": "the price tag should show promo price in red"},
        "missing": [],
        "next_field": "proposed_solution",
        "duplicate_candidate": None,
        "idea_number": None,
        "link": None,
        "reply_text": "fallback text",
    }
    with _patched(_StubProvider(text)):
        out = compose_ideate_reply(configured, result=result, user_message="hi")
    assert out == (
        "*Problem:* the price tag should show promo price in red\n"
        "What's your proposed solution?"
    )


def test_reply_with_extra_question_mark_falls_back(configured):
    text = 'Problem: x? What next?'
    result = {
        "status": "collecting",
        "title": "",
        "captured": {},
        "next_field": None,
        "duplicate_candidate": None,
        "idea_number": None,
        "link": None,
        "reply_text": "fallback text",
    }
    with _patched(_StubProvider(text)):
        out = compose_ideate_reply(configured, result=result, user_message="hi")
    assert out == "fallback text"


def test_reply_with_no_question_falls_back(configured):
    result = {
        "status": "collecting",
        "title": "",
        "captured": {},
        "next_field": None,
        "duplicate_candidate": None,
        "idea_number": None,
        "link": None,
        "reply_text": "fallback text",
    }
    with _patched(_StubProvider("Got it, noted.")):
        out = compose_ideate_reply(configured, result=result, user_message="hi")
    assert out == "fallback text"


# --------------------------------------------------------------------------- #
# AC-1303 / AC-1311 - complete: idea_number verbatim, at most the one URL     #
# --------------------------------------------------------------------------- #
def test_complete_reply_accepted_with_number_and_link(configured):
    text = (
        '"Show promo price in red on price tags"\n'
        "Idea IDEA-0182 is in. We'll update you on WhatsApp.\n"
        "Track it here: https://fe-sorento.foundryx.my/public/ideas/tok_abc123"
    )
    result = {
        "status": "complete",
        "title": "Show promo price in red on price tags",
        "captured": {},
        "next_field": None,
        "duplicate_candidate": None,
        "idea_number": "IDEA-0182",
        "link": "https://fe-sorento.foundryx.my/public/ideas/tok_abc123",
        "reply_text": "fallback",
    }
    with _patched(_StubProvider(text)):
        out = compose_ideate_reply(configured, result=result, user_message="yes")
    assert out == text


def test_complete_reply_missing_idea_number_falls_back(configured):
    text = '"Title"\nYour idea is in. We will update you.\nTrack it here: https://x.test/ideas/tok'
    result = {
        "status": "complete",
        "title": "Title",
        "captured": {},
        "next_field": None,
        "duplicate_candidate": None,
        "idea_number": "IDEA-0182",
        "link": "https://x.test/ideas/tok",
        "reply_text": "fallback",
    }
    with _patched(_StubProvider(text)):
        out = compose_ideate_reply(configured, result=result, user_message="yes")
    assert out == "fallback"


def test_complete_reply_with_extra_url_falls_back(configured):
    text = (
        '"Title"\nIdea IDEA-0182 is in.\n'
        "Track it here: https://x.test/ideas/tok and also see https://evil.test/x"
    )
    result = {
        "status": "complete",
        "title": "Title",
        "captured": {},
        "next_field": None,
        "duplicate_candidate": None,
        "idea_number": "IDEA-0182",
        "link": "https://x.test/ideas/tok",
        "reply_text": "fallback",
    }
    with _patched(_StubProvider(text)):
        out = compose_ideate_reply(configured, result=result, user_message="yes")
    assert out == "fallback"


# --------------------------------------------------------------------------- #
# AC-1304 - duplicate_candidate contains the candidate title verbatim         #
# --------------------------------------------------------------------------- #
def test_duplicate_candidate_reply_accepted_with_title(configured):
    text = "Similar idea exists: Show promo price in red on price tags\nVote for that one, or keep yours separate?"
    result = {
        "status": "duplicate_candidate",
        "title": "",
        "captured": {},
        "next_field": None,
        "duplicate_candidate": {"idea_number": "IDEA-0077", "title": "Show promo price in red on price tags"},
        "idea_number": None,
        "link": None,
        "reply_text": "fallback",
    }
    with _patched(_StubProvider(text)):
        out = compose_ideate_reply(configured, result=result, user_message="hi")
    assert out == text


def test_duplicate_candidate_reply_missing_title_falls_back(configured):
    text = "Similar idea already exists. Vote for that one, or keep yours separate?"
    result = {
        "status": "duplicate_candidate",
        "title": "",
        "captured": {},
        "next_field": None,
        "duplicate_candidate": {"idea_number": "IDEA-0077", "title": "Show promo price in red on price tags"},
        "idea_number": None,
        "link": None,
        "reply_text": "fallback",
    }
    with _patched(_StubProvider(text)):
        out = compose_ideate_reply(configured, result=result, user_message="hi")
    assert out == "fallback"


# --------------------------------------------------------------------------- #
# AC-1305 - LLM failure/timeout/empty falls back unchanged                    #
# --------------------------------------------------------------------------- #
def test_provider_exception_falls_back(configured):
    result = {
        "status": "collecting",
        "title": "",
        "captured": {},
        "next_field": None,
        "duplicate_candidate": None,
        "idea_number": None,
        "link": None,
        "reply_text": "the shared-service words, unchanged",
    }
    with _patched(_BoomProvider()):
        out = compose_ideate_reply(configured, result=result, user_message="hi")
    assert out == "the shared-service words, unchanged"


def test_empty_llm_output_falls_back(configured):
    result = {
        "status": "collecting",
        "title": "",
        "captured": {},
        "next_field": None,
        "duplicate_candidate": None,
        "idea_number": None,
        "link": None,
        "reply_text": "fallback text",
    }
    with _patched(_StubProvider("   ")):
        out = compose_ideate_reply(configured, result=result, user_message="hi")
    assert out == "fallback text"


def test_no_api_key_falls_back(db_session):
    """No AI assistant config seeded -> the composer never even calls the model."""
    result = {
        "status": "collecting",
        "title": "",
        "captured": {},
        "next_field": None,
        "duplicate_candidate": None,
        "idea_number": None,
        "link": None,
        "reply_text": "fallback text",
    }
    out = compose_ideate_reply(db_session, result=result, user_message="hi")
    assert out == "fallback text"


# --------------------------------------------------------------------------- #
# AC-1310 - point-form recap; a one-sentence pack fails                       #
# --------------------------------------------------------------------------- #
def test_recap_reply_accepted_point_form(configured):
    # #1277: bold labels + no title line in a recap - `out` is no longer the raw
    # LLM text verbatim (it used to be plain labels with the quoted title kept).
    text = (
        '"Add slow moving stock filter to dashboard"\n'
        "Problem: add a filter for slow moving stock on the dashboard\n"
        "Solution: a toggle that hides anything that sold in the last 90 days\n"
        "What's the impact if we do this?"
    )
    result = {
        "status": "collecting",
        "title": "Add slow moving stock filter to dashboard",
        "captured": {
            "problem": "add a filter for slow moving stock on the dashboard",
            "proposed_solution": "a toggle that hides anything that sold in the last 90 days",
        },
        "next_field": "impact",
        "duplicate_candidate": None,
        "idea_number": None,
        "link": None,
        "reply_text": "fallback",
    }
    with _patched(_StubProvider(text)):
        out = compose_ideate_reply(configured, result=result, user_message="a toggle that hides stock")
    assert out == (
        "*Problem:* add a filter for slow moving stock on the dashboard\n"
        "*Solution:* a toggle that hides anything that sold in the last 90 days\n"
        "What's the impact if we do this?"
    )


def test_recap_reply_packed_into_one_sentence_falls_back(configured):
    """A recap (opens with the title) that packs the captured fields into one
    sentence instead of per-field lines fails the point-form check (AC-1310)."""
    text = (
        '"Add slow moving stock filter to dashboard"\n'
        "Here's what I've got: problem is stock filter needed, solution is a toggle. "
        "What's the impact if we do this?"
    )
    result = {
        "status": "collecting",
        "title": "Add slow moving stock filter to dashboard",
        "captured": {
            "problem": "add a filter for slow moving stock on the dashboard",
            "proposed_solution": "a toggle that hides anything that sold in the last 90 days",
        },
        "next_field": "impact",
        "duplicate_candidate": None,
        "idea_number": None,
        "link": None,
        "reply_text": "fallback",
    }
    with _patched(_StubProvider(text)):
        out = compose_ideate_reply(configured, result=result, user_message="a toggle")
    assert out == "fallback"


def test_clarifying_answer_is_exempt_from_recap_lines(configured):
    """A plain clarifying answer never opens with the title - it's exempt from
    the field-recap check, but still needs the one trailing question."""
    text = (
        "Impact just means what changes for us once this is done - fewer repeated "
        "questions, happier dealers. What's the impact if we do this?"
    )
    result = {
        "status": "collecting",
        "title": "Chatbot remembers past dealer questions",
        "captured": {"problem": "chatbot should remember what a dealer already asked before"},
        "next_field": "impact",
        "duplicate_candidate": None,
        "idea_number": None,
        "link": None,
        "reply_text": "fallback",
    }
    with _patched(_StubProvider(text)):
        out = compose_ideate_reply(configured, result=result, user_message="what do you mean impact?")
    assert out == text


# --------------------------------------------------------------------------- #
# Reviewer Blocking 1 (round 1, PR #1222 at 720bb8f5): the gate must reject a  #
# fabricated IDEA-<digits> token, URL, or duplicate mention on EVERY status,   #
# not only on complete. Probe table from the review comment.                  #
# --------------------------------------------------------------------------- #
def test_complete_reply_with_substring_idea_number_falls_back(configured):
    """IDEA-0042 is a real fact; IDEA-00421 is NOT the same token (word-boundary,
    never substring)."""
    text = '"Title"\nIdea IDEA-00421 is in. We will update you on WhatsApp.\nTrack it here: https://x.test/ideas/tok'
    result = {
        "status": "complete",
        "title": "Title",
        "captured": {},
        "next_field": None,
        "duplicate_candidate": None,
        "idea_number": "IDEA-0042",
        "link": "https://x.test/ideas/tok",
        "reply_text": "fallback",
    }
    with _patched(_StubProvider(text)):
        out = compose_ideate_reply(configured, result=result, user_message="yes")
    assert out == "fallback"


def test_complete_reply_with_real_and_invented_idea_number_falls_back(configured):
    text = (
        '"Title"\nIdea IDEA-0042 is in, also known as IDEA-0099.\n'
        "Track it here: https://x.test/ideas/tok"
    )
    result = {
        "status": "complete",
        "title": "Title",
        "captured": {},
        "next_field": None,
        "duplicate_candidate": None,
        "idea_number": "IDEA-0042",
        "link": "https://x.test/ideas/tok",
        "reply_text": "fallback",
    }
    with _patched(_StubProvider(text)):
        out = compose_ideate_reply(configured, result=result, user_message="yes")
    assert out == "fallback"


def test_complete_reply_invents_idea_number_when_fact_missing_falls_back(configured):
    text = '"Title"\nIdea IDEA-0777 is in. We will update you on WhatsApp.'
    result = {
        "status": "complete",
        "title": "Title",
        "captured": {},
        "next_field": None,
        "duplicate_candidate": None,
        "idea_number": None,
        "link": None,
        "reply_text": "fallback",
    }
    with _patched(_StubProvider(text)):
        out = compose_ideate_reply(configured, result=result, user_message="yes")
    assert out == "fallback"


def test_collecting_reply_with_url_when_no_link_fact_falls_back(configured):
    text = 'Problem: x\nSee https://evil.test/x for more?'
    result = {
        "status": "collecting",
        "title": "",
        "captured": {},
        "next_field": "impact",
        "duplicate_candidate": None,
        "idea_number": None,
        "link": None,
        "reply_text": "fallback",
    }
    with _patched(_StubProvider(text)):
        out = compose_ideate_reply(configured, result=result, user_message="hi")
    assert out == "fallback"


def test_collecting_reply_invents_idea_number_falls_back(configured):
    text = "Your idea is IDEA-0999. What's the impact?"
    result = {
        "status": "collecting",
        "title": "",
        "captured": {},
        "next_field": "impact",
        "duplicate_candidate": None,
        "idea_number": None,
        "link": None,
        "reply_text": "fallback",
    }
    with _patched(_StubProvider(text)):
        out = compose_ideate_reply(configured, result=result, user_message="hi")
    assert out == "fallback"


# --------------------------------------------------------------------------- #
# Reviewer Should fix 1 (round 2): the fabricated-number check must catch an   #
# invented idea number in any format an LLM could plausibly write it, not     #
# only the exact "IDEA-<digits>" form.                                        #
# --------------------------------------------------------------------------- #
def test_collecting_reply_invents_lowercase_idea_number_falls_back(configured):
    text = "Your idea is idea-0777. What's the impact?"
    result = {
        "status": "collecting",
        "title": "",
        "captured": {},
        "next_field": "impact",
        "duplicate_candidate": None,
        "idea_number": None,
        "link": None,
        "reply_text": "fallback",
    }
    with _patched(_StubProvider(text)):
        out = compose_ideate_reply(configured, result=result, user_message="hi")
    assert out == "fallback"


def test_collecting_reply_invents_spaced_idea_number_falls_back(configured):
    text = "Your idea is IDEA 0777. What's the impact?"
    result = {
        "status": "collecting",
        "title": "",
        "captured": {},
        "next_field": "impact",
        "duplicate_candidate": None,
        "idea_number": None,
        "link": None,
        "reply_text": "fallback",
    }
    with _patched(_StubProvider(text)):
        out = compose_ideate_reply(configured, result=result, user_message="hi")
    assert out == "fallback"


def test_collecting_reply_invents_idea_number_with_trailing_char_falls_back(configured):
    text = "Your idea is IDEA-0777a. What's the impact?"
    result = {
        "status": "collecting",
        "title": "",
        "captured": {},
        "next_field": "impact",
        "duplicate_candidate": None,
        "idea_number": None,
        "link": None,
        "reply_text": "fallback",
    }
    with _patched(_StubProvider(text)):
        out = compose_ideate_reply(configured, result=result, user_message="hi")
    assert out == "fallback"


def test_collecting_reply_invents_duplicate_mention_falls_back(configured):
    text = "Similar idea exists: Made up idea. Keep going?"
    result = {
        "status": "collecting",
        "title": "",
        "captured": {},
        "next_field": "impact",
        "duplicate_candidate": None,
        "idea_number": None,
        "link": None,
        "reply_text": "fallback",
    }
    with _patched(_StubProvider(text)):
        out = compose_ideate_reply(configured, result=result, user_message="hi")
    assert out == "fallback"


def test_duplicate_candidate_reply_with_invented_number_and_url_falls_back(configured):
    text = (
        "Similar idea exists: Show promo price in red on price tags (IDEA-5555, "
        "see https://evil.test/x)\nVote for that one, or keep yours separate?"
    )
    result = {
        "status": "duplicate_candidate",
        "title": "",
        "captured": {},
        "next_field": None,
        "duplicate_candidate": {"idea_number": "IDEA-0077", "title": "Show promo price in red on price tags"},
        "idea_number": None,
        "link": None,
        "reply_text": "fallback",
    }
    with _patched(_StubProvider(text)):
        out = compose_ideate_reply(configured, result=result, user_message="hi")
    assert out == "fallback"


def test_complete_reply_link_with_appended_path_falls_back(configured):
    text = (
        '"Title"\nIdea IDEA-0042 is in.\n'
        "Track it here: https://x.test/ideas/tok/extra"
    )
    result = {
        "status": "complete",
        "title": "Title",
        "captured": {},
        "next_field": None,
        "duplicate_candidate": None,
        "idea_number": "IDEA-0042",
        "link": "https://x.test/ideas/tok",
        "reply_text": "fallback",
    }
    with _patched(_StubProvider(text)):
        out = compose_ideate_reply(configured, result=result, user_message="yes")
    assert out == "fallback"


# --------------------------------------------------------------------------- #
# Reviewer Should fix 1 - voted/cancelled are terminal, no question required   #
# --------------------------------------------------------------------------- #
def test_voted_reply_accepted_without_question(configured):
    text = "Thanks, your vote for IDEA-0077 is counted."
    result = {
        "status": "voted",
        "title": "",
        "captured": {},
        "next_field": None,
        "duplicate_candidate": None,
        "idea_number": "IDEA-0077",
        "link": None,
        "reply_text": "fallback",
    }
    with _patched(_StubProvider(text)):
        out = compose_ideate_reply(configured, result=result, user_message="vote")
    assert out == text


def test_voted_reply_with_invented_idea_number_falls_back(configured):
    text = "Thanks, your vote for IDEA-9999 is counted."
    result = {
        "status": "voted",
        "title": "",
        "captured": {},
        "next_field": None,
        "duplicate_candidate": None,
        "idea_number": "IDEA-0077",
        "link": None,
        "reply_text": "fallback",
    }
    with _patched(_StubProvider(text)):
        out = compose_ideate_reply(configured, result=result, user_message="vote")
    assert out == "fallback"


def test_cancelled_reply_accepted_without_question(configured):
    text = "No worries, I've dropped that idea."
    result = {
        "status": "cancelled",
        "title": "",
        "captured": {},
        "next_field": None,
        "duplicate_candidate": None,
        "idea_number": None,
        "link": None,
        "reply_text": "fallback",
    }
    with _patched(_StubProvider(text)):
        out = compose_ideate_reply(configured, result=result, user_message="cancel")
    assert out == text


# --------------------------------------------------------------------------- #
# Reviewer Should fix 2 - a recap that drops the title line still needs its    #
# per-field lines (detected by captured VALUES appearing in the text, not by  #
# line 1 alone)                                                               #
# --------------------------------------------------------------------------- #
def test_recap_reply_without_title_line_still_requires_field_lines(configured):
    text = (
        "Got it - problem is add a filter for slow moving stock on the dashboard "
        "and solution is a toggle that hides anything that sold in the last 90 days. "
        "What's the impact if we do this?"
    )
    result = {
        "status": "collecting",
        "title": "Add slow moving stock filter to dashboard",
        "captured": {
            "problem": "add a filter for slow moving stock on the dashboard",
            "proposed_solution": "a toggle that hides anything that sold in the last 90 days",
        },
        "next_field": "impact",
        "duplicate_candidate": None,
        "idea_number": None,
        "link": None,
        "reply_text": "fallback",
    }
    with _patched(_StubProvider(text)):
        out = compose_ideate_reply(configured, result=result, user_message="a toggle")
    assert out == "fallback"


# --------------------------------------------------------------------------- #
# Reviewer Should fix 3 - the denial reply rejects an invented URL/question    #
# --------------------------------------------------------------------------- #
def test_denial_reply_with_url_falls_back(configured):
    with _patched(_StubProvider("Not available. Try https://evil.test ?")):
        out = compose_ideate_denial_reply(
            configured, user_message="i have an idea", fallback_text="Sorry, you are not allowed to access ideation"
        )
    assert out == "Sorry, you are not allowed to access ideation"


def test_denial_reply_with_question_falls_back(configured):
    with _patched(_StubProvider("Sorry, would you like to try a different agent?")):
        out = compose_ideate_denial_reply(
            configured, user_message="i have an idea", fallback_text="Sorry, you are not allowed to access ideation"
        )
    assert out == "Sorry, you are not allowed to access ideation"


# --------------------------------------------------------------------------- #
# Reviewer Nit 1 - AC-1311 line positions (idea number on line 2, link on its  #
# own "Track it here:" line), not just presence anywhere in the text          #
# --------------------------------------------------------------------------- #
def test_complete_reply_idea_number_not_on_its_own_line_falls_back(configured):
    text = (
        '"Title" - Idea IDEA-0042 is in. We will update you on WhatsApp.\n'
        "Track it here: https://x.test/ideas/tok"
    )
    result = {
        "status": "complete",
        "title": "Title",
        "captured": {},
        "next_field": None,
        "duplicate_candidate": None,
        "idea_number": "IDEA-0042",
        "link": "https://x.test/ideas/tok",
        "reply_text": "fallback",
    }
    with _patched(_StubProvider(text)):
        out = compose_ideate_reply(configured, result=result, user_message="yes")
    assert out == "fallback"


# Reviewer Should fix 6 (round 1) added unit tests for `canned.access_denied_text`
# itself here, but that function lives in `app.services.chatbot` - importing it
# from this file (outside `tests/chatbot/`) breaks `test_import_boundary.py`
# (Blocking 1, round 2). Moved to
# `tests/chatbot/test_s3_canned_and_ideate.py::TestAccessDeniedTextComposerRouting`.


# --------------------------------------------------------------------------- #
# AC-1307 - access-denied reply for the ideation agent                        #
# --------------------------------------------------------------------------- #
def test_denial_reply_uses_llm_output(configured):
    with _patched(_StubProvider("Sorry, idea capture isn't available for you right now.")):
        out = compose_ideate_denial_reply(
            configured, user_message="i have an idea", fallback_text="Sorry, you are not allowed to access ideation"
        )
    assert out == "Sorry, idea capture isn't available for you right now."


def test_denial_reply_falls_back_on_provider_failure(configured):
    with _patched(_BoomProvider()):
        out = compose_ideate_denial_reply(
            configured, user_message="i have an idea", fallback_text="Sorry, you are not allowed to access ideation"
        )
    assert out == "Sorry, you are not allowed to access ideation"


def test_denial_reply_falls_back_on_empty_output(configured):
    with _patched(_StubProvider("")):
        out = compose_ideate_denial_reply(
            configured, user_message="i have an idea", fallback_text="Sorry, you are not allowed to access ideation"
        )
    assert out == "Sorry, you are not allowed to access ideation"


# --------------------------------------------------------------------------- #
# #1277 (issue) - W1: bold labels. Unit tests of `_format_ideate_reply`       #
# directly, plus integration through `compose_ideate_reply` (AC-1/AC-2).      #
# --------------------------------------------------------------------------- #
def test_format_bolds_plain_labels():
    facts = {"status": "collecting", "title": "", "captured": {}}
    text = "Problem: x\nSolution: y\nWhat's next?"
    out = _format_ideate_reply(text, facts)
    assert out == "*Problem:* x\n*Solution:* y\nWhat's next?"


def test_format_bolds_department_label():
    facts = {"status": "collecting", "title": "", "captured": {}}
    text = "Department: Sales\nWhat's next?"
    out = _format_ideate_reply(text, facts)
    assert out == "*Department:* Sales\nWhat's next?"


def test_format_accepts_already_bold_label_no_double_wrap():
    facts = {"status": "collecting", "title": "", "captured": {}}
    text = "*Problem:* x\nWhat's next?"
    out = _format_ideate_reply(text, facts)
    assert out == text
    assert "**" not in out


def test_format_leaves_clarifying_prose_unchanged():
    facts = {
        "status": "collecting",
        "title": "Chatbot remembers past dealer questions",
        "captured": {"problem": "chatbot should remember what a dealer already asked before"},
    }
    text = (
        "Impact just means what changes for us once this is done - fewer repeated "
        "questions, happier dealers. What's the impact if we do this?"
    )
    out = _format_ideate_reply(text, facts)
    assert out == text


def test_format_is_idempotent():
    facts = {"status": "collecting", "title": "sales order KPI tracking", "captured": {}}
    text = '"sales order KPI tracking"\nProblem: x\nWhat next?'
    once = _format_ideate_reply(text, facts)
    twice = _format_ideate_reply(once, facts)
    assert twice == once


def test_compose_bolds_plain_labels_via_llm_recap(configured):
    text = (
        '"Show promo price in red on price tags"\n'
        "Problem: the price tag should show promo price in red\n"
        "What's your proposed solution?"
    )
    result = {
        "status": "collecting",
        "title": "Show promo price in red on price tags",
        "captured": {"problem": "the price tag should show promo price in red"},
        "next_field": "proposed_solution",
        "duplicate_candidate": None,
        "idea_number": None,
        "link": None,
        "reply_text": "fallback",
    }
    with _patched(_StubProvider(text)):
        out = compose_ideate_reply(configured, result=result, user_message="hi")
    assert "*Problem:*" in out
    assert "Problem: " not in out


def test_compose_accepts_already_bold_recap_no_double_wrap(configured):
    text = (
        "*Problem:* add a filter for slow moving stock on the dashboard\n"
        "*Solution:* a toggle that hides anything that sold in the last 90 days\n"
        "What's the impact if we do this?"
    )
    result = {
        "status": "collecting",
        "title": "Add slow moving stock filter to dashboard",
        "captured": {
            "problem": "add a filter for slow moving stock on the dashboard",
            "proposed_solution": "a toggle that hides anything that sold in the last 90 days",
        },
        "next_field": "impact",
        "duplicate_candidate": None,
        "idea_number": None,
        "link": None,
        "reply_text": "fallback",
    }
    with _patched(_StubProvider(text)):
        out = compose_ideate_reply(configured, result=result, user_message="a toggle")
    assert out == text
    assert "**" not in out


def test_compose_fallback_template_bolds_labels_on_provider_failure(configured):
    """AC-1/AC-2: the shared-service TEMPLATE fallback also gets bolded, not just
    an LLM-composed reply."""
    result = {
        "status": "collecting",
        "title": "",
        "captured": {},
        "next_field": None,
        "duplicate_candidate": None,
        "idea_number": None,
        "link": None,
        "reply_text": "Problem: x\nImpact: z\nAnything else?",
    }
    with _patched(_BoomProvider()):
        out = compose_ideate_reply(configured, result=result, user_message="hi")
    assert "*Problem:* x" in out
    assert "*Impact:* z" in out


# --------------------------------------------------------------------------- #
# #1277 - W3: no title line in a non-complete recap; complete keeps it        #
# (AC-5).                                                                     #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "title_line",
    [
        "sales order KPI tracking",
        '"sales order KPI tracking"',
        '*"sales order KPI tracking"*',
        "Title: sales order KPI tracking",
    ],
)
@pytest.mark.parametrize("status", ["collecting", "review"])
def test_format_drops_title_line_for_non_complete_status(title_line, status):
    facts = {"status": status, "title": "sales order KPI tracking", "captured": {}}
    text = f"{title_line}\nProblem: x\nWhat next?"
    out = _format_ideate_reply(text, facts)
    assert "sales order KPI tracking" not in out
    assert out == "*Problem:* x\nWhat next?"


def test_format_keeps_title_line_on_complete():
    facts = {
        "status": "complete",
        "title": "sales order KPI tracking",
        "idea_number": "IDEA-0003",
        "link": "https://x.test/ideas/tok",
    }
    text = (
        "sales order KPI tracking\n"
        "IDEA-0003 - we'll update you on WhatsApp\n"
        "Track it here: https://x.test/ideas/tok"
    )
    out = _format_ideate_reply(text, facts)
    assert out == text


def test_format_keeps_duplicate_candidate_mention_line():
    facts = {
        "status": "duplicate_candidate",
        "title": "",
        "duplicate_candidate": {"title": "Show promo price in red on price tags"},
    }
    text = (
        "Similar idea exists: Show promo price in red on price tags\n"
        "Vote for that one, or keep yours separate?"
    )
    out = _format_ideate_reply(text, facts)
    assert out == text


@pytest.mark.parametrize(
    "title_line",
    [
        "sales order KPI tracking",
        '"sales order KPI tracking"',
        '*"sales order KPI tracking"*',
        "Title: sales order KPI tracking",
    ],
)
def test_fallback_template_title_line_dropped_on_every_format(configured, title_line):
    """The shared-service TEMPLATE fallback also loses its title line (only
    `complete` keeps one) - the LLM never ran here (_BoomProvider)."""
    fallback = f"{title_line}\nWhat's the impact?"
    result = {
        "status": "collecting",
        "title": "sales order KPI tracking",
        "captured": {},
        "next_field": "impact",
        "duplicate_candidate": None,
        "idea_number": None,
        "link": None,
        "reply_text": fallback,
    }
    with _patched(_BoomProvider()):
        out = compose_ideate_reply(configured, result=result, user_message="hi")
    assert out == "What's the impact?"


# --------------------------------------------------------------------------- #
# #1277 reviewer round 1: the label parser keeps a value's own markup and      #
# accepts the Markdown / italic spellings an LLM writes when told to bold.    #
# --------------------------------------------------------------------------- #
def test_format_keeps_a_value_that_starts_with_an_asterisk():
    facts = {"status": "collecting", "title": "", "captured": {}}
    out = _format_ideate_reply("Problem: *Urgent* orders are late\nWhat next?", facts)
    assert out == "*Problem:* *Urgent* orders are late\nWhat next?"


@pytest.mark.parametrize("line", ["**Problem:** x", "**Problem**: x", "_Problem:_ x"])
def test_format_normalises_markdown_and_italic_labels(line):
    facts = {"status": "collecting", "title": "", "captured": {}}
    assert _format_ideate_reply(f"{line}\nWhat next?", facts) == "*Problem:* x\nWhat next?"


def test_compose_accepts_markdown_bold_recap(configured):
    """An LLM that writes `**Problem:**` is not thrown back to the template (R5:
    the reply keeps the user's language)."""
    text = "**Problem:** stock report is slow\nWhat's your proposed solution?"
    result = {
        "status": "collecting",
        "title": "Faster stock report",
        "captured": {"problem": "stock report is slow"},
        "next_field": "proposed_solution",
        "duplicate_candidate": None,
        "idea_number": None,
        "link": None,
        "reply_text": "fallback",
    }
    with _patched(_StubProvider(text)):
        out = compose_ideate_reply(configured, result=result, user_message="hi")
    assert out == "*Problem:* stock report is slow\nWhat's your proposed solution?"


def test_format_drops_a_full_width_quoted_title_and_collapses_the_gap():
    facts = {"status": "collecting", "title": "销售报告", "captured": {}}
    out = _format_ideate_reply("「销售报告」\n\nProblem: x\n\n\nWhat next?", facts)
    assert out == "*Problem:* x\n\nWhat next?"
