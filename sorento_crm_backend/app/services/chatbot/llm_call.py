"""The ONE seam every model call in a chatbot turn goes through: the semantic parser
(`head/parser.parse`, and so its recall re-parse), the clarifier
(`lanes/casual.call_clarifier`) and the nightly topic labeller (`analytics/labeller`).
Nothing else in `app/services/chatbot` calls a provider.

Owner console test of round 4 (26 Sep 2026, PR #1247, ruling 3): two turns failed with
"Error code: 429 - Rate limit reached for gpt-5.4-mini ... tokens per min (TPM): Limit
200000, Used 200000" and that raw text went to the dealer. A rate limit is a wait, not a
failure: it is retried here with a growing backoff, inside the turn, honouring the
server's own "try again in Ns" when it gives one. Only when every attempt is refused does
the caller get `RateLimited`, and the caller then says its own honest sentence, never the
provider's text (the operator still sees that on the turn row and the trace): a parser
that did not answer says "our AI service did not answer" (`CHATBOT_REPLY_AI_DID_NOT_ANSWER`),
a clarifier sends the canned offer (CHATBOT-FAIL-TRIAGE, owner 30 Oct 2026).

A tokens-per-minute limit clears over tens of seconds, which is why these waits are long.

CHATBOT-QUEUE-FIX (prod 1 Oct, turn a45f): the parser call had NO timeout. The SDK default
is 600 s with two silent retries, and one call took 230 s while the contact's queue slot
waited on it. Every attempt now carries `ATTEMPT_TIMEOUT_SECONDS` with the SDK's own retries
off (this loop is the only retry), and the whole call, backoff included, stops at
`CALL_DEADLINE_SECONDS`. A timeout raises `TimedOut`, which IS a `RateLimited`: to the dealer
both mean "the model did not answer, send that again", so every caller answers a hang the
way it answers a 429, and the row keeps the real reason. With the SDK
retries off, a 5xx / 529 (`is_transient`) is retried here on the same backoff as a 429, and
ends the same way.

CHATBOT-FAIL-REVIEW (owner, 1 Nov 2026: "Gemini timeout can retry up to N times with
configurable"): a timeout or a dropped connection is tried again up to `CHATBOT_LLM_RETRIES`
times, inside the same budget. It used to end the turn on the first timeout, on the reasoning
that a provider that hung was not answering this turn. Production says otherwise: on 29 Oct a
call started 11:44:02 hung for 20 s while the same dealer's call started 11:44:03 was answered.
"""
from __future__ import annotations

import contextvars
import logging
import re
import time
from contextlib import contextmanager
from typing import Any, Iterator

import httpx

from app.config import settings
from app.services.llm_provider import is_timeout  # noqa: F401 - re-exported, callers import it from here

logger = logging.getLogger(__name__)

# RETIRED from every reply path (CHATBOT-FAIL-TRIAGE, owner 30 Oct 2026: never "Sorry, I am
# busy"). No caller sends it; kept only as the banned text the tests check replies against.
RATE_LIMITED_REPLY = "Sorry, I am busy right now, please send that again in a minute."

#: The wait before each retry after a rate limit or an outage, in seconds. A dropped
#: connection walks the same list and then stays on its last value.
BACKOFF_SECONDS = (2.0, 5.0, 10.0)
#: No single wait is longer than this, whatever the server asks for.
MAX_WAIT_SECONDS = 15.0
#: Nor do the waits add up to more than this: a dealer is waiting on the reply.
MAX_TOTAL_WAIT_SECONDS = 30.0

#: One attempt's wall clock. A normal parse answers in 2.6-4.1 s (prod trace, 1 Oct).
ATTEMPT_TIMEOUT_SECONDS = 20.0
#: The whole call, every attempt and wait included. Well under n8n's 90 s turn budget
#: (`send_order.N8N_CHAT_TURN_TIMEOUT_SECONDS`).
CALL_DEADLINE_SECONDS = 35.0
#: An attempt with less than this left is not started: it could only time out.
MIN_ATTEMPT_SECONDS = 1.0
#: Nor is a retry after a lost answer with less than this: a normal parse takes 2.6-4.1 s.
MIN_RETRY_SECONDS = 5.0

_RETRY_IN_RE = re.compile(r"try again in (\d+(?:\.\d+)?)\s*(ms|s)\b", re.IGNORECASE)

# CHAT-TURN-COST: the usage of each answered call inside a `capture_usage()` block. A
# caller whose call returns only the content (the clarifier) bills the turn from here.
_captured: contextvars.ContextVar[list[dict] | None] = contextvars.ContextVar("chatbot_llm_usage", default=None)


@contextmanager
def capture_usage() -> Iterator[list[dict]]:
    """Collect `{provider, model, prompt_tokens, completion_tokens, total_tokens,
    cached_tokens}` for every call `chat` answers inside the block."""
    calls: list[dict] = []
    token = _captured.set(calls)
    try:
        yield calls
    finally:
        _captured.reset(token)


def _capture(provider: str, model: str, result: Any) -> None:
    calls = _captured.get()
    if calls is None:
        return
    calls.append(
        {
            "provider": provider,
            "model": model,
            "prompt_tokens": int(getattr(result, "prompt_tokens", 0) or 0),
            "completion_tokens": int(getattr(result, "completion_tokens", 0) or 0),
            "total_tokens": int(getattr(result, "total_tokens", 0) or 0),
            "cached_tokens": int(getattr(result, "cached_tokens", 0) or 0),
        }
    )


# The seams a test replaces, so no test sleeps or waits on a real clock.
_sleep = time.sleep
_monotonic = time.monotonic


class RateLimited(RuntimeError):
    """Every attempt was refused with a rate limit. `str()` is the provider's last text."""


class TimedOut(RateLimited):
    """The provider did not answer inside the call's time budget. A `RateLimited` on
    purpose: the dealer's reply is the same "busy, send that again" (see module doc)."""


def is_rate_limited(exc: BaseException) -> bool:
    """A 429, however the provider's SDK spells it."""
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    if status == 429 or type(exc).__name__ == "RateLimitError":
        return True
    text = str(exc).lower()
    return "error code: 429" in text or "rate limit reached" in text


def _quota_exhausted(exc: BaseException) -> bool:
    """A 429 that means the account is out of credit, which no wait will clear."""
    return "insufficient_quota" in str(exc)


def is_transient(exc: BaseException) -> bool:
    """A provider-side blip the SDK used to retry on its own before its retries were
    turned off: a 5xx or Anthropic's 529 "overloaded". A dropped connection is
    `is_dropped_connection`, counted against `CHATBOT_LLM_RETRIES`."""
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(status, int) and status >= 500:
        return True
    return type(exc).__name__ in {"InternalServerError", "OverloadedError"}


def is_dropped_connection(exc: BaseException) -> bool:
    """The connection failed before any answer came: an SDK's `APIConnectionError`, or
    Gemini's RuntimeError wrapping httpx's own error. Walks the `from` chain as `is_timeout`
    does, because Gemini re-raises; its other RuntimeErrors (a safety block, an empty
    candidate) carry no such cause, and they are answers a retry would only repeat."""
    seen = 0
    current: BaseException | None = exc
    while current is not None and seen < 5:
        if type(current).__name__ == "APIConnectionError" or isinstance(current, httpx.TransportError):
            return True
        current = current.__cause__
        seen += 1
    return False


def _retries() -> int:
    return max(0, settings.chatbot_llm_retries)


def _server_wait(exc: BaseException) -> float | None:
    match = _RETRY_IN_RE.search(str(exc))
    if not match:
        return None
    value = float(match.group(1))
    return value / 1000.0 if match.group(2).lower() == "ms" else value


def chat(
    provider: str,
    api_key: str,
    model: str,
    messages: list[dict],
    *,
    deadline_seconds: float = CALL_DEADLINE_SECONDS,
    **kwargs: Any,
):
    """`get_provider(provider, api_key, model).chat(messages, model=model, **kwargs)`,
    with a rate limit waited out, a timeout or dropped connection tried again up to
    `CHATBOT_LLM_RETRIES` times, and a hard time budget. Raises `RateLimited` when a rate
    limit never clears or the connection stays down, `TimedOut` when the retries or the
    budget run out; any other error is raised as it came, on the first attempt. `deadline_seconds` widens the budget only for a caller
    no dealer is waiting on (the nightly topic labeller)."""
    from app.services.llm_provider import get_provider

    client = get_provider(provider, api_key, model)
    started = _monotonic()
    deadline = started + deadline_seconds
    waited = 0.0
    backoffs = iter(BACKOFF_SECONDS)
    retries_left = _retries()
    attempt = 0
    while True:
        attempt += 1
        remaining = deadline - _monotonic()
        if remaining < MIN_ATTEMPT_SECONDS:
            logger.error(
                "chatbot llm: %s/%s out of time before attempt %s", provider, model, attempt
            )
            raise TimedOut(f"no answer from {provider} within {deadline_seconds:.0f}s")
        timeout = min(float(kwargs.get("timeout") or ATTEMPT_TIMEOUT_SECONDS), remaining)
        try:
            result = client.chat(messages, model=model, **{**kwargs, "timeout": timeout})
            _capture(provider, model, result)
            return result
        except Exception as exc:  # noqa: BLE001 - inspected, then re-raised
            timed_out = is_timeout(exc)
            if timed_out or is_dropped_connection(exc):
                # A hang has already spent its time, so it goes straight back. A drop fails
                # fast, so it waits the same backoff as any other transient error.
                wait = 0.0 if timed_out else next(backoffs, BACKOFF_SECONDS[-1])
                if retries_left > 0 and deadline - (_monotonic() + wait) >= MIN_RETRY_SECONDS:
                    retries_left -= 1
                    logger.warning(
                        "chatbot llm: %s/%s %s on attempt %s, trying again",
                        provider,
                        model,
                        "timed out" if timed_out else "lost its connection",
                        attempt,
                    )
                    _sleep(wait)
                    waited += wait
                    continue
                logger.error(
                    "chatbot llm: %s/%s %s on attempt %s, giving up after %.1fs",
                    provider,
                    model,
                    "timed out" if timed_out else "lost its connection",
                    attempt,
                    _monotonic() - started,
                )
                if timed_out:
                    raise TimedOut(
                        f"no answer from {provider} within {_monotonic() - started:.0f}s "
                        f"after {attempt} attempt(s) ({exc})"
                    ) from exc
                raise RateLimited(str(exc)) from exc
            transient = is_transient(exc)
            if not transient and not is_rate_limited(exc):
                raise
            backoff = next(backoffs, None)
            wait = None
            if backoff is not None and not _quota_exhausted(exc):
                wait = min(max(backoff, _server_wait(exc) or 0.0), MAX_WAIT_SECONDS)
                if waited + wait > MAX_TOTAL_WAIT_SECONDS:
                    wait = None
                elif deadline - (_monotonic() + wait) < MIN_ATTEMPT_SECONDS:
                    wait = None
            reason = "unavailable" if transient else "rate limited"
            if wait is None:
                # A provider that stayed unavailable is told to the dealer the same way
                # as a rate limit that never cleared: busy, send that again.
                logger.warning("chatbot llm: %s on attempt %s, giving up", reason, attempt)
                raise RateLimited(str(exc)) from exc
            logger.info("chatbot llm: %s on attempt %s, waiting %.1fs", reason, attempt, wait)
            _sleep(wait)
            waited += wait
