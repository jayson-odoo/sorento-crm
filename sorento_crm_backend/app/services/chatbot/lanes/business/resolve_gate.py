"""Port of `sub-resolve-and-gate` (RS-8): 28 nodes, one function, four exits.

`run()` walks the sub's graph in edge order and returns the item ONE of the four
`resolve-exit-*` arms would have emitted - `_exit_kind` plus the six named contract
fields plus that arm's own item, spread FIRST (LESSONS 94: each arm carries a different
item, and the spread order is what keeps `not-found-error-message`'s base intact).

n8n SNAPSHOTS every node's output. `$('resolve-entity').first().json` on the offer arm
does NOT show the keys `disallowed-entity-gate` added to its own input object, even
though within one JavaScript execution those are the same object - the run data is
serialized when the node finishes. Reproduced with `deepcopy` at every hand-off; the
`resolve-exit-offer` captures are what prove it (`resolved` carries the resolver's ten
keys and not one gate key).

Nodes reproduced, in edge order::

    build-ctx / item      the two carriers, with their contract throws
    entry-gate            entry === 'access_check'
    get-access-types      services.access_types
    Aggregate             {name: [...]} across the returned rows
    tier-gate             tier_gate.tier_gate()
    If4                   $json.name.length > 0
    resolve-entity        services.resolve_entity, body byte-equal to the n8n jsonBody
    disallowed-entity-gate gate.run_gate()
    build-ctx-resolved    {...gate, ctx: {...ctx, resolved, entities, gate}}
    If3                   the three-clause miss gate
    If-incoming-picker    require_specific && domain === 'incoming'
    If-customer-picker    customer_probe_entities.length > 0
    probe-*               services.probe
    annotate-*-picker     pickers.annotate_incoming / annotate_customer
    resolve-exit-*        the four arms
"""
from __future__ import annotations

import logging
import re
from copy import deepcopy
from typing import Any

from app.services.chatbot import jsc
from app.services.chatbot.contracts import EXIT_CONTRACT_FIELDS
from app.services.chatbot.lanes.business import pickers
from app.services.chatbot.lanes.business.gate import run_gate
from app.services.chatbot.lanes.business.services import ResolveGateServices
from app.services.chatbot.lanes.business.tier_gate import tier_gate as run_tier_gate

logger = logging.getLogger(__name__)

# `v.replace(/[-\s]+/g, '')` from the resolve-entity body's product-token fold.
_PRODUCT_FOLD = re.compile(r"[-\s]+")

# The two `sub-get-results` tools the pickers probe with, from the probe nodes' own
# `tool` parameters. Not a registry: two literals, named where they are used.
INCOMING_PROBE_TOOL = "crm_incoming_stock_list"
CUSTOMER_PROBE_TOOL = "crm_order_management_orders_list"

# The probe's injected default window, from `probe-customer-orders`' semantic_input
# expression (`$now.minus({days: 90})`). `annotate-customer-picker` mirrors this rule to
# decide whether its miss claim says "no recent delivery" or "no delivery"; the two are
# two halves of one sentence.
CUSTOMER_PROBE_DEFAULT_WINDOW_DAYS = pickers.CUSTOMER_PROBE_WINDOW_DAYS


def default_probe_start() -> str:
    """`$now.minus({days: 90}).toFormat('yyyy-MM-dd')` - the customer probe's window.

    n8n's `$now` is the workflow timezone (Malaysia), not UTC, so a turn taken in the
    eight hours after UTC midnight would otherwise probe a window one day wider than live
    does. Passed INTO `run()` rather than read there, so a replay is deterministic.
    """
    from datetime import datetime, timedelta, timezone

    now_myt = datetime.now(timezone.utc) + timedelta(hours=8)
    return (now_myt - timedelta(days=CUSTOMER_PROBE_DEFAULT_WINDOW_DAYS)).strftime("%Y-%m-%d")


class ResolveGateContractError(ValueError):
    """`build-ctx` / `item` refused the trigger payload, with the sub's own wording."""


def _snapshot(value: Any) -> Any:
    """What n8n's run data does to a node's output before the next node reads it."""
    return deepcopy(value)


# --------------------------------------------------------------------------- #
# Carriers
# --------------------------------------------------------------------------- #


def build_ctx(trigger: dict[str, Any]) -> dict[str, Any]:
    """`build-ctx` - the ctx carrier, with its contract throw.

    Returns `t.ctx` VERBATIM, which is the CARRIER object `{ctx: <the real ctx>}`, not the
    ctx itself: `Call 'sub-resolve-and-gate'` sends `ctx: {{ $('build-ctx').first().json }}`
    from `sub-main-processing`, whose own `build-ctx` emits `{ctx}`. That is why every
    reader in this sub writes `$('build-ctx').first().json.ctx.<key>` and why `run()` takes
    the INNER value.
    """
    ctx = trigger.get("ctx")
    if ctx is None or not isinstance(ctx, dict):
        raise ResolveGateContractError(
            "sub-resolve-and-gate: the trigger carried no `ctx` object - the contract is "
            "{ ctx, entry, item, is_test }"
        )
    return ctx


def carry_item(trigger: dict[str, Any]) -> dict[str, Any]:
    """`item` - re-emits the REAL item the caller was flowing, unchanged."""
    item = trigger.get("item")
    if item is None or not isinstance(item, dict):
        raise ResolveGateContractError(
            "sub-resolve-and-gate: the trigger carried no `item` object - the contract is "
            "{ ctx, entry, item, is_test }"
        )
    return item


def _parser_output(ctx: dict[str, Any]) -> dict[str, Any]:
    """`ctx.parse.output ?? {}`."""
    output = jsc.get(jsc.get(ctx, "parse"), "output")
    return output if isinstance(output, dict) else {}


# --------------------------------------------------------------------------- #
# get-access-types -> Aggregate
# --------------------------------------------------------------------------- #


def aggregate_names(rows: Any) -> dict[str, Any]:
    """The `Aggregate` node over field `name`.

    n8n's Aggregate skips an item that does not carry the field (`keepMissing` is off),
    which is also what makes the `alwaysOutputData` empty item on a zero-row read produce
    `{name: []}` rather than `{name: [undefined]}` - and `If4` then takes its FALSE leg.
    """
    return {"name": [row["name"] for row in jsc.array(rows) if isinstance(row, dict) and "name" in row]}


# --------------------------------------------------------------------------- #
# resolve-entity
# --------------------------------------------------------------------------- #


def _query_text(ctx: dict[str, Any]) -> str:
    """The `query` half of the jsonBody, including its own try/catch fallback to ''."""
    try:
        text = jsc.get(ctx, "text")
        inner = jsc.get(jsc.get(text, "message"), "message")
        value = jsc.get(inner, "text")
        if not jsc.truthy(value):
            value = jsc.get(jsc.get(inner, "attachment"), "description")
        return jsc.js_string(value) if jsc.truthy(value) else ""
    except Exception:  # noqa: BLE001 - `catch (_err) { return ''; }`
        return ""


def _token_of(entity: Any) -> Any:
    """`String(x.canonical_code ?? '').trim() || (x.raw ?? '')`, product-folded.

    The fold is what makes "mfg6651-gm" reach the resolver as "mfg6651gm", and the
    dropped-filter gate's separator-insensitive comparison exists precisely because of it.
    A non-string `raw` on a product entity throws here exactly as it does in n8n.
    """
    value = jsc.nullish_str(jsc.get(entity, "canonical_code")).strip()
    if value == "":
        raw = jsc.get(entity, "raw")
        value = raw if raw is not None else ""
    if jsc.lower_or_empty(jsc.get(entity, "hint")) == "product":
        return _PRODUCT_FOLD.sub("", value)
    return value


def resolve_entity_body(ctx: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    """The `resolve-entity` httpRequest jsonBody, key for key.

    `entity_pins` (H38) is OMITTED in AND mode and when nothing is pinned, which is what
    the n8n expression's `Object.keys(_pins).length ? ... : ''` does. Sending it in AND
    mode is a 400 by the route's own rule, so the omission is load-bearing, not tidiness.

    `dry_run` is the ONE key n8n's body does not have, and it is not a resolution input:
    it tells the endpoint to skip its `ai_assistant_usage_logs` row, which is the last
    write a D14 test turn could otherwise reach through this lane. The resolution is
    identical either way, so shadow parity is unaffected; it is omitted entirely on a live
    turn so the body stays byte-equal to n8n's there.
    """
    parse_output = _parser_output(ctx)
    entities = parse_output.get("entities")
    if not isinstance(entities, list):
        # `_ents.map(...)` with no `?? []` - n8n throws here and the turn fails. Kept a
        # failure rather than softened to `[]`: a parser that emitted no entities array is
        # a broken understanding, and answering it unscoped is worse than saying so.
        raise TypeError(
            "resolve-entity: ctx.parse.output.entities is not an array, so the token map "
            "cannot be built (n8n throws on the same read)"
        )

    match_mode = parse_output.get("match_mode")
    match_mode = match_mode if jsc.truthy(match_mode) else "and"
    body: dict[str, Any] = {
        "query": _query_text(ctx),
        "match_mode": match_mode,
        "tokens": [_token_of(x) for x in entities],
        "allowed_entity_types": [jsc.get(x, "hint") for x in entities],
        "access_levels": parse_output.get("access_levels")
        if jsc.truthy(parse_output.get("access_levels"))
        else [],
        "domain": parse_output.get("domain_hint") if jsc.truthy(parse_output.get("domain_hint")) else "",
        "fallback_to_all_types": True,
        "limit": 15,
        "spec_fallback": True,
        "understand_phrase": True,
    }
    if dry_run:
        body["dry_run"] = True
    if jsc.js_string(match_mode).lower() != "and":
        pins: dict[str, Any] = {}
        for x in entities:
            if jsc.truthy(x) and jsc.truthy(jsc.get(x, "uuid")):
                token = _token_of(x)
                if jsc.truthy(token):
                    pins[token] = jsc.get(x, "uuid")
        if pins:
            body["entity_pins"] = pins
    return body


# --------------------------------------------------------------------------- #
# build-ctx-resolved
# --------------------------------------------------------------------------- #


def build_ctx_resolved(
    gate_item: dict[str, Any],
    *,
    ctx: dict[str, Any],
    resolved: dict[str, Any],
    aggregate: dict[str, Any] | None,
) -> dict[str, Any]:
    """`{...gate, ctx: {...ctx, resolved, entities, gate}}`.

    THE ITEM IS `{...gate, ctx}`, NOT `{ctx}`: `If3` forwards it and
    `not-found-error-message` uses it as the base of its own output, so replacing the
    gate's item with a bare `{ctx}` would rewrite that whole arm.

    `entities` is NULLABLE and that is a MEASUREMENT, not a default: `Aggregate` sits on
    the promotion lane only (55 of 542 captures reached the gate having run it), and every
    reader's `.isExecuted` guard is repointed to `!== null`.
    """
    return {
        **gate_item,
        "ctx": {**ctx, "resolved": resolved, "entities": aggregate, "gate": gate_item},
    }


# --------------------------------------------------------------------------- #
# The three Ifs
# --------------------------------------------------------------------------- #


def if3_miss(ctx_resolved_ctx: dict[str, Any], *, parser: dict[str, Any]) -> bool:
    """`If3` - the miss gate, three OR'd clauses, verbatim.

    Clause 3 is the "customer resolved to nothing" case the first two cannot see: the
    domain accepts a customer, the parser named one, and nothing customer-shaped survived
    the gate.
    """
    gate = jsc.get(ctx_resolved_ctx, "gate") or {}
    resolved = jsc.get(ctx_resolved_ctx, "resolved") or {}

    if jsc.get(gate, "gate_passed") is False:
        return True

    unresolved = jsc.get(resolved, "unresolved_tokens")
    unresolved = unresolved if jsc.truthy(unresolved) else []
    compatible = jsc.get(gate, "compatible_entities")
    compatible = compatible if jsc.truthy(compatible) else []
    if len(jsc.array(unresolved)) > 0 and len(jsc.array(compatible)) == 0:
        return True

    gate_debug = jsc.get(gate, "gate_debug")
    gate_debug = gate_debug if jsc.truthy(gate_debug) else {}
    allowed_lookup = jsc.get(gate_debug, "allowed_lookup")
    allowed_lookup = allowed_lookup if jsc.truthy(allowed_lookup) else []
    parser_entities = parser.get("entities")
    parser_entities = parser_entities if jsc.truthy(parser_entities) else []
    return (
        "customer" in jsc.array(allowed_lookup)
        and any(
            jsc.truthy(e) and jsc.lower_or_empty(jsc.get(e, "hint")) == "customer"
            for e in jsc.array(parser_entities)
        )
        and not any(
            jsc.truthy(c) and jsc.lower_or_empty(jsc.get(c, "entity_type")) == "customer"
            for c in jsc.array(compatible)
        )
    )


def if_incoming_picker(gate: dict[str, Any]) -> bool:
    """`If-incoming-picker` - `require_specific` true AND `gate_debug.domain` == 'incoming'.

    Strict type validation on both conditions, so a non-boolean `require_specific` or a
    non-string domain takes the FALSE leg rather than coercing.
    """
    gate_debug = jsc.get(gate, "gate_debug") or {}
    return jsc.get(gate, "require_specific") is True and jsc.get(gate_debug, "domain") == "incoming"


def if_customer_picker(gate: dict[str, Any]) -> bool:
    """`If-customer-picker` - `(gate.customer_probe_entities || []).length > 0`."""
    probe_entities = jsc.get(gate, "customer_probe_entities")
    probe_entities = probe_entities if jsc.truthy(probe_entities) else []
    return len(jsc.array(probe_entities)) > 0


# --------------------------------------------------------------------------- #
# The probes' inputs (the executeWorkflow parameter expressions)
# --------------------------------------------------------------------------- #


def _semantic_input(
    ctx: dict[str, Any],
    *,
    aggregate: dict[str, Any] | None,
    default_start: str | None,
    space_id: str | None,
) -> dict[str, Any]:
    """The probes' shared `semantic_input`, with the access-level intersection.

    `aggExecuted` is `ctx.entities !== null` on `build-ctx-resolved`'s ctx, which is why
    `Aggregate`'s three-state value had to survive as a key rather than as a guard.
    """
    parser = _parser_output(ctx)
    parser_levels = parser.get("access_levels") if jsc.truthy(parser.get("access_levels")) else []
    if aggregate is not None:
        names = sorted(jsc.array(jsc.get(aggregate, "name")), key=jsc.js_string)
        access_levels = [a for a in names if a in jsc.array(parser_levels)]
    else:
        access_levels = list(jsc.array(parser_levels))
    contact_id = jsc.get(jsc.get(ctx, "contact"), "id")
    start = parser.get("date_filter_start") if "date_filter_start" in parser else None
    end = parser.get("date_filter_end") if "date_filter_end" in parser else None
    return {
        "message_type": parser.get("message_type") if parser.get("message_type") is not None else None,
        "intent_hint": parser.get("intent_hint") if parser.get("intent_hint") is not None else None,
        "domain_hint": parser.get("domain_hint") if parser.get("domain_hint") is not None else None,
        "user_goal": parser.get("user_goal") if parser.get("user_goal") is not None else None,
        "access_levels": access_levels,
        "contact_id": jsc.js_string(contact_id) if contact_id is not None else None,
        "space_id": space_id,
        "date_mode": parser.get("date_mode") if parser.get("date_mode") is not None else None,
        "date_filter_start": (
            default_start if (start is None and end is None and default_start is not None) else start
        ),
        "date_filter_end": end,
        "is_active": parser.get("is_active") if parser.get("is_active") is not None else None,
        "order_status": parser.get("order_status") if parser.get("order_status") is not None else None,
        "requested_attributes": parser.get("requested_attributes")
        if parser.get("requested_attributes") is not None
        else [],
    }


def _user_prompt(
    ctx: dict[str, Any],
    *,
    entities: Any,
    access_levels: Any,
    date_start: Any,
    space_id: str | None,
) -> str:
    """The probes' `user_prompt` text block, field for field."""
    import json as _json

    parser = _parser_output(ctx)
    contact_id = jsc.get(jsc.get(ctx, "contact"), "id")
    return (
        f"message_type: {jsc.js_string(parser.get('message_type'))}  \n"
        f"intent_hint: {jsc.js_string(parser.get('intent_hint'))}  \n"
        f"domain_hint: {jsc.js_string(parser.get('domain_hint'))}  \n"
        f"user_goal: {jsc.js_string(parser.get('user_goal'))}  \n"
        # `ensure_ascii=False`: `JSON.stringify` emits the character, Python's default
        # emits a `\uXXXX` escape, and a customer name with an accent in it would reach the
        # probe's prompt as escaped gibberish where n8n sent the letter.
        f"entities: {_json.dumps(entities, separators=(',', ':'), ensure_ascii=False)} \n"
        f"access level: "
        f"{_json.dumps(access_levels, separators=(',', ':'), ensure_ascii=False)} \n"
        f"contact_id: {jsc.js_string(contact_id)} \n"
        f"space_id: {jsc.js_string(space_id)}\n"
        f"date_mode: {jsc.js_string(parser.get('date_mode'))} \n"
        f"date_filter_start: {jsc.js_string(date_start)}  \n"
        f"date_filter_end: {jsc.js_string(parser.get('date_filter_end'))}  \n"
        f"is_active: {jsc.js_string(parser.get('is_active'))}  \n"
        f"order_status: {jsc.js_string(parser.get('order_status'))}  "
    )


# --------------------------------------------------------------------------- #
# The four exits
# --------------------------------------------------------------------------- #


def exit_item(
    input_item: dict[str, Any],
    *,
    exit_kind: str,
    fields: dict[str, Any],
) -> dict[str, Any]:
    """`{ ...$input.first().json, ..._fields, _exit_kind }` - the spread order matters."""
    out = {**input_item}
    for name in EXIT_CONTRACT_FIELDS:
        out[name] = fields.get(name)
    out["_exit_kind"] = exit_kind
    return out


# --------------------------------------------------------------------------- #
# The walk
# --------------------------------------------------------------------------- #


def run(
    ctx: dict[str, Any],
    entry: Any,
    item: dict[str, Any],
    *,
    services: ResolveGateServices,
    space_id: str | None = None,
    probe_default_start: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """One pass through `sub-resolve-and-gate`. Returns the exit arm's item.

    `space_id` is the default respond workspace's (D5), and it reaches the probes' own
    `semantic_input` where n8n hard-codes `364817`. `probe_default_start` is the
    `$now.minus({days: 90})` the customer probe injects, passed in rather than computed so
    a replay is deterministic.
    """
    # The two carriers' contract throws, against the values this function was handed.
    # `build_ctx` / `carry_item` themselves take the TRIGGER and are what `run_from_trigger`
    # and the `build-ctx` / `item` node replays use.
    carrier = build_ctx({"ctx": {"ctx": ctx}})
    carried_item = carry_item({"item": item})
    ctx = jsc.get(carrier, "ctx")
    if not isinstance(ctx, dict):
        raise ResolveGateContractError(
            "sub-resolve-and-gate: `ctx` carried no inner ctx object - every reader in "
            "this sub indexes `$('build-ctx').first().json.ctx`"
        )
    parser = _parser_output(ctx)

    aggregate: dict[str, Any] | None = None
    tier_gate_out: dict[str, Any] | None = None

    # ── entry-gate: `entry === 'access_check'` (strict string equals) ────────
    if entry == "access_check":
        rows = services.access_types(
            contact_id=jsc.js_string(jsc.get(jsc.get(ctx, "contact"), "id")),
            space_id=space_id,
        )
        aggregate = aggregate_names(rows)
        tier_gate_out = run_tier_gate(
            _snapshot(aggregate), parser=parser, item=_snapshot(carried_item)
        )
        # ── If4: `$json.name.length > 0` on tier-gate's OUTPUT ───────────────
        if len(jsc.array(tier_gate_out.get("name"))) == 0:
            return exit_item(
                _snapshot(tier_gate_out),
                exit_kind="access_ask",
                fields={
                    "aggregate": _snapshot(aggregate),
                    "tier_gate": _snapshot(tier_gate_out),
                },
            )

    # ── resolve-entity ──────────────────────────────────────────────────────
    resolved = services.resolve_entity(resolve_entity_body(ctx, dry_run=dry_run))
    resolved_snapshot = _snapshot(resolved)

    # ── disallowed-entity-gate. Its input IS resolve-entity's item, and it MUTATES
    #    it - so the gate gets its own copy and `resolved` keeps the pre-gate snapshot,
    #    which is what `$('resolve-entity')` returns downstream.
    gate_input = _snapshot(resolved)
    gate_item = run_gate(
        gate_input,
        parser=parser,
        resolver=gate_input,
        session=jsc.get(ctx, "session"),
        tier_gate=tier_gate_out,
        aggregate=aggregate,
    )
    gate_snapshot = _snapshot(gate_item)

    ctx_resolved_item = build_ctx_resolved(
        gate_snapshot,
        ctx=ctx,
        resolved=resolved_snapshot,
        aggregate=_snapshot(aggregate),
    )
    ctx_resolved_snapshot = _snapshot(ctx_resolved_item)

    base_fields = {
        "resolved": resolved_snapshot,
        "gate": gate_snapshot,
        "ctx_resolved": ctx_resolved_snapshot,
        "aggregate": _snapshot(aggregate),
        "tier_gate": _snapshot(tier_gate_out),
    }

    # ── If3 ─────────────────────────────────────────────────────────────────
    if not if3_miss(ctx_resolved_snapshot["ctx"], parser=parser):
        return exit_item(_snapshot(ctx_resolved_item), exit_kind="continue", fields=base_fields)

    picker_gate = jsc.get(ctx_resolved_snapshot["ctx"], "gate") or {}

    # ── If-incoming-picker ──────────────────────────────────────────────────
    if if_incoming_picker(picker_gate):
        entities = jsc.get(picker_gate, "compatible_entities")
        probe = _run_probe(
            services,
            ctx=ctx,
            tool=INCOMING_PROBE_TOOL,
            entities=entities,
            aggregate=aggregate,
            default_start=None,
            space_id=space_id,
        )
        annotated = pickers.annotate_incoming(_snapshot(picker_gate), probe=probe)
        return exit_item(
            _snapshot(annotated),
            exit_kind="offer",
            fields={**base_fields, "annotate_incoming": _snapshot(annotated)},
        )

    # ── If-customer-picker ──────────────────────────────────────────────────
    if if_customer_picker(picker_gate):
        entities = jsc.get(picker_gate, "customer_probe_entities")
        probe = _run_probe(
            services,
            ctx=ctx,
            tool=CUSTOMER_PROBE_TOOL,
            entities=entities,
            aggregate=aggregate,
            default_start=probe_default_start,
            space_id=space_id,
        )
        annotated = pickers.annotate_customer(
            _snapshot(picker_gate), probe=probe, parser=parser
        )
        # `annotate_incoming` stays NULL on this arm: the customer annotator is not the
        # incoming one, and `sub-main-processing`'s `annotate-incoming-gate` reads exactly
        # that key to decide whether its stand-in executes.
        return exit_item(_snapshot(annotated), exit_kind="offer", fields=base_fields)

    return exit_item(_snapshot(ctx_resolved_item), exit_kind="not_found", fields=base_fields)


def _run_probe(
    services: ResolveGateServices,
    *,
    ctx: dict[str, Any],
    tool: str,
    entities: Any,
    aggregate: dict[str, Any] | None,
    default_start: str | None,
    space_id: str | None,
) -> Any:
    """One picker probe. A failure returns None, which is the annotators' UNPROBED arm.

    `probe-customer-orders` carries `onError: continueRegularOutput` for exactly this
    reason: a transient MCP failure must arrive as "we did not measure", never as an empty
    answer set, or every line renders a confident miss on evidence nobody gathered.
    `probe-incoming` has no such setting and its failure ends the turn in n8n - the port
    logs and returns None instead, which the incoming annotator renders as today's
    "None of these have incoming stock right now."
    """
    semantic_input = _semantic_input(
        ctx, aggregate=aggregate, default_start=default_start, space_id=space_id
    )
    user_prompt = _user_prompt(
        ctx,
        entities=entities,
        access_levels=semantic_input["access_levels"],
        date_start=semantic_input["date_filter_start"],
        space_id=space_id,
    )
    try:
        return services.probe(
            tool=tool,
            contact_id=jsc.get(jsc.get(ctx, "contact"), "id"),
            entities=entities,
            semantic_input=semantic_input,
            user_prompt=user_prompt,
        )
    except Exception:  # noqa: BLE001 - an unprobed picker is a documented arm, not a failure
        logger.warning("chatbot: picker probe %s did not run", tool, exc_info=True)
        return None


def run_from_trigger(
    trigger: dict[str, Any],
    *,
    services: ResolveGateServices,
    space_id: str | None = None,
    probe_default_start: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """`run()` from the sub's own `{ctx, entry, item, is_test}` trigger payload.

    The trigger's `ctx` is the CARRIER (`{ctx: ...}`) - see `build_ctx`. This unwraps it
    exactly as every node in the sub does, so a captured execution can be replayed whole.
    """
    carrier = build_ctx(trigger)
    item = carry_item(trigger)
    inner = jsc.get(carrier, "ctx")
    if not isinstance(inner, dict):
        raise ResolveGateContractError(
            "sub-resolve-and-gate: `ctx` carried no inner ctx object - every reader in "
            "this sub indexes `$('build-ctx').first().json.ctx`"
        )
    return run(
        inner,
        trigger.get("entry"),
        item,
        services=services,
        space_id=space_id,
        probe_default_start=probe_default_start,
        dry_run=dry_run,
    )
