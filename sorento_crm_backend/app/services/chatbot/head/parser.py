"""The semantic parser call (AC-104, AC-105, R5).

One LLM call per turn. It is the ONLY place in the engine that reads the customer's words
(D11); everything after it is deterministic over structured state.

R5 closes H44 at the source: the call passes a STRICT `json_schema` to the provider, so a
well-formed object is guaranteed whenever the provider answers at all. A provider error, a
timeout, or a response that still fails validation is a FAILED `understood` stage - never a
soft default, never `intent = unknown` routed as if it were a real answer.

**No DB session is held across this call.** The plan's capacity section is explicit about
it and the 96/100-connection incident is the evidence: `resolve_config` collects everything
the call needs, the caller closes its session, the call runs, the caller reopens. The
signature enforces the discipline - nothing here takes a `Session`.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Mapping

from sqlalchemy.orm import Session

from app.services.ai_prompt_registry import agent_model, render

logger = logging.getLogger(__name__)

PROMPT_KEY = "chatbot_semantic_parser"

# The parser's own error reply. ONE declaration, in `app/services/chatbot_reply_copy.py`
# with the rest of the bot's fixed sentences, because the ENDPOINT sends the same string
# when the TAIL fails and it cannot import this package (AC-002).
from app.services.chatbot_reply_copy import CHATBOT_TURN_ERROR_REPLY as PARSER_ERROR_REPLY

PARSER_MAX_TOKENS = 2048

# NOT bounded by a per-call timeout, and deliberately not pretending to be (issue #656;
# the plan's Capacity section carries the same note). The timeout table names 8 s, but `llm_provider.LLMProvider.chat` has no
# timeout parameter at all - each provider builds its own SDK client - so wiring one means
# changing that shared signature and all three implementations, which is core work outside
# this slice. A declared-but-unapplied constant is worse than none: it reads as a
# guarantee. Follow-up: add `timeout` to `LLMProvider.chat` and pass the plan's value here.


class ParserError(RuntimeError):
    """The parse could not be completed. The caller fails the `understood` stage.

    `usage` is what the provider billed for the attempt, when it got far enough to bill
    anything: a truncated or non-JSON emission still costs tokens, and a spend the table
    cannot see is the whole reason the usage row exists. Empty when the call never
    returned (transport failure).
    """

    usage: dict[str, Any]

    def __init__(self, *args: object, usage: dict[str, Any] | None = None) -> None:
        super().__init__(*args)
        self.usage = usage or {}


@dataclass(frozen=True)
class ParserConfig:
    """Everything the LLM call needs, resolved BEFORE the session is released."""

    system_prompt: str
    prompt_version: int | None
    provider: str
    model: str
    api_key: str
    # Does the RESOLVED prompt ask for the growth-r1 keys (`parser.emits_v3`)? It decides
    # the strict schema, the two extra user-block lines and whether the dialogue rules
    # read the three signals at all. Defaults FALSE so a test stub, a harness mock and any
    # caller written before slice B2 all parse under the v1 contract, which is the one
    # production is promoted to.
    emits_v3: bool = False

# The three keys prompt v3 adds (growth r1 slice B2). Named here because THREE readers
# need the same list: the v3 schema below, `output_exchange.v3_signals`, and the guard
# asserting the live v1 body never mentions one.
V3_EMISSION_KEYS: tuple[str, ...] = ("answers_open_question", "anaphora", "topic_reset")

# What v3 ADDS beyond those three (L1-S2, D3), and what it DROPS.
#
# `asks` replaces the flat `domain_hint` + `entities` pair with what the dealer actually
# said: a list of {domain, entities}, in the order the message names them, so "stock for A
# and eta for B" survives as two asks instead of collapsing into one domain and two loose
# codes. `intent_hint` goes because every domain declares exactly one intent (measured
# 13:13), so it carried nothing `domain_hint` did not; the lanes that still want the word
# derive it from `DOMAIN_SPEC` (AC-1026). `scope_intent`, `broaden_axis`,
# `reference_positions` and `reference_target` go because the deterministic rules that read
# them are the carry rules `dialogue/` replaces.
#
# V1 KEEPS ALL OF THEM (D10). Strict structured output makes every declared property
# required, so a schema shared between the versions would hold the PROMOTED v1 prompt to
# emitting `asks` - a key no instruction in it mentions - and every live turn would fail at
# `understood` before the owner ever moved a label.
V3_ONLY_KEYS: tuple[str, ...] = ("asks", *V3_EMISSION_KEYS)
V1_ONLY_KEYS: tuple[str, ...] = (
    "domain_hint",
    "intent_hint",
    "entities",
    "scope_intent",
    "broaden_axis",
    "reference_positions",
    "reference_target",
)

# The token that says a resolved prompt asks for the v3 shape.
#
# **The marker is the KEY ITSELF, and that is the point.** The registry offers two other
# places to put one - `AIPromptVersion.config_json` and a dedicated first-line token - and
# neither covers every path this has to cover. `ai_prompt_registry.render` returns
# `(text, version)` and nothing else, so `config_json` is not on the resolution path at
# all without widening that signature; and the FALLBACK path has no registry row to carry
# metadata, because a fresh install parses off `chatbot_parser_prompt.SEMANTIC_PARSER_PROMPT`
# before any migration has seeded anything. A token in the TEXT is on every path by
# construction.
#
# Reading the OUTPUT key rather than inventing a marker line then makes the two
# impossible to drift: the schema the provider is held to is derived from the same string
# that tells the model what to emit, so a prompt that asks for `answers_open_question` is
# exactly the prompt whose schema declares it. There is no third place to update.
V3_PROMPT_MARKER = '"answers_open_question"'


def emits_v3(system_prompt: Any) -> bool:
    """Does this RESOLVED prompt text ask for the v3 keys? See `V3_PROMPT_MARKER`."""
    return V3_PROMPT_MARKER in str(system_prompt or "")


def _build_json_schema(*, v3: bool) -> dict[str, Any]:
    """The strict `ParseOutput` schema the provider is held to (AC-105).

    TWO schemas, and the split is the whole of growth r1's promotion safety. 28 top-level
    keys for prompt v1 and v2 and 31 for v3, which adds `answers_open_question`,
    `anaphora` and `topic_reset`. `routing` carries exactly two members in both.

    26 of the 28, and `routing` carrying exactly two members, is what the LIVE parser
    emits: every one of the 488 captured raw emissions has that shape. Growth r1
    (AC-909 / AC-910) adds `group_by` and `top_n`, which no captured emission carries -
    see their own comment below, and `output_exchange._EXEMPT_FROM_REQUIRED` for how a
    pre-growth-r1 emission still post-processes.

    ONE schema for both versions would not be a tidy-up, it would be a live behaviour
    change on the promoted prompt: strict structured output requires every declared
    property to be REQUIRED, so a v1 prompt run against the v3 schema is forced to emit
    three keys no instruction in it mentions, and the model has to invent all three. `parse`
    picks the schema from `ParserConfig.emits_v3`, which is read off the resolved prompt
    TEXT, so the shape the provider is held to and the shape the prompt asks for cannot
    disagree.

    Built from the prompt's own OUTPUT block. `additionalProperties: false` is what makes
    "exactly these keys, no others" a provider guarantee instead of an instruction, and
    every key is `required` so a silently missing one is a validation failure rather than
    a `None` that reads downstream as "the customer said nothing about it".

    Value types stay permissive (`type: [...]` unions rather than enums) on purpose: the
    parser legitimately emits values the enum does not cover yet, `output_exchange`
    normalises several of them (`"null"` to null, a compound access level to a tier
    token), and rejecting them at the provider would fail turns that work today. The
    vocabularies in `contracts.py` are what the code is written against; this schema is
    what the WIRE is held to.
    """
    string_or_null = {"type": ["string", "null"]}
    properties: dict[str, Any] = {
        "message_type": {"type": "string"},
        "intent_hint": string_or_null,
        "domain_hint": string_or_null,
        "scope_intent": string_or_null,
        "is_affirmative": {"type": ["boolean", "null"]},
        "user_goal": string_or_null,
        "access_levels": {"type": "array", "items": {"type": "string"}},
        "broaden_axis": string_or_null,
        "date_mode": string_or_null,
        "date_filter_start": string_or_null,
        "date_filter_end": string_or_null,
        "match_mode": string_or_null,
        "demand_qty": {"type": ["number", "string", "null"]},
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "raw": string_or_null,
                    "hint": string_or_null,
                    "canonical_code": string_or_null,
                    "current_message": {"type": ["boolean", "null"]},
                    "confident": {"type": ["boolean", "null"]},
                },
                "required": ["raw", "hint", "canonical_code", "current_message", "confident"],
            },
        },
        "entity_op": string_or_null,
        "scope_exclusive": {"type": ["boolean", "null"]},
        "requested_attributes": {"type": "array", "items": {"type": "string"}},
        "contains_flyer": {"type": ["boolean", "null"]},
        "reference_positions": {"type": "array", "items": {"type": "number"}},
        "reference_target": string_or_null,
        "person_mention": string_or_null,
        "is_active": {"type": ["boolean", "string", "null"]},
        "order_status": string_or_null,
        # Growth r1 (AC-909 / AC-910). The two keys every list tool this plan touches
        # takes uniformly: which axis to break the answer down by, and how many rows
        # were asked for. ENUM rather than the permissive `string_or_null` the older
        # keys use, and that is safe HERE for the reason the docstring gives for the
        # others being permissive: those keys have live emissions the enum would have
        # to cover, and these two have none - no prompt version before
        # `490_chatbot_parser_growth_r1` asks for them, so the enum cannot reject a
        # value a working turn already produces. `output_exchange` exempts both from
        # its required-key check, so a captured emission that predates them still
        # post-processes with each reading as null.
        "group_by": {
            "type": ["string", "null"],
            "enum": [
                "customer",
                "transporter",
                "date",
                "product",
                "warehouse",
                "supplier",
                None,
            ],
        },
        "top_n": {"type": ["integer", "null"]},
        "correction": {"type": ["boolean", "null"]},
        "routing": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                # `string_or_null`, NOT an enum of `SUGGESTED_TEAMS`, and from
                # 7 Sep 2026 that is a CONTRACT rather than the general permissiveness
                # the docstring above describes (owner rules R-a / R-c, console pass
                # 4). The prompt asks for an enum member when the customer's team word
                # maps to exactly one, and for the customer's OWN word, verbatim and
                # lowercased, when it maps to several ("marketing" - three teams) or to
                # none ("sales"). `null` therefore means one thing only: the customer
                # named no team.
                #
                # That is what lets `lanes/escalation._person_routing` tell "escalate
                # to marketing" (ask which of the three) from "I want to talk to a
                # human" (assign the default) without reading either message, which
                # D11 forbids. Tightening this to an enum would delete the
                # discriminator and take the H64 defect back.
                "suggested_team": string_or_null,
                "suggested_agent": string_or_null,
            },
            # NO `team_source`. It is not a live key: the live `sub-semantic-parser`
            # system message never asks for it and not one of the 488 captured
            # emissions carries it. It belongs to the UNPROMOTED B-TEAM-1' lane change
            # (plan, S1 "pending re-port"), and declaring it `required` here would make
            # the CRM the only deployment that forces the model to invent one.
            "required": ["suggested_team", "suggested_agent"],
        },
        "escalation": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "is_escalation_confirmation": {"type": ["boolean", "null"]},
                "company_pick": string_or_null,
            },
            "required": ["is_escalation_confirmation", "company_pick"],
        },
    }
    if v3:
        for legacy in V1_ONLY_KEYS:
            properties.pop(legacy, None)
        properties.update(
            {
                # WHAT THE DEALER ASKED, in the order they asked it (D3, D11). One entry
                # per domain named; `entities` are the ones that ask BINDS ("stock for A")
                # and an ask with an empty list is a domain named with no subject of its
                # own ("PO?"). An entity the message did not bind to any domain rides an
                # ask with `domain: null`, which `intake.flatten` folds into the turn's
                # entity list without binding it.
                "asks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "domain": string_or_null,
                            "entities": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "raw": string_or_null,
                                        "hint": string_or_null,
                                        "canonical_code": string_or_null,
                                        "current_message": {"type": ["boolean", "null"]},
                                        "confident": {"type": ["boolean", "null"]},
                                    },
                                    "required": [
                                        "raw",
                                        "hint",
                                        "canonical_code",
                                        "current_message",
                                        "confident",
                                    ],
                                },
                            },
                        },
                        "required": ["domain", "entities"],
                    },
                },
                # 1-based POSITIONS against the frozen `open_question.options` rows,
                # never uuids: the model is shown labels only, so a position is the
                # only handle it can hold and the engine resolves it.
                "answers_open_question": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "resolved": {"type": ["boolean", "null"]},
                        "picks": {"type": "array", "items": {"type": "number"}},
                        "yes_no": string_or_null,
                        "free_text": string_or_null,
                    },
                    "required": ["resolved", "picks", "yes_no", "free_text"],
                },
                "anaphora": {"type": ["boolean", "null"]},
                "topic_reset": {"type": ["boolean", "null"]},
            }
        )
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(properties),
    }


PARSE_OUTPUT_JSON_SCHEMA = _build_json_schema(v3=False)
PARSE_OUTPUT_JSON_SCHEMA_V3 = _build_json_schema(v3=True)
PARSE_OUTPUT_SCHEMA_NAME = "chatbot_parse_output"
# The keys the schema declares. Validation is "every required key present, nothing
# unknown kept" - unknown keys are IGNORED (the risk the plan names: a model that
# occasionally adds one must not fail a turn), missing ones are REJECTED. Per SCHEMA,
# because a v1 emission legitimately carries none of the three v3 keys.
DECLARED_KEYS: frozenset[str] = frozenset(PARSE_OUTPUT_JSON_SCHEMA["required"])
DECLARED_KEYS_V3: frozenset[str] = frozenset(PARSE_OUTPUT_JSON_SCHEMA_V3["required"])


def schema_for(*, v3: bool) -> tuple[dict[str, Any], frozenset[str]]:
    """`(json_schema, required_keys)` for the version this turn is parsing under."""
    return (
        (PARSE_OUTPUT_JSON_SCHEMA_V3, DECLARED_KEYS_V3)
        if v3
        else (PARSE_OUTPUT_JSON_SCHEMA, DECLARED_KEYS)
    )


def resolve_config(
    db: Session, *, current_date: str, override_version_id: str | None = None
) -> ParserConfig:
    """Read the prompt, the per-key model override and the API key. Session-bound.

    Call this, then CLOSE the session, then call `parse`. Everything that needs the
    database happens here so nothing needs it while the provider is answering.

    `override_version_id` runs a specific prompt VERSION instead of the published one, and
    the name is `ai_prompt_registry.render`'s own so there is one word for one thing all
    the way down. It exists for the Prompts screen's "Run a turn" test (AC-807), which is
    dry-run only: the engine refuses to read it off a live envelope, so a customer can
    never be answered by an unpublished prompt.
    """
    from app.services.ai_assistant_service import AIAssistantConfigService
    from app.services.llm_provider import resolve_api_key

    system_prompt, prompt_version = render(
        db, PROMPT_KEY, current_date=current_date, override_version_id=override_version_id
    )
    provider_override, model_override = agent_model(db, PROMPT_KEY)

    config = AIAssistantConfigService(db).get()
    if config is None:
        raise ParserError("AI assistant configuration is not set")
    provider = provider_override or config.provider
    model = model_override or config.model
    api_key = resolve_api_key(config, provider)
    if not api_key:
        raise ParserError(f"no API key configured for provider {provider!r}")
    return ParserConfig(
        system_prompt=system_prompt,
        prompt_version=prompt_version,
        provider=provider,
        model=model,
        api_key=api_key,
        # Read off the TEXT that was actually resolved, so promoting v3 is still one label
        # move and nothing here has to be told about it. See `V3_PROMPT_MARKER`.
        emits_v3=emits_v3(system_prompt),
    )


def build_user_block(
    *,
    previous_response: Any,
    latest_user_message: Any,
    pending_kind: str | None,
    emits_v3: bool = False,
    focus_hints: Mapping[str, Any] | None = None,
    open_question_hint: Mapping[str, Any] | None = None,
) -> str:
    """The user turn, in the same two lines the n8n `AI Agent` node sends.

    The ONE addition S1 makes (and the only prompt change allowed before S1b): what the
    bot is waiting for, stated as a fact rather than left for the model to infer from the
    previous reply's wording (R3, D11). It is the open question's kind now, the marker it
    used to read having gone with the five-key session.

    `previous_response` is a v1 / v2 input and the CALLER decides it: the engine reads the
    last `done` turn ROW, never session state, and sends None under v3 (AC-1023 bans
    previous reply text there). The `Previous turn (...)` strip below is kept for a row
    written while the tail still prefixed the compressed view.

    **Growth r1 slice B adds two more, and they are gated on the PROMPT VERSION.** `Focus:`
    is the alive slots and `Open question:` is what the bot is waiting for, each as one
    compact JSON line - structured hints, never transcript prose (D6). Prompt v3's INPUT
    block names them; v1 and v2 have no instruction that mentions either, so sending them
    to one of those would be handing the live model two labelled blocks it was never told
    how to read. `emits_v3` is therefore required for both lines, not merely a non-empty
    hint: a contact who already has focus state must not change how the PROMOTED prompt
    parses, and `test_parser_user_block_parity.py` holds for a session with focus as well
    as for one without.

    Under v3 the lines are still emitted only when there is something to say. An empty
    `Focus: {}` would be a statement the model has to interpret ("the conversation is
    about nothing") rather than the absence of one.
    """
    import json
    import re

    previous = re.sub(
        r"^Previous turn \([a-z_]+\)", "Previous turn", str(previous_response or ""), flags=re.I
    )
    lines = [
        f"Previous response: {previous}",
        f"Current user message: {latest_user_message}",
    ]
    if pending_kind:
        lines.append(f"Pending: the assistant is waiting for a {pending_kind} reply.")
    if emits_v3 and focus_hints:
        lines.append("Focus: " + json.dumps(focus_hints, ensure_ascii=False, sort_keys=True))
    if emits_v3 and open_question_hint:
        lines.append(
            "Open question: "
            + json.dumps(open_question_hint, ensure_ascii=False, sort_keys=True)
        )
    return "\n".join(lines)


class ParsedOutput(dict):
    """The parser's emission, with what the call COST hanging off it as `usage`.

    A dict, not a `(parsed, usage)` pair, and deliberately: `parse` is the seam half a
    dozen tests replace with a two-line stub returning a plain dict, and every reader of
    the emission reads it by key. Renaming the seam for one telemetry number would make
    the stubs lie about the shape. `getattr(out, "usage", {})` is the whole contract, and
    a stub that does not carry one is a legitimate answer: no call, no cost.
    """

    usage: dict[str, Any]

    def __init__(self, parsed: dict[str, Any], usage: dict[str, Any] | None = None) -> None:
        super().__init__(parsed)
        self.usage = usage or {}


def parse(config: ParserConfig, user_block: str) -> ParsedOutput:
    """One structured-output call. Raises `ParserError`; never returns a default.

    The return is the parser's 26 keys; `.usage` on it carries provider, model and token
    counts. Both have a reader: the `understood` trace facts (so an operator can see what
    a turn cost without leaving the screen) and `ai_assistant_usage_logs` (so the
    chatbot's spend lands in the same table every other LLM call here reports to).

    NOTHING here touches the database. That is the rule the capacity section states and
    the reason `ParserConfig` exists.
    """
    from app.services.llm_provider import get_provider

    json_schema, required_keys = schema_for(v3=config.emits_v3)
    messages = [
        {"role": "system", "content": config.system_prompt},
        {"role": "user", "content": user_block},
    ]
    try:
        provider = get_provider(config.provider, config.api_key, config.model)
        result = provider.chat(
            messages,
            temperature=0.0,
            model=config.model,
            max_tokens=PARSER_MAX_TOKENS,
            json_schema=json_schema,
            json_schema_name=PARSE_OUTPUT_SCHEMA_NAME,
        )
    except Exception as exc:  # noqa: BLE001 - provider/transport failure is a failed stage
        raise ParserError(f"parser provider call failed: {exc}") from exc

    usage = {
        "provider": config.provider,
        "model": config.model,
        "prompt_tokens": int(getattr(result, "prompt_tokens", 0) or 0),
        "completion_tokens": int(getattr(result, "completion_tokens", 0) or 0),
        "total_tokens": int(getattr(result, "total_tokens", 0) or 0),
    }
    try:
        content = (result.content or "").strip()
        if not content:
            # An empty structured emission (e.g. an Anthropic max_tokens truncation with no
            # tool_use) would validate as `{}` and route confidently on nothing.
            raise ParserError("parser returned empty content")
        try:
            parsed = json.loads(content)
        except Exception as exc:  # noqa: BLE001
            raise ParserError(f"parser returned non-JSON content: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ParserError("parser returned a non-object")
        missing = required_keys - set(parsed)
        if missing:
            raise ParserError(
                f"parser output missing required key(s): {', '.join(sorted(missing))}"
            )
    except ParserError as exc:
        # The provider answered, so it billed. The turn fails either way; the spend is
        # still real and still has to reach `ai_assistant_usage_logs`.
        exc.usage = usage
        raise
    return ParsedOutput(parsed, usage)
