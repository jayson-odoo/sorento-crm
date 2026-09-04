"""The chatbot turn engine's vocabularies and payload shapes - ONE declaration each.

H28 is enum drift: n8n listed `branch_kind` in the router, again in the Switch it fed,
and again in `escalate-catalog`, and the three lists stopped agreeing without anything
failing. Every vocabulary the engine speaks is therefore declared exactly once here, as a
tuple plus the `Literal` built from it, and `tests/chatbot/test_contracts.py` greps the
package for a second copy.

Naming follows the wire, not Python taste: `qf` keys, `ctx` keys and `session_vars`
members keep the names n8n uses, because a rename is a contract break with the caller and
with 1,535 captured fixtures.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# --------------------------------------------------------------------------- #
# Parser vocabularies (AC-109). Values are the parser prompt's own OUTPUT block.
# --------------------------------------------------------------------------- #

MESSAGE_TYPES = (
    "request_for_help",
    "business_query",
    "clarification",
    "casual",
    "unknown",
)
MessageType = Literal[MESSAGE_TYPES]  # type: ignore[valid-type]

INTENT_HINTS = (
    "check_stock",
    "check_product",
    "check_incoming",
    "check_promotion",
    "check_order",
    "get_forms",
    "check_product_attachment",
    "get_resource_attachment",
    "get_portal_link",
    "check_goods_receive",
    "check_spo",
    "submit_idea",
)
IntentHint = Literal[INTENT_HINTS]  # type: ignore[valid-type]

DOMAIN_HINTS = (
    "master_products",
    "product_attachment",
    "promotion",
    "forms",
    "inventory",
    "order",
    "incoming",
    "portal_link",
    "resource_attachment",
    "goods_receive",
    "spo_allocation",
    "ideate",
)
DomainHint = Literal[DOMAIN_HINTS]  # type: ignore[valid-type]

SUGGESTED_TEAMS = (
    "purchasing",
    "purchasing_certification",
    "customer_service",
    "marketing_product",
    "marketing_form",
    "warehouse",
    "marketing_promotion",
    "it_admin",
)
SuggestedTeam = Literal[SUGGESTED_TEAMS]  # type: ignore[valid-type]

SUGGESTED_AGENTS = (
    "general_enquiries",
    "order_enquiries",
    "incoming_stock_enquiries",
    "marketing_form",
    "it_support",
    # deriveRouting's `ideate` case is the single source of truth for this one: the
    # access check keys on suggested_agent and an unknown agent fails CLOSED.
    "ideation",
)
SuggestedAgent = Literal[SUGGESTED_AGENTS]  # type: ignore[valid-type]

ENTITY_HINTS = (
    "product",
    "promotion",
    "customer",
    "transporter",
    "inbound_shipment",
    "warehouse",
    "attachment",
    "form",
    "order",
    "category",
    "brand",
    "attachment_type",
)
EntityHint = Literal[ENTITY_HINTS]  # type: ignore[valid-type]

# `selection_context` is written by compile-current-state and read by the head to decide
# what an otherwise meaningless reply ("1", "dealer", "yes") refers to.
SELECTION_CONTEXTS = (
    "disambiguation",
    "suggest_offer",
    "member_offer",
    "tier_offer",
    "team_clarify",
    "company_clarify",
)
SelectionContext = Literal[SELECTION_CONTEXTS]  # type: ignore[valid-type]

# --------------------------------------------------------------------------- #
# Engine vocabularies
# --------------------------------------------------------------------------- #

# The 13 arms `route-turn` decides between, in ladder order.
BRANCH_KINDS = (
    "access_denied",
    "escalate_offer",
    "out_of_scope",
    "ideate",
    "offer_hold",
    "escalation_declined",
    "check_promotion",
    "low_signal",
    "clarify_menu",
    "not_supported",
    "stock_denied",
    "demand_qty",
    "business_query",
)
BranchKind = Literal[BRANCH_KINDS]  # type: ignore[valid-type]

# The arms whose first n8n node was a STRIPPING `tag-*` Set. On these the router emits
# `{branch_kind}` and nothing else, so the fan-in downstream sees what it always saw.
TAG_ONLY_BRANCH_KINDS: frozenset[str] = frozenset(
    {"escalate_offer", "escalation_declined", "clarify_menu", "not_supported", "demand_qty"}
)

# Trace stages (AC-003, AC-007). One record per stage, in this order, on a full turn.
TURN_STAGES = (
    "received",
    "understood",
    "access",
    "routed",
    "looked_up",
    "replied",
    "remembered",
    "sent",
)
TurnStage = Literal[TURN_STAGES]  # type: ignore[valid-type]

TRACE_STATUSES = ("ok", "failed", "skipped")
TraceStatus = Literal[TRACE_STATUSES]  # type: ignore[valid-type]

# `chatbot.turns.stage` records WHERE a turn stopped. It is a superset of TURN_STAGES:
# three failure points sit outside the trace timeline - `intake` is before the first
# trace record exists (H5, AC-107), `queued` is the S7 per-contact wait (AC-710) and
# `casual_llm` is the S4 clarifier call (AC-403).
TURN_FAILURE_STAGES = TURN_STAGES + ("intake", "queued", "casual_llm")
TurnFailureStage = Literal[TURN_FAILURE_STAGES]  # type: ignore[valid-type]
# Enforced where the column is written (`engine._close_turn`), so a typo'd stage fails
# loudly instead of landing in the row and reading as an unknown state on the trace
# screen.

TURN_STATUSES = ("queued", "processing", "delegated", "done", "failed")
TurnStatus = Literal[TURN_STATUSES]  # type: ignore[valid-type]

# What the CALLER executes, in order (D4/D9: the CRM never sends).
ACTION_KINDS = (
    "send_message",
    "send_attachments",
    "assign_conversation",
    "add_comment",
    "update_contact_fields",
)
ActionKind = Literal[ACTION_KINDS]  # type: ignore[valid-type]

# Which injector delivered this envelope (D15). The engine never behaves differently on
# it; it exists so a trace row can say where a duplicate came from.
INGRESS_KINDS = ("webhook", "poller", "retry", "console")
IngressKind = Literal[INGRESS_KINDS]  # type: ignore[valid-type]

# `pending` marker kinds (R3). These replace the two frozen string contracts the JS
# matched with a regex over the previous reply.
PENDING_KINDS = (
    "escalation_offer",
    "team_clarify",
    "company_clarify",
    "tier_ask",
    "member_offer",
)
PendingKind = Literal[PENDING_KINDS]  # type: ignore[valid-type]

# --------------------------------------------------------------------------- #
# Session state (R2: every key compile-current-state writes, nothing dropped)
# --------------------------------------------------------------------------- #

SESSION_VAR_KEYS = (
    "message_type",
    "intent_hint",
    "domain_hint",
    "user_goal",
    "query_scope",
    "query_brands",
    "access_levels",
    "entities",
    "routing",
    "escalation",
    "response",
    "last_result_set",
    "selection_context",
    "date_filter_start",
    "date_filter_end",
    "date_mode",
    "requested_attributes",
    "match_mode",
    "contains_flyer",
    "dym_offer",
    "dym_candidates",
    "ideation",
    "dym_last_result_set",
    "tier_menu",
    "picker_last_result_set",
    "picker_families",
    "picker_domain",
    "picker_selection_context",
    "picker_families_carried",
    "routing_roster_plan",
    "routing_brand",
    "routing_brand_source",
    "routing_company",
    "routing_companies",
    # R3: the persisted marker that replaces the frozen-string reads.
    "pending",
)


class Pending(BaseModel):
    """What the bot is waiting for, recorded rather than re-read out of its own words."""

    model_config = ConfigDict(extra="forbid")

    kind: PendingKind
    team: str | None = None
    domain: str | None = None


class SessionVars(BaseModel):
    """`respond_contacts.session_vars.variables`, allowlisted (H15, AC-203).

    `extra = "forbid"` is what stops a harness key or a stray diagnostic leaking into a
    customer's session: the JS built a fresh object literal per writer, so anything a
    writer happened to set survived. The tail (S2) is what enforces this on the write
    path; S1 only reads.
    """

    model_config = ConfigDict(extra="forbid")

    message_type: Any = None
    intent_hint: Any = None
    domain_hint: Any = None
    user_goal: Any = None
    query_scope: Any = None
    query_brands: Any = None
    access_levels: Any = None
    entities: Any = None
    routing: Any = None
    escalation: Any = None
    response: Any = None
    last_result_set: Any = None
    selection_context: Any = None
    date_filter_start: Any = None
    date_filter_end: Any = None
    date_mode: Any = None
    requested_attributes: Any = None
    match_mode: Any = None
    contains_flyer: Any = None
    dym_offer: Any = None
    dym_candidates: Any = None
    ideation: Any = None
    dym_last_result_set: Any = None
    tier_menu: Any = None
    picker_last_result_set: Any = None
    picker_families: Any = None
    picker_domain: Any = None
    picker_selection_context: Any = None
    picker_families_carried: Any = None
    routing_roster_plan: Any = None
    routing_brand: Any = None
    routing_brand_source: Any = None
    routing_company: Any = None
    routing_companies: Any = None
    pending: Pending | None = None


# --------------------------------------------------------------------------- #
# Transport (the plan's "Transport contract with n8n")
# --------------------------------------------------------------------------- #


class Envelope(BaseModel):
    """The redis queue item `A` the two injectors both post, unchanged (D15).

    `message` is the respond.io webhook body; `contact` is the respond.io contact record
    n8n already looked up. Everything else is optional metadata about HOW the turn
    arrived, and the engine's behaviour depends on none of it except `is_test` /
    `test_run_id` (D14).
    """

    model_config = ConfigDict(extra="allow")

    message: dict[str, Any]
    contact: dict[str, Any]
    test_run_id: str | None = None
    is_test: bool = False
    mode: str | None = None
    scope: str | None = None
    ingress: IngressKind = "webhook"

    @field_validator("contact")
    @classmethod
    def _contact_must_identify_somebody(cls, contact: dict[str, Any]) -> dict[str, Any]:
        """`contact.id` is the respond.io contact id, and nothing works without it.

        Validated HERE so a caller that omits it gets a 422 naming the field, which is a
        misconfigured integration telling its operator what is wrong. Left to the engine
        it was a `ValueError` raised before the turn row existed, which the endpoint's
        generic handler turned into a bare 500 - the same symptom as a real outage, with
        nothing to distinguish them.
        """
        if contact.get("id") in (None, ""):
            raise ValueError(
                "contact.id is required: it is the respond.io contact id every session "
                "read, access check and turn row keys on"
            )
        return contact

    @property
    def dry_run(self) -> bool:
        """D14: a test envelope does ZERO writes outside `chatbot.turns`.

        Both signals mean the same thing and either is enough - the clone sets
        `test_run_id`, the chat console sets `is_test`, and `mode` is n8n's own
        pre-existing marker. Evaluated BEFORE any side-effecting service, never after
        (H37: n8n called next-assignee first and guarded second).
        """
        return bool(self.is_test or self.test_run_id or (self.mode and self.mode != "live"))


# `Action` and `Reply` are deliberately NOT modelled. `TurnResponse` carries both as plain
# dicts: an action's payload differs per kind, `reply.result_set` is whatever the lane
# produced, and `response_model` silently DROPS anything a model does not declare - so a
# half-right model is worse than none. The vocabulary that DOES need pinning is
# `ACTION_KINDS` above, and the endpoint tests assert the keys survive the wire.


class TurnRequest(BaseModel):
    """`POST /api/v1/external/chat/turn` body."""

    model_config = ConfigDict(extra="forbid")

    envelope: Envelope


class TurnResponse(BaseModel):
    """`POST /api/v1/external/chat/turn` 200 body.

    `delegate` names the n8n lane that must still run; `null` means the CRM finished the
    turn and the caller only sends. `session_patch` is populated on a dry run only, so a
    console or clone turn can be inspected without anything having been written.
    """

    model_config = ConfigDict(extra="forbid")

    turn_id: str
    ctx: dict[str, Any] | None = None
    item: dict[str, Any] | None = None
    branch_kind: BranchKind | None = None
    delegate: str | None = None
    reply: dict[str, Any] | None = None
    # The caller executes these IN ORDER. Declared as dicts because the payload
    # differs per kind and `response_model` silently DROPS anything undeclared.
    actions: list[dict[str, Any]] = Field(default_factory=list)
    session_patch: dict[str, Any] | None = None
    duplicate: bool = False


# Which branch kinds still hand back to an n8n lane. After S1 that is all of them: the
# head decides and n8n answers. Each later slice REMOVES entries here (S3 takes eight,
# S4 one, S5 one, S6 three), and S7 empties it and deletes `delegate` entirely. Derived
# from BRANCH_KINDS minus what the CRM already completes, so the two can never disagree.
CRM_COMPLETED_BRANCH_KINDS: frozenset[str] = frozenset({"low_signal"})
DELEGATED_BRANCH_KINDS: frozenset[str] = frozenset(BRANCH_KINDS) - CRM_COMPLETED_BRANCH_KINDS
