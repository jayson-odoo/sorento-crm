"""Fulfilment Priority: one policy, used at both moments it applies.

AC-H5 says the ranking that decides what goes on a container and the ranking that decides which
purchase-order line a shipment draws down are the SAME policy, and that two policies for the two
moments is a defect. That is easy to say and easy to lose: the Loading Plan grew its factor
assembly privately, and the allocation suggestion would have grown its own beside it. Two
implementations agreeing today is not the same as one implementation, and the day they disagree
is the day a planner is told two different things about the same purchase order.

So the assembly lives here, and both callers import it. The generic scorer (`rank_score`,
`Factor`) stays in `cash_ranking`; this module is the SCM-specific part - which factors exist,
where their values come from, and how a purchase order's demand class is resolved.

The four factors:

  * `po_document_sequence` - the order the buyer already reads off the list. Sequence, not date:
    two orders raised the same day still have an order.
  * `demand_class`        - project versus dealer, resolved through the SO<->PO claim.
  * `need_by_date`        - sooner is higher.
  * `document_age`        - older document is higher, which is the same helper read the other way.

Every factor degrades gracefully: a value we do not have is ABSENT, not zero. `rank_score`
divides by the weight of the factors actually present, so an absent factor lowers nobody's score
- it just stops being part of the comparison. Demand is the one place where "nothing" is a real
value rather than a gap: no claimed sales order behind a purchase order is a demand of 0.0 and
PRESENT, because a purchase order owed to a customer has to be able to outrank one owed to
nobody. Only a resolved class the policy does not weight is absent (see `demand_value`).
"""
from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.scm import PriorityPolicy
from app.services.scm.cash_ranking import Factor

#: The factor keys a policy may weight. Adding a fifth is a row in `scm.priority_policy.factors`
#: plus a value here; it is never a schema change (AC-H6 applies the same rule to demand classes).
FACTOR_KEYS = ("po_document_sequence", "demand_class", "need_by_date", "document_age")

#: What a policy-less database ranks by. Sequence only: with no policy row the tenant has said
#: nothing about what demand is worth, so the fallback ranks by the order the buyer already
#: reads off the list rather than inventing a weighting.
DEFAULT_WEIGHTS = {"po_document_sequence": 1.0}

#: What migration 374 seeds as the active policy, and what a fresh install seeds directly (311).
#: Here so tests and the PR can quote one source. With demand at 3.0 against sequence at 1.0 the
#: score bands do not overlap: project [0.75, 1.0], retail [0.30, 0.55], nothing owed [0, 0.25].
#: So a line owed to a customer always outranks one owed to nobody, and document sequence orders
#: the lines inside each band. The migrations keep the literals rather than importing this, so
#: they stay standalone; changing one means changing both.
SEEDED_WEIGHTS = {
    "po_document_sequence": 1.0,
    "demand_class": 3.0,
    "need_by_date": 0.0,
    "document_age": 0.0,
}

#: What each resolved demand class is worth, seeded alongside `SEEDED_WEIGHTS`.
SEEDED_CLASS_WEIGHTS = {"project": 1.0, "retail": 0.4}


def active_policy(db: Session) -> Optional[PriorityPolicy]:
    """The one active policy, or None. A partial unique index makes "one" true at the DB level."""
    return (
        db.query(PriorityPolicy)
        .filter(PriorityPolicy.is_active.is_(True))
        .order_by(PriorityPolicy.created_at)
        .first()
    )


def policy_weights(policy: Optional[PriorityPolicy]) -> tuple[dict, dict]:
    """`(factor weights, demand-class weights)` for a policy, or the documented default."""
    if policy is None:
        return dict(DEFAULT_WEIGHTS), {}
    return dict(policy.factors or {}), dict(policy.demand_class_weights or {})


def demand_class_by_po(db: Session, po_numbers: set[str]) -> dict[str, str]:
    """The demand class of the sales orders each purchase order is feeding.

    Through `scm.order_link_claim`, which is where the SO<->PO pairing lives. A purchase order
    nobody has claimed against is simply missing from the result; `demand_value` turns that into
    a demand of 0.0, because nothing owed is a value and not a gap.
    """
    if not po_numbers:
        return {}
    from app.services.company_scope_sql import company_sql_predicate

    predicate, params = company_sql_predicate(db, "c.company_id", param_prefix="p")
    rows = db.execute(
        text(
            f"""
            SELECT c.po_number, so.demand_class, count(*) AS n
              FROM scm.order_link_claim c
              JOIN sales_orders so ON so.so_number = c.so_number
             WHERE c.po_number = ANY(:nums)
               AND so.demand_class IS NOT NULL
               AND {predicate or 'true'}
             GROUP BY c.po_number, so.demand_class
             ORDER BY c.po_number, n DESC
            """
        ),
        {"nums": list(po_numbers), **params},
    ).mappings().all()
    out: dict[str, str] = {}
    for r in rows:
        out.setdefault(str(r["po_number"]), str(r["demand_class"]))
    return out


def demand_value(
    classes: dict[str, str], class_weights: dict[str, float], po_number: str
) -> Optional[float]:
    """The demand factor value for one purchase order.

    No claimed sales order behind the purchase order is a demand of NOTHING owed, so it is
    0.0 and PRESENT: that is what lets a purchase order feeding a customer outrank one
    feeding no one. A resolved class the policy does not weight is still absent, because
    then the policy has not said what it is worth.
    """
    klass = classes.get(po_number)
    if klass is None:
        return 0.0
    w = class_weights.get(klass)
    return float(w) if w is not None else None


def sequence_values(candidates: Sequence[dict]) -> dict[str, float]:
    """1.0 for the oldest purchase-order document, sliding to 0.0 for the newest.

    Keyed by `po_number`. Ties share a value, so a same-day pair is not split by an accident of
    row order.
    """
    ordered: list[str] = []
    for c in candidates:
        key = str(c.get("po_number") or "")
        if key not in ordered:
            ordered.append(key)
    n = len(ordered)
    if n <= 1:
        return {k: 1.0 for k in ordered}
    return {k: 1.0 - (i / (n - 1)) for i, k in enumerate(ordered)}


def date_values(candidates: Sequence[dict], key: str) -> dict[str, Optional[float]]:
    """Sooner is higher, over the span present in this candidate set. Keyed by `po_line_id`."""
    dates = [c[key] for c in candidates if c.get(key)]
    if not dates:
        return {}
    lo, hi = min(dates), max(dates)
    span = (hi - lo).days or 1
    return {
        str(c["po_line_id"]): (1.0 - ((c[key] - lo).days / span)) if c.get(key) else None
        for c in candidates
    }


def factors_for(
    weights: dict,
    *,
    sequence: Optional[float],
    demand_weight: Optional[float],
    need_by: Optional[float],
    age: Optional[float],
) -> list[Factor]:
    """The four factors, each carrying its weight and whether it had a value at all."""
    values = {
        "po_document_sequence": sequence,
        "demand_class": demand_weight,
        "need_by_date": need_by,
        "document_age": age,
    }
    return [
        Factor(key=k, weight=float(weights.get(k, 0.0) or 0.0), value=v, present=v is not None)
        for k, v in values.items()
    ]


def factors_for_candidates(db: Session, candidates: Sequence[dict]) -> dict[str, list[Factor]]:
    """Factors per `po_line_id` for a set of candidate purchase-order lines.

    The whole assembly in one call, so a caller that only wants "rank these PO lines by the
    active policy" cannot accidentally build three quarters of it. Candidates are dicts carrying
    `po_line_id`, `po_number`, `expected_date` and `po_date` - the shape both the Loading Plan
    and the allocation suggestion already work in.
    """
    weights, class_weights = policy_weights(active_policy(db))
    classes = demand_class_by_po(
        db, {str(c["po_number"]) for c in candidates if c.get("po_number")}
    )
    sequence = sequence_values(candidates)
    need_by = date_values(candidates, "expected_date")
    ages = date_values(candidates, "po_date")

    out: dict[str, list[Factor]] = {}
    for c in candidates:
        line_id = str(c["po_line_id"])
        out[line_id] = factors_for(
            weights,
            sequence=sequence.get(str(c.get("po_number") or "")),
            demand_weight=demand_value(classes, class_weights, str(c.get("po_number") or "")),
            need_by=need_by.get(line_id),
            age=ages.get(line_id),
        )
    return out
