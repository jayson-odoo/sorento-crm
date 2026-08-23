"""What a product set costs.

The price is DERIVED, never stored. Sorento's catalogue parks the whole set's
list price on one member - `SRTWCX8608-RL` the pedestal reads 1180.00 while
`SRTWCY8608` the cistern reads 0.00 - so the set price is a sum over whichever
members are ticked, not a sum over all of them and not a number typed twice.

Deriving it at read time is the point: a member's price changes and the set
follows with no backfill and no second source of truth to drift.

An absent price is not zero. A set with nothing ticked, or with no members yet,
returns `None` and a reason. The dealer-kit pricing work already paid for this
lesson - a list price of zero is missing data, not a free product - and a set
mid-authoring that claims "RM 0.00" is worse than one that says it has no basis.

UAC group D. Plan: `documentation/plans/master-data/PLAN-product-sets.md`.

Not to be confused with `product_predicate_service.py`, which filters products by
spec predicate for the chatbot's backward search. That module used to hold this
name.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

# Reasons a set has no computable price. Returned rather than raised: "this set
# has no price basis yet" is an ordinary state during authoring, not an error.
NO_MEMBERS = "no_members"
NO_MEMBER_CONTRIBUTES = "no_member_contributes"


@dataclass(frozen=True)
class SetPrice:
    """Both figures, always.

    A dataclass rather than a dict so a field cannot be quietly lost on the way
    out - FastAPI's ``response_model`` drops anything it was not told about, and
    an override that vanishes between the service and the wire looks exactly
    like an override nobody set.
    """

    computed: Optional[Decimal]
    override: Optional[Decimal]
    reason: Optional[str] = None

    @property
    def is_overridden(self) -> bool:
        return self.override is not None

    @property
    def resolved(self) -> Optional[Decimal]:
        """What to show. The override when set, otherwise the computed figure."""
        return self.override if self.override is not None else self.computed

    def as_dict(self) -> dict[str, Any]:
        return {
            "computed": self.computed,
            "override": self.override,
            "resolved": self.resolved,
            "is_overridden": self.is_overridden,
            "reason": self.reason,
        }


def resolve_set_price(product_set) -> SetPrice:
    """``SUM(member.list_price * quantity)`` over the ticked members.

    Pure over an already-loaded set: no session, no queries, so the rule is
    table-testable and cannot accidentally depend on request scope.

    The override is reported even when the computed figure is absent. A person
    who typed a price for a set with no basis should see their own number, not
    have it swallowed because the derivation had nothing to work with.
    """
    override = _as_decimal(getattr(product_set, "list_price_override", None))
    members = list(getattr(product_set, "members", None) or [])

    if not members:
        return SetPrice(computed=None, override=override, reason=NO_MEMBERS)

    contributing = [m for m in members if getattr(m, "contributes_to_price", False)]
    if not contributing:
        return SetPrice(computed=None, override=override, reason=NO_MEMBER_CONTRIBUTES)

    computed = Decimal("0")
    for member in contributing:
        price = _as_decimal(getattr(getattr(member, "product", None), "list_price", None))
        quantity = _as_decimal(getattr(member, "quantity", None))
        # A missing member price contributes nothing rather than blowing up the
        # whole set: one unpriced part should not make the other two unanswerable.
        computed += (price or Decimal("0")) * (quantity if quantity is not None else Decimal("1"))

    return SetPrice(computed=computed.quantize(Decimal("0.01")), override=override)


def _as_decimal(value) -> Optional[Decimal]:
    if value is None:
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))
