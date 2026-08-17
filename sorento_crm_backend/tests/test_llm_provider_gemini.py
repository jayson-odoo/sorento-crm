"""Gemini adapter tests.

The adapter exists because document extraction is the one job where Gemini
measurably beat the alternatives on the client's own scan (52/52 line amounts,
the single strike-through, the handwriting) at a fraction of the token cost.
See PLAN-project-lead-to-so.md section 5b.

No network here: the transport is a module-level function so a test can
substitute it and assert on the exact request body we send.
"""
from __future__ import annotations

import io

import pytest

from app.services import llm_provider as mod
from app.services.llm_provider import GeminiProvider, ImagePart, get_provider


def _ok_body(text: str = '{"ok": true}') -> dict:
    return {
        "candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 7, "totalTokenCount": 18},
    }


@pytest.fixture()
def captured(monkeypatch):
    """Swap the transport and record every (url, payload) pair sent."""
    calls: list[tuple[str, dict]] = []

    def _fake(url: str, payload: dict, *, api_key: str, timeout: int = 180) -> dict:
        calls.append((url, payload))
        return _ok_body()

    monkeypatch.setattr(mod, "_gemini_post", _fake)
    return calls


def test_factory_resolves_gemini() -> None:
    provider = get_provider("gemini", "k", "gemini-2.5-flash")
    assert isinstance(provider, GeminiProvider)
    assert provider.name == "gemini"
    assert provider.default_model == "gemini-2.5-flash"


def test_factory_defaults_to_flash() -> None:
    assert get_provider("gemini", "k").default_model == "gemini-2.5-flash"


def test_chat_returns_normalized_result(captured) -> None:
    result = GeminiProvider("k").chat([{"role": "user", "content": "hi"}])

    assert result.content == '{"ok": true}'
    assert (result.prompt_tokens, result.completion_tokens, result.total_tokens) == (11, 7, 18)
    assert result.tool_calls == []


def test_api_key_travels_in_the_header_not_the_url(captured) -> None:
    """A key in the query string lands in logs and proxy access records."""
    GeminiProvider("secret-key").chat([{"role": "user", "content": "hi"}])

    url, _ = captured[0]
    assert "secret-key" not in url
    assert url.endswith("/models/gemini-2.5-flash:generateContent")


def test_system_message_becomes_system_instruction(captured) -> None:
    GeminiProvider("k").chat(
        [{"role": "system", "content": "be terse"}, {"role": "user", "content": "hi"}]
    )

    _, payload = captured[0]
    assert payload["systemInstruction"]["parts"] == [{"text": "be terse"}]
    assert [c["role"] for c in payload["contents"]] == ["user"]


def test_assistant_role_maps_to_model(captured) -> None:
    GeminiProvider("k").chat(
        [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
            {"role": "user", "content": "c"},
        ]
    )

    _, payload = captured[0]
    assert [c["role"] for c in payload["contents"]] == ["user", "model", "user"]


def test_images_attach_to_the_last_user_turn(captured) -> None:
    GeminiProvider("k").chat(
        [{"role": "user", "content": "page 1"}],
        images=[ImagePart(mime="image/png", data_b64="QUJD")],
    )

    _, payload = captured[0]
    parts = payload["contents"][-1]["parts"]
    assert parts[0] == {"text": "page 1"}
    assert parts[1] == {"inline_data": {"mime_type": "image/png", "data": "QUJD"}}


def test_json_schema_forces_structured_output(captured) -> None:
    schema = {"type": "object", "properties": {"n": {"type": "integer"}}}
    GeminiProvider("k").chat([{"role": "user", "content": "hi"}], json_schema=schema)

    _, payload = captured[0]
    cfg = payload["generationConfig"]
    assert cfg["responseMimeType"] == "application/json"
    assert cfg["responseSchema"] == schema


def test_json_object_response_format_asks_for_json_without_a_schema(captured) -> None:
    GeminiProvider("k").chat(
        [{"role": "user", "content": "hi"}], response_format={"type": "json_object"}
    )

    _, payload = captured[0]
    assert payload["generationConfig"]["responseMimeType"] == "application/json"
    assert "responseSchema" not in payload["generationConfig"]


def test_temperature_and_max_tokens_are_forwarded(captured) -> None:
    GeminiProvider("k").chat([{"role": "user", "content": "hi"}], temperature=0.4, max_tokens=256)

    _, payload = captured[0]
    assert payload["generationConfig"]["temperature"] == 0.4
    assert payload["generationConfig"]["maxOutputTokens"] == 256


def test_model_override_beats_the_default(captured) -> None:
    GeminiProvider("k", default_model="gemini-2.5-flash").chat(
        [{"role": "user", "content": "hi"}], model="gemini-2.5-pro"
    )

    url, _ = captured[0]
    assert url.endswith("/models/gemini-2.5-pro:generateContent")


def test_multi_part_response_is_concatenated(monkeypatch) -> None:
    """Long structured output arrives split across parts, not as one string."""
    monkeypatch.setattr(
        mod,
        "_gemini_post",
        lambda url, payload, api_key="", timeout=180: {
            "candidates": [{"content": {"parts": [{"text": '{"a":'}, {"text": " 1}"}]}}],
            "usageMetadata": {},
        },
    )

    assert GeminiProvider("k").chat([{"role": "user", "content": "hi"}]).content == '{"a": 1}'


def test_blocked_prompt_raises_with_the_reason(monkeypatch) -> None:
    """A safety block returns 200 with no candidate. Silence would look like an empty PO."""
    monkeypatch.setattr(
        mod,
        "_gemini_post",
        lambda url, payload, api_key="", timeout=180: {"promptFeedback": {"blockReason": "SAFETY"}},
    )

    with pytest.raises(RuntimeError, match="SAFETY"):
        GeminiProvider("k").chat([{"role": "user", "content": "hi"}])


def test_truncated_response_raises_rather_than_returning_half_a_document(monkeypatch) -> None:
    """MAX_TOKENS mid-JSON is the failure mode that silently drops PO lines."""
    monkeypatch.setattr(
        mod,
        "_gemini_post",
        lambda url, payload, api_key="", timeout=180: {
            "candidates": [{"content": {"parts": [{"text": '{"lines": [1,2'}]}, "finishReason": "MAX_TOKENS"}],
            "usageMetadata": {},
        },
    )

    with pytest.raises(RuntimeError, match="MAX_TOKENS"):
        GeminiProvider("k").chat([{"role": "user", "content": "hi"}])


def test_tools_are_rejected_rather_than_silently_dropped() -> None:
    """The agent loop must not think it has function calling here."""
    with pytest.raises(NotImplementedError):
        GeminiProvider("k").chat(
            [{"role": "user", "content": "hi"}], tools=[{"type": "function", "function": {}}]
        )


def test_embed_is_not_supported() -> None:
    with pytest.raises(NotImplementedError):
        GeminiProvider("k").embed("hi")


def test_test_connection_reports_success_and_elapsed(captured) -> None:
    ok, message, elapsed = GeminiProvider("k").test_connection()

    assert ok is True
    assert message == "OK"
    assert elapsed >= 0


def test_test_connection_reports_the_failure(monkeypatch) -> None:
    def _boom(url, payload, api_key="", timeout=180):
        raise RuntimeError("HTTP 403: key invalid")

    monkeypatch.setattr(mod, "_gemini_post", _boom)

    ok, message, _ = GeminiProvider("k").test_connection()
    assert ok is False
    assert "403" in message


def _http_error(code: str, body: bytes):
    """urllib is imported INSIDE the transport, so the patch goes on the real module."""
    import urllib.error

    def _raise(*_args, **_kwargs):
        raise urllib.error.HTTPError("u", code, "err", {}, io.BytesIO(body))

    return _raise


def test_a_billing_cap_reads_as_an_operator_problem_not_a_bad_document(monkeypatch):
    """A 429 used to reach the screen as a wall of provider JSON, which reads like the
    file could not be understood. It is the billing cap, nobody's document is at fault,
    and the person looking at it needs to know that nothing was lost."""
    import urllib.request

    monkeypatch.setattr(
        urllib.request, "urlopen",
        _http_error(429, b'{"error":{"message":"exceeded its monthly spending cap"}}'),
    )

    with pytest.raises(RuntimeError) as exc:
        mod._gemini_post("https://example/models/x:generateContent", {}, api_key="k")

    message = str(exc.value)
    assert "billing cap" in message
    assert "nothing is lost" in message
    # The raw provider blob never reaches a person.
    assert "RESOURCE_EXHAUSTED" not in message


def test_a_rejected_key_says_so_plainly(monkeypatch):
    import urllib.request

    monkeypatch.setattr(
        urllib.request, "urlopen",
        _http_error(403, b'{"error":{"message":"API key not valid"}}'),
    )

    with pytest.raises(RuntimeError, match="rejected our key"):
        mod._gemini_post("https://example/models/x:generateContent", {}, api_key="k")
