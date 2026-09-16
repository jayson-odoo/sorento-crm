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

from dataclasses import replace
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


def envelope_missed(env: dict[str, Any]) -> bool:
    """Did this domain answer nothing? ONE rule, read by the ladder here and by the
    composer's own miss line.

    A domain missed when it rendered nothing and was neither refused nor broken: either
    every code it was asked about came back in `miss`, or - when the fetch carried no
    named code at all (an order ask narrowed by customer only, a report scoped by date) -
    the TOOL itself said it had no result. `tool_has_result`, not `has_result`, because
    the latter is ANDed with the figures: a report rendered as `lane_text` found rows and
    is not a miss.
    """
    if env.get("figures") or env.get("denied") or env.get("error"):
        return False
    entities = [e for e in (env.get("entities") or [])]
    miss = [m for m in (env.get("miss") or [])]
    if entities:
        return bool(miss) and set(entities) <= set(miss)
    return env.get("tool_has_result") is not True


def _fetch_one(ctx: Any, domain: str, spec: FetchSpec) -> dict[str, Any]:
    result = ctx.tool_runner(domain, spec)
    envelope: dict[str, Any] = {"domain": domain, "denied": False}
    if isinstance(result, dict):
        envelope.update(result)
    trace = getattr(ctx, "trace", None)
    if trace is not None:
        trace.add("tool", {"domain": domain})
    return envelope


def _ladder_of(ctx: Any, domain: str) -> list[str]:
    """`chatbot_domains.ladder` for this domain, in its configured order (AC-1501)."""
    policy = getattr(ctx, "policy", None)
    row = policy.domain(domain) if policy is not None else None
    return [r for r in (getattr(row, "ladder", ()) or ()) if isinstance(r, str) and r]


def run_fetch(plan: Plan, ctx: Any) -> list[dict[str, Any]]:
    envelopes: list[dict[str, Any]] = []

    for spec in plan.fetch:
        envelope = _fetch_one(ctx, spec.domain, spec)
        envelopes.append(envelope)
        _climb(ctx, spec, envelope, envelopes)

    for domain in plan.denied:
        envelopes.append(_denied_envelope(domain))

    return envelopes


def _climb(
    ctx: Any, spec: FetchSpec, primary: dict[str, Any], envelopes: list[dict[str, Any]]
) -> None:
    """Contract 3 and 125: a domain that answered nothing asks the next one along.

    The ladder is `chatbot_domains.ladder`, walked IN ORDER, and it stops at the first
    rung with rows - the customer asked one question, so they get one answer, from
    whichever domain has it. Every rung goes through the SAME `tool_runner` the primary
    fetch used (same gate, same grants, same trace event), so a rung the contact is not
    granted refuses exactly as a named domain would.

    A rung that answers is appended as its own envelope and the composer prints it as a
    second section under the primary's miss line (contract 122, one section per domain).
    When every rung misses, nothing is appended: the rungs tried are recorded ON the
    primary envelope so the miss line can name them once, which is AC-922's "nothing on
    any rung" shape rather than three empty headers.
    """
    if not envelope_missed(primary):
        return
    rungs = _ladder_of(ctx, spec.domain)
    if not rungs:
        return

    tried: list[str] = []
    answered: str | None = None
    for rung in rungs:
        tried.append(rung)
        rung_envelope = _fetch_one(ctx, rung, replace(spec, domain=rung))
        rung_envelope["crossdomain_rung"] = spec.domain
        if not envelope_missed(rung_envelope):
            envelopes.append(rung_envelope)
            answered = rung
            break
    if answered is None:
        primary["rungs_tried"] = list(tried)

    trace = getattr(ctx, "trace", None)
    if trace is not None:
        trace.add(
            "crossdomain",
            {"domain": spec.domain, "rungs_tried": list(tried), "answered": answered},
        )
