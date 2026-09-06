"""Port of `sub-fetch-results` + `sub-get-rag` + `sub-get-results` (S6b, AC-604 to AC-606).

The business lane's fetch step: pick ONE tool, call it over MCP, render the answer
deterministically. Six node bodies become six functions, line for line against the exported
JavaScript, with the same `jsc` shim S6a uses for JS truthiness / `String()` / `Number()`.

Three hazards are fixed here rather than reproduced, and each says so at its own site:

* **H53** - `sub-get-rag`'s pgvector SQL is RETIRED. Tool search is
  `EmbeddingReadService.search_tool_chunks` behind the `tool_search` seam, so no query
  leaves the service layer. Nothing in this module names a table or writes SQL.
* **H52** - the MCP endpoint is `settings.ai_assistant_mcp_url`, bound in `services.py`.
  n8n bakes a raw IP endpoint into TWO nodes; this module contains no host, no port and no
  scheme at all, and `call_tool` is a pass-through onto whatever client it is handed. The
  absence is mechanical: `test_s6b_fetch_lane.py` greps this file's source for both.
* **H11** - `tool-filter.js` returns `[]` on zero tools and that empty array is
  indistinguishable from "ran and found nothing to say". `tool_filter` keeps the empty
  item list for parity (D8) and adds `outcome`, which the caller can act on.
* **H58** - the pick is an argmax over an embedded catalogue that contains WRITE tools
  (`crm_order_cancel`, `crm_complaint_close`, the two purchase-request approvals,
  `crm_it_support_ticket_create`, `crm_ideation_turn`), and `tool_filter` takes the top hit
  with no further test. `CHATBOT_READ_ONLY_TOOLS` below is the allow-list: the chatbot's
  retrieval seam (`services._tool_search`) drops everything else from the candidate list,
  and `ensure_read_only` refuses it at both call seams anyway. The POOL keeps the write
  tools, on purpose - the in-app AI assistant retrieves them and confirms with a human
  before each one, which is a gate this chatbot does not have.

**H43 is moot, not fixed.** The n8n query's `$4` is `domain`, LIKE-matched against
`source_id`, and some live call sites never bind it. In process `domain` is a parameter of
one function call, so `domain=None` means "no filter" by construction and can never mean
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

    Explicitly NOT the first array element - `sub-get-rag`'s final Code node collapses
    `source_id` to a name and SUMS the similarities, so the SQL's best-first order stops
    being provably maximal the moment a tool has two source ids.

    Emitting exactly one item is structural, not incidental: the per-tool fan-out that used
    to sit downstream is deleted, so two items here would run the whole fetch, compile and
    send chain twice - two WhatsApp messages to one customer.
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
    return ToolPick(
        items=[
            {
                "json": {
                    **(best if isinstance(best, dict) else {}),
                    "_tool_pick": {
                        "chosen": _label(best),
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


def rag_query_params(
    embedding: list[float], *, source_type: Any, limit: Any, domain: Any
) -> dict[str, Any]:
    """`sub-get-rag`'s first Code node: the embedding becomes the SQL's bound parameters.

    Ported for REPLAY rather than for use: in process there is no `$1..$4` to bind, so the
    only consumer is `test_replay.py`. It is here because the node has 38 real captures and
    grading it is what proves the port reads the embedding response the same way n8n does -
    `$json.data[0].embedding`, and the pgvector literal is `[a,b,c]` with no spaces.
    """
    return {
        "vector_text": "[" + ",".join(jsc.js_string(v) for v in jsc.array(embedding)) + "]",
        "source_type": source_type,
        "limit": limit,
        "domain": domain,
    }


def collapse_tool_rows(rows: Any) -> list[dict[str, Any]]:
    """`sub-get-rag`'s second Code node: `source_id` -> name, similarities SUMMED.

    `implemented::crm_forms_management_forms_list` becomes `crm_forms_management_forms_list`
    and every chunk of the same tool adds to one score. This is exactly why `tool_filter`
    cannot take the SQL's first row: once a tool has two source ids the best-first order
    stops being provably maximal.
    """
    summed: dict[str, dict[str, Any]] = {}
    for entry in jsc.array(rows):
        raw = jsc.get(entry, "source_id") or ""
        parts = jsc.js_string(raw).split("::")
        # `raw.split('::')[1] || raw` - the `||` is load-bearing: a source id that ends in
        # `::` splits to an EMPTY second segment, which is falsy, and the JS falls back to
        # the whole id rather than keying every such row under "".
        candidate = parts[1] if len(parts) > 1 else ""
        name = candidate if jsc.truthy(candidate) else jsc.js_string(raw)
        if name not in summed:
            summed[name] = {"name": name, "similarity": 0}
        # `+= undefined` is NaN in JS, not a TypeError. A row with no similarity therefore
        # poisons its tool's score to NaN, which `_score` then reads as -Infinity: last.
        summed[name]["similarity"] += jsc.js_number(
            jsc.get(entry, "similarity", jsc.UNDEFINED)
        )
    return list(summed.values())


def select_tool(db: Any, *, query: str, domain: str | None, services: Any) -> list[dict[str, Any]]:
    """`sub-get-rag`, end to end: embed the query, search, collapse to `[{name, similarity}]`.

    `db` is accepted and deliberately UNUSED: the seams are already bound to a session by
    `services.py`, and taking the parameter keeps the call site honest about the fact that a
    session existed - while this function itself holds none across the embedding call
    (the plan's capacity rule).
    """
    _ = db
    embedding = services.embed(query)
    return services.tool_search(embedding, query=query, domain=domain)


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
}

ORDER_TOOLS: frozenset[str] = frozenset(
    {"crm_order_management_orders_list", "crm_order_management_orders_by_product_list"}
)

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

    # order_status (order tools only): "outstanding" | "delivered"; omitted when null.
    if tool_name in ORDER_TOOLS and jsc.get(semantic_input, "order_status") in (
        "outstanding",
        "delivered",
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
# in the Tool-RAG pool - the in-app AI assistant retrieves them ON PURPOSE and gates each
# behind a user confirmation and a permission check. The chatbot has no user to confirm
# with, which is the whole difference.
CHATBOT_READ_ONLY_TOOLS: frozenset[str] = frozenset(
    {
        "crm_certificates_list",
        "crm_complaint_analytics",
        "crm_complaints_list",
        "crm_forms_management_forms_list",
        "crm_incoming_stock_by_product",
        "crm_incoming_stock_list",
        "crm_incoming_stock_shipments",
        "crm_inventory_stock_balance_list",
        "crm_inventory_warehouses_list",
        # POST, and still a read: the body carries the keyword because it does not fit in
        # a query string. Same for the two below.
        "crm_lookup_resolve",
        "crm_marketing_promotion_attachments_list",
        "crm_marketing_promotion_products_list",
        "crm_marketing_promotions_list",
        "crm_master_brands_list",
        "crm_master_customers_list",
        "crm_master_product_attachments_list",
        "crm_master_product_categories_list",
        "crm_master_products_list",
        "crm_master_units_of_measure_list",
        "crm_order_analytics",
        "crm_order_management_orders_by_product_list",
        "crm_order_management_orders_list",
        "crm_portal_link_get",
        "crm_project_detail",
        "crm_project_forecast",
        "crm_project_quotations_list",
        "crm_projects_list",
        "crm_resource_attachments_catalogue",
        "crm_resource_attachments_current_stock_list",
        "crm_resource_attachments_list",
        "crm_sla_conversation_event_logs_list",
        "crm_sla_conversation_tracking_dashboard",
        "crm_sla_conversation_tracking_list",
        "crm_system_tool_capabilities_summary",
        "user_guides_read",
    }
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
    The tool is chosen by cosine similarity and `tool_filter` takes the single top hit with
    no further test, so until now the only thing standing between a customer's phrasing and
    `crm_order_cancel` was that no phrasing had scored it first. The chatbot's retrieval
    seam (`services._tool_search`) drops write tools from the candidate list, which is what
    stops them being PICKED; this is what stops one being CALLED however it was named -
    including the tier probe and a tool name that arrived on a payload rather than from the
    search.
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

    * One label per RECORD. A customer reached both by its account code and by its name
      arrives as two rows on one uuid; the longer of the two is the name, and the account
      code is an internal identifier the customer never typed and cannot check. (The gate
      drops the resolver's `match_field` today; when it carries it, that field is the exact
      test and replaces the length tie-break.)
    * An alias row collapses into its base, for the types that HAVE aliases only.
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
        # `code` is the canonical code the customer recognises, never a uuid: for types with
        # no code the resolver fills it with the record's OWN uuid, and four promotion uuids
        # once printed under "no promotions records for ...".
        if not code or code == uuid or _UUID_RE.match(code):
            continue
        row = {"type": jsc.nullish_str(jsc.get(x, "entity_type")).strip().lower(), "code": code}
        if not uuid:
            unkeyed.append(row)
            continue
        held = by_record.get(uuid)
        if held is None or len(code) > len(held["code"]):
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


def output_structurer(result: Any, ctx: dict[str, Any] | None) -> dict[str, Any]:
    """The MCP render envelope becomes a WhatsApp message. Deterministic, no LLM (H7).

    `result` is what the MCP client returned (n8n's `$('MCP Client1').first().json`) and
    `ctx` is the trigger (`semantic_input`, `entities`), so the two by-name reads become
    parameters and nothing else about the body changes.
    """
    ctx = ctx if isinstance(ctx, dict) else {}
    e = _extract_envelope(result)

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

    # H46: CONTAINS the sentinel, not IS it. `contracts.is_timeline` is the one declaration
    # (S6a put it there for exactly this consumer); re-deriving it here is what let a
    # mutation test "prove" the `not timeline` guard below was redundant.
    timeline = is_timeline(req_attrs)
    keep_keys = set(ALWAYS_KEPT_KEYS)
    for k in req_attrs:
        kk = jsc.nullish_str(k).strip()
        if kk:
            keep_keys.add(kk)

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
    # A field counts as a date by its VALUE, never by its key name.
    if timeline:

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

    # A quantity ask prints the SUMMARY ONLY: the two order perspectives are separate
    # questions and the parser already separates them. The ROWS are suppressed from the
    # MESSAGE, never from the STATE - `answers` below is untouched, so a positional pick
    # still resolves against the same page rows. And ONLY the numbered list goes: the
    # multi-company note reads `e.items` for attribution and must keep seeing the real rows.
    for i, it in enumerate([] if qs_render else (e.get("items") or [])):
        field_lines = "\n".join(
            f"*{jsc.js_string(jsc.get(f, 'label', jsc.UNDEFINED))}:* "
            f"{_fmt_value(jsc.get(f, 'value'))}"
            for f in (jsc.get(it, "fields") or [])
        )
        line = f"{i + 1}. {field_lines}"
        flags = jsc.get(it, "flags")
        if jsc.truthy(flags) and jsc.truthy(jsc.get(flags, "discontinued")):
            line += "\n⚠️  *(PRODUCT DISCONTINUED)*"
        if jsc.truthy(flags) and jsc.truthy(jsc.get(flags, "expired")):
            line += "\n⚠️  *(EXPIRED)*"
        if jsc.truthy(flags) and jsc.truthy(jsc.get(flags, "unallocated")):
            line += "\n\U0001f6a9  *(PENDING ALLOCATION)*"
        elif jsc.truthy(flags) and jsc.truthy(jsc.get(flags, "partially_allocated")):
            line += "\n\U0001f6a9  *(PARTIAL ALLOCATION)*"
        msg += line + "\n\n"

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

    out: dict[str, Any] = {
        "response": msg.strip(),
        "response_intro": e.get("intro"),
        "answers": e.get("items"),
    }
    # Spread-in, not defaulted: a reply with no summary keeps EXACTLY the keys it has today.
    if qs_render:
        out["summary_items"] = e["summary_items"]
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
