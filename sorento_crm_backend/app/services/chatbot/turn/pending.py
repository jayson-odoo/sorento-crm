# Pending: one object, one constructor (PLAN-chatbot-turn-rearch.md "APPLY contract",
# AC-1521). Every `Pending(` call site lives here; every resolver lives in apply.py.
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

# The lane's eight offer/roster kinds plus the reconciliation-only ninth, and the sales
# report's own detail offer (PLAN-chatbot-sales-report.md S4 wiring point 7): a KIND is
# added, an arm is not - every site that used to test the literal `"outstanding_detail"`
# tests membership in `contracts.DETAIL_OFFER_KINDS` instead, so the two share one
# mechanism rather than one being a copy of the other.
PENDING_KINDS: tuple[str, ...] = (
    "product_pick",
    "customer_pick",
    "tier_pick",
    "team_pick",
    "company_pick",
    "member_offer",
    "outstanding_scope",
    "outstanding_detail",
    "sales_report_detail",
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


#: AC-816 rule 1: how many turns an unanswered escalation offer stays on the customer's
#: screen. Three, the did-you-mean offer's own lifetime, because "unanswered" is not a
#: licence to live forever - an offer the customer simply ignored used to be re-armed on
#: every later turn, so a bare "yes" about something else three or twenty turns on still
#: read as an escalation confirmation and assigned a human to a conversation nobody had
#: asked to escalate. A constant, not a setting: `system_settings` carries no chatbot TTL
#: column today (checked), and one preference does not need a table.
OFFER_TTL = 3


def tick(pending: Pending | None) -> Pending | None:
    """One more turn has begun: the open offer's clock ticks, and at zero it is gone.

    Read at the LOAD seam (`turn_runtime.load_state`), so an expired offer is simply not
    there - APPLY, the router, the parser's option list and the tail all agree about it
    without any of them having to know the rule. The remaining count rides on the marker
    itself (AC-816: "rather than a session key of its own, because the marker is already
    what says the offer is open and a second key could disagree with it"), and the write
    is automatic: the tail stores the pending the turn CARRIED, which is this ticked one.
    A marker with no count - written by n8n, or before this rule shipped - reads as open
    and starts its clock on this turn.

    Only the three ESCALATION offers have a clock. The business questions do not: R22
    ruled `outstanding_scope` / `outstanding_detail` sticky on purpose ("a TTL would
    close it behind a customer who is still reading it"), and the roster kinds are
    contract 36's sticky roster by definition. What expires is the offer whose stale
    acceptance hands a human a conversation nobody asked to escalate, and that is
    `_answer_offer`'s own set.

    A turn that re-prints the question or narrows it still SPENDS one turn against the
    clock - or the narrow arm becomes the unbounded carry again (AC-816 rule 1's own
    words).
    """
    if pending is None or pending.kind not in ESCALATION_OFFER_KINDS:
        return pending
    carried = pending.payload.get("ttl")
    remaining = (carried if isinstance(carried, int) else OFFER_TTL) - 1
    if remaining <= 0:
        return None
    payload = dict(pending.payload)
    payload["ttl"] = remaining
    return replace(pending, payload=payload)


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
