"""Port of `route-turn.js` (spine RS-1b): ONE decision, 13 predicates, ladder order.

Every predicate below is the same expression the If ladder it replaced carried, in the
same priority order, and they are evaluated LAZILY in that order. That laziness is
load-bearing, not stylistic: `_is_stock_check_denied` reads
`custom_fields.find(...).value` with no guard and THROWS when the contact has no
`is_allowed_stock` field (live's own expression), and that throw must stay unreachable
for every turn that leaves the ladder earlier.

The two shapes the arms receive are both reproduced:

* the five `TAG_ONLY` arms, whose first n8n node was a STRIPPING `tag-*` Set, get exactly
  `{branch_kind}` - that Set's own output, so the fan-in's input does not move;
* every other arm keeps `ctx.access` (the access check's response, which the If ladder
  passed through untouched) and gains ONE key, `branch_kind`.

R1 (H1) is the one deliberate change and it is a DATA switch, not a code one: n8n tests
`intent_hint === 'stock_check'` while the parser emits `check_stock`, so the whole
demand-qty lane is dead by vocabulary (0/150 live fixtures). The port uses the correct
word, and `stock_denial_enabled` - `system_settings.chatbot_stock_denial_enabled`,
default FALSE - decides whether the predicate is evaluated at all.

**Flag-off is NOT byte-identical, and the difference is worth naming** (review S8). Live
still EVALUATES its dead predicate, so a contact with no `is_allowed_stock` custom field
makes `custom_fields.find(...).value` throw and the turn dies; with the flag off the port
skips the predicate entirely and answers `business_query`. Every contact the corpus has
carries the field, so no capture shows it - but shadow mode will, as a CRM reply where
live sent nothing. It is a strict improvement (an answered turn instead of a dropped one)
and it is recorded in the plan's hazard table on the H1 row rather than left as a
surprise. With the flag ON the throw is reproduced exactly.
"""
from __future__ import annotations

import re
from typing import Any

from app.services.chatbot import jsc
from app.services.chatbot.contracts import TAG_ONLY_BRANCH_KINDS

_BARE_DIGITS = re.compile(r"^[0-9]+$")


def _prev_variables(ctx: dict) -> dict:
    """`(s && s.session_vars && s.session_vars.variables) || (s && s.variables) || {}`."""
    session = ctx.get("session")
    nested = jsc.get(jsc.get(session, "session_vars"), "variables")
    if jsc.truthy(nested):
        return nested
    flat = jsc.get(session, "variables")
    if jsc.truthy(flat):
        return flat
    return {}


def decide(ctx: dict, *, stock_denial_enabled: bool = False) -> tuple[str, dict]:
    """`(branch_kind, tier_stamp)` for one turn. Pure; no I/O, no session write."""
    qf = jsc.get(jsc.get(ctx, "parse"), "output") or {}
    esc = jsc.get(qf, "escalation") or {}

    # -- the 13 predicates, one named function each, in ladder order ---------- #

    def access_allowed() -> bool:
        # `ctx.access.allowed` under operator `true` (strict boolean). An ABSENT value
        # coerces to false and takes the FALSE leg, which is what `!== true` says.
        return jsc.get(jsc.get(ctx, "access"), "allowed") is True

    def wants_escalation_or_help() -> bool:
        # OR of the two clauses, `==` / `!=` kept loose as written.
        return esc.get("is_escalation_confirmation") is True or (
            qf.get("message_type") == "request_for_help"
            and qf.get("domain_hint") != "portal_link"
        )

    def is_cs_order_enquiry_pick() -> bool:
        routing = jsc.get(qf, "routing") or {}
        return (
            esc.get("is_escalation_confirmation") is True
            and qf.get("suggest_pick_context") is True
            and routing.get("suggested_team") == "customer_service"
            and routing.get("suggested_agent") == "order_enquiries"
            and not jsc.truthy(esc.get("preferred_assignee_id"))
        )

    def is_ideate_domain() -> bool:
        # The ONE condition on this ladder with typeValidation `loose`, so the left value
        # is coerced to string before the compare.
        return jsc.js_string(qf.get("domain_hint")) == "ideate"

    def is_offer_hold() -> bool:
        # Verbatim including its fail-closed catch: any missing signal or throw => false
        # => exactly the path this turn took before.
        try:
            if (
                esc.get("is_escalation_confirmation") is True
                or esc.get("escalation_declined") is True
                or esc.get("retarget_team") is True
            ):
                return False
            if qf.get("member_pick_context") is not True:
                return False
            if esc.get("offer_hold") is not True and not isinstance(
                esc.get("member_reprompt"), str
            ):
                return False
            prev = _prev_variables(ctx)
            if prev.get("selection_context") != "member_offer":
                return False
            plan = jsc.array(prev.get("routing_roster_plan"))
            return len(plan) > 1
        except Exception:
            return False

    def is_explicit_correction() -> bool:
        return (
            qf.get("correction") is True
            and qf.get("message_type") != "casual"
            and qf.get("message_type") != "business_query"
        )

    def is_escalation_declined() -> bool:
        return esc.get("escalation_declined") is True

    def is_low_signal() -> bool:
        # OR of four; the fourth is the bare-business-query clause (loose `==`, so an
        # ABSENT domain_hint counts exactly like a null one).
        return (
            qf.get("message_type") == "casual"
            or qf.get("message_type") == "unknown"
            or qf.get("message_type") == "confirmation"
            or (qf.get("message_type") == "business_query" and qf.get("domain_hint") is None)
        )

    def is_clarification() -> bool:
        return qf.get("message_type") == "clarification"

    def is_unsupported_domain() -> bool:
        return qf.get("domain_hint") in ("goods_receive", "spo_allocation")

    def is_check_promotion() -> bool:
        return qf.get("intent_hint") == "check_promotion"

    def is_stock_check_denied() -> bool:
        # H1 / R1: `check_stock` is the vocabulary the parser actually emits. Reachable
        # only when the setting is on, so the lane cannot wake up by accident.
        custom_fields = jsc.get(ctx, "contact")["custom_fields"]
        row = jsc.find(custom_fields, lambda x: jsc.get(x, "name") == "is_allowed_stock")
        # `.value` with no optional chaining: THROWS when the field is absent, which is
        # live's own expression and the reason the ladder above must stay lazy.
        raw = row["value"] if "value" in row else None
        allowed_stock = None if raw is None else jsc.to_boolean(raw)
        return (
            allowed_stock is not True
            and qf.get("intent_hint") == "check_stock"
            and not jsc.is_empty(qf.get("entities"))
        )

    def is_demand_qty_missing() -> bool:
        return jsc.is_empty(qf.get("demand_qty")) or qf.get("demand_qty") == 0

    # -- tier re-pick by digit (RS-9 triage Fix 6) ----------------------------- #
    # In a tiered promotion thread a bare digit or a tier word refers to the TIER MENU,
    # never to promo rows - a promo reply already attaches every file, so row-picking one
    # serves nothing. Exact match, never fuzzy (H42): this is the owner's own rule and the
    # only place outside the parser that reads the raw message, inventoried as such in the
    # plan's text-sniffing table.
    def _tier_menu() -> list | None:
        try:
            variables = _prev_variables(ctx)
            menu = variables.get("tier_menu")
            return menu if jsc.is_array(menu) and len(menu) > 0 else None
        except Exception:
            return None

    def _live_roster_owns_digits() -> bool:
        # A LIVE roster that can legitimately consume a bare digit outranks the tier
        # intercept: a CS-member pick can fire a real assignment. `suggest_offer` is
        # deliberately NOT here - overriding it with the tier menu is the whole rule.
        try:
            variables = _prev_variables(ctx)
            return variables.get("selection_context") in ("member_offer", "disambiguation")
        except Exception:
            return False

    def _raw_msg() -> str:
        try:
            text = jsc.get(ctx, "text")
            value = jsc.get(jsc.get(jsc.get(text, "message"), "message"), "text")
            return jsc.js_string(value if jsc.truthy(value) else "").strip()
        except Exception:
            return ""

    menu = _tier_menu()
    # `tier_menu`'s mere presence already scopes this to the promotion thread; the domain
    # guard only rejects a turn that EXPLICITLY named a different one (loose null, same
    # convention as the bare-business-query clause above).
    thread_ok = qf.get("domain_hint") is None or qf.get("domain_hint") == "promotion"
    raw_msg = _raw_msg()

    tier_hit = False
    tier_entry: Any = None
    if menu and thread_ok and raw_msg and not _live_roster_owns_digits():
        if _BARE_DIGITS.match(raw_msg):
            n = jsc.js_number(raw_msg)
            tier_hit = True
            # An out-of-range digit still routes check_promotion, but with NO valid pick
            # stamped, so tier-gate re-asks instead of dumping a catalogue.
            tier_entry = menu[int(n) - 1] if 1 <= n <= len(menu) else None
        else:
            norm_msg = raw_msg.lower()
            by_word = jsc.find(
                menu,
                lambda e: jsc.js_string(jsc.get(e, "label")).strip().lower() == norm_msg
                or jsc.js_string(jsc.get(e, "value")).strip().lower() == norm_msg,
            )
            if by_word is not None:
                tier_hit = True
                tier_entry = by_word

    # -- the decision --------------------------------------------------------- #
    if not access_allowed():
        branch_kind = "access_denied"
    elif wants_escalation_or_help():
        branch_kind = "escalate_offer" if is_cs_order_enquiry_pick() else "out_of_scope"
    elif is_ideate_domain():
        branch_kind = "ideate"
    elif is_offer_hold():
        branch_kind = "offer_hold"
    elif is_explicit_correction():
        branch_kind = "escalate_offer"
    elif is_escalation_declined():
        branch_kind = "escalation_declined"
    elif tier_hit:
        branch_kind = "check_promotion"
    elif is_low_signal():
        branch_kind = "low_signal"
    elif is_clarification():
        branch_kind = "clarify_menu"
    elif is_unsupported_domain():
        branch_kind = "not_supported"
    elif is_check_promotion():
        branch_kind = "check_promotion"
    elif stock_denial_enabled and is_stock_check_denied():
        branch_kind = "demand_qty" if is_demand_qty_missing() else "stock_denied"
    else:
        branch_kind = "business_query"

    # Fix 6's stamp, additive only. Fix 8: ANY intercept hit proves the promotion thread,
    # so both arms carry the turn's known domain forward.
    tier_stamp: dict[str, Any] = {}
    if tier_hit:
        if tier_entry is not None:
            tier_stamp["tier_pick"] = jsc.get(tier_entry, "value")
        else:
            tier_stamp["tier_pick_invalid"] = True
        tier_stamp["tier_pick_domain"] = "promotion"

    return branch_kind, tier_stamp


def route_turn(ctx: dict, *, stock_denial_enabled: bool = False) -> list[dict[str, Any]]:
    """The n8n item list `route-turn` emits, so a fixture can be replayed against it."""
    branch_kind, tier_stamp = decide(ctx, stock_denial_enabled=stock_denial_enabled)
    if branch_kind in TAG_ONLY_BRANCH_KINDS:
        return [{"json": {"branch_kind": branch_kind}}]
    access = jsc.get(ctx, "access") or {}
    return [{"json": {**access, "branch_kind": branch_kind, **tier_stamp}}]
