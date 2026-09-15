# route: Plan in, one branch kind out - and nothing else (PLAN-chatbot-turn-rearch.md
# "APPLY contract", AC-1528). Stage D of the seven.
#
# Thirteen branch kinds, but only six DECISIONS (the plan's own stage D: "ask | business
# | escalation | casual | canned | denied"); the kinds are what the lanes, the trace
# screen and n8n's own arm names have always been called, so the mapping stays visible
# here rather than being renamed underneath them.
#
# Two kinds are deliberately absent: `access_denied` from a refused access agent, and
# `stock_denied` / `demand_qty`, which are decided from the CONTACT's own record before a
# plan exists at all (contract 58, 61, 62). The engine settles those before it routes.
from __future__ import annotations

from app.services.chatbot.turn.plan import Plan

# A pending kind the turn is ASKING becomes the arm that owns that question.
_ASK_BRANCH: dict[str, str] = {
    "team_pick": "escalate_offer",
    "member_offer": "escalate_offer",
    "company_pick": "escalate_offer",
}

_LANE_BRANCH: dict[str, str] = {
    "escalation": "out_of_scope",
    "escalation_declined": "escalation_declined",
    "not_supported": "not_supported",
    "clarification": "clarify_menu",
    "casual": "low_signal",
}


def route(plan: Plan) -> str:
    # A question outranks everything: a turn that cannot say WHAT it is about has nothing
    # to fetch and nobody to escalate to yet (contract 111 - did-you-mean before the team
    # question).
    if plan.ask is not None:
        return _ASK_BRANCH.get(plan.ask.kind, "clarify_menu")

    if plan.denied and not plan.fetch:
        return "access_denied"

    lane = plan.trace.lane
    if lane in _LANE_BRANCH:
        return _LANE_BRANCH[lane]

    if "ideate" in plan.domains:
        return "ideate"

    if plan.fetch:
        return "business_query"

    return "low_signal"
