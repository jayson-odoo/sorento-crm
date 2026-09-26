"""PR #1247 round 6, owner console test of round 4 (26 Sep 2026 08:18Z to 08:21Z):
"why rate limit is reached? why when i say tia also rate limit reached?"

Observed: two turns (08:19:37, 08:20:29) FAILED and sent the dealer the raw provider
text "There is some error encountered by the AI: Error code: 429 - Rate limit reached
for gpt-5.4-mini ... tokens per min (TPM): Limit 200000, Used 200000" (ClarifierError).
The owner's "tia" hit the same.

Rulings:
3. A 429 never reaches the user as raw error text and never fails silently: it is
   retried with backoff inside the turn, and on final failure the reply is one short
   plain sentence. ONE wrapper for every model call the chatbot makes in a turn
   (`chatbot/llm_call.py`): the parser, its recall re-parse, and the clarifier.
Ruling 4 (a small-talk fast path) was DROPPED by the owner on 26 Sep ~08:33Z ("the tia
is a typo of tiga so it supposed to pass through parser"); its tests went with it in
round 7 (`test_stock_ask_ht26_r7_every_turn_parsed.py` holds the "tia" replay).

Nothing here reaches a real model: the provider is a stub that raises the OpenAI SDK's
own `RateLimitError` shape (`status_code` 429 and the SDK's message text).
"""
from __future__ import annotations

from typing import Any

import pytest

from app.services.chatbot import engine as engine_mod
from app.services.chatbot import llm_call
from app.services.chatbot.head import parser as parser_mod
from app.services.chatbot.lanes import casual
from app.services.llm_provider import ChatResult

from tests.chatbot.test_s4_casual_lane import low_signal_enabled  # noqa: F401 - fixture
from tests.chatbot.test_engine import (  # noqa: F401 - fixtures used by name
    CONTACT_ID,
    _envelope,
    _parser_output,
    _turn_row,
    seeded,
    stub_access,
    stub_parser,
)

OWNER_429 = (
    "Error code: 429 - {'error': {'message': 'Rate limit reached for gpt-5.4-mini in "
    "organization org-x on tokens per min (TPM): Limit 200000, Used 200000, Requested "
    "25385. Please try again in 7.615s. Visit https://platform.openai.com/account/"
    "rate-limits to learn more.', 'type': 'tokens', 'param': None, 'code': "
    "'rate_limit_exceeded'}}"
)


class RateLimitError(Exception):
    """The OpenAI SDK's own class name and shape: `status_code` 429, the server's text."""

    status_code = 429


class Provider:
    """`get_provider(...)`'s stand-in: fails `fail` times with a 429, then answers."""

    def __init__(self, fail: int, content: str = "{}", error: Exception | None = None):
        self.fail = fail
        self.calls = 0
        self.content = content
        self.error = error

    def chat(self, messages, **kwargs):
        self.calls += 1
        if self.calls <= self.fail:
            raise self.error or RateLimitError(OWNER_429)
        return ChatResult(content=self.content, prompt_tokens=10, completion_tokens=2, total_tokens=12)


@pytest.fixture()
def slept(monkeypatch):
    waits: list[float] = []
    monkeypatch.setattr(llm_call, "_sleep", waits.append)
    return waits


def _install(monkeypatch, provider: Provider) -> None:
    import app.services.llm_provider as llm_provider

    monkeypatch.setattr(llm_provider, "get_provider", lambda *a, **k: provider)


# --------------------------------------------------------------------------- #
# Ruling 3: one wrapper, retried with backoff
# --------------------------------------------------------------------------- #


def test_a_429_is_retried_with_backoff_and_then_answers(monkeypatch, slept):
    provider = Provider(fail=2, content="hello")
    _install(monkeypatch, provider)
    result = llm_call.chat("openai", "sk", "m", [{"role": "user", "content": "x"}])
    assert result.content == "hello"
    assert provider.calls == 3
    assert len(slept) == 2
    # The server said "try again in 7.615s", and each wait honours at least that.
    assert all(wait >= 7.615 for wait in slept)
    assert all(wait <= llm_call.MAX_WAIT_SECONDS for wait in slept)


def test_the_waits_grow_when_the_server_names_no_time(monkeypatch, slept):
    provider = Provider(fail=3, content="ok", error=RateLimitError("Error code: 429 - slow down"))
    _install(monkeypatch, provider)
    llm_call.chat("openai", "sk", "m", [])
    assert slept == list(llm_call.BACKOFF_SECONDS)
    assert slept == sorted(slept) and slept[0] < slept[-1]


def test_a_429_that_never_clears_raises_rate_limited(monkeypatch, slept):
    provider = Provider(fail=99)
    _install(monkeypatch, provider)
    with pytest.raises(llm_call.RateLimited):
        llm_call.chat("openai", "sk", "m", [])
    assert provider.calls == len(llm_call.BACKOFF_SECONDS) + 1
    assert sum(slept) <= llm_call.MAX_TOTAL_WAIT_SECONDS


def test_an_exhausted_quota_is_not_waited_on(monkeypatch, slept):
    """A 429 that says the account is out of credit will not clear in a minute."""
    provider = Provider(
        fail=99, error=RateLimitError("Error code: 429 - {'code': 'insufficient_quota'}")
    )
    _install(monkeypatch, provider)
    with pytest.raises(llm_call.RateLimited):
        llm_call.chat("openai", "sk", "m", [])
    assert provider.calls == 1 and slept == []


def test_any_other_error_is_not_retried(monkeypatch, slept):
    provider = Provider(fail=1, error=ValueError("bad request"))
    _install(monkeypatch, provider)
    with pytest.raises(ValueError):
        llm_call.chat("openai", "sk", "m", [])
    assert provider.calls == 1 and slept == []


def test_the_parser_call_goes_through_the_wrapper(monkeypatch, slept):
    provider = Provider(fail=1, content='{"x": 1}')
    _install(monkeypatch, provider)
    monkeypatch.setattr(parser_mod, "assert_emission", lambda emission: None)
    config = parser_mod.ParserConfig(
        system_prompt="s", prompt_version=1, provider="openai", model="m", api_key="k"
    )
    assert dict(parser_mod.parse(config, "block")) == {"x": 1}
    assert provider.calls == 2


def test_the_parser_names_a_final_rate_limit(monkeypatch, slept):
    _install(monkeypatch, Provider(fail=99))
    config = parser_mod.ParserConfig(
        system_prompt="s", prompt_version=1, provider="openai", model="m", api_key="k"
    )
    with pytest.raises(parser_mod.ParserError) as caught:
        parser_mod.parse(config, "block")
    assert caught.value.rate_limited is True


@pytest.mark.real_casual_llm
def test_the_clarifier_call_goes_through_the_wrapper(monkeypatch, slept):
    provider = Provider(fail=1, content='{"response": "You are welcome"}')
    _install(monkeypatch, provider)
    config = casual.ClarifierConfig(
        system_prompt="s", prompt_version=1, provider="openai", model="m", api_key="k"
    )
    assert casual.call_clarifier(config, "u") == '{"response": "You are welcome"}'
    assert provider.calls == 2


@pytest.mark.real_casual_llm
def test_the_clarifier_raises_its_own_rate_limited_error(monkeypatch, slept):
    _install(monkeypatch, Provider(fail=99))
    config = casual.ClarifierConfig(
        system_prompt="s", prompt_version=1, provider="openai", model="m", api_key="k"
    )
    with pytest.raises(casual.ClarifierRateLimited):
        casual.call_clarifier(config, "u")


def test_no_chatbot_module_calls_a_provider_outside_the_wrapper():
    """ONE wrapper: every `provider.chat(` in the chatbot package is inside `llm_call`."""
    import re
    from pathlib import Path

    import app.services.chatbot as package

    root = Path(package.__file__).parent
    call = re.compile(r"get_provider\(|(?<!llm_call)\.chat\(")
    offenders = [
        str(path.relative_to(root))
        for path in root.rglob("*.py")
        if path.name != "llm_call.py" and call.search(path.read_text())
    ]
    assert offenders == []


def _message(text: str) -> dict[str, Any]:
    return {
        "event_type": "message.received",
        "contact": {"id": CONTACT_ID},
        "message": {
            "messageId": f"ZZT-msg-{abs(hash(text))}",
            "contactId": CONTACT_ID,
            "channelId": "whatsapp",
            "traffic": "incoming",
            "message": {"type": "text", "text": text},
        },
    }


# --------------------------------------------------------------------------- #
# Ruling 3, at the turn: the dealer reads one plain sentence
# --------------------------------------------------------------------------- #


def test_a_parser_rate_limit_replies_with_the_plain_sentence(
    session_factory, seeded, stub_parser, stub_access
):
    stub_parser(error=parser_mod.ParserError(f"parser provider call failed: {OWNER_429}", rate_limited=True))
    stub_access()
    result = engine_mod.run_turn(_envelope(), session_factory=session_factory)
    assert result.reply["text"] == llm_call.RATE_LIMITED_REPLY
    assert "429" not in result.reply["text"] and "error" not in result.reply["text"].lower()
    assert [a["text"] for a in result.actions if a["kind"] == "send_message"] == [
        llm_call.RATE_LIMITED_REPLY
    ]
    row = _turn_row(session_factory, result.turn_id)
    assert row.status == "failed" and "429" in row.error, "the operator still sees why"


def test_a_clarifier_rate_limit_replies_with_the_plain_sentence(
    session_factory, seeded, stub_parser, stub_access, monkeypatch, low_signal_enabled
):
    stub_parser(_parser_output(message_type="casual", domain_hint=None, intent_hint=None, entities=[]))
    stub_access()
    monkeypatch.setattr(casual, "resolve_for_prompt", lambda db, *, ctx: {"resolutions": []})
    monkeypatch.setattr(casual, "resolve_clarifier_config", lambda db, **_: object())

    def limited(config, user_prompt):
        raise casual.ClarifierRateLimited(OWNER_429)

    monkeypatch.setattr(casual, "call_clarifier", limited)
    result = engine_mod.run_turn(
        _envelope(message=_message("what can you do")), session_factory=session_factory
    )
    assert result.reply["text"] == llm_call.RATE_LIMITED_REPLY
    assert not result.reply["text"].startswith(casual.CLARIFIER_ERROR_PREFIX)
    row = _turn_row(session_factory, result.turn_id)
    assert row.status == "failed" and row.stage == "casual_llm" and "429" in row.error


def test_the_rate_limited_reply_has_no_dashes():
    assert chr(0x2014) not in llm_call.RATE_LIMITED_REPLY and chr(0x2013) not in llm_call.RATE_LIMITED_REPLY
