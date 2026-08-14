"""Which promotions may be served as an answer, defined once for every surface.

The customer's question is "any promo for X?", and until now two surfaces
answered it with two different mechanisms: the resolver returned every promotion
containing the product, and the promotions list returned the active ones with a
blanket fall back to ALL inactive ones when nothing active matched. Neither knew
that the five kinds of promotion Sorento runs differ in what happens after the
end date, so the answer to the SRTWC286 question was the A3 flyer (live) and the
July WC promo that had just ended was never mentioned.

The rule this module holds:

1. **A live promotion always wins.** Every live row in the candidate set is served.
2. **Expired rows fall back per TYPE, not globally.** A type with no live row in
   the candidate set may contribute its latest expired row when the type's config
   allows it. A live A3 flyer therefore does not suppress an expired standard
   promo -- that suppression IS the bug.
3. **The type decides.** `show_expired` off (special) means nothing of that kind
   is ever served after its end date. The two bounds
   (`expired_valid_until_year_end`, `expired_max_age_days`) both apply when both
   are set.
4. **Latest only.** Ordered `end_date DESC, created_at DESC`, one row per type,
   plus an exact `end_date` tie, capped at 2. The customer asking "did I just
   miss something?" wants the thing that just ended, not a museum tour.
5. **An unclassified promotion follows the default type**, so legacy rows behave
   as the standard promotions they are.

"Candidate set" is always the population the caller's own filters produced -- the
promotions containing the product asked about, already access-filtered. Scoping
the per-type suppression globally would let an active PP promo for a different
product hide the expired PP promo for this one.

This module imports neither `marketing_service` nor `references`, so both can use
it without a cycle -- the same discipline `promotion_window` keeps.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Optional, Sequence

from sqlalchemy.orm import Session

from app.models.marketing import Promotion, PromotionType
from app.services import promotion_window

# One row per type, plus an exact end_date tie. Two campaigns of the same kind
# ending on the same day for the same audience are both "the thing that just
# ended"; a third would be history.
MAX_EXPIRED_PER_TYPE = 2

# Upper bound on how many candidate rows the policy will rank in Python. Well
# above any real candidate set (the whole table is ~29 rows); a cap that bites is
# logged, never silently truncated.
CANDIDATE_CAP = 500


@dataclass
class ServingVerdict:
    """What may be served, and which of it needs the expired-but-usable phrasing."""

    served_ids: set[str] = field(default_factory=set)
    expired_but_usable_ids: set[str] = field(default_factory=set)
    type_by_promotion: dict[str, Optional[PromotionType]] = field(default_factory=dict)
    truncated: bool = False

    def is_served(self, promotion_id) -> bool:
        return str(promotion_id) in self.served_ids

    def is_expired_but_usable(self, promotion_id) -> bool:
        return str(promotion_id) in self.expired_but_usable_ids


def _expired_row_allowed(promo_type: Optional[PromotionType], end_date: Optional[date], today: date) -> bool:
    """Whether an expired row of *promo_type* is still within that type's bounds."""
    if promo_type is None:
        # No types configured at all: keep today's behaviour rather than serving
        # nothing, which would silently empty every promo answer.
        return True
    if not promo_type.show_expired:
        return False
    if end_date is None:
        # A promotion with no end date is live by definition, so this is
        # unreachable through `evaluate`; guard anyway rather than pick a bound.
        return True
    if promo_type.expired_valid_until_year_end and end_date.year != today.year:
        return False
    max_age = promo_type.expired_max_age_days
    if max_age is not None and (today - end_date).days > int(max_age):
        return False
    return True


def evaluate(
    promotions: Sequence[Promotion],
    types_by_id: dict[str, PromotionType],
    default_type: Optional[PromotionType],
    today: date,
) -> ServingVerdict:
    """Apply the serving policy to a candidate set already in hand."""
    verdict = ServingVerdict()
    if not promotions:
        return verdict

    live: list[Promotion] = []
    expired: list[Promotion] = []
    for promo in promotions:
        promo_type = types_by_id.get(str(promo.promotion_type_id)) if promo.promotion_type_id else None
        if promo_type is None:
            promo_type = default_type
        verdict.type_by_promotion[str(promo.id)] = promo_type
        if promotion_window.is_live(promo.is_active, promo.start_date, promo.end_date, today):
            live.append(promo)
        else:
            expired.append(promo)

    for promo in live:
        verdict.served_ids.add(str(promo.id))

    # A type with a live row in this candidate set answers the question already.
    live_type_keys = {_type_key(verdict.type_by_promotion.get(str(p.id))) for p in live}

    by_type: dict[Optional[str], list[Promotion]] = {}
    for promo in expired:
        promo_type = verdict.type_by_promotion.get(str(promo.id))
        key = _type_key(promo_type)
        if key in live_type_keys:
            continue
        if not _expired_row_allowed(promo_type, promo.end_date, today):
            continue
        by_type.setdefault(key, []).append(promo)

    for rows in by_type.values():
        rows.sort(
            key=lambda p: (
                p.end_date or date.min,
                p.created_at or _MIN_CREATED,
            ),
            reverse=True,
        )
        newest_end = rows[0].end_date
        for promo in rows[:MAX_EXPIRED_PER_TYPE]:
            # Beyond the first row, only an exact end_date tie qualifies.
            if promo.end_date != newest_end:
                break
            verdict.served_ids.add(str(promo.id))
            verdict.expired_but_usable_ids.add(str(promo.id))

    return verdict


def _type_key(promo_type: Optional[PromotionType]) -> Optional[str]:
    return str(promo_type.id) if promo_type is not None else None


class _MinCreated:
    """Sorts below every datetime, so a NULL `created_at` never wins a tie."""

    def __lt__(self, other):  # pragma: no cover - trivial
        return True

    def __gt__(self, other):  # pragma: no cover - trivial
        return False

    def __eq__(self, other):  # pragma: no cover - trivial
        return isinstance(other, _MinCreated)

    def __hash__(self):  # pragma: no cover - trivial
        return hash("_MinCreated")


_MIN_CREATED = _MinCreated()


def load_types(db: Session) -> tuple[dict[str, PromotionType], Optional[PromotionType]]:
    """Every promotion type by id, plus the default one."""
    types = db.query(PromotionType).all()
    by_id = {str(t.id): t for t in types}
    default = next((t for t in types if t.is_default), None)
    return by_id, default


def evaluate_candidates(
    db: Session,
    candidate_ids: Iterable[str],
    today: date,
) -> ServingVerdict:
    """Serving verdict for a candidate set identified by id.

    Loads the promotions and the type table, then applies `evaluate`. Callers
    holding the rows already should call `evaluate` directly.
    """
    ids = [str(i) for i in dict.fromkeys(candidate_ids or [])]
    if not ids:
        return ServingVerdict()
    truncated = len(ids) > CANDIDATE_CAP
    if truncated:
        import logging

        logging.getLogger(__name__).warning(
            "promotion serving policy capped at %s of %s candidate rows",
            CANDIDATE_CAP,
            len(ids),
        )
        ids = ids[:CANDIDATE_CAP]
    promotions = db.query(Promotion).filter(Promotion.id.in_(ids)).all()
    types_by_id, default = load_types(db)
    verdict = evaluate(promotions, types_by_id, default, today)
    verdict.truncated = truncated
    return verdict
