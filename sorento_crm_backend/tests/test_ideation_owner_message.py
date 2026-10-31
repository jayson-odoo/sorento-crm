"""AGENTIC-IDEATE owner hand test round (AC-HT-1 to AC-HT-4).

The owner's own message, "I think we need to have sorento agentic ai", is the case in every test. Three things
went wrong on the copy: the extractor handed a key to the wrong provider, a failed extraction read as "no idea"
(so the bot asked, then gave up), and the router did not know the create tool by that sentence. No live
provider and no network: the provider is a stub patched at `get_provider`, shared service calls are the existing
fakes of test_ideation_capture_turn.py. Postgres only (blank schema).
"""
from __future__ import annotations

import json

import pytest

from app.services.ai_assistant_service import AIAssistantConfigService
from app.services.ideation_extractor import IdeateExtraction, extract_ideate_turn
from app.services.llm_provider import ChatResult
from tests._pg_fixture import blank_session
from tests.test_ideation_capture_turn import _no_ss, env  # noqa: F401 - the capture-turn harness and its fixture

OWNER = "I think we need to have sorento agentic ai"
PROBLEM_TEXT = "We need an agentic AI assistant in Sorento"
GEMINI_KEY = "ZZT-gemini-slot-key-1111"
OPENAI_KEY = "ZZT-openai-primary-key-2222"
ENV_OPENAI_KEY = "ZZT-env-openai-key-3333"

GOOD_PAYLOAD = {
    "fields": [{"key": "problem", "value": PROBLEM_TEXT}],
    "remove": [], "skip": [], "title": "Agentic AI for Sorento", "review_action": "none", "change_text": "",
    "duplicate_choice": "none", "use_cases": [], "has_idea": True,
}


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


class Recorder:
    """A stand-in for `get_provider` that remembers what it was built with."""

    def __init__(self, content=None, error=None):
        self.content = json.dumps(GOOD_PAYLOAD) if content is None else content
        self.error = error
        self.built: list[tuple[str, str]] = []

    def __call__(self, provider_name, api_key, model=None):
        self.built.append((provider_name, api_key))
        outer = self

        class _Provider:
            def chat(self, *_a, **_k):
                if outer.error is not None:
                    raise outer.error
                return ChatResult(content=outer.content, prompt_tokens=1, completion_tokens=1, total_tokens=2)

        return _Provider()


def configure(db, *, provider, primary="", gemini="", openai=""):
    cfg = AIAssistantConfigService(db).get()
    cfg.provider = provider
    cfg.model = "gemini-2.5-flash" if provider == "gemini" else "gpt-4o-mini"
    cfg.api_key_ciphertext = primary
    cfg.gemini_api_key_ciphertext = gemini
    cfg.openai_api_key_ciphertext = openai
    cfg.is_enabled = True
    db.commit()


@pytest.fixture()
def env_keys(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "openai_api_key", ENV_OPENAI_KEY)
    monkeypatch.setattr(settings, "gemini_api_key", "")


# ------------------------------------------------------------------ AC-HT-1 the key follows the provider


def test_AC_HT_1_a_gemini_assistant_with_only_a_gemini_key_builds_the_provider_with_that_key(db, env_keys, monkeypatch):
    configure(db, provider="gemini", primary="", gemini=GEMINI_KEY)
    rec = Recorder()
    monkeypatch.setattr("app.services.ideation_extractor.get_provider", rec)
    out = extract_ideate_turn(db, message_text=OWNER)
    assert rec.built == [("gemini", GEMINI_KEY)], rec.built
    assert out.fields.get("problem") == PROBLEM_TEXT


def test_AC_HT_1_an_openai_assistant_with_a_primary_key_still_gets_it(db, env_keys, monkeypatch):
    configure(db, provider="openai", primary=OPENAI_KEY)
    rec = Recorder()
    monkeypatch.setattr("app.services.ideation_extractor.get_provider", rec)
    out = extract_ideate_turn(db, message_text=OWNER)
    assert rec.built == [("openai", OPENAI_KEY)], rec.built
    assert out.fields.get("problem") == PROBLEM_TEXT


def test_AC_HT_1_a_key_for_another_provider_is_never_handed_over(db, env_keys, monkeypatch):
    configure(db, provider="gemini", primary="", gemini=GEMINI_KEY)
    rec = Recorder()
    monkeypatch.setattr("app.services.ideation_extractor.get_provider", rec)
    extract_ideate_turn(db, message_text=OWNER)
    assert all(key not in (ENV_OPENAI_KEY, OPENAI_KEY) for _, key in rec.built)


def test_AC_HT_1_the_denial_reply_call_resolves_the_key_the_same_way(db, env_keys, monkeypatch):
    from app.services import ideation_turn_service

    configure(db, provider="gemini", primary="", gemini=GEMINI_KEY)
    rec = Recorder(content="Sorry, you cannot use ideas.")
    monkeypatch.setattr(ideation_turn_service, "get_provider", rec)
    ideation_turn_service._call_ideate_reply_llm(db, user_message=OWNER)
    assert rec.built == [("gemini", GEMINI_KEY)], rec.built


# ------------------------------------------------------------------ AC-HT-2 a failure is not "no idea"


def test_AC_HT_2_a_provider_that_raises_is_a_failed_extraction(db, env_keys, monkeypatch):
    configure(db, provider="openai", primary=OPENAI_KEY)
    monkeypatch.setattr("app.services.ideation_extractor.get_provider", Recorder(error=RuntimeError("down")))
    assert extract_ideate_turn(db, message_text=OWNER).failed is True


def test_AC_HT_2_invalid_json_is_a_failed_extraction(db, env_keys, monkeypatch):
    configure(db, provider="openai", primary=OPENAI_KEY)
    monkeypatch.setattr("app.services.ideation_extractor.get_provider", Recorder(content="not json at all"))
    assert extract_ideate_turn(db, message_text=OWNER).failed is True


def test_AC_HT_2_no_key_is_a_failed_extraction(db, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    configure(db, provider="openai", primary="")
    rec = Recorder()
    monkeypatch.setattr("app.services.ideation_extractor.get_provider", rec)
    assert extract_ideate_turn(db, message_text=OWNER).failed is True
    assert rec.built == []


def test_AC_HT_2_a_prompt_that_cannot_render_is_a_failed_extraction(db, env_keys, monkeypatch):
    configure(db, provider="openai", primary=OPENAI_KEY)
    monkeypatch.setattr("app.services.ideation_extractor.get_provider", Recorder())

    def boom(*_a, **_k):
        raise RuntimeError("no prompt")

    monkeypatch.setattr("app.services.ideation_extractor.ai_prompt_registry.render", boom)
    assert extract_ideate_turn(db, message_text=OWNER).failed is True


def test_AC_HT_2_a_model_answer_of_no_idea_is_not_a_failure(db, env_keys, monkeypatch):
    configure(db, provider="openai", primary=OPENAI_KEY)
    payload = {**GOOD_PAYLOAD, "fields": [], "has_idea": False}
    monkeypatch.setattr("app.services.ideation_extractor.get_provider", Recorder(content=json.dumps(payload)))
    out = extract_ideate_turn(db, message_text="I have an idea")
    assert out.failed is False
    assert out.has_idea is False


def test_AC_HT_2_a_good_extraction_is_not_failed(db, env_keys, monkeypatch):
    configure(db, provider="openai", primary=OPENAI_KEY)
    monkeypatch.setattr("app.services.ideation_extractor.get_provider", Recorder())
    assert extract_ideate_turn(db, message_text=OWNER).failed is False


# ------------------------------------------------------------------ AC-HT-3 a failed extraction is said plainly


def failed_extraction():
    ex = IdeateExtraction()
    ex.failed = True  # set after construction so a missing field fails in the code under test
    return ex


def says_could_not_read(text_):
    low = (text_ or "").lower()
    return "read" in low or "understand" in low


@pytest.mark.parametrize("ask_reply", [False, True], ids=["first_message", "answer_to_the_ask"])
def test_AC_HT_3_a_failed_extraction_says_it_could_not_read_the_idea_and_creates_nothing(env, ask_reply):
    env.ready()
    env.extractions[OWNER] = failed_extraction()
    out = env.turn_ask(OWNER) if ask_reply else env.turn(OWNER)
    assert out["status"] == "extract_failed", out
    assert says_could_not_read(out["reply_text"]), out["reply_text"]
    kinds = [kind for kind, _facts, _msg in env.renders]
    assert "ask_idea" not in kinds and "ask_idea_gave_up" not in kinds, kinds
    _no_ss(env)
    assert not env.persisted().get("ideation")


def test_AC_HT_3_the_same_message_sent_again_is_read_fresh(env):
    env.ready()
    env.extractions[OWNER] = failed_extraction()
    assert env.turn(OWNER)["status"] == "extract_failed"
    working = IdeateExtraction(fields={"problem": PROBLEM_TEXT}, title="Agentic AI for Sorento")
    env.extractions[OWNER] = working
    env.created()
    assert env.turn(OWNER)["status"] == "complete"


def test_AC_HT_3_the_lane_opens_no_required_ask_for_a_failed_extraction(monkeypatch):
    from app.services.chatbot.lanes import ideate as ideate_mod

    monkeypatch.setattr(
        ideate_mod, "call_ideation_tool",
        lambda **kwargs: {"status": "extract_failed", "reply_text": "I could not read that.", "link": None,
                          "session_vars": {"ideation": None}},
    )
    ctx = {
        "parse": {"output": {}},
        "session": {"session_vars": {}},
        "text": {"message": {"message": {"text": OWNER}}},
        "contact": {"id": 4242, "firstName": "ZZT"},
    }
    out = ideate_mod.run(ctx, {})
    assert out.get("required_ask") is None


# ------------------------------------------------------------------ AC-HT-4 the verdict stays the model's


def test_AC_HT_4_a_working_extractor_creates_the_owners_idea_in_one_turn(env):
    env.ready()
    env.extractions[OWNER] = IdeateExtraction(fields={"problem": PROBLEM_TEXT}, title="Agentic AI for Sorento")
    env.created()
    out = env.turn(OWNER)
    assert out["status"] == "complete", out
    assert len(env.create_calls) == 1 and env.create_calls[0]["problem"] == PROBLEM_TEXT


def test_AC_HT_4_an_intent_only_message_still_asks_for_the_idea_and_a_second_one_gives_up(env):
    env.ready()
    intent_only = IdeateExtraction()
    intent_only.has_idea = False
    env.extractions["I have an idea"] = intent_only
    first = env.turn("I have an idea")
    assert first["status"] == "ask_idea", first
    again = env.turn_ask("I have an idea")
    assert again["status"] == "ask_idea_gave_up", again
    _no_ss(env)
