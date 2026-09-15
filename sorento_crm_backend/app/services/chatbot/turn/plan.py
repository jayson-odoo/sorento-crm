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


@dataclass
class Plan:
    domains: list[str]
    fetch: list[FetchSpec]
    ask: Any
    denied: list[str]
    trace: Trace
