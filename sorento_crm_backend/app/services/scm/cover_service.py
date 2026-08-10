"""Where a shortage could be covered from, instead of bought.

> "actually the use stock is use from BRW, not from BRW-IB"

The plan's "use stock" action was built on a wrong reading of what it means. A line's OWN
on-hand is already inside its net position - it is not a choice, it is arithmetic that has
already happened. The real question is whether some OTHER location is holding stock that could
cover this shortage, so the company does not buy what it already owns.

## What counts as free

Surplus, never on-hand. A location holding 231 against its own demand of 419 has nothing to
give: taking its stock would rob a location that is itself short and the engine would simply
recommend buying it again next week. So:

    free(location) = max(0, on_hand - that location's own demand)

## Why the demand cannot come from `scm.net_position_v`

That view reports `committed` from the order book alone. On the live run, DC1-BB shows
`committed = 0` and `net_position = +231` for MWC7624-RL-S10, while the PLAN for the same
location says it needs 419 and is short 188 - because the plan also counts the uploaded
outstanding-sales feed. Reading the view would have offered those 231 units as free to cover
another location, which is the exact error this module exists to prevent.

So demand is taken from the run's own recommendations, which is the only figure that agrees
with what the buyer is looking at. A location holding stock with NO demand produces no
recommendation at all (BRW-BB's 5 units on that same SKU), so absence of a row means zero
demand, not absence of stock.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class CoverSource:
    """One location that could give stock to another, and how much."""

    warehouse_id: str
    warehouse_code: str
    segment: Optional[str]
    qty: float
    #: True when the source sits in a different segment from the line being covered. Dealer
    #: stock covering project demand is a real option and a real decision, so it is offered
    #: and flagged rather than mixed in silently.
    cross_segment: bool


@dataclass(frozen=True)
class CoverProposal:
    """What to do about one short line: cover this much, buy the rest."""

    cover_qty: float
    buy_qty: float
    sources: list[CoverSource]

    @property
    def is_split(self) -> bool:
        return self.cover_qty > 0 and self.buy_qty > 0


# A location's stock and the demand the PLAN placed on it, per product.
_POSITIONS_SQL = """
WITH plan_demand AS (
    SELECT r.product_id,
           r.warehouse_id,
           MAX(COALESCE((r.inputs ->> 'committed')::numeric, 0)) AS demand,  -- the API calls this outstanding_sales
           MAX(COALESCE((r.inputs ->> 'on_hand')::numeric, 0))           AS plan_on_hand
    FROM scm.reorder_recommendation r
    WHERE r.run_id::text = :run_id
    GROUP BY r.product_id, r.warehouse_id
)
SELECT s.product_id::text                         AS product_id,
       s.warehouse_id::text                       AS warehouse_id,
       w.warehouse_code                           AS warehouse_code,
       w.segment                                  AS segment,
       s.quantity_on_hand::numeric                AS on_hand,
       COALESCE(d.demand, 0)::numeric             AS demand
FROM stock s
JOIN warehouses w ON w.id = s.warehouse_id
LEFT JOIN plan_demand d
       ON d.product_id = s.product_id AND d.warehouse_id = s.warehouse_id
WHERE s.quantity_on_hand > 0
  AND w.counts_as_available
  -- ::text on BOTH sides: a bare uuid = ANY(text[]) is 'operator does not exist'
  AND s.product_id::text = ANY(:product_ids)
"""


def free_stock_by_product(
    db: Session, run_id: str, product_ids: list[str]
) -> dict[str, list[CoverSource]]:
    """Free stock per product, per location, largest first.

    `cross_segment` is left False here: it depends on the line being covered, which this
    function does not know. :func:`propose_cover` stamps it.
    """
    if not product_ids:
        return {}
    rows = db.execute(
        text(_POSITIONS_SQL),
        {"run_id": run_id, "product_ids": [str(p) for p in product_ids]},
    ).mappings().all()

    out: dict[str, list[CoverSource]] = {}
    for r in rows:
        free = float(r["on_hand"]) - float(r["demand"])
        if free <= 0:
            continue
        out.setdefault(r["product_id"], []).append(
            CoverSource(
                warehouse_id=r["warehouse_id"],
                warehouse_code=r["warehouse_code"],
                segment=r["segment"],
                qty=free,
                cross_segment=False,
            )
        )
    for sources in out.values():
        sources.sort(key=lambda s: (-s.qty, s.warehouse_code))
    return out


def propose_cover(
    shortage: float,
    line_warehouse_id: Optional[str],
    line_segment: Optional[str],
    free: list[CoverSource],
    *,
    already_taken: Optional[dict[str, float]] = None,
) -> CoverProposal:
    """How much of `shortage` other locations can cover, and from where.

    Sources in the SAME segment are offered first: moving project stock to serve dealer demand
    (or the reverse) crosses a boundary the business tracks deliberately, so it should be the
    fallback rather than the first answer, and it is always marked.

    `already_taken` is what earlier decisions in this same pass have consumed, keyed by
    warehouse. Without it two lines are each told the same units are free and the second
    decision quietly cannot be honoured.
    """
    if shortage <= 0:
        return CoverProposal(cover_qty=0.0, buy_qty=0.0, sources=[])

    taken = already_taken or {}
    candidates: list[CoverSource] = []
    for s in free:
        if line_warehouse_id is not None and s.warehouse_id == line_warehouse_id:
            # Its own stock is already inside the net. Offering it back would double count.
            continue
        remaining = s.qty - taken.get(s.warehouse_id, 0.0)
        if remaining <= 0:
            continue
        candidates.append(
            CoverSource(
                warehouse_id=s.warehouse_id,
                warehouse_code=s.warehouse_code,
                segment=s.segment,
                qty=remaining,
                cross_segment=bool(line_segment and s.segment and s.segment != line_segment),
            )
        )

    candidates.sort(key=lambda s: (s.cross_segment, -s.qty, s.warehouse_code))

    used: list[CoverSource] = []
    covered = 0.0
    for s in candidates:
        if covered >= shortage:
            break
        take = min(s.qty, shortage - covered)
        used.append(
            CoverSource(
                warehouse_id=s.warehouse_id,
                warehouse_code=s.warehouse_code,
                segment=s.segment,
                qty=take,
                cross_segment=s.cross_segment,
            )
        )
        covered += take

    return CoverProposal(
        cover_qty=covered,
        # The remainder is bought. Neither half is rounded away: a shortage that can be
        # half covered is a split, not a choice between two whole answers.
        buy_qty=max(0.0, shortage - covered),
        sources=used,
    )
