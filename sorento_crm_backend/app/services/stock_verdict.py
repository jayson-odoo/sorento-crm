"""The verdict, one pure function (dealer stock verdict S0, D6, D7).

`verdict()` is the ONE decision seam every arm of the dealer's stock reply passes
through: given how many units are on hand at the dealer's allowed warehouses (after
open sales orders), how many they asked for, and how many are counted as incoming
(in-transit allocations) or on open purchase order lines at those same warehouses, it
answers whether Sorento can supply the ask, whether the answer is running low, and -
when it cannot - which of incoming/purchase to name and whether either is itself
running short.

No I/O, no dates: the ETA a caller attaches to a `Verdict.sources` entry is the
caller's business (`app/services/inventory_service.py`), not this function's. Pure and
table-driven on purpose, so it is the one place the rule (D6) is written and tested -
`tests/test_stock_verdict.py` runs the owner's own 18-row matrix against it.

D6 in full. Deficit D = ask - available, T = threshold_pct (compared as a percentage,
never as a float - every comparison below is `x * 100 >= threshold_pct * y`, so the
rule is exact integer arithmetic with no floating-point rounding at the boundary):

* ask <= available -> "available"; `running_low` when ask * 100 >= T * available.
* Else ("not_available"), incoming is consulted FIRST:
  - incoming >= D -> sources ("incoming",), purchase is NOT named even if it is also
    nonzero; `limited` when D * 100 >= T * incoming.
  - 0 < incoming < D and incoming + purchase >= D -> sources ("incoming", "purchase");
    `limited` when D * 100 >= T * (incoming + purchase).
  - incoming == 0 and purchase >= D -> sources ("purchase",); `limited` when
    D * 100 >= T * purchase.
  - otherwise -> sources (), `limited` False (no disclaimer at all).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Tuple


@dataclass(frozen=True)
class Verdict:
    answer: Literal["available", "not_available"]
    running_low: bool
    sources: Tuple[str, ...]
    limited: bool


def verdict(*, available: int, ask: int, incoming: int, purchase: int, threshold_pct: int) -> Verdict:
    """The dealer stock verdict rule (D6). `ask` must be positive - the caller never
    asks this function to judge a zero or negative quantity."""
    if ask <= 0:
        raise ValueError(f"ask must be positive, got {ask}")

    if ask <= available:
        running_low = ask * 100 >= threshold_pct * available
        return Verdict(answer="available", running_low=running_low, sources=(), limited=False)

    deficit = ask - available

    if incoming >= deficit:
        limited = deficit * 100 >= threshold_pct * incoming
        return Verdict(answer="not_available", running_low=False, sources=("incoming",), limited=limited)

    if 0 < incoming < deficit and incoming + purchase >= deficit:
        limited = deficit * 100 >= threshold_pct * (incoming + purchase)
        return Verdict(
            answer="not_available",
            running_low=False,
            sources=("incoming", "purchase"),
            limited=limited,
        )

    if incoming == 0 and purchase >= deficit:
        limited = deficit * 100 >= threshold_pct * purchase
        return Verdict(answer="not_available", running_low=False, sources=("purchase",), limited=limited)

    return Verdict(answer="not_available", running_low=False, sources=(), limited=False)
