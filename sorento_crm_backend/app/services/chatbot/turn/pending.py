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


def is_roster(kind: str) -> bool:
    """Does this pending stay alive after its own pick (contract 36)?

    Not a list lookup, because the list cannot be complete. `narrow.decide` mints the
    ask's kind as `f"{entity_kind}_pick"` / `f"{entity_kind}_ask"` straight off
    `chatbot_entity_kinds`, an OPERATOR-editable table: measured on the seeded rows,
    twelve kinds exist and only `product`, `customer`, `tier` and `attachment_type` carry
    a narrowing policy today, so the Chatbot Domains screen can mint `brand_pick`,
    `warehouse_pick` or `order_pick` the moment somebody sets one. Those read as "not a
    roster" against the nine literals and lost contract 36's sticky roster silently.

    The nine named kinds keep their own classification (`tier_pick`, `team_pick` and
    `company_pick` end in `_pick` and are one-off offers, not rosters); anything the
    narrower minted outside them is a candidate list, and a candidate list is a roster.
    """
    if kind in ROSTER_KINDS:
        return True
    if kind in PENDING_KINDS:
        return False
    return kind.endswith("_pick") or kind.endswith("_ask")


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

# The three offers the ESCALATION lane owns, both halves of them. `route()` sends the
# ASK to `escalate_offer` off this set, and `apply._answer_pending` sends the ANSWER
# back to the escalation lane off the same one - the arm that asks and the arm that
# answers must not be able to disagree about which questions are escalation questions.
# The other three offer kinds are BUSINESS questions (`tier_pick` is contract 15's price
# tier, `outstanding_scope` and `outstanding_detail` are contract 38 and 39): accepting
# one of those is a fetch, not a handover.
ESCALATION_OFFER_KINDS: frozenset[str] = frozenset({"team_pick", "member_offer", "company_pick"})


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
