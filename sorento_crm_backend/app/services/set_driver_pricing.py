"""How a product SET's money lands on its parts when a set is split into its components.

Owner ruling (5 Nov 2026, "ok a", R6a on lane AC-QTSO-CRM): a quoted set line is sold at the
set rate per set. When it is split into parts, the main ("driver") part carries ALL of the
set's money and the other parts ride at zero. The driver's unit price is the set rate divided
by its quantity per set, so the split always adds up to exactly what was accepted:

    set RM100 x 2 sets, driver 2 per set  ->  driver 4 x 50.00 = 200.00

Unit prices are whole cents (AutoCount takes qty x unit price; we assume no discount
semantics). When the money does not divide into whole cents, the driver goes as TWO rows of
the same item: all but one unit at the rounded-down rate, and one unit carrying the remainder
cents, e.g. RM200 over 6 units -> 5 x 33.33 + 1 x 33.35 = 200.00.

ONE function, shared by the SO draft (`project_so_draft_service`) and the AutoCount QT/SO
writer (lane AC-QTSO-CRM), so the two can never price a set differently.
"""
from __future__ import annotations

from decimal import ROUND_DOWN, Decimal
from typing import List, Tuple

_CENTS = Decimal("0.01")
_ONE = Decimal("1")


def split_set_driver_price(
    set_rate: Decimal, set_qty: Decimal, driver_qty_per_set: Decimal
) -> List[Tuple[Decimal, Decimal]]:
    """The driver part's ``(qty, unit_price)`` rows for ``set_qty`` sets at ``set_rate``.

    The rows total ``set_rate x set_qty`` rounded to cents, to the cent. One row when the
    money divides evenly (always the case at 1 per set, which returns the set rate untouched);
    two rows otherwise, the second being a single unit carrying the remainder. The unit
    price is rounded DOWN, so the remainder row is never cheaper than the others.

    Edge cases: a driver quantity that is not a whole number above 1 (a fractional or
    negative quantity, or a fraction of a set) cannot be split that way, so it goes as one
    row at the nearest cent; only there can the total miss by up to half a cent per unit.
    A driver quantity of zero (a part frozen at 0 per set, or no sets) has nothing to carry
    the money and is returned as ``[(0, set_rate)]``.
    """
    driver_qty = set_qty * driver_qty_per_set
    if driver_qty_per_set == _ONE or driver_qty == 0:
        return [(driver_qty, set_rate)]

    total = (set_rate * set_qty).quantize(_CENTS)
    exact = total / driver_qty
    if exact == exact.quantize(_CENTS):
        return [(driver_qty, exact.quantize(_CENTS))]
    if driver_qty <= _ONE or driver_qty != driver_qty.to_integral_value():
        return [(driver_qty, exact.quantize(_CENTS))]

    base = exact.quantize(_CENTS, rounding=ROUND_DOWN)
    rest = driver_qty - _ONE
    return [(rest, base), (_ONE, total - base * rest)]
