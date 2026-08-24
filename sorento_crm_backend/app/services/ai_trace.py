"""M2 - per-turn trace collector for the AI assistant pipeline.

A ``TurnTrace`` is created once per ``respond()`` call and buffers spans in
memory as the pipeline runs (reformulator, retriever, entity-resolver, each LLM
round, each tool call). It is flushed ONCE post-turn as a single bulk insert
(PLAN Q6). Flush is best-effort - a telemetry failure must never 500 a
successful answer (CLAUDE.md post-commit-side-effect rule): callers wrap
``flush()`` and swallow, and ``flush()`` itself also self-guards.

Field names are OpenTelemetry GenAI-semconv-shaped so a future OTLP export is a
straight field-map (PLAN Q1). No real OTel export in M2.

Payloads (LLM messages, tool results, retriever docs) are truncated at a
configurable byte cap with a ``truncated: true`` flag (PLAN Q2/B8).
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MAX_PAYLOAD_BYTES = 16384

# Span kinds (OTel/OpenInference-ish).
KIND_AGENT = "AGENT"
KIND_LLM = "LLM"
KIND_TOOL = "TOOL"
KIND_RETRIEVER = "RETRIEVER"
KIND_CHAIN = "CHAIN"
KIND_GUARDRAIL = "GUARDRAIL"
KIND_EMBEDDING = "EMBEDDING"
KIND_EVALUATOR = "EVALUATOR"


def _uuid_str() -> str:
    return str(uuid.uuid4())


def _byte_len(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))
    except Exception:
        return len(str(value).encode("utf-8"))


def _cap_structure(value: Any, str_budget: int, list_cap: int) -> Any:
    """Recursively cap long string leaves and long lists while KEEPING the JSON
    structure intact, so the payload stays a valid nested object the UI can
    pretty-print. Cut strings/lists get an inline ``…[+N …]`` marker."""
    if isinstance(value, str):
        if len(value) > str_budget:
            return value[:str_budget] + f"…[+{len(value) - str_budget} chars truncated]"
        return value
    if isinstance(value, dict):
        return {k: _cap_structure(v, str_budget, list_cap) for k, v in value.items()}
    if isinstance(value, list):
        capped = [_cap_structure(v, str_budget, list_cap) for v in value[:list_cap]]
        if len(value) > list_cap:
            capped.append(f"…[+{len(value) - list_cap} items truncated]")
        return capped
    return value


def _truncate_payload(value: Any, max_bytes: int) -> Any:
    """Cap a JSON-able payload at ``max_bytes`` (serialized) while PRESERVING its
    JSON structure - long string leaves and long lists are trimmed in place with
    an inline ``…[+N …]`` marker, so the stored value stays a valid nested object
    the trace UI renders as pretty-printed JSON (not a flat serialized blob).

    Only when structure-preserving trimming still can't fit (or the value isn't
    JSON-able) does it fall back to the ``{truncated, byte_size, preview}``
    envelope."""
    if value is None:
        return None
    if _byte_len(value) <= max_bytes:
        return value
    # Progressively tighten the per-string / list budgets until it fits.
    for str_budget in (max_bytes // 2, max_bytes // 4, max_bytes // 8, 1500, 600, 200):
        candidate = _cap_structure(value, max(120, str_budget), list_cap=50)
        if _byte_len(candidate) <= max_bytes:
            return candidate
    # Pathological (e.g. thousands of tiny keys) - last-resort flat preview.
    try:
        serialized = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        serialized = str(value)
    return {
        "truncated": True,
        "byte_size": len(serialized.encode("utf-8")),
        "preview": serialized[: max(0, max_bytes)],
    }


def sweep_expired_traces(db: Any) -> dict[str, int]:
    """Delete traces past their retention window (PLAN Q2/B11). ``ok`` traces
    past ``ai_trace_ttl_days``; ``error``/``flagged`` traces past
    ``ai_trace_error_ttl_days``. Spans cascade via FK. Returns counts. TTLs are
    read from ``system_settings`` (singleton) with defaults 30d / 90d.

    Best-effort: any failure is logged and returns zeros (never raises) so the
    scheduler heartbeat is not disrupted.
    """
    from datetime import timedelta

    from app.models.ai_assistant import AIAssistantTrace

    try:
        ttl_days = 30
        error_ttl_days = 90
        try:
            from app.models.user import SystemSetting

            row = db.query(SystemSetting).order_by(SystemSetting.id.asc()).first()
            if row is not None:
                ttl_days = int(getattr(row, "ai_trace_ttl_days", 30) or 30)
                error_ttl_days = int(getattr(row, "ai_trace_error_ttl_days", 90) or 90)
        except Exception:
            logger.warning("trace sweep: settings read failed; using defaults 30/90")

        now = datetime.utcnow()
        ok_cutoff = now - timedelta(days=max(1, ttl_days))
        err_cutoff = now - timedelta(days=max(1, error_ttl_days))

        # ok, not-flagged → ttl_days
        ok_deleted = (
            db.query(AIAssistantTrace)
            .filter(
                AIAssistantTrace.status == "ok",
                AIAssistantTrace.flagged.is_(False),
                AIAssistantTrace.created_at < ok_cutoff,
            )
            .delete(synchronize_session=False)
        )
        # error OR flagged → error_ttl_days
        err_deleted = (
            db.query(AIAssistantTrace)
            .filter(
                ((AIAssistantTrace.status == "error") | (AIAssistantTrace.flagged.is_(True))),
                AIAssistantTrace.created_at < err_cutoff,
            )
            .delete(synchronize_session=False)
        )
        db.commit()
        result = {"ok_deleted": int(ok_deleted or 0), "error_deleted": int(err_deleted or 0)}
        logger.info("AI trace sweep: %s", result)
        return result
    except Exception:
        logger.exception("AI trace sweep failed (best-effort)")
        try:
            db.rollback()
        except Exception:
            pass
        return {"ok_deleted": 0, "error_deleted": 0}


@dataclass
class _SpanRecord:
    id: str
    parent_id: str | None
    dotted_order: str
    span_kind: str
    name: str
    input_json: Any = None
    output_json: Any = None
    status: str = "ok"
    error: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    latency_ms: int = 0
    request_model: str | None = None
    response_model: str | None = None
    finish_reason: str | None = None
    invocation_params: dict[str, Any] | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    prompt_name: str | None = None
    prompt_version: int | None = None
    tool_name: str | None = None
    tool_call_id: str | None = None
    tool_args: Any = None
    tool_result: Any = None
    query: str | None = None
    documents: Any = None
    top_k: int | None = None


class TurnTrace:
    """In-memory span buffer for one assistant turn."""

    def __init__(
        self,
        *,
        user_id: str | None,
        conversation_id: str | None,
        session_id: str | None,
        env: str | None = None,
        max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
    ) -> None:
        self.trace_id: str = _uuid_str()
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.session_id = session_id
        self.env = env
        self.max_payload_bytes = max(512, int(max_payload_bytes or DEFAULT_MAX_PAYLOAD_BYTES))
        self._spans: list[_SpanRecord] = []
        self._seq = 0
        self._started_perf = time.perf_counter()
        self.started_at = datetime.utcnow()
        # The root AGENT span - every other span defaults to it as parent.
        self.root_id = self.add_span(
            kind=KIND_AGENT,
            name="assistant turn",
            parent_id=None,
        )

    # -- helpers -----------------------------------------------------------

    def _next_dotted(self) -> str:
        self._seq += 1
        # zero-padded monotonically-increasing key => spans sort in emit order.
        return f"{self._seq:06d}"

    def _cap(self, value: Any) -> Any:
        return _truncate_payload(value, self.max_payload_bytes)

    # -- span creation -----------------------------------------------------

    def add_span(
        self,
        *,
        kind: str,
        name: str,
        parent_id: str | None = "__root__",
        input_json: Any = None,
        output_json: Any = None,
        status: str = "ok",
        error: str | None = None,
        latency_ms: int | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        request_model: str | None = None,
        response_model: str | None = None,
        finish_reason: str | None = None,
        invocation_params: dict[str, Any] | None = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        prompt_name: str | None = None,
        prompt_version: int | None = None,
        tool_name: str | None = None,
        tool_call_id: str | None = None,
        tool_args: Any = None,
        tool_result: Any = None,
        query: str | None = None,
        documents: Any = None,
        top_k: int | None = None,
    ) -> str:
        """Append a completed span; returns its id. ``parent_id`` defaults to
        the root AGENT span (pass ``None`` only for the root itself)."""
        pid = self.root_id if parent_id == "__root__" else parent_id
        rec = _SpanRecord(
            id=_uuid_str(),
            parent_id=pid,
            dotted_order=self._next_dotted(),
            span_kind=kind,
            name=name[:2000] if name else "",
            input_json=self._cap(input_json),
            output_json=self._cap(output_json),
            status=status if status in {"ok", "error"} else "ok",
            error=(error or None) and str(error)[:4000],
            start_time=start_time,
            end_time=end_time,
            latency_ms=int(latency_ms or 0),
            request_model=request_model,
            response_model=response_model,
            finish_reason=finish_reason,
            invocation_params=invocation_params,
            tokens_in=int(tokens_in or 0),
            tokens_out=int(tokens_out or 0),
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            tool_args=self._cap(tool_args),
            tool_result=self._cap(tool_result),
            query=query,
            documents=self._cap(documents),
            top_k=top_k,
        )
        self._spans.append(rec)
        return rec.id

    # Convenience wrappers ------------------------------------------------

    def add_llm_span(
        self,
        *,
        name: str,
        model: str | None,
        messages_in: Any,
        result: Any,
        started_perf: float,
        prompt_name: str | None = None,
        prompt_version: int | None = None,
        status: str = "ok",
        error: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Record an LLM call from a ``ChatResult``-shaped ``result``."""
        latency_ms = int((time.perf_counter() - started_perf) * 1000)
        content = getattr(result, "content", None) if result is not None else None
        tool_calls = getattr(result, "tool_calls", None) if result is not None else None
        finish = None
        raw = getattr(result, "raw", None) if result is not None else None
        try:
            # OpenAI: raw.choices[0].finish_reason ; Anthropic: raw.stop_reason
            if raw is not None:
                choices = getattr(raw, "choices", None)
                if choices:
                    finish = getattr(choices[0], "finish_reason", None)
                if finish is None:
                    finish = getattr(raw, "stop_reason", None)
        except Exception:
            finish = None
        return self.add_span(
            kind=KIND_LLM,
            name=name,
            input_json={"messages": messages_in},
            output_json={"content": content, "tool_calls": tool_calls or []},
            status=status,
            error=error,
            latency_ms=latency_ms,
            request_model=model,
            finish_reason=finish if isinstance(finish, str) else None,
            invocation_params={"temperature": temperature, "max_tokens": max_tokens},
            tokens_in=int(getattr(result, "prompt_tokens", 0) or 0) if result is not None else 0,
            tokens_out=int(getattr(result, "completion_tokens", 0) or 0) if result is not None else 0,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
        )

    def add_tool_span(
        self,
        *,
        tool_name: str,
        tool_call_id: str | None,
        args: Any,
        result_text: str | None,
        started_perf: float,
        ok: bool,
        error: str | None = None,
    ) -> str:
        latency_ms = int((time.perf_counter() - started_perf) * 1000)
        parsed: Any = result_text
        if isinstance(result_text, str):
            try:
                parsed = json.loads(result_text)
            except Exception:
                parsed = {"text": result_text}
        return self.add_span(
            kind=KIND_TOOL,
            name=f"tool {tool_name}",
            input_json={"args": args},
            output_json=parsed,
            status="ok" if ok else "error",
            error=error,
            latency_ms=latency_ms,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            tool_args=args,
            tool_result=parsed,
        )

    # -- flush -------------------------------------------------------------

    def flush(self, db: Any, *, message_id: str | None, status: str = "ok") -> str | None:
        """Persist trace + spans in one shot. Best-effort: returns the trace id
        on success, ``None`` on failure (never raises)."""
        from app.models.ai_assistant import AIAssistantSpan, AIAssistantTrace

        try:
            latency_ms = int((time.perf_counter() - self._started_perf) * 1000)
            tokens_in = sum(s.tokens_in for s in self._spans)
            tokens_out = sum(s.tokens_out for s in self._spans)
            trace = AIAssistantTrace(
                id=self.trace_id,
                message_id=message_id,
                conversation_id=self.conversation_id,
                user_id=self.user_id,
                session_id=self.session_id,
                started_at=self.started_at,
                ended_at=datetime.utcnow(),
                total_tokens_in=tokens_in,
                total_tokens_out=tokens_out,
                status="error" if status == "error" else "ok",
                env=self.env,
                latency_ms=latency_ms,
                span_count=len(self._spans),
            )
            db.add(trace)
            # Emit the trace INSERT before the spans so the spans' FK
            # (span.trace_id -> traces.id) is satisfied. SQLAlchemy's batched
            # insertmany does not reliably order the parent row first when there
            # is no ORM relationship() between the two, so force it explicitly.
            db.flush()
            for rec in self._spans:
                db.add(
                    AIAssistantSpan(
                        id=rec.id,
                        trace_id=self.trace_id,
                        parent_id=rec.parent_id,
                        dotted_order=rec.dotted_order,
                        span_kind=rec.span_kind,
                        name=rec.name,
                        input_json=rec.input_json,
                        output_json=rec.output_json,
                        status=rec.status,
                        error=rec.error,
                        start_time=rec.start_time,
                        end_time=rec.end_time,
                        latency_ms=rec.latency_ms,
                        request_model=rec.request_model,
                        response_model=rec.response_model,
                        finish_reason=rec.finish_reason,
                        invocation_params=rec.invocation_params,
                        tokens_in=rec.tokens_in,
                        tokens_out=rec.tokens_out,
                        prompt_name=rec.prompt_name,
                        prompt_version=rec.prompt_version,
                        tool_name=rec.tool_name,
                        tool_call_id=rec.tool_call_id,
                        tool_args=rec.tool_args,
                        tool_result=rec.tool_result,
                        query=rec.query,
                        documents=rec.documents,
                        top_k=rec.top_k,
                    )
                )
            db.commit()
            return self.trace_id
        except Exception:
            logger.exception("Failed to flush AI assistant trace (best-effort)")
            try:
                db.rollback()
            except Exception:
                pass
            return None
