"""LLM provider abstraction (OpenAI, Anthropic, Gemini).

Goal: keep the agent loop and reformulator/embedder pieces in
``ai_assistant_service`` provider-agnostic. Each provider exposes the same
``chat`` / ``embed`` / ``test_connection`` surface and returns a normalized
``ChatResult`` whose ``raw`` field carries enough provider-native data to
iterate tool calls in the agent loop.

Gemini is the exception to "same surface, same capabilities": it is here for
document extraction only, and raises rather than pretends on tool calling and
embeddings. See ``GeminiProvider``.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


logger = logging.getLogger(__name__)


@dataclass
class ChatResult:
    """Normalized chat completion result.

    ``tool_calls`` is a normalized OpenAI-style list of pending calls the
    caller needs to execute. ``raw`` retains the provider-native response
    so the agent loop can append the assistant message back in the
    provider's expected schema.
    """

    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    tool_calls: list[dict] = field(default_factory=list)  # [{id, name, arguments}]
    raw: Any = None  # provider-native response


@dataclass
class ImagePart:
    """Single image attached to the last user message in a multimodal call.

    ``mime`` must be a content type the active provider accepts
    (``image/png``, ``image/jpeg``, ``image/webp``). ``data_b64`` is raw
    base64 with no ``data:`` prefix — each provider's ``chat`` adapter
    wraps it in the native shape.
    """

    mime: str
    data_b64: str


class LLMProvider(Protocol):
    name: str

    def chat(
        self,
        messages: list[dict],
        *,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.0,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        images: Optional[list[ImagePart]] = None,
        response_format: Optional[dict] = None,
        json_schema: Optional[dict] = None,
        json_schema_name: Optional[str] = None,
    ) -> ChatResult: ...

    def embed(self, text: str) -> list[float]: ...

    def test_connection(self) -> tuple[bool, str, int]: ...


# ---------------------------------------------------------------------------
# Multimodal helpers
# ---------------------------------------------------------------------------


def _attach_images_openai(
    messages: list[dict], images: list[ImagePart]
) -> list[dict]:
    """Return a copy of ``messages`` with ``images`` appended to the final
    user message in OpenAI's vision format.

    If no user message exists, a new one is created. The original text is
    preserved as a ``{"type":"text"}`` block so callers can keep passing
    plain-string content.
    """
    if not images:
        return messages
    out = [dict(m) for m in messages]
    last_user_idx = -1
    for i in range(len(out) - 1, -1, -1):
        if out[i].get("role") == "user":
            last_user_idx = i
            break
    if last_user_idx == -1:
        out.append({"role": "user", "content": []})
        last_user_idx = len(out) - 1

    msg = out[last_user_idx]
    existing = msg.get("content")
    blocks: list[dict] = []
    if isinstance(existing, str) and existing:
        blocks.append({"type": "text", "text": existing})
    elif isinstance(existing, list):
        blocks.extend(existing)
    for img in images:
        blocks.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{img.mime};base64,{img.data_b64}",
                },
            }
        )
    msg["content"] = blocks
    out[last_user_idx] = msg
    return out


def _attach_images_anthropic(
    messages: list[dict], images: list[ImagePart]
) -> list[dict]:
    """Return a copy of ``messages`` with ``images`` appended to the final
    user message in Anthropic's content-block format."""
    if not images:
        return messages
    out = [dict(m) for m in messages]
    last_user_idx = -1
    for i in range(len(out) - 1, -1, -1):
        if out[i].get("role") == "user":
            last_user_idx = i
            break
    if last_user_idx == -1:
        out.append({"role": "user", "content": []})
        last_user_idx = len(out) - 1

    msg = out[last_user_idx]
    existing = msg.get("content")
    blocks: list[dict] = []
    if isinstance(existing, str) and existing:
        blocks.append({"type": "text", "text": existing})
    elif isinstance(existing, list):
        blocks.extend(existing)
    for img in images:
        blocks.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": img.mime,
                    "data": img.data_b64,
                },
            }
        )
    msg["content"] = blocks
    out[last_user_idx] = msg
    return out


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, default_model: str = "gpt-4o-mini") -> None:
        self.api_key = api_key
        self.default_model = default_model

    # Lazy-import the SDK so importing this module is cheap and we don't fail
    # in environments without the SDK present (tests monkey-patch it anyway).
    def _client(self):
        from openai import OpenAI

        return OpenAI(api_key=self.api_key)

    def chat(
        self,
        messages: list[dict],
        *,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.0,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        images: Optional[list[ImagePart]] = None,
        response_format: Optional[dict] = None,
        json_schema: Optional[dict] = None,
        json_schema_name: Optional[str] = None,
    ) -> ChatResult:
        client = self._client()
        outbound_messages = (
            _attach_images_openai(messages, images) if images else messages
        )
        kwargs: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": outbound_messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        # Structured-output: force a schema-valid JSON object as the response
        # (OpenAI native strict mode). Takes precedence over response_format.
        if json_schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": json_schema_name or "structured_result",
                    "schema": json_schema,
                    "strict": True,
                },
            }
        elif response_format is not None:
            kwargs["response_format"] = response_format

        completion = client.chat.completions.create(**kwargs)

        # Defensive normalization — tests use simple stub objects.
        choice = completion.choices[0]
        msg = choice.message
        content = (getattr(msg, "content", None) or "")
        normalized_calls: list[dict] = []
        for call in (getattr(msg, "tool_calls", None) or []):
            fn = getattr(call, "function", None)
            args_raw = getattr(fn, "arguments", "") if fn is not None else ""
            try:
                parsed = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
            except Exception:
                parsed = {}
            normalized_calls.append(
                {
                    "id": getattr(call, "id", None),
                    "name": getattr(fn, "name", "") if fn is not None else "",
                    "arguments": parsed if isinstance(parsed, dict) else {},
                }
            )

        usage = getattr(completion, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", prompt_tokens + completion_tokens) or 0)

        return ChatResult(
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            tool_calls=normalized_calls,
            raw=completion,
        )

    def embed(self, text: str) -> list[float]:
        client = self._client()
        resp = client.embeddings.create(model="text-embedding-3-small", input=text)
        return list(resp.data[0].embedding)

    def test_connection(self) -> tuple[bool, str, int]:
        started = time.perf_counter()
        try:
            self.chat(
                [{"role": "user", "content": "hi"}],
                temperature=0,
                max_tokens=1,
            )
            elapsed = int((time.perf_counter() - started) * 1000)
            return True, "OK", elapsed
        except Exception as exc:  # noqa: BLE001
            elapsed = int((time.perf_counter() - started) * 1000)
            return False, str(exc), elapsed


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------


def _split_system_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    """Anthropic carries the system prompt as a separate parameter.

    We concatenate any ``system`` entries from the OpenAI-style list and
    return ``(system_text, non_system_messages)``. Tool/assistant messages
    are passed through; tool results are converted to a user-role message
    with ``tool_result`` content blocks (handled by ``_convert_messages``).
    """
    system_parts: list[str] = []
    rest: list[dict] = []
    for msg in messages:
        role = msg.get("role")
        if role == "system":
            content = msg.get("content")
            if isinstance(content, str):
                system_parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and isinstance(block.get("text"), str):
                        system_parts.append(block["text"])
        else:
            rest.append(msg)
    return ("\n\n".join(p for p in system_parts if p).strip(), rest)


def _convert_tools_to_anthropic(tools: list[dict]) -> list[dict]:
    """Convert OpenAI-style ``[{type,function:{name,description,parameters}}]``
    to Anthropic's ``[{name,description,input_schema}]``."""
    out: list[dict] = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        fn = tool.get("function") if isinstance(tool.get("function"), dict) else tool
        name = fn.get("name")
        if not name:
            continue
        out.append(
            {
                "name": name,
                "description": fn.get("description") or "",
                "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
            }
        )
    return out


def _convert_messages_to_anthropic(messages: list[dict]) -> list[dict]:
    """Convert OpenAI-style messages (user/assistant/tool with tool_calls) to
    Anthropic's content-block format.

    Tool-result messages (``role=tool``) become ``user`` messages with a
    single ``tool_result`` content block keyed by ``tool_call_id`` →
    ``tool_use_id``. Assistant messages with ``tool_calls`` produce content
    blocks containing both any text and ``tool_use`` entries.
    """
    out: list[dict] = []
    for msg in messages:
        role = msg.get("role")
        if role == "tool":
            tool_call_id = msg.get("tool_call_id") or msg.get("tool_use_id") or ""
            content = msg.get("content")
            if not isinstance(content, str):
                content = json.dumps(content)
            out.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_call_id,
                            "content": content,
                        }
                    ],
                }
            )
            continue

        if role == "assistant":
            blocks: list[dict] = []
            text = msg.get("content")
            if isinstance(text, str) and text.strip():
                blocks.append({"type": "text", "text": text})
            for call in msg.get("tool_calls") or []:
                fn = (call.get("function") or {}) if isinstance(call, dict) else {}
                args_raw = fn.get("arguments") or "{}"
                try:
                    parsed = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
                except Exception:
                    parsed = {}
                if not isinstance(parsed, dict):
                    parsed = {}
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": call.get("id") or "",
                        "name": fn.get("name") or "",
                        "input": parsed,
                    }
                )
            if not blocks:
                blocks = [{"type": "text", "text": ""}]
            out.append({"role": "assistant", "content": blocks})
            continue

        # default: user message (or anything else) — pass through as text
        content = msg.get("content")
        if isinstance(content, str):
            out.append({"role": "user", "content": content})
        elif isinstance(content, list):
            out.append({"role": "user", "content": content})
        else:
            out.append({"role": "user", "content": json.dumps(content) if content is not None else ""})
    return out


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, default_model: str = "claude-haiku-4-5") -> None:
        self.api_key = api_key
        self.default_model = default_model

    def _client(self):
        import anthropic

        return anthropic.Anthropic(api_key=self.api_key)

    def chat(
        self,
        messages: list[dict],
        *,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.0,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        images: Optional[list[ImagePart]] = None,
        response_format: Optional[dict] = None,
        json_schema: Optional[dict] = None,
        json_schema_name: Optional[str] = None,
    ) -> ChatResult:
        client = self._client()
        system_text, rest = _split_system_messages(messages)
        # Structured-output: Anthropic has no response_format=json_schema. Force
        # a single tool whose input_schema IS the target schema and require it
        # via tool_choice — the model's tool_use.input is the schema-valid object.
        # We surface that object as ``content`` (JSON string) so the caller parses
        # it exactly like the OpenAI path.
        if json_schema is not None:
            tool_name = json_schema_name or "structured_result"
            ant_messages = _convert_messages_to_anthropic(rest)
            if images:
                ant_messages = _attach_images_anthropic(ant_messages, images)
            forced_kwargs: dict[str, Any] = {
                "model": model or self.default_model,
                "messages": ant_messages,
                "temperature": temperature,
                "max_tokens": max_tokens or 1024,
                "tools": [{
                    "name": tool_name,
                    "description": "Emit the structured result.",
                    "input_schema": json_schema,
                }],
                "tool_choice": {"type": "tool", "name": tool_name},
            }
            if system_text:
                forced_kwargs["system"] = system_text
            resp = client.messages.create(**forced_kwargs)
            payload: dict | None = None
            for block in (getattr(resp, "content", None) or []):
                if getattr(block, "type", None) == "tool_use":
                    payload = getattr(block, "input", {}) or {}
                    break
            if payload is None:
                # No tool_use block (e.g. max_tokens truncation / refusal). Raise so
                # the caller's retry fires instead of silently emitting an empty
                # object that would validate into a confident default result.
                raise RuntimeError(
                    f"forced tool '{tool_name}' produced no tool_use block "
                    f"(stop_reason={getattr(resp, 'stop_reason', None)})"
                )
            usage = getattr(resp, "usage", None)
            pt = int(getattr(usage, "input_tokens", 0) or 0)
            ct = int(getattr(usage, "output_tokens", 0) or 0)
            return ChatResult(
                content=json.dumps(payload, ensure_ascii=False),
                prompt_tokens=pt,
                completion_tokens=ct,
                total_tokens=pt + ct,
                tool_calls=[],
                raw=resp,
            )
        # Anthropic has no native JSON-mode flag; emulate by appending an
        # explicit instruction to the system prompt. The extract service
        # validates the response is parseable JSON either way.
        if response_format and response_format.get("type") == "json_object":
            json_directive = (
                "Return ONLY a single JSON object as the assistant message — "
                "no prose, no code fences, no leading or trailing text."
            )
            system_text = f"{system_text}\n\n{json_directive}".strip()
        ant_messages = _convert_messages_to_anthropic(rest)
        if images:
            ant_messages = _attach_images_anthropic(ant_messages, images)
        kwargs: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": ant_messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 1024,
        }
        if system_text:
            kwargs["system"] = system_text
        if tools:
            kwargs["tools"] = _convert_tools_to_anthropic(tools)

        resp = client.messages.create(**kwargs)

        text_chunks: list[str] = []
        normalized_calls: list[dict] = []
        for block in (getattr(resp, "content", None) or []):
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_chunks.append(getattr(block, "text", "") or "")
            elif block_type == "tool_use":
                normalized_calls.append(
                    {
                        "id": getattr(block, "id", None) or "",
                        "name": getattr(block, "name", "") or "",
                        "arguments": getattr(block, "input", {}) or {},
                    }
                )

        usage = getattr(resp, "usage", None)
        prompt_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        total_tokens = prompt_tokens + completion_tokens

        return ChatResult(
            content="".join(text_chunks),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            tool_calls=normalized_calls,
            raw=resp,
        )

    def embed(self, text: str) -> list[float]:
        """Anthropic does not currently expose a first-party embeddings API.

        Fall back to OpenAI when an OpenAI key is configured at the platform
        level; otherwise raise so the caller surfaces a clear error.
        """
        from app.config import settings

        if settings.openai_api_key:
            return OpenAIProvider(settings.openai_api_key).embed(text)
        raise RuntimeError(
            "Anthropic provider does not support embeddings; configure OPENAI_API_KEY "
            "as a fallback for the embedding pipeline."
        )

    def test_connection(self) -> tuple[bool, str, int]:
        started = time.perf_counter()
        try:
            self.chat(
                [{"role": "user", "content": "hi"}],
                temperature=0,
                max_tokens=1,
            )
            elapsed = int((time.perf_counter() - started) * 1000)
            return True, "OK", elapsed
        except Exception as exc:  # noqa: BLE001
            elapsed = int((time.perf_counter() - started) * 1000)
            return False, str(exc), elapsed


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------

_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


def _gemini_post(url: str, payload: dict, *, api_key: str, timeout: int = 180) -> dict:
    """Single transport seam for the Gemini REST call.

    A module-level function rather than a method so tests can substitute it
    without a fake SDK, and so the key stays out of the URL: Google accepts
    ``x-goog-api-key``, and a key in the query string ends up in every log
    line and proxy record that ever sees the request.
    """
    import urllib.error
    import urllib.request

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:500]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from None


def _convert_messages_to_gemini(messages: list[dict]) -> tuple[Optional[dict], list[dict]]:
    """Split off the system instruction and map roles onto Gemini's names.

    Gemini calls the assistant ``model`` and carries the system prompt in a
    separate ``systemInstruction`` field, same shape of problem as Anthropic.
    """
    system_text, rest = _split_system_messages(messages)
    contents: list[dict] = []
    for message in rest:
        role = "model" if message.get("role") == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": str(message.get("content") or "")}]})
    instruction = {"parts": [{"text": system_text}]} if system_text else None
    return instruction, contents


class GeminiProvider:
    """Google Gemini via REST, for document extraction.

    Deliberately narrow: ``chat`` with optional images and forced JSON, which
    is the whole job (reading a scanned PO or a delivery-schedule matrix).
    Tool calling and embeddings raise instead of pretending, so the agent loop
    can never be handed a provider that quietly ignores its tools.
    """

    name = "gemini"

    def __init__(self, api_key: str, default_model: str = "gemini-2.5-flash") -> None:
        self.api_key = api_key
        self.default_model = default_model

    def chat(
        self,
        messages: list[dict],
        *,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.0,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        images: Optional[list[ImagePart]] = None,
        response_format: Optional[dict] = None,
        json_schema: Optional[dict] = None,
        json_schema_name: Optional[str] = None,
    ) -> ChatResult:
        if tools:
            raise NotImplementedError(
                "GeminiProvider does not implement tool calling; use openai or anthropic"
            )

        instruction, contents = _convert_messages_to_gemini(messages)
        if images:
            if not contents:
                contents = [{"role": "user", "parts": []}]
            for image in images:
                contents[-1]["parts"].append(
                    {"inline_data": {"mime_type": image.mime, "data": image.data_b64}}
                )

        generation: dict[str, Any] = {"temperature": temperature}
        if max_tokens is not None:
            generation["maxOutputTokens"] = max_tokens
        if json_schema is not None:
            generation["responseMimeType"] = "application/json"
            generation["responseSchema"] = json_schema
        elif (response_format or {}).get("type") in {"json_object", "json_schema"}:
            generation["responseMimeType"] = "application/json"

        payload: dict[str, Any] = {"contents": contents, "generationConfig": generation}
        if instruction:
            payload["systemInstruction"] = instruction

        url = f"{_GEMINI_BASE}/models/{model or self.default_model}:generateContent"
        body = _gemini_post(url, payload, api_key=self.api_key)

        candidates = body.get("candidates") or []
        if not candidates:
            reason = (body.get("promptFeedback") or {}).get("blockReason") or "no candidate"
            raise RuntimeError(f"Gemini returned no candidate: {reason}")

        candidate = candidates[0]
        finish = candidate.get("finishReason")
        # A truncated document is worse than a failed one: half a PO looks like
        # a complete PO with lines missing, and nothing downstream can tell.
        if finish and finish not in {"STOP", "MAX_TOKENS"}:
            raise RuntimeError(f"Gemini stopped early: {finish}")
        if finish == "MAX_TOKENS":
            raise RuntimeError("Gemini stopped early: MAX_TOKENS (response truncated)")

        content = "".join(
            part.get("text", "") for part in (candidate.get("content") or {}).get("parts") or []
        )
        usage = body.get("usageMetadata") or {}
        prompt_tokens = int(usage.get("promptTokenCount") or 0)
        completion_tokens = int(usage.get("candidatesTokenCount") or 0)

        return ChatResult(
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=int(usage.get("totalTokenCount") or prompt_tokens + completion_tokens),
            tool_calls=[],
            raw=body,
        )

    def embed(self, text: str) -> list[float]:
        raise NotImplementedError("GeminiProvider is extraction-only; embeddings live elsewhere")

    def test_connection(self) -> tuple[bool, str, int]:
        started = time.perf_counter()
        try:
            self.chat([{"role": "user", "content": "hi"}], temperature=0, max_tokens=1)
            return True, "OK", int((time.perf_counter() - started) * 1000)
        except Exception as exc:  # noqa: BLE001
            return False, str(exc), int((time.perf_counter() - started) * 1000)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_provider(provider: str, api_key: str, model: Optional[str] = None) -> LLMProvider:
    """Resolve a provider implementation by name.

    Raises ``ValueError`` for unknown providers so the calling code can
    surface a sensible error to the operator.
    """
    key = (provider or "").strip().lower()
    if key == "openai":
        return OpenAIProvider(api_key=api_key, default_model=model or "gpt-4o-mini")
    if key == "anthropic":
        return AnthropicProvider(api_key=api_key, default_model=model or "claude-haiku-4-5")
    if key == "gemini":
        return GeminiProvider(api_key=api_key, default_model=model or "gemini-2.5-flash")
    raise ValueError(f"Unsupported provider: {provider}")
