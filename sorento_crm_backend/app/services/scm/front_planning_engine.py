"""Order promising: what covers a Project SO line, and why (PLAN 3.2, 3.3, 3.5).

PURE arithmetic, the same discipline as ``coverage_timeline`` and ``reorder_engine``'s top
half: no database, no LLM, no optimizer, no configuration knob. Every number here is
derived from the rule that produced it, and every rule states itself in a sentence that
travels with the quantity, because a proposal that shows a number without saying why is a
number CS has to go and verify somewhere else (AC-B14).

Two functions, and they answer two different questions.

``propose_line`` answers "how should THIS line be met" - Reserve from eligible free stock,
then timely SPO cover, then Buy for whatever is left. Eligibility is section 3.3's
hot-selling rule: a dealer hot-selling product may not touch dealer-facing stock at all and
may draw from the shared pool only above the pool's own reorder level.

``attribute_sources`` answers "who gets the one pile" - several lines competing for one
location's opening stock and its dated incoming, resolved in section 3.5's fixed order so
the same facts always produce the same answer and the database's row order never
participates.

Quantities are ``Decimal`` throughout. These figures are compared for exact equality at
confirmation, and a binary float does not survive that.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

ZERO = Decimal("0")

# The four component kinds of the balance invariant (PLAN 3.1):
#   open_so_qty = timely_spo_coverage + reserve_qty + borrow_qty + buy_qty
TIMELY_SPO = "timely_spo"
RESERVE = "reserve"
BORROW = "borrow"
BUY = "buy"

#: How each kind reads on screen. Kept beside the kinds so `Component.stated` and the UI
#: cannot spell the same component two ways.
COMPONENT_LABELS = {
    TIMELY_SPO: "Timely SPO",
    RESERVE: "Reserve",
    BORROW: "Borrow",
    BUY: "Buy",
}

BUY_REASON = "remaining uncovered need"


def qty_text(value: Decimal) -> str:
    """A quantity as a person writes it.

    ``Decimal("40").normalize()`` is ``4E+1``, which inside a reason string reads as a
    defect rather than as forty units.
    """
    return format(_dec(value).normalize(), "f")


def _dec(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return ZERO
    return Decimal(str(value))


@dataclass(frozen=True)
class Component:
    """One proposed component: how much, from where, and why."""

    kind: str
    qty: Decimal
    #: The rule's own sentence. Deterministic for the same snapshot, never LLM-written,
    #: and frozen with the line snapshot at confirmation.
    reason: str
    #: Where the quantity comes from: the fulfilment location for own-location Reserve and
    #: timely SPO cover, the pool warehouse for pool Reserve, the donor location for
    #: Borrow. Buy has none - it is not held anywhere yet.
    source_location: Optional[str] = None

    @property
    def stated(self) -> str:
        """The whole phrase AC-B14 quotes: "Reserve 10: free stock at BRW ..."."""
        return f"{COMPONENT_LABELS[self.kind]} {qty_text(self.qty)}: {self.reason}"


def _own_reason(location: str) -> str:
    return f"free stock at {location} covers the need by the required date"


def _pool_reason_with_level(pool_location: str, level: Decimal) -> str:
    return (
        f"free stock in the shared {pool_location} pool above its reorder level of "
        f"{qty_text(level)} covers the need by the required date"
    )


def _spo_reason(spo_number: str, arrival_date: Optional[date]) -> str:
    when = arrival_date.isoformat() if arrival_date else "an unstated date"
    return f"SPO {spo_number} arrives on {when}, by the required date"


# --------------------------------------------------------------------------- #
# Reserve eligibility (PLAN 3.3)
# --------------------------------------------------------------------------- #


def reserve_capacity(
    *,
    is_dealer_hot_selling: bool,
    fulfilment_location: Optional[str],
    pool_location: Optional[str],
    free_stock: Mapping[str, Any],
    reorder_levels: Mapping[str, Any],
) -> List[Tuple[str, Decimal, str]]:
    """How much Reserve each location may contribute, in draw order, with its reason.

    Shared by the proposal and by the confirmation recheck, so the sheet cannot offer a
    Reserve the commit would refuse.

    * **Dealer hot-selling**: dealer-facing free stock contributes nothing, and the pool
      contributes only above its own per-location reorder level -
      ``max(pool free - coalesce(level, 0), 0)``. An absent or NULL level is 0 (Q7).
    * **Otherwise**: the line's own fulfilment location first, then the shared pool, with
      no floor on either.
    """
    out: List[Tuple[str, Decimal, str]] = []
    pool_free = max(_dec(free_stock.get(pool_location)) if pool_location else ZERO, ZERO)

    if is_dealer_hot_selling:
        if not pool_location:
            return out
        level = max(_dec(reorder_levels.get(pool_location)), ZERO)
        cap = max(pool_free - level, ZERO)
        if cap > ZERO:
            out.append((pool_location, cap, _pool_reason_with_level(pool_location, level)))
        return out

    if fulfilment_location:
        own_free = max(_dec(free_stock.get(fulfilment_location)), ZERO)
        if own_free > ZERO:
            out.append((fulfilment_location, own_free, _own_reason(fulfilment_location)))
    if pool_location and pool_location != fulfilment_location and pool_free > ZERO:
        out.append((pool_location, pool_free, _own_reason(pool_location)))
    return out


# --------------------------------------------------------------------------- #
# One line's composition (PLAN 3.2)
# --------------------------------------------------------------------------- #


def propose_line(
    *,
    open_qty: Any,
    line_no: Optional[int] = None,
    required_date: Optional[date] = None,
    fulfilment_location: Optional[str] = None,
    is_dealer_hot_selling: bool = False,
    free_stock: Optional[Mapping[str, Any]] = None,
    pool_location: Optional[str] = None,
    reorder_levels: Optional[Mapping[str, Any]] = None,
    timely_spo_qty: Any = ZERO,
    timely_spo_refs: Optional[Sequence[Mapping[str, Any]]] = None,
    is_discontinued: bool = False,
    borrow_qty: Any = ZERO,
) -> Tuple[Component, ...]:
    """The proposed composition for one line, in PLAN 3.2's own order.

    1. start at the line's current open quantity;
    2. Reserve from eligible free stock (section 3.3, via `reserve_capacity`);
    3. timely SPO cover, for supply arriving on or before the required date;
    4. Borrow is never PROPOSED - its quantity comes from CS, and it is passed back in as
       ``borrow_qty`` when the residual is recomputed at confirmation. The Borrow
       components themselves carry the reason CS typed, so the caller composes them;
    5. Buy is the remaining positive residual.

    A component contributing nothing is not proposed at all: emitting a zero would force a
    reason for a quantity that does not exist.

    ``line_no``, ``required_date`` and ``is_discontinued`` do not change a quantity.
    They travel with the call because the snapshot freezes them and because the
    discontinued warning is stated beside the Buy the caller renders.
    """
    remaining = max(_dec(open_qty), ZERO)
    components: List[Component] = []

    for location, capacity, reason in reserve_capacity(
        is_dealer_hot_selling=is_dealer_hot_selling,
        fulfilment_location=fulfilment_location,
        pool_location=pool_location,
        free_stock=free_stock or {},
        reorder_levels=reorder_levels or {},
    ):
        if remaining <= ZERO:
            break
        take = min(remaining, capacity)
        if take <= ZERO:
            continue
        components.append(
            Component(kind=RESERVE, qty=take, reason=reason, source_location=location)
        )
        remaining -= take

    timely = max(_dec(timely_spo_qty), ZERO)
    if remaining > ZERO and timely > ZERO:
        components.extend(
            _timely_components(
                min(remaining, timely), timely_spo_refs, fulfilment_location
            )
        )
        remaining -= min(remaining, timely)

    remaining -= max(_dec(borrow_qty), ZERO)

    if remaining > ZERO:
        components.append(Component(kind=BUY, qty=remaining, reason=BUY_REASON))
    return tuple(components)


def _timely_components(
    qty: Decimal,
    refs: Optional[Sequence[Mapping[str, Any]]],
    location: Optional[str],
) -> List[Component]:
    """Timely cover, named by the SPO rows that supply it when they are known.

    Named is the useful form: "SPO 202703-S0011 arrives on 2027-03-01" is something CS can
    look up, and an unnamed quantity is not.
    """
    if not refs:
        return [
            Component(
                kind=TIMELY_SPO,
                qty=qty,
                reason="incoming supply arrives by the required date",
                source_location=location,
            )
        ]
    out: List[Component] = []
    remaining = qty
    for ref in _sorted_supply(refs):
        if remaining <= ZERO:
            break
        take = min(remaining, max(_dec(ref.get("qty")), ZERO))
        if take <= ZERO:
            continue
        out.append(
            Component(
                kind=TIMELY_SPO,
                qty=take,
                reason=_spo_reason(
                    str(ref.get("spo_number") or ""), _as_date(ref.get("arrival_date"))
                ),
                source_location=location,
            )
        )
        remaining -= take
    return out


# --------------------------------------------------------------------------- #
# Several lines against one location's supply (PLAN 3.5)
# --------------------------------------------------------------------------- #


def _as_date(value: Any) -> Optional[date]:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _demand_sort_key(line: Mapping[str, Any]) -> tuple:
    """Required date, SO number, line number (missing last), then internal line id.

    The line id is a final stable key only and is never displayed: two lines that agree on
    everything a person can see still have to be ordered the same way on every run.
    """
    when = _as_date(line.get("required_date"))
    line_no = line.get("line_no")
    return (
        when is None,
        when or date.min,
        str(line.get("so_number") or ""),
        line_no is None,
        int(line_no) if line_no is not None else 0,
        str(line.get("line_id") or ""),
    )


def _supply_sort_key(event: Mapping[str, Any]) -> tuple:
    """Arrival date, SPO number, SPO line number (missing last), then allocation id."""
    when = _as_date(event.get("arrival_date"))
    line_no = event.get("spo_line_no")
    return (
        when is None,
        when or date.min,
        str(event.get("spo_number") or ""),
        line_no is None,
        int(line_no) if line_no is not None else 0,
        str(event.get("allocation_id") or ""),
    )


def _sorted_supply(events: Iterable[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    return sorted(events, key=_supply_sort_key)


def attribute_sources(
    *,
    product_code: Optional[str] = None,
    warehouse_code: str,
    opening_stock: Any = ZERO,
    supply_events: Optional[Sequence[Mapping[str, Any]]] = None,
    demand_lines: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Dict[Tuple[str, Optional[int]], Tuple[Component, ...]]:
    """Share one product-location's dated supply across the lines asking for it.

    Keyed by each demand line's own ``key`` when it states one, and by
    ``(so_number, line_no)`` when it does not.

    The explicit key is not a convenience. ``line_no`` comes from the PROJECT mirror, and a
    core sales-order line that nobody has adopted has none - so every unmirrored line of one
    sales order collapsed onto the single key ``(so_number, None)``, and all but one of them
    silently received no share at all while the pile was credited as if they had. Invisible on
    the per-order sheet, which only ever walks mirrored lines; fatal to the multi-order board,
    where most lines at a pile belong to orders nobody has adopted.

    Sources are consumed in PLAN 3.5's order - opening stock first, then SPO arriving on or
    before that line's required date - with lines processed by required date, SO number,
    line number (missing last) and finally the internal line id. An SPO arriving ON the
    required date counts; one arriving the day after contributes nothing at that date and
    is advisory evidence instead.

    ``product_code`` names the pile in a failure message and takes no part in the
    arithmetic; the caller has already narrowed the rows to one product and location.
    """
    stock_left = max(_dec(opening_stock), ZERO)
    supply: List[Dict[str, Any]] = [
        {
            "spo_number": str(event.get("spo_number") or ""),
            "spo_line_no": event.get("spo_line_no"),
            "allocation_id": event.get("allocation_id"),
            "arrival_date": _as_date(event.get("arrival_date")),
            "left": max(_dec(event.get("qty")), ZERO),
        }
        for event in _sorted_supply(supply_events or [])
    ]

    out: Dict[Tuple[str, Optional[int]], Tuple[Component, ...]] = {}
    for line in sorted(demand_lines or [], key=_demand_sort_key):
        remaining = max(_dec(line.get("open_qty")), ZERO)
        required_date = _as_date(line.get("required_date"))
        components: List[Component] = []

        take = min(remaining, stock_left)
        if take > ZERO:
            components.append(
                Component(
                    kind=RESERVE,
                    qty=take,
                    reason=_own_reason(warehouse_code),
                    source_location=warehouse_code,
                )
            )
            stock_left -= take
            remaining -= take

        for event in supply:
            if remaining <= ZERO:
                break
            if event["left"] <= ZERO:
                continue
            arrival = event["arrival_date"]
            if required_date is not None and (arrival is None or arrival > required_date):
                # Later than the need: advisory at this date, and it contributes nothing.
                continue
            taken = min(remaining, event["left"])
            components.append(
                Component(
                    kind=TIMELY_SPO,
                    qty=taken,
                    reason=_spo_reason(event["spo_number"], arrival),
                    source_location=warehouse_code,
                )
            )
            event["left"] -= taken
            remaining -= taken

        if remaining > ZERO:
            components.append(Component(kind=BUY, qty=remaining, reason=BUY_REASON))

        stated = line.get("key")
        key = stated if stated is not None else (
            str(line.get("so_number") or ""), line.get("line_no")
        )
        out[key] = tuple(components)
    return out
