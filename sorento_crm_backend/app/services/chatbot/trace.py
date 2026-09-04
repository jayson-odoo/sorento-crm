"""The turn trace: one record per stage, written as each stage ends (AC-007, D13).

The operator journey is the whole point. `summary` and `why` are SENTENCES the engine
composes from structured state - never the customer's text, never JSON - so the screen in
S2b renders words a non-engineer can read ("Understood as a business query about product
SRTWC8517, dealer tier" / "Routed to the business lane: access allowed, no escalation
asked"). `facts` is a small flat dict for the row's key/value chips, and `raw` is the
technical payload behind "Technical details", byte-capped the way the AI-assistant trace
already caps its spans.

Nothing here decides anything. A stage that did not run for a lane is simply absent, not
recorded as `skipped` with an empty body - AC-252 says an unrun stage is omitted.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from app.services.chatbot.contracts import TraceStatus, TurnStage

# One stage's `raw` payload, capped. A parser response plus a session blob is a few KB;
# 32 KB leaves room for a large result set without letting one turn's trace dominate the
# row. Over the cap, the payload is replaced by a note naming its size, so the reader is
# told the truth instead of being shown a silently truncated object.
RAW_BYTE_CAP = 32_768


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# The whole ENVELOPE and the whole RESPONSE, capped the same way and for the same reason:
# `chatbot.turns` is written once per customer message forever, and one media-heavy
# envelope or one result set of ten thousand rows would otherwise sit in the row for the
# life of the table. Larger than the trace's per-stage cap because both are load-bearing -
# a duplicate delivery replays `response`, and Retry re-injects `envelope` - so the cap has
# to be a guardrail against the pathological case, not a routine truncation.
#
# Twice the endpoint's 256 KB body limit on purpose: a body the route ACCEPTED must never
# come back capped, or Retry would re-inject a note. This only ever fires on a document the
# engine grew itself (a huge result set) or on an internal caller that skipped the route.
DOCUMENT_BYTE_CAP = 524_288


def cap_document(value: Any, *, limit: int = DOCUMENT_BYTE_CAP) -> Any:
    """`_cap` for a whole stored document. Over the limit, a note that names the size."""
    return _cap(value, limit=limit)


def _cap(raw: Any, *, limit: int = RAW_BYTE_CAP) -> Any:
    if raw is None:
        return None
    try:
        encoded = json.dumps(raw, default=str)
    except Exception:  # noqa: BLE001 - a trace must never fail the turn
        return {"note": "payload is not JSON-serialisable"}
    if len(encoded) <= limit:
        return json.loads(encoded)
    return {
        "note": f"payload omitted: {len(encoded)} bytes exceeds the {limit} byte cap",
    }


class TurnTrace:
    """An ordered list of stage records, plus the clock for the stage in progress."""

    __slots__ = ("_records", "_started_perf", "_started_iso")

    def __init__(self) -> None:
        self._records: list[dict[str, Any]] = []
        self._started_perf: float | None = None
        self._started_iso: str | None = None

    def start(self) -> None:
        """Mark the beginning of the next stage. Idempotent within a stage."""
        self._started_perf = time.perf_counter()
        self._started_iso = _now_iso()

    def record(
        self,
        stage: TurnStage,
        *,
        status: TraceStatus = "ok",
        summary: str,
        why: str,
        facts: dict[str, Any] | None = None,
        error: str | None = None,
        raw: Any = None,
    ) -> None:
        """Append one stage record and reset the clock for the next stage."""
        started_perf = self._started_perf if self._started_perf is not None else time.perf_counter()
        self._records.append(
            {
                "stage": stage,
                "status": status,
                "started_at": self._started_iso or _now_iso(),
                "ms": int((time.perf_counter() - started_perf) * 1000),
                "summary": summary,
                "why": why,
                "facts": facts or {},
                "error": error,
                "raw": _cap(raw),
            }
        )
        self.start()

    @property
    def records(self) -> list[dict[str, Any]]:
        return self._records

    def stages(self) -> list[str]:
        return [r["stage"] for r in self._records]


# --------------------------------------------------------------------------- #
# Sentence builders. D11: composed from STRUCTURED STATE, never from the
# customer's words and never by an LLM.
# --------------------------------------------------------------------------- #

_LANE_WORDS = {
    "access_denied": "Access refused",
    "escalate_offer": "Escalation offer",
    "out_of_scope": "Escalation",
    "ideate": "Idea capture",
    "offer_hold": "Holding an offer open",
    "escalation_declined": "Escalation declined",
    "check_promotion": "Business query: promotion",
    "low_signal": "Small talk",
    "clarify_menu": "Asked to clarify",
    "not_supported": "Not supported",
    "stock_denied": "Stock access refused",
    "demand_qty": "Asked for a quantity",
    "business_query": "Business query",
}


def lane_words(branch_kind: str | None, domain_hint: str | None = None) -> str:
    """The lane in plain words, for the Turn line's status row (AC-251)."""
    base = _LANE_WORDS.get(branch_kind or "", "Unknown lane")
    if branch_kind == "business_query" and domain_hint:
        return f"{base}: {domain_hint.replace('_', ' ')}"
    return base


MAX_ENTITY_CHARS = 40


def _clip(value: str) -> str:
    return value if len(value) <= MAX_ENTITY_CHARS else value[: MAX_ENTITY_CHARS - 1] + "\u2026"


def understood_summary(qf: dict[str, Any]) -> str:
    """"Understood as a business query about product SRTWC8517, dealer tier"."""
    message_type = (qf.get("message_type") or "unknown").replace("_", " ")
    parts = [f"Understood as {message_type}"]
    domain = qf.get("domain_hint")
    if domain:
        parts.append(f"about {str(domain).replace('_', ' ')}")
    entities = qf.get("entities") if isinstance(qf.get("entities"), list) else []
    # Truncated: an entity's `raw` is CUSTOMER TEXT, and an unbounded one turns a one-line
    # summary into a paragraph on the trace screen (and a long row in the turn record).
    named = [
        _clip(str(e.get("canonical_code") or e.get("raw")))
        for e in entities
        if isinstance(e, dict) and (e.get("canonical_code") or e.get("raw"))
    ][:3]
    if named:
        parts.append("(" + ", ".join(named) + ")")
    tiers = qf.get("access_levels") if isinstance(qf.get("access_levels"), list) else []
    if tiers:
        parts.append(", ".join(str(t).replace("_", " ") for t in tiers) + " tier")
    return " ".join(parts)


def routed_why(branch_kind: str, qf: dict[str, Any], access_allowed: bool) -> str:
    """One sentence naming the reason this lane won, from state only."""
    escalation = qf.get("escalation") if isinstance(qf.get("escalation"), dict) else {}
    if branch_kind == "access_denied":
        return "Routed to the refusal: this contact is not granted the agent the turn needs."
    if branch_kind == "out_of_scope":
        return "Routed to escalation: the customer asked for a person or accepted the offer."
    if branch_kind == "escalation_declined":
        return "Routed to the decline: the customer turned the escalation offer down."
    if branch_kind == "low_signal":
        return "Routed to small talk: no domain and no decisive intent were understood."
    if branch_kind == "clarify_menu":
        return "Routed to the clarify menu: the turn was understood as a clarification."
    if branch_kind == "not_supported":
        return "Routed to the refusal: the domain asked about is not supported."
    if branch_kind == "ideate":
        return "Routed to idea capture: the turn proposes an idea."
    if branch_kind == "offer_hold":
        return "Held the previous offer open: the reply neither picked nor abandoned it."
    if escalation.get("is_escalation_confirmation") is True:
        return "Routed by the escalation confirmation the customer gave."
    access_words = "access allowed" if access_allowed else "access refused"
    return f"Routed to the {lane_words(branch_kind).lower()}: {access_words}, no escalation asked."
