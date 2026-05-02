"""LLM provider abstraction (OpenAI + Anthropic).

Goal: keep the agent loop and reformulator/embedder pieces in
``ai_assistant_service`` provider-agnostic. Each provider exposes the same
``chat`` / ``embed`` / ``test_connection`` surface and returns a normalized
``ChatResult`` whose ``raw`` field carries enough provider-native data to
iterate tool calls in the agent loop.
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
        if response_format is not None:
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
    ) -> ChatResult:
        client = self._client()
        system_text, rest = _split_system_messages(messages)
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
    raise ValueError(f"Unsupported provider: {provider}")
