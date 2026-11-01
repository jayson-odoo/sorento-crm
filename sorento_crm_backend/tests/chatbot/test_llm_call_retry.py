"""A model call that hung or lost its connection is tried again, up to N times.

Owner, 1 Nov 2026: "Gemini timeout can retry up to N times with configurable."

Production, 29 Oct (masked): three parser calls failed "no answer from gemini within 20s"
on one-line stock asks and the contact was told to send it again. It is per request, not an
outage: a call started 11:44:02 hung for 20 s while the same dealer's call started 11:44:03
was answered. A normal parse takes 2.6-4.1 s.

The Gemini cases run the real `GeminiProvider` with only `httpx.request` faked, so the error
shapes are the provider's own. No key, no network.
"""
from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.config import settings
from app.services import llm_provider
from app.services.chatbot import llm_call
from app.services.chatbot.head import parser as parser_mod
from tests.chatbot.test_parser_max_tokens import _emission

MODEL = "gemini-3.5-flash-lite"
MESSAGES = [{"role": "user", "content": "check stock"}]


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture()
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(llm_call, "_monotonic", c)

    def _sleep(seconds: float) -> None:
        c.now += seconds

    monkeypatch.setattr(llm_call, "_sleep", _sleep)
    return c


def _retries(monkeypatch, n: Any) -> None:
    """The env var's effect (`CHATBOT_LLM_RETRIES`), set where a Settings field's value lives."""
    monkeypatch.setitem(settings.__dict__, "chatbot_llm_retries", n)


class Response:
    status_code = 200

    def __init__(self, text: str) -> None:
        self._text = text

    def json(self) -> dict:
        return {
            "candidates": [{"content": {"parts": [{"text": self._text}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1, "totalTokenCount": 2},
        }


class Wire:
    """`httpx.request`: raises each failure in turn, then answers. A failure eats the time a
    real one would: a timeout its whole attempt, a dropped connection none."""

    def __init__(self, clock: Clock, failures: list[Exception], text: str = "ok") -> None:
        self.clock = clock
        self.failures = list(failures)
        self.text = text
        self.timeouts: list[float] = []

    def __call__(self, method: str, url: str, **kwargs: Any) -> Response:
        self.timeouts.append(kwargs["timeout"])
        if self.failures:
            failure = self.failures.pop(0)
            if isinstance(failure, httpx.TimeoutException):
                self.clock.now += kwargs["timeout"]
            raise failure
        return Response(self.text)


def _wire(monkeypatch, clock: Clock, *failures: Exception, text: str = "ok") -> Wire:
    wire = Wire(clock, list(failures), text)
    monkeypatch.setattr(httpx, "request", wire)
    return wire


def _hang() -> Exception:
    return httpx.ReadTimeout("The read operation timed out")


def _drop(kind: type[httpx.TransportError] = httpx.RemoteProtocolError) -> Exception:
    return kind("Server disconnected without sending a response")


def _call():
    return llm_call.chat("gemini", "k", MODEL, MESSAGES)


# ---------------------------------------------------------------------- the owner's rule


def test_a_gemini_timeout_is_tried_again_and_the_contact_gets_the_answer(monkeypatch, clock) -> None:
    wire = _wire(monkeypatch, clock, _hang())
    assert _call().content == "ok"
    assert len(wire.timeouts) == 2


@pytest.mark.parametrize(
    "kind", [httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadError], ids=lambda k: k.__name__
)
def test_a_dropped_gemini_connection_is_tried_again(monkeypatch, clock, kind) -> None:
    wire = _wire(monkeypatch, clock, _drop(kind))
    assert _call().content == "ok"
    assert len(wire.timeouts) == 2


def test_n_limits_the_retries(monkeypatch, clock) -> None:
    _retries(monkeypatch, 2)
    wire = _wire(monkeypatch, clock, _drop(), _drop(), _drop())
    with pytest.raises(llm_call.RateLimited):
        _call()
    assert len(wire.timeouts) == 3


def test_n_above_the_old_four_attempts_is_honoured(monkeypatch, clock) -> None:
    """N is the rule, not the length of the backoff table."""
    _retries(monkeypatch, 5)
    monkeypatch.setattr(llm_call, "BACKOFF_SECONDS", (1.0,))
    wire = _wire(monkeypatch, clock, *[_drop() for _ in range(5)])
    assert _call().content == "ok"
    assert len(wire.timeouts) == 6


def test_n_zero_turns_the_retry_off(monkeypatch, clock) -> None:
    _retries(monkeypatch, 0)
    wire = _wire(monkeypatch, clock, _hang())
    with pytest.raises(llm_call.TimedOut):
        _call()
    assert len(wire.timeouts) == 1


def test_the_default_comes_from_config(monkeypatch, clock) -> None:
    assert isinstance(settings.chatbot_llm_retries, int)
    assert settings.chatbot_llm_retries >= 1


# ---------------------------------------------------------------------- inside the budget


def test_a_big_n_never_outruns_the_call_budget(monkeypatch, clock) -> None:
    _retries(monkeypatch, 10)
    started = clock.now
    wire = _wire(monkeypatch, clock, *[_hang() for _ in range(10)])
    with pytest.raises(llm_call.TimedOut) as caught:
        _call()
    assert clock.now - started <= llm_call.CALL_DEADLINE_SECONDS
    # 20 s, then the 15 s left: one retry is all a timeout can get out of 35 s.
    assert wire.timeouts == [pytest.approx(20.0, abs=0.5), pytest.approx(15.0, abs=0.5)]
    assert isinstance(caught.value, llm_call.RateLimited)


def test_a_retry_too_short_to_answer_is_not_started(monkeypatch, clock) -> None:
    """A normal parse takes 2.6-4.1 s, so 2 s left can only time out again."""
    wire = _wire(monkeypatch, clock, _hang())
    with pytest.raises(llm_call.TimedOut):
        llm_call.chat("gemini", "k", MODEL, MESSAGES, deadline_seconds=22.0)
    assert len(wire.timeouts) == 1


def test_a_retry_after_a_drop_waits_and_stays_inside_the_budget(monkeypatch, clock) -> None:
    started = clock.now
    _retries(monkeypatch, 50)
    wire = _wire(monkeypatch, clock, *[_drop() for _ in range(50)])
    with pytest.raises(llm_call.RateLimited):
        _call()
    assert clock.now - started <= llm_call.CALL_DEADLINE_SECONDS
    assert len(wire.timeouts) < 50


# ---------------------------------------------------------------------- what stays as it was


def test_a_gemini_400_is_not_retried(monkeypatch, clock) -> None:
    class Refused:
        status_code = 400
        text = '{"error": {"message": "Request contains an invalid argument."}}'

        def json(self) -> dict:
            return {"error": {"message": "Request contains an invalid argument."}}

    calls: list[Any] = []

    def request(method: str, url: str, **kwargs: Any) -> Refused:
        calls.append(url)
        return Refused()

    monkeypatch.setattr(httpx, "request", request)
    with pytest.raises(llm_provider.GeminiHTTPError):
        _call()
    assert len(calls) == 1


def test_a_gemini_answer_with_no_candidates_is_not_a_dropped_connection(monkeypatch, clock) -> None:
    """Gemini's other RuntimeErrors (a safety block, an empty candidate) are answers, and
    the same words come back on a retry."""

    class Blocked:
        status_code = 200

        def json(self) -> dict:
            return {"candidates": [], "promptFeedback": {"blockReason": "SAFETY"}}

    calls: list[Any] = []

    def request(method: str, url: str, **kwargs: Any) -> Blocked:
        calls.append(url)
        return Blocked()

    monkeypatch.setattr(httpx, "request", request)
    with pytest.raises(RuntimeError, match="no candidates"):
        _call()
    assert len(calls) == 1


# ---------------------------------------------------------------------- end to end, the parser


def test_the_parser_answers_after_one_timeout(monkeypatch, clock) -> None:
    """The production turn: a parse that used to fail `understood` now returns its emission.
    The context cache is left out: a hang on its create step is swallowed and is not this."""
    monkeypatch.setattr(llm_provider.GeminiProvider, "_cached_content", lambda *a, **k: None)
    wire = _wire(monkeypatch, clock, _hang(), text=_emission())
    config = parser_mod.ParserConfig(
        system_prompt="s", prompt_version=1, provider="gemini", model=MODEL, api_key="k"
    )
    assert parser_mod.parse(config, "block") is not None
    assert len(wire.timeouts) == 2


# ---------------------------------------------------------------------- what review found open


class APIConnectionError(Exception):
    """The OpenAI / Anthropic SDK's own class name for a dropped connection."""


class SdkProvider:
    def __init__(self, failures: list[Exception]) -> None:
        self.failures = list(failures)
        self.calls = 0

    def chat(self, messages, **kwargs):
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return llm_provider.ChatResult(content="ok", prompt_tokens=1, completion_tokens=1, total_tokens=2)


def test_a_dropped_sdk_connection_is_tried_again(monkeypatch, clock) -> None:
    provider = SdkProvider([APIConnectionError("Connection error.")])
    monkeypatch.setattr(llm_provider, "get_provider", lambda *a, **k: provider)
    assert llm_call.chat("openai", "k", "m", MESSAGES).content == "ok"
    assert provider.calls == 2


def test_n_zero_stops_a_dropped_sdk_connection_too(monkeypatch, clock) -> None:
    _retries(monkeypatch, 0)
    provider = SdkProvider([APIConnectionError("Connection error.")])
    monkeypatch.setattr(llm_provider, "get_provider", lambda *a, **k: provider)
    with pytest.raises(llm_call.RateLimited):
        llm_call.chat("openai", "k", "m", MESSAGES)
    assert provider.calls == 1


def test_the_real_limits_of_a_big_n_on_a_dropped_connection(monkeypatch, clock) -> None:
    """Said plainly, because `CHATBOT_LLM_RETRIES` reads as if N were the whole rule: with the
    real backoff and the 35 s budget a drop gets at most 4 retries, however big N is."""
    slept: list[float] = []
    real_sleep = llm_call._sleep

    def _sleep(seconds: float) -> None:
        slept.append(seconds)
        real_sleep(seconds)

    monkeypatch.setattr(llm_call, "_sleep", _sleep)
    _retries(monkeypatch, 50)
    wire = _wire(monkeypatch, clock, *[_drop() for _ in range(50)])
    with pytest.raises(llm_call.RateLimited):
        _call()
    assert slept == [2.0, 5.0, 10.0, 10.0]
    assert len(wire.timeouts) == 5


def test_the_default_is_three(monkeypatch) -> None:
    assert type(settings).model_fields["chatbot_llm_retries"].default == 3


@pytest.mark.real_casual_llm
def test_the_clarifier_keeps_the_one_attempt_it_always_had(monkeypatch, clock) -> None:
    """Budget: one turn can make a parser call and a clarifier call, and the queue cap
    (`dispatch.max_queue_wait_seconds`) counts one 35 s model call. A clarifier that fails
    has an honest canned reply to fall back on, so it does not spend a second 15 s."""
    from app.services.chatbot.lanes import casual

    seen: list[dict[str, Any]] = []

    def chat(provider, key, model, messages, **kwargs):
        seen.append(kwargs)
        raise llm_call.TimedOut("no answer")

    monkeypatch.setattr(llm_call, "chat", chat)
    config = casual.ClarifierConfig(system_prompt="s", prompt_version=1, provider="gemini", model=MODEL, api_key="k")
    with pytest.raises(casual.ClarifierRateLimited):
        casual.call_clarifier(config, "hello")
    assert seen[0].get("deadline_seconds") == llm_call.ATTEMPT_TIMEOUT_SECONDS


def test_every_model_call_but_the_parser_states_its_own_budget() -> None:
    """The queue cap counts ONE 35 s model call for a turn, and that one is the parser's. Any
    other call in a turn that took the default would add a second 35 s on top of it."""
    import ast
    from pathlib import Path

    import app.services.chatbot as package

    root = Path(package.__file__).parent
    unbudgeted: list[str] = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            base = node.func.value
            if node.func.attr != "chat" or not (isinstance(base, ast.Name) and base.id == "llm_call"):
                continue
            if path.name != "parser.py" and not any(k.arg == "deadline_seconds" for k in node.keywords):
                unbudgeted.append(f"{path.relative_to(root)}:{node.lineno}")
    assert unbudgeted == []
