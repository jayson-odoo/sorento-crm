"""WA-COMPLAINT-INTAKE round 14 red tests: an issue flow never gives up, and the complaint about the
assistant's answer files with the exchange it complains about.

Contract: documentation/plans/chatbot/PROMPT-wa-issue-ideate.md section "Round 14" (crew decision 14 Nov).
Live failure: "this is not the asnwer i want" -> asked "What went wrong?" -> "i want to report this is not
the answer i want to the IT team" -> the IDEA give-up ("I still couldn't find an idea in that ...").

- An issue flow asks "What went wrong?" at most once and never gives up: the answer to that ask, even with
  no problem in it, files the issue with the user's own words (title by the shared `item_title`).
- The idea flow's give-up is unchanged.
- The give-up copy has an issue wording in en / ms / zh, never the word idea.
- The capture hands the contact's last exchanges (`turn_runtime.recent_exchanges`) to the extractor, and
  the filed item's transcript carries them.
- The extractor schema says, by meaning, that "the assistant's answer was wrong / not what I wanted" is a
  problem.

Real Postgres on the blank scratch schema (`env` fixture from test_ideation_capture_turn); every test
seeds its own workspace, contact, user and chatbot turns. Placeholder data only.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

# MUST be the first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot_reply_copy import (
    IDEATION_CAPTURE_ASK_IDEA,
    IDEATION_CAPTURE_ASK_ISSUE,
    IDEATION_CAPTURE_GIVE_UP,
)
from app.services.ideation_extractor import IdeateExtraction
from app.services.llm_provider import ChatResult
from tests.test_ideation_capture_turn import Env, env  # noqa: F401  (fixture)

IDEA_NUMBER = "IDEA-0184"
LANGUAGES = ("en", "ms", "zh")

# The owner's conversation (round 14 live failure), typo kept.
FIRST = "this is not the asnwer i want"
SECOND = "i want to report this is not the answer i want to the IT team"
# The exchange it complains about.
PREV_USER = "how much is the promo for SRTWC286-SH"
PREV_BOT = "Promotion: none found"
COMPLAINT_PROBLEM = "The assistant's answer to the promo question was not what the user wanted"


def _words(text: str) -> set[str]:
    return set(re.findall(r"\w+", (text or "").lower()))


def _lines(reply: str) -> list[str]:
    return [line.strip() for line in reply.splitlines() if line.strip()]


def _script(e: Env, text: str, *, type_: str, has_idea: bool | None, fields: dict | None = None,
            language: str = "en", title: str = "") -> str:
    e.extraction(text, fields=fields or {}, title=title, language=language)
    e.extractions[text].type = type_
    e.extractions[text].has_idea = has_idea
    return text


def _seed_done_turn(e: Env, user_text: str, bot_text: str, *, minutes_ago: int = 2) -> None:
    """One completed exchange with this contact, stored the way the engine stores it."""
    e.db.add(
        ChatbotTurn(
            id=str(uuid.uuid4()),
            contact_respond_id=e.rio,
            message_id=f"zzt-r14-{uuid.uuid4().hex[:8]}",
            ingress="webhook",
            is_test=False,
            status="done",
            stage="sent",
            branch_kind="business_query",
            envelope={"message": {"message": {"message": {"type": "text", "text": user_text}}}},
            response={"reply": {"text": bot_text}},
            created_at=datetime.now() - timedelta(minutes=minutes_ago),
        )
    )
    e.db.flush()


# --------------------------------------------------------------------------- #
# 1. An issue flow asks at most once and never gives up                       #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("second_type", ["issue", "idea"], ids=["answer_read_as_issue", "answer_read_as_idea"])
def test_R14_an_issue_flow_files_the_answer_to_its_ask_and_never_gives_up(env, second_type):  # noqa: F811
    env.ready()
    env.created()

    # Turn 1: an intent-only report reads as an issue -> the issue ask.
    first = env.turn(_script(env, FIRST, type_="issue", has_idea=False))
    assert first["status"] == "ask_idea", first["status"]
    assert first["reply_text"] == IDEATION_CAPTURE_ASK_ISSUE["en"]
    assert env.create_calls == []

    # Turn 2: the answer to that ask still holds no problem. The capture remembers the flow was an
    # issue (whatever type the extractor reads now) and files it rather than giving up.
    second = env.turn_ask(_script(env, SECOND, type_=second_type, has_idea=False))
    assert second["status"] != "ask_idea_gave_up", second["reply_text"]
    assert second["status"] == "complete", second
    assert len(env.create_calls) == 1, env.create_calls
    (payload,) = env.create_calls
    assert payload["type"] == "issue", payload
    assert (payload.get("title") or "").strip(), payload
    problem = (payload.get("problem") or "").strip()
    assert problem, payload
    # Made of the user's own words: every word of the problem was said by the user.
    said = _words(FIRST) | _words(SECOND)
    assert _words(problem) <= said, (problem, _words(problem) - said)

    lines = _lines(second["reply_text"])
    assert f"Logged as issue {IDEA_NUMBER}" in lines, second["reply_text"]
    assert IDEATION_CAPTURE_GIVE_UP["en"] not in second["reply_text"]
    assert "couldn't find an idea" not in second["reply_text"].lower()


def test_R14_an_issue_ask_reply_with_no_problem_never_gives_up(env):  # noqa: F811
    """Even with no remembered ask (the slot came back without it), an answer read as an issue with no
    problem files the issue with the user's words: an issue flow never gives up."""
    env.ready()
    env.created()
    out = env.turn_ask(_script(env, SECOND, type_="issue", has_idea=False))
    assert out["status"] == "complete", out
    (payload,) = env.create_calls
    assert payload["type"] == "issue"
    assert (payload.get("problem") or "").strip()
    assert _words(payload["problem"]) <= _words(SECOND), payload["problem"]


# --------------------------------------------------------------------------- #
# 2. The idea flow's give-up is unchanged (control)                           #
# --------------------------------------------------------------------------- #
def test_R14_the_idea_flow_still_gives_up_with_the_idea_wording(env):  # noqa: F811
    env.ready()
    env.created()
    first = env.turn(_script(env, "I have an idea", type_="idea", has_idea=False))
    assert first["status"] == "ask_idea"
    assert first["reply_text"] == IDEATION_CAPTURE_ASK_IDEA["en"]

    second = env.turn_ask(_script(env, "want to submit idea", type_="idea", has_idea=False))
    assert second["status"] == "ask_idea_gave_up", second
    assert second["reply_text"] == IDEATION_CAPTURE_GIVE_UP["en"]
    assert env.create_calls == []


# --------------------------------------------------------------------------- #
# 3. The issue give-up copy never says idea                                    #
# --------------------------------------------------------------------------- #
def _issue_give_up() -> dict[str, str]:
    from app.services import chatbot_reply_copy

    copy = getattr(chatbot_reply_copy, "IDEATION_CAPTURE_GIVE_UP_ISSUE", None)
    assert isinstance(copy, dict), "chatbot_reply_copy.IDEATION_CAPTURE_GIVE_UP_ISSUE (en/ms/zh) is missing"
    return copy


@pytest.mark.parametrize("language", LANGUAGES)
def test_R14_the_issue_give_up_copy_exists_and_never_says_idea(language):
    from app.services.chatbot_reply_copy import CHATBOT_REPLY_COPY

    text_ = _issue_give_up().get(language, "")
    assert text_.strip(), f"{language}: no issue give-up text"
    assert "idea" not in text_.lower(), f"{language}: {text_!r}"
    assert "创意" not in text_, f"{language}: {text_!r}"
    assert text_ != IDEATION_CAPTURE_GIVE_UP[language]
    # Registered like every other capture reply, so an owner edit can win.
    key = "ideation_capture_give_up_issue" + ("" if language == "en" else f".{language}")
    assert key in CHATBOT_REPLY_COPY, key
    assert CHATBOT_REPLY_COPY[key][1] == text_


@pytest.mark.parametrize("language", LANGUAGES)
def test_R14_a_give_up_in_an_issue_flow_renders_the_issue_wording(language):
    from app.services.ideation_capture_replies import render_reply

    got = render_reply("ask_idea_gave_up", {"type": "issue"}, user_message="x", language=language)
    assert got == _issue_give_up()[language], got
    assert "idea" not in got.lower() and "创意" not in got


@pytest.mark.parametrize("language", LANGUAGES)
def test_R14_the_idea_give_up_still_renders_the_idea_wording(language):
    """Control: the idea flow's give-up is the same text as before."""
    from app.services.ideation_capture_replies import render_reply

    assert render_reply("ask_idea_gave_up", {}, user_message="x", language=language) == IDEATION_CAPTURE_GIVE_UP[language]
    assert (
        render_reply("ask_idea_gave_up", {"type": "idea"}, user_message="x", language=language)
        == IDEATION_CAPTURE_GIVE_UP[language]
    )


# --------------------------------------------------------------------------- #
# 4. The extractor sees the previous exchange                                 #
# --------------------------------------------------------------------------- #
class _CapturingProvider:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[list[dict[str, Any]]] = []

    def chat(self, messages, *_a, **_k):  # noqa: ANN001
        self.calls.append(list(messages))
        return ChatResult(content=json.dumps(self.payload), prompt_tokens=1, completion_tokens=1, total_tokens=2)


@pytest.fixture
def real_extractor(env, monkeypatch):  # noqa: F811
    """The capture runs the REAL `extract_ideate_turn`; only the provider is stubbed (it records what
    it was sent)."""
    import app.services.ideation_capture_service as svc
    from app.services import ideation_extractor

    provider = _CapturingProvider(
        {
            "fields": [{"key": "problem", "value": COMPLAINT_PROBLEM}],
            "use_cases": [], "remove": [], "skip": [], "title": "Assistant answer not satisfying",
            "review_action": "none", "change_text": "", "duplicate_choice": "none",
            "has_idea": True, "type": "issue", "language": "en",
        }
    )
    config = SimpleNamespace(provider="openai", model="gpt-zzt")
    monkeypatch.setattr(ideation_extractor.AIAssistantConfigService, "get", lambda self: config)
    monkeypatch.setattr(ideation_extractor, "resolve_api_key", lambda cfg, provider_name: "sk-zzt")
    monkeypatch.setattr(ideation_extractor.ai_prompt_registry, "render", lambda db, name: ("system zzt", 0))
    monkeypatch.setattr(ideation_extractor, "get_provider", lambda *a, **k: provider)
    monkeypatch.setattr(svc, "extract_ideate_turn", ideation_extractor.extract_ideate_turn)
    return provider


def test_R14_the_extractor_is_sent_the_previous_exchange(env, real_extractor):  # noqa: F811
    env.ready()
    env.created()
    _seed_done_turn(env, PREV_USER, PREV_BOT)

    out = env.turn(SECOND)
    assert real_extractor.calls, "the extractor never reached the provider"
    user_block = "\n".join(
        str(m.get("content") or "") for m in real_extractor.calls[0] if m.get("role") == "user"
    )
    assert PREV_USER in user_block, user_block
    assert PREV_BOT in user_block, user_block
    assert SECOND in user_block, user_block
    assert out["status"] == "complete", out


# --------------------------------------------------------------------------- #
# 5. The filed issue's transcript carries the exchange it complains about     #
# --------------------------------------------------------------------------- #
def test_R14_the_filed_issue_transcript_carries_the_previous_exchange(env):  # noqa: F811
    env.ready()
    env.created()
    _seed_done_turn(env, PREV_USER, PREV_BOT)
    _script(env, SECOND, type_="issue", has_idea=True, fields={"problem": COMPLAINT_PROBLEM},
            title="Assistant answer not satisfying")

    out = env.turn(SECOND)
    assert out["status"] == "complete", out
    (payload,) = env.create_calls
    transcript = payload.get("raw_transcript") or ""
    assert PREV_BOT in transcript, transcript
    assert PREV_USER in transcript, transcript
    assert SECOND in transcript, transcript


# --------------------------------------------------------------------------- #
# 6. The schema says it by meaning                                            #
# --------------------------------------------------------------------------- #
def test_R14_the_schema_counts_a_complaint_about_the_assistants_answer_as_a_problem():
    from app.services.ideation_extractor import IDEATE_EXTRACTION_JSON_SCHEMA as schema

    props = schema["properties"]
    described = " ".join(
        [
            props["has_idea"].get("description", ""),
            props["fields"].get("description", ""),
            props["fields"]["items"]["properties"]["key"].get("description", ""),
        ]
    ).lower()
    assert "assistant's answer" in described, described
    assert "not what" in described, described
