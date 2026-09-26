"""The ONE seam every model call in a chatbot turn goes through: the semantic parser
(`head/parser.parse`, and so its recall re-parse) and the clarifier
(`lanes/casual.call_clarifier`). Nothing else in `app/services/chatbot` calls a provider.

Owner console test of round 4 (26 Sep 2026, PR #1247, ruling 3): two turns failed with
"Error code: 429 - Rate limit reached for gpt-5.4-mini ... tokens per min (TPM): Limit
200000, Used 200000" and that raw text went to the dealer. A rate limit is a wait, not a
failure: it is retried here with a growing backoff, inside the turn, honouring the
server's own "try again in Ns" when it gives one. Only when every attempt is refused does
the caller get `RateLimited`, and the caller then says `RATE_LIMITED_REPLY`, never the
provider's text (the operator still sees that on the turn row and the trace).

The OpenAI SDK retries a 429 twice on its own, over a second or two. A tokens-per-minute
limit clears over tens of seconds, which is why these waits are longer.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any

logger = logging.getLogger(__name__)

RATE_LIMITED_REPLY = "Sorry, I am busy right now, please send that again in a minute."

#: The wait before each retry, in seconds: four attempts in all.
BACKOFF_SECONDS = (2.0, 5.0, 10.0)
#: No single wait is longer than this, whatever the server asks for.
MAX_WAIT_SECONDS = 15.0
#: Nor do the waits add up to more than this: a dealer is waiting on the reply.
MAX_TOTAL_WAIT_SECONDS = 30.0

_RETRY_IN_RE = re.compile(r"try again in (\d+(?:\.\d+)?)\s*(ms|s)\b", re.IGNORECASE)

# The seam a test replaces, so no test sleeps.
_sleep = time.sleep


class RateLimited(RuntimeError):
    """Every attempt was refused with a rate limit. `str()` is the provider's last text."""


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


def _server_wait(exc: BaseException) -> float | None:
    match = _RETRY_IN_RE.search(str(exc))
    if not match:
        return None
    value = float(match.group(1))
    return value / 1000.0 if match.group(2).lower() == "ms" else value


def chat(provider: str, api_key: str, model: str, messages: list[dict], **kwargs: Any):
    """`get_provider(provider, api_key, model).chat(messages, model=model, **kwargs)`,
    with a rate limit waited out. Raises `RateLimited` when it never clears; any other
    error is raised as it came, on the first attempt."""
    from app.services.llm_provider import get_provider

    client = get_provider(provider, api_key, model)
    waited = 0.0
    for attempt, backoff in enumerate((*BACKOFF_SECONDS, None), 1):
        try:
            return client.chat(messages, model=model, **kwargs)
        except Exception as exc:  # noqa: BLE001 - inspected, then re-raised
            if not is_rate_limited(exc):
                raise
            wait = None
            if backoff is not None and not _quota_exhausted(exc):
                wait = min(max(backoff, _server_wait(exc) or 0.0), MAX_WAIT_SECONDS)
                if waited + wait > MAX_TOTAL_WAIT_SECONDS:
                    wait = None
            if wait is None:
                logger.warning("chatbot llm: rate limited on attempt %s, giving up", attempt)
                raise RateLimited(str(exc)) from exc
            logger.info("chatbot llm: rate limited on attempt %s, waiting %.1fs", attempt, wait)
            _sleep(wait)
            waited += wait
    raise AssertionError("unreachable")  # pragma: no cover - the loop always returns or raises
