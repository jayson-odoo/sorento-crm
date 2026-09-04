"""Port of the business lane's ANSWER half (S6c, AC-607 to AC-609).

The spine's own nodes between the fetch and the tail: `validator`, `promo-picker`, the
three cross-domain nodes, `build-result`, `If6`/`Aggregate1`, and the two miss-lane
renderers (`not-found-error-message`, `access-level-choice-message`) plus the composer
`build-suggest-offer`. `sub_answer.py` and `miss_suggest.py` hold the two sub-workflows
this file dispatches into.

**Source of truth is the LIVE SPINE's copy of each body**, not the clone's and not
`sub-main-processing`'s: every capture the corpus grades these against came from
`live-spine-sorento-consume-main`, and the three copies genuinely differ (measured:
`build-suggest-offer` is 710 / 729 / 944 lines across them). `build-result` is the one
exception - it lives only in `sub-main-processing-live` and `sub-answer`, and the tester's
runner passes the sub's five producers, so the 88-line version is the one ported.

**Nothing here holds a database session.** The two seams that do I/O
(`AnswerServices.mcp_probe`, `.family_fetch`) are injected, and the only function that
reads the database at all is `completed_lanes`, which is a turn-time flag read the engine
makes before this lane runs.

**D11.** Everything after the parser works on structured state. Where a ported body
sniffs raw text - and a few do - the line carries `# D11-reproduced` naming the n8n site,
so a new fuzzy match cannot slip in beside a parity one.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Literal

from app.services.chatbot import jsc

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# `If6` and `Aggregate1` - the dispatch between the answer and the miss lane.
# --------------------------------------------------------------------------- #

Lane = Literal["sub_answer", "miss_suggest"]


def dispatch(result: dict[str, Any] | None) -> Lane:
    """`If6`: `validator.has_result` AND `validator.is_valid`, both STRICT booleans.

    Strict type validation on both conditions, so anything that is not literally `True`
    takes the FALSE leg into the miss lane. That is the safe direction: a turn that cannot
    prove it has an answer goes to the lane that says so.
    """
    body = result if isinstance(result, dict) else {}
    return (
        "sub_answer"
        if body.get("has_result") is True and body.get("is_valid") is True
        else "miss_suggest"
    )


def aggregate_response_intro(result: dict[str, Any] | None) -> list[Any]:
    """`Aggregate1` (`fieldsToAggregate: [response_intro]`) on the miss branch.

    n8n's Aggregate SKIPS an item that does not carry the field, which is why a null
    `response_intro` collects to `[]` rather than `[None]` - and why the miss lane must be
    handed the list, not the raw value.
    """
    body = result if isinstance(result, dict) else {}
    value = body.get("response_intro")
    return [] if value is None else [value]


# --------------------------------------------------------------------------- #
# H45 - a row already in the answer is never offered again.
# --------------------------------------------------------------------------- #


def _code_key(value: Any) -> str:
    """The one code comparison this lane uses: trimmed, upper, nothing else.

    Every code compare in the ported bodies is `String(x).trim().toUpperCase()`, so the
    predicate is written ONCE here rather than re-derived per call site - which is what
    let a did-you-mean re-offer a row the answer had already shown (H45).
    """
    return jsc.nullish_str(value).strip().upper()


def exclude_already_shown(candidates: Any, *, shown_codes: Any) -> list[Any]:
    """H45: drop every candidate whose code is already in the answer.

    ONE outcome-level predicate, applied where the offer is built, rather than a guard
    repeated in each renderer - the hazard was that the renderers disagreed about what
    "already shown" meant.
    """
    shown = {_code_key(c) for c in jsc.array(shown_codes) if _code_key(c)}
    if not shown:
        return list(jsc.array(candidates))
    kept: list[Any] = []
    for candidate in jsc.array(candidates):
        code = candidate if isinstance(candidate, str) else (
            jsc.get(candidate, "code")
            or jsc.get(candidate, "canonical_code")
            or jsc.get(candidate, "label")
        )
        if _code_key(code) in shown:
            continue
        kept.append(candidate)
    return kept


# --------------------------------------------------------------------------- #
# The per-lane completion switch.
# --------------------------------------------------------------------------- #

def completed_lanes(db: Any) -> list[str]:
    """`system_settings.chatbot_completed_lanes`, as a list, default EMPTY.

    A thin adapter over S4's own reader (`engine._enabled_lanes`, itself over
    `delegate.enabled_lanes_from`) so this lane has no second copy of the parsing rules -
    hostile input tolerance included. The engine reads the settings ROW once per turn and
    should pass that row down; this wrapper is for a caller holding only a session.
    """
    from app.services.chatbot.engine import _enabled_lanes

    return sorted(_enabled_lanes(db))


def lane_disposition(
    branch_kind: str | None, *, completed_lanes: Any
) -> Literal["complete", "delegate"]:
    """Does the CRM finish this turn, or hand it back to n8n?

    The same TWO conditions `delegate.delegate_for` applies, phrased for this lane: the
    CODE must be able to complete the arm, and the OWNER must have turned it on. Expressed
    through `delegate_for` itself rather than re-implemented, so the two can never drift
    about a lane's disposition - that drift is the whole reason the pair is checked in one
    place.
    """
    from app.services.chatbot.delegate import delegate_for

    if branch_kind is None:
        return "delegate"
    enabled = frozenset(jsc.array(completed_lanes))
    return "complete" if delegate_for(branch_kind, enabled) is None else "delegate"


# --------------------------------------------------------------------------- #
# validator
# --------------------------------------------------------------------------- #


def validator(
    result: dict[str, Any] | None,
    *,
    semantic_parser: dict[str, Any] | None,
    not_allowed_check_stock: bool = False,
) -> dict[str, Any]:
    """`validator`: stamps `is_valid`, and on the stock-denial arm rewrites `response`.

    `is_valid` is set to TRUE unconditionally - the name is aspirational, and reproducing
    that is the point: `If6` reads it, so a port that made it conditional would reroute
    turns n8n answers today.

    The `not_allowed_check_stock` block is the demand-quantity answer: group the returned
    rows by product, sum `stock_qty`, and say per product whether the demanded quantity can
    be fulfilled. It is reached only from the arm S6a's `Edit Fields2` stamps.
    """
    output = result if isinstance(result, dict) else {}
    output["is_valid"] = True
    if not not_allowed_check_stock:
        return output

    parser_node = semantic_parser if isinstance(semantic_parser, dict) else {}
    parser_output = parser_node.get("output")
    if not isinstance(parser_output, dict):
        parser_output = parser_node
    demand_qty = jsc.js_number(jsc.nullish_str(parser_output.get("demand_qty"), "0"))

    answers = output.get("answers") if isinstance(output.get("answers"), list) else []
    grouped: dict[str, dict[str, Any]] = {}
    for item in answers:
        product = jsc.get(item, "product") or "UNKNOWN_PRODUCT"
        stock_qty = jsc.js_number(
            jsc.get(item, "stock_qty") if jsc.get(item, "stock_qty") is not None else 0
        )
        group = grouped.setdefault(
            product, {"product": product, "total_stock_qty": 0, "rows": []}
        )
        group["total_stock_qty"] += stock_qty
        group["rows"].append(item)

    intro_lines = []
    for group in grouped.values():
        if demand_qty <= group["total_stock_qty"]:
            intro_lines.append(
                f"Quantity of {jsc.js_string(demand_qty)} for product "
                f"{group['product']} can be fulfilled."
            )
        else:
            intro_lines.append(
                f"Quantity of {jsc.js_string(demand_qty)} for product "
                f"{group['product']} cannot be fulfilled. Total available quantity is "
                f"{jsc.js_string(group['total_stock_qty'])}."
            )
    output["response"] = "\n".join(intro_lines)
    return output


# --------------------------------------------------------------------------- #
# build-result
# --------------------------------------------------------------------------- #


def build_result(
    item: dict[str, Any] | None,
    *,
    validator: dict[str, Any] | None,
    promo: dict[str, Any] | None,
    zeroset: dict[str, Any] | None,
    tool: Any = None,
    tier_probe: Any = None,
    crossdomain_render: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """`build-result`: the `result` contract every later reader keys on.

    EVERY value-bearing key is a named producer's output VERBATIM - no reshaping and no
    defaults, except where the producer is itself NULLABLE (`tier_probe`, `xd.block`), in
    which case the null IS the contract.
    """
    body = item if isinstance(item, dict) else {}
    validator_out = validator if isinstance(validator, dict) else {}
    zs = zeroset if isinstance(zeroset, dict) else {}
    block = None
    if isinstance(crossdomain_render, dict):
        block = crossdomain_render.get("_xdBlock") or None
    xd_active = bool(jsc.truthy(zs.get("_xd")) and jsc.get(zs.get("_xd"), "active"))
    return {
        **body,
        "result": {
            # The whole CRM answer envelope, forward-looking: no reader needs it yet.
            "rows": validator_out,
            "has_result": validator_out.get("has_result"),
            "is_valid": validator_out.get("is_valid"),
            "tool": tool,
            "promo": promo,
            "xd": {"active": xd_active, "block": block},
            "tier_probe": tier_probe if tier_probe is not None else None,
        },
    }


# --------------------------------------------------------------------------- #
# access-level-choice-message
# --------------------------------------------------------------------------- #

TIER_DISPLAY = {"office": "Office", "dealer": "Dealer", "end_user": "End user"}
ASK_ORDER = ("office", "dealer", "end_user")

# Friendlier labels than the raw `domain_hint`, verbatim.
DOMAIN_LABELS = {
    "promotion": "promotions",
    "master_products": "product information",
    "product_attachment": "product attachments",
    "inventory": "stock",
    "order": "orders",
    "incoming": "incoming stock",
    "forms": "forms",
    "portal_link": "this request",
}


def access_level_choice_message(
    item: dict[str, Any] | None,
    *,
    parser: dict[str, Any] | None,
    tier_availability: Any = None,
) -> dict[str, Any]:
    """The tier ask, reached on `If4` FALSE: either no access at all, or a pick is needed.

    A NUMBERED TYPED LIST, never WhatsApp quick-reply buttons (D3), offering ONLY the tiers
    this contact holds. The roster is persisted by the tail with
    `selection_context = 'tier_offer'`, and the parser resolves a numbered or tier-word
    reply against it - never to entities.
    """
    out = item if isinstance(item, dict) else {}
    names = out.get("name") if isinstance(out.get("name"), list) else []
    q = parser if isinstance(parser, dict) else {}
    domain = q.get("domain_hint") or "this enquiry"
    domain_label = DOMAIN_LABELS.get(q.get("domain_hint")) or domain

    entitled = out.get("entitled_tiers") if isinstance(out.get("entitled_tiers"), list) else []
    held = [t for t in ASK_ORDER if t in entitled]
    is_clarification = False

    if len(names) == 0:
        escalate_message = f"You have no access levels configured to get {domain_label}."
    elif len(held) == 0:
        # Entitlement holds no mappable tier: fall back to the legacy compound prompt
        # rather than an empty numbered list. Defensive - tier-gate proceeds in this case.
        escalate_message = (
            f"Please specify which access level you'd like to use for {domain_label}:"
        )
        is_clarification = True
    else:
        # D14 availability annotation, styled like every other picker in the system
        # ("1. CODE - has incoming"), with a plain hyphen. `tier_availability` null means
        # "not determined" and renders exactly as before, with no annotation. The
        # all-empty case never reaches here: `if-tier-has-any` sends it down the answer
        # lane so the customer gets the real not-found instead of a list of dead options.
        avail = tier_availability if jsc.truthy(tier_availability) else None
        # D16: name the thing being asked about, so the question cannot read as being
        # about nothing. Echo what the customer TYPED, never a canonical code - one raw
        # token can resolve to two products, and naming one would claim we searched
        # something they did not ask for. Past 60 chars the echo is DROPPED rather than
        # truncated, because half a promotion name reads like a different promotion.
        raws: list[str] = []
        for e in jsc.array(q.get("entities")):
            v = jsc.js_string(jsc.get(e, "raw") or "").strip()
            if v and not any(x.lower() == v.lower() for x in raws):
                raws.append(v)
        scope_label = ", ".join(raws[:3])
        if len(scope_label) > 60:
            scope_label = ""
        scope_suffix = f" for {scope_label}" if scope_label else ""
        lines = "\n".join(
            f"{i + 1}. {TIER_DISPLAY[t]}"
            + ("" if avail is None else (" - has promotion" if jsc.get(avail, t) else " - no promotion"))
            for i, t in enumerate(held)
        )
        escalate_message = (
            f"Which access level do you need{scope_suffix}?\n{lines}\n"
            'Reply with the number(s), e.g. "1", "1 and 2", or "all".'
        )
        is_clarification = True
        out["tier_offer"] = True
        out["tier_last_result_set"] = [
            {
                "idx": i + 1,
                "label": TIER_DISPLAY[t],
                "value": t,
                "tier": t,
                "uuid": None,
                "entity_type": "access_tier",
                "product": None,
                "filename": None,
            }
            for i, t in enumerate(held)
        ]

    out["escalate_message"] = escalate_message
    out["is_clarification"] = is_clarification
    # D3: the ask is a numbered TYPED list, never quick-reply buttons.
    out["quick_reply"] = ""
    return out


# --------------------------------------------------------------------------- #
# crossdomain-zeroset / -probe / -render
# --------------------------------------------------------------------------- #

_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def _norm_code(value: Any) -> str:
    return jsc.js_string(value).strip().upper()


def _envelope_items(env: Any) -> list[Any]:
    """`answers`, else `items`, else nothing - the CRM envelope has carried both."""
    if isinstance(jsc.get(env, "answers"), list):
        return env["answers"]
    if isinstance(jsc.get(env, "items"), list):
        return env["items"]
    return []


def _field_val(item: Any, label: str) -> Any:
    """`fields.find(f => f.label.trim().toLowerCase() === label)`."""
    field = jsc.find(
        jsc.get(item, "fields") or [],
        lambda x: jsc.js_string(jsc.get(x, "label") or "").strip().lower() == label,
    )
    return jsc.get(field, "value") if jsc.truthy(field) else None


def crossdomain_zeroset(
    item: dict[str, Any] | None,
    *,
    parser: dict[str, Any] | None,
    resolved: dict[str, Any] | None,
    session: Any = None,
) -> dict[str, Any]:
    """The SINGLE source of truth for "asked but returned nothing".

    Passes the validator item through UNTOUCHED except for one namespaced key `_xd`, so
    `If6` and the whole miss path see exactly what they see today.
    """
    passthrough = item if isinstance(item, dict) else {}
    out = {**passthrough}

    def off(why: str) -> dict[str, Any]:
        out["_xd"] = {"active": False, "why": why}
        return out

    qf = parser if isinstance(parser, dict) else {}
    dh = qf.get("domain_hint")
    if dh != "inventory" and dh != "incoming":
        return off("domain")
    if qf.get("message_type") != "business_query":
        return off("message_type")

    other_tool = "crm_inventory_stock_balance_list" if dh == "incoming" else "crm_incoming_stock_list"
    team = "purchasing" if dh == "incoming" else "warehouse"

    # The RETURNED set. The tail's own reader prefers `central-exchange`, which does not
    # exist yet at this point in the chain, so this reads the validator item and
    # REPLICATES that unwrap. Parity is proven by the shadow gate, never assumed.
    env: Any = passthrough
    if jsc.truthy(env) and isinstance(jsc.get(env, "output"), dict):
        env = env["output"]
    items = _envelope_items(env)
    returned_codes: set[str] = set()
    for it in items:
        v = _field_val(it, "product code")
        if v is not None and jsc.js_string(v).strip() not in ("", "—"):
            returned_codes.add(_norm_code(v))

    # The REQUESTED set: TYPED-exact UNION DYM-PICKED. Deliberately NOT
    # `compatible_entities`, which drops `match_tier` and carries resolver-expanded
    # siblings the customer never typed.
    rz = resolved if isinstance(resolved, dict) else {}

    def is_prod(m: Any) -> bool:
        return jsc.truthy(m) and jsc.js_string(jsc.get(m, "entity_type")).lower() == "product"

    requested: list[dict[str, Any]] = []
    seen: set[str] = set()

    def uuid_list(u: Any) -> list[Any]:
        if u is None:
            return []
        return [x for x in u if jsc.truthy(x)] if isinstance(u, list) else [u]

    def add(code: Any, uuid: Any, strict: bool) -> None:
        """KEEP EVERY UUID PER CODE, not the first (mc-label).

        One typed code can exist in more than one company, and the resolver returns one
        match per company with the SAME canonical_code. Deduped by CODE, so first-wins
        silently dropped the other company's uuid and the cross-probe then reported that
        company as plainly absent. `uuid` keeps first-add semantics; `uuids` is the union.
        """
        if code is None or code == "":
            return
        n = _norm_code(code)
        if not n:
            return
        us = uuid_list(uuid)
        if n in seen:
            existing = jsc.find(requested, lambda x: x["_n"] == n)
            if jsc.truthy(existing):
                if strict:
                    existing["strict"] = True
                for u in us:
                    if u not in existing["uuids"]:
                        existing["uuids"].append(u)
                # NO backfill of `uuid`: promoting an entry into `probeable` that way
                # started a cross-domain probe that does not run today.
            return
        seen.add(n)
        requested.append(
            {"_n": n, "code": code, "uuid": us[0] if us else None, "uuids": list(us), "strict": bool(strict)}
        )

    or_resolutions = rz.get("resolutions") if isinstance(rz.get("resolutions"), list) else None
    uuid_by_code: dict[str, list[Any]] = {}
    for r in or_resolutions or []:
        for m in jsc.array(jsc.get(r, "matches")):
            if not is_prod(m) or not jsc.truthy(jsc.get(m, "canonical_code")) or not jsc.truthy(
                jsc.get(m, "uuid")
            ):
                continue
            k = _norm_code(jsc.get(m, "canonical_code"))
            bucket = uuid_by_code.setdefault(k, [])
            if jsc.get(m, "uuid") not in bucket:
                bucket.append(jsc.get(m, "uuid"))

    if or_resolutions is not None:
        for r in or_resolutions:
            prods = [m for m in jsc.array(jsc.get(r, "matches")) if is_prod(m)]
            if not prods:
                continue
            exacts = [m for m in prods if jsc.get(m, "match_tier") == "exact"]
            if exacts:
                for m in exacts:
                    if jsc.truthy(jsc.get(m, "canonical_code")):
                        add(jsc.get(m, "canonical_code"), jsc.get(m, "uuid"), False)
            elif len(prods) == 1 and jsc.truthy(jsc.get(prods[0], "canonical_code")):
                add(jsc.get(prods[0], "canonical_code"), jsc.get(prods[0], "uuid"), False)
    else:
        tokens = {_norm_code(t) for t in jsc.array(rz.get("tokens"))}
        if isinstance(rz.get("intersection"), list):
            intersection: list[Any] = rz["intersection"]
        elif jsc.truthy(rz.get("by_entity_type")):
            intersection = []
            for value in (rz.get("by_entity_type") or {}).values():
                intersection.extend(value if isinstance(value, list) else [value])
        else:
            intersection = []
        for m in intersection:
            if is_prod(m) and jsc.truthy(jsc.get(m, "canonical_code")) and _norm_code(
                jsc.get(m, "canonical_code")
            ) in tokens:
                add(jsc.get(m, "canonical_code"), jsc.get(m, "uuid"), False)

    # DYM-PICKED (strict): prior cumulative picks plus this turn's pick.
    variables = jsc.get(jsc.get(session, "session_vars"), "variables")
    if not jsc.truthy(variables):
        variables = jsc.get(session, "variables")
    dym_offer = jsc.get(variables, "dym_offer") if jsc.truthy(variables) else None
    prev = jsc.get(dym_offer, "picked") if isinstance(jsc.get(dym_offer, "picked"), list) else []
    for c in prev:
        add(c, uuid_by_code.get(_norm_code(c)), True)
    if jsc.truthy(qf.get("dym_offer_pick_code")):
        add(
            qf["dym_offer_pick_code"],
            uuid_by_code.get(_norm_code(qf["dym_offer_pick_code"])),
            True,
        )

    # MISSING: a TYPED code is satisfied by a prefix-family member, a PICKED one only
    # exactly. Deliberately does NOT bail when `returned_codes` is empty - that total-miss
    # case is exactly what this feature exists for.
    missing: list[dict[str, Any]] = []
    for rq in requested:
        if rq["strict"]:
            ok = rq["_n"] in returned_codes
        else:
            ok = any(rc == rq["_n"] or rc.startswith(rq["_n"]) for rc in returned_codes)
        if ok:
            continue
        miss = {"code": rq["code"], "uuid": rq["uuid"], "_n": rq["_n"], "entity_type": "product"}
        # Added ONLY when the code really spans companies, so a single-company turn's
        # `_xd.missing` keeps exactly the keys it has today.
        if len(rq["uuids"]) > 1:
            miss["uuids"] = list(rq["uuids"])
        missing.append(miss)
    probeable = [m for m in missing if jsc.truthy(m["uuid"])]

    probe_entities: list[dict[str, Any]] = []
    for m in probeable:
        us = m["uuids"] if isinstance(m.get("uuids"), list) and m["uuids"] else [m["uuid"]]
        probe_entities.extend(
            {"uuid": u, "entity_type": "product", "code": m["code"]} for u in us
        )

    out["_xd"] = {
        "active": len(probeable) > 0,
        "origin_domain": dh,
        "other_tool": other_tool,
        "team": team,
        "requested": [r["code"] for r in requested],
        "returned_codes": list(returned_codes),
        "missing": missing,
        "probe_entities": probe_entities,
    }
    return out


def crossdomain_probe_args(
    zeroset: dict[str, Any] | None,
    *,
    parser: dict[str, Any] | None,
    entities_names: Any,
    contact_id: Any,
    space_id: Any = "364817",
) -> dict[str, Any]:
    """`crossdomain-probe`'s `sub-get-results` inputs, key for key.

    `access_levels` is the SORTED entitlement intersected with what the parser stated, and
    only when the entitlement read ran at all - otherwise the parser's own list, unchanged.
    """
    xd = zeroset if isinstance(zeroset, dict) else {}
    qf = parser if isinstance(parser, dict) else {}
    parser_levels = qf.get("access_levels") if isinstance(qf.get("access_levels"), list) else []
    if entities_names is not None:
        names = sorted(jsc.array(entities_names), key=jsc.js_string)
        access_levels = [a for a in names if a in parser_levels]
    else:
        access_levels = list(parser_levels)
    codes = ", ".join(jsc.js_string(jsc.get(e, "code")) for e in jsc.array(xd.get("probe_entities")))
    return {
        "tool": xd.get("other_tool"),
        "contact_id": contact_id,
        "entities": xd.get("probe_entities"),
        "semantic_input": {
            "message_type": qf.get("message_type") if qf.get("message_type") is not None else None,
            "intent_hint": qf.get("intent_hint") if qf.get("intent_hint") is not None else None,
            "domain_hint": qf.get("domain_hint") if qf.get("domain_hint") is not None else None,
            "user_goal": qf.get("user_goal") if qf.get("user_goal") is not None else None,
            "access_levels": access_levels,
            "contact_id": jsc.js_string(contact_id) if contact_id is not None else None,
            "space_id": space_id,
            "is_active": qf.get("is_active") if qf.get("is_active") is not None else None,
        },
        "user_prompt": (
            f"cross-domain probe ({jsc.js_string(xd.get('origin_domain'))} -> "
            f"{jsc.js_string(xd.get('other_tool'))}) for: {codes}"
        ),
    }


def _fmt_xd_value(v: Any) -> str:
    """`crossdomain-render`'s own `fmtValue` - a PLAIN hyphen, and date-only timestamps."""
    if v is None or v == "":
        return "-"
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, str) and _ISO_RE.match(v):  # D11-reproduced: crossdomain-render's ISO_RE
        match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", v)  # D11-reproduced: same node's Date read
        if match:
            return f"{match.group(3)}/{match.group(2)}/{match.group(1)}"
    if isinstance(v, list):
        return ", ".join(_fmt_xd_value(x) for x in v)
    return jsc.js_string(v)


def crossdomain_render(
    probe_result: dict[str, Any] | None,
    *,
    zeroset: dict[str, Any] | None,
    validator: dict[str, Any] | None,
) -> dict[str, Any]:
    """Render the other domain's rows under the miss, POSITIVE FACTS ONLY.

    A missing code with no probed row is simply not mentioned: saying nothing beats
    asserting an absence the probe did not establish.
    """
    zs = zeroset if isinstance(zeroset, dict) else {}
    passthrough = validator if isinstance(validator, dict) else {}
    out: dict[str, Any] = {**passthrough, "_xd": zs}

    env: Any = probe_result if jsc.truthy(probe_result) else {}
    if jsc.truthy(env) and isinstance(jsc.get(env, "output"), dict):
        env = env["output"]
    has_envelope = (
        isinstance(jsc.get(env, "answers"), list)
        or isinstance(jsc.get(env, "items"), list)
        or isinstance(jsc.get(env, "has_result"), bool)
    )
    if not has_envelope or jsc.truthy(jsc.get(env, "error")):
        out["_xdBlock"] = {
            "block": "",
            "any": False,
            "degraded": True,
            "reason": "probe_error" if jsc.truthy(jsc.get(env, "error")) else "no_envelope",
        }
        return out

    items = _envelope_items(env)

    def field_by_key(it: Any, k: str) -> Any:
        f = jsc.find(jsc.get(it, "fields") or [], lambda x: jsc.has(x, "key") and x["key"] == k)
        return jsc.get(f, "value") if jsc.truthy(f) else None

    def field_pref(it: Any, k: str, *labels: str) -> Any:
        v = field_by_key(it, k)
        if v is not None:
            return v
        for label in labels:
            lv = _field_val(it, label)
            if lv is not None:
                return lv
        return None

    by_code: dict[str, list[Any]] = {}
    for it in items:
        c = jsc.nullish_str(_field_val(it, "product code")).strip()
        if not c or c == "—":
            continue
        by_code.setdefault(c.upper(), []).append(it)

    blocks: list[str] = []
    for m in jsc.array(zs.get("missing")):
        rows = list(by_code.get(jsc.get(m, "_n"), []))
        if not rows:
            continue  # positive facts only

        def qty(it: Any) -> float:
            n = jsc.js_number(field_pref(it, "quantity_on_hand", "quantity on hand"))
            return float("nan") if jsc.is_nan(n) else float(n)

        def eta(it: Any) -> str:
            return jsc.nullish_str(
                field_pref(it, "estimated_arrival_date", "eta", "estimated arrival date")
            )

        if any(not jsc.is_nan(jsc.js_number(qty(it))) for it in rows):
            rows.sort(key=lambda it: -(0 if jsc.is_nan(qty(it)) else qty(it)))
        elif any(eta(it) for it in rows):
            rows.sort(key=eta)
        for it in rows:
            field_lines = "\n".join(
                f"*{jsc.get(f, 'label')}:* {_fmt_xd_value(jsc.get(f, 'value'))}"
                for f in (jsc.get(it, "fields") or [])
            )
            if not field_lines:
                continue
            line = f"- {field_lines}"
            flags = jsc.get(it, "flags") or {}
            if jsc.truthy(jsc.get(flags, "discontinued")):
                line += "\n⚠️  *(PRODUCT DISCONTINUED)*"
            if jsc.truthy(jsc.get(flags, "expired")):
                line += "\n⚠️  *(PROMO EXPIRED)*"
            if jsc.truthy(jsc.get(flags, "unallocated")):
                line += "\n\U0001f6a9  *(PENDING ALLOCATION)*"
            elif jsc.truthy(jsc.get(flags, "partially_allocated")):
                line += "\n\U0001f6a9  *(PARTIAL ALLOCATION)*"
            blocks.append(line)

    lead = (
        "But here are the stock details for the requested products:"
        if zs.get("origin_domain") == "incoming"
        else "But there is INCOMING stock (ETA) for the requested products:"
    )
    xd_files = env["attachments"] if isinstance(jsc.get(env, "attachments"), list) else []
    mention = "\n\n" + "I have attached the file(s) below." if (blocks and xd_files) else ""

    silent_note = ""
    lookup_cos = (
        env["lookup_companies"] if isinstance(jsc.get(env, "lookup_companies"), list) else []
    )
    if blocks and len(lookup_cos) > 1:
        shown = {
            c
            for c in (jsc.nullish_str(_field_val(it, "company")).strip() for it in items)
            if c
        }
        silent = [
            n
            for n in (jsc.nullish_str(jsc.get(c, "name")).strip() for c in lookup_cos)
            if n and n not in shown
        ]
        if shown and silent:
            codes = list(
                dict.fromkeys(
                    c
                    for c in (
                        jsc.nullish_str(_field_val(it, "product code")).strip() for it in items
                    )
                    if c
                )
            )
            what = ("stock" if zs.get("origin_domain") == "incoming" else "incoming") + " records" + (
                f" for {', '.join(codes)}" if codes else ""
            )
            silent_note = "\n\n" + "\n".join(f"*{n}:* no {what}." for n in silent)

    out["_xdBlock"] = {
        "block": (lead + "\n\n" + "\n\n".join(blocks) + silent_note + mention) if blocks else "",
        "any": len(blocks) > 0,
        "attachments": xd_files,
        "team": zs.get("team") or None,
        "origin": zs.get("origin_domain") or None,
        "probed_rows": len(items),
        "rendered_rows": len(blocks),
    }
    return out


def run_crossdomain(
    validator_result: dict[str, Any] | None,
    *,
    parser: dict[str, Any] | None,
    resolved: dict[str, Any] | None,
    session: Any,
    entities_names: Any,
    services: Any,
    contact_id: Any,
    space_id: Any = "364817",
    dry_run: bool = False,
) -> dict[str, Any]:
    """`crossdomain-zeroset -> crossdomain-gate -> crossdomain-probe -> crossdomain-render`.

    D14: a dry run makes the SAME probe. The read is what a test turn has to reproduce, or
    console and clone testing prove nothing about production; the writes are what D14
    suppresses, and this lane has none.
    """
    zeroset = crossdomain_zeroset(
        validator_result, parser=parser, resolved=resolved, session=session
    )
    xd = zeroset.get("_xd") or {}
    if xd.get("active") is not True:
        return {"zeroset": zeroset, "render": None}
    args = crossdomain_probe_args(
        xd,
        parser=parser,
        entities_names=entities_names,
        contact_id=contact_id,
        space_id=space_id,
    )
    try:
        probe_result = services.mcp_probe(args["tool"], args)
    except Exception:  # noqa: BLE001 - a failed probe renders as `degraded`, never a dead turn
        logger.warning("chatbot: cross-domain probe did not run", exc_info=True)
        probe_result = None
    render = crossdomain_render(
        probe_result if isinstance(probe_result, dict) else {},
        zeroset=xd,
        validator=validator_result,
    )
    return {"zeroset": zeroset, "render": render}
