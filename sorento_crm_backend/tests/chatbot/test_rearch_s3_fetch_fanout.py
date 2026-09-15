"""S3 - fetch fan-out (AC-1530, PLAN-chatbot-turn-rearch.md "Fetch and compose").

`turn/fetch.py::run_fetch(plan, ctx) -> list[Envelope]` does not exist yet on this
branch, so EVERY test below is RED at collection with `ModuleNotFoundError:
No module named 'app.services.chatbot.turn.fetch'` - the right reason: the module
this slice adds has not been written. Nothing here reaches an LLM, n8n, respond.io or
a live MCP server; the tool call is stubbed at `ctx.tool_runner` (see the module
docstring below for why that name, not an established one, was picked).

`Envelope` here is the CONTRACT's ""today's fetch envelope dict plus `domain` and
`denied`"" (PLAN, task brief) - a plain dict, not `contracts.Envelope` (the respond.io
webhook envelope) which is an unrelated type of the same English word.

Grant/deny semantics are pinned by `turn/state.py::Profile.grants`'s own docstring
(already committed in S2): `None` = unrestricted; a concrete list denies any domain
whose `reveal_key` (or bare name, absent one) is not a member. `turn/apply.py`'s
`_narrow_and_plan` (also already committed, S2) computes `Plan.denied` from exactly
this rule and excludes a denied domain from `Plan.fetch` - so `run_fetch` is not asked
to re-derive the grant decision, only to emit a `denied=True` envelope for each name in
`plan.denied` and never call a tool for it. This is read off the committed S2 source,
not assumed.

**Ambiguity flagged to the captain**: `ctx`'s exact attribute names (`tool_runner`,
`trace`, `policy`, `profile`) are this tester's own choice, made because no S3 module
exists yet to read the real names off. `ctx.trace` is `trace.TurnTrace()`, the
already-committed stage/event recorder (`trace.add(kind, payload)` - see
`app/services/chatbot/trace.py`), since AC-1530 explicitly asks for "one `tool` trace
event each carrying the domain" and that is the ONE established sub-event seam in this
codebase today (`TurnTrace.add`, consumed by growth-r1's A9 events).
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.services.chatbot.trace import TurnTrace
from app.services.chatbot.turn.plan import FetchSpec, Plan, Trace
from app.services.chatbot.turn.state import Profile

from tests.chatbot._turn_helpers import POLICY_DOMAIN_ROWS, TIER_ORDER_FIXTURE, build_policy, _domain_row


def _policy_with(*rows: dict[str, Any]):
    from app.services.chatbot.turn.policy import Policy

    return Policy.from_rows(domains=list(rows), kinds=[], tier_order=TIER_ORDER_FIXTURE)


def _spec(domain: str, **overrides: Any) -> FetchSpec:
    base = dict(entities=[], filters={}, date_window=None)
    base.update(overrides)
    return FetchSpec(domain=domain, **base)


def _plan(*, fetch: list[FetchSpec], denied: list[str] | None = None) -> Plan:
    return Plan(
        domains=[s.domain for s in fetch] + list(denied or []),
        fetch=fetch,
        ask=None,
        denied=list(denied or []),
        trace=Trace(),
    )


def _ctx(*, policy=None, profile=None, tool_runner=None) -> SimpleNamespace:
    calls: list[tuple[str, FetchSpec]] = []

    def _default_tool(domain: str, spec: FetchSpec) -> dict[str, Any]:
        calls.append((domain, spec))
        return {"items": [{"code": f"{domain}-item"}], "has_result": True}

    runner = tool_runner or _default_tool
    ctx = SimpleNamespace(
        policy=policy or build_policy(),
        profile=profile if profile is not None else Profile(),
        trace=TurnTrace(),
        tool_runner=runner,
    )
    ctx.tool_calls = calls if tool_runner is None else getattr(runner, "calls", [])
    return ctx


def _run_fetch(plan: Plan, ctx: SimpleNamespace):
    from app.services.chatbot.turn.fetch import run_fetch

    return run_fetch(plan, ctx)


class TestOrderAndOneToolEach:
    def test_tools_run_in_plan_fetch_order(self) -> None:
        calls: list[str] = []

        def runner(domain: str, spec: FetchSpec) -> dict[str, Any]:
            calls.append(domain)
            return {"items": [], "has_result": False}

        plan = _plan(
            fetch=[_spec("inventory"), _spec("incoming")],
            denied=[],
        )
        ctx = _ctx(tool_runner=runner)

        envelopes = _run_fetch(plan, ctx)

        assert calls == ["inventory", "incoming"], (
            "run_fetch must call the tool for each FetchSpec in plan.fetch order, "
            f"got call order {calls!r}"
        )
        assert [e["domain"] for e in envelopes] == ["inventory", "incoming"]

    def test_one_tool_trace_event_per_domain_carrying_the_domain(self) -> None:
        plan = _plan(fetch=[_spec("inventory"), _spec("incoming")], denied=[])
        ctx = _ctx()

        _run_fetch(plan, ctx)

        tool_events = [e for e in ctx.trace.events if e.get("kind") == "tool"]
        assert len(tool_events) == 2, (
            f"expected one `tool` trace event per fetched domain, got {tool_events!r}"
        )
        assert {e.get("domain") for e in tool_events} == {"inventory", "incoming"}


class TestDeniedDomainNeverCallsATool:
    def test_denied_domain_yields_denied_envelope_and_no_tool_call(self) -> None:
        calls: list[str] = []

        def runner(domain: str, spec: FetchSpec) -> dict[str, Any]:
            calls.append(domain)
            return {"items": [], "has_result": False}

        plan = _plan(fetch=[], denied=["order"])
        ctx = _ctx(tool_runner=runner)

        envelopes = _run_fetch(plan, ctx)

        assert calls == [], f"a denied domain must never reach the tool runner: {calls!r}"
        assert len(envelopes) == 1
        assert envelopes[0]["domain"] == "order"
        assert envelopes[0]["denied"] is True

    def test_granted_domain_envelope_is_not_denied(self) -> None:
        plan = _plan(fetch=[_spec("inventory")], denied=[])
        ctx = _ctx()

        envelopes = _run_fetch(plan, ctx)

        assert len(envelopes) == 1
        assert envelopes[0]["domain"] == "inventory"
        assert envelopes[0]["denied"] is False


class TestPerDomainGrantsOnTwoDomainFanOut:
    """Contract 128: "per-domain grants on fan-out" - a two-domain plan where one
    domain is denied (SO-outstanding, no grant) must still fetch the other."""

    def test_order_outstanding_denied_inventory_still_fetched(self) -> None:
        calls: list[str] = []

        def runner(domain: str, spec: FetchSpec) -> dict[str, Any]:
            calls.append(domain)
            return {"items": [{"code": f"{domain}-1"}], "has_result": True}

        # Mirrors what S2's `_narrow_and_plan` already produces for this exact shape:
        # `order`'s reveal_key ungranted -> Plan.denied=["order"], Plan.fetch keeps
        # only "inventory".
        plan = _plan(fetch=[_spec("inventory")], denied=["order"])
        ctx = _ctx(
            policy=_policy_with(
                _domain_row("order", narrowing={"customer": "must_narrow_one"}, reveal_key="order_outstanding"),
                _domain_row("inventory", narrowing={"product": "list_all"}),
            ),
            profile=Profile(grants=[]),
            tool_runner=runner,
        )

        envelopes = _run_fetch(plan, ctx)

        by_domain = {e["domain"]: e for e in envelopes}
        assert by_domain["order"]["denied"] is True
        assert by_domain["inventory"]["denied"] is False
        assert calls == ["inventory"], (
            f"the denied domain must be skipped and the granted one still fetched: {calls!r}"
        )


class TestEnvelopeCarriesDomainDataOnSuccess:
    def test_envelope_carries_the_tool_response_shape(self) -> None:
        plan = _plan(fetch=[_spec("inventory")], denied=[])
        ctx = _ctx()

        envelopes = _run_fetch(plan, ctx)

        env = envelopes[0]
        assert env["domain"] == "inventory"
        assert env["denied"] is False
        assert env.get("items") or env.get("has_result") is not None, (
            f"a successful envelope must still carry today's fetch-envelope shape "
            f"(items / has_result), got {env!r}"
        )
