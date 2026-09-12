"""Compose one turn's `trace_detail` for `GET /system/chatbot/turns/{id}` (Slice D).

READ-ONLY over `chatbot_turn.trace` - a list of dicts already written per stage by
`trace.py::TurnTrace.record` (`{"stage": ..., "status": ..., "started_at": ..., "ms":
..., "summary": ..., "why": ..., "facts": {...}, "error": ..., "raw": {...}}`) and,
once the sibling `feat/chatbot-growth-data` / `feat/chatbot-growth-dialogue` lanes land
`TurnTrace.add(kind, payload)`, entries of the shape `{"kind": <one of "tool",
"crossdomain", "reveals", "decay", "focus", "open_question">, **payload}` appended to
the SAME list.

This module never depends on those lanes landing first: a `kind` this build has never
seen simply contributes nothing, so `tool` / `crossdomain` / `reveals` / `decay` /
`focus` / `open_question` render as empty sections until the writer exists - which is
the explicit contract this slice was built against (captain's brief, chatbot growth r1
Slice D).

Nothing here writes anything. `app/services/chatbot/trace.py` (the write side, and the
`memory_delta` this reuses for the session diff) is untouched.
"""
from __future__ import annotations

import json
from typing import Any

from app.models.chatbot_turn import ChatbotTurn
from app.services.chatbot import trace as trace_mod

#: Envelope truncation cap for the `tool` section (AC-970). Deliberately smaller than
#: `trace.py`'s own 32 KB per-stage `raw` cap: a turn detail screen renders ONE tool
#: call's envelope inline, where the per-stage trace only ever offers it behind
#: "technical details". 8 KB is what the plan's Slice D block names.
TOOL_ENVELOPE_BYTE_CAP = 8_192


def _records(row: ChatbotTurn) -> list[dict[str, Any]]:
    raw = row.trace
    return [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []


def _stage_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Records `trace.py::record` wrote: carry `stage`, never `kind`."""
    return [r for r in records if r.get("kind") is None and r.get("stage") is not None]


def _kind_records(records: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    """Records a `TurnTrace.add(kind, payload)` call wrote, in the order they landed."""
    return [r for r in records if r.get("kind") == kind]


def _cap_envelope(envelope: Any) -> Any:
    """Truncate, never drop (review, 7 Sep 2026): the cut is on ENCODED BYTES, not
    code points - a code-point cut on a multibyte (e.g. Chinese) envelope either
    undercounts the real size against the byte cap or slices a character in half,
    which `errors="ignore"` on decode then silently drops instead of rendering.

    `ensure_ascii=False`: the default `json.dumps` escapes every non-ASCII
    character to a `\\uXXXX` sequence, which is pure ASCII and can never be cut
    mid-character - that would make the byte-vs-code-point distinction this fix
    exists for moot. Un-escaped, a Chinese envelope's characters are the real
    2-4 byte UTF-8 sequences the byte cap has to reckon with.
    """
    if envelope is None:
        return None
    try:
        encoded = json.dumps(envelope, default=str, ensure_ascii=False)
    except Exception:  # noqa: BLE001 - a trace read must never fail the request
        return {"truncated": True, "note": "payload is not JSON-serialisable"}
    encoded_bytes = encoded.encode("utf-8")
    if len(encoded_bytes) <= TOOL_ENVELOPE_BYTE_CAP:
        return json.loads(encoded)
    return {
        "truncated": True,
        "bytes": len(encoded_bytes),
        "head": encoded_bytes[:TOOL_ENVELOPE_BYTE_CAP].decode("utf-8", errors="ignore"),
    }


def _stages(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """`{name, started_at, ms, status, summary, error}`, the failing stage FIRST
    (AC-973) - an operator opening a failed turn should not have to scroll to find
    what broke.
    """
    stages = [
        {
            "name": r.get("stage"),
            "started_at": r.get("started_at"),
            "ms": r.get("ms"),
            "status": r.get("status"),
            "summary": r.get("summary"),
            "error": r.get("error"),
        }
        for r in _stage_records(records)
    ]
    failed_first = [s for s in stages if s["status"] == "failed"]
    rest = [s for s in stages if s["status"] != "failed"]
    return failed_first + rest


def _understood_raw(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    for r in _stage_records(records):
        if r.get("stage") == "understood":
            return r.get("raw") if isinstance(r.get("raw"), dict) else {}
    return None


def _parse(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    understood_raw = _understood_raw(records)
    if understood_raw is None:
        return None
    understood_facts = next(
        (r.get("facts") or {} for r in _stage_records(records) if r.get("stage") == "understood"),
        {},
    )
    return {
        "raw": understood_raw.get("parser_raw"),
        "post_processed": understood_raw.get("derived"),
        "prompt_version": understood_facts.get("prompt_version"),
        # Not on every `understood` record today - the engine's success-path facts
        # (engine.py) do not carry `model`, only the failed-parse arm does. Left
        # None on the common (success) case rather than guessed.
        "model": understood_facts.get("model"),
    }


def _session_variables(session_vars_raw: Any) -> dict[str, Any]:
    """`{"session_vars": {"session_vars": {"variables": {...}}}}` - the SAME double
    nesting `engine.py`'s `received` stage stores (`raw={"session_vars": session_block}`
    over `jsc.get(jsc.get(session_block, "session_vars"), "variables")`)."""
    if not isinstance(session_vars_raw, dict):
        return {}
    outer = session_vars_raw.get("session_vars")
    if not isinstance(outer, dict):
        return {}
    inner = outer.get("session_vars")
    if not isinstance(inner, dict):
        return {}
    variables = inner.get("variables")
    return variables if isinstance(variables, dict) else {}


def _session(records: list[dict[str, Any]]) -> dict[str, Any]:
    received_raw = next(
        (r.get("raw") for r in _stage_records(records) if r.get("stage") == "received"),
        None,
    )
    before = _session_variables(received_raw)

    remembered = next((r for r in _stage_records(records) if r.get("stage") == "remembered"), None)
    remembered_raw = remembered.get("raw") if isinstance(remembered, dict) else None
    session_patch = (remembered_raw or {}).get("session_patch") if isinstance(remembered_raw, dict) else None
    after = (session_patch or {}).get("variables") if isinstance(session_patch, dict) else None
    # No patch written (refused / no memory to save / dry run) -> the memory is KEPT
    # exactly as it was, same rule `engine.py`'s own `memory_delta` call applies.
    if after is None:
        after = before

    delta = trace_mod.memory_delta(before=before, after=after)
    diff = [{"key": key, "change": "gained"} for key in delta["new"]] + [
        {"key": key, "change": "lost"} for key in delta["cleared"]
    ]
    diff.sort(key=lambda entry: entry["key"])
    return {"before": before, "after": after, "diff": diff}


def _tool(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    entries = _kind_records(records, "tool")
    if not entries:
        return None
    entry = entries[-1]  # the business lane calls at most one tool per turn today
    return {
        "name": entry.get("name"),
        "args": entry.get("args"),
        "envelope": _cap_envelope(entry.get("envelope")),
        "ms": entry.get("ms"),
    }


def _crossdomain(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "rung": e.get("rung"),
            "tool": e.get("tool"),
            "args": e.get("args"),
            "rows": e.get("rows"),
            "rendered": e.get("rendered"),
        }
        for e in _kind_records(records, "crossdomain")
    ]


def _reveals(records: list[dict[str, Any]]) -> dict[str, Any]:
    entries = _kind_records(records, "reveals")
    entry = entries[-1] if entries else {}
    return {
        "restricted_fields_seen": entry.get("restricted_fields_seen") or [],
        "granted": entry.get("granted") or [],
        "dropped": entry.get("dropped") or [],
    }


def _decay(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "slot": e.get("slot"),
            "value": e.get("value"),
            "set_at_turn": e.get("set_at_turn"),
            "age_turns": e.get("age_turns"),
            "age_minutes": e.get("age_minutes"),
            "reason": e.get("reason"),
        }
        for e in _kind_records(records, "decay")
    ]


def _focus(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "slot": e.get("slot"),
            "before": e.get("before"),
            "after": e.get("after"),
            "rule": e.get("rule"),
            "source": e.get("source"),
        }
        for e in _kind_records(records, "focus")
    ]


def _open_question(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    entries = _kind_records(records, "open_question")
    if not entries:
        return None
    entry = entries[-1]
    return {
        "before": entry.get("before"),
        "answer": entry.get("answer"),
        "after": entry.get("after"),
        "handler": entry.get("handler"),
        "outcome": entry.get("outcome"),
    }


def compose_trace_detail(row: ChatbotTurn) -> dict[str, Any]:
    records = _records(row)
    return {
        "stages": _stages(records),
        "parse": _parse(records),
        "decay": _decay(records),
        "open_question": _open_question(records),
        "focus": _focus(records),
        "tool": _tool(records),
        "crossdomain": _crossdomain(records),
        "reveals": _reveals(records),
        "session": _session(records),
    }
