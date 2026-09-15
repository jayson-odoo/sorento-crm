# Pending: one object, one constructor (PLAN-chatbot-turn-rearch.md "APPLY contract",
# AC-1521). Every `Pending(` call site lives here; every resolver lives in apply.py.
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# The lane's eight offer/roster kinds plus the reconciliation-only ninth.
PENDING_KINDS: tuple[str, ...] = (
    "product_pick",
    "customer_pick",
    "tier_pick",
    "team_pick",
    "company_pick",
    "member_offer",
    "outstanding_scope",
    "outstanding_detail",
    "kind_pick",
)

# Stay alive, tracked by `answered_positions`, after their own pick.
ROSTER_KINDS: frozenset[str] = frozenset({"product_pick", "customer_pick", "kind_pick"})


@dataclass(frozen=True)
class Pending:
    kind: str
    expects: str | None
    options: list[dict[str, Any]]
    team: str | None
    payload: dict[str, Any]
    asked_at_turn: int | None

    @property
    def answered_positions(self) -> list[int]:
        return list(self.payload.get("answered_positions") or [])


def ask(
    kind: str,
    options: list[dict[str, Any]],
    *,
    team: str | None = None,
    asked_at_turn: int | None = None,
    expects: str | None = None,
    payload: dict[str, Any] | None = None,
) -> Pending:
    return Pending(
        kind=kind,
        expects=expects,
        options=options,
        team=team,
        payload=dict(payload or {}),
        asked_at_turn=asked_at_turn,
    )


def with_answered_positions(pending: Pending, positions: list[int]) -> Pending:
    # A roster kind's own re-ask: the SAME pending, carrying which positions this
    # turn's pick answered, layered onto whatever was already answered before.
    merged = sorted(set(pending.answered_positions) | set(positions))
    payload = dict(pending.payload)
    payload["answered_positions"] = merged
    return Pending(
        kind=pending.kind,
        expects=pending.expects,
        options=pending.options,
        team=pending.team,
        payload=payload,
        asked_at_turn=pending.asked_at_turn,
    )


# Offer kinds clear when they are answered; the roster kinds above stay alive.
OFFER_KINDS: frozenset[str] = frozenset(PENDING_KINDS) - ROSTER_KINDS


def to_wire(pending: Pending | None) -> dict[str, Any] | None:
    """`session_vars.open_question` - the ONE open question, as stored (AC-1504)."""
    if pending is None:
        return None
    return {
        "kind": pending.kind,
        "expects": pending.expects,
        "options": list(pending.options),
        "team": pending.team,
        "asked_at_turn": pending.asked_at_turn,
        "payload": dict(pending.payload),
    }


def from_wire(raw: Any) -> Pending | None:
    """The inverse. An `open_question` written by an older build carries only `kind` and
    `options`; the missing members read as "not stated", never as a failed turn."""
    if not isinstance(raw, dict) or not raw.get("kind"):
        return None
    options = raw.get("options")
    payload = raw.get("payload")
    return Pending(
        kind=str(raw["kind"]),
        expects=raw.get("expects"),
        options=[o for o in options if isinstance(o, dict)] if isinstance(options, list) else [],
        team=raw.get("team"),
        payload=dict(payload) if isinstance(payload, dict) else {},
        asked_at_turn=raw.get("asked_at_turn"),
    )
