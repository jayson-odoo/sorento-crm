"""Gemini adapter tests for the document-extraction lane.

The adapter exists because document extraction is the one job where Gemini
measurably beat the alternatives on the client's own scan (52/52 line amounts,
the single strike-through, the handwriting) at a fraction of the token cost.
See PLAN-project-lead-to-so.md section 5b.

What is asserted here is the request `document_extraction.py` actually sends and
the handful of properties that lane depends on. The broad adapter surface
(thinking budgets, tool calling, schema translation, embeddings,
`test_connection`) is covered in `tests/test_llm_provider.py`; nothing is
duplicated here.

No network: `GeminiProvider._request` goes out over `httpx.request`, so that is
the seam a test substitutes, the same way the Gemini section of
`tests/test_llm_provider.py` does.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.llm_provider import GeminiProvider, ImagePart, get_provider


class _StubResponse:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload) if isinstance(payload, (dict, list)) else str(payload)

    def json(self):
        return self._payload


class _Transport:
    """Records every request and replays a canned response."""

    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code
        self.calls: list[dict[str, Any]] = []

    def __call__(self, method: str, url: str, **kwargs: Any) -> _StubResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        return _StubResponse(self.payload, self.status_code)

    @property
    def last(self) -> dict[str, Any]:
        return self.calls[-1]

    @property
    def body(self) -> dict[str, Any]:
        return self.calls[-1]["json"]


def _ok_body(text: str = '{"ok": true}') -> dict:
    return {
        "candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 7, "totalTokenCount": 18},
    }


def _install(monkeypatch, transport: _Transport) -> _Transport:
    monkeypatch.setattr("httpx.request", transport)
    return transport


@pytest.fixture()
def sent(monkeypatch) -> _Transport:
    """Swap the transport and record every request the provider makes."""
    return _install(monkeypatch, _Transport(_ok_body()))


def test_factory_resolves_gemini() -> None:
    provider = get_provider("gemini", "k", "gemini-2.5-flash")
    assert isinstance(provider, GeminiProvider)
    assert provider.name == "gemini"
    assert provider.default_model == "gemini-2.5-flash"


def test_chat_returns_normalized_result(sent: _Transport) -> None:
    result = GeminiProvider("k").chat([{"role": "user", "content": "hi"}])

    assert result.content == '{"ok": true}'
    assert (result.prompt_tokens, result.completion_tokens, result.total_tokens) == (11, 7, 18)
    assert result.tool_calls == []


def test_api_key_travels_in_the_header_not_the_url(sent: _Transport) -> None:
    """A key in the query string lands in logs and proxy access records."""
    GeminiProvider("secret-key").chat([{"role": "user", "content": "hi"}])

    assert "secret-key" not in sent.last["url"]
    assert sent.last["url"].endswith("/models/gemini-2.5-flash:generateContent")
    assert sent.last["headers"]["x-goog-api-key"] == "secret-key"


def test_temperature_and_max_tokens_are_forwarded(sent: _Transport) -> None:
    """A non-zero temperature reaches the request, and a flash answer budget is
    passed through untouched because flash thinks zero tokens."""
    GeminiProvider("k", default_model="gemini-2.5-flash").chat(
        [{"role": "user", "content": "hi"}], temperature=0.4, max_tokens=256
    )

    generation = sent.body["generationConfig"]
    assert generation["temperature"] == 0.4
    assert generation["maxOutputTokens"] == 256


def test_the_page_extraction_call_shape(sent: _Transport) -> None:
    """The exact request `document_extraction.render_pages` -> `chat` produces:
    one prompt, one page image, JSON forced, nothing else."""
    GeminiProvider("k").chat(
        [{"role": "user", "content": "read page 1"}],
        images=[ImagePart(mime="image/png", data_b64="QUJD")],
        temperature=0,
        response_format={"type": "json_object"},
    )

    payload = sent.body
    assert "systemInstruction" not in payload
    assert "tools" not in payload
    assert payload["generationConfig"]["responseMimeType"] == "application/json"
    assert "responseSchema" not in payload["generationConfig"]
    parts = payload["contents"][-1]["parts"]
    assert parts[0] == {"text": "read page 1"}
    assert parts[1] == {"inlineData": {"mimeType": "image/png", "data": "QUJD"}}


def test_multi_part_response_is_concatenated(monkeypatch) -> None:
    """Long structured output arrives split across parts, not as one string."""
    _install(
        monkeypatch,
        _Transport(
            {
                "candidates": [{"content": {"parts": [{"text": '{"a":'}, {"text": " 1}"}]}}],
                "usageMetadata": {},
            }
        ),
    )

    assert GeminiProvider("k").chat([{"role": "user", "content": "hi"}]).content == '{"a": 1}'


def test_a_truncated_candidate_comes_back_as_partial_content(monkeypatch) -> None:
    """MAX_TOKENS mid-JSON returns what the model managed to write rather than
    raising. The extraction lane relies on the JSON parse failing downstream
    (`document_extraction` records "the model's answer was not valid JSON" and
    keeps the raw text), so half a document is still reported as a bad page and
    never as a complete one."""
    _install(
        monkeypatch,
        _Transport(
            {
                "candidates": [
                    {
                        "content": {"parts": [{"text": '{"lines": [1,2'}]},
                        "finishReason": "MAX_TOKENS",
                    }
                ],
                "usageMetadata": {},
            }
        ),
    )

    result = GeminiProvider("k").chat([{"role": "user", "content": "hi"}])
    assert result.content == '{"lines": [1,2'
    with pytest.raises(json.JSONDecodeError):
        json.loads(result.content)


def test_an_over_quota_call_says_what_is_wrong_without_a_wall_of_json(monkeypatch) -> None:
    """A 429 is the operator's to fix, not the document's, and it used to reach the
    screen as a raw provider envelope that read like the file was unreadable. Only
    Google's own sentence and the status code survive into the message."""
    _install(
        monkeypatch,
        _Transport(
            {
                "error": {
                    "code": 429,
                    "status": "RESOURCE_EXHAUSTED",
                    "message": "Your project has exceeded its monthly spending cap.",
                }
            },
            status_code=429,
        ),
    )

    with pytest.raises(RuntimeError) as exc:
        GeminiProvider("k").chat([{"role": "user", "content": "hi"}])

    message = str(exc.value)
    assert "429" in message
    assert "monthly spending cap" in message
    assert "RESOURCE_EXHAUSTED" not in message
