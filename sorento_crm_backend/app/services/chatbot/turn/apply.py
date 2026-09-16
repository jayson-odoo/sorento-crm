# apply(): the pure core (PLAN-chatbot-turn-rearch.md "APPLY contract", AC-1520). One
# function, six named steps called in order: answer_pending, focus_rules, exclusive,
# reconcile, narrow, plan. No message text read anywhere below - every input is
# already-structured (Verdict dict, Policy, State).
from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any

from app.services.chatbot import contracts
from app.services.chatbot.turn.narrow import decide as narrow_decide
from app.services.chatbot.turn.pending import ROSTER_KINDS, Pending, ask as pending_ask, with_answered_positions
from app.services.chatbot.turn.plan import FetchSpec, Plan, Trace
from app.services.chatbot.turn.policy import Policy
from app.services.chatbot.turn.reconcile import apply_reconciliation
from app.services.chatbot.turn.state import KIND_FIELD_MAP, Focus, State

RESET_KEEPS = {"tier", "brands"}

# D6, "domain follows the document": a turn that names a document kind and no domain is
# about the domain that OWNS that document. A dict rather than a policy column because it
# is five literals that follow from what the document IS - a migration for this would be a
# table with one true row shape and no second reader.
DOMAIN_BY_DOCUMENT: dict[str, str] = {
    "SO": "order",
    "DO": "order",
    "PO": "purchase_order",
    "SPO": "incoming",
    "GRN": "goods_receive",
}


def _is_continuation(verdict: dict[str, Any]) -> bool:
    """AC-1317: "show me the next page of the set you just counted". The parser's own
    `continuation` schema key (bool), read as-is - matching free-text `user_goal`
    against a word list was still a text rule wearing the parser's clothes; a
    dedicated boolean is the deterministic signal (captain ruling, 16 Sep 2026)."""
    return verdict.get("continuation") is True


def _domain_of_document(document: list[str]) -> str | None:
    for kind in document:
        name = DOMAIN_BY_DOCUMENT.get(str(kind).strip().upper())
        if name:
            return name
    return None


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
        # Contract 121: a pick never re-domains the turn. The question recorded the
        # domain it was asked for, so the answer goes back to it rather than leaving
        # a bare positional with nothing to be about.
        asked_for = pending.payload.get("domain")
        if asked_for:
            focus.domains = [asked_for]
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

    if answers.get("resolved") is False:
        # The customer TRIED to answer and missed (a number off the list, a label that
        # matches nothing offered): the SAME question is re-printed, state untouched.
        trace.rules_fired.append("answer_pending_unresolved")
        short_circuit = Plan(domains=[], fetch=[], ask=pending, denied=[], trace=trace)
        return state.focus, pending, short_circuit, False

    # `resolved` null (or absent): the parser judged this message to be about something
    # else (cluster 4, owner ruling 16 Sep 2026 - the PARSER decides, no word lists). It
    # is not an answer, so the question stays open exactly as it was and the message is
    # planned as any other; the tail keeps the carried pending (`answer.question or
    # state.pending`). Before this rule every such message fell through to the re-print
    # above, which is what re-asked the customer on every aside the moment the question
    # survived a dry run (finding 2a).
    trace.rules_fired.append("answer_pending_not_an_answer")
    return focus, pending, None, False


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
        # Every axis the old topic filled goes; the tier and the brand are the contact's,
        # not the topic's, so they stay. The rules BELOW still run on the emptied focus -
        # a reset turn is a new topic, and it names that topic's own domain and entities
        # in the same breath ("never mind, promotions?"). Returning here left the new
        # topic with no domain at all, so the next reset had nothing to close an episode
        # on (AC-1546).
        kept = {k: getattr(focus, k) for k in RESET_KEEPS}
        focus = Focus(**kept)
        trace.rules_fired.append("reset_on_topic")

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


# The message types that carry no business question of their own (contract 49, 51).
_CASUAL_TYPES = frozenset({"casual", "unknown", "confirmation"})
# Domains that answer a request for help rather than escalating it (contract 21, 22).
_HELP_EXEMPT_DOMAINS = frozenset({"portal_link", "ideate"})


def _lane(verdict: dict[str, Any], domains: list[str], policy: Policy) -> str | None:
    """Which NON-business lane this turn belongs to, or None for a business question.

    Read off the verdict's own structured signals and the policy's `supported` flag -
    never off the message. `route()` is the only reader (AC-1528: the router takes a plan
    and nothing else), so the decision is made here, where the verdict is.
    """
    escalation = verdict.get("escalation") or {}
    message_type = verdict.get("message_type")

    if escalation.get("escalation_declined") is True:
        return "escalation_declined"
    if escalation.get("is_escalation_confirmation") is True:
        return "escalation"
    if message_type == "escalation":
        return "escalation"
    if message_type == "request_for_help" and verdict.get("domain_hint") not in _HELP_EXEMPT_DOMAINS:
        return "escalation"
    if domains and all(
        (policy.domain(name) is not None and not policy.domain(name).supported) for name in domains
    ):
        return "not_supported"
    if message_type == "clarification":
        return "clarification"
    if message_type in _CASUAL_TYPES:
        # Owner console pass 4 item E (`member_offer_filter_modification` in the old
        # ladder): a casual-typed turn that still names or carries a domain is
        # narrowing a LIVE business question, not idle chat - the customer's own
        # words were the whole reason `domains` resolved to something, and swallowing
        # it here would answer "hanlim" with small talk instead of the order it names.
        if domains:
            return None
        # Owner console defect E: `scope_intent: "broaden"` on a casual/no-domain turn
        # asks to see MORE, not less - that is a clarifying question, never idle chat.
        if verdict.get("scope_intent") == "broaden":
            return "clarification"
        return "casual"
    if message_type == "business_query" and not domains:
        return "casual"
    return None


def _did_you_mean(
    entities: list[dict[str, Any]],
    policy: Policy,
    state: State,
    trace: Trace,
    candidates: dict[str, list[dict[str, Any]]] | None = None,
):
    """An entity the parser could not place asks before anything else does (contract 26,
    111: did-you-mean before the team question).

    `confident is False` is the parser's own "I read a token here and could not pin it".
    The kind's `did_you_mean` flag (AC-1502) decides whether that kind is worth asking
    about at all; a kind that is not stays silent and simply does not narrow.

    A kind the RESOLVER already found real candidates for (the second `apply()` pass,
    `candidates` non-empty for this kind) defers to the narrower instead of asking the
    raw guess back: "wc286" is one typed word and ten real products, and a roster of the
    resolver's own matches is a better question than "did you mean wc286?" - the
    narrower's `narrow_to_code` ask is what actually lists them (contract 28).
    """
    unsure = [e for e in entities if e.get("confident") is False and e.get("hint")]
    if not unsure:
        return None
    kind = unsure[0]["hint"]
    if (candidates or {}).get(kind):
        return None
    row = policy.kind(kind)
    if row is not None and not row.did_you_mean:
        return None
    options = [
        {
            "position": i + 1,
            "label": e.get("raw"),
            "uuid": e.get("canonical_code") or e.get("raw"),
            "uuids": [e.get("canonical_code") or e.get("raw")],
            "entity_type": kind,
            "payload": {"did_you_mean": True},
        }
        for i, e in enumerate(unsure)
    ]
    trace.rules_fired.append("did_you_mean")
    return pending_ask(f"{kind}_pick", options, asked_at_turn=state.turn_no, expects="pick")


def _narrow_and_plan(
    focus: Focus,
    policy: Policy,
    domains: list[str],
    state: State,
    trace: Trace,
    attributes: tuple[str, ...] = (),
    candidates: dict[str, list[dict[str, Any]]] | None = None,
) -> Plan:
    denied: list[str] = []
    ask: Pending | None = None
    fetch: list[FetchSpec] = []

    outcomes = []
    for name in domains:
        row = policy.domain(name)
        if row is None:
            continue
        if not row.supported:
            # The bot refuses this domain out of the box (contract 63). Nothing is
            # fetched and nothing is asked; `_lane` has already routed the turn.
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
            outcome = narrow_decide(
                kind=kind,
                policy_value=policy_value,
                focus=focus,
                profile=state.profile,
                attributes=attributes,
                resolved_candidates=(candidates or {}).get(kind),
            )
            trace.narrowing.append(f"{name}.{kind}:{outcome.note or policy_value}")
            if outcome.ask_kind:
                domain_ask_kind = outcome.ask_kind
                domain_ask_options = outcome.ask_options
                break
            entities.extend(outcome.entities)
            if outcome.filter_value is not None:
                filters[kind] = outcome.filter_value
        # Attribute-first (AC-1534): a HAS turn ("which taps have certificates") names
        # its scope with a `product_type`/`category` entity, not a `product` one - the
        # resolver's own class-word match is what carries the real product candidates
        # (`turn_runtime.candidates_by_kind`'s "product" bucket), and a domain whose
        # `narrowing` map has no "product" key (most domains never narrow on it) would
        # otherwise leave the fetch with NO entities at all, which falls through to
        # every compatible entity the resolver matched for ANY token this turn -
        # including ones the class word coincidentally also hit (contract 114). Only
        # fires when nothing already claimed "product" and this domain did not ask.
        if (
            attributes
            and domain_ask_kind is None
            and "product" not in row.narrowing
            and not entities
        ):
            product_candidates = (candidates or {}).get("product")
            if product_candidates:
                entities.extend(product_candidates)
        outcomes.append((name, domain_ask_kind, domain_ask_options, entities, filters))

    asking = next((o for o in outcomes if o[1]), None)
    if asking:
        name, ask_kind, ask_options, _entities, _filters = asking
        team = policy.domain(name).escalation_team_code if policy.domain(name) else None
        if ask_kind == "tier_pick" and not ask_options:
            # The tier menu is the policy's own order (AC-1502), not a hand-built list:
            # the narrower knows a tier is missing, the policy knows which tiers exist.
            ask_options = [
                {
                    "position": i + 1,
                    "label": tier.replace("_", " "),
                    "uuid": tier,
                    "uuids": [tier],
                    "entity_type": "tier",
                    "payload": {"tier": tier},
                }
                for i, tier in enumerate(policy.tier_order)
            ]
        ask = pending_ask(
            ask_kind,
            ask_options,
            team=team,
            asked_at_turn=state.turn_no,
            expects="pick",
            # The domain this question is being asked FOR: what the answer goes back
            # to next turn (contract 121), since the answer itself is a bare number.
            payload={"domain": name},
        )
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
    candidates: dict[str, list[dict[str, Any]]] | None = None,
):
    trace = Trace()

    # F3 (contract 65): a `domain_hint` outside the declared enum must never reach a
    # reader - evidence turn b5b19cec-dccc-4eda-b766-1aeb1362957b emitted "purchasing"
    # (a TEAM name, not a domain) and it survived into a tool pick. `coerce_domain_hint`
    # existed but had no call site anywhere in the rearch (AC-1592 test triage);
    # coerced ONCE here, at the verdict's one entry point into apply(), so every
    # downstream read (`_reconcile_step`, `_answer_pending`, `_exclusive`,
    # `_focus_rules`, the `domains` build below, `_lane`) sees the same coerced value
    # rather than needing its own guard.
    coerced_domain_hint = contracts.coerce_domain_hint(verdict.get("domain_hint"))
    if coerced_domain_hint != verdict.get("domain_hint"):
        trace.rules_fired.append("domain_hint_coerced")
        verdict = {**verdict, "domain_hint": coerced_domain_hint}

    # AC-1592 test triage: the old `head/output_exchange.py::_assert_emission` named
    # a malformed emission's bad KEY and expected TYPE before anything downstream ever
    # touched it; the S3 rewrite dropped it with no equivalent, so a malformed
    # `entities` (a real LLM call cannot produce one - `head/parser.py::parse` passes
    # `json_schema=PARSE_OUTPUT_JSON_SCHEMA` straight to the provider - this is a
    # harness-injected-mock hazard only) surfaced as an unnamed `AttributeError` deep
    # in a helper instead of a clear, named failure. `entities` is the one declared
    # ARRAY key this module actually reads item-by-item.
    raw_entities = verdict.get("entities")
    if raw_entities is not None and not isinstance(raw_entities, list):
        raise contracts.ParserOutputError(
            f"parser emission key 'entities' must be an array, got "
            f"{type(raw_entities).__name__}"
        )

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
    elif focus.domains:
        domains = list(focus.domains)
    else:
        # D6: nothing named a domain and nothing is carried, but the focus knows what
        # DOCUMENT the conversation is about, and a document belongs to one domain.
        carried = _domain_of_document(focus.document)
        domains = [carried] if carried else []
        if carried:
            focus.domains = [carried]
            trace.rules_fired.append("domain_follows_document")

    new_state = State(focus=focus, pending=pending_after, profile=state.profile, turn_no=state.turn_no)
    trace.lane = _lane(verdict, domains, policy)

    # A did-you-mean outranks both the narrower and the lane: an entity nobody could place
    # is the first thing worth asking about (contract 26, 111).
    answers = verdict.get("answers_open_question") or {}
    if answers.get("resolved") is not True:
        dym = _did_you_mean(entities, policy, new_state, trace, candidates)
        if dym is not None:
            return new_state, Plan(
                domains=list(domains), fetch=[], ask=dym, denied=[], trace=trace
            )

    # A continuation pages the set the LAST answer described: same domain, same
    # description, one page further on (AC-1317). It never re-narrows and never re-asks -
    # the customer has already answered every question this set needed.
    if _is_continuation(verdict) and focus.set_page:
        carried = focus.set_page.get("set_key") or {}
        domain = carried.get("domain")
        if domain:
            trace.rules_fired.append("set_page_continuation")
            return new_state, Plan(
                domains=[domain],
                fetch=[
                    FetchSpec(
                        domain=domain,
                        entities=[],
                        filters={"set_page": dict(focus.set_page)},
                        date_window=None,
                    )
                ],
                ask=None,
                denied=[],
                trace=trace,
            )

    attributes = tuple(
        a for a in (verdict.get("requested_attributes") or []) if isinstance(a, str) and a
    )
    plan = _narrow_and_plan(focus, policy, domains, new_state, trace, attributes, candidates)

    return new_state, plan
