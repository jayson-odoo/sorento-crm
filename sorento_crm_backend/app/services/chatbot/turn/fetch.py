# Fetch fan-out: loop `plan.fetch` in order, resolve -> gate -> tool -> envelope
# (PLAN-chatbot-turn-rearch.md "Fetch and compose", AC-1530). A denied domain
# (already decided by `turn/apply.py::_narrow_and_plan`, S2) never reaches a tool -
# it yields a `denied=True` envelope and nothing else.
#
# `ctx` here is a duck-typed bag (`SimpleNamespace` in tests, whatever `engine.py`
# builds in production): `ctx.tool_runner(domain, spec) -> dict` is the ONE seam that
# actually reaches a tool (an MCP call in production, a stub in every test), and
# `ctx.trace` is `app.services.chatbot.trace.TurnTrace`, whose `.add(kind, payload)`
# records one `tool` event per fetched domain (contract 129: "one tool entry per
# domain").
from __future__ import annotations

from typing import Any

from app.services.chatbot.turn.plan import FetchSpec, Plan


def _denied_envelope(domain: str) -> dict[str, Any]:
    return {
        "domain": domain,
        "denied": True,
        "entities": [],
        "figures": [],
        "files": [],
        "miss": [],
    }


def run_fetch(plan: Plan, ctx: Any) -> list[dict[str, Any]]:
    envelopes: list[dict[str, Any]] = []

    for spec in plan.fetch:
        result = ctx.tool_runner(spec.domain, spec)
        envelope: dict[str, Any] = {"domain": spec.domain, "denied": False}
        if isinstance(result, dict):
            envelope.update(result)
        trace = getattr(ctx, "trace", None)
        if trace is not None:
            trace.add("tool", {"domain": spec.domain})
        envelopes.append(envelope)

    for domain in plan.denied:
        envelopes.append(_denied_envelope(domain))

    return envelopes
