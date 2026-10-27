"""Parser gold runner (CHAT-CODE-LOOKUP R2-1): one gold message x N repeats through the semantic parser only.

usage (cwd = the backend dir of the checkout under test):
  python -m scripts.chatbot_eval.parser_gold live --gold F --out F --max-usd X --require-key-last4 XXXX \
      --prompt-version-id ID --repeats N [--closed-lists-mode block|index]
      [--reasoning-effort off|low]
      (calls ONLY the parser, on the pinned prompt version, with the user turn the engine builds for a fresh
      turn and the candidate block when the version carries CLOSED LISTS; every DB session is rolled back; spend
      is capped by --max-usd and only a provider key ending with --require-key-last4 may spend.
      --closed-lists-mode forces `chatbot_closed_lists_mode` for this process only, never in the DB; without it
      the DB value is used. The header line and every row name the mode the run used: off when the version
      carries no CLOSED LISTS section. --reasoning-effort forces the stored parser setting
      `chatbot_parser_reasoning_effort` for this process only, never in the DB ("off" sends none, as the setting's
      off does); without it the DB value is used. Header and rows record the effort the parse read)

Imports only the stdlib at module level and `app.*` inside functions, like replay.py. Output rows carry ids,
the pass flag, the reasons, the spend and the parse's own routing fields; each row's entities carry `raw`,
a span of the gold message (synthetic and committed, so it holds no real customer text).
"""
from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import re
import sys
import threading
import time
from typing import Any

#: The parse's own cost, as the provider reported it on the result's `usage` (None when it reported none).
USAGE_KEYS = ("prompt_tokens", "cached_tokens", "completion_tokens", "reasoning_tokens")

EXPECT_KEYS = frozenset({
    "products_only",
    "status", "not_status", "domain_hint", "intent_hint", "product", "no_attribute", "customer", "canonical",
    "attributes_only", "attributes_include", "attachment_types", "warehouse", "promotion_kind", "is_active",
    "continues", "topic_reset", "answer_mode", "picked", "reference_positions", "entity_op", "broaden_axis",
    "state_ops_include", "state_ops_exclude",
    # REPORT-SMART-L v92: the report fields, each compared with the parse field of the same name.
    "order_status", "group_by", "measure", "basis", "compare_to", "sales_channel", "ranking_refine",
    # REPORT-SMART-L delivery gold: the paper codes list (["DO"]), plain equality.
    "document",
    # REPORT-SMART-L v103: true means the parse carries no entity at all (an axis phrase is no entity); checked only when true, false is a no-op.
    "entities_none",
    # REPORT-SMART-L R5 row 13: the parse's `self_reference`, null read as false.
    "self_reference",
    # REPORT-SMART-L R6: the parse's `by_words` (any string: the message names an axis; null: it names none; graded only when the parse carries the key).
    "by_words",
    # CHAT-V66-REGRESSIONS: the access levels the message selects, compared as a set, case aside.
    "access_levels",
})
#: The expect keys read straight off the verdict (null means null or absent).
_REPORT_KEYS = ("order_status", "group_by", "measure", "basis", "compare_to", "sales_channel", "ranking_refine",
                "document")
#: LEAN v90: the type each of these expect values must have (null allowed where listed).
_EXPECT_TYPES: dict[str, tuple[type, ...]] = {
    "products_only": (list,),
    "access_levels": (list,),
    "entities_none": (bool,),
    "self_reference": (bool,),
    "by_words": (str, type(None)),
    "is_active": (bool, type(None)),
    "continues": (bool,),
    "promotion_kind": (str, type(None)),
    "topic_reset": (bool,),
    "answer_mode": (str, type(None)),
    "picked": (list,),
    "reference_positions": (list,),
    "entity_op": (str, type(None)),
    "broaden_axis": (str, type(None)),
    "state_ops_include": (list,),
    "state_ops_exclude": (list,),
}
#: PARSER-TEMPLATE F1-B: what a gold row may say the conversation held before its message. Each
#: value is the text as the user block shows it, or null.
#: `last_list` and `pending_task` are the State block's own rendered values; `open_question` may be the
#: JSON object the real State line and `parser.open_question_line` both dump.
CONTEXT_KEYS = frozenset({"previous_reply", "subject", "open_question", "last_list", "pending_task", "reply_to"})


def _valid_context(context: Any) -> bool:
    return (
        isinstance(context, dict)
        and set(context) <= CONTEXT_KEYS
        and all(
            value is None or isinstance(value, str) or (key == "open_question" and isinstance(value, dict))
            for key, value in context.items()
        )
    )


def load_gold(path: Any) -> list[dict[str, Any]]:
    """The gold rows `{id, message, expect}` (plus `context` when the row has one); ValueError on bad
    JSON, a blank message, a repeated id, an unknown expect key or a malformed context."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {n}: not json") from exc
            if not isinstance(row, dict) or not str(row.get("id") or "").strip():
                raise ValueError(f"line {n}: no id")
            if row["id"] in seen:
                raise ValueError(f"line {n}: repeated id {row['id']}")
            if not str(row.get("message") or "").strip():
                raise ValueError(f"line {n}: blank message")
            expect = row.get("expect", {})
            if not isinstance(expect, dict) or set(expect) - EXPECT_KEYS:
                raise ValueError(f"line {n}: unknown expect key")
            if "warehouse" in expect and not (
                isinstance(expect["warehouse"], list) and all(isinstance(w, str) for w in expect["warehouse"])
            ):
                raise ValueError(f"line {n}: warehouse must be a list of warehouse words")
            bad = [k for k, types in _EXPECT_TYPES.items() if k in expect and not isinstance(expect[k], types)]
            if bad:
                raise ValueError(f"line {n}: {bad[0]} has the wrong type")
            if "products_only" in expect and not all(isinstance(c, str) for c in expect["products_only"]):
                raise ValueError(f"line {n}: products_only must be a list of product codes")
            if "context" in row and not _valid_context(row["context"]):
                raise ValueError(f"line {n}: context must map {sorted(CONTEXT_KEYS)} to text or null")
            seen.add(row["id"])
            gold = {"id": row["id"], "message": row["message"], "expect": expect}
            if "context" in row:
                gold["context"] = row["context"]
            rows.append(gold)
    return rows


def _fold(value: Any) -> str:
    return re.sub(r"[^0-9a-z]", "", str(value or "").casefold())


def _answer_fields(answer: Any) -> dict[str, Any] | None:
    """The parse's `open_question_answer` as a row records it: mode, picked, items."""
    if not isinstance(answer, dict):
        return None
    return {k: answer.get(k) for k in ("mode", "picked", "items")}


def _state_change_fields(changes: Any) -> list[dict[str, Any]] | None:
    """The parse's `state_changes` as a row records them, or None when the prompt has none."""
    if not isinstance(changes, list):
        return None
    return [{k: c.get(k) for k in ("op", "axis", "position")} for c in changes if isinstance(c, dict)]


def _warehouse_raws(entities: list[dict[str, Any]]) -> list[Any]:
    return [e.get("raw") for e in entities if e.get("hint") == "warehouse"]


def grade_parse(verdict: dict[str, Any], expect: dict[str, Any]) -> tuple[bool, list[str]]:
    """(passed, reasons) for one parse against one expectation; every failed check is reported."""
    reasons: list[str] = []
    verdict = verdict if isinstance(verdict, dict) else {}
    entities = [e for e in verdict.get("entities") or [] if isinstance(e, dict)]
    if "status" in expect and verdict.get("status") != expect["status"]:
        reasons.append(f"status {verdict.get('status')!r} != {expect['status']!r}")
    if "not_status" in expect and verdict.get("status") in expect["not_status"]:
        reasons.append(f"status {verdict.get('status')!r} is forbidden")
    for key in ("domain_hint", "intent_hint"):
        if key in expect and verdict.get(key) != expect[key]:
            reasons.append(f"{key} {verdict.get(key)!r} != {expect[key]!r}")
    if "product" in expect:
        codes = {_fold(e.get("canonical_code")) for e in entities if e.get("hint") == "product"}
        if _fold(expect["product"]) not in codes:
            reasons.append(f"no product entity {expect['product']!r}")
    if "canonical" in expect:
        picks = [_fold(e.get("canonical_code")) for e in entities if e.get("hint") == "product"]
        if expect["canonical"] is None:
            if any(picks):
                reasons.append("a product entity has a canonical_code")
        elif _fold(expect["canonical"]) not in picks:
            reasons.append(f"no product canonical_code {expect['canonical']!r}")
    if "attributes_only" in expect:
        allowed = {str(a).casefold() for a in expect["attributes_only"] or []}
        extra = sorted({str(a).casefold() for a in verdict.get("requested_attributes") or []} - allowed)
        if extra:
            reasons.append(f"attributes outside the allowed set: {extra}")
    if "attributes_include" in expect:
        asked = {_fold(a) for a in verdict.get("requested_attributes") or []}
        missing = [a for a in expect["attributes_include"] or [] if _fold(a) not in asked]
        if missing:
            reasons.append(f"attributes not requested: {missing}")
    if "attachment_types" in expect:
        from app.services.chatbot.head.closed_lists_prompt import NOT_LISTED

        # Only an entity downstream grounds names a type: head/grounding drops an unconfident
        # pick and a NOT_LISTED one (grounding._on_closed_lists).
        grounded = [
            e for e in entities if e.get("hint") == "attachment_type"
            and e.get("confident") is not False and e.get("listed_item") != NOT_LISTED
        ]
        named = {_fold(e.get(k)) for e in grounded for k in ("canonical_code", "listed_item") if e.get(k)}
        missing = [t for t in expect["attachment_types"] or [] if _fold(t) not in named]
        if missing:
            reasons.append(f"no attachment_type entity for {missing}")
    if "no_attribute" in expect:
        asked = {str(a).casefold() for a in verdict.get("requested_attributes") or []}
        if str(expect["no_attribute"]).casefold() in asked:
            reasons.append(f"attribute {expect['no_attribute']!r} requested")
    if "customer" in expect:
        has = any(e.get("hint") == "customer" for e in entities)
        if has != bool(expect["customer"]):
            reasons.append("customer entity " + ("missing" if expect["customer"] else "present"))
    if "access_levels" in expect:
        got = {_fold(a) for a in verdict.get("access_levels") or []}
        if got != {_fold(a) for a in expect["access_levels"]}:
            reasons.append(f"access_levels {verdict.get('access_levels')!r} != {expect['access_levels']!r}")
    if "promotion_kind" in expect and _fold(verdict.get("promotion_kind")) != _fold(expect["promotion_kind"]):
        reasons.append(f"promotion_kind {verdict.get('promotion_kind')!r} != {expect['promotion_kind']!r}")
    if "is_active" in expect and verdict.get("is_active") is not expect["is_active"]:
        reasons.append(f"is_active {verdict.get('is_active')!r} != {expect['is_active']!r}")
    if "continues" in expect:
        flagged = verdict.get("continuation") is True
        if expect["continues"]:
            # Continuing the listed set: the paging flag, and no new file ask beside it (turn_runtime.with_set_more).
            if not flagged or verdict.get("domain_hint") == "product_attachment" or any(
                e.get("hint") == "attachment_type" for e in entities
            ):
                reasons.append(f"continues: continuation {verdict.get('continuation')!r}, "
                               f"domain_hint {verdict.get('domain_hint')!r}, or a file type entity")
        elif flagged:
            reasons.append("continues: continuation is true")
    if "warehouse" in expect:
        # The parse's own warehouse words, folded, as a set: [] means no warehouse entity at all.
        got = {_fold(raw) for raw in _warehouse_raws(entities)}
        want = {_fold(w) for w in expect["warehouse"] or []}
        if got != want:
            reasons.append(f"warehouse raws {sorted(got)} != {sorted(want)}")
    if "products_only" in expect:
        allowed = {_fold(c) for c in expect["products_only"]}
        stray = sorted(
            {_fold(e.get("canonical_code")) for e in entities if e.get("hint") == "product"} - allowed
        )
        if stray:
            reasons.append(f"product entities outside the allowed set: {stray}")
    if "self_reference" in expect and (verdict.get("self_reference") is True) is not expect["self_reference"]:
        reasons.append(f"self_reference {verdict.get('self_reference')!r} != {expect['self_reference']!r}")
    if "by_words" in expect and "by_words" in verdict:
        # Null against non-null only (the words themselves vary), and only when the prompt in use emits the key.
        named = bool(str(verdict.get("by_words") or "").strip())
        if named is not (expect["by_words"] is not None):
            reasons.append(f"by_words {verdict.get('by_words')!r}: expected {'words' if expect['by_words'] is not None else 'null'}")
    if expect.get("entities_none") and entities:
        reasons.append(f"entities {[(e.get('hint'), e.get('raw')) for e in entities]} but none expected")
    answer = verdict.get("open_question_answer")
    answer = answer if isinstance(answer, dict) else {}
    if "topic_reset" in expect and (verdict.get("topic_reset") is True) is not expect["topic_reset"]:
        reasons.append(f"topic_reset {verdict.get('topic_reset')!r} != {expect['topic_reset']!r}")
    if "answer_mode" in expect and answer.get("mode") != expect["answer_mode"]:
        reasons.append(f"answer_mode {answer.get('mode')!r} != {expect['answer_mode']!r}")
    if "picked" in expect and list(answer.get("picked") or []) != expect["picked"]:
        reasons.append(f"picked {answer.get('picked')!r} != {expect['picked']!r}")
    if "reference_positions" in expect and list(verdict.get("reference_positions") or []) != expect["reference_positions"]:
        reasons.append(f"reference_positions {verdict.get('reference_positions')!r} != {expect['reference_positions']!r}")
    for key in ("entity_op", "broaden_axis"):
        if key in expect and verdict.get(key) != expect[key]:
            reasons.append(f"{key} {verdict.get(key)!r} != {expect[key]!r}")
    if ("state_ops_include" in expect or "state_ops_exclude" in expect) and "state_changes" in verdict:
        ops = {c.get("op") for c in verdict.get("state_changes") or [] if isinstance(c, dict)}
        missing = [o for o in expect.get("state_ops_include") or [] if o not in ops]
        if missing:
            reasons.append(f"state_changes lack ops {missing}")
        present = [o for o in expect.get("state_ops_exclude") or [] if o in ops]
        if present:
            reasons.append(f"state_changes carry forbidden ops {present}")
    for key in _REPORT_KEYS:
        if key in expect and verdict.get(key) != expect[key]:
            reasons.append(f"{key} {verdict.get(key)!r} != {expect[key]!r}")
    return (not reasons, reasons)


def summarise(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Per case id: how many repeats ran and how many passed."""
    out: dict[str, dict[str, int]] = {}
    for row in rows:
        cell = out.setdefault(str(row["id"]), {"n": 0, "passed": 0})
        cell["n"] += 1
        cell["passed"] += 1 if row.get("passed") else 0
    return out


def _state_block(context: dict[str, Any]) -> str:
    """A gold context as the `State:` block, in `chat_state.render`'s four-line shape (the gold
    gives the subject already rendered, so there is no Focus to view)."""
    question = context.get("open_question")
    last = context.get("last_list")
    if not last:
        last_line = "- last list: none"
    else:
        last_line = "- last list " + last if last.startswith("(") else "- last list: " + last
    return "\n".join([
        "State:",
        f"- subject: {context.get('subject') or 'none'}",
        "- open question: " + (json.dumps(question, ensure_ascii=False) if question else "none"),
        last_line,
        "- pending task: " + (context.get("pending_task") or "none"),
    ])


def _subject_values(subject: Any) -> dict[str, list[str]]:
    """A gold `subject` (the State block's rendered text, `chat_state._subject_text`) back to its key -> values;
    the held domain is not a value."""
    out: dict[str, list[str]] = {}
    for part in str(subject or "").split("; "):
        key, _sep, value = part.partition(" ")
        if key and value and key != "domain":
            out[key] = [v for v in value.split(", ") if v]
    return out


def _fresh_turn(message: str) -> tuple[Any, str]:
    """A fresh text turn as the engine reads it: its UserTurn (`user_turn.from_envelope`) and the
    `Current user message` text (`engine.build_latest_user_message`), both off a text envelope."""
    from app.services.chatbot import engine
    from app.services.chatbot import user_turn as user_turn_mod
    from app.services.chatbot.contracts import Envelope

    # The contact id only satisfies the envelope's schema: neither reader looks at it.
    text_message = {"message": {"message": {"type": "text", "text": message}}}
    envelope = Envelope(message=text_message, contact={"id": "parser-gold"})
    return user_turn_mod.from_envelope(envelope), engine.build_latest_user_message(envelope)


def _mode_used(config: Any) -> str:
    """The closed lists mode the config renders: off when the version carries no CLOSED LISTS section."""
    if not getattr(config, "closed_lists", False):
        return "off"
    return "index" if getattr(config, "closed_lists_index", False) else "block"


#: The `span_extract` event of this thread's latest `_parse_one` (None for a version without the span marker).
_SPAN = threading.local()


def _parse_one(message: str, config: Any, factory: Any, context: dict[str, Any] | None = None) -> Any:
    """The parser's emission for one message, with the user turn the engine builds: for a turn with no
    history (no held product, so no held ids), or (F1-B) for a gold `context` rendered through the same
    ContextLayers, as the `State:` block when the version asks for one and as the legacy Current subject /
    Open question lines otherwise. Index mode renders as the engine does: the candidate block with the
    index lines and no Product types / Product details lines."""
    from app.models.base import set_company_scope
    from app.services.chatbot import engine, turn_runtime
    from app.services.chatbot.head import lookup_lists, parser
    from app.services.chatbot.turn import context as context_mod
    from app.services.company_scope import DEFAULT_COMPANY_ID
    from app.services.reports.ask import SALES_CHANNELS

    user_turn, latest_user_message = _fresh_turn(message)
    _SPAN.event = None
    held = context or {}
    # CHAT-V66-REGRESSIONS: a lookup version gets the engine's lookup blocks (the message's own text plus the values the
    # row's subject holds) and loses the per-turn lists, as `engine.run_turn` builds it. The gold contact resolves to
    # no one, so no Salesperson or Customer block (staff-only blocks the harness never sees).
    spans = bool(getattr(config, "lookup_spans", False))
    lookup = bool(getattr(config, "lookup_lists", False)) or spans
    lookup_lines = None
    span_prep = None
    db = factory()
    try:
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        brands = turn_runtime.active_brands(db)
        promotion_kinds = turn_runtime.promotion_kind_rows(db)
        lists_free = config.closed_lists_index or lookup
        product_types = None if lists_free else turn_runtime.product_type_names(db)
        product_details = None if lists_free else turn_runtime.product_detail_values(db)
        lines, _listed, _picks = (
            engine._candidate_lines(db, user_turn, [], code_lookup=config.code_lookup, index=config.closed_lists_index)
            if config.closed_lists
            else (None, frozenset(), {})
        )
        if spans:
            # ENTITY-EXTRACT-MATCH S2: the span seam, as the engine runs it (the call itself after the session closes).
            span_prep = engine._span_prep(
                db, user_turn.own_text, frozenset(), "parser-gold", None, brands,
                lookup_lists.held_values(_subject_values(held.get("subject"))), None,
            )
        elif lookup:
            lookup_lines, _event = engine._lookup_lines(
                db, user_turn.own_text, config, frozenset(), "parser-gold", None, brands,
                lookup_lists.held_values(_subject_values(held.get("subject"))),
            )
    finally:
        db.close()
    if span_prep is not None:
        lookup_lines, _event, _SPAN.event = engine._span_lookup(
            span_prep, session_factory=factory, contact_respond_id="parser-gold", dry_run=True, turn_id=None
        )
    # As the engine: an empty state adds no block.
    held_any = bool(
        held.get("subject") or held.get("open_question") or held.get("last_list") or held.get("pending_task")
    )
    state = _state_block(held) if config.state_block and held_any else None
    layers = context_mod.ContextLayers(
        # A quote renders only in the layered (non-off) layout, as the engine's levels do; a row
        # without one keeps the legacy byte-identical block.
        level="conversation" if held.get("reply_to") else "off", profile_facts=None, summaries=None, earlier_messages=None,
        previous_response=held.get("previous_reply"),
        current_subject=None if state else held.get("subject"),
        pending_kind=None, pending_options=None, settings_profile_line=None,
        current_message=latest_user_message, reply_to=held.get("reply_to"), media_line=None,
        brands=None if lookup else brands, promotion_kinds=None if lookup else promotion_kinds,
        # REPORT-SMART-L R9: as the engine, only when the prompt names the line (`ParserConfig.sales_channels`).
        sales_channels=list(SALES_CHANNELS) if getattr(config, "sales_channels", True) and not lookup else None,
        product_types=product_types, product_details=product_details, candidate_lines=lines,
        lookup_lines=lookup_lines or None,
        open_question_line=None if state else parser.open_question_line(held.get("open_question")),
        state_block=state,
    )
    user_block, _report = context_mod.assemble(layers)
    # The parser call alone is timed (the engine's own `parse_started` span), not the user turn build.
    started = time.perf_counter()
    out = parser.parse(config, user_block)
    ms = round((time.perf_counter() - started) * 1000)
    if not isinstance(out, dict):
        return out  # not an emission: run_live records the error
    return parser.ParsedOutput(dict(out), {**(getattr(out, "usage", None) or {}), "parser_ms": ms})


def _pinned_version(session_factory: Any, version_id: str) -> int:
    """The stored version number of a pinned parser prompt. ValueError when the id is not a stored
    version of the parser prompt (the registry would fall back silently) or when it carries a label
    (a labelled version is what production reads; a gold run pins an unlabelled one)."""
    from app.models.ai_prompt import AIPromptLabel, AIPromptVersion
    from scripts.chatbot_eval import replay

    if not replay._pin_resolves(session_factory, version_id):
        raise ValueError("prompt_version_id is not a stored version of the parser prompt")
    db = session_factory()
    try:
        number = db.query(AIPromptVersion.version).filter(AIPromptVersion.id == version_id).scalar()
        labelled = db.query(AIPromptLabel.id).filter(AIPromptLabel.version_id == version_id).first() is not None
    finally:
        db.close()
    if labelled:
        raise ValueError("prompt_version_id carries a label; pin an unlabelled version")
    return int(number)


@contextlib.contextmanager
def _forced_mode(mode: str | None) -> Any:
    """`chatbot_closed_lists_mode` forced for this process while the run lasts (the reader the parser's
    `resolve_config` calls answers `mode`); the database is never written. None leaves the DB value."""
    if mode is None:
        yield
        return
    from unittest import mock

    from app.services.chatbot.head import closed_lists_index

    with mock.patch.object(closed_lists_index, "read_mode", lambda db: mode):
        yield


@contextlib.contextmanager
def _forced_effort(effort: str | None) -> Any:
    """`chatbot_parser_reasoning_effort` forced for this process while the run lasts (the reader the parser's
    `resolve_config` calls, `parser.reasoning_effort_setting`, answers `effort`); the database is never written
    and the provider request is the product's own. None leaves the DB value."""
    if effort is None:
        yield
        return
    from unittest import mock

    from app.services.chatbot.head import parser

    with mock.patch.object(parser, "reasoning_effort_setting", lambda db: effort):
        yield


def run_live(rows: list[dict[str, Any]], *, session_factory: Any, version_id: str, repeats: int, max_usd: float,
             require_key_last4: str, on_row: Any = None, closed_lists_mode: str | None = None,
             on_start: Any = None, reasoning_effort: str | None = None) -> list[dict[str, Any]]:
    """Each gold message x `repeats` through the parser alone; stops cleanly at the spend cap or a wrong key.
    `closed_lists_mode` ("block" | "index") forces the mode in-process, `reasoning_effort` (one of
    `parser.REASONING_EFFORTS`) the stored parser effort; `on_start` gets the run header."""
    from app.services.chatbot import engine
    from app.services.chatbot.head import closed_lists_index, parser
    from scripts.chatbot_eval import replay
    from app.services.company_scope import register_company_scope_listeners

    if closed_lists_mode is not None and closed_lists_mode not in closed_lists_index.MODES:
        raise ValueError(f"closed_lists_mode must be one of {sorted(closed_lists_index.MODES)}")
    if reasoning_effort is not None and reasoning_effort not in parser.REASONING_EFFORTS:
        raise ValueError(f"reasoning_effort must be one of {sorted(parser.REASONING_EFFORTS)}")
    register_company_scope_listeners()  # idempotent; without it set_company_scope filters nothing

    if not replay._valid_last4(require_key_last4):
        raise ValueError("require_key_last4 must be exactly 4 non-blank characters")
    total = replay._new_usage()
    total.update(max_calls=None, max_usd=max_usd, stop=None, require_key_last4=require_key_last4)
    out: list[dict[str, Any]] = []
    previous_disable = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        with contextlib.ExitStack() as stack:
            replay._guard_network(stack, [], replay.MODEL_HOSTS)
            stack.enter_context(_forced_mode(closed_lists_mode))
            stack.enter_context(_forced_effort(reasoning_effort))
            usage = replay._new_usage()
            stack.enter_context(replay._metered(usage, total))
            with replay._rolled_back(session_factory) as factory:
                db = factory()
                try:
                    # The engine's own CURRENT DATE text (Malaysia time, its format), so the system prompt is its.
                    config = parser.resolve_config(
                        db, current_date=engine._current_date_directive(), override_version_id=version_id
                    )
                finally:
                    db.close()
                mode = _mode_used(config)
                effort = getattr(config, "reasoning_effort", "off")
                if reasoning_effort is not None and config.provider != "openai":
                    raise ValueError(f"reasoning_effort is forced on OpenAI only, not {config.provider!r}")
                if on_start is not None:
                    on_start({"prompt_version": config.prompt_version, "closed_lists_mode": mode,
                              "forced": closed_lists_mode is not None, "reasoning_effort": effort,
                              "reasoning_forced": reasoning_effort is not None})
                for case in rows:
                    for repeat in range(repeats):
                        before = total["usd"]
                        row: dict[str, Any] = {
                            "id": case["id"], "repeat": repeat, "prompt_version": config.prompt_version,
                            "closed_lists_mode": mode, "reasoning_effort": effort,
                        }
                        try:
                            parsed = _parse_one(case["message"], config, factory, context=case.get("context"))
                            if getattr(_SPAN, "event", None):  # S2: did the span call fall back to the n-gram lines
                                row.update(span_fallback=bool(_SPAN.event.get("fallback")),
                                           span_fallback_reason=_SPAN.event.get("fallback_reason"))
                            usage = getattr(parsed, "usage", None) or {}
                            row.update({k: usage.get(k) for k in (*USAGE_KEYS, "parser_ms")})
                            verdict = dict(parsed)
                            passed, reasons = grade_parse(verdict, case["expect"])
                            entities = [e for e in verdict.get("entities") or [] if isinstance(e, dict)]
                            row.update(
                                passed=passed, reasons=reasons,
                                **{k: verdict.get(k) for k in ("status", "domain_hint", "intent_hint", "requested_attributes", "entities",
                                                  "document", "order_status")},
                                warehouse=_warehouse_raws(entities),
                                **{k: verdict.get(k) for k in ("topic_reset", "entity_op", "broaden_axis", "reference_positions")},
                                open_question_answer=_answer_fields(verdict.get("open_question_answer")),
                                state_changes=_state_change_fields(verdict.get("state_changes")),
                            )
                        except replay._CapStop as stop:
                            total["stop"] = total.get("stop") or stop.reason
                            row.update(passed=False, reasons=[f"stopped: {stop.reason}"])
                        except Exception as exc:  # noqa: BLE001 - the type only, never message text
                            row.update(passed=False, reasons=[f"error: {type(exc).__name__}"])
                        row["usd"] = round(total["usd"] - before, 6)
                        out.append(row)
                        if on_row is not None:
                            on_row(row)
                        if total.get("stop"):
                            return out
    finally:
        logging.disable(previous_disable)
    return out


def _refuse(message: str) -> int:
    print(f"refused: {message}", file=sys.stderr)
    return 2


def _cmd_live(args: argparse.Namespace) -> int:
    if args.max_usd is None or args.max_usd <= 0:
        return _refuse("--max-usd is required and must be positive")
    last4 = args.require_key_last4
    if not isinstance(last4, str) or len(last4) != 4 or any(c.isspace() for c in last4):
        return _refuse("--require-key-last4 is required: exactly 4 non-blank characters")
    if not args.prompt_version_id:
        return _refuse("--prompt-version-id is required (the live run never uses the production label)")
    if args.repeats is None or args.repeats < 1:
        return _refuse("--repeats must be at least 1")
    rows = load_gold(args.gold)
    import app

    if not os.path.abspath(app.__file__).startswith(os.getcwd() + os.sep):
        return _refuse(f"app is imported from {app.__file__}, not from the cwd")
    from app.database import SessionLocal

    try:
        _pinned_version(SessionLocal, args.prompt_version_id)
    except ValueError as exc:
        return _refuse(str(exc))

    with open(args.out, "w") as fh:
        os.chmod(args.out, 0o600)

        def write(row: dict[str, Any]) -> None:
            fh.write(json.dumps(row) + "\n")
            fh.flush()

        def header(info: dict[str, Any]) -> None:
            forced = "forced" if info["forced"] else "from the db"
            effort = f"{info['reasoning_effort']} ({'forced' if info['reasoning_forced'] else 'from the db'})"
            print(f"prompt_version {info['prompt_version']} closed_lists_mode {info['closed_lists_mode']} ({forced})"
                  f" reasoning_effort {effort}", flush=True)

        try:
            results = run_live(
                rows, session_factory=SessionLocal, version_id=args.prompt_version_id, repeats=args.repeats,
                max_usd=args.max_usd, require_key_last4=last4, on_row=write, closed_lists_mode=args.closed_lists_mode,
                on_start=header, reasoning_effort=args.reasoning_effort,
            )
        except ValueError as exc:
            return _refuse(str(exc))
    for case_id, cell in summarise(results).items():
        print(f"{case_id} {cell['passed']}/{cell['n']}")
    print(f"total usd {sum(r.get('usd', 0.0) for r in results):.4f}")
    stopped = [r for r in results if any(str(x).startswith("stopped") for x in r.get("reasons", []))]
    return 1 if stopped else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    live = sub.add_parser("live")
    live.add_argument("--gold", required=True)
    live.add_argument("--out", required=True)
    live.add_argument("--max-usd", type=float, default=None)
    live.add_argument("--require-key-last4", default=None)
    live.add_argument("--prompt-version-id", default=None)
    live.add_argument("--repeats", type=int, default=None)
    live.add_argument("--closed-lists-mode", choices=("block", "index"), default=None)
    # The stored setting's values (head/parser.REASONING_EFFORTS; app is not imported before the args parse).
    live.add_argument("--reasoning-effort", choices=("off", "low"), default=None)
    args = ap.parse_args(argv)
    return _cmd_live(args)


if __name__ == "__main__":
    sys.path.insert(0, os.getcwd())
    sys.exit(main())
