"""Gemini adapter: the document-extraction guarantees.

The adapter exists because document extraction is the one job where Gemini
measurably beat the alternatives on the client's own scan (52/52 line amounts,
the single strike-through, the handwriting) at a fraction of the token cost.
See PLAN-project-lead-to-so.md section 5b.

The adapter itself (transport, tool calling, schema translation, thinking
budget, embeddings) is covered in ``test_llm_provider.py``. What is here is the
extraction lane's two demands on it, which are cheap to lose in a merge:

* a partial answer is never returned as if it were whole, and
* a quota wall or a rejected key names the operator rather than reading like an
  unreadable document.

No network: the seam is ``httpx.request``, the exact call ``_request`` makes.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.llm_provider import GeminiProvider, get_provider


class _StubHTTPResponse:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload) if isinstance(payload, (dict, list)) else str(payload)

    def json(self):
        return self._payload


def _install(monkeypatch, payload: Any, status_code: int = 200) -> list[dict]:
    """Swap the transport and record every request sent."""
    calls: list[dict] = []

    def _transport(method: str, url: str, **kwargs: Any) -> _StubHTTPResponse:
        calls.append({"method": method, "url": url, **kwargs})
        return _StubHTTPResponse(payload, status_code)

    monkeypatch.setattr("httpx.request", _transport)
    return calls


def _candidate(text: str, finish: str | None = "STOP") -> dict:
    candidate: dict[str, Any] = {"content": {"role": "model", "parts": [{"text": text}]}}
    if finish is not None:
        candidate["finishReason"] = finish
    return {"candidates": [candidate], "usageMetadata": {}}


# ---- the factory the extraction lane goes through -------------------------


def test_factory_resolves_gemini_and_defaults_to_flash() -> None:
    provider = get_provider("gemini", "k")

    assert isinstance(provider, GeminiProvider)
    assert provider.default_model == "gemini-2.5-flash"


# ---- a partial answer is never passed off as a whole one ------------------


def test_truncated_response_raises_rather_than_returning_half_a_document(monkeypatch) -> None:
    """MAX_TOKENS mid-JSON is the failure mode that silently drops PO lines.

    The text that came back is real, so nothing downstream can tell it is half
    a document; only the finish reason says so.
    """
    _install(monkeypatch, _candidate('{"lines": [1,2', finish="MAX_TOKENS"))

    with pytest.raises(RuntimeError, match="MAX_TOKENS"):
        GeminiProvider("k").chat([{"role": "user", "content": "hi"}])


def test_a_candidate_cut_short_by_safety_raises_with_its_reason(monkeypatch) -> None:
    _install(monkeypatch, _candidate("partial", finish="RECITATION"))

    with pytest.raises(RuntimeError, match="RECITATION"):
        GeminiProvider("k").chat([{"role": "user", "content": "hi"}])


def test_a_completed_answer_still_comes_back(monkeypatch) -> None:
    """The guard above must not fire on the normal path."""
    _install(monkeypatch, _candidate('{"ok": true}'))

    assert GeminiProvider("k").chat([{"role": "user", "content": "hi"}]).content == '{"ok": true}'


def test_an_answer_with_no_finish_reason_is_accepted(monkeypatch) -> None:
    """Not every response carries one, and absence is not truncation."""
    _install(monkeypatch, _candidate("plain text", finish=None))

    assert GeminiProvider("k").chat([{"role": "user", "content": "hi"}]).content == "plain text"


# ---- a wall the operator can act on, not a wall of provider JSON ----------


def test_a_billing_cap_reads_as_an_operator_problem_not_a_bad_document(monkeypatch) -> None:
    """A 429 used to reach the screen as raw provider JSON, which reads like the
    file could not be understood. It is the billing cap, nobody's document is at
    fault, and the person looking at it needs to know nothing was lost."""
    _install(
        monkeypatch,
        {"error": {"message": "exceeded its monthly spending cap"}},
        status_code=429,
    )

    with pytest.raises(RuntimeError) as exc:
        GeminiProvider("k").chat([{"role": "user", "content": "hi"}])

    message = str(exc.value)
    assert "billing cap" in message
    assert "Nothing uploaded is lost" in message
    # Gemini's own words survive too - they are what separates one 429 from another.
    assert "spending cap" in message


def test_a_plain_rate_limit_does_not_claim_the_cap_was_hit(monkeypatch) -> None:
    _install(monkeypatch, {"error": {"message": "Quota exceeded, retry later"}}, status_code=429)

    with pytest.raises(RuntimeError) as exc:
        GeminiProvider("k").chat([{"role": "user", "content": "hi"}])

    assert "rate limit has been reached" in str(exc.value)


def test_a_rejected_key_says_whose_problem_it_is(monkeypatch) -> None:
    _install(monkeypatch, {"error": {"message": "API key not valid"}}, status_code=403)

    with pytest.raises(RuntimeError) as exc:
        GeminiProvider("k").chat([{"role": "user", "content": "hi"}])

    message = str(exc.value)
    assert "rejected our key" in message
    assert "GEMINI_API_KEY" in message
    assert "API key not valid" in message


def test_an_ordinary_failure_gets_no_invented_advice(monkeypatch) -> None:
    """We only name an owner where we actually know one."""
    _install(monkeypatch, {"error": {"message": "model not found"}}, status_code=404)

    with pytest.raises(RuntimeError) as exc:
        GeminiProvider("k").chat([{"role": "user", "content": "hi"}])

    message = str(exc.value)
    assert "model not found" in message
    assert "Nothing uploaded is lost" not in message
