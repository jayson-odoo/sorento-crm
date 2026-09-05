"""The business lane. S6a owns resolve + gate; fetch (S6b) and answer (S6c) follow.

`run_until_exit` is the ONE call site the engine makes into this package. It exists so
S6a can ship without restructuring `engine.py`: the head still routes, and three of its
arms now come here first and hand n8n a resolve+gate result instead of nothing.

**Which arms, and why those three.** `sorento-consume-main`'s `route` Switch wires
`check_promotion` (arm 8) to `tag-entry-access-check` and both `stock_denied` (arm 11, via
`Edit Fields2`) and `business_query` (the fallback) to `tag-entry-resolve`; both tags then
call `sub-main-processing`, which calls `sub-resolve-and-gate`. So the three arms are the
sub's three real call sites, `entry` is the tag they carried, and `not_allowed_check_stock`
is `Edit Fields2`' one field.

After S6a the CRM returns `delegate = "business_query"` with `delegate_payload` = the
sub's own output item. n8n's `sub-main-processing` enters at `resolve-arm`; its stand-in
chain (`resolve-gate` / `aggregate-gate` / `annotate-incoming-gate` plus the five
name-preserving Code nodes) re-emits the six contract fields, so every by-name reader
downstream is unchanged and the old wiring is one edge away from being restored.
"""
from __future__ import annotations

from typing import Any

import logging

from app.services.chatbot import jsc
from app.services.chatbot.lanes.business import fetch as fetch_mod
from app.services.chatbot.lanes.business import resolve_gate
from app.services.chatbot.lanes.business.services import FetchServices, ResolveGateServices

logger = logging.getLogger(__name__)

# `branch_kind` -> the `entry` its `tag-entry-*` node stamps. The three arms that reach
# `sub-resolve-and-gate`, and nothing else: an arm absent from this map never enters the
# lane, which is what keeps `run_until_exit` a no-op for the other ten.
ENTRY_BY_BRANCH_KIND: dict[str, str] = {
    "check_promotion": "access_check",
    "stock_denied": "resolve",
    "business_query": "resolve",
}

# The n8n lane the caller must still run after S6a. One name for all three arms because
# they converge on ONE node (`resolve-arm`), and the arm they take there is `_exit_kind`.
DELEGATE = "business_query"


def handles(branch_kind: str | None) -> bool:
    """Does the business lane own this arm?"""
    return branch_kind in ENTRY_BY_BRANCH_KIND


def run_until_exit(
    ctx: dict[str, Any],
    item: dict[str, Any],
    *,
    branch_kind: str,
    services: ResolveGateServices,
    space_id: str | None = None,
    probe_default_start: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run resolve + gate for one turn and return the `{delegate, payload}` fragment.

    `item` is the router's own item, forwarded UNCHANGED.

    `not_allowed_check_stock` is the spine's `Edit Fields2`, which sits on the ONE edge
    `If7`'s TRUE output takes (`If7 -> Edit Fields2 -> If8`) and sets the single boolean
    `validator` reads. S6a left it unstamped because the reader then was n8n's own
    `validator`, which reads `$('Edit Fields2')` by name; at S6c the CRM IS the validator
    and reads the flag off this payload, so the arm that carries it has to carry it here.
    The route already gates the arm: `stock_denied` can only be decided when
    `system_settings.chatbot_stock_denial_enabled` is on (R1), so no second flag read is
    needed - with the switch off no turn reaches this branch at all.
    """
    entry = ENTRY_BY_BRANCH_KIND[branch_kind]
    payload = resolve_gate.run(
        ctx,
        entry,
        item,
        services=services,
        space_id=space_id,
        probe_default_start=probe_default_start,
        dry_run=dry_run,
    )
    if branch_kind == "stock_denied":
        payload["not_allowed_check_stock"] = True
    return {"delegate": DELEGATE, "payload": payload}


def _rag_message(parse_output: dict[str, Any]) -> str:
    """The three-line prompt `Execute 'sub-get-rag'` sends, then the newline strip.

    `sub-get-rag`'s own first step is `$json.message.replace(/\r?\n/g, ' ')` before the
    text is embedded, so the vector is built from a SINGLE line. Embedding the newlines
    instead changes the vector on every turn - 38 of 38 captures carry the stripped form -
    and therefore changes which tool is picked. The strip belongs here, at the seam that
    builds the text, not inside the embedding provider.
    """
    message = (
        f"intent_hint: {jsc.js_string(parse_output.get('intent_hint'))}\n"
        f"domain_hint: {jsc.js_string(parse_output.get('domain_hint'))}\n"
        f"user_goal: {jsc.js_string(parse_output.get('user_goal'))}"
    )
    return message.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def _fetch_semantic_input(
    parse_output: dict[str, Any],
    *,
    tier_gate: dict[str, Any] | None,
    contact_id: Any,
    space_id: str | None,
) -> dict[str, Any]:
    """`Call 'sub-get-results'`'s `semantic_input`, all thirteen fields.

    It was `{}`, and that was not a small omission: `access_levels`, `is_active`,
    `date_mode`, `order_status`, `requested_attributes` and both date filters all reach the
    MCP tool through this object, so an empty one silently widened every read and left the
    timeline and per-field denial paths dead.

    `access_levels` comes from `tier-gate.access_levels_recomposed` when the tier gate ran
    - the tier x brand recomposition is computed ONCE, there - and from the parser's own
    list otherwise, which is the legacy behaviour off the promotion lane.
    """
    tg = tier_gate if isinstance(tier_gate, dict) else None
    if tg is not None:
        access_levels = tg.get("access_levels_recomposed")
    else:
        access_levels = (
            parse_output.get("access_levels")
            if isinstance(parse_output.get("access_levels"), list)
            else []
        )
    return {
        "message_type": parse_output.get("message_type"),
        "intent_hint": parse_output.get("intent_hint"),
        "domain_hint": parse_output.get("domain_hint"),
        "user_goal": parse_output.get("user_goal"),
        "access_levels": access_levels,
        "contact_id": jsc.js_string(contact_id) if contact_id is not None else None,
        "space_id": space_id or fetch_mod.SPACE_ID,
        "date_mode": parse_output.get("date_mode"),
        "date_filter_start": parse_output.get("date_filter_start"),
        "date_filter_end": parse_output.get("date_filter_end"),
        "is_active": parse_output.get("is_active"),
        "order_status": parse_output.get("order_status"),
        "requested_attributes": (
            parse_output.get("requested_attributes")
            if parse_output.get("requested_attributes") is not None
            else []
        ),
    }


def _error_fragment(reason: str, *, outcome: str | None = None) -> dict[str, Any]:
    """`fetch-result`'s `error` arm, as the fragment the engine records a failure from."""
    item = fetch_mod.fetch_result({"error": reason})
    fragment: dict[str, Any] = {
        "kind": "error",
        "_fetch_arm": item["_fetch_arm"],
        "error": reason,
        "fetch": item,
    }
    if outcome is not None:
        fragment["outcome"] = outcome
    return fragment


def run_fetch(
    payload: dict[str, Any],
    *,
    services: FetchServices,
    dry_run: bool = False,
    space_id: str | None = None,
) -> dict[str, Any]:
    """S6b: the fetch step, the next call site after `run_until_exit`'s `continue` exit.

    `payload` is the resolve+gate output item - what `sub-fetch-results` receives as
    `ctx_resolved` + `tier_gate` today. The return is a FRAGMENT in the same shape
    `run_until_exit` produces, so the engine keeps one call per lane stage.

    Three arms, from `fetch-result`'s own three:

    * `tier_ask` - the customer must pick an access tier before anything is fetched, so
      the per-tier probe plan runs and its answers are folded back in. It must NOT fall
      through to an ordinary result delegate while a tier is unresolved; S6c renders the
      copy from `tier_probe`.
    * `error` - the tool returned an error item, or the call itself failed. n8n carries
      `onError: continueErrorOutput` on that node for exactly this reason: a transient MCP
      failure is an ANSWERABLE outcome, not a dead turn.
    * `result` - S6c is not built, so the turn still delegates to n8n's business lane, and
      the fetch's own output rides on `delegate_payload` so the next slice has something to
      answer from without re-fetching.

    D14: `dry_run` performs the SAME reads. A test turn that skipped the fetch would prove
    nothing about production, and this lane writes nothing either way - the only write on
    the whole turn is `chatbot.turns`, which the engine owns. The parameter is taken (and
    unused) so the engine's call site reads the same as every other lane's.
    """
    _ = dry_run
    raw_gate = payload.get("gate")
    gate: dict[str, Any] = raw_gate if isinstance(raw_gate, dict) else {}
    raw_tier_gate = payload.get("tier_gate")
    tier_gate: dict[str, Any] | None = raw_tier_gate if isinstance(raw_tier_gate, dict) else None

    ctx = payload.get("ctx") if isinstance(payload.get("ctx"), dict) else {}
    parse_output = ((ctx.get("parse") or {}).get("output")) or {}
    contact_id = (ctx.get("contact") or {}).get("id")
    entities = gate.get("compatible_entities") or []
    semantic_input = _fetch_semantic_input(
        parse_output, tier_gate=tier_gate, contact_id=contact_id, space_id=space_id
    )

    def probe(tool: str, probe_entities: Any, probe_levels: Any) -> Any:
        """One `sub-get-results` call: build the args the same way, then the same seam."""
        trigger = {
            "tool": tool,
            "entities": probe_entities,
            "semantic_input": {**semantic_input, "access_levels": probe_levels},
            "contact_id": contact_id,
        }
        args = fetch_mod.entity_ids_transformer(trigger, space_id=space_id)
        return fetch_mod.parse_mcp_content(
            fetch_mod.call_tool(tool, args, mcp=_McpSeam(services.mcp_call))
        )

    # ── the tier ask, with its per-tier probe ────────────────────────────────
    # `if-tier-ask` sits UPSTREAM of the rag call in n8n: there is nothing to fetch until
    # the customer has said which tier they mean. The probe plan is what makes the ask
    # honest ("Dealer - has promotion"), so it runs here rather than being skipped.
    if payload.get("tier_ask") is True or (tier_gate or {}).get("tier_ask") is True:
        plan_items = [i["json"] for i in fetch_mod.tier_probe_plan(tier_gate or payload)]
        probe_results: list[Any] = []
        for plan_item in plan_items:
            if plan_item.get("probe_skipped") is True:
                probe_results.append({})
                continue
            try:
                probe_results.append(
                    probe(
                        fetch_mod.TIER_PROBE_TOOL,
                        entities,
                        plan_item.get("probe_access_levels") or [],
                    )
                )
            except Exception:  # noqa: BLE001 - an unprobed tier is "unknown", never "none"
                logger.warning("chatbot: tier probe did not run", exc_info=True)
                probe_results.append(None)
        collected = fetch_mod.tier_probe_collect(
            tier_gate or payload, plan_items=plan_items, probe_results=probe_results
        )
        item = fetch_mod.fetch_result({**payload, **collected})
        return {
            "kind": "tier_ask",
            "_fetch_arm": item["_fetch_arm"],
            "tier_probe": collected,
            "fetch": item,
        }

    # ── tool selection ───────────────────────────────────────────────────────
    domain = parse_output.get("domain_hint") or (tier_gate or {}).get("tier_pick_domain")
    try:
        candidates = fetch_mod.select_tool(
            None, query=_rag_message(parse_output), domain=domain, services=services
        )
    except Exception as exc:  # noqa: BLE001 - no vector, no tool: an answerable outcome
        logger.warning("chatbot: tool search did not run", exc_info=True)
        return _error_fragment(f"tool search failed: {exc}")

    pick = fetch_mod.tool_filter(
        candidates,
        has_product=(
            any(isinstance(e, dict) and e.get("entity_type") == "product" for e in entities)
            if isinstance(entities, list)
            else None
        ),
    )
    if pick.outcome == "not_found":
        # H11: zero tools is an OUTCOME, not an empty turn. The engine gets something to
        # say rather than a fragment that looks like a lane which never ran.
        return _error_fragment("no MCP tool matched this question", outcome="not_found")

    # ── the read ─────────────────────────────────────────────────────────────
    tool_item = pick.items[0]["json"]
    tool_name = jsc.js_string(tool_item.get("name") or "")
    trigger = {
        "tool": tool_name,
        "entities": entities,
        "semantic_input": semantic_input,
        "contact_id": contact_id,
    }
    args = fetch_mod.entity_ids_transformer(trigger, space_id=space_id)
    try:
        raw = fetch_mod.call_tool(tool_name, args, mcp=_McpSeam(services.mcp_call))
    except Exception as exc:  # noqa: BLE001 - `onError: continueErrorOutput`, verbatim
        logger.warning("chatbot: MCP tool %s failed", tool_name, exc_info=True)
        return _error_fragment(f"MCP tool {tool_name} failed: {exc}")

    envelope = fetch_mod.parse_mcp_content(raw)
    # The ERROR check comes BEFORE the render: an error envelope has no rows, and rendering
    # it first would build a "No matching results found." message for a turn that failed.
    if isinstance(envelope, dict) and isinstance(envelope.get("error"), str):
        return _error_fragment(envelope["error"])

    structured = fetch_mod.output_structurer(envelope, trigger)
    item = fetch_mod.fetch_result(structured, tool=tool_item, tier_probe=None)
    return {
        "kind": "result",
        "_fetch_arm": item["_fetch_arm"],
        "delegate": DELEGATE,
        "delegate_payload": {**payload, "fetch": item},
        "fetch": item,
    }


class _McpSeam:
    """Adapts the `mcp_call(name, args)` seam to `call_tool`'s client-shaped parameter.

    `call_tool` is the ported node and takes something with `.call_tool(name, args)`; the
    bundle is a plain callable so a test can stub it in one line. This is the two-line
    adapter that lets the production path go through the ported function rather than
    around it.
    """

    __slots__ = ("_call",)

    def __init__(self, call: Any) -> None:
        self._call = call

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        return self._call(name, arguments)


__all__ = [
    "DELEGATE",
    "ENTRY_BY_BRANCH_KIND",
    "handles",
    "run_fetch",
    "run_until_exit",
]


def complete_answer(
    payload: dict[str, Any],
    *,
    turn_id: str,
    ctx: dict[str, Any],
    item: dict[str, Any],
    branch_kind: str,
    services: Any,
    session_factory: Any,
    space_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """S6c: finish the business turn in process, and return `{reply, actions, ...}`.

    The third and last call site into this package, after `run_until_exit` and `run_fetch`.
    It runs the ANSWER half - `validator`, `promo-picker`, the three cross-domain nodes and
    `build-result` - then `If6` dispatches into `sub-answer` or the miss lane, and the
    `sub-output` fragments go to the S2 tail (`engine.complete_turn`), which composes the
    reply and writes the session exactly as it does for every other completed lane.

    `payload` is `run_until_exit`'s output with `run_fetch`'s `fetch` folded in, i.e. the
    same object `delegate_payload` carries today.

    **The ITEM handed to the tail is the LANE's own output, never `route-turn`'s** - the
    same rule S4 learned the hard way. `complete_turn`'s entry gate runs `escalate-catalog`
    only when the item carries a `branch_kind`, and these lane outputs carry none, so the
    catalog is skipped and the compile-state ladder falls through to the lane's own
    response. Hand it the router's item instead and the catalog wins the ladder with an
    empty `response`, and the reply comes out blank.

    **No database session is held across the probes.** Everything this function reads from
    the database was read before it was called; `services` is the injected seam pair, and
    the only session opened here is the tail's own, after every probe has answered.
    """
    from app.services.chatbot import engine as engine_mod
    from app.services.chatbot.lanes.business import answer as answer_mod
    from app.services.chatbot.lanes.business import miss_suggest as miss_mod
    from app.services.chatbot.lanes.business import sub_answer as sub_answer_mod

    parser = ((ctx.get("parse") or {}).get("output")) or {}
    session_block = ctx.get("session") or {}
    contact = ctx.get("contact") or {}
    contact_id = contact.get("id")
    resolved = payload.get("resolved") if isinstance(payload.get("resolved"), dict) else {}
    gate = payload.get("gate") if isinstance(payload.get("gate"), dict) else {}
    fetch = payload.get("fetch") if isinstance(payload.get("fetch"), dict) else {}
    exit_kind = payload.get("_exit_kind")
    # The entitlement union the resolver's aggregate returned, when it ran. Two readers:
    # `crossdomain-probe`'s access-level intersection and the promotion entitlement-miss
    # sentence. `None` is "the aggregate did not run", which both arms handle.
    aggregate = payload.get("aggregate") if isinstance(payload.get("aggregate"), dict) else None
    entities_names = aggregate.get("name") if aggregate is not None else None

    fragments: dict[str, Any] = {"ctx": ctx, "resolved": resolved, "gate": gate}
    lane_item: dict[str, Any]

    if exit_kind == "access_ask" or fetch.get("_fetch_arm") == "tier_ask":
        # The customer has to name an access tier before anything can be read.
        # `access-level-choice-message` renders the ask, and S6b's per-tier probe is what
        # makes it honest ("Dealer - has promotion").
        tier_source = fetch if fetch.get("_fetch_arm") == "tier_ask" else payload
        lane_item = answer_mod.access_level_choice_message(tier_source, parser=parser)
        fragments["access_choice"] = lane_item

    elif exit_kind == "offer":
        # The gate rendered its own picker (incoming / customer). It is already the answer.
        lane_item = dict(payload)
        fragments["incoming_picker"] = lane_item

    elif exit_kind == "not_found" or fetch.get("_fetch_arm") == "error":
        lane_item = _run_miss_half(
            payload,
            parser=parser,
            resolved=resolved,
            gate=gate,
            services=services,
            contact_id=contact_id,
            space_id=space_id,
            execution_id=turn_id,
            fragments=fragments,
            miss_mod=miss_mod,
            answer_mod=answer_mod,
            dry_run=dry_run,
        )

    else:
        # The ANSWER half proper. `validator` stamps `is_valid` (and rewrites the response
        # on the demand-quantity arm), `promo-picker` owns the promotion ordering / pick /
        # roster, the cross-domain trio asks the OTHER domain about a code that came back
        # empty, and `build-result` is the `result` contract every later reader keys on.
        structured = fetch.get("result") if isinstance(fetch.get("result"), dict) else fetch
        validated = answer_mod.validator(
            dict(structured),
            semantic_parser=(ctx.get("parse") or {}),
            not_allowed_check_stock=bool(payload.get("not_allowed_check_stock")),
        )
        promo = answer_mod.promo_picker(
            validated, parser=parser, resolved=resolved, gate=gate
        )
        crossdomain = answer_mod.run_crossdomain(
            validated,
            parser=parser,
            resolved=resolved,
            session_block=session_block,
            entities_names=entities_names,
            services=services,
            contact_id=contact_id,
            space_id=space_id,
            dry_run=dry_run,
        )
        result_item = answer_mod.build_result(
            promo,
            validator=validated,
            promo=promo,
            zeroset=crossdomain.get("zeroset"),
            tool=(fetch.get("tool") if isinstance(fetch.get("tool"), dict) else None),
            tier_probe=fetch.get("tier_probe"),
            crossdomain_render=crossdomain.get("render"),
        )
        fragments["result"] = result_item.get("result")
        fragments["crossdomain_render"] = crossdomain.get("render")

        if answer_mod.dispatch(result_item.get("result")) == "sub_answer":
            lane_item = _run_answer_half(
                result_item,
                parser=parser,
                resolved=resolved,
                gate=gate,
                services=services,
                contact_id=contact_id,
                space_id=space_id,
                fragments=fragments,
                sub_answer_mod=sub_answer_mod,
                miss_mod=miss_mod,
            )
        else:
            # `Aggregate1` collects `response_intro` off the item before the miss lane
            # runs, and the miss renderer's payload is what carries it forward.
            miss_payload = {
                **result_item,
                "response_intro": answer_mod.aggregate_response_intro(
                    result_item.get("result")
                ),
            }
            lane_item = _run_miss_half(
                miss_payload,
                parser=parser,
                resolved=resolved,
                gate=gate,
                services=services,
                contact_id=contact_id,
                space_id=space_id,
                execution_id=turn_id,
                fragments=fragments,
                miss_mod=miss_mod,
                answer_mod=answer_mod,
                dry_run=dry_run,
                build_result=result_item.get("result"),
            )

    # The row was closed `delegated` at `routed` by the caller before this function ran
    # (`engine.close_turn_for_tail`), which is the state `complete_turn` refuses to run
    # without and the state the turn is genuinely in while the tail has not folded the
    # lane's result in yet.
    completed = engine_mod.complete_turn(
        turn_id,
        {**fragments, "item": lane_item},
        session_factory=session_factory,
    )
    return {
        "reply": completed.reply,
        "actions": completed.actions,
        "session_patch": completed.session_patch,
        "status": completed.status,
        "stage": completed.stage,
    }


def _run_answer_half(
    result_item: dict[str, Any],
    *,
    parser: dict[str, Any],
    resolved: dict[str, Any],
    gate: dict[str, Any],
    services: Any,
    contact_id: Any,
    space_id: str | None,
    fragments: dict[str, Any],
    sub_answer_mod: Any,
    miss_mod: Any,
) -> dict[str, Any]:
    """`sub-answer`, in process: central-exchange, the miss roster, the partial did-you-mean."""
    trigger = {"item": result_item}
    entered = sub_answer_mod.answer_input(trigger)
    central = sub_answer_mod.central_exchange(entered)
    build_result_block = result_item.get("result") or {}

    checked = sub_answer_mod.miss_roster_check(
        central, build_result=build_result_block, parser=parser
    )
    member_offer = None
    roster_plan = None
    if checked.get("_offer") is True:
        roster_plan = sub_answer_mod.miss_roster_plan(
            checked,
            build_result=build_result_block,
            parser=parser,
            gate=gate,
            central_exchange=central,
        )
        member_offer = sub_answer_mod.build_miss_member_offer(
            checked, central_exchange=central, roster_plan=roster_plan
        )

    # The PARTIAL did-you-mean: the answer came back, but some of the tokens the customer
    # named resolved to nothing. Same planner as the miss lane's, deployed on this arm.
    plan = sub_answer_mod.dym_transform_partial(
        member_offer if member_offer is not None else central,
        parser=parser,
        gate=gate,
        resolved=resolved,
        central_exchange=central,
    )
    annotated = None
    if plan.get("probe_needed") is True:
        try:
            probe = services.mcp_probe(
                plan.get("probe_tool"),
                miss_mod._probe_args(
                    plan.get("dym_probe_entities") or [],
                    parser=parser,
                    contact_id=contact_id,
                    space_id=space_id,
                ),
            )
        except Exception:  # noqa: BLE001 - fail OPEN: no annotation, today's bare offer
            logger.warning("chatbot: partial did-you-mean probe did not run", exc_info=True)
            probe = {"error": "probe failed"}
        annotated = sub_answer_mod.dym_annotate_partial(
            probe,
            payload=member_offer if member_offer is not None else central,
            transform=plan,
        )

    answer = sub_answer_mod.answer_result(
        annotated if annotated is not None else (member_offer or central),
        central_exchange=central,
        member_offer=member_offer,
        dym_annotate_partial=annotated,
    )
    fragments["answer"] = answer
    return answer


def _run_miss_half(
    payload: dict[str, Any],
    *,
    parser: dict[str, Any],
    resolved: dict[str, Any],
    gate: dict[str, Any],
    services: Any,
    contact_id: Any,
    space_id: str | None,
    execution_id: str,
    fragments: dict[str, Any],
    miss_mod: Any,
    answer_mod: Any,
    dry_run: bool,
    build_result: Any = None,
) -> dict[str, Any]:
    """`not-found-error-message` -> `sub-miss-suggest` -> `build-suggest-offer`."""
    not_found = answer_mod.not_found_error_message(
        payload, parser=parser, resolved=resolved, gate=gate
    )
    fragments["not_found"] = not_found

    offer = miss_mod.run_miss_lane(
        not_found,
        parser=parser,
        resolved=resolved,
        gate=gate,
        services=services,
        build_result=build_result,
        contact_id=contact_id,
        space_id=space_id,
        execution_id=execution_id,
        dry_run=dry_run,
    )
    fragments["suggest_offer"] = offer
    return offer
