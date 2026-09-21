"""One numbering rule for a set of core sales-order lines (PLAN-so-lines-autocount-order.md
3.5, B1 review round).

Three readers turn `sales_order_lines` rows into the `line 3`-style ordinal a human or a
save/confirm key names, and they have to agree: `FulfilmentBoardService._line_numbers` (the
board), `project_line_draft_service._resolve_core_line` (Save / Undo resolve a key by NAME,
not by row) and `ProjectSOAdoptionService._mirror` (what a fresh mirror is numbered when it
is created). A number the board hands out that the resolver reads differently 422s Save and
404s Undo; a mirror numbered by a different rule than the board would have used misnames the
very line adoption itself just addressed. A small module next to none of the three, so
either can import it without a cycle.

The rule, per sales order:

  1. every contributing line carries a DISTINCT, non-null `line_no` (AutoCount's own `Seq`)
     -> that IS the number, gaps and all: 5, 1, 3 stays 5, 1, 3, never renumbered to
     1, 2, 3 - line 5 has to keep meaning line 5 on both sides of the ESB link.
  2. otherwise every line falls back to a DERIVED 1..n, by (required date, nulls last;
     product code; line id) - today's rule, for an order AutoCount has never numbered. A
     PARTIAL `line_no` (some lines numbered, one not) is not enough to trust: the whole
     order falls back together, never a mix of the two rules on one order.

The board and the resolver ADDITIONALLY let a complete, distinct MIRROR numbering win over
either of the above (unchanged by this module - each caller still applies it itself): once
adopted, the mirror is the address Confirm and its drafts use, and Re-sync can renumber a
later line. `_mirror` has no mirror to defer to - it is what CREATES one - so it only ever
runs rule 1 or 2 here.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, NamedTuple, Optional, Sequence

_EARLIEST = date.min


class LineFacts(NamedTuple):
    """What the rule needs about one core line, built by each caller from whatever ORM
    shape it already queried - this module stays free of any one caller's query shape."""

    id: str
    line_no: Optional[int]
    required_date: Optional[date]
    product_code: str


def has_own_numbering(entries: Sequence[LineFacts]) -> bool:
    """Rule 1's gate: every entry carries a `line_no`, and no two share one. `False` on an
    empty sequence - there is nothing to prefer AutoCount's numbers over."""
    if not entries:
        return False
    line_nos = [entry.line_no for entry in entries]
    return all(n is not None for n in line_nos) and len(set(line_nos)) == len(line_nos)


def number_lines(entries: Sequence[LineFacts]) -> Dict[str, int]:
    """`{id: number}` for one order's worth of lines - rule 1 then rule 2 (module
    docstring). Numbers start at 1 under rule 2; a caller appending to an existing,
    already-numbered set (`_mirror`'s `start_at`) slides these into place itself."""
    if has_own_numbering(entries):
        return {entry.id: int(entry.line_no) for entry in entries}  # type: ignore[arg-type]
    ordered = sorted(
        entries,
        key=lambda e: (
            e.required_date is None,
            e.required_date or _EARLIEST,
            e.product_code or "",
            e.id,
        ),
    )
    return {entry.id: index for index, entry in enumerate(ordered, start=1)}
