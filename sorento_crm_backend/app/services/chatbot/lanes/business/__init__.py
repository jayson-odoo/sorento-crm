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

from app.services.chatbot.lanes.business import fetch as fetch_mod
from app.services.chatbot.lanes.business import resolve_gate
from app.services.chatbot.lanes.business.services import FetchServices, ResolveGateServices

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

    An earlier version stamped `not_allowed_check_stock: true` here for the `stock_denied`
    arm, mirroring the spine's `Edit Fields2`. It was dead and is gone: inside the sub the
    item reaches only `tier-gate`'s `$('item')` read, which is on the `access_check` path
    that `stock_denied` never takes, and the node that actually consumes the field -
    `sub-main-processing`'s `validator` - reads it off `$('Edit Fields2')` BY NAME, not off
    the flowing item. That Set node stays in n8n and keeps owning the value; a CRM copy
    would have been a second writer of something it cannot be read from.
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
    return {"delegate": DELEGATE, "payload": payload}


def run_fetch(
    payload: dict[str, Any],
    *,
    services: FetchServices,
    dry_run: bool = False,
) -> dict[str, Any]:
    """S6b: the fetch step, the next call site after `run_until_exit`'s `continue` exit.

    `payload` is the resolve+gate output item - what `sub-fetch-results` receives as
    `ctx_resolved` + `tier_gate` today. The return is a FRAGMENT in the same shape
    `run_until_exit` produces, so the engine keeps one call per lane stage.

    Three arms, from `fetch-result`'s own three:

    * `tier_ask` - the customer must pick an access tier before anything is fetched. It
      must NOT fall through to an ordinary result delegate while a tier is unresolved;
      S6c renders the copy.
    * `error` - the tool returned an error item. The fragment carries the reason so the
      engine can record a failed turn at `looked_up`, the shape every other lane's failure
      already has.
    * `result` - S6c is not built, so the turn still delegates to n8n's business lane, and
      the fetch's own output rides on `delegate_payload` so the next slice has something to
      answer from without re-fetching.

    D14: a dry run performs the SAME reads. A test turn that skipped the fetch would prove
    nothing about production, and this lane writes nothing either way - the only write on
    the whole turn is `chatbot.turns`, which the engine owns.
    """
    gate = payload.get("gate") if isinstance(payload.get("gate"), dict) else {}
    tier_gate = payload.get("tier_gate") if isinstance(payload.get("tier_gate"), dict) else None

    # The tier ask short-circuits BEFORE any tool is chosen: `if-tier-ask` sits upstream of
    # the rag call in n8n for the same reason - there is nothing to fetch until the customer
    # has said which tier they mean.
    if payload.get("tier_ask") is True or (tier_gate or {}).get("tier_ask") is True:
        item = fetch_mod.fetch_result(
            {**payload, "tier_any_available": bool(payload.get("tier_any_available", True))}
        )
        return {"kind": "tier_ask", "_fetch_arm": item["_fetch_arm"], "fetch": item}

    parse_output = ((payload.get("ctx") or {}).get("parse") or {}).get("output") or {}
    query = (
        f"intent_hint: {parse_output.get('intent_hint')}\n"
        f"domain_hint: {parse_output.get('domain_hint')}\n"
        f"user_goal: {parse_output.get('user_goal')}"
    )
    domain = parse_output.get("domain_hint") or (tier_gate or {}).get("tier_pick_domain")

    candidates = fetch_mod.select_tool(None, query=query, domain=domain, services=services)
    entities = gate.get("compatible_entities") or []
    pick = fetch_mod.tool_filter(
        candidates,
        has_product=any(
            isinstance(e, dict) and e.get("entity_type") == "product" for e in entities
        )
        if isinstance(entities, list)
        else None,
    )
    if pick.outcome == "not_found":
        # H11: zero tools is an OUTCOME, not an empty turn. The engine gets something to
        # say rather than a fragment that looks like a lane which never ran.
        item = fetch_mod.fetch_result({"error": "no MCP tool matched this question"})
        return {
            "kind": "error",
            "_fetch_arm": item["_fetch_arm"],
            "error": "no MCP tool matched this question",
            "outcome": "not_found",
            "fetch": item,
        }

    tool_item = pick.items[0]["json"]
    tool_name = str(tool_item.get("name") or "")
    trigger = {
        "tool": tool_name,
        "entities": entities,
        "semantic_input": payload.get("semantic_input") or {},
        "contact_id": ((payload.get("ctx") or {}).get("contact") or {}).get("id"),
    }
    args = fetch_mod.entity_ids_transformer(trigger)
    raw = services.mcp_call(tool_name, args)
    structured = fetch_mod.output_structurer(
        raw if isinstance(raw, dict) else fetch_mod._safe_json(raw), trigger
    )
    if isinstance(raw, str):
        parsed = fetch_mod._safe_json(raw)
        if isinstance(parsed, dict) and isinstance(parsed.get("error"), str):
            item = fetch_mod.fetch_result({"error": parsed["error"]})
            return {
                "kind": "error",
                "_fetch_arm": item["_fetch_arm"],
                "error": parsed["error"],
                "fetch": item,
            }

    item = fetch_mod.fetch_result(structured, tool=tool_item, tier_probe=None)
    return {
        "kind": "result",
        "_fetch_arm": item["_fetch_arm"],
        "delegate": DELEGATE,
        "delegate_payload": {**payload, "fetch": item},
        "fetch": item,
    }


__all__ = [
    "DELEGATE",
    "ENTRY_BY_BRANCH_KIND",
    "handles",
    "run_fetch",
    "run_until_exit",
]
