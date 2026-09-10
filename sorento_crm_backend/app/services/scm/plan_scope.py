"""ONE rule for whether a plan row is on the buyer's business by default.

PLAN-plan-list-tile-sheet-one-scope.md / UAC "The one rule" (owner rulings):

* 12 Aug 2026: "if net is not below my reorder level, it is not my business, I don't need
  to see this in reorder planning" - a covered row on the MANUAL basis (`reorder_level`)
  whose net sits above its own level is not something the buyer needs to act on.
* 10 Sep 2026: "tile counts what the list show, and the exported excel should be faithful
  to the list also" - the list, the Decisions tile total and the order sheet export must
  agree on which rows are hidden, so the rule lives in ONE place and all three read it,
  rather than three independent re-derivations that could drift (measured: the list showed
  415 of 950, the tile said "0 of 950", the sheet printed 950).

This is the backend twin of what used to be spelled only in the frontend
(`PlanLinesSection.visibleLines` + `orderQtyLedger.lineBreachStatus`, S6-FE). `net_position`
here is the rec's OWN stored column ALONE - never the engine's decision net (`net_position +
po_ordered`, `reorder_run_service`'s `net = net_position + po_ordered`) - because that is the
exact figure the frontend's `l.net` (`lib/planRow.ts`, `net: rec.net_position`) already reads
and the rule has to keep matching what the buyer sees on the ledger sentence.

A missing basis or a missing net means SHOWN, never hidden: hiding a row on a fact nobody
measured would silently drop it off a list the buyer is meant to be able to trust.
"""
from __future__ import annotations

from typing import Optional


def hidden_by_default(
    *,
    rec_type: Optional[str],
    policy_type: Optional[str],
    reorder_level: Optional[float],
    master_reorder_level: Optional[float],
    net_position: Optional[float],
) -> bool:
    """True when ALL hold: the row is `covered`, its basis is the manual `reorder_level`
    policy, a basis value exists (the row's own `reorder_level`, else the product's
    `master_reorder_level`), `net_position` is not None, and `net_position > basis`.
    """
    if rec_type != "covered":
        return False
    if policy_type != "reorder_level":
        return False
    basis = reorder_level if reorder_level is not None else master_reorder_level
    if basis is None or net_position is None:
        return False
    return net_position > basis
