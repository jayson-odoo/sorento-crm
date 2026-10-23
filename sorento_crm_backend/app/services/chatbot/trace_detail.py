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
import re
from typing import Any

from sqlalchemy.orm import Session

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
    """`{name, started_at, ms, status, summary, error, facts}`, the failing stage
    FIRST (AC-973) - an operator opening a failed turn should not have to scroll to
    find what broke.

    `facts` (browser pass, chatbot media-into-turn): every stage record already
    carries it, flattened to plain display values (`engine.py::_media_intake_facts`
    is the one that matters here - modality/decision/status/elapsed_ms/entities/
    attributes/notes/truncated, never a bare id) - dropped from this projection
    before now, which is why a media turn's own Stages tab showed the badge and the
    summary line but none of what was actually read.
    """
    stages = [
        {
            "name": r.get("stage"),
            "started_at": r.get("started_at"),
            "ms": r.get("ms"),
            "status": r.get("status"),
            "summary": r.get("summary"),
            "error": r.get("error"),
            "facts": r.get("facts") or {},
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
            # STOCK-MISS-RENDER: a rung the bridge did not climb says why
            # (`answer_bridge.answer_for`'s `primary_tool_not_run`); a climbed rung
            # keeps its five-key shape (`test_turn_detail_api.py` pins it).
            **({"skipped": e.get("skipped")} if e.get("skipped") else {}),
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


#: The `customer_scope` event's fields, in the order the panel prints them. Every scope
#: decision on a turn writes one (CHATBOT-SELFREF-SCOPE R4): the engine's gate, screen
#: and scoped-to-links pass, the fetch clamp and refusal, the tier-probe refusal, and the
#: B2 re-route - so a refusal explains itself on the trace.
_CUSTOMER_SCOPE_FIELDS = (
    "decision", "refused", "reason", "ids", "dropped", "kept", "typed", "self_reference", "tool", "offer_passed",
)


def _customer_scope(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"at": e.get("at"), **{k: e.get(k) for k in _CUSTOMER_SCOPE_FIELDS if e.get(k) is not None}}
        for e in _kind_records(records, "customer_scope")
    ]


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


#: `prompt_text` cap (AC-1549): 64 KB, code points (a trace's own text field, not the
#: byte-cap `_cap_envelope` above uses for a tool envelope).
PROMPT_TEXT_CHAR_CAP = 65_536


def _apply(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The turn re-architecture's `apply` stage record (AC-1549): verdict in, the one
    decision it was read as, state diff out, narrowing fired, reconciliation if any, the
    turn plan."""
    entries = _kind_records(records, "apply")
    if not entries:
        return None
    entry = entries[-1]
    return {
        "verdict": entry.get("verdict"),
        "decision": entry.get("decision"),
        "state_diff": entry.get("state_diff"),
        "narrowing": entry.get("narrowing"),
        "reconciled": entry.get("reconciled"),
        "plan": entry.get("plan"),
    }


def _memory(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The three memory shelves before/after, each with its own writer (AC-1549),
    plus the contact's context level, what this turn saved as a profile fact (S2 -
    always `[]` until then) and the open question (chatbot memory lane A, contract
    section 6)."""
    entries = _kind_records(records, "memory")
    if not entries:
        return None
    entry = entries[-1]
    return {
        "level": entry.get("level"),
        "focus": entry.get("focus"),
        "profile": entry.get("profile"),
        "episodes": entry.get("episodes"),
        "facts_saved": entry.get("facts_saved") or [],
        "open_question": entry.get("open_question"),
    }


def _context(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The per-layer token budget report (chatbot memory lane A, contract section
    6): `{level, layers: [{layer, est_tokens, cap, dropped}], total_est_tokens,
    cap}`, exactly as `turn/context.py::assemble` returns it - `None` on a turn
    that never reached a successful parse (no `context` event was ever added)."""
    entries = _kind_records(records, "context")
    if not entries:
        return None
    entry = entries[-1]
    return {
        "level": entry.get("level"),
        "layers": entry.get("layers") or [],
        "total_est_tokens": entry.get("total_est_tokens"),
        "cap": entry.get("cap"),
    }


def _order(row: ChatbotTurn, db: Session | None = None) -> dict[str, Any] | None:
    """The per-contact ordering ticket (chatbot memory lane A round 3, AC-MEM014) -
    read-only, nothing to set. `ticket`/`wait_ms` come off the turn's own "queued"
    STAGE record (`trace.py::record`, not a separate `add(kind, ...)` event) - S7
    mode only, absent on an unordered or dry-run turn, which is the common case in
    every environment without Redis ordering switched on. A queue TIMEOUT fails the
    turn AT that same stage and carries `ticket` there too (no `wait_ms`, since it
    never finished waiting), so a caller reads one shape either way.
    `previous`/`next` are this contact's neighbouring turns on the SAME `is_test`
    side, by `created_at` - never another contact's, never across worlds - and need a
    live session, which `compose_trace_detail` does not always have one to hand; a
    caller with a session passes it, and every other caller reads `None` here rather
    than opening one of its own (this module is otherwise a read-only projection of a
    single already-loaded row, contract with no DB dependency).
    """
    records = _records(row)
    queued_records = [r for r in _stage_records(records) if r.get("stage") == "queued"]
    queued = queued_records[-1] if queued_records else {}
    facts = queued.get("facts") or {}
    ticket = facts.get("ticket")
    wait_ms = facts.get("wait_ms")
    if ticket is None and wait_ms is None:
        return None
    if db is None:
        return {"ticket": ticket, "wait_ms": wait_ms, "previous": None, "next": None}

    earlier = (
        db.query(ChatbotTurn)
        .filter(
            ChatbotTurn.contact_respond_id == row.contact_respond_id,
            ChatbotTurn.is_test.is_(row.is_test),
            ChatbotTurn.created_at < row.created_at,
        )
        .order_by(ChatbotTurn.created_at.desc())
        .first()
    )
    later = (
        db.query(ChatbotTurn)
        .filter(
            ChatbotTurn.contact_respond_id == row.contact_respond_id,
            ChatbotTurn.is_test.is_(row.is_test),
            ChatbotTurn.created_at > row.created_at,
        )
        .order_by(ChatbotTurn.created_at.asc())
        .first()
    )
    return {
        "ticket": ticket,
        "wait_ms": wait_ms,
        "previous": _order_neighbor(earlier),
        "next": _order_neighbor(later),
    }


def _order_neighbor(row: ChatbotTurn | None) -> dict[str, Any] | None:
    if row is None:
        return None
    envelope = row.envelope if isinstance(row.envelope, dict) else {}
    inner = (envelope.get("message") or {}).get("message") or {}
    text_value = (inner.get("message") or {}).get("text") or ""
    # AC-MEM015: the neighbour's OWN ticket, off its OWN "queued" stage - so the
    # drawer's "ran after"/"next" can show "#N" without a second round trip. `None`
    # for a neighbour that never queued (ordering off, or a dry run).
    neighbor_records = [r for r in _stage_records(_records(row)) if r.get("stage") == "queued"]
    neighbor_ticket = ((neighbor_records[-1].get("facts") or {}) if neighbor_records else {}).get("ticket")
    return {
        "turn_id": row.id,
        "created_at": row.created_at,
        "message": str(text_value)[:120],
        "ticket": neighbor_ticket,
    }


def _prompt_text(records: list[dict[str, Any]]) -> str | None:
    """The rendered user block plus hint blocks, capped at 64 KB (AC-1549)."""
    entries = _kind_records(records, "prompt_text")
    if not entries:
        return None
    text = entries[-1].get("text")
    if not isinstance(text, str):
        return None
    return text[:PROMPT_TEXT_CHAR_CAP]


_HINT_WORDS = {
    "product": "a product",
    "category": "a product type",
    "product_type": "a product type",
    "specification": "a specification",
    "spec": "a specification",
    "attachment_type": "a file",
    "warehouse": "a warehouse",
    "brand": "a brand",
    "customer": "a customer",
    "sales_agent": "a sales agent",
    "order": "an order",
    "promotion": "a promotion",
    "product_attachment": "a product file",
    "inventory": "stock",
    "incoming": "incoming stock",
}


def _hint_words(hint: str) -> str:
    """A hint in plain words; one the table does not name still never shows an underscore."""
    return _HINT_WORDS.get(hint, hint.replace("_", " "))


_LIST_WORDS = {"attachment_type": "file type", "cert_kind": "certificate", "cert_scheme": "certificate scheme"}
_UNDERSCORED = re.compile(r"(?<=[A-Za-z0-9])_(?=[A-Za-z0-9])")
_UUID_LIKE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_CLASS_HINTS = ("category", "product_type")
LOOKED_UP_DETAIL_CAP = 8


def _say(text: Any) -> str:
    """Text with no snake_case word left in it."""
    return _UNDERSCORED.sub(" ", str(text))


def _fold(text: Any) -> str:
    from app.services.chatbot.head.candidates import _phrase

    return _phrase(text or "")


class _Lookups:
    """Registry labels, value labels and attachment type names, read once for a turn's detail;
    without a session (or when a read fails) the key or code itself, with no underscore."""

    def __init__(self, db: Session | None) -> None:
        self.specs: dict[str, tuple[str | None, dict[str, Any]]] = {}
        self.types: dict[str, str] = {}
        if db is None:
            return
        try:
            with db.begin_nested():
                from app.services import chatbot_prompt_vars as pv
                from app.services.product_spec_registry import active_registry

                for row in active_registry(db):
                    self.specs[row.spec_key] = (str(row.label) if row.label else None, dict(row.value_labels or {}))
                for row in [*pv._file_type_rows(db), *pv._cert_kind_rows(db)]:
                    name = str(row.get("type_name") or "").strip()
                    if name:
                        for key in (row.get("code"), name):
                            self.types[_fold(key)] = name
        except Exception:  # noqa: BLE001 - labels are a nicety; the raw words still read
            self.specs, self.types = {}, {}

    def label(self, key: Any) -> str:
        label = self.specs.get(str(key), (None, {}))[0]
        return label or _say(key).capitalize()

    def value(self, key: Any, value: Any) -> str:
        if str(key) in self.specs:
            from app.services.product_spec_registry import display_spec_value

            return _say(display_spec_value(value, self.specs[str(key)][1]))
        return _say(value)

    def type_name(self, code: Any) -> str:
        return self.types.get(_fold(code)) or _say(code)


def _result_text(note: dict[str, Any] | None, lk: _Lookups) -> dict[str, str]:
    """One entity's grounding outcome in plain words (CHAT-INDEX-VIZ wording table)."""
    if note is None:
        return {"outcome": "kept", "text": "Kept"}
    to = note.get("to")
    if isinstance(to, list):
        parts = []
        for item in to:
            if isinstance(item, dict):
                key = item.get("key")
                label = item.get("label") or (lk.label(key) if key else "")
                if item.get("value") is not None and label:
                    parts.append(f"{label}: {lk.value(key, item['value'])}")
                elif item.get("said"):
                    parts.append(str(item["said"]))  # the customer's own words, as typed
            elif str(item).strip():
                parts.append(str(item))
        if not parts:
            return {"outcome": "changed", "text": "Changed"}
        return {"outcome": "changed", "text": "Changed: read as " + "; ".join(parts)}
    to = str(to)
    if to == "dropped: a finish short form, no warehouse on file":
        return {"outcome": "dropped", "text": "Dropped: a finish code ending, not on the warehouse list"}
    if to in ("dropped: not on the closed lists", "dropped: not a listed document type"):
        return {"outcome": "dropped", "text": "Dropped: not on the file type list"}
    if to == "unknown product type":
        return {"outcome": "dropped", "text": "Dropped: not a known product type"}
    if to.startswith("on the ") and " list: " in to:
        listed, _, code = to[len("on the "):].partition(" list: ")
        return {"outcome": "kept", "text": f"Kept: on the {_LIST_WORDS.get(listed, _say(listed))} list ({lk.type_name(code)})"}
    if to == "canonical dropped: not on the candidate block":
        return {"outcome": "changed", "text": "Changed: product code not among the matches, removed"}
    if to.startswith("canonical refused:"):
        return {"outcome": "changed", "text": "Changed: several product codes fit, the bot asks which"}
    if to.startswith("listed product type: "):
        return {"outcome": "changed", "text": f"Changed: read as the product type {_say(to[len('listed product type: '):])}"}
    if to == "category":
        return {"outcome": "changed", "text": "Changed: read as a product type"}
    return {"outcome": "changed", "text": f"Changed: read as {_say(to)}"}


def _noun_of(note: dict[str, Any] | None) -> str | None:
    """`file type` / `certificate` / `certificate scheme`, from a kept-on-a-list note."""
    to = str((note or {}).get("to") or "")
    if to.startswith("on the ") and " list: " in to:
        listed = to[len("on the "):].partition(" list: ")[0]
        return _LIST_WORDS.get(listed)
    return None


def _understood_text(entity: dict[str, Any], lk: _Lookups, noun: str | None = None) -> str:
    head = f'"{entity.get("raw")}"'
    hint = str(entity.get("hint") or "")
    key, spec_value = entity.get("spec_key"), entity.get("spec_value")
    value = entity.get("canonical_code") or entity.get("listed_item")
    if not hint:
        return f"{head}: {value}" if value else head
    if hint in _CLASS_HINTS and (value or spec_value):
        return f"{head} read as product type {_say(value or spec_value)}"
    if key and spec_value is not None:
        return f"{head} read as {lk.label(key)}: {lk.value(key, spec_value)}"
    if hint == "product" and value:
        return f"{head} read as product {value}"
    if hint == "attachment_type" and value:
        return f"{head} read as {noun or 'file type'} {lk.type_name(value)}"
    text = f"{head} read as {_hint_words(hint)}"
    return f"{text}: {value}" if value else text


_PLUMBING_ARGS = frozenset({"contact_id", "space_id", "dry_run", "limit", "offset"})
#: Args that carry the customer's own words: shown as typed.
_FREE_TEXT_ARGS = frozenset({"query", "q", "text", "search"})


def _arg_text(value: Any) -> str:
    return "yes" if value is True else "no" if value is False else str(value)


def _looked_up(records: list[dict[str, Any]], lk: _Lookups) -> dict[str, Any] | None:
    """What the bot looked up this turn (its tool call), in plain words. Codes (`*_code`,
    `*_codes` args) and free text stay as stored; internal ids (`*_id`, `*_ids`) and plumbing
    args are left out; a registry spec key shows its label and value label."""
    entries = _kind_records(records, "tool")
    if not entries or not entries[-1].get("name"):
        return None
    entry = entries[-1]
    details: list[str] = []
    args = entry.get("args") if isinstance(entry.get("args"), dict) else {}
    for key, value in args.items():
        if key in _PLUMBING_ARGS or key.endswith(("_id", "_ids")) or value is None or isinstance(value, dict):
            continue
        items = [v for v in (value if isinstance(value, list) else [value]) if v not in (None, "") and not isinstance(v, (dict, list))]
        items = [v for v in items if not _UUID_LIKE.match(str(v))]
        if not items:
            continue
        if key in lk.specs:
            label, text = lk.label(key), ", ".join(lk.value(key, v) for v in items)
        elif key.endswith(("_code", "_codes")) or key in _FREE_TEXT_ARGS:
            label, text = _say(key).capitalize(), ", ".join(str(v) for v in items)
        else:
            label, text = _say(key).capitalize(), _say(", ".join(_arg_text(v) for v in items))
        details.append(f"{label}: {text}")
        if len(details) == LOOKED_UP_DETAIL_CAP:
            break
    what = _say(entry["name"])
    return {"what": what[:1].upper() + what[1:], "details": details}


def _index_match(records: list[dict[str, Any]], db: Session | None = None) -> dict[str, Any] | None:
    """CHAT-INDEX-VIZ: the word -> matched entry -> what the bot understood -> kept/dropped flow of
    a turn that ran in index mode; None for a turn with no `closed_lists_index` event."""
    events = _kind_records(records, "closed_lists_index")
    if not events:
        return None
    event = events[-1]
    lk = _Lookups(db)
    matches = [m for m in event.get("matches") or [] if isinstance(m, dict)]
    words = [str(w) for w in event.get("words") or []]
    plain = [m for m in matches if not m.get("held") and m.get("word")]
    matched_words: set[str] = set()
    for m in plain:
        matched_words.update(_fold(m["word"]).split())

    rows: list[dict[str, Any]] = []
    by_word: dict[str, dict[str, Any]] = {}
    for m in plain:
        row = by_word.get(m["word"])
        if row is None:
            row = by_word[m["word"]] = {"word": m["word"], "matched": [], "parser_got": [], "understood": [], "result": []}
            rows.append(row)
        row["matched"].append({
            "plain": m.get("plain") or _say(m.get("entry")),
            "source": m.get("source") or str(m.get("list") or ""),
            "close_spelling": bool(m.get("close_spelling")),
        })
        if m.get("line") not in row["parser_got"]:
            row["parser_got"].append(m.get("line"))

    notes = []
    for r in _kind_records(records, "grounding"):
        notes += [n for n in r.get("changes") or [] if isinstance(n, dict)]
    raw = _understood_raw(records) or {}
    parser_raw = raw.get("parser_raw") if isinstance(raw.get("parser_raw"), dict) else {}
    entities = [e for e in parser_raw.get("entities") or [] if isinstance(e, dict)]

    leftover: list[dict[str, str]] = []
    for entity in entities:
        folded = f" {_fold(entity.get('raw'))} "
        row = next((r for r in rows if folded == f" {_fold(r['word'])} "), None) or next(
            (r for r in rows if f" {_fold(r['word'])} " in folded), None
        )
        note = next(
            (n for n in notes if n.get("from") == entity.get("hint") and _fold(n.get("raw")) == _fold(entity.get("raw"))),
            None,
        )
        text = _understood_text(entity, lk, _noun_of(note))
        result = _result_text(note, lk)
        if row is None:
            leftover.append({"text": text, "outcome": result["outcome"], "result": result["text"]})
        else:
            row["understood"].append({"text": text})
            row["result"].append(result)

    return {
        "words": [{"text": w, "matched": _fold(w) in matched_words} for w in words],
        "rows": rows,
        "held": [m.get("plain") or _say(m.get("entry")) for m in matches if m.get("held")],
        "not_from_lists": leftover,
        "failed": bool(event.get("failed")),
        "looked_up": _looked_up(records, lk),
    }


def compose_trace_detail(row: ChatbotTurn, db: Session | None = None) -> dict[str, Any]:
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
        "customer_scope": _customer_scope(records),
        "session": _session(records),
        "apply": _apply(records),
        "memory": _memory(records),
        "context": _context(records),
        "order": _order(row, db),
        "prompt_text": _prompt_text(records),
        "index_match": _index_match(records, db),
    }
