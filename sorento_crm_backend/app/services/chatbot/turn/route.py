# route: Plan in, one branch kind out - and nothing else (PLAN-chatbot-turn-rearch.md
# "APPLY contract", AC-1528).
from __future__ import annotations

from app.services.chatbot.turn.plan import Plan


def route(plan: Plan) -> str:
    if plan.denied and not plan.fetch and plan.ask is None:
        return "access_denied"
    if plan.ask is not None:
        return "clarify_menu"
    if plan.fetch:
        return "business_query"
    if plan.denied:
        return "access_denied"
    return "low_signal"
