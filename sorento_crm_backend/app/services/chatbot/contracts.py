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

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.chatbot import jsc

# --------------------------------------------------------------------------- #
# DOMAIN_SPEC (D9). One row per domain; five tables are views over it.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DomainSpec:
    """Everything about a domain that is the SAME fact said in several places (D9).

    Evidence, not a hypothetical: adding one domain (`purchase_order`) meant editing six
    separate literals, and each of the five below is a per-domain fact that was written
    down independently and could therefore disagree with the others without anything
    failing. That is H28 - enum drift - with the domain as the enum.

    Deliberately NOT in here, and this is the whole discipline of the table: the tables
    that carry a per-domain HAZARD rather than a per-domain fact. `AXIS_BY_DOMAIN`,
    `DOMAIN_SUBJECT_AXIS`, `DOMAIN_SUBJECT_HINT`, `DOMAIN_BLOCKED_HINTS`,
    `MEMBER_OFFER_FILTER_HINTS` and `DOMAIN_BROADEN_BLOCKED_HINTS` each carry a
    hand-earned annotation naming the live turn that put a row there (owner rulings K2 to
    K4, C1, the 2026-08-09 promotion-brand leak). Folding those into a uniform table would
    lose the reason with the shape, which is the mistake `PRINCIPLES.md` calls "copying a
    mechanism without the justification that earned it". They stay where they are, in
    `head/output_exchange.py`, next to their evidence.

    * `intents` - the `intent_hint` values that mean THIS domain. One tuple, flattened into
      `INTENT_HINTS`; a 1:1 mapping today and the table is what makes that visible.
    * `bare_entity_type` - owner ruling K rule 4: what a message that is nothing but a code
      or a name IS under this domain. `None` means the rule does not apply, which is not
      the same as "product" - see `BARE_ENTITY_TYPE_BY_DOMAIN`'s own note for why a wrong
      guess is worse than not inheriting.
    * `switch_words` - the words that SWITCH a conversation into this domain, inverted into
      `DOMAIN_SWITCH_WORDS` (word -> domain). The inversion is what makes "one word, one
      domain" a property the guardrail test can check rather than an accident of hand
      editing.
    * `tools` - the MCP tools a turn in this domain answers from, FIRST ONE FIRST.
      `lanes/business/fetch.select_tool` calls `tools[0]` and nothing else, so the head
      of each tuple is a contract, not an ordering: reorder it and a different tool
      answers the customer. It is the tool production already chose - measured over the
      740 business turns in the 7 Sep 2026 prod copy, the embedding pick this replaced
      was the first-listed tool on every one of them, and
      `tests/chatbot/test_tool_pick_from_domain_spec.py` pins the eleven names.
      The REST of each tuple is an allow-list, not a candidate list: the union feeds
      `fetch.CHATBOT_READ_ONLY_TOOLS`, which is what the probes and the cross-domain
      rung are checked against when they name a tool directly.
      `mcp_tool_registry_service.sync_catalog` also stamps this mapping (via
      `mcp_tool_domains.CHATBOT_TOOL_DOMAINS`) onto `mcp_tools.chatbot_domain` - one
      domain per tool, a tool listed twice raises at sync time - and nothing reads that
      column since the tool search went (see its own docstring).
    * `escalation_team` - the `SUGGESTED_TEAMS` member a turn in this domain escalates to.
      Mirrors `output_exchange.derive_routing`'s ladder, which is a REPLAY-GRADED ported
      node and therefore stays the executable copy; the guardrail test asserts the two
      agree, which is what stops the pair drifting. `None` where `derive_routing` itself
      falls through to the null pair.
    * `default_supported` - False puts the domain in `DEFAULT_UNSUPPORTED_DOMAINS`, i.e.
      the bot refuses it out of the box. Note that every unsupported domain has an EMPTY
      `tools` tuple: the refusal is not a policy, it is that nothing can answer.
    """

    intents: tuple[str, ...]
    bare_entity_type: str | None
    switch_words: tuple[str, ...]
    tools: tuple[str, ...]
    escalation_team: str | None
    default_supported: bool = True


DOMAIN_SPEC: dict[str, DomainSpec] = {
    "master_products": DomainSpec(
        intents=("check_product",),
        bare_entity_type=None,
        switch_words=(
            "catalogue",
            "catalog",
            "spec",
            "specs",
            "specification",
            "specifications",
            "dimension",
            "dimensions",
        ),
        tools=(
            "crm_master_products_list",
            "crm_master_brands_list",
            "crm_master_product_categories_list",
            "crm_master_units_of_measure_list",
        ),
        escalation_team="purchasing",
    ),
    "product_attachment": DomainSpec(
        intents=("check_product_attachment",),
        bare_entity_type=None,
        switch_words=(),
        tools=("crm_master_product_attachments_list", "crm_certificates_list"),
        # `derive_routing` splits this one on the CERTIFICATE signal
        # (purchasing_certification when a cert word is present, marketing_product
        # otherwise), which is a per-turn decision and not a per-domain fact. The
        # non-cert arm is the one recorded here; the guardrail test asks
        # `derive_routing` with no cert signal, so the split stays where it is
        # executable.
        escalation_team="marketing_product",
    ),
    "promotion": DomainSpec(
        intents=("check_promotion",),
        bare_entity_type="product",
        switch_words=("promo", "promos", "promotion", "promotions", "promosi"),
        tools=(
            "crm_marketing_promotions_list",
            "crm_marketing_promotion_attachments_list",
            "crm_marketing_promotion_products_list",
        ),
        escalation_team="marketing_promotion",
    ),
    "forms": DomainSpec(
        intents=("get_forms",),
        bare_entity_type=None,
        switch_words=(),
        tools=("crm_forms_management_forms_list",),
        escalation_team="marketing_form",
    ),
    "inventory": DomainSpec(
        intents=("check_stock",),
        bare_entity_type="product",
        switch_words=("stock", "stocks", "inventory", "stok", "qty", "quantity"),
        tools=("crm_inventory_stock_balance_list", "crm_inventory_warehouses_list"),
        escalation_team="warehouse",
    ),
    "order": DomainSpec(
        intents=("check_order",),
        bare_entity_type="customer",
        # "delivery" and its forms (owner turn 2d903c96, 8 Sep 2026): "delivery to hanlim"
        # came back `request_for_help` with both hints null, and with no switch word for
        # the delivery vocabulary the #6 consumer and the escalation guard had nothing
        # structural to read. NOT "do": it collides with the English verb ("do you have").
        switch_words=(
            "order", "orders", "outstanding", "tempahan",
            "delivery", "deliveries", "deliver", "delivered",
            "penghantaran", "hantar", "dihantar",
        ),
        tools=(
            "crm_order_management_orders_list",
            "crm_order_management_orders_by_product_list",
            # `crm_order_analytics` is OUT of the pool (8 Sep 2026). Measured on the graded
            # console file: it won the pick on plain quantity asks ("how many did KENWEALTH
            # TRADING take of C-FH14", turns 87694182 / 0b10a4c0 at 0.4195 against the
            # order list's 0.4161; "delivery to hanlim", turn 11932963 at 0.497) and
            # answered EMPTY every time, because its `metric` query param is required and
            # the fetch lane never maps one from the parser - so the customer got "no order
            # matched" and an escalate offer for a question the order list answers. Re-add
            # it the day the lane maps a `metric` (count / total_value / avg_delivery_days)
            # off the parser's emission; until then a tool that cannot be called correctly
            # must not be retrievable.
            # The customer master is claimed HERE and not by `master_products`: a
            # customer is only ever looked up to narrow an order question.
            "crm_master_customers_list",
        ),
        escalation_team="customer_service",
    ),
    "incoming": DomainSpec(
        intents=("check_incoming",),
        bare_entity_type="product",
        switch_words=(
            "incoming",
            "eta",
            "shipment",
            "shipments",
            "arriving",
            "container",
            "containers",
        ),
        tools=(
            "crm_incoming_stock_list",
            "crm_incoming_stock_by_product",
            "crm_incoming_stock_shipments",
        ),
        escalation_team="purchasing",
    ),
    "portal_link": DomainSpec(
        intents=("get_portal_link",),
        bare_entity_type=None,
        switch_words=(),
        tools=("crm_portal_link_get",),
        escalation_team=None,
    ),
    "resource_attachment": DomainSpec(
        intents=("get_resource_attachment",),
        bare_entity_type=None,
        switch_words=(),
        tools=(
            "crm_resource_attachments_list",
            "crm_resource_attachments_catalogue",
            "crm_resource_attachments_current_stock_list",
        ),
        # Unmapped in `derive_routing` ON PURPOSE: the row pairing it with
        # marketing_product belongs to the unpromoted B-TEAM-1' lane change, and the
        # live body routes it by the prior-state carry instead.
        escalation_team=None,
    ),
    "goods_receive": DomainSpec(
        intents=("check_goods_receive",),
        bare_entity_type=None,
        switch_words=(),
        tools=(),
        escalation_team=None,
        # Nothing reads GRN data. The refusal is not a policy the owner could relax by
        # editing `chatbot_unsupported_domains`; it is that there is no tool.
        default_supported=False,
    ),
    "spo_allocation": DomainSpec(
        intents=("check_spo",),
        bare_entity_type=None,
        # "spo" (8 Sep 2026, the trigger the purchase_order row names): measured last-in
        # asks under the labelled prompt came back in the WRONG domain - turn bd6eacf4
        # ("last in for C-FH14" -> order / check_order) and 796957f4 (the same words ->
        # incoming / check_incoming). "spo" is the one token of that vocabulary that is a
        # whole word of its own; "last" / "in" are not sanctioned here, so the bare
        # "last in" phrasing is the prompt's to teach, not this table's.
        switch_words=("spo",),
        # `..._spo_allocations_...` and not `..._spo_...`: the name predates the 8 Sep
        # 2026 fix (the retired tool search filtered `source_id LIKE '%spo_allocation%'`,
        # so the shorter name was unretrievable from this domain - growth r1 A6). No
        # search and no name decides retrievability now, this row does, but the owner
        # ruled against renaming a shipped tool.
        tools=("crm_procurement_spo_allocations_last_receipt_list",),
        escalation_team=None,
    ),
    "ideate": DomainSpec(
        intents=("submit_idea",),
        bare_entity_type=None,
        switch_words=(),
        # `crm_ideation_turn` is a WRITE tool and deliberately outside the chatbot's
        # allow-list; the ideate lane calls it directly rather than retrieving it.
        tools=(),
        # No CS team: an idea is captured, never escalated. Its access AGENT
        # (`ideation`) is `derive_routing`'s own single source of truth.
        escalation_team=None,
    ),
    "purchase_order": DomainSpec(
        intents=("check_po",),
        # No row, by owner ruling K rule 4's own trigger: a MEASURED turn where a bare
        # token under this domain is mis-hinted, and it has answered none yet.
        bare_entity_type=None,
        # No switch words yet either. "PO" is two letters that collide with product
        # codes and with "po" inside other tokens, and `DOMAIN_SWITCH_WORDS` is matched
        # per WORD against the customer's message with no domain context - a wrong
        # switch would drag an unrelated turn into this domain. The decisive
        # `intent_hint` the prompt now teaches is the signal; add a switch word when a
        # measured turn shows the intent alone is not enough.
        #
        # That turn arrived (8 Sep 2026): 18d9b95c, "PO for SRTWC8517" under the labelled
        # prompt -> domain inventory / check_stock, and the bare "PO?" (1d22dbb6 ->
        # inventory, 98a9bec0 -> null) - the intent alone was not enough. Matched per WHOLE
        # token by `_TOKEN_RE`, so "po" inside a code ("po1234") does not fire.
        switch_words=("po",),
        tools=("crm_procurement_po_placed_list",),
        escalation_team="purchasing",
    ),
}

# Tools the chatbot MAY call that no domain answers FROM. Two kinds, and neither is an
# oversight: reads for surfaces the chatbot does not route to by domain at all (projects,
# complaints, SLA), and cross-cutting helpers a lane reaches for by name rather than by
# cosine search (`crm_lookup_resolve`, `user_guides_read`,
# `crm_system_tool_capabilities_summary`). Named rather than left implicit so
# `CHATBOT_READ_ONLY_TOOLS` below is the exact union of "claimed by exactly one domain"
# and "claimed by nobody, on purpose" - which is what makes the allow-list a derived view
# instead of a third list to keep in step.
UNDOMAINED_CHATBOT_TOOLS: tuple[str, ...] = (
    "crm_complaint_analytics",
    "crm_complaints_list",
    "crm_lookup_resolve",
    "crm_project_detail",
    "crm_project_forecast",
    "crm_project_quotations_list",
    "crm_projects_list",
    "crm_sla_conversation_event_logs_list",
    "crm_sla_conversation_tracking_dashboard",
    "crm_sla_conversation_tracking_list",
    "crm_system_tool_capabilities_summary",
    "user_guides_read",
)

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

# Every declared intent, flattened out of `DOMAIN_SPEC` (D9). One tuple, and the mapping
# from an intent back to its domain is now a property of the table rather than a fact a
# reader had to know: `check_po` means `purchase_order` because that is the row it is on.
INTENT_HINTS: tuple[str, ...] = tuple(
    intent for spec in DOMAIN_SPEC.values() for intent in spec.intents
)
IntentHint = Literal[INTENT_HINTS]  # type: ignore[valid-type]

DOMAIN_HINTS: tuple[str, ...] = tuple(DOMAIN_SPEC)
DomainHint = Literal[DOMAIN_HINTS]  # type: ignore[valid-type]


def coerce_domain_hint(value: Any) -> Any:
    """A `domain_hint` outside the enum above, coerced to null. THE one guard.

    F3 (review, 7 Sep 2026). Evidence turn b5b19cec-dccc-4eda-b766-1aeb1362957b: the
    parser tagged `domain_hint: "purchasing"` for "IBWB248什么时候会到仓库？" - "purchasing"
    is a TEAM name (`SUGGESTED_TEAMS`), not a domain - and `select_tool`'s
    `source_id LIKE '%purchasing%'` filter matched nothing (every incoming tool's
    `source_id` is `implemented::crm_incoming_stock_*`), so the turn ended `not_found`.
    That filter is GONE since 8 Sep 2026 (the lane picks `DOMAIN_SPEC[domain].tools[0]`,
    and a team name is not a key), so the same turn ends the same way for a plainer
    reason. The guard stays: a domain outside the enum must not reach any reader.

    A domain reaches a turn from exactly TWO places, and both call this:

    * the parser's emission, at `head/output_exchange._post_process`;
    * the contact's STORED memory, at `engine._drop_unknown_carried_domain` - which is what turn
      fca4aa5e-806b-4403-aa2e-fc2d0961fb2d proved the emission guard alone does not
      cover. That turn's parser emitted a clean `incoming`, and the carried
      `variables.domain_hint: "purchasing"` (written by an earlier turn, or by n8n) was
      adopted over it by `resolve_gate.retype_shipment_miss` - one of EIGHT sites that
      inherit the carried domain verbatim.

    Guarding the two entry points rather than the eight inheritors is what keeps this one
    place: every reader downstream, `select_tool` included, is then trusted as-is.
    """
    return value if value in DOMAIN_HINTS else None

# --------------------------------------------------------------------------- #
# The views over DOMAIN_SPEC (D9, AC-931). Each of these was an independent literal
# somewhere else in the package; the literal is gone and this is the only copy.
# --------------------------------------------------------------------------- #

#: Owner ruling K rule 4: what a BARE entity IS under a carried domain. A domain with no
#: `bare_entity_type` is ABSENT here, not present with a null - the readers test
#: membership, and "the rule does not apply" is a different answer from "it is a product".
#: Was a literal in `head/output_exchange.py`.
BARE_ENTITY_TYPE_BY_DOMAIN: dict[str, str] = {
    domain: spec.bare_entity_type
    for domain, spec in DOMAIN_SPEC.items()
    if spec.bare_entity_type is not None
}

#: word -> domain, inverted from each row's `switch_words`. The inversion is the point: a
#: word claimed by two domains is now impossible to write, where the hand-maintained dict
#: would simply have kept the last one. Was a literal in `head/output_exchange.py`.
DOMAIN_SWITCH_WORDS: dict[str, str] = {
    word: domain for domain, spec in DOMAIN_SPEC.items() for word in spec.switch_words
}

#: What `route.decide`'s `not_supported` arm tests when no configured list is supplied
#: (AC-304). Was a literal in `head/route.py`, and repeated in TWO core-side places that
#: cannot import this package (AC-002): `SystemSetting.chatbot_unsupported_domains`'s own
#: default and `settings.py`'s null-reset table. Those two now read it through
#: `app/modules/chatbot/lane_vocabulary.py`, the module's existing doorway for exactly this
#: problem, and the column's `server_default` stays a DDL literal (it has to be) pinned by
#: `tests/chatbot/test_domain_spec.py`.
DEFAULT_UNSUPPORTED_DOMAINS: tuple[str, ...] = tuple(
    domain for domain, spec in DOMAIN_SPEC.items() if not spec.default_supported
)

#: Every tool claimed by a domain. `lanes/business/fetch.CHATBOT_READ_ONLY_TOOLS` is this
#: plus `UNDOMAINED_CHATBOT_TOOLS`; see that constant for why the allow-list is derived
#: rather than a third list.
DOMAIN_CLAIMED_TOOLS: tuple[str, ...] = tuple(
    tool for spec in DOMAIN_SPEC.values() for tool in spec.tools
)


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

# The team `output_exchange`'s routing chain falls to when this turn named none, its domain
# derives none and no previous turn carried one - the HARD default at the end of the
# nullish chain, so this body never emits a null team. Named here because TWO readers need
# the same word: the chain that writes it, and the escalation lane's inheritance guard
# (AC-815 / review of #706 B1), which must not mistake a carried default for a previous
# turn's real routing.
DEFAULT_SUGGESTED_TEAM = "customer_service"
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
# four failure points sit outside the trace timeline - `intake` is before the first
# trace record exists (H5, AC-107), `queued` is the S7 per-contact wait (AC-710),
# `casual_llm` is the S4 clarifier call (AC-403), and `delegated` is a turn an n8n lane
# took over and never finished, failed by the sweep (AC-260,
# `app/services/chatbot_turn_sweep.py`).
TURN_FAILURE_STAGES = TURN_STAGES + ("intake", "queued", "casual_llm", "delegated")
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
#
# `shadow` (AC-1027) is the one member that is not an injector: it marks a row the engine
# wrote about ITSELF, a second parse of a live turn under the version in
# `system_settings.chatbot_parser_shadow_version`. It sends nothing, writes no session and
# escalates nothing, and it names the turn it shadows in `shadow_of`.
INGRESS_KINDS = ("webhook", "poller", "retry", "console", "shadow")
IngressKind = Literal[INGRESS_KINDS]  # type: ignore[valid-type]

# The business lane's resolve+gate exits (S6a). Taken from the four `resolve-exit-*`
# bodies' own `_exit_kind` literals, in the order `sub-main-processing`'s `resolve-arm`
# Switch tests them - NOT guessed, because that Switch is what routes on the value and a
# fifth word here would be an arm nothing is wired to.
EXIT_KINDS = ("continue", "access_ask", "not_found", "offer")
ExitKind = Literal[EXIT_KINDS]  # type: ignore[valid-type]

# The six named contract fields every `resolve-exit-*` arm adds beside `_exit_kind`, in
# the order the bodies list them. `sub-main-processing`'s stand-in chain reads exactly
# these - `resolve-gate` / `aggregate-gate` / `annotate-incoming-gate` test them for
# `!== null`, and the `resolve-entity` / `disallowed-entity-gate` / `build-ctx-resolved` /
# `Aggregate` / `tier-gate` / `annotate-incoming-picker` stand-ins re-emit them - so a
# missing key is an n8n node that silently stops executing, not a missing field.
EXIT_CONTRACT_FIELDS = (
    "resolved",
    "gate",
    "ctx_resolved",
    "aggregate",
    "tier_gate",
    "annotate_incoming",
)

# `requested_attributes`' timeline sentinel (H46). `output-structurer` reads it as
# `.some(k => String(k ?? '').trim() === '__all__')` - CONTAINS the sentinel, not IS it
# alone - and a review once called that guard redundant because every mutation it was
# tested against emitted the sentinel by itself. Declared here, with `is_timeline` beside
# it, so S6b's port consumes the one reading instead of re-deriving it.
TIMELINE_SENTINEL = "__all__"


def is_timeline(requested_attributes: Any) -> bool:
    """`_isTimeline`: does `requested_attributes` CONTAIN the sentinel (H46)?

    Mixed emission (`['__all__', 'gatepass_date']`) is timeline mode, exactly as it is in
    n8n. The parser is *instructed* to emit the sentinel alone, but an instruction is not
    an invariant, and reading this as equality would flip a real turn's behaviour.
    """
    if not isinstance(requested_attributes, list):
        return False
    return any(
        jsc.js_string("" if key is None else key).strip() == TIMELINE_SENTINEL
        for key in requested_attributes
    )

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
# Dialogue state (growth r1, slice B: ONE focus object, ONE open question)
# --------------------------------------------------------------------------- #

# The nine axes the conversation can hold a value on, and the ONLY keys `focus` may
# carry. Named here rather than inferred from whatever a rule happened to write,
# because `Focus` forbids extras and the decay pass walks this tuple: a tenth axis has
# to be added deliberately, in one place, or it does not exist.
#
# TWO axes are plural and the rest are singular, which is not an inconsistency: a question
# can be about several products at once ("SRTWC8517 and SRTKS6091 stock") and about several
# domains at once ("stock and eta"), and never about two customers at once. `products` holds
# a list of entities, `domains` holds a list of domain names in the order the dealer said
# them (D3, D11), and the singular axes hold one value each.
FOCUS_SLOTS = (
    "domains",
    "products",
    "customer",
    "transporter",
    "warehouse",
    "date_window",
    "attributes",
    "tier",
    "brands",
)
FocusSlotName = Literal[FOCUS_SLOTS]  # type: ignore[valid-type]

# What SET a slot, recorded rather than inferred. `current_message` is the customer's
# own words this turn, `reuse` is a rule carrying an alive slot forward, `pick` is an
# answer to an open question and `quoted` is a reply to an older message. The trace
# renders it verbatim, so an operator reading "why is this scoped to ABC" gets the
# answer without reading any code.
FOCUS_SOURCES = ("current_message", "reuse", "pick", "quoted")
FocusSource = Literal[FOCUS_SOURCES]  # type: ignore[valid-type]

# The SIX kinds of question the bot can leave open, each with ONE handler in
# `dialogue/open_question.py`. They replace the five `pending` kinds, the eight-rule
# `dym_offer` ladder, `selection_context` and the `picker_*` keys: those were each
# hand-added and none of them aged, which is defect 3 of the growth plan.
#
# `escalate_yes_no` is NOT among them and is not a loss (D5): an escalate offer naming ONE
# team is a `team_pick` with one option and `expects: yes_no`, which is the same question
# the customer sees today, and an offer naming two or more is the same kind with
# `expects: pick`. One kind, one handler, and the one-team and two-team offers stop being
# different code paths that can disagree.
OPEN_QUESTION_KINDS = (
    "product_pick",
    "customer_pick",
    "team_pick",
    "company_pick",
    "tier_pick",
    "member_offer",
)
OpenQuestionKind = Literal[OPEN_QUESTION_KINDS]  # type: ignore[valid-type]

# What KIND of answer resolves the question. A pick resolves against the frozen
# `options` rows by position; a yes/no resolves against `answers_open_question.yes_no`;
# `free` takes the customer's own words through `free_text`.
OPEN_QUESTION_EXPECTS = ("pick", "yes_no", "free")
OpenQuestionExpects = Literal[OPEN_QUESTION_EXPECTS]  # type: ignore[valid-type]


class FocusSlot(BaseModel):
    """One axis of what the conversation is currently about.

    `set_at_turn` is the CONTACT's turn number (`engine._turn_no`). Nothing expires on it
    (D9 leaves no counter at all); it is kept because the trace screen answers "when did
    the bot start scoping this to ABC" with it, and a turn number is the only clock a
    dealer's conversation actually has.

    `set_at` is the WALL CLOCK, and it is `None` on every slot this engine writes. AC-206
    says a dry run's returned `session_patch` is byte-equal to what a live run persists,
    and a timestamp inside the state makes two otherwise identical turns differ. The field
    exists because AC-1002 names it in the slot shape and because a session written by
    another writer may carry one; the TRACE is where the clock is read from, stamped `at`
    by `TurnTrace.add`.
    """

    model_config = ConfigDict(extra="forbid")

    value: Any = None
    set_at_turn: int = 0
    set_at: Any = None
    source: FocusSource = "current_message"


class Focus(BaseModel):
    """What the conversation is about, per axis, each axis ageing on its own.

    ONE writer (`dialogue/focus.py`), against the two the growth plan measured: the
    parser prompt's "always continue the previous turn" plus ten deterministic rules in
    `head/output_exchange.py`. A slot is cleared by exactly three things and nothing else
    (D9, `dialogue/clearing.py`): a current-message entity of the same axis, a topic reset,
    or the Respond.io conversation-closed event. No counter, no lifetime, no settings
    field - a dealer cannot see a turn count, so nothing may expire on one.

    `domains` is the list the fan-out reads, in the order the dealer named them (D3, D11).
    A domain word with no entity REPLACES it and never appends (D7).
    """

    model_config = ConfigDict(extra="forbid")

    domains: FocusSlot | None = None
    products: FocusSlot | None = None
    customer: FocusSlot | None = None
    transporter: FocusSlot | None = None
    warehouse: FocusSlot | None = None
    date_window: FocusSlot | None = None
    attributes: FocusSlot | None = None
    tier: FocusSlot | None = None
    brands: FocusSlot | None = None


class OpenQuestion(BaseModel):
    """The ONE question the bot is waiting for an answer to (D7).

    `options` are FROZEN rows: the uuid, the code and the label the customer was
    actually shown, carried verbatim into the next turn and never re-resolved. That is
    the whole point of freezing them - "2" must mean the second row the customer read,
    not the second row a fresh lookup would return today.

    There is NO lifetime on it (D9, AC-1019). A question is cleared when it is answered,
    when a newer one replaces it, or when the customer asks something else instead - and
    `member_offer`, which used to live 3 turns, follows the same rule as the rest. An offer
    the customer can still see on their screen is still answerable, and a counter was only
    ever a guess at when they had stopped looking.
    """

    model_config = ConfigDict(extra="forbid")

    kind: OpenQuestionKind
    options: list[dict[str, Any]] = Field(default_factory=list)
    expects: OpenQuestionExpects
    asked_at_turn: int = 0
    # The wall clock, `None` on everything this engine writes, for the same AC-206 reason
    # `FocusSlot.set_at` is: a dry run's patch must be byte-equal to a live run's.
    asked_at: Any = None
    # Everything the handler needs and nothing the reader has to guess at: the offering
    # domain, the team an escalation names, issue #708's `keep` list of siblings that
    # already resolved. Free-form because the seven handlers need seven different
    # things, and a model per kind would be seven classes to keep in step with one
    # dispatcher.
    payload: dict[str, Any] = Field(default_factory=dict)


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
    # Growth r1 slice B: the dialogue state, ONE writer per layer (D6/D7). `pending`,
    # `dym_offer`, `selection_context` and the `picker_*` keys above stay for one
    # release as MIRRORS derived from `open_question` (AC-951), so every existing world
    # still grades while the corpus is re-derived.
    "focus",
    "open_question",
)


class Pending(BaseModel):
    """What the bot is waiting for, recorded rather than re-read out of its own words."""

    model_config = ConfigDict(extra="forbid")

    kind: PendingKind
    team: str | None = None
    domain: str | None = None
    # `member_offer` only: how many more turns the roster stays on the customer's screen
    # (AC-816 rule 1, `tail/pending.MEMBER_OFFER_TTL`). Absent on every other kind, and on
    # a marker written by n8n, which has no clock - the reader treats absence as "open".
    ttl: int | None = None
    # `team_clarify` only (AC-821 / AC-822): the teams the ask actually OFFERED, as
    # `{team, label}` - the slug the router acts on beside the exact string the customer
    # saw on the quick reply. One list, so a tap can never resolve to a team the ask did
    # not name, and `output_exchange._team_clarify_pick` can compare the reply against OUR
    # OWN string by equality instead of trying to understand it. Absent on a marker written
    # before this shipped, which is why that reader treats absence as "parser answer only".
    options: list[dict[str, Any]] | None = None


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
    focus: Focus | None = None
    open_question: OpenQuestion | None = None


# The widths the `chatbot.turns` columns actually have. Validated on the way IN so an
# over-long identifier is a 422 naming the field, never a truncation error at insert.
MAX_MESSAGE_ID_LENGTH = 128

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
    # Gate 4 (shadow mode). Same reason as `messageId`: it lands in a VARCHAR(128).
    shadow_of: str | None = Field(default=None, max_length=128)

    @field_validator("message")
    @classmethod
    def _identifiers_must_fit_their_columns(cls, message: dict[str, Any]) -> dict[str, Any]:
        """`messageId` is stored in a VARCHAR(128); an over-long one is the CALLER's bug.

        Without this the insert raises a `StringDataRightTruncation` deep in the engine and
        the caller sees a 500 - indistinguishable from the CRM being down, and n8n retries
        it. 422 naming the field says which byte to fix.
        """
        inner = message.get("message")
        message_id = inner.get("messageId") if isinstance(inner, dict) else None
        if message_id is not None and len(str(message_id)) > MAX_MESSAGE_ID_LENGTH:
            raise ValueError(
                f"message.message.messageId is longer than {MAX_MESSAGE_ID_LENGTH} "
                "characters, which is the width of the column it is stored in"
            )
        return message

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
    # The ENGINE's dry-run verdict, not an echo of the request: `is_test`, `test_run_id`
    # and a non-live `mode` all produce it (D14), and n8n gates its egress on this rather
    # than on re-deriving the same rule from the envelope it sent.
    is_test: bool = False
    ctx: dict[str, Any] | None = None
    item: dict[str, Any] | None = None
    branch_kind: BranchKind | None = None
    delegate: str | None = None
    reply: dict[str, Any] | None = None
    # The caller executes these IN ORDER. Declared as dicts because the payload
    # differs per kind and `response_model` silently DROPS anything undeclared.
    actions: list[dict[str, Any]] = Field(default_factory=list)
    session_patch: dict[str, Any] | None = None
    # S6a: the business lane's resolve+gate result, i.e. exactly the item
    # `sub-resolve-and-gate` used to return. `delegate` names the lane; this is what that
    # lane resumes on, and n8n's `resolve-item` re-emits it verbatim into `resolve-arm`.
    # Null on every arm the CRM does not run the lane for, and it disappears at S6c when
    # the CRM finishes the turn itself.
    delegate_payload: dict[str, Any] | None = None
    duplicate: bool = False


class CompleteRequest(BaseModel):
    """`POST /api/v1/external/chat/turn/{turn_id}/complete` body (AC-201).

    The `sub-output` trigger contract, unchanged: `item` plus the eleven nullable
    producer outputs the sub's RS-9 carrier stubs re-emit today. Each value is a
    producer's WHOLE output, verbatim, because the tail's by-name reads dig into it
    (`result.result.xd.block`, `answer.outcome_fragment['central-exchange']`) and
    reshaping it here would move the very bytes the replay corpus grades.

    `ctx` is optional: `/turn` already persisted it on the row, which is where the tail
    reads it from. Accepting it anyway means the n8n node can keep sending exactly what
    it sends today - a caller that has to DELETE a field to be accepted is a caller that
    breaks on the next deploy.
    """

    model_config = ConfigDict(extra="forbid")

    item: dict[str, Any]
    ctx: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    resolved: dict[str, Any] | None = None
    gate: dict[str, Any] | None = None
    offer_hold: dict[str, Any] | None = None
    suggest_offer: dict[str, Any] | None = None
    not_found: dict[str, Any] | None = None
    incoming_picker: dict[str, Any] | None = None
    access_choice: dict[str, Any] | None = None
    crossdomain_render: dict[str, Any] | None = None
    answer: dict[str, Any] | None = None
    clarify: dict[str, Any] | None = None


class CompleteResponse(BaseModel):
    """`POST .../complete` 200 body.

    `reply` is `{text, quick_replies, result_set, attachments_src}` - the four values
    `sub-sendmsg` and `send-attachments` reach for by name today, so each of their
    expressions becomes one read (AC-207). A plain dict for the same reason `Reply` is
    not modelled above: `result_set` is whatever the lane produced, and `response_model`
    silently DROPS anything a model does not declare.
    """

    model_config = ConfigDict(extra="forbid")

    turn_id: str
    reply: dict[str, Any] | None = None
    actions: list[dict[str, Any]] = Field(default_factory=list)
    # D14: populated on a dry run only, so a console or clone turn can be inspected
    # without anything having been written.
    session_patch: dict[str, Any] | None = None
    # The ROW's `is_test`, decided on the envelope at `/turn` and repeated here so n8n's
    # `test-guard` can log what it recorded instead of sent without carrying the head's
    # answer across two calls. Not a second switch: every action already carries the same
    # value on `dry_run`.
    is_test: bool = False


# Which branch kinds still hand back to an n8n lane. After S1 that is all of them: the
# head decides and n8n answers. Each later slice REMOVES entries here (S3 takes eight,
# S4 one, S5 one, S6 three), and S7 empties it and deletes `delegate` entirely. Derived
# from BRANCH_KINDS minus what the CRM already completes, so the two can never disagree.
# The business lane's three arms (S6). They converge on ONE n8n lane (`business_query`)
# and on ONE module here (`lanes/business/`), so the three travel together everywhere:
# into `CRM_COMPLETED_BRANCH_KINDS` (the code can finish them), into
# `SELF_CLOSING_BRANCH_KINDS` (their own module closes the row), and out of
# `lanes/canned.py`'s set (it does not compose them). `lanes.business.ENTRY_BY_BRANCH_KIND`
# is the runtime map; this is the same three as a contract, so `contracts` needs no import
# of a lane.
BUSINESS_BRANCH_KINDS: frozenset[str] = frozenset(
    {"business_query", "check_promotion", "stock_denied"}
)

CRM_COMPLETED_BRANCH_KINDS: frozenset[str] = frozenset(
    {
        # S3 - the canned lanes, offer-hold and ideation. Each is answered from the
        # prompt registry or (for `ideate`) from the `crm_ideation_turn` MCP tool, and
        # every one of them ends the turn inside `run_turn`.
        "access_denied",
        "escalate_offer",
        "escalation_declined",
        "clarify_menu",
        "not_supported",
        "demand_qty",
        "offer_hold",
        "ideate",
        # S4 - the small-talk clarifier.
        "low_signal",
        # S5 - the escalation lane, which hands the turn to a person.
        "out_of_scope",
    }
    # S6 - the business lane's three arms: resolve, gate, fetch, answer and miss all run
    # in process, so the turn no longer leaves the CRM for an n8n sub-workflow. Declared
    # separately below because two other places need the three by name.
    | BUSINESS_BRANCH_KINDS
)
# The kinds that have a lane MODULE of their own and close their own turn row once that
# lane has answered: `low_signal` is `lanes/casual.py` (S4) and `out_of_scope` is
# `lanes/escalation.py` (S5). Every other kind the CRM completes is composed by
# `lanes/canned.py`, which projects its own set off the two above rather than repeating
# either, and closes in `_run_stages`' canned block. Declared HERE because the engine and
# the canned module both need the answer, and two literals would drift the moment a slice
# adds a lane - which is exactly what S5 landing on S3 would otherwise have done. The
# three business arms are in here for the same reason: `lanes/business/` composes and
# closes them itself, through `complete_turn`, and `canned.py` must not try to.
SELF_CLOSING_BRANCH_KINDS: frozenset[str] = (
    frozenset({"low_signal", "out_of_scope"}) | BUSINESS_BRANCH_KINDS
)

# What a dry run prints where a SEAM would have supplied a value (D14, AC-507). One
# token, so a reader of a preview action can tell at a glance that nothing behind it
# happened. Declared here rather than in a lane because two lanes now stand values in -
# `out_of_scope` for the assignee and the SLA timestamps, `ideate` for the whole reply
# the write tool would have composed - and an executor that had to match two spellings of
# "nothing happened" would be matching a typo the day a third lane arrived.
PREVIEW = "<preview>"

# The same fact said in the CUSTOMER's words. `PREVIEW` is an operator token and belongs on
# `status` and the trace facts; it must never reach a `send_message`, because the executor
# executes actions and nothing else, so a dry-run ideate turn sent the literal string
# "<preview>" to whoever typed the idea. One sentence, in the vocabulary of the person who
# would read it, and it still says plainly that nothing was generated.
PREVIEW_IDEATE_REPLY = "[dry-run: ideation reply not generated]"


# `DELEGATED_BRANCH_KINDS` used to be the complement of the set above and is GONE: with
# `system_settings.chatbot_completed_lanes` in the decision, "delegated" is no longer a
# property of the build at all - the same kind delegates or completes depending on data -
# so a module-level constant claiming otherwise could only mislead. `delegate.delegate_for`
# is the one place that answers the question, and it needs both halves to do it.
