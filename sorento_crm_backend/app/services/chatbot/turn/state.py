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


# --------------------------------------------------------------------------- #
# The wire shape: what `respond_contacts.session_vars.focus` holds between turns
# (AC-1504). ONE shape, not two - `apply()` works on this dataclass and the session
# stores the same axes, so nothing has to map a singular field onto a plural one and
# lose a ledger family on the way (journey step 5, D7).
# --------------------------------------------------------------------------- #

FOCUS_LIST_FIELDS = ("products", "customers", "warehouse", "brands", "tier", "domains", "document")


def focus_to_wire(focus: Focus) -> dict[str, Any]:
    wire: dict[str, Any] = {name: list(getattr(focus, name)) for name in FOCUS_LIST_FIELDS}
    wire["status"] = focus.status
    wire["date_window"] = focus.date_window
    wire["extra"] = {k: list(v) for k, v in (focus.extra or {}).items()}
    return wire


def focus_from_wire(raw: Any) -> Focus:
    """The inverse. Tolerant by design: a slot written by an older build may hold a bare
    string where this one holds an entity dict, and a focus that cannot be read is a
    forgotten conversation, not a failed turn."""
    if not isinstance(raw, dict):
        return Focus()
    focus = Focus()
    for name in FOCUS_LIST_FIELDS:
        value = raw.get(name)
        if not isinstance(value, list):
            continue
        if name in ("brands", "tier", "domains", "document"):
            setattr(focus, name, [v for v in value if isinstance(v, str)])
        else:
            setattr(focus, name, [_entity(v) for v in value if v is not None])
    # `customer` singular is what the first cut of the wire shape wrote; read forward so
    # a contact mid-conversation at deploy keeps the customer they already named.
    if not focus.customers and isinstance(raw.get("customer"), dict):
        focus.customers = [raw["customer"]]
    status = raw.get("status")
    focus.status = status if isinstance(status, str) else None
    window = raw.get("date_window")
    focus.date_window = window if isinstance(window, dict) else None
    extra = raw.get("extra")
    if isinstance(extra, dict):
        focus.extra = {
            k: [_entity(v) for v in value if v is not None]
            for k, value in extra.items()
            if isinstance(value, list)
        }
    return focus


def _entity(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {"raw": value, "canonical_code": value}
