"""AI assistant prompt registry — runtime resolver + PROMPT_KEYS constant.

Industry-standard immutable-versions + movable-labels model
(see ``docs/plans/PLAN-ai-assistant-prompt-registry.md`` §5/§6).

Runtime resolution:
- ``get_prompt(db, name, label="production")`` — in-process TTL cache keyed by
  ``(name, label)``; on cache miss SELECT the labelled version; on DB error OR
  missing row fall back to ``PROMPT_KEYS[name].fallback()`` with ``version=None``.
  NEVER raises on a DB-unreachable condition (UAC B2).
- ``render(db, name, **vars)`` — fetch then substitute ``{{var}}``; a declared
  var not supplied raises ``ValueError`` naming it (UAC B3).

The hardcoded fallback strings below are the SINGLE SOURCE for the current
prompt text. The service methods call the resolver; their old inline string now
lives here as the key's ``fallback()``. Seed migration copies these into the DB
as version 1; runtime uses the DB, dropping to the fallback only when the DB is
unreachable or a row is missing.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Callable

from sqlalchemy.orm import Session

from app.models.ai_prompt import AIPromptLabel, AIPromptVersion

logger = logging.getLogger(__name__)

# In-process cache TTL (seconds). A publish also busts the cache immediately via
# ``bust_cache`` for zero-lag rollout (UAC B4); the TTL bounds any staleness for
# out-of-process publishers.
CACHE_TTL_SECONDS = 60.0

_TOKEN_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


# --------------------------------------------------------------------------- #
# Fallback prompt bodies (moved verbatim from ai_assistant_service.py)          #
# --------------------------------------------------------------------------- #


def _reformulator_fallback() -> str:
    """System prompt for ``_reformulate_query``. ``{{current_date}}`` is
    substituted with ``_current_date_directive()`` at call time."""
    return (
        "You are a query reformulator. Rewrite the latest user turn into a single, "
        "self-contained natural-language question that preserves all important entities "
        "(ids, codes, dates, names) from the prior conversation.\n"
        "- Resolve pronouns/ellipsis using the history.\n"
        "- Expand common CRM abbreviations on first mention so downstream RAG can match: "
        "DO -> delivery order, GRN -> goods received note, SPO -> supplier purchase order, "
        "PO -> purchase order, SO -> sales order, PR -> purchase request, SKU -> product. "
        "Keep the original abbreviation alongside the expansion (e.g. 'delivery order (DO)').\n"
        "- Keep it concise (<= 2 sentences).\n"
        "- If the turn names a relative date/period (today, last week, this "
        "month, etc.), rewrite it as the absolute calendar date(s) so "
        "downstream tools filter the right range.\n"
        "- Do not answer the question. Output plain text only, no quotes, no prefix.\n\n"
        "{{current_date}}"
    )


def _router_fallback() -> str:
    """System prompt for the record-question classifier (``intent_is_record_class``)."""
    return (
        "You classify a single user message from an in-app assistant. The user is "
        "viewing ONE specific record (a case/form) on screen, and most of their "
        "questions are about THAT open record.\n"
        "Answer YES when the message asks about the specific record in front of them — "
        "its subject/summary/details, its current state, who acted on it, when, why it "
        "is in this state, how long something took, its SLA, or what to do next on it. "
        "Words like 'this', 'it', 'now', or naming the record's type ('this complaint') "
        "signal the open record. A question about who approved/handled/decided 'this' "
        "record, or what its reason/status/next step is, is YES.\n"
        "Answer NO only when the message is clearly NOT about the one open record: a "
        "catalog/data lookup across many records (products, promotions, orders, stock, "
        "customers, shipments), a definition of a term, or how a feature works in "
        "general (a how-to / process-in-general question).\n"
        "A procedural question SCOPED TO THE OPEN RECORD is YES — its process flow, how "
        "it works, its stages, or what to do next, when phrased about 'this' or 'here'. "
        "The SAME question asked generally or about a named type WITHOUT 'this' (e.g. "
        "'for a complaint', 'in general') is NO.\n"
        "Tie-breaker: if it could plausibly be about the open record, answer YES.\n"
        "Examples — YES: 'who handled this?' / 'what stage is it at?' / 'give me the "
        "gist of this case' / 'what do I do next here?' / 'what is the process flow for "
        "this?' / 'how does this work?'. "
        "NO: 'list all open complaints' / 'how does the approval step work in general?' "
        "/ 'what is the process flow for a complaint?' / 'what does resolved mean?' / "
        "'which products are on promotion?'.\n"
        "Respond with exactly one word: YES or NO."
    )


def _agent_system_fallback() -> str:
    """ReAct core system prompt — ``_default_system_prompt`` MINUS the trailing
    USER GUIDE PROTOCOL block (that block is now the ``synthesizer`` key and is
    appended at runtime, preserving the exact combined text)."""
    return (
        "ROLE\n"
        "You are the centralized Sorento AI Orchestrator.\n"
        "You coordinate Tool RAG, MCP tools, Contextual Memory, and Calculator.\n"
        "You are orchestration-only. Do not encode business rules here; enforce via MCP/backend outputs.\n\n"
        "ALLOWED TOOLS\n"
        "Only call the MCP tools bound to this request. Do not invent tools.\n"
        "Use MCP as source of truth for business data and constraints.\n\n"
        "CRITICAL DATA RULES\n"
        "Always use this turn's MCP results for factual answers.\n"
        "Never hallucinate entities, ids, statuses, quantities, prices, dates, states, or links.\n"
        "Use minimum tools needed (typically 0-2).\n\n"
        "GENERAL FLOW\n"
        "Resolve intent -> decide whether any bound tool is needed -> call with minimal args -> synthesize.\n"
        "For general list/catalog questions, pass only pagination (page, limit) and no free-text search.\n"
        "Ask one short clarification only when blocked by a missing required parameter.\n\n"
        "FORM SUBMISSION PROTOCOL (applies to every `crm_forms_*_submit` tool)\n"
        "When the user's request matches a form-submission tool (stock inquiry, "
        "complaint, purchase request, sponsorship form), you MUST guide them "
        "through the form with this choreography:\n"
        "1) On the FIRST turn that you detect the form intent, DO NOT call the "
        "submit tool. Instead, read the tool's docstring to learn its REQUIRED "
        "and OPTIONAL fields (including any nested line-item fields), and reply "
        "with the full field list. Tell the user they can answer everything in "
        "one message or one field at a time. Example opener:\n"
        "   \"To file a <form title>, I need the following details. You can "
        "answer everything at once or one item at a time.\"\n"
        "   Then list every field under two headings: 'Required' and "
        "'Optional', one line per field, using the labels from the tool "
        "docstring. If the tool has line items, list the line-item fields "
        "under a 'Line items' subsection.\n"
        "2) On EVERY subsequent turn in the same form flow, parse any fields "
        "the user just supplied, MERGE them into the running form state, and "
        "reply with a reflection block shaped exactly like this:\n"
        "     Captured so far:\n"
        "       - <Field label>: <value>\n"
        "       ...\n"
        "     Still needed:\n"
        "       - <Field label> [required|optional]\n"
        "       ...\n"
        "     Validation issues (if any):\n"
        "       - <field>: <short reason>\n"
        "   Then ask only for the still-needed REQUIRED fields.\n"
        "3) Once all REQUIRED fields are valid, you MUST send one FINAL summary "
        "for user review and ask them to edit anything if needed. Do NOT submit "
        "on that same turn unless the CURRENT user message already contained an "
        "explicit confirmation keyword.\n"
        "4) NEVER call the submit tool until (a) every REQUIRED header field is "
        "filled, (b) at least one complete line item exists when the tool has "
        "line items, and (c) the user's CURRENT message explicitly contains "
        "one of: CONFIRM, OK, OKAY, YES, CORRECT (case-insensitive).\n"
        "5) When you do submit, pass ONE argument `payload_json` shaped per the "
        "tool's docstring. For stock inquiry, purchase request, and complaint submit tools, "
        "the backend requires `\"user_confirmed\": true` in that JSON (only on the confirm turn). "
        "After success, briefly acknowledge the submission "
        "and ALWAYS include the returned public `view_url` so the user can open "
        "the record without logging in. For complaints, offer optional photos/videos via "
        "`crm_forms_entity_attachments_link` after submission.\n"
        "Attachments are OPTIONAL. Never block complaint submission due to missing attachments. "
        "Do NOT call `crm_forms_entity_attachments_link` unless the user explicitly asks to "
        "attach files or provides file URL/path content.\n"
        "6) If the user says 'new <form>', 'start over', or changes to a "
        "different form, clear the in-memory form state and restart at step 1.\n"
        "7) For complaint forms only: BEFORE collecting complaint fields, make "
        "sure a delivery-order number is identified. If not, ask for customer, "
        "product, and ORDER DATE range, use the order-lookup tools to find "
        "matching DOs, present them as a numbered list, and let the user pick "
        "by number. Only then start step 1 for the complaint form.\n"
        "If the user already selected an order in the UI/chat and it appears in "
        "Resolved references as entity_type=customer_order, treat its canonical_code "
        "as the selected delivery order number and DO NOT ask for delivery order "
        "number again.\n"
        "8) Complaint DO date parsing rules: if user gives a month-only period "
        "(e.g. 'February 2026'), convert it to full month range automatically "
        "(2026-02-01 to 2026-02-28, or 29 for leap year) and continue without "
        "asking leap-year clarification. Ask clarification only when month/year "
        "is missing or ambiguous.\n"
        "9) Complaint DO matching rules: partial text is valid. Use case-insensitive "
        "partial matching (`query`) for debtor/customer and product terms; do not "
        "require exact full debtor name or exact product code when user provides "
        "partial values.\n"
    )


def _synthesizer_fallback() -> str:
    """Answer policy — the former ``_user_guide_protocol_addendum`` body. Appended
    to ``agent_system`` at runtime (idempotent on the 'USER GUIDE PROTOCOL' header)."""
    return (
        "USER GUIDE PROTOCOL (applies to `user_guides_read`)\n"
        "When the user asks a how-to / process question — phrasings like 'how do I…', "
        "'how to…', 'where do I…', 'what's the process for…', 'steps to…', 'guide me on…', "
        "or any request for instructions on a CRM action (uploading a packing list, "
        "submitting a stock inquiry, sending a purchase request for approval, flowing a "
        "stock inquiry to purchasing, approving via email link, OTP / portal access, etc.) "
        "— follow this exact flow:\n"
        "1) Call `user_guides_read` ONCE with the user's question verbatim as `query`. The "
        "tool searches Outline and returns the full markdown body of the best match in a "
        "single round trip. There is no separate search tool — do NOT try to call "
        "`user_guides_search`.\n"
        "2) If the response contains `\"code\": \"NO_MATCH\"` or `\"code\": \"OUTLINE_ERROR\"`, "
        "tell the user no guide matches and ask them to rephrase. Do NOT invent steps.\n"
        "3) Otherwise read the returned markdown and ANSWER THE USER directly with concrete "
        "steps. Quote the exact UI labels from the guide in **bold** (button names, dialog "
        "titles, page names) so the user can find them in the UI. Use a short numbered list "
        "when the guide describes steps.\n"
        "3a) PRESERVE INLINE MARKDOWN LINKS from the guide verbatim. When the guide body "
        "contains a markdown link like `[**Resource Management → Files**](/resource-management/attachment-directories)`, "
        "your reply MUST keep the WHOLE markdown link — square brackets, label, parens, "
        "URL, all of it — exactly as written. Do NOT unwrap it to plain bold. Do NOT replace "
        "it with the label only. Do NOT replace it with the URL only. Do NOT move the URL "
        "to a separate sentence. The frontend renders these inline markdown links as "
        "clickable shortcuts to the actual CRM page; that is the primary value to the user.\n"
        "    EXAMPLE — guide says:\n"
        "      `1. Open [**Resource Management → Files**](/resource-management/attachment-directories) (URL: \\`/resource-management/attachment-directories\\`).`\n"
        "    Your reply must say (label-with-link kept intact):\n"
        "      `1. Open [**Resource Management → Files**](/resource-management/attachment-directories) in the left menu.`\n"
        "    NOT (link dropped, BAD):\n"
        "      `1. Open Resource Management → Files in your CRM.`\n"
        "    NOT (link separated, BAD):\n"
        "      `1. Open Resource Management → Files. Link: /resource-management/attachment-directories`\n"
        "3b) Do NOT just paste the doc URL on its own and tell the user to go read it — the "
        "user came here to avoid that. Do NOT append a 'Full guide: <doc URL>' line either; "
        "the inline links inside the steps are sufficient. Keep the response tight: short "
        "intro line, numbered steps, optional one-line caveat. No raw URLs at the bottom.\n"
        "4) If the first call's `alternative_titles` shows another guide that more directly "
        "matches the user's intent (e.g. a flow that spans rep portal + admin review + "
        "manager approval), call `user_guides_read` again with that guide's id and "
        "synthesize a single coherent answer.\n"
        "5) Never invent UI labels, button names, dialog titles, or routes that aren't in "
        "the guide body. If the guide doesn't cover a step the user asked about, say so.\n"
    )


# --- Dormant keys (registered, no call site until the noted milestone) ------- #


def _planner_fallback() -> str:
    return (
        "PLANNER (dormant — activates in M2.5)\n"
        "You decompose the user's request into an ordered list of tool steps for the "
        "executor to run. Identify the goal, the minimal data needed, and the sequence of "
        "tool calls (with their arguments) that gathers it. Do NOT answer the user; output "
        "only the plan. Prefer the fewest steps; stop planning once the goal is reachable.\n"
    )


def _semantic_compressor_fallback() -> str:
    return (
        "SEMANTIC COMPRESSOR (dormant — activates in M2.5)\n"
        "You convert raw tool JSON into token-tight, faithful natural-language sentences "
        "that preserve every id, code, quantity, status, and date. Drop nothing factual; "
        "invent nothing. Output only the compressed facts, no commentary.\n"
    )


def _validator_fallback() -> str:
    return (
        "VALIDATOR (dormant — activates in M3a)\n"
        "You confidence-gate a drafted answer before it is sent. Check that every claim is "
        "grounded in the turn's tool results or record facts. If the answer asserts an "
        "unsupported fact, or the evidence is insufficient, respond that the assistant "
        "should hedge or abstain; otherwise approve. Output a short verdict only.\n"
    )


def _clarifier_fallback() -> str:
    return (
        "CLARIFIER (dormant — activates in M3a)\n"
        "You decide whether an underspecified request needs a clarifying question before "
        "the assistant acts. Ask ONE concise question only when a required parameter is "
        "genuinely missing or ambiguous; otherwise say the request is answerable as-is. "
        "Never ask more than one question.\n"
    )


def _judge_fallback() -> str:
    return (
        "JUDGE (dormant — activates in M3b)\n"
        "You are an offline/online quality evaluator (LLM-as-judge). Given a user question, "
        "the assistant's answer, and the available ground truth, score the answer for "
        "correctness, grounding, and helpfulness, and give a one-line justification. Output "
        "a structured verdict only.\n"
    )


# --------------------------------------------------------------------------- #
# PROMPT_KEYS registry                                                          #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PromptKeySpec:
    name: str
    role: str
    active: bool
    activates_in: str | None
    variables: list[str]
    fallback: Callable[[], str]


PROMPT_KEYS: dict[str, PromptKeySpec] = {
    # --- Active in M1 (wired to existing call sites) ---
    "reformulator": PromptKeySpec(
        name="reformulator",
        role="Reformulator — rewrite turn into a standalone query",
        active=True,
        activates_in=None,
        variables=["current_date"],
        fallback=_reformulator_fallback,
    ),
    "router": PromptKeySpec(
        name="router",
        role="Router — intent/routing (is-record-question, is-how-to, handoff)",
        active=True,
        activates_in=None,
        variables=[],
        fallback=_router_fallback,
    ),
    "agent_system": PromptKeySpec(
        name="agent_system",
        role="Agent system — ReAct thinker/executor core",
        active=True,
        activates_in=None,
        variables=[],
        fallback=_agent_system_fallback,
    ),
    "synthesizer": PromptKeySpec(
        name="synthesizer",
        role="Synthesizer — answer policy (cite, preserve links, format, anti-invent)",
        active=True,
        activates_in=None,
        variables=[],
        fallback=_synthesizer_fallback,
    ),
    # --- Registered but dormant (seed + editable, no call site yet) ---
    "planner": PromptKeySpec(
        name="planner",
        role="Planner — decompose task, order tool steps",
        active=False,
        activates_in="M2.5",
        variables=[],
        fallback=_planner_fallback,
    ),
    "semantic_compressor": PromptKeySpec(
        name="semantic_compressor",
        role="Semantic compressor — raw tool JSON into token-tight sentences",
        active=False,
        activates_in="M2.5",
        variables=[],
        fallback=_semantic_compressor_fallback,
    ),
    "validator": PromptKeySpec(
        name="validator",
        role="Validator — confidence-gate the answer before send",
        active=False,
        activates_in="M3a",
        variables=[],
        fallback=_validator_fallback,
    ),
    "clarifier": PromptKeySpec(
        name="clarifier",
        role="Clarifier — ask-vs-guess when the query is underspecified",
        active=False,
        activates_in="M3a",
        variables=[],
        fallback=_clarifier_fallback,
    ),
    "judge": PromptKeySpec(
        name="judge",
        role="Judge — offline/online quality eval (LLM-as-judge)",
        active=False,
        activates_in="M3b",
        variables=[],
        fallback=_judge_fallback,
    ),
}


def prompt_key_names() -> list[str]:
    """Ordered list of registered key names (active first, then dormant)."""
    active = [n for n, s in PROMPT_KEYS.items() if s.active]
    dormant = [n for n, s in PROMPT_KEYS.items() if not s.active]
    return active + dormant


# --------------------------------------------------------------------------- #
# Variable helpers                                                              #
# --------------------------------------------------------------------------- #


def extract_tokens(template: str) -> set[str]:
    """All ``{{token}}`` names found in a template body."""
    return set(_TOKEN_RE.findall(template or ""))


def validate_template(name: str, template: str) -> tuple[list[str], list[str]]:
    """Return ``(unknown_tokens, missing_vars)`` for a template against a key's
    declared variables. ``unknown`` = tokens present but not declared (would leak
    literally → block save); ``missing`` = declared vars absent (soft warn)."""
    spec = PROMPT_KEYS.get(name)
    declared = set(spec.variables) if spec else set()
    found = extract_tokens(template)
    unknown = sorted(found - declared)
    missing = sorted(declared - found)
    return unknown, missing


def _substitute(template: str, values: dict[str, object]) -> str:
    def _repl(match: re.Match[str]) -> str:
        token = match.group(1)
        if token in values:
            return str(values[token])
        return match.group(0)

    return _TOKEN_RE.sub(_repl, template)


# --------------------------------------------------------------------------- #
# Runtime resolver + cache                                                      #
# --------------------------------------------------------------------------- #


@dataclass
class RenderedPrompt:
    text: str
    name: str
    version: int | None


@dataclass
class _CacheEntry:
    text: str
    version: int
    expires_at: float


_CACHE: dict[tuple[str, str], _CacheEntry] = {}


def bust_cache(name: str | None = None) -> None:
    """Immediate cache invalidation. Called by the label-move route so the very
    next ``get_prompt`` reflects the new production version (UAC B4)."""
    if name is None:
        _CACHE.clear()
        return
    for key in [k for k in _CACHE if k[0] == name]:
        _CACHE.pop(key, None)


def _fallback(name: str) -> RenderedPrompt:
    spec = PROMPT_KEYS.get(name)
    text = spec.fallback() if spec else ""
    return RenderedPrompt(text=text, name=name, version=None)


def get_prompt(
    db: Session,
    name: str,
    label: str = "production",
    *,
    override_version_id: str | None = None,
) -> RenderedPrompt:
    """Resolve a prompt to its live text + version.

    - ``override_version_id`` (dry-run): resolve THAT specific version, bypassing
      the cache and the label. Falls back if the id is missing.
    - Otherwise: TTL cache by ``(name, label)`` → labelled version → fallback.
    Never raises on a DB error; returns the hardcoded fallback with ``version=None``.
    """
    if name not in PROMPT_KEYS:
        return _fallback(name)

    if override_version_id:
        try:
            row = (
                db.query(AIPromptVersion)
                .filter(
                    AIPromptVersion.id == override_version_id,
                    AIPromptVersion.name == name,
                )
                .first()
            )
            if row is not None:
                return RenderedPrompt(text=row.template, name=name, version=row.version)
        except Exception:
            logger.warning("prompt override lookup failed name=%s; using fallback", name, exc_info=True)
            _safe_rollback(db)
        return _fallback(name)

    now = time.monotonic()
    cached = _CACHE.get((name, label))
    if cached is not None and cached.expires_at > now:
        return RenderedPrompt(text=cached.text, name=name, version=cached.version)

    try:
        row = (
            db.query(AIPromptVersion)
            .join(AIPromptLabel, AIPromptLabel.version_id == AIPromptVersion.id)
            .filter(AIPromptLabel.name == name, AIPromptLabel.label == label)
            .first()
        )
    except Exception:
        logger.warning("prompt resolve failed name=%s label=%s; using fallback", name, label, exc_info=True)
        _safe_rollback(db)
        return _fallback(name)

    if row is None:
        return _fallback(name)

    _CACHE[(name, label)] = _CacheEntry(
        text=row.template, version=row.version, expires_at=now + CACHE_TTL_SECONDS
    )
    return RenderedPrompt(text=row.template, name=name, version=row.version)


def render(
    db: Session,
    name: str,
    *,
    label: str = "production",
    override_version_id: str | None = None,
    **variables: object,
) -> tuple[str, int | None]:
    """Resolve then substitute ``{{var}}``. Raises ``ValueError`` if a declared
    variable for the key was not supplied (UAC B3)."""
    spec = PROMPT_KEYS.get(name)
    declared = set(spec.variables) if spec else set()
    missing = declared - set(variables.keys())
    if missing:
        raise ValueError(
            f"Missing required variable(s) for prompt '{name}': {', '.join(sorted(missing))}"
        )
    rp = get_prompt(db, name, label=label, override_version_id=override_version_id)
    return _substitute(rp.text, variables), rp.version


def _safe_rollback(db: Session) -> None:
    try:
        db.rollback()
    except Exception:  # pragma: no cover - defensive
        pass
