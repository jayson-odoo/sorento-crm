# State: focus + pending + profile (PLAN-chatbot-turn-rearch.md "APPLY contract").
# Dataclasses only - no pydantic here, no I/O, nothing imported outside the stdlib.
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Entity kinds that get their own plural Focus field. Anything else lands in
# `Focus.extra`, keyed by kind - a kind this turn's tests never exercise on Focus
# directly still has somewhere safe to sit rather than being silently dropped.
KIND_FIELD_MAP: dict[str, str] = {
    "product": "products",
    "customer": "customers",
    "warehouse": "warehouse",
    "brand": "brands",
}


@dataclass
class Focus:
    products: list[dict[str, Any]] = field(default_factory=list)
    customers: list[dict[str, Any]] = field(default_factory=list)
    warehouse: list[dict[str, Any]] = field(default_factory=list)
    brands: list[str] = field(default_factory=list)
    tier: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    document: list[str] = field(default_factory=list)
    status: str | None = None
    date_window: dict[str, Any] | None = None
    extra: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


@dataclass
class Profile:
    tier: str | None = None
    language: str | None = None
    # None = unrestricted (every domain answers). A concrete list, possibly empty,
    # switches a domain to deny-by-default: granted only when the domain's own
    # `reveal_key` (or, absent one, its bare name) is a member.
    grants: list[str] | None = None
    default_ledgers: list[str] | None = None


@dataclass
class State:
    focus: Focus
    pending: Any = None
    profile: Profile = field(default_factory=Profile)
    turn_no: int = 0
