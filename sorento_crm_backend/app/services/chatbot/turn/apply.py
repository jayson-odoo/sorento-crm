# apply(): the pure core (PLAN-chatbot-turn-rearch.md "APPLY contract", AC-1520). One
# function, six named steps called in order: answer_pending, focus_rules, exclusive,
# reconcile, narrow, plan. No message text read anywhere below - every input is
# already-structured (Verdict dict, Policy, State).
from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any

from app.services.chatbot.turn.narrow import decide as narrow_decide
from app.services.chatbot.turn.pending import ROSTER_KINDS, Pending, ask as pending_ask, with_answered_positions
from app.services.chatbot.turn.plan import FetchSpec, Plan, Trace
from app.services.chatbot.turn.policy import Policy
from app.services.chatbot.turn.reconcile import apply_reconciliation
from app.services.chatbot.turn.state import KIND_FIELD_MAP, Focus, State

RESET_KEEPS = {"tier", "brands"}


def _set_kind_field(focus: Focus, kind: str, entities: list[dict[str, Any]]) -> None:
    attr = KIND_FIELD_MAP.get(kind)
    if attr:
        setattr(focus, attr, entities)
    else:
        focus.extra[kind] = entities


def _answer_pending(state: State, verdict: dict[str, Any], trace: Trace):
    # Returns (focus_after, pending_after, short_circuit_plan, domain_locked).
    pending = state.pending
    focus = copy.deepcopy(state.focus)

    if pending is None:
        return focus, None, None, False

    answers = verdict.get("answers_open_question") or {}
    if answers.get("resolved") is True:
        picks = answers.get("picks")
        if picks == "all":
            positions = [o["position"] for o in pending.options]
        elif isinstance(picks, list):
            positions = picks
        else:
            positions = []

        matched = [o for o in pending.options if o.get("position") in positions]
        if matched:
            built: list[dict[str, Any]] = []
            for option in matched:
                uuids = option.get("uuids") or ([option["uuid"]] if option.get("uuid") else [])
                for u in uuids:
                    built.append(
                        {
                            "raw": option.get("label"),
                            "hint": option.get("entity_type"),
                            "canonical_code": u,
                            "uuid": u,
                            "current_message": True,
                            "confident": True,
                        }
                    )
            kind_for_focus = matched[0].get("entity_type")
            if kind_for_focus:
                _set_kind_field(focus, kind_for_focus, built)

        trace.rules_fired.append("answer_pending")
        if pending.kind in ROSTER_KINDS:
            return focus, with_answered_positions(pending, positions), None, True
        return focus, None, None, True

    is_affirmative = verdict.get("is_affirmative")
    escalation = verdict.get("escalation") or {}
    verdict_entities = verdict.get("entities") or []

    if is_affirmative is True or escalation.get("is_escalation_confirmation") is True:
        trace.rules_fired.append("answer_pending_accept")
        return focus, None, None, False

    if escalation.get("escalation_declined") is True or (is_affirmative is False and not verdict_entities):
        trace.rules_fired.append("answer_pending_decline")
        return focus, None, None, False

    if is_affirmative is False and verdict_entities:
        # A "no" carrying its own entities is not a decline - the offer stays open.
        trace.rules_fired.append("answer_pending_own_entities")
        return focus, pending, None, False

    # Nothing resolved it: the SAME question is re-printed, state untouched.
    trace.rules_fired.append("answer_pending_unresolved")
    short_circuit = Plan(domains=[], fetch=[], ask=pending, denied=[], trace=trace)
    return state.focus, pending, short_circuit, False


def _focus_rules(
    focus: Focus,
    verdict: dict[str, Any],
    entities: list[dict[str, Any]],
    *,
    domain_locked: bool,
    domain_override: str | None,
    trace: Trace,
) -> Focus:
    if verdict.get("topic_reset"):
        kept = {k: getattr(focus, k) for k in RESET_KEEPS}
        focus = Focus(**kept)
        trace.rules_fired.append("reset_on_topic")
        return focus

    confident_entities = [e for e in entities if e.get("confident") is not False]
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for e in confident_entities:
        hint = e.get("hint")
        if not hint:
            continue
        by_kind.setdefault(hint, []).append(e)

    for kind, group in by_kind.items():
        _set_kind_field(focus, kind, group)
    if by_kind:
        trace.rules_fired.append("replace_same_axis")
    else:
        trace.rules_fired.append("reuse_alive")

    if not domain_locked:
        asks = verdict.get("asks") or []
        if domain_override:
            focus.domains = [domain_override]
            trace.rules_fired.append("domains_from_reconciliation")
        elif asks:
            focus.domains = [a["domain"] for a in asks if a.get("domain")]
            trace.rules_fired.append("domains_from_asks")
        elif verdict.get("domain_hint"):
            focus.domains = [verdict["domain_hint"]]
            trace.rules_fired.append("domains_from_asks")
        # else: no domain word this turn - focus.domains carries over unchanged.

    document = verdict.get("document")
    status = verdict.get("status")
    if document:
        focus.document = list(document)
    if status:
        focus.status = status
    if verdict.get("date_mode") or verdict.get("date_filter_start") or verdict.get("date_filter_end"):
        focus.date_window = {
            "mode": verdict.get("date_mode"),
            "start": verdict.get("date_filter_start"),
            "end": verdict.get("date_filter_end"),
        }
        trace.rules_fired.append("date_restated_only")

    return focus


def _exclusive(verdict: dict[str, Any], trace: Trace) -> None:
    # `replace_same_axis` already narrows only the axis a new entity named (see
    # `_focus_rules` above) - `scope_exclusive` confirms the same reading rather than
    # changing it, so this step is a trace marker, not a second mutation.
    if verdict.get("scope_exclusive"):
        trace.rules_fired.append("exclusive")


def _reconcile_step(
    entities: list[dict[str, Any]],
    resolved: dict[str, dict[str, int]] | None,
    policy: Policy,
    verdict: dict[str, Any],
    trace: Trace,
):
    result = apply_reconciliation(entities, resolved)
    trace.reconciled = result.reconciled

    if result.kind_pick_options is not None:
        pending = pending_ask("kind_pick", result.kind_pick_options, team=None, asked_at_turn=None)
        return result.entities, None, Plan(domains=[], fetch=[], ask=pending, denied=[], trace=trace)

    domain_override = None
    if result.reconciled and not verdict.get("domain_hint") and not verdict.get("asks"):
        _raw, _old, new_kind = result.reconciled[-1]
        for row in policy.domains:
            if new_kind in row.narrowing:
                domain_override = row.name
                break

    return result.entities, domain_override, None


def _narrow_and_plan(
    focus: Focus,
    policy: Policy,
    domains: list[str],
    state: State,
    trace: Trace,
) -> Plan:
    denied: list[str] = []
    ask: Pending | None = None
    fetch: list[FetchSpec] = []

    outcomes = []
    for name in domains:
        row = policy.domain(name)
        if row is None:
            continue
        if state.profile.grants is not None:
            required = row.reveal_key or row.name
            if required not in state.profile.grants:
                denied.append(name)
                continue
        entities: list[dict[str, Any]] = []
        filters: dict[str, Any] = {}
        domain_ask_kind = None
        domain_ask_options: list[dict[str, Any]] = []
        for kind, policy_value in row.narrowing.items():
            outcome = narrow_decide(kind=kind, policy_value=policy_value, focus=focus, profile=state.profile)
            trace.narrowing.append(f"{name}.{kind}:{policy_value}")
            if outcome.ask_kind:
                domain_ask_kind = outcome.ask_kind
                domain_ask_options = outcome.ask_options
                break
            entities.extend(outcome.entities)
            if outcome.filter_value is not None:
                filters[kind] = outcome.filter_value
        outcomes.append((name, domain_ask_kind, domain_ask_options, entities, filters))

    asking = next((o for o in outcomes if o[1]), None)
    if asking:
        name, ask_kind, ask_options, _entities, _filters = asking
        team = policy.domain(name).escalation_team_code if policy.domain(name) else None
        ask = pending_ask(ask_kind, ask_options, team=team, asked_at_turn=state.turn_no)
    else:
        for name, _ask_kind, _ask_options, entities, filters in outcomes:
            row = policy.domain(name)
            fetch.append(
                FetchSpec(
                    domain=name,
                    entities=entities,
                    filters=filters,
                    date_window=focus.date_window if row and row.takes_date_filter else None,
                )
            )

    return Plan(domains=list(domains), fetch=fetch, ask=ask, denied=denied, trace=trace)


def apply(
    state: State,
    verdict: dict[str, Any],
    policy: Policy,
    resolved: dict[str, dict[str, int]] | None = None,
):
    trace = Trace()

    verdict_entities = list(verdict.get("entities") or [])
    entities, domain_override, reconcile_short_circuit = _reconcile_step(
        verdict_entities, resolved, policy, verdict, trace
    )
    if reconcile_short_circuit is not None:
        return state, reconcile_short_circuit

    focus_after_pending, pending_after, pending_short_circuit, domain_locked = _answer_pending(
        state, verdict, trace
    )
    if pending_short_circuit is not None:
        unchanged = replace(state, pending=pending_after)
        return unchanged, pending_short_circuit

    _exclusive(verdict, trace)

    focus = _focus_rules(
        focus_after_pending,
        verdict,
        entities,
        domain_locked=domain_locked,
        domain_override=domain_override,
        trace=trace,
    )

    asks = verdict.get("asks") or []
    if asks:
        domains = [a["domain"] for a in asks if a.get("domain")]
    elif verdict.get("domain_hint"):
        domains = [verdict["domain_hint"]]
    else:
        domains = list(focus.domains)

    new_state = State(focus=focus, pending=pending_after, profile=state.profile, turn_no=state.turn_no)
    plan = _narrow_and_plan(focus, policy, domains, new_state, trace)

    return new_state, plan
