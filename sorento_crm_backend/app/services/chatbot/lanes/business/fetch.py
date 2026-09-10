"""Port of `sub-fetch-results` + `sub-get-results` (S6b, AC-604 to AC-606).

The business lane's fetch step: pick ONE tool, call it over MCP, render the answer
deterministically. Six node bodies become six functions, line for line against the exported
JavaScript, with the same `jsc` shim S6a uses for JS truthiness / `String()` / `Number()`.

Three hazards are fixed here rather than reproduced, and each says so at its own site:

* **H53** - `sub-get-rag` is GONE, SQL and vector alike. The tool is read straight off
  `contracts.DOMAIN_SPEC[domain].tools[0]` (`select_tool` below), so this module names no
  table, writes no SQL, and makes no provider call. Measured over the 740 business turns
  in the 7 Sep 2026 prod copy, the embedding pick WAS the domain's first-listed tool on
  every turn, and the seeding chain the search depended on cannot run in the deployed
  backend image at all: production's tool RAG has been frozen since 2 June 2026.
* **H52** - the MCP endpoint is `settings.ai_assistant_mcp_url`, bound in `services.py`.
  n8n bakes a raw IP endpoint into TWO nodes; this module contains no host, no port and no
  scheme at all, and `call_tool` is a pass-through onto whatever client it is handed. The
  absence is mechanical: `test_s6b_fetch_lane.py` greps this file's source for both.
* **H11** - `tool-filter.js` returns `[]` on zero tools and that empty array is
  indistinguishable from "ran and found nothing to say". `tool_filter` keeps the empty
  item list for parity (D8) and adds `outcome`, which the caller can act on.
* **H58** - the pick used to be an argmax over an embedded catalogue that contains WRITE
  tools (`crm_order_cancel`, `crm_complaint_close`, the two purchase-request approvals,
  `crm_it_support_ticket_create`, `crm_ideation_turn`), and `tool_filter` takes the single
  candidate with no further test. `CHATBOT_READ_ONLY_TOOLS` below is the allow-list, and
  since the candidate is now `DOMAIN_SPEC`'s own first tool the hazard is structural
  rather than scored: nothing outside that table can be named, and `ensure_read_only`
  refuses anything off the list at both call seams anyway. The embedded POOL keeps the
  write tools, on purpose - the in-app AI assistant retrieves them and confirms with a
  human before each one, which is a gate this chatbot does not have.

**H43 is moot, not fixed.** The n8n query's `$4` is `domain`, LIKE-matched against
`source_id`, and some live call sites never bind it. In process `domain` is a parameter of
one function call, so `domain=None` means "no tool" by construction and can never mean
"the caller forgot to wire a parameter".

**H49, the tool-selection distribution.** `crm_order_management_orders_by_product_list` has
never been selected in any capture graded so far, so this module has NO per-tool branch
keyed on it. `entity_ids_transformer`'s `DATE_PARAMS` / `ORDER_TOOLS` tables are copied
verbatim from the JS and are LOOKUP TABLES, not branches: they name that tool because the
JS does, and porting them minus one row would be a silent behaviour change on the day it is
first selected. The measurement that would justify an actual branch has not been taken.

**H7 is answered by construction:** `output_structurer` is deterministic string building.
There is no answer LLM anywhere in this lane (D10), so the "orphaned answer LLM" hazard has
nothing to attach to.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from app.services.chatbot import jsc
from app.services.chatbot.contracts import (
    DOMAIN_CLAIMED_TOOLS,
    DOMAIN_SPEC,
    UNDOMAINED_CHATBOT_TOOLS,
)
from app.services.chatbot.contracts import is_timeline

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# tool-filter
# --------------------------------------------------------------------------- #

ToolOutcome = Literal["picked", "not_found"]


@dataclass(frozen=True)
class ToolPick:
    """`tool-filter`'s item list, plus the outcome its empty array could not express.

    `items` is BYTE-EQUAL to the JS (D8): one item on a pick, zero on none. `outcome` is
    H11's fix and is always set, so "no tool matched" is never mistaken for "nothing ran".
    """

    items: list[dict[str, Any]] = field(default_factory=list)
    outcome: ToolOutcome = "not_found"


def _score(tool: Any) -> float:
    """`Number.isFinite(Number(t?.similarity)) ? n : -Infinity`.

    The default matters and it is NOT `None`: an ABSENT `similarity` is `undefined`, and
    `Number(undefined)` is NaN, so the tool sorts LAST. An explicit `null` is
    `Number(null) === 0`, which sorts above a negative score. Reading both as `None` would
    collapse the two and quietly promote a tool that carries no score at all.
    """
    n = jsc.js_number(jsc.get(tool, "similarity", jsc.UNDEFINED))
    if isinstance(n, float) and (jsc.is_nan(n) or n in (float("inf"), float("-inf"))):
        return float("-inf")
    return float(n)


def _label(tool: Any) -> str:
    """`String(t?.name ?? '')`."""
    return jsc.nullish_str(jsc.get(tool, "name"))


def tool_filter(candidates: Any, *, has_product: bool | None) -> ToolPick:
    """ONE tool per turn: highest `similarity`, tiebreak `name` ASC.

    The BODY is n8n's, unchanged and graded byte for byte against 38 captures (D8), which
    is why the ranking is still here after the pick stopped being a ranking. `select_tool`
    now hands it exactly one candidate off `DOMAIN_SPEC` (similarity 1.0), so the sort has
    one element and the argmax is the identity - the node keeps working the way its
    captures say it does, and nothing about how the candidate was chosen leaked into it.

    Emitting exactly one item is structural, not incidental: the per-tool fan-out that used
    to sit downstream is deleted, so two items here would run the whole fetch, compile and
    send chain twice - two WhatsApp messages to one customer.

    By the time a candidate list reaches this function it is already final: `run_fetch`
    stamps `_tool_pick.source` on the OUTPUT rather than reaching in here, so this stays a
    ported node with no CRM-specific rule grafted onto it.
    """
    raw_tools = jsc.array(candidates)
    # `sort((a,b) => cmp(score(b), score(a)) || cmp(label(a), label(b)))`, and Python's
    # sort is stable like the JS engine's, so equal keys keep the input order.
    ordered = sorted(raw_tools, key=lambda t: (-_score(t), _label(t)))
    if not ordered:
        # 0 tools in, 0 items out - today's behaviour exactly. The OUTCOME is what makes
        # the difference visible (H11); the item list stays empty for parity.
        return ToolPick(items=[], outcome="not_found")
    best = ordered[0]
    picked_name = _label(best)
    return ToolPick(
        items=[
            {
                "json": {
                    **(best if isinstance(best, dict) else {}),
                    "name": picked_name,
                    "_tool_pick": {
                        "chosen": picked_name,
                        "rejected": [
                            {"name": _label(t), "similarity": _score(t)} for t in ordered[1:]
                        ],
                        "count": len(raw_tools),
                        "has_product": has_product,
                    },
                }
            }
        ],
        outcome="picked",
    )


def select_tool(domain: str | None) -> list[dict[str, Any]]:
    """The domain's tool, read off `DOMAIN_SPEC`. No embedding, no database, no network.

    `[{"name": DOMAIN_SPEC[domain].tools[0], "similarity": 1.0}]` for a domain with a
    non-empty `tools` tuple, `[]` for everything else: no domain, a domain outside the
    table, and the two domains that answer from nothing (`goods_receive`, `ideate`). The
    empty list reaches `tool_filter` and ends the turn `not_found`, exactly as a zero-row
    search did (H11).

    NULL DOMAIN IS A NARROWING, and a deliberate one: the search ran UNFILTERED when
    `domain` was null, so such a turn could still come back with a tool, and this returns
    nothing. Measured on `sorento_ai_automation_0907`: of 994 `business_query` turns, 0
    reached the fetch step with a null or missing `domain_hint`, so the narrowing has no
    measured effect. A tool picked by cosine distance alone, with no domain to answer
    from, was never a defensible answer anyway.

    **Why the vector search went (owner ruling, 8 Sep 2026: "we can drop the rag from
    chatbot lane").** The candidate set was already this literal, and it is small: 4 tools
    for `master_products`, 3 for the next three domains, 2 for two more, 1 for the last
    four - median 2. Measured over every business turn in the 7 Sep 2026 prod copy
    (`sorento_ai_automation_0907`, `chatbot.turns.trace` `_tool_pick.chosen`, 740 turns),
    the pick was the domain's FIRST-LISTED tool on all 740; not one variant
    (`orders_by_product_list`, `incoming_stock_by_product`, `incoming_stock_shipments`,
    `brands_list`, `product_categories_list`, `units_of_measure_list`,
    `promotion_attachments_list`, `promotion_products_list`,
    `resource_attachments_catalogue`, `resource_attachments_current_stock_list`,
    `warehouses_list`, `certificates_list`) was ever chosen. One embedding call per turn
    was deciding a question with one answer.

    It also could not be trusted to keep deciding it. The search needed a registry row and
    an embedded chunk per tool, and that seeding chain cannot run in the deployed backend
    image (the MCP catalogue is not in it, PR #748), so production's tool pool has been
    frozen since 2 June 2026: every tool added after that date was unretrievable, and "last
    in for SRT62-GM" answered "no spo_allocation matched these" with 10 fully-received
    allocations in the table. Reading the table makes that failure class impossible instead
    of monitored.

    The FIRST entry of each `tools` tuple is therefore a contract. The rest stay where they
    are as allow-list members for the probes and the cross-domain rung
    (`CHATBOT_READ_ONLY_TOOLS` is derived from `DOMAIN_CLAIMED_TOOLS`), not as candidates.

    A `domain` outside the parser's own declared enum should never reach this call in the
    first place - `contracts.coerce_domain_hint` guards both ways in: the parser's emission
    in `output_exchange.py`, and the contact's carried memory in `engine.py`. Evidence turn
    b5b19cec-dccc-4eda-b766-1aeb1362957b arrived with `domain_hint: "purchasing"`, a TEAM
    name, and ended `not_found`; one that got past both guards would end the same way here,
    by falling off the table rather than by zeroing a `LIKE` filter.
    """
    spec = DOMAIN_SPEC.get(domain) if domain else None
    if spec is None or not spec.tools:
        return []
    return [{"name": spec.tools[0], "similarity": 1.0}]


# --------------------------------------------------------------------------- #
# tier-probe-plan / tier-probe-collect
# --------------------------------------------------------------------------- #

TIER_ORDER = ("dealer", "office", "end_user")


def tier_probe_plan(tier_gate: dict[str, Any] | None) -> list[dict[str, Any]]:
    """One item per entitled tier, so the probe can ask "any promotions here at all?".

    Per tier and not one batched call because promotion rows carry NO access level - there
    is no key to match a batched answer back on, and reading the tier out of a filename is
    the same string-guessing that mislabelled 1,934 rows on the brand work.

    An empty plan returns ONE defensive item rather than `[]`: returning nothing would skip
    every downstream node including the ask itself, and the customer would get silence
    instead of a degraded ask.
    """
    tg = tier_gate if isinstance(tier_gate, dict) else {}
    raw_plan = tg.get("tier_probe_plan")
    plan: list[Any] = raw_plan if isinstance(raw_plan, list) else []
    if len(plan) == 0:
        return [
            {
                "json": {
                    **tg,
                    "probe_tier": None,
                    "probe_access_levels": [],
                    "probe_skipped": True,
                }
            }
        ]
    return [
        {
            "json": {
                **tg,
                "probe_tier": jsc.get(p, "tier"),
                # the compound names for THIS tier alone, from the same `recompose` the
                # answer lane uses - never string-built, never the raw entitlement
                "probe_access_levels": (
                    jsc.get(p, "access_levels")
                    if isinstance(jsc.get(p, "access_levels"), list)
                    else []
                ),
                "probe_skipped": False,
            }
        }
        for p in plan
    ]


def tier_probe_collect(
    tier_gate: dict[str, Any] | None, *, plan_items: Any, probe_results: Any
) -> dict[str, Any]:
    """Fold the N per-tier probe answers back into ONE item.

    PAIRING is positional and that is an ordering ASSUMPTION, so it is checked rather than
    trusted: if the counts disagree every tier falls back to `null` (unknown), the renderer
    drops the annotation and the ask still works. A wrong pairing would tell a customer "no
    promotion" about a tier that has them, which is worse than silence.

    AVAILABILITY is deliberately generous - `has_result is True` OR a non-empty `answers` -
    because the envelope has carried both over time and the failure direction matters: a
    false "no promotion" hides real files, a false "has promotion" costs one wasted pick.
    """
    base = tier_gate if isinstance(tier_gate, dict) else {}
    results = list(jsc.array(probe_results))
    plan = list(jsc.array(plan_items))

    availability: dict[str, bool] | None = None
    if len(plan) > 0 and len(plan) == len(results) and jsc.get(plan[0], "probe_skipped") is not True:
        availability = {}
        for index, plan_item in enumerate(plan):
            tier = jsc.get(plan_item, "probe_tier")
            if not jsc.truthy(tier):
                continue
            j = results[index] if jsc.truthy(results[index]) else {}
            rows = jsc.get(j, "answers") if isinstance(jsc.get(j, "answers"), list) else []
            availability[tier] = jsc.get(j, "has_result") is True or len(rows) > 0

    # `None` availability means "we could not determine this", NOT "nothing is available".
    # The renderer and the router both read it that way.
    any_available = any(availability.values()) if availability is not None else True
    return {
        **base,
        "tier_availability": availability,
        "tier_available_list": (
            [t for t in TIER_ORDER if availability.get(t)] if availability is not None else None
        ),
        "tier_any_available": any_available,
        "_tier_probe_count": len(results),
        "_tier_probe_planned": len(plan),
    }


# --------------------------------------------------------------------------- #
# entity-ids-transformer
# --------------------------------------------------------------------------- #

TYPE_TO_PARAM: dict[str, str] = {
    "product": "product_ids",
    "promotion": "promotion_ids",
    "order": "order_ids",
    "customer_order": "order_ids",
    "order_number": "order_ids",
    "customer": "customer_ids",
    "transporter": "transporter_ids",
    "form": "form_ids",
    "shipment": "shipment_ids",
    "inbound_shipment": "shipment_ids",
    # PLURAL, and the singular is a silent drop: `crm_master_product_attachments_list` -
    # the tool the dym / sibling / incoming probes hit - accepts ONLY the plural, and when
    # the singular was sent the probes got EVERY attachment and a Technical-Specifications
    # row was reported as "has certificate".
    "attachment_type": "attachment_type_ids",
    "attachment": "attachment_ids",
    "certificate": "certificate_ids",
    # Three tools accept it: `crm_inventory_stock_balance_list`,
    # `crm_inventory_warehouses_list` and
    # `crm_procurement_spo_allocations_last_receipt_list`.
    "warehouse": "warehouse_ids",
}

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z", re.IGNORECASE
)


# Tools that answer a DOCUMENT request and must be given something to narrow by.
# `crm_resource_attachments_list`'s own contract says it: "They named NO document at all ->
# this tool returns NOTHING, by design. `contact_id` alone is NOT a narrowing filter". The
# transformer is uuid-only, so an entity it could not resolve contributes no `*_ids` key at
# all, and the call went out carrying `view` / `contact_id` / `space_id` only - a listing of
# every attachment the contact is entitled to, which is a directory dump, not an answer.
ENTITY_FILTER_REQUIRED_TOOLS: frozenset[str] = frozenset({"crm_resource_attachments_list"})

# What counts as narrowing on those tools: every entity-id param the transformer can emit,
# plus the document-type filters the tool takes by name.
NARROWING_PARAMS: frozenset[str] = frozenset(TYPE_TO_PARAM.values()) | frozenset(
    {
        "attachment_type_code",
        "attachment_type_codes",
        "attachment_type_id",
        "directory_id",
        "uploaded_by",
    }
)


def has_narrowing_filter(args: Any) -> bool:
    """True when the built args carry at least one non-empty narrowing key."""
    if not isinstance(args, dict):
        return False
    return any(jsc.truthy(args.get(key)) for key in NARROWING_PARAMS)



# Params the tool takes as a SCALAR string rather than a list. Empty today: the
# `attachment_type_id` singular was removed when the plural landed. Kept because the shape
# matters as much as the spelling - sending an array where a scalar is expected is the same
# silent drop as sending the wrong name.
SCALAR_PARAMS: frozenset[str] = frozenset()

DATE_PARAMS: dict[str, tuple[str, str]] = {
    "crm_order_management_orders_list": ("actual_delivery_date_from", "actual_delivery_date_to"),
    "crm_order_management_orders_by_product_list": (
        "actual_delivery_date_from",
        "actual_delivery_date_to",
    ),
    "crm_incoming_stock_list": ("eta_from", "eta_to"),
    "crm_incoming_stock_by_product": ("eta_from", "eta_to"),
    "crm_incoming_stock_shipments": ("eta_from", "eta_to"),
    "crm_marketing_promotions_list": ("period_from", "period_to"),
    "crm_resource_attachments_list": ("uploaded_at_from", "uploaded_at_to"),
    "crm_resource_attachments_catalogue": ("uploaded_at_from", "uploaded_at_to"),
    "crm_sla_conversation_event_logs_list": ("date_from", "date_to"),
    "crm_procurement_po_placed_list": ("expected_date_from", "expected_date_to"),
}

ORDER_TOOLS: frozenset[str] = frozenset(
    {"crm_order_management_orders_list", "crm_order_management_orders_by_product_list"}
)

# A3/A5/A6 (chatbot-growth-r1): the tools whose `group_by` this transformer
# passes straight through as a query param (the backend validates the axis;
# see `ORDER_GROUP_BY_AXES` / each route's own set - not re-validated here).
GROUP_BY_TOOLS: frozenset[str] = frozenset(
    {
        "crm_order_management_orders_list",
        "crm_procurement_po_placed_list",
    }
)

# A6: the one tool with its OWN `top_n` param (default 1, "last 3 in"); every
# other GROUP_BY_TOOLS/ORDER_TOOLS member aliases `top_n` to `limit` instead
# (above), since it has no `top_n` param of its own.
TOP_N_DIRECT_TOOLS: frozenset[str] = frozenset({"crm_procurement_spo_allocations_last_receipt_list"})

# n8n hard-codes this and OVERRIDES the `semantic_input` value with it (which carried the
# identical string in all 24 sampled executions). D5 says the respond.io space id comes
# from the default respond workspace row, and it scopes to the VALUE, not to a list of
# call sites - so the port takes it as a parameter with n8n's own literal as the default.
# The replay pins the literal, so no fixture moves; production passes the workspace row's.
SPACE_ID = "364817"


def space_id_or_default(space_id: Any) -> str:
    """The ONE workspace fallback, so the four tool call sites cannot disagree.

    `entity-ids-transformer`, `Call 'sub-get-results'`, `crossdomain-probe` and the three
    did-you-mean probes all send the same workspace, and an install with no default
    respond workspace row must not have some of them send `null` while the others send
    n8n's literal - the MCP read is scoped by it.
    """
    return space_id if space_id else SPACE_ID

# `tier-probe`'s own tool. The per-tier question is "are there any promotions at this tier
# at all", so it is the promotions read, asked once per entitled tier - promotion rows carry
# no access level, so there is no key a single batched answer could be matched back on.
TIER_PROBE_TOOL = "crm_marketing_promotions_list"


def entity_ids_transformer(
    trigger: dict[str, Any] | None, *, space_id: str | None = None
) -> dict[str, Any]:
    """The MCP tool's arguments, built from the gate's already-resolved entities.

    `space_id` defaults to n8n's own literal so a replay is byte-equal; production passes
    the default respond workspace's (D5), which is the same value on this install and the
    right one on any other.
    """
    trig = trigger if isinstance(trigger, dict) else {}
    semantic_input: Any = trig.get("semantic_input")
    entities: Any = trig.get("entities")

    params: dict[str, list[Any]] = {}
    seen_uuids: set[Any] = set()
    unmapped_types: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for e in jsc.array(entities):
        entity_type = jsc.get(e, "entity_type") if jsc.truthy(e) else None
        uuid = jsc.get(e, "uuid") if jsc.truthy(e) else None
        if not jsc.truthy(uuid) or not _UUID_RE.match(jsc.js_string(uuid)):
            skipped.append(
                {"code": jsc.get(e, "code") if jsc.truthy(e) else None, "reason": "missing_or_bad_uuid"}
            )
            continue
        if uuid in seen_uuids:
            continue
        param = TYPE_TO_PARAM.get(entity_type) if isinstance(entity_type, str) else None
        if not param:
            unmapped_types.append({"entity_type": entity_type, "uuid": uuid})
            continue
        seen_uuids.add(uuid)
        bucket = params.setdefault(param, [])
        if uuid not in bucket:  # `Set.add` - insertion-ordered and deduped
            bucket.append(uuid)

    out: dict[str, Any] = {}
    truncated: list[dict[str, Any]] = []
    for param, values in params.items():
        if param not in SCALAR_PARAMS:
            out[param] = values
            continue
        out[param] = values[0]
        # The gate normally narrows to exactly one. If more ever arrives, record it rather
        # than truncate in silence.
        if len(values) > 1:
            truncated.append({"param": param, "kept": values[0], "dropped": values[1:]})

    out["_diagnostics"] = {
        "entities_in": len(jsc.array(entities)),
        "total_uuids_passed": sum(
            len(v) if isinstance(v, list) else (1 if jsc.truthy(v) else 0) for v in out.values()
        ),
        "scalar_truncated": truncated,
        "skipped": skipped,
        "unmapped_types": unmapped_types,
    }

    out["view"] = "render"
    # `out.date_mode = semantic_input?.date_mode` - an ABSENT key leaves `undefined` here,
    # and `JSON.stringify` drops an undefined value rather than writing null. So the key is
    # omitted, not nulled, when `semantic_input` does not carry it. Measured: 7 of the 20
    # `entity-ids-transformer` captures have no `date_mode` at all.
    if jsc.has(semantic_input, "date_mode"):
        out["date_mode"] = semantic_input["date_mode"]

    tool_name = jsc.js_string(trig["tool"]).strip() if jsc.truthy(trig.get("tool")) else ""
    start = jsc.get(semantic_input, "date_filter_start") or trig.get("date_filter_start")
    end = jsc.get(semantic_input, "date_filter_end") or trig.get("date_filter_end")
    date_params = DATE_PARAMS.get(tool_name)
    if date_params:
        if jsc.truthy(start):
            out[date_params[0]] = start
        if jsc.truthy(end):
            out[date_params[1]] = end

    # Same undefined-drop rule as `date_mode` above. `contact_id` and `space_id` are
    # re-assigned unconditionally at the bottom, so their absence here is invisible; these
    # four assignments are kept in the JS's own order anyway, because key order is what a
    # reader diffs.
    for key in ("contact_id", "space_id", "access_levels", "is_active"):
        if jsc.has(semantic_input, key):
            out[key] = semantic_input[key]

    # order_status (order tools only): "outstanding" | "delivered" | "so_outstanding"
    # (A3, AC-905); omitted when null.
    if tool_name in ORDER_TOOLS and jsc.get(semantic_input, "order_status") in (
        "outstanding",
        "delivered",
        "so_outstanding",
    ):
        out["order_status"] = jsc.get(semantic_input, "order_status")

    # A quantity ask makes the CRM aggregate. A plain DO list sends nothing: the key is
    # ABSENT, never false, so the MCP payload is unchanged.
    req_attrs = (
        jsc.get(semantic_input, "requested_attributes")
        if isinstance(jsc.get(semantic_input, "requested_attributes"), list)
        else []
    )
    if tool_name in ORDER_TOOLS and any(
        jsc.nullish_str(a).strip() == "quantity" for a in req_attrs
    ):
        out["include_summary"] = True
        # `include_pipeline` (fix, 7 Sep 2026): opt-in, separately from
        # `include_summary` above, for the SAME reason `include_specs` /
        # `include_sellable` below are opt-in rather than a server-level default - the
        # MCP server is shared with n8n, and n8n's own quantity-ask workflow already
        # sends `include_summary=true` today. The CRM asks for the three-line pipeline
        # by name; a caller that only asks `include_summary` gets the summary shape it
        # got before this plan. Both `ORDER_TOOLS` members declare the param on their
        # ToolSpec (`catalog.py`: orders_list and orders_by_product_list), which is what
        # keeps the MCP from stripping it - pinned by
        # `test_growth_fix_opt_in_envelope_fields.py`.
        out["include_pipeline"] = True

    # A1/A2 (chatbot-growth-r1), opt-in from THIS caller (fix, 7 Sep 2026): these two
    # used to be defaulted ON in `sorento_crm_mcp/server.py`'s
    # `TOOL_DEFAULT_QUERY_PARAMS` for every caller of the shared MCP server - n8n
    # included, which never asked for either and has no field-reveal filter of its
    # own. Moved here so only the CRM's own turn opts in, per the reason that turn
    # actually has:
    #   - `include_specs`: a product SPEC question ("SRTWC8517 spec", "wattage of
    #     X") - `check_product` intent or the `master_products` domain, the same
    #     pair A1's presenter branch reads.
    #   - `include_sellable`: only when the contact's OWN access grants
    #     `inventory.sellable` (Slice C's `contact_field_reveals`, read off `ctx.access`
    #     the same way A2's restricted-field drop reads it) - asking for a number the
    #     renderer would then have to hide is pointless, and every other contact's call
    #     stays the pre-A2 shape.
    if tool_name == "crm_master_products_list" and (
        jsc.get(semantic_input, "intent_hint") == "check_product"
        or jsc.get(semantic_input, "domain_hint") == "master_products"
    ):
        out["include_specs"] = True
    if tool_name == "crm_inventory_stock_balance_list":
        access = trig.get("access") if isinstance(trig.get("access"), dict) else {}
        attributes = access.get("attributes") if isinstance(access.get("attributes"), list) else []
        if "inventory.sellable" in attributes:
            out["include_sellable"] = True

    # group_by / top_n (A3, AC-909/AC-910): additive parser keys, uniform across
    # every list tool this plan touches. `top_n` aliases to `limit` for the
    # order tools (the tool has no `top_n` param of its own); A6's SPO tool
    # reads `top_n` directly (see `TOP_N_DIRECT_TOOLS`).
    group_by = jsc.get(semantic_input, "group_by")
    if tool_name in GROUP_BY_TOOLS and jsc.truthy(group_by):
        out["group_by"] = jsc.js_string(group_by)
    top_n = jsc.get(semantic_input, "top_n")
    if jsc.truthy(top_n):
        if tool_name in TOP_N_DIRECT_TOOLS:
            out["top_n"] = top_n
        elif tool_name in ORDER_TOOLS or tool_name in GROUP_BY_TOOLS:
            out["limit"] = top_n

    # E1 (attribute-first asks, fix round 11 Sep): a HAS turn - the resolver's
    # `predicate` block rode through the gate untouched - shows the first FIVE
    # qualifying PRODUCTS, never five ROWS: `limit` is the tool's own ROW cap
    # (a stock answer can carry several warehouse rows per product, a cert
    # answer several files per product), so setting `limit=5` there cut a
    # 7-product answer down to 5 rows spanning 4 products under a header that
    # said "Showing 5" - `limit` is left at the tool's own default entirely,
    # and the PAGE is built by slicing `product_ids` itself. "more" (E3) pages
    # the next five ids from the carried offer the same way.
    if trig.get("predicate") is not None and isinstance(out.get("product_ids"), list):
        out["product_ids"] = out["product_ids"][:5]

    # COERCE, THEN TRIM, and the ORDER is the whole point. `contact_id` arrives as BOTH an
    # int and a SPACE-PADDED string in production, in adjacent executions: five spine call
    # sites write `{{ ... .json.id }} ` with a trailing space inside the template. A number
    # has no `.trim`, so `String()` must come first - `.trim().toString()` is a TypeError on
    # the int the answer path actually receives. `String(x ?? '')` handles int, string,
    # padded string, null and undefined without knowing which caller sent what, and lands on
    # `''` (a scope that matches nothing) rather than `undefined`, which would DROP the key
    # and widen the read to every customer.
    raw_contact = trig.get("contact_id")
    if raw_contact is None:
        raw_contact = jsc.get(semantic_input, "contact_id")
    out["contact_id"] = jsc.nullish_str(raw_contact).strip()
    out["space_id"] = space_id_or_default(space_id)
    return out


# --------------------------------------------------------------------------- #
# The MCP call (H52)
# --------------------------------------------------------------------------- #


def parse_mcp_content(raw: Any) -> Any:
    """The MCP client's `content[]` blocks, each parsed on its own.

    `MCPRuntimeClient.call_tool` JOINS every text block with a newline, which turns two
    JSON documents into one unparseable string. n8n's own `findPayload` walks the blocks
    and takes the FIRST that carries a render envelope, so the port has to see them
    separately too - joining is what would lose a tool that answers in two chunks.
    """
    if not isinstance(raw, str):
        return raw
    parsed = _safe_json(raw)
    if parsed is not None:
        return parsed
    blocks = [_safe_json(chunk) for chunk in raw.split("\n") if chunk.strip()]
    for block in blocks:
        if isinstance(block, dict) and _find_payload(block) is not None:
            return block
    for block in blocks:
        if isinstance(block, dict):
            return block
    return raw


class ToolNotAllowed(RuntimeError):
    """H58: this tool is not one the chatbot may call, so it is not called at all.

    Its own type rather than a bare `RuntimeError` because the caller answers it
    differently from an MCP failure: a refusal is not "the read did not work", it is "the
    read was never allowed", and `run_fetch` records it as the `tool_not_allowed` outcome
    so the reason is on the trace an operator reads.
    """


# The MCP tools this chatbot may call. An ALLOW-list, so a tool that is not named here is
# refused - a new write tool added to the MCP catalogue is out by default rather than in
# until somebody remembers to deny it.
#
# **Why a literal and not a walk of `sorento_crm_mcp/catalog.py`.** The deployed backend
# image does not contain that package: `sorento_crm/docker-compose.yml` builds the backend
# with `context: ./sorento_crm_backend`, the Dockerfile's `COPY . .` therefore copies only
# the backend, `mcp` is not in `requirements.txt` and no volume mounts it. A catalogue read
# on the turn path would raise `ModuleNotFoundError` in every container, the path fallback
# in `mcp_tool_capability_service._load_catalog_specs` would look for `/sorento_crm_mcp/`
# and fail too, and `run_fetch`'s broad `except` would turn EVERY live business turn into
# "MCP tool X failed". A frozen set costs nothing and cannot fail.
#
# The catalogue is still the source of truth for WHICH names belong here, and the two are
# pinned together by `tests/chatbot/test_tool_pool_is_read_only.py`, which imports the
# catalogue (available in CI and in a checkout, never in the container) and asserts this
# set EQUALS "method GET, or the spec's own `read_only` flag". Drift in either direction
# fails CI, which is where the catalogue is readable, instead of at 3am in production.
#
# The six the audit found, deliberately absent: `crm_complaint_close`, `crm_order_cancel`,
# `crm_purchase_request_approve`, `crm_purchase_request_reject`,
# `crm_it_support_ticket_create`, `crm_ideation_turn`. They stay in the MCP catalogue and
# in the in-app assistant's embedded pool - it retrieves them ON PURPOSE and gates each
# behind a user confirmation and a permission check. The chatbot has no user to confirm
# with, which is the whole difference.
#
# **Where the names live (D9, AC-931).** Still a frozen literal, for every reason above -
# it is simply no longer a THIRD list. Each name is either claimed by exactly one domain
# (`contracts.DOMAIN_SPEC[domain].tools`) or named in `contracts.UNDOMAINED_CHATBOT_TOOLS`
# as claimed by nobody on purpose, and this set is their union. This list is the ALLOW-list
# for every seam a tool name can reach the MCP client through (the probes and the
# cross-domain rung name their tool directly); the one tool a turn is ANSWERED from is
# `DOMAIN_SPEC[domain].tools[0]`, read by `select_tool`.
# `tests/chatbot/test_tool_pool_is_read_only.py` still pins the whole union against the MCP
# catalogue's read-only set, unchanged.
CHATBOT_READ_ONLY_TOOLS: frozenset[str] = frozenset(
    DOMAIN_CLAIMED_TOOLS + UNDOMAINED_CHATBOT_TOOLS
)


def ensure_read_only(name: Any) -> None:
    """Refuse a tool the chatbot may not call. Raises `ToolNotAllowed`, returns nothing.

    ONE rule, called at the TWO seams a tool name can reach the MCP client through: this
    module's `call_tool` (the fetch step and the tier probe) and `services._mcp_call` (the
    answer and miss-suggest probes, which call the bundle directly). Two call sites of one
    function rather than two rules: whichever path a name arrives on, the same set decides.
    """
    if jsc.js_string(name) not in CHATBOT_READ_ONLY_TOOLS:
        raise ToolNotAllowed(
            f"MCP tool {name} is not allowed: the chatbot may only call read tools"
        )


def call_tool(name: str, args: dict[str, Any], *, mcp: Any) -> Any:
    """One MCP tool call, passed straight through (D10) - if the tool only READS.

    No re-shaping in either direction: the arguments are what `entity_ids_transformer`
    built and the result is what the tool returned, so `output_structurer` still sees the
    presenter shape it was written against. The endpoint is whatever `mcp` was constructed
    with, and `services.py` builds it from `settings.ai_assistant_mcp_url` - this module
    names no host, no scheme and no port.

    **The allow-list check is HERE, at the egress, and it is not defensive coding (H58).**
    The tool used to be chosen by cosine similarity over a pool that contains write tools,
    so the only thing standing between a customer's phrasing and `crm_order_cancel` was
    that no phrasing had scored it first. `select_tool` now reads the name off
    `DOMAIN_SPEC`, so a write tool cannot be PICKED at all; this is what stops one being
    CALLED however else it was named - the tier probe, and any tool name that arrived on a
    payload rather than from the domain table.
    """
    ensure_read_only(name)
    return mcp.call_tool(name, args)


# --------------------------------------------------------------------------- #
# output-structurer
# --------------------------------------------------------------------------- #

_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")

# Identity is an ALLOW-LIST, not a label test: short, stable, and shared with the renderers.
# `company_name` is identity because it says WHICH company's row this is - without it a
# two-company answer would read as a one-company answer.
IDENTITY_KEYS: frozenset[str] = frozenset(
    {
        "product_code",
        "product_name",
        "shipment_number",
        "shipping_container_number",
        "batch_number",
        "remaining_incoming_quantity",
        "warehouse_allocations",
        "unallocated_quantity",
        "warehouse",
        "system_location",
        "quantity_on_hand",
        "company_name",
    }
)

# ETA is kept ALWAYS, asked for or not: it is the public answer to "where is my container",
# and the cross-domain renderer sorts incoming rows on it.
ALWAYS_KEPT_KEYS: frozenset[str] = frozenset({"estimated_arrival_date"})

# Chronological order of an inbound container's clearance checkpoints. Mirrors the
# admin-editable `statuses` rows (entity_type "inbound_shipment", by sort_order) as they
# stand on prod; hardcoded because output_structurer is a pure function with no session.
CLEARANCE_CHECKPOINT_ORDER: tuple[str, ...] = (
    "loading_date", "etc_date", "etd_date", "estimated_arrival_date", "eta_delay_date",
    "inspection_date", "approval_date", "gatepass_date", "warehouse_arrival_date",
    "informed_collection_date", "collection_date",
)


def _safe_json(value: Any) -> Any:
    try:
        return json.loads(value)
    except Exception:  # noqa: BLE001 - `try { JSON.parse } catch { return null }`
        return None


def _as_obj(value: Any) -> Any:
    if isinstance(value, str):
        return _safe_json(value)
    return value if isinstance(value, dict) else None


def _find_payload(j: Any) -> dict[str, Any] | None:
    """The render envelope, wherever the MCP client happened to wrap it."""
    if not jsc.truthy(j):
        return None
    if isinstance(jsc.get(j, "items"), list) or jsc.truthy(jsc.get(j, "portal_url")) or jsc.truthy(
        jsc.get(j, "token")
    ):
        return j if isinstance(j, dict) else None
    for key in ("result", "response", "toolResult", "output", "json", "text"):
        o = _as_obj(jsc.get(j, key))
        if o is not None and (
            isinstance(o.get("items"), list) or jsc.truthy(o.get("portal_url")) or jsc.truthy(o.get("token"))
        ):
            return o
    if isinstance(jsc.get(j, "content"), list):
        for c in jsc.get(j, "content"):
            o = _as_obj(jsc.get(c, "text") if jsc.truthy(c) else None)
            if o is not None and (
                isinstance(o.get("items"), list)
                or jsc.truthy(o.get("portal_url"))
                or jsc.truthy(o.get("token"))
            ):
                return o
    return None


def _rendered_answers(e: dict[str, Any]) -> list[Any]:
    """The grouped rows in the order the numbered message printed them.

    Same walk and same skip conditions as the group render below, so "row 2 on screen" and
    `answers[1]` cannot disagree. Falls back to the flat `items` when a group carries none,
    because an empty `answers` would break the positional pick outright rather than shift
    it.
    """
    out: list[Any] = []
    for grp in e.get("groups") or []:
        if not isinstance(grp, dict) or not isinstance(grp.get("items"), list):
            continue
        out.extend(grp["items"])
    return out or (e.get("items") or [])


def group_axis(ctx: Any) -> str:
    """The `group_by` axis this turn asked for, off the trigger's `semantic_input`.

    Read twice - once to filter the grouped rows, once to decide whether the AXIS itself
    is a restricted value - so it is one function rather than two inline digs through a
    value that arrives as a dict on a live turn and as a JSON STRING on some captured n8n
    triggers (`output_structurer` already has to handle both).
    """
    si: Any = (ctx or {}).get("semantic_input") if isinstance(ctx, dict) else None
    if isinstance(si, str):
        si = _safe_json(si)
    if not isinstance(si, dict):
        return ""
    return jsc.js_string(si.get("group_by") or "").strip()


def _extract_envelope(j: Any) -> dict[str, Any]:
    empty = {
        "items": [],
        "attachments": [],
        "action_links": [],
        "intro": "No matching results found.",
        "has_result": False,
    }
    p = _find_payload(j)
    if p is None:
        return empty
    if isinstance(p.get("items"), list):
        return p  # render envelope
    if jsc.truthy(p.get("portal_url")):  # raw portal-link tool
        return {
            "items": [],
            "attachments": [],
            "action_links": [
                {"label": "Portal Link", "url": p["portal_url"], "type": "portal_link"}
            ],
            "intro": "Here is your portal link.",
            "has_result": True,
        }
    return empty


def _fmt_ts(iso: Any) -> str | None:
    """`new Date(iso)` then local `getDate()`/`getMonth()`/... - components, verbatim.

    Every captured `last_updated_at` is a NAIVE ISO string, which `new Date` reads as local
    time and `getDate()` then reads straight back, so the rendered components equal the
    input's (measured on all 20 `output-structurer` captures). Implemented as a component
    read rather than through a timezone, which is also what makes it deterministic.
    """
    if not jsc.truthy(iso):
        return None
    text = jsc.js_string(iso)
    match = re.match(
        r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}):(\d{2}))?", text
    )
    if not match:
        return None
    year, month, day = match.group(1), match.group(2), match.group(3)
    date = f"{day}/{month}/{year}"
    hour, minute, second = match.group(4), match.group(5), match.group(6)
    if hour is None:
        return date
    if (int(hour), int(minute), int(second)) == (0, 0, 0):
        return date  # midnight -> date only
    return f"{date} {hour}:{minute}:{second}"


# The JS renders an empty value and an object joiner with an EM DASH, and the access note
# with one too. Written as escapes, not as the character: the repo forbids an em dash in
# anything WE write, and these are neither ours nor prose - they are three literals from a
# node body that ships, and changing them would change what a customer is sent. Nothing in
# the 20 graded captures reaches any of the three, so this is faithfulness, not evidence.
_EM_DASH = "\u2014"


def _fmt_value(v: Any) -> str:
    if v is None or v == "":
        return _EM_DASH
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, str):
        return (_fmt_ts(v) or v) if _ISO_RE.match(v) else v
    if isinstance(v, (int, float)):
        return jsc.js_string(v)
    if isinstance(v, list):
        return ", ".join(_fmt_value(x) for x in v)
    if isinstance(v, dict):
        parts = [
            (_fmt_value(x) if isinstance(x, (dict, list)) else jsc.js_string(x))
            for x in v.values()
            if x is not None and x != ""
        ]
        return f" {_EM_DASH} ".join(parts) if parts else _EM_DASH
    return jsc.js_string(v)


def _has_key(f: Any) -> bool:
    """`Object.prototype.hasOwnProperty.call(f, 'key')`.

    PRESENCE, never `=== null`: the CRM OMITS `key` where a presenter has no source key,
    and testing for null instead would treat an unkeyed field as keyed.
    """
    return isinstance(f, dict) and "key" in f


def _humanise(key: str) -> str:
    text = re.sub(r"_date\Z", "", key).replace("_", " ")
    return text[:1].upper() + text[1:] if text else text


# Types whose rows carry ALIAS variants of one name. A debtor master holds "NAME",
# "NAME [A/C I]", "NAME [A/C II]" as separate accounts of the same customer, and naming all
# three reads as three customers. Product codes are NOT in here and must never be: a variant
# code that extends another code ("SRT100-BL" under "SRT100") is a different product.
_ALIAS_COLLAPSE_TYPES: frozenset[str] = frozenset({"customer"})


def _axis_labelled_subject(entities: Any) -> str:
    """What was searched, said the way the customer said it: "customer X, product Y".

    The line this feeds used to flatten every `entities[].code` into one comma list, so a
    multi-alias customer arrived as an INTERNAL debtor code plus one bullet per alias row -
    "no order records for 300-H070, HANLIM TRADING SDN BHD [A/C I], HANLIM TRADING SDN BHD,
    RPACC" - un-labelled, so it read as four separate things.

    Three STRUCTURAL rules, no text patterns over the customer's words (D11):

    * **A customer is named by the resolver's own `display_name`, never by
      `canonical_code`.** Live, "hanlim" resolves to TWO `customers` rows - one reached by
      `customer_code` (`300-H070`) and one by the denormalised `debtor_name` - on two
      different uuids, so the per-uuid de-dupe keeps both and the longest-code tie-break
      below can never fire between them. The account code is an internal identifier the
      customer has never seen. `gate.run_gate` carries `display_name` for exactly this,
      and a record without one falls back to its code, which is the whole of today's
      behaviour for every other type.
    * An alias row collapses into its base, for the types that HAVE aliases only - which
      is what prints ONE line for "HANLIM TRADING SDN BHD" and "HANLIM TRADING SDN BHD
      [A/C II]". It works on the LABEL, so it could not match a code against a name.
    * The label comes from `_AXES`, the miss lane's own axis vocabulary, so the two lanes
      cannot drift. A type no axis claims keeps today's bare, unlabelled code.
    """
    # `_AXES` lives in `answer.py`, which imports THIS module, so the import is
    # function-level to keep that cycle open. One vocabulary, one place: a second copy here
    # would drift the moment an axis is added.
    from app.services.chatbot.lanes.business.answer import _AXES

    by_record: dict[str, dict[str, str]] = {}
    unkeyed: list[dict[str, str]] = []
    for x in jsc.array(entities):
        code = jsc.nullish_str(jsc.get(x, "code")).strip()
        uuid = jsc.nullish_str(jsc.get(x, "uuid")).strip()
        # The resolver's human label wins where it gave one (customers today); everything
        # else keeps the canonical code, which for a product IS what the customer typed.
        label = jsc.nullish_str(jsc.get(x, "display_name")).strip() or code
        # Whatever is about to be PRINTED is what must not be a uuid: for types with no
        # code the resolver fills `code` with the record's OWN uuid, and four promotion
        # uuids once printed under "no promotions records for ...".
        if not label or label == uuid or _UUID_RE.match(label):
            continue
        row = {"type": jsc.nullish_str(jsc.get(x, "entity_type")).strip().lower(), "code": label}
        if not uuid:
            unkeyed.append(row)
            continue
        held = by_record.get(uuid)
        if held is None or len(label) > len(held["code"]):
            by_record[uuid] = row
    rows = [*by_record.values(), *unkeyed]

    kept: list[dict[str, str]] = []
    for row in rows:
        lowered = row["code"].lower()
        if row["type"] in _ALIAS_COLLAPSE_TYPES and any(
            other is not row
            and other["type"] == row["type"]
            and other["code"].lower() != lowered
            and lowered.startswith(other["code"].lower())
            for other in rows
        ):
            continue  # an alias of a base this axis already names
        if any(k["code"].lower() == lowered for k in kept):
            continue
        kept.append(row)

    parts: list[str] = []
    claimed: set[str] = set()
    for axis in _AXES:
        types = {jsc.nullish_str(t).strip().lower() for t in (axis.get("types") or [])}
        claimed |= types
        codes = [r["code"] for r in kept if r["type"] in types]
        if codes:
            # "A", "A and B", "A, B and C" - the last join is a word so the axis boundary
            # stays readable next to the comma that separates axes.
            listed = (
                codes[0]
                if len(codes) == 1
                else f"{', '.join(codes[:-1])} and {codes[-1]}"
            )
            parts.append(f"{jsc.js_string(axis['label']).lower()} {listed}")
    # A type no axis claims keeps today's bare code, so a promotion or an attachment type is
    # still named rather than dropped by a vocabulary that does not know it.
    leftovers = [r["code"] for r in kept if r["type"] not in claimed]
    if leftovers:
        parts.append(", ".join(leftovers))
    return ", ".join(parts)


def _date_window_phrase(semantic_input: Any) -> str:
    """", dates 01/09/2026 to 30/09/2026" - the window that was searched, or "" for none.

    A miss inside a date window is a different fact from a miss over all time, and the
    customer cannot tell which they got without being told.
    """
    si = semantic_input if isinstance(semantic_input, dict) else {}
    start = _fmt_ts(si.get("date_filter_start")) if jsc.truthy(si.get("date_filter_start")) else None
    end = _fmt_ts(si.get("date_filter_end")) if jsc.truthy(si.get("date_filter_end")) else None
    if start and end:
        return f", dates {start}" if start == end else f", dates {start} to {end}"
    if start:
        return f", dates from {start}"
    if end:
        return f", dates up to {end}"
    return ""


def _names_a_shipment(ctx: dict[str, Any]) -> bool:
    """A bare container ask ("incoming TIIU6323920") is a timeline ask, not an ETA-only one.

    Evidence: live turn f07632b6-d56d-4036-944c-8200462caac3 - "incoming TIIU6323920" parses
    to `requested_attributes: []` with entity `{"raw": "TIIU6323920", "hint":
    "inbound_shipment", "confident": true}`. A question that names a specific container and
    asks for no particular attribute is a timeline ask: every recorded checkpoint comes out,
    chronologically, exactly as the `__all__` sentinel does today.

    Checked against the RESOLVED entity list first - `entity_type` is the field
    `gate.run_gate` stamps and `entity_ids_transformer`'s `TYPE_TO_PARAM` keys on - and only
    falls back to the parser's own `hint` when the resolved list carries no type at all (the
    gate ran empty, so there is nothing else to check).
    """
    entities = ctx.get("entities") if isinstance(ctx.get("entities"), list) else []
    typed = [e for e in entities if jsc.truthy(e) and jsc.truthy(jsc.get(e, "entity_type"))]
    if typed:
        return any(
            jsc.js_string(jsc.get(e, "entity_type")).strip() == "inbound_shipment" for e in typed
        )
    semantic_input = ctx.get("semantic_input")
    if isinstance(semantic_input, str):
        semantic_input = _safe_json(semantic_input)
    parsed_entities = (
        jsc.get(semantic_input, "entities") if isinstance(semantic_input, dict) else None
    )
    return any(
        jsc.truthy(e) and jsc.js_string(jsc.get(e, "hint")).strip() == "inbound_shipment"
        for e in jsc.array(parsed_entities)
    )


#: D12 (owner ruling, 8 Sep 2026, turn 8f4a8526 "SRTJC802A-1500 product details"): the
#: BASE fields a product answer ALWAYS carries, whatever `requested_attributes` says -
#: item 8's `_PRODUCT_IDENTITY_LABELS` (Product Code, Company only) meant an asked word
#: that named no base field of its own (or a wrongly-emitted `["price"]` for a message
#: that named no property at all) dropped List Price, Dimensions, Product Name and
#: Description from the reply. Discontinued flag and attachments are not `fields` rows
#: at all and were never affected by this.
_PRODUCT_IDENTITY_LABELS: frozenset[str] = frozenset(
    {"Product Code", "Product Name", "Description", "List Price", "Dimensions", "Company"}
)

_SPEC_KEY_PREFIX = "spec:"
_SPEC_SUMMARY_CAP = 8


def _normalize_spec_word(v: Any) -> str:
    """Lowercase, trim, collapse `_`/`-` to a space - the same normalization on
    both sides of a spec-vocabulary match (a registry key and a customer's own
    word disagree on separators, never on letters)."""
    return re.sub(r"[_\-]+", " ", jsc.nullish_str(v).strip().lower()).strip()


#: D12: since a base field is now ALWAYS on the page (`_PRODUCT_IDENTITY_LABELS`), an
#: asked word naming one is no longer a thing to PICK (item 8's `_BASE_FIELD_BY_ASK`
#: is retired) - it only means "do not add a miss line for this word", because the
#: field it names is already there. Single-token entry matches the whole ask EXACTLY;
#: only the one multi-token entry ("list price") may be contained in a longer ask -
#: same discipline as item 8's own matching, kept for the same reason ("seat size"
#: must not read as a hit on "size").
_BASE_PROPERTY_WORDS: frozenset[str] = frozenset(
    {
        "price", "list price", "harga", "cost",
        "dimension", "dimensions", "size", "ukuran", "saiz",
        "description", "name",
    }
)


def _names_a_base_property(norm: str) -> bool:
    for w in _BASE_PROPERTY_WORDS:
        if norm == w or (" " in w and w in norm):
            return True
    return False


_MISS_CODES_CAP = 5


def _tokens(norm: str) -> set[str]:
    return set(norm.split())


def _project_product_specs(e: dict[str, Any], req_attrs: list[Any]) -> None:
    """A1 (AC-901/AC-902): the product spec projection, product envelopes ONLY.

    A SEPARATE branch from the clearance/incoming projection above - deliberately
    not folded into it. That one is gated on `field_vocabulary` truthiness and
    would, for a no-attribute ask, strip every keyed field down to the identity
    allow-list; the compact "Specs:" line below IS the no-attribute case, so
    reusing that gate would delete the very thing this function exists to add.

    No requested_attributes: every item keeps its base fields, plus ONE synthetic
    "Specs:" field summarising up to `_SPEC_SUMMARY_CAP` populated keys ("and N
    more" beyond that). Byte-identical to before item 8.

    With requested_attributes (item 8 / D12, 8 Sep 2026), every item ALWAYS keeps its
    base fields (`_PRODUCT_IDENTITY_LABELS`: Product Code, Product Name, Description,
    List Price, Dimensions, Company) - a base field is never dropped by an ask, and an
    asked word is never "matched" to one; it is on the page regardless. Only the SPEC
    keys are on demand, per asked word:
      1. SPEC KEYS BY TOKEN CONTAINMENT - exact match on the normalised key or label
         first, else every key whose key OR label tokens contain every asked token
         ("material" reaches both `material` and `seat_material` via "Seat cover
         material"; "seat cover material" reaches `seat_material` only), rendered in
         registry order (the order the presenter emitted them).
      2. ONE MISS LINE PER ASKED WORD, not per item, for a word that matched NO spec key
         on that item - EXCEPT a word naming a base property (`_names_a_base_property`:
         price / list price / harga / cost / dimension(s) / size / ukuran / saiz /
         description / name), which produces no miss line at all: the field it names is
         already on the page, so "not recorded" would contradict what the reply just
         showed. A genuine spec miss goes into ONE `spec_misses` entry, rendered once
         AFTER the items by `output_structurer` - "*<label>:* not recorded for A, B, C
         (+N more)", label from the registry when the word matches a known key/label,
         else the asked word; codes capped at `_MISS_CODES_CAP`. (Not `summary_items`:
         that slot is the quantity-summary mode and suppresses the item rows, fetch.py's
         items loop.)
    An item with no spec hit for any asked word keeps its base fields only - byte
    identity with the no-attribute path's own field set.
    """
    vocab_raw = e.get("spec_vocabulary")
    vocab: dict[str, str] = vocab_raw if isinstance(vocab_raw, dict) else {}
    # (spec_key, label, norm_key, norm_label) per registry row, registry order kept
    vocab_rows: list[tuple[str, str, str, str]] = [
        (str(key), str(label), _normalize_spec_word(key), _normalize_spec_word(label))
        for key, label in vocab.items()
    ]

    def vocab_label_for(norm: str) -> str | None:
        """The registry label a miss line names: exact match first, else the one row
        whose key or label contains every asked token (several -> the first)."""
        for _k, label, nk, nl in vocab_rows:
            if norm in (nk, nl):
                return label
        toks = _tokens(norm)
        for _k, label, nk, nl in vocab_rows:
            if toks and (toks <= _tokens(nk) or toks <= _tokens(nl)):
                return label
        return None

    # The normalised word AND the word the customer actually typed, PAIRED (review, nit
    # 10). Two parallel lists went out of step the moment `req_attrs` carried a blank or a
    # word that normalised away - `req_attrs[asked_norms.index(norm)]` then named a
    # DIFFERENT attribute in the "no X recorded" sentence, and it only shows on the one
    # phrasing that has a blank in it.
    asked: list[tuple[str, str]] = []
    seen_norms: set[str] = set()
    for raw in req_attrs:
        text = jsc.nullish_str(raw).strip()
        if not text:
            continue
        norm = _normalize_spec_word(text)
        if norm and norm not in seen_norms:
            asked.append((norm, text))
            seen_norms.add(norm)

    missed_codes: dict[str, list[str]] = {norm: [] for norm, _ in asked}

    for it in e.get("items") or []:
        if not jsc.truthy(it) or not isinstance(jsc.get(it, "fields"), list):
            continue
        fields: list[dict[str, Any]] = it["fields"]
        code = None
        for f in fields:
            if isinstance(f, dict) and f.get("label") == "Product Code":
                code = f.get("value")
                break
        base = [
            f
            for f in fields
            if not (isinstance(f, dict) and jsc.js_string(f.get("key") or "").startswith(_SPEC_KEY_PREFIX))
        ]
        spec_fields = [
            f
            for f in fields
            if isinstance(f, dict) and jsc.js_string(f.get("key") or "").startswith(_SPEC_KEY_PREFIX)
        ]

        if not asked:
            # No attribute asked: base fields untouched, plus the compact summary.
            if spec_fields:
                shown = spec_fields[:_SPEC_SUMMARY_CAP]
                remainder = len(spec_fields) - len(shown)
                summary = ", ".join(f"{f.get('label')}: {f.get('value')}" for f in shown)
                if remainder > 0:
                    summary += f" and {remainder} more"
                it["fields"] = base + [{"key": "specs_summary", "label": "Specs", "value": summary}]
            continue

        # An attribute was asked: identity fields + the base fields + the spec keys it names.
        # D12: base fields are ALWAYS kept - no ask can drop or add one.
        kept_base = [
            f for f in base if isinstance(f, dict) and f.get("label") in _PRODUCT_IDENTITY_LABELS
        ]
        spec_norms: list[tuple[dict[str, Any], str, str]] = []  # (field, norm_key, norm_label)
        for f in spec_fields:
            raw_key = jsc.js_string(f.get("key") or "")[len(_SPEC_KEY_PREFIX):]
            spec_norms.append((f, _normalize_spec_word(raw_key), _normalize_spec_word(f.get("label"))))

        matched: list[dict[str, Any]] = []
        seen_field_ids: set[int] = {id(f) for f in kept_base}
        for norm, _asked_word in asked:
            # 1. spec keys: an exact key/label match AND every key whose key or label
            #    tokens contain every asked token - ALL of them, in registry order
            toks = _tokens(norm)
            contained = [
                f
                for f, nk, nl in spec_norms
                if norm in (nk, nl) or (toks and (toks <= _tokens(nk) or toks <= _tokens(nl)))
            ]
            hit = bool(contained)
            for f in contained:
                if id(f) not in seen_field_ids:
                    matched.append(f)
                    seen_field_ids.add(id(f))
            # 2. a spec miss - UNLESS the word names a base property, which is already
            #    on the page (kept_base, above) and needs no "not recorded" line.
            if not hit and not _names_a_base_property(norm):
                missed_codes[norm].append(jsc.js_string(code))
        it["fields"] = kept_base + matched

    # 3. one miss line per asked word, rendered ONCE after the items
    misses: list[dict[str, Any]] = []
    for norm, asked_word in asked:
        codes = missed_codes.get(norm) or []
        if not codes:
            continue
        label = vocab_label_for(norm) or asked_word
        listed = ", ".join(codes[:_MISS_CODES_CAP])
        extra = len(codes) - _MISS_CODES_CAP
        value = f"not recorded for {listed}" + (f" (+{extra} more)" if extra > 0 else "")
        misses.append({"key": f"spec_miss:{norm}", "label": label, "value": value})
    if misses:
        e["spec_misses"] = misses


def output_structurer(result: Any, ctx: dict[str, Any] | None) -> dict[str, Any]:
    """The MCP render envelope becomes a WhatsApp message. Deterministic, no LLM (H7).

    `result` is what the MCP client returned (n8n's `$('MCP Client1').first().json`) and
    `ctx` is the trigger (`semantic_input`, `entities`), so the two by-name reads become
    parameters and nothing else about the body changes.
    """
    ctx = ctx if isinstance(ctx, dict) else {}
    e = _extract_envelope(result)

    # -- restricted-field drop (A2/A5/A6, general rule) ---------------------- #
    # A presenter marks a field or summary item RESTRICTED by putting its key in
    # the envelope's `restricted_fields` (field key -> permission key, e.g.
    # "inventory.sellable", "purchase_orders.supplier" - `sorento_crm_mcp.
    # presenters._Builder.restrict`). Dropped here unless the contact's access
    # grants that permission. `ctx["access"]["attributes"]` is a list; today
    # `head/access.py::check_access` always returns it as None (Slice C wires it
    # from `contact_field_reveals`), so None is read as the EMPTY grant set and
    # every restricted field is hidden by construction - which is exactly what
    # keeps a stock/PO/SPO answer byte-identical to before this rule existed
    # (AC-903). The MCP itself stays unfiltered; this is the ONE place a
    # restricted field is ever dropped for the chatbot.
    restricted = e.get("restricted_fields")
    if isinstance(restricted, dict) and restricted:
        access_ctx = ctx.get("access") if isinstance(ctx.get("access"), dict) else {}
        granted_raw = access_ctx.get("attributes")
        granted = set(granted_raw) if isinstance(granted_raw, list) else set()

        def _keep_field(f: Any) -> bool:
            """Keep, drop, or SWAP. A restricted field that carries `granted_value` is
            a plain field with a granted suffix (D1, the compact stock block's
            "*Total:* 51 (O/S: 36)"): under the grant its value becomes the granted one,
            without it the plain value stays and the suffix never reaches the reader.
            A restricted field with no `granted_value` is dropped whole, as before."""
            if not _has_key(f):
                return True
            perm = restricted.get(jsc.js_string(f["key"]))
            if perm is None:
                return True
            has_granted_value = isinstance(f, dict) and "granted_value" in f
            if perm in granted:
                if has_granted_value:
                    f["value"] = f.pop("granted_value")
                return True
            if has_granted_value:
                f.pop("granted_value", None)
                return True
            return False

        def _filter_rows(rows: Any) -> None:
            for row in rows or []:
                if jsc.truthy(row) and isinstance(jsc.get(row, "fields"), list):
                    row["fields"] = [f for f in row["fields"] if _keep_field(f)]

        _filter_rows(e.get("items"))
        _filter_rows(e.get("summary_items"))
        # A3/A5's GROUPED shape carries the same rows a second time, and the first
        # cut of this rule filtered `items` only - so `group_by=product` on a PO
        # question rendered every supplier a dealer must never see, and
        # `group_by=supplier` printed the restricted value as the SECTION HEADING,
        # where no field filter could ever reach it. Both are closed here: every
        # group's rows go through the same `_keep_field`, and the AXIS itself is
        # refused below when the grant is not held.
        for grp in e.get("groups") or []:
            if not (jsc.truthy(grp) and isinstance(grp, dict)):
                continue
            _filter_rows(grp.get("items"))
            _filter_rows(grp.get("summary_items"))

        # THE HEADING IS NOT A FIELD. A group's `label` is the axis value itself, so a
        # restricted axis leaks by being grouped ON, whatever the rows carry. The answer
        # is to drop the grouping and answer FLAT rather than to redact the headings:
        # "Supplier A / Supplier B" with the names blanked still tells the dealer how many
        # suppliers there are and which rows share one, and an ungrouped list is the
        # honest answer to a question we may not break down.
        # The axis NAME and the restricted FIELD KEY are the same word by construction:
        # a tool may only group on an axis it renders as a field, and `group_by=supplier`
        # groups on the `supplier` field the presenter marked restricted. So the lookup
        # is the same `restricted` map, with no second table to keep in step.
        axis = group_axis(ctx)
        axis_perm = restricted.get(axis) if axis else None
        if axis_perm is not None and axis_perm not in granted:
            e["groups"] = []
            e["group_by_dropped"] = axis

    # -- requested-attribute projection ------------------------------------- #
    # The CRM dumps every clearance field the caller may see, by design: it prevents the
    # LEAK, this prevents the DUMP. KEY-based, never label-based: a label table here was
    # drift by construction and silently broke a sort when a label was renamed.
    semantic_input: Any = ctx.get("semantic_input")
    if isinstance(semantic_input, str):
        semantic_input = _safe_json(semantic_input)
    semantic_input = semantic_input if isinstance(semantic_input, dict) else {}
    req_attrs: list[Any] = (
        semantic_input.get("requested_attributes")
        if isinstance(semantic_input.get("requested_attributes"), list)
        else []
    )

    # A1 (AC-901/AC-902): the product spec projection, gated on the envelope's OWN
    # result_type - never on `field_vocabulary`/`spec_vocabulary` truthiness, so a
    # product with zero derived specs (no `spec_vocabulary` at all) still gets the
    # plain today's-four-fields answer rather than being skipped by accident.
    if jsc.js_string(e.get("result_type") or "") == "products":
        _project_product_specs(e, req_attrs)

    # H46: CONTAINS the sentinel, not IS it. `contracts.is_timeline` is the one declaration
    # (S6a put it there for exactly this consumer); re-deriving it here is what let a
    # mutation test "prove" the `not timeline` guard below was redundant.
    timeline = is_timeline(req_attrs) or (not req_attrs and _names_a_shipment(ctx))
    keep_keys = set(ALWAYS_KEPT_KEYS)
    for k in req_attrs:
        kk = jsc.nullish_str(k).strip()
        if kk:
            keep_keys.add(kk)

    # A checkpoint ask ("when is gatepass?") implies every EARLIER checkpoint in the
    # container's journey - a customer asking about gatepass wants the whole story up to
    # it, not one isolated date. `req_attrs` itself is untouched (echoed back, and drives
    # the "not recorded yet" notes below): only `keep_keys` grows.
    expanded = False
    if not timeline:
        checkpoint_idx = [
            CLEARANCE_CHECKPOINT_ORDER.index(kk)
            for k in req_attrs
            if (kk := jsc.nullish_str(k).strip()) in CLEARANCE_CHECKPOINT_ORDER
        ]
        if checkpoint_idx:
            keep_keys.update(CLEARANCE_CHECKPOINT_ORDER[: max(checkpoint_idx) + 1])
            expanded = True

    # SCOPE GUARD: projection touches the CLEARANCE-gated incoming envelope ONLY. Gate on
    # what the envelope IS, not on whether keys happen to be present - resource attachments
    # are keyed too, and gating on "anything keyed" would drop both fields of a document
    # answer and render it with nothing at all.
    clearance_envelope = jsc.js_string(e.get("result_type") or "") == "incoming_stock" or bool(
        jsc.truthy(e.get("field_vocabulary"))
    )
    any_keyed = clearance_envelope and any(
        any(_has_key(f) for f in (jsc.get(it, "fields") or []))
        for it in (e.get("items") or [])
        if jsc.truthy(it)
    )
    for it in (e.get("items") or []) if any_keyed else []:
        if not jsc.truthy(it) or not isinstance(jsc.get(it, "fields"), list):
            continue
        it["fields"] = [
            f
            for f in it["fields"]
            if (not _has_key(f))
            or jsc.js_string(f["key"]) in IDENTITY_KEYS
            or timeline
            or jsc.js_string(f["key"]) in keep_keys
        ]

    # -- chronological order -------------------------------------------------- #
    # Containers arrive on a timeline and the CRM returns them in no stable order. Rows
    # with NO usable ETA sort LAST, never first: a missing date must not masquerade as
    # "arriving soonest". Ties keep their original order.
    if any_keyed:

        def _eta_of(it: Any) -> str:
            f = jsc.find(
                jsc.get(it, "fields") or [],
                lambda x: _has_key(x) and jsc.js_string(x["key"]) == "estimated_arrival_date",
            )
            v = jsc.nullish_str(jsc.get(f, "value")) if jsc.truthy(f) else ""
            return v if _DATE_RE.match(v) else ""

        items = e.get("items") or []
        if any(_eta_of(it) for it in items):
            e["items"] = [
                it
                for _, _, it in sorted(
                    ((_eta_of(it), i, it) for i, it in enumerate(items)),
                    key=lambda triple: (triple[0] == "", triple[0], triple[1]),
                )
            ]

    # -- timeline field order: dates chronological, sorted IN PLACE ----------- #
    # A timeline should READ as a timeline. The CRM's own order is NARRATIVE, not
    # value-ordered. Only the SEQUENCE within the date block is this node's business:
    # LAYOUT belongs to the CRM, and an earlier version that re-emitted `[...facts,
    # ...dates]` dragged the ETA below the quantity and undid a merged CRM change.
    # A field counts as a date by its VALUE, never by its key name. An expanded checkpoint
    # ask is a partial timeline and reads the same way.
    if timeline or expanded:

        def _date_of(f: Any) -> str | None:
            v = jsc.get(f, "value") if jsc.truthy(f) else None
            return v[:10] if isinstance(v, str) and _DATE_RE.match(v) else None

        for it in e.get("items") or []:
            if not jsc.truthy(it) or not isinstance(jsc.get(it, "fields"), list):
                continue
            slots = [i for i, f in enumerate(it["fields"]) if _date_of(f)]
            if len(slots) < 2:
                continue  # nothing to reorder
            ordered_fields = sorted(
                (it["fields"][i] for i in slots), key=lambda f: _date_of(f) or ""
            )
            for n, slot in enumerate(slots):
                it["fields"][slot] = ordered_fields[n]

    # -- denied vs not-yet-reached ------------------------------------------- #
    # "There is no gatepass date yet" is a LIE when the truth is "you may not see it".
    denied_map: dict[str, Any] = {}
    for d in ((e.get("field_access") or {}).get("denied") or []) if isinstance(
        e.get("field_access"), dict
    ) else []:
        key = jsc.nullish_str(jsc.get(d, "field")).strip()
        if key:
            denied_map[key] = d

    # Label source, in order: what the CRM called it on a row that DOES carry the key, then
    # the CRM's own `field_vocabulary`, then the denial entry's label, then the key
    # humanised. No local vocabulary table - that is the drift this rebuild removed.
    label_by_key: dict[str, Any] = {}
    for it in e.get("items") or []:
        for f in (jsc.get(it, "fields") or []) if jsc.truthy(it) else []:
            if _has_key(f) and jsc.truthy(f.get("label")) and jsc.js_string(f["key"]) not in label_by_key:
                label_by_key[jsc.js_string(f["key"])] = f["label"]
    raw_vocab = e.get("field_vocabulary")
    vocab: dict[str, Any] = raw_vocab if isinstance(raw_vocab, dict) else {}

    def _label_for(k: str, d: Any) -> str:
        return jsc.js_string(
            label_by_key.get(k)
            or vocab.get(k)
            or (jsc.get(d, "label") or jsc.get(d, "field_label") if jsc.truthy(d) else None)
            or _humanise(k)
        )

    # PER-ROW absence, GLOBAL denial: different kinds of fact, different rendering. Absence
    # is per-ROW data (one container had the date, three did not); denial is per-CONTACT
    # permission, identical on every row, so it stays ONE line.
    if any_keyed and not timeline:
        for it in e.get("items") or []:
            if not jsc.truthy(it) or not isinstance(jsc.get(it, "fields"), list):
                continue
            have = {jsc.js_string(f["key"]) for f in it["fields"] if _has_key(f)}
            for k in req_attrs:
                kk = jsc.nullish_str(k).strip()
                if not kk or kk in have or kk in denied_map:
                    continue
                it["fields"].append(
                    {"key": kk, "label": _label_for(kk, None), "value": "not recorded yet"}
                )

    access_notes: list[str] = []
    # The `not timeline` here IS LOAD-BEARING, and the reasoning that once called it
    # redundant was wrong: `is_timeline` CONTAINS the sentinel, so a mixed
    # `['__all__', 'eta_delay_date']` with that key denied WOULD emit the note without it.
    # Every fixture used the sentinel alone, so the mutation test was pointed at the one
    # shape that cannot discriminate.
    for k in req_attrs if (any_keyed and not timeline) else []:
        kk = jsc.nullish_str(k).strip()
        if not kk:
            continue
        d = denied_map.get(kk)
        if not d:
            continue  # absence is annotated per row above
        access_notes.append(
            f"I can't share the {_label_for(kk, d).lower()} {_EM_DASH} "
            "please check with the office."
        )

    # The PRESENTER owns the intro whenever it emits `summary_items` - it states the page
    # geometry there, and this override would replace it with a sentence that says less.
    qs_presenter_owns_intro = bool(
        isinstance(e.get("summary_items"), list)
        and len(e["summary_items"])
        and e.get("has_result") is True
    )
    order_status = semantic_input.get("order_status")
    if (
        jsc.truthy(e.get("has_result"))
        and isinstance(e.get("items"), list)
        and len(e["items"])
        and order_status in ("outstanding", "delivered")
        and not qs_presenter_owns_intro
    ):
        e["intro"] = (
            "Here are the outstanding orders I found."
            if order_status == "outstanding"
            else "Here are the delivered orders I found."
        )

    msg = jsc.js_string(e.get("intro") or "Here are the results.").strip() + "\n\n"

    # The summary follows the ANSWER, not the rows: `has_result is True`, never truthiness,
    # because a boolean arriving as the STRING "false" is truthy and would print a summary
    # onto a no-result reply. Byte-inert without `summary_items`.
    qs_render = bool(
        isinstance(e.get("summary_items"), list)
        and len(e["summary_items"])
        and e.get("has_result") is True
        and isinstance(e.get("items"), list)
        and len(e["items"])
    )
    if qs_render:
        for si in e["summary_items"]:
            if not isinstance(si, dict) or not isinstance(si.get("fields"), list):
                continue  # a hostile entry is skipped, never thrown on
            summary_lines = "\n".join(
                # `${f.label}` on an absent key renders the WORD `undefined`, not "None"
                # - and this string is sent to a customer.
                f"*{jsc.js_string(f.get('label', jsc.UNDEFINED))}:* {_fmt_value(f.get('value'))}"
                for f in si["fields"]
                if isinstance(f, dict)
            )
            if summary_lines:
                msg += summary_lines + "\n\n"

    action_links = e.get("action_links") or []
    for i, link in enumerate(action_links):
        label = jsc.get(link, "label")
        url = jsc.get(link, "url", jsc.UNDEFINED)
        msg += (
            f"{i + 1}. *{jsc.js_string(label) if jsc.truthy(label) else 'Link'}:* "
            f"{jsc.js_string(url)}\n"
        )
    if len(action_links):
        msg += "\n"

    def _item_line(position: int, it: Any) -> str:
        field_lines = "\n".join(
            f"*{jsc.js_string(jsc.get(f, 'label', jsc.UNDEFINED))}:* "
            f"{_fmt_value(jsc.get(f, 'value'))}"
            for f in (jsc.get(it, "fields") or [])
        )
        line = f"{position}. {field_lines}"
        flags = jsc.get(it, "flags")
        if jsc.truthy(flags) and jsc.truthy(jsc.get(flags, "discontinued")):
            line += "\n⚠️  *(PRODUCT DISCONTINUED)*"
        if jsc.truthy(flags) and jsc.truthy(jsc.get(flags, "expired")):
            line += "\n⚠️  *(EXPIRED)*"
        if jsc.truthy(flags) and jsc.truthy(jsc.get(flags, "unallocated")):
            line += "\n\U0001f6a9  *(PENDING ALLOCATION)*"
        elif jsc.truthy(flags) and jsc.truthy(jsc.get(flags, "partially_allocated")):
            line += "\n\U0001f6a9  *(PARTIAL ALLOCATION)*"
        return line

    # A3 (AC-905/AC-906): grouped sections, ONE generic branch for every tool - the
    # presenter already mapped `groups[].rows` through the same row->item builder
    # the flat list uses (`sorento_crm_mcp.presenters`), so this only adds a
    # heading per bucket and keeps the running item number global across groups
    # (a positional pick still resolves against `answers`, which stays the FLAT
    # `e.get("items")` below - grouping is presentation only, never carried state).
    groups_render = bool(
        isinstance(e.get("groups"), list) and len(e["groups"]) and not qs_render
    )
    if groups_render:
        position = 0
        for grp in e["groups"]:
            if not isinstance(grp, dict) or not isinstance(grp.get("items"), list):
                continue
            label = jsc.js_string(grp.get("label") or grp.get("key") or "").strip()
            if label:
                msg += f"*{label}*\n"
            for it in grp["items"]:
                position += 1
                msg += _item_line(position, it) + "\n\n"

    # A quantity ask prints the SUMMARY ONLY: the two order perspectives are separate
    # questions and the parser already separates them. The ROWS are suppressed from the
    # MESSAGE, never from the STATE - `answers` below is untouched, so a positional pick
    # still resolves against the same page rows. And ONLY the numbered list goes: the
    # multi-company note reads `e.items` for attribution and must keep seeing the real rows.
    for i, it in enumerate([] if (qs_render or groups_render) else (e.get("items") or [])):
        msg += _item_line(i + 1, it) + "\n\n"
    # Item 8: the product projection's miss lines, one per asked word, AFTER the items
    # (`_project_product_specs`). Byte-inert when the key is absent.
    for miss in e.get("spec_misses") or []:
        if isinstance(miss, dict):
            msg += f"*{jsc.js_string(miss.get('label', jsc.UNDEFINED))}:* {_fmt_value(miss.get('value'))}\n\n"

    # -- multi-company: name the companies that came back EMPTY --------------- #
    # A FOUND row already says which company it belongs to. What the customer cannot see is
    # the company that WAS searched and returned nothing.
    raw_lookup_cos = e.get("lookup_companies")
    lookup_cos: list[Any] = raw_lookup_cos if isinstance(raw_lookup_cos, list) else []
    if len(lookup_cos) > 1:

        def _co_of_row(it: Any) -> str:
            f = jsc.find(
                jsc.get(it, "fields") or [],
                lambda x: jsc.truthy(x)
                and (jsc.js_string(jsc.get(x, "key") or "") == "company_name" or jsc.get(x, "label") == "Company"),
            )
            return jsc.nullish_str(jsc.get(f, "value")).strip() if jsc.truthy(f) else ""

        shown_cos = {c for c in (_co_of_row(it) for it in (e.get("items") or [])) if c}
        # NEVER assert absence from a NEGATIVE. Rows present but unattributed means the CRM
        # did not stamp them, and declaring every lookup company silent underneath rows we
        # just printed is a worse statement than the one this block exists to fix.
        can_attribute = not len(e.get("items") or []) or len(shown_cos) > 0
        # `code` is the canonical code the customer recognises, never a uuid: for types with
        # no code the resolver fills it with the record's OWN uuid, and four promotion uuids
        # once printed under "no promotions records for ...".
        entities0 = ctx.get("entities")
        if isinstance(entities0, str):
            entities0 = _safe_json(entities0)
        subject = _axis_labelled_subject(entities0)
        # The noun comes from the envelope's own `result_type`, so there is no local
        # vocabulary here to go stale.
        noun = jsc.js_string(e.get("result_type") or "").replace("_", " ").strip()
        what = (f"{noun} records" if noun else "records") + (
            f" found for {subject}{_date_window_phrase(semantic_input)}" if subject else ""
        )
        silent = [
            n
            for n in (jsc.nullish_str(jsc.get(c, "name")).strip() for c in lookup_cos)
            if n and n not in shown_cos
        ]
        if can_attribute and silent:
            # ONE sentence for all the silent companies, not one per company. The subject is
            # the same in every copy, so repeating it per company said the customer's own
            # name back to them once per lookup - and on a total miss (nothing found
            # anywhere) that is the whole reply, twice over. A single silent company is
            # byte-identical to before.
            names = (
                silent[0]
                if len(silent) == 1
                else f"{', '.join(silent[:-1])} and {silent[-1]}"
            )
            msg += f"*{names}:* no {what}." + "\n\n"

    if access_notes:
        msg += "\n".join(access_notes) + "\n\n"

    ts = _fmt_ts(e.get("last_updated_at"))
    if ts:
        msg += f"_Data last updated: {ts}_"

    # E2 (attribute-first asks, AC-1316): a HAS turn's set-answer header, PREPENDED
    # as its own line ahead of everything above - the block itself (intro, items,
    # summaries, ...) is untouched. Deferred-import: `answer.py` imports FROM this
    # module (`DATE_PARAMS`, `space_id_or_default`), so a module-level import here
    # would be circular.
    predicate = ctx.get("predicate") if isinstance(ctx.get("predicate"), dict) else None
    if predicate is not None:
        from app.services.chatbot.lanes.business.answer import (
            build_set_header,
            build_set_page_header,
            set_noun_for,
        )

        qualifying_total = jsc.get(predicate, "qualifying_total") or 0
        require = jsc.get(predicate, "require") or {}
        # E3/AC-1317: a "more" continuation page carries its OWN pre-known
        # `set_noun` and page bounds (`page`) - a "more" turn runs no resolver
        # call, so there are no fresh `class_labels` to re-derive one from.
        page = jsc.get(predicate, "page")
        if isinstance(page, dict):
            header = build_set_page_header(
                qualifying_total,
                jsc.get(page, "start"),
                jsc.get(page, "end"),
                jsc.js_string(jsc.get(page, "set_noun")) or "products",
                require,
            )
        else:
            # R8 (console fix round 2, AC-1330): `shown` is distinct PRODUCTS
            # rendered, never tool rows - a stock/cert answer carries one row per
            # warehouse/certificate, so five products across three warehouses is
            # fifteen rows and would have overstated "Showing 15" for a five-page
            # answer. Falls back to the row count when no row carries a product
            # code at all (a result type this header never fires for today).
            items0 = e.get("items") or []

            def _product_code_of_row(it: Any) -> str:
                fields = jsc.get(it, "fields")
                if not isinstance(fields, list):
                    return ""
                for f in fields:
                    if isinstance(f, dict) and f.get("label") == "Product Code":
                        return jsc.nullish_str(f.get("value")).strip()
                return ""

            shown_codes = {c for c in (_product_code_of_row(it) for it in items0) if c}
            shown = len(shown_codes) if shown_codes else len(items0)
            set_noun = set_noun_for(jsc.array(jsc.get(predicate, "class_labels")))
            # `set_noun_for` is always plural (its own contract, AC-1316) - singular
            # only for the ONE-qualifying-product header ("1 tap has ...", never
            # "1 taps has ..."), by dropping the trailing "s" our own pluralisation
            # always adds.
            if qualifying_total == 1 and set_noun.endswith("s"):
                set_noun = set_noun[:-1]
            header = build_set_header(qualifying_total, shown, set_noun, require)
        msg = f"{header}\n{msg}"

    out: dict[str, Any] = {
        "response": msg.strip(),
        "response_intro": e.get("intro"),
        # GROUPED: the flat `items` order and the NUMBERED order the customer just read
        # are two different orders, and `answers` is what a positional pick ("2") resolves
        # against - so a grouped answer used to hand back a different record than the one
        # numbered 2 on screen (review, should-fix 4). Flattened in RENDER order, which is
        # the only order the customer can be talking about. Ungrouped, this is `items`
        # unchanged, so nothing else moves.
        "answers": _rendered_answers(e) if groups_render else e.get("items"),
    }
    # Spread-in, not defaulted: a reply with no summary keeps EXACTLY the keys it has today.
    if qs_render:
        out["summary_items"] = e["summary_items"]
    if groups_render:
        out["groups"] = e["groups"]
    out.update(
        {
            "attachments": e.get("attachments") or [],
            "action_links": e.get("action_links") or [],
            "last_updated_at": e.get("last_updated_at") or None,
            "has_result": bool(jsc.truthy(e.get("has_result"))),
            "alternatives": e["alternatives"] if isinstance(e.get("alternatives"), list) else [],
            "relaxed_axis": e.get("relaxed_axis") if "relaxed_axis" in e else None,
            "field_access": e.get("field_access") if "field_access" in e else None,
            "requested_attributes": req_attrs,
            # false = the CRM served no keyed fields, so projection and access notes were
            # skipped. Sustained false with a non-empty `requested_attributes` means the MCP
            # process needs restarting, NOT that the parser stopped emitting keys.
            "keys_served": any_keyed,
        }
    )
    if len(lookup_cos) > 1:
        out["lookup_companies"] = lookup_cos
    return out


# --------------------------------------------------------------------------- #
# fetch-result
# --------------------------------------------------------------------------- #


def fetch_result(
    item: dict[str, Any] | None, *, tool: Any = None, tier_probe: Any = None
) -> dict[str, Any]:
    """`sub-fetch-results`' ONE exit, three mutually exclusive arms.

    Content, not node identity, tells them apart - and each discriminating field is one the
    respective DOWNSTREAM reader already depends on, not a new assumption:
    `tier_any_available` is the boolean `if-tier-has-any` reads, `error` is the field the
    error path already reads, and anything else is the normal CRM envelope.

    `tier_probe` is ALWAYS present on the result arm (a value or `None`), never omitted: the
    tier-probe arm ran on about 3 of 220 live turns that reach this exit at all, so the key
    has to be stable or its reader needs a guard nobody wrote.
    """
    j = item if isinstance(item, dict) else {}
    if isinstance(j.get("tier_any_available"), bool):
        return {**j, "_fetch_arm": "tier-ask"}
    if isinstance(j.get("error"), str):
        return {**j, "_fetch_arm": "error"}
    return {**j, "tool": tool, "tier_probe": tier_probe, "_fetch_arm": "result"}
