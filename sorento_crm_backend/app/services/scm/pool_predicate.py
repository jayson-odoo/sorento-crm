"""ONE spelling of "a site pool", for every screen whose numbers have to foot.

**The rule.** A warehouse is a SITE POOL unless its `segment` says `project`. A location
nobody has classified counts: `COALESCE(segment, 'dealer')`, because an unclassified
warehouse is a warehouse somebody has not got round to, not a project bin - and treating it
as a bin would quietly drop real stock out of every figure on these screens.

**Why the two exclusions.** A PROJECT bin holds stock already committed to a named project,
so it is not supply anybody may plan against; an INACTIVE location holds stock nobody can
pick. Neither belongs in "what we have", so neither belongs in a cell whose lightbox lists
what we have.

**Why one module.** The same predicate was written four times - `container_request_service.
_pool_predicate`, `container_request_drill._POOL`, `spo_conversion_service._ACTIVE_POOL` and
`reorder_run_service`'s `is_dealer_expr` - each with a comment saying it was "character for
character" one of the others. That is a rule that only holds while four files agree, and the
screens it feeds are the ones the captain's AC-G3 requires to foot with each other: the SPO
planner's On hand must equal its own dialog, and the container request's must equal the
lightbox behind it. A predicate that has to be identical in four places is one predicate.

`segment` is the test, never the warehouse code's naming convention (a hyphen suffix is not a
classification - `project_supply_service._site_pool_warehouses` warns the same), and never
`pool_warehouse_id`, which drives the unrelated fulfilment-pool netting opt-in whose members
are not necessarily project-segment locations.
"""
from __future__ import annotations

from typing import Optional

#: The segment on a project bin. Everything else, unset included, is a site pool.
PROJECT_SEGMENT = "project"

#: What an unclassified warehouse counts as.
_DEFAULT_SEGMENT = "dealer"


def site_pool_sql(alias: str = "w") -> str:
    """The segment half of the rule, for a query that states `is_active` itself.

    Takes its alias so one rule can be written into any query without a second spelling of
    it existing anywhere.
    """
    return f"(COALESCE({alias}.segment, '{_DEFAULT_SEGMENT}') <> '{PROJECT_SEGMENT}')"


def active_site_pool_sql(alias: str = "w") -> str:
    """The whole rule: active, and not a project bin."""
    return f"({alias}.is_active AND COALESCE({alias}.segment, '{_DEFAULT_SEGMENT}') <> '{PROJECT_SEGMENT}')"


#: The two ready-made forms for the common alias, so a caller that needs no alias of its own
#: reads as a constant rather than as a call.
SITE_POOL_SQL = site_pool_sql()
ACTIVE_SITE_POOL_SQL = active_site_pool_sql()


def is_site_pool(segment: Optional[str]) -> bool:
    """The same rule for a caller holding ORM rows rather than writing SQL."""
    return (segment or _DEFAULT_SEGMENT) != PROJECT_SEGMENT


__all__ = [
    "ACTIVE_SITE_POOL_SQL",
    "PROJECT_SEGMENT",
    "SITE_POOL_SQL",
    "active_site_pool_sql",
    "is_site_pool",
    "site_pool_sql",
]
