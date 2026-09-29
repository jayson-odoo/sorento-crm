# Plan: what APPLY decided, as data (PLAN-chatbot-turn-rearch.md "APPLY contract",
# AC-1528). route() reads a Plan and nothing else.
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FetchSpec:
    domain: str
    entities: list[dict[str, Any]]
    filters: dict[str, Any]
    date_window: dict[str, Any] | None


@dataclass
class Trace:
    rules_fired: list[str] = field(default_factory=list)
    state_diff: dict[str, Any] = field(default_factory=dict)
    narrowing: list[str] = field(default_factory=list)
    reconciled: list[tuple[str, str, str]] = field(default_factory=list)
    # The non-business lane this turn belongs to, when the verdict named one:
    # "escalation", "escalation_declined", "not_supported", "clarification", "casual".
    # `route()` reads it and nothing else does. It lives on the Trace rather than as a
    # sixth Plan field because the Plan's own field set is the contract (AC-1528) - and
    # because "which lane, and why" is exactly what an operator reads the trace for.
    lane: str | None = None
    # The team an ACCEPTED escalation offer named: the option the customer picked off
    # the roster (`payload.team`), else the single team the yes/no offer was made for.
    # It lives beside `lane` for the same reason - it is a fact about WHICH lane this
    # turn goes to, and the Plan's own field set is the contract (AC-1528) - and it has
    # exactly one reader, `engine.run_turn`, which hands it to `lane_parse_output` as
    # the head of the `routing.suggested_team` chain (contract 108).
    team: str | None = None
    # AC-1700: the SPECIFIC member an accepted `member_offer` pick named
    # (`option.payload.respond_user_id`), else `None` for a bare "yes" (round robin) or
    # any other accepted offer kind. Lives beside `team` for the same reason and has the
    # same one reader, `engine.run_turn`, which hands it to `lane_parse_output` as
    # `ctx.parse.output.escalation.preferred_assignee_id` - `lanes/escalation.py::
    # escalation_context`'s own read of that key, the SAME field the retired
    # `head/output_exchange` used to populate, now written by the seam that replaced it
    # instead of a second, parallel assignment mechanism.
    assignee: str | None = None
    # Hand pass 11, blocker 2: the COMPANY a POSITION over a company-carrying escalate
    # offer named (`option.payload.company`), else `None` for a bare "yes" or an offer
    # whose options name no company. Lives beside `assignee` for the same reason and has
    # the same one reader, `engine.run_turn`, which hands it to `lane_parse_output` as
    # `ctx.parse.output.escalation.company_pick` - the key `lanes/escalation.py::
    # escalation_context` already validates a TYPED company name through, so a tapped
    # number and a typed word route through one seam rather than two.
    company: str | None = None
    # What an ANSWERED outstanding question (contract 38, 39) decided: `{kind, scope,
    # detail}`. It lives beside `lane` and `team` for the same reason they do - the
    # Plan's own field set is the contract (AC-1528) - and it has exactly one reader,
    # `apply()` itself, which stamps the carry onto the turn's `FetchSpec.filters` so
    # the runtime knows this fetch is a re-run of the question's own report.
    outstanding: dict[str, Any] | None = None
    # What `turn/decide.py` read this message as: `{"kind", "why"}`. One of ANSWER,
    # REFINE, NEW_ASK or CARRY, and the single rule that decided it. The engine puts it
    # on the `apply` trace record so the console drawer prints the decision itself rather
    # than leaving an operator to infer it from the rules that fired.
    decision: dict[str, str] | None = None
    # The entity kinds a NUMBERED PICK settled this turn. The narrower reads it and does
    # not re-ask them: a roster the customer has just answered is not a choice still on
    # the table, whatever the domain's policy would say about the same rows carried in
    # from an earlier turn (owner hand pass 2, item 10).
    picked_kinds: list[str] = field(default_factory=list)
    # Ported from PR #1118 (feat/chatbot-dealer-stock-verdict, not merged, owner ruling
    # 24 Sep 2026) for chatbot-stock-ask-v2 S3: the OPEN TASK's own re-ask, when this
    # turn resumes a task rather than filling it - the question text, and nothing
    # else. It lives on the Trace for the same reason `lane` and `outstanding` do -
    # the Plan's own field set is the contract - and it has two readers:
    # `turn/route.py`, which keeps the turn on the task's own arm although nothing is
    # being fetched, and `engine.py`, which composes it as the whole reply.
    task_question: str | None = None


@dataclass
class Plan:
    domains: list[str]
    fetch: list[FetchSpec]
    ask: Any
    denied: list[str]
    trace: Trace
