"""Turn engines. HttpTurnEngine posts a dry-run envelope to the CRM; others load by `module:Class`."""

from __future__ import annotations

import importlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from .trace import build_digest, parse_trace

MAX_TRIES = 5
RETRY_STATUS = (429, 502, 503, 504)


@dataclass
class Outcome:
    reply_text: str
    branch_kind: str | None = None
    dry_run: bool = True
    tool_errors: list[str] = field(default_factory=list)
    lane_notes: list[str] = field(default_factory=list)
    trace_digest: dict | None = None
    tokens: dict = field(default_factory=lambda: {"prompt": 0, "cached": 0, "output": 0})
    latency_ms: int = 0
    state: dict | None = None
    raw: dict = field(default_factory=dict)


class Engine(Protocol):
    def turn(self, case: Any, text: str, state: dict | None, run_id: str) -> Outcome: ...


def _is_final_text(case: Any, text: str) -> bool:
    final = {case.message.get("text")} | {v.get("text") for v in case.variants}
    return text in final


class HttpTurnEngine:
    def __init__(
        self, base_url: str, api_key: str, timeout: float = 60, trace_reader: Any = None, contact_reset: Any = None, prompt_version: Any = None
    ):
        self.trace_reader = trace_reader
        self.contact_reset = contact_reset
        self.prompt_version = prompt_version
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def build_envelope(self, case: Any, text: str, state: dict | None, run_id: str) -> dict:
        contact_id = str(case.contact.get("respond_id", ""))
        inner: dict[str, Any] = {
            "contactId": contact_id,
            "messageId": f"eval-{uuid.uuid4().hex[:12]}",
            "message": {"type": "text", "text": text},
        }
        reply_to = case.message.get("reply_to")
        if isinstance(reply_to, str) and reply_to and _is_final_text(case, text):
            inner["replyTo"] = {"id": "", "text": reply_to}
        elif reply_to and not isinstance(reply_to, str) and _is_final_text(case, text):
            inner["replyTo"] = {
                "id": str(reply_to.get("id", "")),
                "sender": {"source": reply_to.get("source") or "n8n"},
                "message": {"text": reply_to.get("text", "")},
            }
        env: dict[str, Any] = {
            "message": {"contact": {"id": contact_id}, "message": inner, "event_type": "message.received"},
            "contact": {"id": contact_id, "custom_fields": case.contact.get("custom_fields") or []},
            "is_test": True,
            "test_run_id": run_id,
            "ingress": "console",
        }
        if self.prompt_version is not None:
            env["prompt_overrides"] = {"chatbot_semantic_parser": str(self.prompt_version)}
        if state is not None:
            env["previous_conversation_state"] = state
        return env

    def fetch_trace(self, turn_id: str) -> dict | None:
        """Tokens and tool errors from the turns row when a trace reader is set, else None."""
        if self.trace_reader is None or not turn_id:
            return None
        entries = self.trace_reader.fetch(turn_id)
        tokens, errors, notes = parse_trace(entries)
        return {"tokens": tokens, "tool_errors": errors, "lane_notes": notes, "entries": entries or []}

    def reset_contact(self, case: Any) -> None:
        """Clear the contact's earlier test memory (private eval DB only); no-op without a reset handle."""
        if self.contact_reset is not None:
            self.contact_reset.reset(str(case.contact.get("respond_id", "")))

    def _post(self, client: httpx.Client, url: str, env: dict) -> httpx.Response:
        for attempt in range(MAX_TRIES):
            last = attempt == MAX_TRIES - 1
            try:
                resp = client.post(url, json={"envelope": env}, headers={"X-API-Key": self.api_key})
            except httpx.TransportError:
                if last:
                    raise
                time.sleep(2.0**attempt)
                continue
            if resp.status_code not in RETRY_STATUS or last:
                return resp
            try:
                wait = float(resp.headers.get("Retry-After", ""))
            except ValueError:
                wait = 2.0**attempt
            time.sleep(min(wait, 60.0))
        raise RuntimeError("unreachable")  # pragma: no cover

    def turn(self, case: Any, text: str, state: dict | None, run_id: str) -> Outcome:
        env = self.build_envelope(case, text, state, run_id)
        url = f"{self.base_url}/api/v1/external/chat/turn"
        started = time.monotonic()
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = self._post(client, url, env)
        except httpx.TransportError as exc:
            latency = int((time.monotonic() - started) * 1000)
            return Outcome(reply_text="", dry_run=True, tool_errors=[f"transport: {type(exc).__name__}"], latency_ms=latency)
        latency_ms = int((time.monotonic() - started) * 1000)
        if resp.status_code != 200:
            return Outcome(reply_text="", dry_run=True, tool_errors=[f"http {resp.status_code}"], latency_ms=latency_ms)
        body = resp.json()
        actions = body.get("actions") or []
        dry = body.get("is_test") is True and all(a.get("dry_run") is True for a in actions)
        trace = self.fetch_trace(body.get("turn_id", "")) or {}
        tokens = body.get("tokens") or trace.get("tokens") or {}
        tool_errors = list(body.get("tool_errors") or []) + list(trace.get("tool_errors") or [])
        reply_text = (body.get("reply") or {}).get("text") or ""
        return Outcome(
            trace_digest=build_digest(trace.get("entries"), reply_text, body.get("branch_kind")),
            reply_text=reply_text,
            branch_kind=body.get("branch_kind"),
            dry_run=dry,
            tool_errors=tool_errors,
            lane_notes=list(trace.get("lane_notes") or []),
            tokens={k: int(tokens.get(k, 0) or 0) for k in ("prompt", "cached", "output")},
            latency_ms=latency_ms,
            state=body.get("session_patch"),
            raw=body,
        )


class AgentTurnEngine:
    """AGENTIC-P1: one case turn = one forced console agent turn (`POST /system/chatbot/console/turn` with `force_agent`).

    The route is a staff console route, so it takes a staff session token (`EVAL_AGENT_TOKEN`), not the
    integration key. The agent only reads, so every outcome is a dry run. `reset_contact` starts a new
    agent conversation, which is how the agent clears its context."""

    TOOL_FAILURES = ("denied", "invalid", "error", "timeout")

    def __init__(self, base_url: str, api_key: str = "", timeout: float = 120, token: str | None = None, **_: Any):
        import os

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.token = token if token is not None else os.environ.get("EVAL_AGENT_TOKEN", "")
        self.transport: Any = None

    def _client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self.timeout, transport=self.transport, headers={"Authorization": f"Bearer {self.token}"}
        )

    def reset_contact(self, case: Any) -> None:
        body = {"contact_respond_id": str(case.contact.get("respond_id", ""))}
        with self._client() as client:
            client.post(f"{self.base_url}/api/v1/system/chatbot/agent/conversation/new", json=body)

    def turn(self, case: Any, text: str, state: dict | None, run_id: str) -> Outcome:
        body = {
            "contact_respond_id": str(case.contact.get("respond_id", "")), "text": text,
            "run_id": run_id, "force_agent": True,
        }
        started = time.monotonic()
        try:
            with self._client() as client:
                resp = client.post(f"{self.base_url}/api/v1/system/chatbot/console/turn", json=body)
        except httpx.TransportError as exc:
            latency = int((time.monotonic() - started) * 1000)
            return Outcome(reply_text="", tool_errors=[f"transport: {type(exc).__name__}"], latency_ms=latency)
        latency_ms = int((time.monotonic() - started) * 1000)
        if resp.status_code != 200:
            try:
                detail = resp.json().get("detail")
            except ValueError:
                detail = None
            reason = detail.get("reason") if isinstance(detail, dict) else None
            label = f"http {resp.status_code}" + (f" {reason}" if reason else "")
            return Outcome(reply_text="", tool_errors=[label], latency_ms=latency_ms)
        top = resp.json()
        data = top.get("agent")
        if not isinstance(data, dict):
            # Refused, busy or failed: the console answers with reply text and no agent block.
            return Outcome(
                reply_text=top.get("reply_text") or "", tool_errors=["no agent turn"], latency_ms=latency_ms, raw=top
            )
        usage = data.get("usage") or {}
        calls = [c for c in data.get("tool_calls") or [] if isinstance(c, dict)]
        notes = [f"rounds={data.get('rounds', 0)}"]
        if data.get("limit_hit"):
            notes.append(f"limit={data['limit_hit']}")
        notes += [f"tool {c.get('name')} {c.get('status')}" for c in calls]
        return Outcome(
            reply_text=data.get("reply_text") or "",
            branch_kind=f"agent:{data.get('status')}",
            dry_run=True,
            tool_errors=[f"{c.get('name')}: {c.get('status')}" for c in calls if c.get("status") in self.TOOL_FAILURES],
            lane_notes=notes,
            tokens={
                "prompt": int(usage.get("prompt_tokens", 0) or 0),
                "cached": int(usage.get("cached_tokens", 0) or 0),
                "output": int(usage.get("completion_tokens", 0) or 0),
            },
            latency_ms=latency_ms,
            raw=data,
        )


def load_engine(spec: str, **kw: Any) -> Engine:
    if spec == "http":
        return HttpTurnEngine(**kw)
    module, _, name = spec.partition(":")
    if not name:
        raise ValueError(f"engine must be 'http' or 'pkg.mod:Class', got {spec!r}")
    return getattr(importlib.import_module(module), name)(**kw)
