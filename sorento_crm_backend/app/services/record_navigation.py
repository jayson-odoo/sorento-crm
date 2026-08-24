"""Shared, resource-agnostic prev/next neighbour math for list->detail pagers.

A detail page shows a "X / Y" pager that walks the previous/next record within
the exact filtered+sorted+searched set the user navigated from. The frontend
calls a per-resource ``/neighbours`` endpoint; each endpoint resolves the ordered
id list for the active list query and hands it to :func:`compute_neighbours`.

This module is intentionally pure (no DB, no SQLAlchemy) so it is trivially
unit-testable and reusable by every resource that adopts the pattern.

Locked decisions (see docs/plans/PLAN-record-navigation-standardization.md):
- D3 circular wrap: Next on the last record wraps to the first; Prev on the
  first wraps to the last. Both neighbours are non-null whenever total > 1.
- The caller owns the D2 fallback: if ``current_id`` is not in the filtered set,
  the caller re-resolves the unfiltered (default-sorted) ordered ids and calls
  this helper again, so the pager is never dead.
"""

from typing import Optional


def compute_neighbours(ordered_ids: list[str], current_id: str) -> dict:
    """Compute the 1-based position and circular prev/next ids for ``current_id``.

    Args:
        ordered_ids: the ids of the filtered+sorted set, in display order. Must
            be deterministically ordered by the caller (stable tie-breaker).
        current_id: the id whose neighbours we want.

    Returns:
        ``{"total": int, "index": int|None, "prev_id": str|None, "next_id": str|None}``

        - ``total`` - size of the set.
        - ``index`` - 1-based position of ``current_id`` in the set, or ``None``
          when it is not present (caller decides whether to retry with the
          unfiltered set per D2).
        - ``prev_id`` / ``next_id`` - circular neighbours (D3). ``None`` only
          when there is no sensible neighbour: an empty set, a single-record set
          (``total <= 1``), or ``current_id`` absent from the set.
    """
    total = len(ordered_ids)
    current_key = str(current_id)

    pos: Optional[int] = None
    for i, rid in enumerate(ordered_ids):
        if str(rid) == current_key:
            pos = i
            break

    if pos is None:
        # Not in this set - caller may retry with the unfiltered set (D2).
        return {"total": total, "index": None, "prev_id": None, "next_id": None}

    if total <= 1:
        # Single record: pager reads "1 / 1", both chevrons disabled (UAC-7).
        return {"total": total, "index": pos + 1, "prev_id": None, "next_id": None}

    # Circular wrap (D3 / UAC-6).
    prev_id = ordered_ids[(pos - 1) % total]
    next_id = ordered_ids[(pos + 1) % total]
    return {
        "total": total,
        "index": pos + 1,
        "prev_id": str(prev_id),
        "next_id": str(next_id),
    }
