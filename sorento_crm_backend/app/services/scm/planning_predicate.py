"""ONE spelling of "this bin takes part in fulfilment planning", for every reader of it.

**The rule.** A warehouse is IN fulfilment planning when it is ACTIVE and its
`fulfilment_planning` flag is true. Nothing else: not the code's suffix, not the segment,
not `counts_as_available`. Migration 443 seeds the flag from the client's own group
convention once, and from then on it is configuration an admin edits on the Warehouses
screen - deriving it at runtime would bake one client's naming into the engine, which is
the mistake `pool_warehouse_id` and `segment` were both stored to avoid.

**What being OFF means.** Everything (R17). A bin that is off contributes no on hand, no
incoming and no sales-order line to the ladder, the fulfilment board, the donor lists or
the Stock Debt view. That is stronger than `counts_as_available`, where the stock is merely
not sellable while the location's demand still counts against the group; here the location
is not part of the question at all.

**What being OFF does NOT change: what a location HOLDS.** `free_stock_by_location`,
`stock_levels_by_location` and `held_stock_by_location` are the public stock seams the
board's stock detail and the location-stock screen print, and they answer for every ACTIVE
bin. A bin nobody plans against still holds its stock, and 1,928 on hand printed beside 0
free reads as a defect rather than as a policy. The narrowing belongs to what a proposal
may DRAW (`project_supply_service._drawable_free_stock`) and to what the ownership groups
NET, never to the figures a screen states.

**Why one module.** The same test is applied by `project_supply_service`
(`_planning_warehouses`, the group siblings, the cross-group donor walk), by the ownership
group index it hands `group_netting`, and by the board (its group index and its demand
rows). Four files agreeing by hand is a rule that holds until one of them is edited - the
exact reasoning `pool_predicate.py` records for the site-pool test, and it is this module's
whole justification.

**A line at a dealer-segment bin is plannable although the bin is OFF (DEALER-PLANNING, owner
1 Nov 2026).** Dealer sales orders sit at a site pool such as BRW. Refusing them told a planner
to fix a location that was already right, and ticking the flag instead would add the pool to the
planning, netting and Stock Debt reads of every project line. So the VERDICT
(`outside_fulfilment_planning`) exempts the dealer segment, using the one spelling
`pool_predicate.is_site_pool`, and the flag and `in_fulfilment_planning` do not move: what a line
may be planned AT and what the engine reads as planning supply are two questions.

**Which ORDERS are admitted at all (DEALER-PLANNING PR 2, owner 1 Nov 2026).** Project class as
ever, or an order that weighs as retail (`demand_class.planning_class`, so `other` too) with at
least one line at an active dealer-segment bin. One predicate, `admitted_to_planning`, so the
board, line drafts, adoption and the worklist cannot disagree about it. It is a HEADER test: every
line of an admitted order is on the board, so its line numbers stay the ones a draft key names,
and a retail line at a project bin is on screen with the verdict rather than missing
(`outside_fulfilment_planning`). `adopt_for_migration` and the OI import stay project only, on
purpose: their population is history measured and accepted as project.

**Site pools are OFF, and that is not a bug.** A pool is reached through
`pool_warehouse_id`, never as an ownership group, so the pool rung reads its own set
(`project_supply_service._site_pool_warehouses`) and is unaffected by this predicate.
Anything that nets the two together has to union the two sets explicitly, which is what
`_pile_facts` does.
"""
from __future__ import annotations

from typing import Any, Optional

from app.services.scm.demand_class import DEFAULT_DEMAND_CLASS, OTHER, PROJECT, planning_class
from app.services.scm.pool_predicate import is_site_pool, site_pool_clause

#: The verdict a line at a flagged-off bin carries, on the board and at confirm
#: (AC-S1-6). One string, shared, because the board renders it and the confirm refuses
#: with it, and two spellings would read as two different rules.
OUTSIDE_FULFILMENT_PLANNING = "Outside fulfilment planning"

#: Why an order is not admitted (`why_not_admitted`). One spelling per reason, because adoption
#: refuses with it and the board's empty state prints it.
NO_CLASS_REASON = "This sales order has no class set, so it is not planned here."
NO_DEALER_LINE_REASON = (
    "This dealer sales order has no line at a dealer location, so it is not planned here."
)


def fulfilment_planning_predicate(model: Optional[Any] = None):
    """The same rule as an ORM clause, for a caller writing a SQLAlchemy query.

    `model` defaults to `app.models.inventory.Warehouse`; pass an alias when the query
    joins the table twice. Imported lazily so this module stays importable from anywhere
    without dragging the model graph in behind it.
    """
    if model is None:
        from app.models.inventory import Warehouse as model
    return (model.is_active.is_(True)) & (model.fulfilment_planning.is_(True))


def in_fulfilment_planning(warehouse: Any) -> bool:
    """The same rule for a caller holding an ORM row rather than writing a query.

    A row that predates the column (a stub built in a test, a detached object) reads as
    False, which is the column's own default and the safe answer: a location nobody has
    decided about is not planned against.
    """
    if warehouse is None:
        return False
    return bool(getattr(warehouse, "is_active", False)) and bool(
        getattr(warehouse, "fulfilment_planning", False)
    )


#: Documents whose stock sits at a bin the ladder does not plan (a consignment at CON). Their
#: lines are planned at that bin, so they never earn the OUTSIDE_FULFILMENT_PLANNING verdict.
#: The bin stays flagged off, so no DRAW reads it and sales order lines never see it.
PLANNED_AT_OWN_BIN_DOC_TYPES = frozenset({"consignment"})


def planned_at_own_bin(warehouse: Any, doc_type: Optional[str]) -> bool:
    """Whether this line is planned AT its own bin: its doc type is in
    `PLANNED_AT_OWN_BIN_DOC_TYPES` AND the bin is not in fulfilment planning.

    Regardless of the bin's `is_active`: the bin is the document's own location, and the dev
    CON is inactive as well as flagged off. A consignment line at a bin that IS in planning
    (active, flag on) is planned like a sales order line (CONSIGN-PLAN card R6), so the doc
    type alone is never enough.
    """
    return (
        doc_type in PLANNED_AT_OWN_BIN_DOC_TYPES
        and warehouse is not None
        and not in_fulfilment_planning(warehouse)
    )


def outside_fulfilment_planning(
    warehouse: Any, doc_type: Optional[str] = None, demand_class: Optional[str] = None
) -> bool:
    """Whether this bin earns the `OUTSIDE_FULFILMENT_PLANNING` verdict: ACTIVE, flag off.

    A line whose `doc_type` is in `PLANNED_AT_OWN_BIN_DOC_TYPES` never earns it, and neither
    does a line at a dealer-segment bin (see the module docstring). What is left is a project
    bin somebody flagged off, and a RETAIL order's line at any project bin, flag or no flag:
    retail is admitted for its dealer locations, and a project bin holds a project's stock.

    Deliberately not `not in_fulfilment_planning(...)`. An INACTIVE warehouse was already
    outside everything the ladder reads before this flag existed, and it keeps the verdict
    it carried then - telling a planner that a retired bin is "outside fulfilment planning"
    points them at a switch that is not the one to flip.
    """
    if warehouse is None or doc_type in PLANNED_AT_OWN_BIN_DOC_TYPES:
        return False
    if is_site_pool(getattr(warehouse, "segment", None)):
        return False
    if planning_class(demand_class) == DEFAULT_DEMAND_CLASS:
        return True
    return bool(getattr(warehouse, "is_active", False)) and not bool(
        getattr(warehouse, "fulfilment_planning", False)
    )


def admitted_to_planning():
    """Whether a sales order is planning work at all, as a clause over `SalesOrder`.

    A correlated EXISTS over ALIASES: the callers' own queries have `sales_order_lines` in
    their FROM, and a sub-select over the same unaliased table would correlate to the row being
    aggregated and become a per-line filter. ANY line counts, a cancelled one too: the board's
    cancelled-line reads exist for an order with no live line left, and an order must not fall
    off them because the book cancelled its last dealer line.
    """
    from sqlalchemy import and_, exists, or_
    from sqlalchemy.orm import aliased

    from app.models.inventory import Warehouse
    from app.models.order import SalesOrder, SalesOrderLine

    line = aliased(SalesOrderLine)
    location = aliased(Warehouse)
    at_dealer_location = (
        exists()
        .where(
            line.sales_order_id == SalesOrder.id,
            location.id == line.warehouse_id,
            location.is_active.is_(True),
            site_pool_clause(location),
        )
        .correlate(SalesOrder)
    )
    return or_(
        SalesOrder.demand_class == PROJECT,
        and_(SalesOrder.demand_class.in_((DEFAULT_DEMAND_CLASS, OTHER)), at_dealer_location),
    )


def why_not_admitted(demand_class: Optional[str]) -> str:
    """The true reason for an order `admitted_to_planning` left out, given its class."""
    return NO_DEALER_LINE_REASON if demand_class else NO_CLASS_REASON


__all__ = [
    "NO_CLASS_REASON",
    "NO_DEALER_LINE_REASON",
    "OUTSIDE_FULFILMENT_PLANNING",
    "PLANNED_AT_OWN_BIN_DOC_TYPES",
    "admitted_to_planning",
    "fulfilment_planning_predicate",
    "in_fulfilment_planning",
    "planned_at_own_bin",
    "outside_fulfilment_planning",
    "why_not_admitted",
]
