"""The ONE shared text ladder both tail writers walk (PLAN-chatbot-answer-half-reattach.md
slice R4, AC-1683): `escalate_catalog` -> `cs_offer_gate` -> `cs_roster_plan` ->
`fetch_rosters` -> `build_cs_member_offer` -> `build_outcome` -> `compose_reply`.

Extracted out of `engine.run_tail`'s own body (the canned-lane / n8n-delegate tail) so the
new turn engine's own single-domain BUSINESS miss (`app.services.chatbot.answer_bridge.
answer_for`) composes its reply through the SAME code, never a second copy - the plan's
own "text = tail/outcome.escalate_catalog + tail/reply_ladder.compose_reply (alive today)"
line. `engine.run_tail` calls this function for its own producers; behaviour is unchanged
(`test_replay.py`'s byte-for-byte grades stay green, untouched).
"""
from __future__ import annotations

from typing import Any, Mapping

from app.services.chatbot.tail import member_offer as member_mod
from app.services.chatbot.tail import outcome as outcome_mod
from app.services.chatbot.tail import reply_ladder


def compose_from_fragments(
    item: Mapping[str, Any],
    ctx: Mapping[str, Any],
    canned: Any,
    values: Mapping[str, Any],
    *,
    db: Any,
) -> dict[str, Any]:
    """`{text, quick_replies, result_set, producers, outcome}` from a lane's own item and
    fragments - `run_tail`'s own lines, unchanged: the CARRIER_FIELDS producers, the
    escalate catalog (only when `item` carries a `branch_kind`), the CS member offer merge
    (`cs_offer_gate`), `build_outcome`'s 15-key map, then `compose_reply`.

    `producers` and `outcome` ride on the return so a caller (the bridge's own miss arm)
    can tell WHICH producer built the roster a bare number answers next turn
    (`producers["build-cs-member-offer"]` vs `producers["build-suggest-offer"]`) without
    re-deriving `run_miss_lane`'s own output a second time.
    """
    producers: dict[str, Any] = {}
    for name, field in outcome_mod.CARRIER_FIELDS.items():
        if values.get(field) is not None:
            producers[name] = values[field]

    outcome_input: dict[str, Any] = dict(item)
    if str(item.get("branch_kind") or "") != "":
        catalog = outcome_mod.escalate_catalog(
            item,
            ctx,
            canned,
            not_found=values.get("not_found"),
            incoming_picker=values.get("incoming_picker"),
            access_choice=values.get("access_choice"),
            suggest_offer=values.get("suggest_offer"),
            gate=values.get("gate"),
            offer_hold=values.get("offer_hold"),
        )
        producers["escalate-catalog"] = catalog
        outcome_input = catalog
        if outcome_mod.cs_offer_gate(catalog, ctx, values.get("gate")):
            plan = member_mod.cs_roster_plan(values.get("gate"))
            rosters = member_mod.fetch_rosters(db, plan, ctx)
            offer = member_mod.build_cs_member_offer(catalog, plan, rosters)
            producers["cs-roster-plan"] = plan
            producers["build-cs-member-offer"] = offer
            outcome_input = offer

    outcome_items = outcome_mod.build_outcome([{"json": outcome_input}], producers)
    outcome = outcome_items[0]["json"].get("outcome") or {}
    composed = reply_ladder.compose_reply(outcome)
    return {
        "text": composed.get("text"),
        "quick_replies": composed.get("quick_replies"),
        "result_set": composed.get("result_set") or [],
        "producers": producers,
        "outcome": outcome,
    }
