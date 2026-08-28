"""Where a shortage could be covered from, instead of bought.

> "actually the use stock is use from BRW, not from BRW-IB"

The plan's "use stock" action was built on a wrong reading of what it means. A line's OWN
on-hand is already inside its net position - it is not a choice, it is arithmetic that has
already happened. The real question is whether some OTHER location is holding stock that could
cover this shortage, so the company does not buy what it already owns.

## Where cover may come from

The SITE POOL, and nowhere else (R18, captain 28 Aug). Stock in a project bin is already
claimed by an Order Inquiry, so offering it to a reorder promises units that cannot move -
the live tell was a plan row reading "Stock 34" off BRW-IB while the BRW pool held none.

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

from app.services.scm.reorder_policy import ALL_LOCATIONS, COVER_SCOPES, DEFAULT_COVER_SCOPE, OWN_POOL

__all__ = [
    "ALL_LOCATIONS",
    "COVER_SCOPES",
    "CoverProposal",
    "CoverSource",
    "DEFAULT_COVER_SCOPE",
    "OWN_POOL",
    "free_stock_by_product",
    "propose_cover",
    "sources_in_scope",
]


@dataclass(frozen=True)
class CoverSource:
    """One location that could give stock to another, and how much."""

    warehouse_id: str
    warehouse_code: str
    #: The location's own segment. `project` is never a source (R18) - the segment is
    #: carried so :func:`sources_in_scope` can say so rather than trusting its caller.
    segment: Optional[str]
    qty: float
    #: The pool this location belongs to - `COALESCE(pool_warehouse_id, id)`, so a location
    #: with no pool of its own IS its own pool. Carried on every source because the cover
    #: endpoint is keyed by PRODUCT while the scope question is per ROW: two rows of the same
    #: product can sit in different pools, so the filter cannot be applied once for all.
    pool_warehouse_id: Optional[str] = None


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
    WHERE r.run_id = CAST(:run_id AS uuid)
    GROUP BY r.product_id, r.warehouse_id
)
SELECT s.product_id::text                              AS product_id,
       s.warehouse_id::text                            AS warehouse_id,
       w.warehouse_code                                AS warehouse_code,
       w.segment                                       AS segment,
       COALESCE(w.pool_warehouse_id, w.id)::text       AS pool_warehouse_id,
       s.quantity_on_hand::numeric                     AS on_hand,
       COALESCE(d.demand, 0)::numeric                  AS demand
FROM stock s
JOIN warehouses w ON w.id = s.warehouse_id
LEFT JOIN plan_demand d
       ON d.product_id = s.product_id AND d.warehouse_id = s.warehouse_id
WHERE s.quantity_on_hand > 0
  AND w.counts_as_available
  -- SITE POOL ONLY (R18, captain 28 Aug). A project bin's stock is already claimed by an
  -- Order Inquiry, so offering it to a reorder promises the same units twice: the plan
  -- read "Stock 34" off BRW-IB while the BRW pool held none, and none of those 34 could
  -- move. `segment` is the test, never the code's hyphen suffix, and a location nobody
  -- has classified counts as pool - the same call `reorder_run_service._planning_rows`
  -- makes for the on-hand this cover is netted against.
  AND COALESCE(w.segment, 'dealer') <> 'project'
  -- The cast goes on the PARAMETER. `uuid = ANY(text[])` is 'operator does not exist',
  -- which is what the ::text-on-both-sides version was working around; casting the bound
  -- array instead satisfies the operator without casting the column.
  --
  -- Consistency, not a measured win. The list here is the run's whole product scope
  -- (2,581 ids against 13,039 stock rows on the prod copy), and at that width Postgres
  -- rightly prefers a sequential scan whichever side carries the cast. What this buys is
  -- that the cast is no longer the thing DECIDING that: the planner is free to use the
  -- index the day a caller passes a short list. The predicate that genuinely needed the
  -- index is `run_id` above, which selects 4,634 rows out of 396,601.
  AND s.product_id = ANY(CAST(:product_ids AS uuid[]))
"""


def free_stock_by_product(
    db: Session, run_id: str, product_ids: list[str]
) -> dict[str, list[CoverSource]]:
    """Free stock per product, per SITE POOL location, largest first (R18).

    Project bins never appear: their stock is spoken for by an Order Inquiry, so a reorder
    that covered from one would move units that are not there to move.
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
                pool_warehouse_id=r["pool_warehouse_id"],
            )
        )
    for sources in out.values():
        sources.sort(key=lambda s: (-s.qty, s.warehouse_code))
    return out


def sources_in_scope(
    free: list[CoverSource],
    cover_scope: Optional[str],
    line_pool_warehouse_id: Optional[str],
) -> list[CoverSource]:
    """The sources the policy actually allows this row to draw on.

    A PROJECT bin is dropped whatever the scope says (R18): it is not an option the policy
    widens or narrows, it is stock a reorder may never take. The read that builds the map
    already excludes it, and this states the rule where the offer is composed, so a caller
    holding an older payload cannot re-admit one.

    Under `own_pool` a source has to sit in the ROW's pool. A row whose own pool is unknown
    (a network row carries no warehouse) is NOT filtered to nothing: there is no pool to
    compare against, and scoping it would silently delete every option rather than narrow
    them. A source with no pool of its own IS its own pool, which is what
    `COALESCE(pool_warehouse_id, id)` means one layer down.

    An absent or unrecognised `cover_scope` reads as ``own_pool``, matching
    ``DEFAULT_COVER_SCOPE``. Only the explicit ``all_locations`` opens the whole network:
    testing for ``!= OWN_POOL`` failed OPEN, so a caller that omitted the argument offered
    every site rather than the one the policy allows.
    """
    pool_only = [s for s in free if (s.segment or "dealer") != "project"]
    if cover_scope == ALL_LOCATIONS or not line_pool_warehouse_id:
        return pool_only
    return [
        s for s in pool_only
        if (s.pool_warehouse_id or s.warehouse_id) == line_pool_warehouse_id
    ]


def propose_cover(
    shortage: float,
    line_warehouse_id: Optional[str],
    free: list[CoverSource],
    *,
    already_taken: Optional[dict[str, float]] = None,
    cover_scope: Optional[str] = None,
    line_pool_warehouse_id: Optional[str] = None,
) -> CoverProposal:
    """How much of `shortage` other SITE POOLS can cover, and from where.

    Biggest pile first, the code breaking a tie so two runs cannot disagree. There is no
    segment ranking any more: after R18 a project bin is not a lower-ranked option, it is
    not an option (`sources_in_scope` drops it), so nothing here crosses a boundary.

    `already_taken` is what earlier decisions in this same pass have consumed, keyed by
    warehouse. Without it two lines are each told the same units are free and the second
    decision quietly cannot be honoured.

    `cover_scope` is the global policy's answer to "may this row use another site's stock at
    all". `own_pool` narrows the offer to the row's own pool BEFORE anything else, so an
    out-of-scope location is never proposed, never ranked and never counted. It is also the
    default: absent or unrecognised reads as `own_pool`, never as the whole network. The row's
    own warehouse is still excluded either way: scope narrows the offer, it never re-admits
    stock that is already inside the net.

    No production caller: the allocation runs client-side because the free pool is shared and
    only the client knows what has been decided so far (see the module docstring). This
    function is the MIRROR-OF-RECORD for `scm/reorder/lib/coverPlan.ts` and is exercised by
    tests alone - when the two disagree, this one states the intended rule.
    """
    if shortage <= 0:
        return CoverProposal(cover_qty=0.0, buy_qty=0.0, sources=[])

    taken = already_taken or {}
    candidates: list[CoverSource] = []
    for s in sources_in_scope(free, cover_scope, line_pool_warehouse_id):
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
                pool_warehouse_id=s.pool_warehouse_id,
            )
        )

    candidates.sort(key=lambda s: (-s.qty, s.warehouse_code))

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
                pool_warehouse_id=s.pool_warehouse_id,
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
