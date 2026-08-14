"""Collection membership: rule union pins minus exclusions (AC-F2).

Kept as a pure function over id lists, deliberately. Whether the RULE matched
the right products is a database question answered by the rule engine and the
company scope filter; what happens to those ids afterwards is set algebra a
Designer reasons about directly, and it is easier to trust when nothing else is
in the way.

Two rules carry the weight:

  * **An exclusion always wins.** It beats a rule match and it beats a pin,
    including a pin the same person added five minutes earlier. Anything else is
    the system arguing with the more recent decision.
  * **`manual_order` is a preference, not a membership list.** Ids in it that
    are no longer members are ignored (a stale order list must never resurrect a
    product), and members missing from it sort after the ordered ones in their
    incoming order (a newly matched product must not silently jump to the front,
    and must not vanish).
"""
from __future__ import annotations

from typing import Iterable, Optional


def _clean(ids: Optional[Iterable[Optional[str]]]) -> list[str]:
    """Drop nulls and blanks. A null in `pinned_product_ids` would otherwise
    become a tile bound to nothing."""
    if not ids:
        return []
    return [str(value) for value in ids if value]


def assemble_members(
    *,
    matched: Optional[Iterable[Optional[str]]],
    pinned: Optional[Iterable[Optional[str]]] = None,
    excluded: Optional[Iterable[Optional[str]]] = None,
    manual_order: Optional[Iterable[Optional[str]]] = None,
) -> list[str]:
    """Resolve the ordered member ids of a collection.

    ``matched`` is what the rule produced, already company-scoped and in the
    query's own order - which is the documented fallback sort.
    """
    excluded_set = set(_clean(excluded))

    # dict preserves insertion order and de-duplicates in one pass: rule matches
    # first, then hand-picked additions.
    members: dict[str, None] = {}
    for product_id in _clean(matched) + _clean(pinned):
        if product_id not in excluded_set:
            members[product_id] = None

    order = _clean(manual_order)
    if not order:
        return list(members)

    ordered = [product_id for product_id in order if product_id in members]
    seen = set(ordered)
    return ordered + [product_id for product_id in members if product_id not in seen]
