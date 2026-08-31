"""One way to turn a customer's product code into products.

There used to be two, and they disagreed. `product_attachments` treated a code as
a SUBSTRING and returned every match; `promotions` did an EXACT match with a
`+`-split fallback. So the same code read off the same flyer could link an
attachment and fail to create a promotion, and nothing said why. That divergence
predates product sets and is a defect on its own.

The tiers, in order, and the order is the design:

1. **exact** product code. A real product always wins its own code.
2. **product set** code, expanded to its members. This is the gap sets exist to
   fill: `SRTWC8608-RL` is printed on a flyer and no product carries it.
3. **`+` split**, each part matched exactly. Preserves what promotions did.
4. **substring**, every match returned. Preserves what attachments did, and its
   reason: "WC7601" names MWC7601-RL-S12, IBWC7601-RL-S10 and everything else
   carrying it, and taking one arbitrarily left the rest silently uncovered.
5. **prefix**, last resort: a code that is really a FAMILY description, e.g. a
   certificate reading "SRTBV - BRASS BALL VALVE" names every `SRTBV...`
   product, not one product literally coded that way. Only reached when tiers
   1-4 all miss. Head-only (the text before the first ` - `, or the first
   whitespace token), a minimum head length and a fan-out cap keep this from
   matching generic description words or an unusably broad family. See
   `PLAN-shared-brand-attachments.md` S1 for the measured guard rails.

Set expansion sits ABOVE substring on purpose. `SRTWC8608-RL` is a substring of
`SRTWC8608-RL-200`, so a substring-first resolver would answer a set code with
one unrelated product and quietly drop the three the customer meant.

**Company scope comes from the session, not from an argument.** Every query here
is ORM, so `do_orm_execute` (`app/services/company_scope.py`) injects the caller's
scope. The attachment path pins the session to the attachment's company before
calling, and that is what stops one company's set resolving another's members.
A raw `text()` query would bypass the listener entirely.

UAC group F. Plan: `documentation/plans/master-data/PLAN-product-sets.md` section 5.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.product_set import ProductSet, ProductSetMember

#: How a match was reached. Carried so a caller can explain itself, and so the
#: fan-out can be told apart from a link a person made by hand.
VIA_EXACT = "exact"
VIA_PRODUCT_SET = "product_set"
VIA_PLUS_SPLIT = "plus_split"
VIA_SUBSTRING = "substring"
VIA_PREFIX = "prefix"

#: Tier 5 guard rails, measured against the products table (23,063 rows,
#: `PLAN-shared-brand-attachments.md` S1). A head shorter than this matches too
#: much to be useful ("SRT" alone answers 9,655 products); a fan-out over the
#: cap is refused outright rather than returned as a useless partial list.
PREFIX_MIN_HEAD = 4
PREFIX_MAX_FANOUT = 200


@dataclass(frozen=True)
class CodeMatch:
    """One product the caller's code resolved to."""

    requested_code: str
    product: Product
    via: str
    #: Set to the set's id when this product arrived through a set expansion.
    #: NULL means a person or an exact code made this link.
    product_set_id: Optional[str] = None


@dataclass
class ResolvedCodes:
    matches: list[CodeMatch] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)

    @property
    def products_by_code(self) -> dict[str, Product]:
        """`{product_code: Product}`, for callers that index by code."""
        return {
            (m.product.product_code or "").strip(): m.product for m in self.matches
        }

    def codes_for(self, requested_code: str) -> list[str]:
        """The concrete product codes one requested code resolved to."""
        return [
            (m.product.product_code or "").strip()
            for m in self.matches
            if m.requested_code == requested_code
        ]

    def product_set_id_for(self, product_code: str) -> Optional[str]:
        """The set that put this product here, or None."""
        for m in self.matches:
            if (m.product.product_code or "").strip() == product_code:
                return m.product_set_id
        return None


def _normalize(value: Optional[str]) -> str:
    """Spaces out, case folded. Matches what the attachment path already did."""
    return (value or "").replace(" ", "").strip().lower()


def _norm_col(column):
    return func.lower(func.replace(column, " ", ""))


def _plus_parts(code: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"\s*\+\s*", code) if p and p.strip()]
    return parts if len(parts) > 1 else []


def resolve_codes_to_products(
    db: Session, codes: Iterable[Optional[str]]
) -> ResolvedCodes:
    """Resolve each code through the tiers above. Unmatched codes are REPORTED.

    A code that names nothing comes back in ``unmatched`` rather than being
    dropped: "your code matched nothing" has to reach the customer, because a
    silent zero is the exact failure this feature exists to remove.
    """
    result = ResolvedCodes()
    seen: set[str] = set()

    for raw in codes:
        code = (raw or "").strip()
        if not code:
            continue
        normalized = _normalize(code)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)

        matches = (
            _exact(db, code, normalized)
            or _via_product_set(db, code, normalized)
            or _via_plus_split(db, code)
            or _substring(db, code, normalized)
            or _via_prefix(db, code, normalized)
        )
        if matches:
            result.matches.extend(matches)
        else:
            result.unmatched.append(code)

    return result


def _exact(db: Session, code: str, normalized: str) -> list[CodeMatch]:
    rows = (
        db.query(Product)
        .filter(_norm_col(Product.product_code) == normalized)
        .order_by(Product.product_code)
        .all()
    )
    return [CodeMatch(requested_code=code, product=row, via=VIA_EXACT) for row in rows]


def _via_product_set(db: Session, code: str, normalized: str) -> list[CodeMatch]:
    """A set code answers with its members, each stamped with the set's id.

    Company scope is applied by the session listener: ``ProductSet`` carries
    ``CompanyScopedMixin``, so another company's set is invisible here and its
    members are never reached. ``ProductSetMember`` is deliberately unscoped and
    is reached only THROUGH its scoped parent, the way ``certificate_products``
    is reached through ``Certificate``.
    """
    product_set = (
        db.query(ProductSet)
        .filter(_norm_col(ProductSet.set_code) == normalized)
        .first()
    )
    if product_set is None:
        return []

    members = (
        db.query(ProductSetMember)
        .filter(ProductSetMember.product_set_id == product_set.id)
        .order_by(ProductSetMember.sort_order)
        .all()
    )
    return [
        CodeMatch(
            requested_code=code,
            product=member.product,
            via=VIA_PRODUCT_SET,
            product_set_id=product_set.id,
        )
        for member in members
        if member.product is not None
    ]


def _via_plus_split(db: Session, code: str) -> list[CodeMatch]:
    """`A + B` names two products. Each part is matched exactly, never fuzzily."""
    out: list[CodeMatch] = []
    for part in _plus_parts(code):
        for match in _exact(db, code, _normalize(part)):
            out.append(
                CodeMatch(
                    requested_code=code, product=match.product, via=VIA_PLUS_SPLIT
                )
            )
    return out


def _substring(db: Session, code: str, normalized: str) -> list[CodeMatch]:
    """Every product carrying the code, because taking one arbitrarily hid the rest."""
    rows = (
        db.query(Product)
        .filter(_norm_col(Product.product_code).like(f"%{normalized}%"))
        .order_by(Product.product_code)
        .all()
    )
    return [
        CodeMatch(requested_code=code, product=row, via=VIA_SUBSTRING) for row in rows
    ]


_DASH_SPLIT_RE = re.compile(r"\s+-\s+")


def _prefix_head(code: str) -> str:
    """The FAMILY portion of a code: text left of the first ` - `, else the
    first whitespace-delimited token. Empty when there is nothing to split."""
    dash_parts = _DASH_SPLIT_RE.split(code, maxsplit=1)
    if len(dash_parts) > 1 and dash_parts[0].strip():
        return dash_parts[0].strip()
    tokens = code.split()
    return tokens[0] if tokens else ""


def _via_prefix(db: Session, code: str, normalized: str) -> list[CodeMatch]:
    """Last resort: the code names a family by its head, not a real product.

    Only reached when tiers 1-4 all miss. A single-token code (no ` - `, no
    whitespace to split on) is skipped: its head IS the whole code, and that
    was already tried as `exact` and `substring` above.
    """
    head = _prefix_head(code)
    head_normalized = _normalize(head)
    if not head_normalized or head_normalized == normalized:
        return []
    if len(head_normalized) < PREFIX_MIN_HEAD:
        return []

    rows = (
        db.query(Product)
        .filter(_norm_col(Product.product_code).like(f"{head_normalized}%"))
        .order_by(Product.product_code)
        .limit(PREFIX_MAX_FANOUT + 1)
        .all()
    )
    if len(rows) > PREFIX_MAX_FANOUT:
        # More hits than a family can plausibly be: refuse rather than link a
        # useless partial subset ("SRT" alone answers 9,655 products).
        return []
    return [CodeMatch(requested_code=code, product=row, via=VIA_PREFIX) for row in rows]
