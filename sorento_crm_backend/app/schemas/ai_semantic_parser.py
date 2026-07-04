"""Structured contract for the AI assistant Semantic Parser node (M0).

The parser is the single front-of-pipeline LLM: it *understands language and
emits parameters*, never prose (except ``standalone_query``, which is only an
embedding seed for RAG — never shown to the user). A deterministic router then
switches on ``intent`` + ``signals``.

See ``docs/plans/PLAN-ai-assistant-structured-parser.md``.

``PARSE_RESULT_JSON_SCHEMA`` is hand-written to satisfy OpenAI structured-output
**strict** mode (every property required, ``additionalProperties: false``,
nullables expressed as ``["type", "null"]``). It is ALSO used verbatim as the
Anthropic forced-tool ``input_schema``. ``ParseResult`` (Pydantic) validates the
returned object; ``fallback_parse()`` builds the degrade-to-agent-loop default.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# Closed intent set — ONE intent = ONE router branch (domain is a param, not an
# intent). Order documents router precedence intent-family, not evaluation order.
Intent = Literal[
    "capability",       # static capability catalog, no LLM
    "smalltalk",        # greetings / thanks — no tools
    "how_to",           # user guides (Outline)
    "definition",       # explain a term/status — no live data, no guide
    "record_question",  # facts about the OPEN record (already loaded)
    "record_action",    # mutate an existing record: close/cancel/approve (write)
    "data_query",       # live system data via MCP read tools
    "form_submit",      # CREATE a form entity (write)
    "unknown",          # parser low-confidence / parse failure default
]

FormTarget = Literal[
    "complaint", "stock_inquiry", "purchase_request", "sponsorship_form"
]

Domain = Literal[
    "stock", "orders", "products", "promotions", "customers", "sla", "shipments"
]

TimeScope = Literal["point", "range", "recent", "all"]


class DateRange(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    from_: Optional[str] = Field(default=None, alias="from")  # YYYY-MM-DD, absolute
    to: Optional[str] = None


class ParseEntities(BaseModel):
    record_ref: Optional[str] = None       # code/id the user named, verbatim
    domain: Optional[Domain] = None         # data_query bucket
    customer: Optional[str] = None
    product: Optional[str] = None
    date_range: DateRange = Field(default_factory=DateRange)
    time_scope: Optional[TimeScope] = None


class ParseSignals(BaseModel):
    targets_open_record: bool = False       # replaces intent_is_record_class YES/NO
    is_write_intent: bool = False           # M3a write-confirm seed
    needs_clarification: bool = False       # M3a clarifier seed
    clarify_question: Optional[str] = None
    clarify_options: list[str] = Field(default_factory=list)


class ParseResult(BaseModel):
    standalone_query: str = ""              # RAG embedding seed ONLY (never user-facing)
    intent: Intent = "unknown"
    language: str = "en"                    # detected reply language
    confidence: float = 0.0                 # parser self-confidence 0–1
    form_target: Optional[FormTarget] = None
    entities: ParseEntities = Field(default_factory=ParseEntities)
    signals: ParseSignals = Field(default_factory=ParseSignals)


def fallback_parse(raw_message: str) -> ParseResult:
    """Degrade-to-agent-loop default when the parser LLM fails or returns
    unparseable output. ``intent="unknown"`` routes to the agent loop (today's
    default path); ``standalone_query`` = the raw turn so RAG still has a seed.
    """
    return ParseResult(standalone_query=(raw_message or "").strip(), intent="unknown")


# --------------------------------------------------------------------------- #
# JSON Schema — OpenAI strict-mode compliant + Anthropic tool input_schema      #
# --------------------------------------------------------------------------- #

_NULLABLE_STR = {"type": ["string", "null"]}

PARSE_RESULT_JSON_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "standalone_query": {
            "type": "string",
            "description": "Self-contained rewrite of the latest turn (resolve pronouns/ellipsis "
            "from history; expand CRM abbreviations DO/GRN/SPO/PO/SO/PR/SKU keeping the "
            "abbreviation). For RAG embedding only.",
        },
        "intent": {
            "type": "string",
            "enum": [
                "capability", "smalltalk", "how_to", "definition",
                "record_question", "record_action", "data_query",
                "form_submit", "unknown",
            ],
            "description": "The single processing branch this turn needs. capability=what the "
            "system can do; smalltalk=greeting/thanks; how_to=step-by-step from a user guide; "
            "definition=meaning of a term/status; record_question=facts about the record on "
            "screen; record_action=change an existing record (close/cancel/approve); "
            "data_query=look up live system data; form_submit=create a complaint/inquiry/PR/"
            "sponsorship; unknown=cannot tell.",
        },
        "language": {
            "type": "string",
            "description": "BCP-ish code of the language to reply in (en, ms, zh, ...).",
        },
        "confidence": {
            "type": "number",
            "description": "0-1 self-confidence in the intent classification.",
        },
        "form_target": {
            "type": ["string", "null"],
            "enum": ["complaint", "stock_inquiry", "purchase_request", "sponsorship_form", None],
            "description": "Which form, when intent=form_submit; else null.",
        },
        "entities": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "record_ref": {**_NULLABLE_STR, "description": "Record code/id named verbatim, e.g. C-1042."},
                "domain": {
                    "type": ["string", "null"],
                    "enum": ["stock", "orders", "products", "promotions", "customers", "sla", "shipments", None],
                    "description": "Data bucket, when intent=data_query; else null.",
                },
                "customer": _NULLABLE_STR,
                "product": _NULLABLE_STR,
                "date_range": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "from": {**_NULLABLE_STR, "description": "Absolute YYYY-MM-DD; resolve relatives (today/last week/Feb 2026)."},
                        "to": {**_NULLABLE_STR, "description": "Absolute YYYY-MM-DD."},
                    },
                    "required": ["from", "to"],
                },
                "time_scope": {
                    "type": ["string", "null"],
                    "enum": ["point", "range", "recent", "all", None],
                },
            },
            "required": ["record_ref", "domain", "customer", "product", "date_range", "time_scope"],
        },
        "signals": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "targets_open_record": {"type": "boolean", "description": "True if the ask is about the record currently on screen."},
                "is_write_intent": {"type": "boolean", "description": "True for record_action / form_submit or any mutating ask."},
                "needs_clarification": {"type": "boolean", "description": "True only when a wrong guess is costly AND ambiguity would change the answer."},
                "clarify_question": _NULLABLE_STR,
                "clarify_options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Enumerable choices → FE chips; empty → free-form follow-up.",
                },
            },
            "required": ["targets_open_record", "is_write_intent", "needs_clarification", "clarify_question", "clarify_options"],
        },
    },
    "required": [
        "standalone_query", "intent", "language", "confidence",
        "form_target", "entities", "signals",
    ],
}

# Name used for OpenAI json_schema.name and the Anthropic forced-tool name.
PARSE_RESULT_SCHEMA_NAME = "semantic_parse_result"
