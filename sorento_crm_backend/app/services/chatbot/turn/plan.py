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


@dataclass
class Plan:
    domains: list[str]
    fetch: list[FetchSpec]
    ask: Any
    denied: list[str]
    trace: Trace
