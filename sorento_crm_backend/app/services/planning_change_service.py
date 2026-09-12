"""The SO book's own reaction to the plan (`documentation/plans/scm/PLAN-so-book-diff-
replanning.md` section 2).

A batch is born, best-effort, right after `outstanding_import_service.apply()` writes a
re-uploaded book: one row per PLANNED line the upload changed, what the line's active
decision holds today, the facts the suggestion rule used, and a suggested reaction the
planner already knows from the fulfilment board. Nothing is written to the plan until
`apply()` in this module runs, and that only touches the rows the planner accepted.

Kept ignorant of `outstanding_import_service`'s own internals beyond the `Diff` it hands
over - the same separation `project_so_ingest_service` keeps from the SCM import today - and
called from that module's `apply()`, never the reverse.

**`release` returns the WHOLE line to the board** (captain, 19 August 2026, PLAN section 6):
excluded from the new revision exactly like a `replan` row, so its Reserve hold is gone on
the next read AND its incoming/Buy parts are not carried either - they are re-proposed when
the line is next confirmed. `_check_line` permits no partial cover (a line named in a
`ConfirmLine` must sum to exactly its open quantity), so a "keep Buy, drop only Reserve"
composition has no seam without touching `project_supply_service.py`'s validation itself; a
real partial-cover seam is a follow-up, not this slice.

**`release` = releasing the project's claim ENTIRELY** (captain, 19 August 2026, correcting
the first cut of AC-R08): the reserve frees at its own location AND the Buy this line was
holding is no longer a purchase FOR this line - it becomes a POOL purchase. So a release is
not silent on Order Inquiry after all: every non-`actioned` OI row the line already raised
moves its `stock_location` to the line's pool (an `actioned` one keeps its location, already
bought, and gets the note only), and a `RELEASE` change row makes the same true in the
worklist the way a `DELAY` row does. Only the RESERVE side is silent - it is not a purchase,
so it raises nothing new.

Two further deliberate simplifications, flagged here because a future slice will want them
fixed properly rather than rediscovered by reading a bug report:

* **`replan` on `qty_up`** excludes the WHOLE line from the new revision (same as `advanced`)
  rather than freezing the existing covered quantity and running only the delta through the
  ladder - the same missing "partial confirm" seam.
* **`DATE_AND_QTY_CHANGED`** (both moved in one upload) is classified by DATE first: this
  build's own tie-break, because the section-0 table has no combined row and the two single
  changes disagree on suggestion.

**A line's already-`placed` Buy is invisible to the board's own ladder** (the captain, 20
Aug, diagnosing two live double-counts): `_proposal_for` asks `FulfilmentBoardService` to
walk the ladder for the line's FULL open quantity, and the board reads nothing off
`order_inquiry_rows` - it has no way to know part of that quantity is already covered by a
real purchase order tagged through section G's "Place on PO". `_apply_placed_offset`
relabels that much of the proposal's own Reserve/incoming rungs onto its Buy figure before
the row is stored, so the composition still balances the line's full open quantity but the
portion already bought reads as Buy - which `ProjectOrderInquiryService.refresh_for_decision`
then nets against the placed row itself, raising nothing further for it. See
`_inquiry_rows_and_buy_actioned` (reads `INQUIRY_PLACED` as actioned, same as `INQUIRY_ACTIONED`)
and `scripts/repair_20aug_placed_double_counts.py` for the two live rows this corrects.
"""
from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.models.inventory import Warehouse
from app.models.stock_transfer import TRANSFER_MOVED, StockTransfer
from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.planning_change import (
    PLANNING_CHANGE_STATE_APPLIED,
    PLANNING_CHANGE_STATE_FAILED,
    PLANNING_CHANGE_STATE_PENDING,
    PLANNING_CHANGE_STATE_SUPERSEDED,
    PlanningChangeBatch,
    PlanningChangeRow,
)
from app.models.product import Product
from app.models.project_so import (
    ALLOC_SOURCE_OTHER_LOCATION,
    INQUIRY_ACTIONED,
    INQUIRY_CANCELLED,
    INQUIRY_PARTLY_LINKED,
    INQUIRY_PLACED,
    IV_ORDER,
    IV_ORDER_BACK,
    IV_RESERVE_AND_ORDER,
    OrderInquiryLink,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
    SOSupplyDecision,
)
from app.models.projects import Project
from app.models.scm import ItemClassification
from app.models.user import User
from app.services.error_handler import AppException
from app.services.scm.front_planning_engine import BORROW, BUY, RESERVE, TIMELY_SPO, qty_text
from app.services.scm.outstanding_diff import (
    ADDED,
    CLOSED,
    DATE_AND_QTY_CHANGED,
    DATE_MOVED,
    PRODUCT_CHANGED,
    QTY_CHANGED,
    Diff,
    states_settled,
)
from app.services.project_so_delta_service import RESERVE_WINDOW_DAYS

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")


def _dec(value: Any) -> Decimal:
    if value is None:
        return _ZERO
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001 - a malformed stored figure is data, not a crash
        return _ZERO


def _json_safe(value: Any) -> Any:
    """A board contribution carries raw `date`/`Decimal` values (it is normally serialized
    through a pydantic response model, not read as a plain dict); round-tripping through
    `json` here is what makes it storable in a JSONB column."""
    if value is None:
        return None
    return json.loads(json.dumps(value, default=str))


def _as_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


# ============================================================================
# The suggestion: the re-run at the new state, DIFFED against what is held.
# Pure. `documentation/plans/scm/PLAN-scm-change-management-one-engine.md` rule 3.
# ============================================================================

#: The four classes a composition is made of, in the order a suggestion states them:
#: what the line already holds, read the same way `_held_from_frozen` writes it.
_CLASSES = ("reserve", "borrow", "spo", "buy")

#: How a class names itself inside a "Reduce X 100 to 0" sentence. `Buy` is capitalised
#: because it is the name of the Order Inquiry row a reader is looking at, not a noun.
_CLASS_WORD = {"reserve": "reserve", "borrow": "borrow", "spo": "SPO", "buy": "Buy"}


def _day(value: Any) -> str:
    """`20 Nov` - the date in a sentence a person reads, never an ISO string."""
    when = _as_date(value)
    return f"{when.day} {when.strftime('%b')}" if when else ""


def _days_word(days: int) -> str:
    return f"{days} day{'' if days == 1 else 's'}"


def _component(
    action: str,
    source: Optional[str],
    qty_now: Decimal,
    label: str,
    *,
    qty_was: Optional[Decimal] = None,
    location: Optional[str] = None,
    document: Optional[str] = None,
    target: Optional[str] = None,
    item_code: Optional[str] = None,
) -> dict:
    """One line of the suggestion, with the sentence the board prints for it.

    The sentence is composed HERE and printed verbatim: only this side knows which rung
    covered what, against which document, for whose order, so a second composition in the
    frontend could only drift from it (Slice C contract A).
    """
    return {
        "action": action,
        "source": source,
        "qty_was": qty_text(qty_was) if qty_was is not None else None,
        "qty_now": qty_text(qty_now),
        "location": location,
        "document": document,
        "target": target,
        "item_code": item_code,
        "label": label,
    }


def _held_classes(held: Optional[dict]) -> Dict[str, List[Tuple[Decimal, Optional[str]]]]:
    """What the line holds, as `(qty, location)` per class - `held_json`'s own shape."""
    held = held or {}
    out: Dict[str, List[Tuple[Decimal, Optional[str]]]] = {c: [] for c in _CLASSES}
    for entry in held.get("reserve") or []:
        qty = _dec(entry.get("qty"))
        if qty > _ZERO:
            out["reserve"].append((qty, entry.get("location")))
    for entry in held.get("borrow") or []:
        qty = _dec(entry.get("qty"))
        if qty > _ZERO:
            out["borrow"].append((qty, entry.get("location")))
    spo = _dec(held.get("timely_spo_qty"))
    if spo > _ZERO:
        out["spo"].append((spo, None))
    buy = _dec(held.get("buy_qty"))
    if buy > _ZERO:
        out["buy"].append((buy, None))
    return out


def _proposed_classes(proposal: Optional[dict]) -> Optional[Dict[str, dict]]:
    """The re-run, per class: how much, and the sources that say where and off what.

    The AGGREGATE is authoritative wherever the contribution carries one - the same rule
    `composition_from_proposal` follows, and for the same reason: `_apply_placed_offset`
    moves quantity between rungs and keeps the aggregates in step.
    """
    if not proposal:
        return None
    sources = proposal.get("sources") or []
    by_class: Dict[str, List[dict]] = {c: [] for c in _CLASSES}
    for source in sources:
        kind = source.get("kind")
        if kind == RESERVE:
            by_class["reserve"].append(source)
        elif kind == BORROW:
            by_class["borrow"].append(source)
        elif kind == TIMELY_SPO:
            by_class["spo"].append(source)
        elif kind == BUY:
            by_class["buy"].append(source)

    def total(aggregate_key: Optional[str], klass: str) -> Decimal:
        if aggregate_key is not None and proposal.get(aggregate_key) is not None:
            return _dec(proposal.get(aggregate_key))
        return sum((_dec(s.get("qty")) for s in by_class[klass]), _ZERO)

    return {
        "reserve": {
            "qty": total("qty_proposed_reserve", "reserve"),
            "sources": by_class["reserve"],
        },
        # No `qty_proposed_borrow` aggregate exists on a contribution (the two borrow rungs
        # are newer than that field), so the sources ARE the total - the same read
        # `composition_from_proposal` makes.
        "borrow": {"qty": total(None, "borrow"), "sources": by_class["borrow"]},
        "spo": {"qty": total("qty_proposed_incoming", "spo"), "sources": by_class["spo"]},
        "buy": {"qty": total("qty_proposed_buy", "buy"), "sources": by_class["buy"]},
    }


def _split_over_sources(
    total: Decimal, sources: List[dict]
) -> List[Tuple[Decimal, dict]]:
    """`total` spread over its own sources, take-until-covered, remainder on the last.

    The same convention `_reserve_components_from_sources` uses, so a suggestion line and
    the composition it will post name the same warehouses in the same order.
    """
    if total <= _ZERO:
        return []
    if not sources:
        return [(total, {})]
    out: List[Tuple[Decimal, dict]] = []
    remaining = total
    for source in sources:
        if remaining <= _ZERO:
            break
        take = min(_dec(source.get("qty")), remaining)
        if take <= _ZERO:
            continue
        out.append((take, source))
        remaining -= take
    if remaining > _ZERO:
        if out:
            out[-1] = (out[-1][0] + remaining, out[-1][1])
        else:
            out.append((remaining, sources[0]))
    return out


def _fit_to_new_quantity(
    proposed: Dict[str, dict], proposal: dict, facts: dict
) -> Dict[str, dict]:
    """The ladder's ANSWER, at the line's own NEW quantity.

    `_proposal_for` asks the board to walk the LIVE line, and the live line is normally
    already written by the time a batch is built (the trigger writes, then raises the
    change). When it is not - an ESB push whose board read raced the write, a caller that
    diffs before it commits - the walk comes back sized to the OLD quantity, and a diff
    against it would offer to keep a Buy for stock the customer no longer wants.

    So: when the walk's own quantity IS the old one and the line now asks for a different
    one, the CLASS TOTALS are trimmed to the new need (last rung first - Buy, then SPO,
    then Borrow, then the reserve, the reverse of the order the ladder filled them in) or
    the shortfall is added to the Buy, which is what "remaining uncovered need" already
    means. Which rungs were chosen stays the engine's answer; only the size is the line's.

    A walk sized to NEITHER quantity is left alone: that is a partially delivered line,
    where the outstanding quantity is legitimately smaller than what was ordered.
    """
    walked_raw = (
        proposal.get("qty_outstanding")
        if proposal.get("qty_outstanding") is not None
        else proposal.get("qty")
    )
    walked = _dec(walked_raw)
    old_qty = _dec(facts.get("qty_was"))
    new_qty = _dec(facts.get("qty_now"))
    if new_qty <= _ZERO or walked == new_qty or walked != old_qty:
        return proposed
    if new_qty < walked:
        over = walked - new_qty
        for klass in ("buy", "spo", "borrow", "reserve"):
            if over <= _ZERO:
                break
            cut = min(proposed[klass]["qty"], over)
            if cut <= _ZERO:
                continue
            proposed[klass]["qty"] = proposed[klass]["qty"] - cut
            over -= cut
    else:
        proposed["buy"]["qty"] = proposed["buy"]["qty"] + (new_qty - walked)
    return proposed


def _sourcing_components(
    klass: str,
    proposed: dict,
    facts: dict,
    *,
    item_code: Optional[str] = None,
    shortfall: bool = False,
    qty_was: Optional[Decimal] = None,
) -> List[dict]:
    """New sourcing for quantity the hold does not already cover, one line per source."""
    new_date = facts.get("new_date")
    out: List[dict] = []
    for qty, source in _split_over_sources(proposed["qty"], proposed["sources"]):
        location = source.get("location")
        if klass == "reserve":
            # The pool-share rung is the ONE step allowed to cover part of a unit, and only
            # inside the immediate window (rule 1), so it is named as itself rather than
            # folded into "use own" - a reader has to be able to see which one they got.
            if source.get("rung") == "pool":
                out.append(_component(
                    "use_own", "pool_share", qty,
                    f"Pool share {qty_text(qty)} at {location}" if location
                    else f"Pool share {qty_text(qty)}",
                    location=location, item_code=item_code,
                ))
            else:
                out.append(_component(
                    "use_own", "reserve", qty,
                    f"Use own {qty_text(qty)} at {location}" if location
                    else f"Use own {qty_text(qty)}",
                    location=location, item_code=item_code,
                ))
        elif klass == "borrow":
            donor = source.get("donor_so_number") or source.get("supply_document")
            whose = donor or location
            out.append(_component(
                "borrow", "borrow", qty,
                f"Borrow {qty_text(qty)} from {whose}, order-back raised" if whose
                else f"Borrow {qty_text(qty)}, order-back raised",
                location=location, target=donor, item_code=item_code,
            ))
        elif klass == "spo":
            document = source.get("supply_document")
            label = f"SPO {qty_text(qty)} on {document}" if document else f"SPO {qty_text(qty)}"
            if new_date:
                label = f"{label} for {_day(new_date)}"
            out.append(_component(
                "spo", "spo", qty, label, document=document, item_code=item_code,
            ))
        else:
            # Rule 8: inside the immediate window a purchase cannot land in time, so the
            # remainder is SAID to be short rather than promised as a Buy nobody can keep.
            label = (
                f"Short {qty_text(qty)} by {_day(new_date)}"
                if shortfall
                else f"Buy {qty_text(qty)} for {_day(new_date)}"
            )
            out.append(_component(
                "buy", "buy", qty, label, qty_was=qty_was, item_code=item_code,
            ))
    return out


def _release_components(
    held_by: Dict[str, List[Tuple[Decimal, Optional[str]]]],
    facts: dict,
    *,
    item_code: Optional[str] = None,
) -> List[dict]:
    """Every held component leaves the line: the whole hold, released or reallocated.

    A reserve FREES where it sits (or goes to the dealer pool, which wins over a waiting
    project row - rule 6); quantity on a document is REALLOCATED, because a purchase
    somebody already arranged is not given back for nothing.
    """
    dealer = bool((facts.get("dealer_hot_selling") or {}).get("value"))
    target = facts.get("reallocate_to") or "pool"
    placed = facts.get("placed") or {}
    placed_qty = _dec(placed.get("qty"))
    document = placed.get("document")
    out: List[dict] = []
    for qty, location in held_by["reserve"]:
        out.append(_component(
            "release", "reserve", qty,
            f"Release {qty_text(qty)} to dealer pool" if dealer
            else (f"Release {qty_text(qty)}, free at {location}" if location
                  else f"Release {qty_text(qty)}"),
            location=location, target="dealer pool" if dealer else None,
            item_code=item_code,
        ))
    for qty, location in held_by["borrow"]:
        out.append(_component(
            "release", "borrow", qty,
            f"Release borrow {qty_text(qty)}, the order-back is cancelled",
            location=location, item_code=item_code,
        ))
    for qty, _location in held_by["spo"]:
        out.append(_component(
            "reallocate", "spo", qty,
            f"Reallocate SPO {qty_text(qty)} to {target}",
            target=target, item_code=item_code,
        ))
    for qty, _location in held_by["buy"]:
        on_document = min(qty, placed_qty)
        unplaced = qty - on_document
        if unplaced > _ZERO:
            out.append(_component(
                "reduce", "buy", _ZERO,
                f"Reduce Buy {qty_text(unplaced)} to 0",
                qty_was=unplaced, item_code=item_code,
            ))
        if on_document > _ZERO:
            out.append(_component(
                "reallocate", "po", on_document,
                f"Reallocate {document} {qty_text(on_document)} to {target}" if document
                else f"Reallocate {qty_text(on_document)} to {target}",
                document=document, target=target, item_code=item_code,
            ))
    return out


def _keep_components(
    held_by: Dict[str, List[Tuple[Decimal, Optional[str]]]],
) -> List[dict]:
    """The hold stands as it is - what a row with no re-run to diff against can say."""
    out: List[dict] = []
    for klass in _CLASSES:
        total = sum((qty for qty, _ in held_by[klass]), _ZERO)
        if total <= _ZERO:
            continue
        label = (
            f"Keep {qty_text(total)}"
            if klass in ("reserve", "buy")
            # A borrow and an SPO share name a debt and a document, so they say which one
            # is being kept; a reserve and a Buy are the line's own and need no qualifier.
            else f"Keep {_CLASS_WORD[klass]} {qty_text(total)}"
        )
        out.append(_component(
            "keep", "po" if klass == "buy" else klass, total, label,
            location=held_by[klass][0][1] if held_by[klass] else None,
        ))
    return out


def compose_suggestion(
    kind: str, held: Optional[dict], proposal: Optional[dict], facts: dict
) -> dict:
    """The suggestion for one changed line: the re-run DIFFED against what is held.

    No I/O, no clock, no database - `kind` / `held` / `proposal` / `facts` are the wire
    shapes (`PlanningChangeKind`, `held_json`, a `BoardContribution`, `facts_json`) as
    plain dicts, and everything the diff needs that is not in the first three (what is on
    a document, where freed quantity would go, whether the new date is inside the immediate
    window) is a FACT the caller measured.

    Per held class: Keep it, Reduce it, Release it or Reallocate it; then new sourcing for
    whatever the hold does not cover (rule 3). Held components come first, in held order.

    Replaces `suggest()` and its rule table: a verb the row agreed with executed nothing,
    which is why an "accept" decision had to exist at all.
    """
    facts = facts or {}
    held_by = _held_classes(held)
    proposed = _proposed_classes(proposal)
    if proposed is not None and proposal:
        proposed = _fit_to_new_quantity(proposed, proposal, facts)
    new_date = facts.get("new_date")
    late_days: Optional[int] = None
    shortfall_qty: Optional[str] = None

    # The line is gone, or the product on it is: the whole hold leaves, whatever it was.
    if kind == "cancelled":
        return {
            "components": _release_components(held_by, facts),
            "late_days": None,
            "shortfall_qty": None,
        }
    if kind == "product_changed":
        # ONE row, never a cancelled plus an added pair (rule 5): the OLD product's hold
        # is released and the NEW product is sourced as a new line in the same row, each
        # component saying which product it is about.
        components = _release_components(
            held_by, facts, item_code=facts.get("item_code_was")
        )
        if proposed:
            for klass in _CLASSES:
                components.extend(_sourcing_components(
                    klass, proposed[klass], facts, item_code=facts.get("item_code_now"),
                ))
        return {"components": components, "late_days": None, "shortfall_qty": None}

    if proposed is None:
        # No re-run to diff against (the board could walk nothing for this line), so the
        # honest answer is that the plan stands - not a blank, and not a guess.
        return {
            "components": _keep_components(held_by),
            "late_days": None,
            "shortfall_qty": None,
        }

    placed = facts.get("placed") or {}
    placed_qty = _dec(placed.get("qty"))
    document = placed.get("document")
    target = facts.get("reallocate_to") or "pool"
    dealer = bool((facts.get("dealer_hot_selling") or {}).get("value"))
    # Rule 8: a purchase cannot land inside the immediate window, so whatever the ladder
    # leaves as a Buy for a line due that soon is a SHORTFALL, stated as one.
    immediate = bool(facts.get("immediate"))

    components: List[dict] = []
    sourced: set = set()
    for klass in _CLASSES:
        held_total = sum((qty for qty, _ in held_by[klass]), _ZERO)
        wanted = proposed[klass]["qty"]
        if held_total <= _ZERO:
            continue
        sourced.add(klass)

        if klass == "buy":
            on_document = min(held_total, placed_qty)
            unplaced = held_total - on_document
            if immediate and wanted > _ZERO:
                # The remainder stays a Buy and the board says how short the line is,
                # rather than promising a date nobody can keep.
                shortfall_qty = qty_text(wanted)
                components.extend(_sourcing_components(
                    klass, proposed[klass], facts, shortfall=True, qty_was=held_total,
                ))
                continue
            if wanted > held_total:
                # Rule 4: a top-up JOINS the held Buy, on the same inquiry row.
                components.append(_component(
                    "buy", "buy", wanted,
                    f"Buy {qty_text(wanted)} (was {qty_text(held_total)})",
                    qty_was=held_total, document=document,
                ))
                continue
            cut = held_total - wanted
            # Reduce the UNPLACED quantity first: what purchasing has not arranged yet is
            # what costs nothing to drop (S2).
            cut_unplaced = min(unplaced, cut)
            if cut_unplaced > _ZERO:
                components.append(_component(
                    "reduce", "buy", unplaced - cut_unplaced,
                    f"Reduce Buy {qty_text(unplaced)} to {qty_text(unplaced - cut_unplaced)}",
                    qty_was=unplaced,
                ))
            cut_placed = cut - cut_unplaced
            kept_placed = on_document - cut_placed
            if kept_placed > _ZERO:
                late_days = _late_days(facts, kept_placed)
                label = (
                    f"Keep {document} {qty_text(kept_placed)} of {qty_text(on_document)}"
                    if cut_placed > _ZERO and document
                    else f"Keep {qty_text(kept_placed)}"
                )
                if late_days:
                    label = f"{label}, late by {_days_word(late_days)}"
                components.append(_component(
                    "keep", "po", kept_placed, label,
                    qty_was=on_document if cut_placed > _ZERO else None,
                    document=document,
                ))
            elif cut_unplaced <= _ZERO and wanted == held_total:
                # Nothing is placed and nothing moved: the Buy stands as it is.
                components.append(_component(
                    "keep", "buy", held_total, f"Keep {qty_text(held_total)}",
                ))
            if cut_placed > _ZERO:
                components.append(_component(
                    "reallocate", "po", cut_placed,
                    f"Reallocate {document} {qty_text(cut_placed)} to {target}" if document
                    else f"Reallocate {qty_text(cut_placed)} to {target}",
                    document=document, target=target,
                ))
            continue

        if wanted == held_total:
            components.extend(_keep_components({
                k: (held_by[k] if k == klass else []) for k in _CLASSES
            }))
            continue
        if wanted > held_total:
            # A top-up of a stock hold joins the same source, the same way a Buy's does.
            components.extend(_sourcing_components(klass, proposed[klass], facts))
            continue
        if wanted > _ZERO:
            components.append(_component(
                "reduce", klass, wanted,
                f"Reduce {_CLASS_WORD[klass]} {qty_text(held_total)} to {qty_text(wanted)}",
                qty_was=held_total,
                location=held_by[klass][0][1],
            ))
            continue
        # The class leaves the line entirely.
        components.extend(_release_components(
            {k: (held_by[k] if k == klass else []) for k in _CLASSES}, facts,
        ))

    # Whatever the hold never covered at all is new sourcing, after the held components.
    for klass in _CLASSES:
        if klass in sourced or proposed[klass]["qty"] <= _ZERO:
            continue
        shortfall = klass == "buy" and immediate
        if shortfall:
            shortfall_qty = qty_text(proposed[klass]["qty"])
        components.extend(_sourcing_components(
            klass, proposed[klass], facts, shortfall=shortfall,
        ))

    return {
        "components": components,
        "late_days": late_days,
        "shortfall_qty": shortfall_qty,
    }


def _late_days(facts: dict, kept_qty: Decimal) -> Optional[int]:
    """How many days after the line's NEW date the quantity it keeps actually lands.

    Measured against the placed supply's own arrival (the PO line's expected date, else
    the purchase order's, else the date the inquiry row was raised against), because that
    is when the goods exist. `None` when the line is on time or nothing is placed - a unit
    kept late is shown as late (rule 8), never silently kept, and never flagged when it is
    not.
    """
    placed = facts.get("placed") or {}
    arrival = _as_date(placed.get("arrival_date"))
    new_date = _as_date(facts.get("new_date"))
    if kept_qty <= _ZERO or arrival is None or new_date is None:
        return None
    days = (arrival - new_date).days
    return days if days > 0 else None


def _is_null_anchored_date_move(c) -> bool:
    """A DATE_MOVED / DATE_AND_QTY_CHANGED change whose FROM or TO date is `None`.

    `days_moved` cannot be measured against a missing endpoint (`outstanding_diff.Change
    .days_moved` already returns `None` for exactly this), so there is no delay/advance to
    react to - a line getting its FIRST-EVER date, or one an upload wiped, is not a
    schedule move and must not manufacture a reaction (the 19 Aug 2026 incident: a reader
    that could not parse a serial date nulled `required_date` on 14,128 lines, and every
    one of them would otherwise have built a spurious `advanced`/`delayed` batch row).
    A pure QTY change on the same line is unaffected - only DATE-kind changes are checked.
    """
    if c.kind not in (DATE_MOVED, DATE_AND_QTY_CHANGED):
        return False
    before_date = c.before.required_date if c.before else None
    after_date = c.after.required_date if c.after else None
    return before_date is None or after_date is None


def _map_kind(c) -> str:
    if c.kind == CLOSED:
        return "cancelled"
    if c.kind == ADDED:
        return "added"
    if c.kind == PRODUCT_CHANGED:
        return "product_changed"
    if c.kind == QTY_CHANGED:
        return "qty_up" if c.qty_delta > 0 else "qty_down"
    days = c.days_moved or 0
    if c.kind == DATE_MOVED:
        return "advanced" if days < 0 else "delayed"
    # DATE_AND_QTY_CHANGED: date first (see module docstring).
    if days:
        return "advanced" if days < 0 else "delayed"
    return "qty_up" if c.qty_delta > 0 else "qty_down"


def _from_to(c) -> Tuple[dict, dict]:
    before = c.before
    after = c.after
    from_ = {
        "required_date": before.required_date.isoformat()
        if before and before.required_date
        else None,
        "qty": qty_text(_dec(before.qty)) if before else None,
        "status": "open" if before else None,
        # The OLD product, on a `product_changed` row only - `None` everywhere else, same
        # as the fields above (Slice A rule 5, "carrying the old and the new product").
        "item_code": before.item_code if (before and c.kind == PRODUCT_CHANGED) else None,
    }
    if c.kind == CLOSED:
        to_ = {"required_date": None, "qty": None, "status": "closed", "item_code": None}
    else:
        to_ = {
            "required_date": after.required_date.isoformat()
            if after and after.required_date
            else None,
            "qty": qty_text(_dec(after.qty)) if after else None,
            "status": "open" if after else None,
            "item_code": after.item_code if (after and c.kind == PRODUCT_CHANGED) else None,
        }
    return from_, to_


def _board_link(so_number: str, item_code: str, when: Optional[date]) -> str:
    when_part = when.isoformat() if when else ""
    return f"/project-sales/fulfilment-planning?orders={so_number}&cell={item_code}|{when_part}"


# ============================================================================
# Building a batch
# ============================================================================


def build_batch(
    db: Session,
    diff: Diff,
    *,
    applied_line_ids: Dict[int, str],
    order_ids: Dict[str, str],
    actor: Optional[str],
    import_job_id: Optional[str],
    file_name: Optional[str],
) -> Optional[PlanningChangeBatch]:
    """One row per changed line that is HELD by the order's ACTIVE supply decision or has a
    non-cancelled Order Inquiry row (`PLAN-scm-planning-change-gate-held-or-inquiry.md`,
    AC-G1). Being adopted onto `projects.sales_orders` is not, by itself, enough: an
    undecided line is silent, whatever changed. `None` when no changed line clears that
    gate - the caller shows nothing for such an upload - for all three triggers that call
    this function (SO book re-upload, ESB ingest, manual SO edit).

    `applied_line_ids` / `order_ids` are `outstanding_import_service.apply()`'s own local
    state, passed in because an ADDED change's `row_ref` is a source ROW NUMBER, not a
    line id, and by the time this runs the write has already happened.
    """
    from app.services.project_fulfilment_board_service import FulfilmentBoardService
    from app.services.project_supply_service import ProjectSupplyService

    changed = []
    for c in diff.changes:
        if c.kind == "unchanged":
            continue
        if c.kind == ADDED and states_settled(c.after):
            # A line that ARRIVES already delivered asks for no reaction: there is nothing
            # left to plan, source or promise. It is only reachable since the upload became
            # the whole order book, and without this a completed year would raise a batch of
            # thousands of "added" rows about deliveries that happened months ago.
            continue
        if _is_null_anchored_date_move(c):
            logger.debug(
                "planning change: skipping %s on %s / %s - a null-anchored date move "
                "builds no reaction", c.kind, c.doc_number, c.item_code,
            )
            continue
        changed.append(c)
    if not changed:
        return None

    core_line_ids = {applied_line_ids.get(id(c)) for c in changed}
    core_line_ids.discard(None)
    project_lines_by_core: Dict[str, ProjectSalesOrderLine] = {}
    if core_line_ids:
        for pl in (
            db.query(ProjectSalesOrderLine)
            .filter(ProjectSalesOrderLine.core_sales_order_line_id.in_(list(core_line_ids)))
            .all()
        ):
            project_lines_by_core[str(pl.core_sales_order_line_id)] = pl

    order_core_ids = {v for v in order_ids.values() if v}
    pso_by_core_so: Dict[str, ProjectSalesOrder] = {}
    if order_core_ids:
        for pso in (
            db.query(ProjectSalesOrder)
            .filter(ProjectSalesOrder.so_id.in_(list(order_core_ids)))
            .all()
        ):
            pso_by_core_so[str(pso.so_id)] = pso

    entries: List[dict] = []
    for c in changed:
        core_line_id = applied_line_ids.get(id(c))
        if not core_line_id:
            continue
        if c.kind == ADDED:
            core_so_id = order_ids.get(c.doc_number)
            pso = pso_by_core_so.get(str(core_so_id)) if core_so_id else None
            if pso is None:
                continue
            entries.append(
                {"change": c, "core_line_id": core_line_id, "project_line": None, "order": pso}
            )
            continue
        project_line = project_lines_by_core.get(core_line_id)
        if project_line is None:
            continue
        pso = (
            db.query(ProjectSalesOrder)
            .filter(ProjectSalesOrder.id == project_line.project_sales_order_id)
            .one_or_none()
        )
        if pso is None:
            continue
        entries.append(
            {
                "change": c,
                "core_line_id": core_line_id,
                "project_line": project_line,
                "order": pso,
            }
        )

    if not entries:
        return None

    core_line_ids_all = [e["core_line_id"] for e in entries]
    product_by_core: Dict[str, Optional[str]] = {}
    for cid, pid in (
        db.query(SalesOrderLine.id, SalesOrderLine.product_id)
        .filter(SalesOrderLine.id.in_(core_line_ids_all))
        .all()
    ):
        product_by_core[str(cid)] = str(pid) if pid else None

    for e in entries:
        e["product_id"] = product_by_core.get(e["core_line_id"])

    product_ids = {e["product_id"] for e in entries if e["product_id"]}
    moved_transfers = _moved_transfers(db, core_line_ids_all)
    dealer_where, project_where = _hot_selling_evidence(db, product_ids)
    discontinued_ids = _discontinued_products(db, product_ids)
    product_names = _product_names(db, product_ids)

    by_order: Dict[str, List[dict]] = defaultdict(list)
    for e in entries:
        by_order[str(e["order"].id)].append(e)

    # The id is generated here, not left to the column default, so a kept `PlanningChangeRow`
    # can carry `batch_id` before the batch itself is ever added to the session - the empty
    # case (1,307 of 1,308 changed lines on the 10 Sep live measurement) is the COMMON path
    # under the held-or-inquiry gate, so it must not pay for an INSERT it then has to DELETE.
    batch = PlanningChangeBatch(
        id=str(uuid.uuid4()),
        import_job_id=import_job_id,
        upload_file_name=file_name,
        created_by=actor,
    )

    supply = ProjectSupplyService(db)
    # Keyed `(so_number, project_line_id)`, not just `so_number` - see `_proposal_for`.
    board_cache: Dict[Tuple[str, Optional[str]], dict] = {}

    kept_orders: set = set()
    kept_rows: List[PlanningChangeRow] = []
    for pso_id, group in by_order.items():
        order = group[0]["order"]
        active_decision = supply.active_decision(pso_id)
        latest_decision = supply.latest_decision(pso_id)
        revision_no = (
            active_decision.revision_no
            if active_decision
            else (latest_decision.revision_no if latest_decision else 0)
        )
        frozen = supply.frozen_lines_of(active_decision)
        so_number = _so_number(order)
        # Only asked when the group actually carries an `added` change - the order-level
        # half of the gate a new line needs (rule 5: "an ADDED change... is raised when the
        # ORDER has at least one held or inquiry line"), and most groups have none.
        order_has_held_or_inquiry = (
            _order_has_held_or_inquiry(db, pso_id, frozen)
            if any(e["change"].kind == ADDED for e in group)
            else False
        )
        for e in group:
            row = _build_row(
                db,
                batch,
                order,
                e,
                frozen,
                revision_no,
                dealer_where,
                project_where,
                discontinued_ids,
                product_names,
                board_cache,
                so_number,
                moved_transfers,
                order_has_held_or_inquiry,
            )
            if row is None:
                # AC-G1/AC-G4: the line is neither held nor inquired, so it stays off the
                # batch entirely - not a row worth counting.
                continue
            kept_orders.add(pso_id)
            kept_rows.append(row)

    if not kept_rows:
        # Every changed line on this upload/edit failed the held-or-inquiry gate: there is
        # nothing to re-decide, so no batch is ever written for the pill to point at.
        return None

    batch.order_count = len(kept_orders)
    batch.line_count = len(kept_rows)
    db.add(batch)
    for row in kept_rows:
        db.add(row)
    db.flush()
    return batch


def pending_batch_id_by_sales_order(
    db: Session, sales_order_ids: Sequence[str],
) -> Dict[str, str]:
    """The newest PENDING planning-change batch per core `sales_orders.id`, one query.

    `PLAN-scm-board-picks-up-pending-change.md` change 1: the body `SalesOrderService
    .with_planning_changes` used to keep for itself, lifted out here so the fulfilment
    board and the fulfilment-planning list can name the same batch the SCM Sales Orders
    list already does - one rule, three readers. "Pending" means the batch itself is
    unapplied (`applied_at IS NULL`) AND the row is `applied_state == 'pending'`
    (`PLAN-scm-planning-change-gate-held-or-inquiry.md`, AC-G5): a batch left open but
    whose only rows were superseded by the held-or-inquiry gate has nothing left to
    decide either. `{}` for an empty `sales_order_ids`; an id with nothing pending is
    simply absent from the returned dict (never a `None` value), so a caller uses
    `.get(so_id)`.
    """
    if not sales_order_ids:
        return {}

    from app.models.planning_change import PlanningChangeBatch, PlanningChangeRow

    found = (
        db.query(ProjectSalesOrder.so_id, PlanningChangeBatch.id)
        .join(PlanningChangeRow,
              PlanningChangeRow.project_sales_order_id == ProjectSalesOrder.id)
        .join(PlanningChangeBatch,
              PlanningChangeBatch.id == PlanningChangeRow.batch_id)
        .filter(
            ProjectSalesOrder.so_id.in_(list(sales_order_ids)),
            PlanningChangeBatch.applied_at.is_(None),
            PlanningChangeRow.applied_state == PLANNING_CHANGE_STATE_PENDING,
        )
        .order_by(PlanningChangeBatch.created_at.desc())
        .all()
    )
    result: Dict[str, str] = {}
    for so_id, batch_id in found:
        # The NEWEST pending batch wins: rows arrive newest-batch-first, and a second
        # pass for the same order must not overwrite it with an older one.
        result.setdefault(str(so_id), str(batch_id))
    return result


def _so_number(order: ProjectSalesOrder) -> str:
    return order.autocount_doc_no or order.provisional_ref or str(order.id)


def _order_has_held_or_inquiry(
    db: Session, pso_id: str, frozen: Dict[str, dict]
) -> bool:
    """Whether ANY line on this order is held by its active decision or carries a
    non-cancelled Order Inquiry row.

    A new line (`added`) has no mirror line of its own yet, so the per-line held-or-inquiry
    gate `_build_row` asks every other kind can never pass it - it is asked of the ORDER
    instead (Slice A rule 5): a line added to an order nobody has decided anything on is
    silent, exactly like any other change to an undecided order, but a line added to an
    order that already carries a commitment is exactly the kind of exception the gate exists
    to surface.
    """
    if frozen:
        return True
    return (
        db.query(OrderInquiryRow.id)
        .join(ProjectSalesOrderLine, OrderInquiryRow.so_line_id == ProjectSalesOrderLine.id)
        .filter(
            ProjectSalesOrderLine.project_sales_order_id == pso_id,
            OrderInquiryRow.state != INQUIRY_CANCELLED,
        )
        .first()
        is not None
    )


def _hot_selling_evidence(
    db: Session, product_ids: set
) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """Dealer / project hot-selling evidence: locations holding ABC A on that demand class.

    A lightweight standalone read rather than `ProjectSupplyService._classification` (which
    another slice is actively editing for wording/evidence): same predicate, same columns.
    """
    if not product_ids:
        return {}, {}
    rows = (
        db.query(
            ItemClassification.product_id,
            ItemClassification.abc_class_retail,
            ItemClassification.abc_class_project,
            Warehouse.warehouse_code,
        )
        .join(Warehouse, Warehouse.id == ItemClassification.warehouse_id)
        .filter(
            ItemClassification.product_id.in_(list(product_ids)),
            Warehouse.is_active.is_(True),
            Warehouse.counts_as_available.is_(True),
        )
        .all()
    )
    dealer_where: Dict[str, List[str]] = {}
    project_where: Dict[str, List[str]] = {}
    for pid, abc_retail, abc_project, code in rows:
        pid = str(pid)
        if (abc_retail or "").upper() == "A":
            dealer_where.setdefault(pid, []).append(code or "")
        if (abc_project or "").upper() == "A":
            project_where.setdefault(pid, []).append(code or "")
    for codes in dealer_where.values():
        codes.sort()
    for codes in project_where.values():
        codes.sort()
    return dealer_where, project_where


def _discontinued_products(db: Session, product_ids: set) -> set:
    if not product_ids:
        return set()
    rows = (
        db.query(Product.id)
        .filter(Product.id.in_(list(product_ids)), Product.is_discontinued.is_(True))
        .all()
    )
    return {str(r[0]) for r in rows}


def _product_names(db: Session, product_ids: set) -> Dict[str, str]:
    if not product_ids:
        return {}
    rows = db.query(Product.id, Product.product_name).filter(Product.id.in_(list(product_ids))).all()
    return {str(pid): name for pid, name in rows}


def _held_from_frozen(frozen_entry: dict, revision_no: int) -> dict:
    components = frozen_entry.get("components") or []
    reserve = [
        {
            "location": c.get("source_location"),
            "warehouse_id": c.get("source_warehouse_id"),
            "qty": c.get("qty"),
        }
        for c in components
        if c.get("kind") == RESERVE
    ]
    borrow = [
        {
            "location": c.get("source_location"),
            "warehouse_id": c.get("source_warehouse_id"),
            "qty": c.get("qty"),
            "source": c.get("source"),
        }
        for c in components
        if c.get("kind") == BORROW
    ]
    buy_qty = sum((_dec(c.get("qty")) for c in components if c.get("kind") == BUY), _ZERO)
    timely_qty = sum(
        (_dec(c.get("qty")) for c in components if c.get("kind") == TIMELY_SPO), _ZERO
    )
    return {
        "reserve": reserve,
        "borrow": borrow,
        "buy_qty": qty_text(buy_qty),
        "timely_spo_qty": qty_text(timely_qty),
        "revision_no": revision_no,
    }


def _inquiry_rows_and_buy_actioned(
    db: Session, project_line_id: Optional[str]
) -> Tuple[List[dict], dict]:
    """`buy_actioned` reads `INQUIRY_PLACED` as actioned too, not `INQUIRY_ACTIONED` alone.

    The live "Place on PO" path (section G) is what actually moves a Buy row off
    `raised` today - `mark_rows` (the only writer of `INQUIRY_ACTIONED`) is not called
    for an ORDER row on the real workflow anymore. A predicate that recognised only
    `actioned` read every placed row's Buy as still-open, which is what let a `qty_up`
    reconfirm run the FULL ladder for a line that already had real placed supply (Case B,
    the captain, 20 Aug: SRTWC287A-RL, placed 5, no active decision, `buy_actioned=false`
    let the board propose Reserve 10 - 15 against a 10 line).

    `"qty"` is the SUM of every currently placed-or-actioned Buy on the line (there can be
    more than one, e.g. a cascade split across several PO lines) - `_apply_placed_offset`
    below is what actually spends it, netting the board's own fresh proposal down to the
    uncovered remainder.
    """
    if not project_line_id:
        return [], {"value": False, "po_number": None, "qty": qty_text(_ZERO)}
    rows = (
        db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.so_line_id == project_line_id,
            OrderInquiryRow.state != INQUIRY_CANCELLED,
        )
        .order_by(OrderInquiryRow.created_at.desc())
        .all()
    )
    out = [
        {
            "id": str(r.id),
            "verb": r.verb,
            "qty": qty_text(_dec(r.qty)),
            "state": r.state,
        }
        for r in rows
    ]
    committed = [
        r
        for r in rows
        if r.state in (INQUIRY_ACTIONED, INQUIRY_PLACED)
        and r.verb in (IV_ORDER, IV_RESERVE_AND_ORDER)
        # A row a PRIOR planning change already redirected to replenish the pool no
        # longer serves this line - it must not be read back as still-placed cover for
        # it, or a second pass would offset against the same PO twice.
        and not r.redirected_to_pool
    ]
    actioned_buy = committed[0] if committed else None
    placed_qty = sum((_dec(r.qty) for r in committed), _ZERO)
    return out, {
        "value": actioned_buy is not None,
        # `po_ref` is the section-G placement tag (the modern field); `spo_ref` is kept as
        # a fallback for whatever an older `actioned` row may have carried it in.
        "po_number": (actioned_buy.po_ref or actioned_buy.spo_ref) if actioned_buy else None,
        "qty": qty_text(placed_qty),
    }


def _placed_links(db: Session, project_line_id: Optional[str]) -> dict:
    """The quantity of this line's demand that is already ON a document, and which one.

    Read off `OrderInquiryLink` rather than off the row's own state, because a row placed
    for PART of its quantity reads `partly_linked` and keeps its full demand (S2's own
    shape: 234 raised, 134 on a purchase order, 100 still unlinked) - a state check would
    see nothing placed there and the suggestion would offer to drop a real purchase order.

    `arrival_date` is when that supply is expected: the purchase order LINE's own date,
    else the order's, else the date the inquiry row was raised against - the date the
    purchase was placed to meet. It is what "late by N days" is measured from.
    """
    empty = {"qty": qty_text(_ZERO), "document": None, "arrival_date": None}
    if not project_line_id:
        return empty
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine

    rows = (
        db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.so_line_id == project_line_id,
            OrderInquiryRow.state != INQUIRY_CANCELLED,
            OrderInquiryRow.verb.in_((IV_ORDER, IV_RESERVE_AND_ORDER)),
        )
        .all()
    )
    row_ids = [str(r.id) for r in rows]
    if not row_ids:
        return empty
    links = (
        db.query(OrderInquiryLink)
        .filter(OrderInquiryLink.row_id.in_(row_ids))
        .order_by(OrderInquiryLink.linked_at.asc())
        .all()
    )
    if not links:
        return empty
    total = sum((_dec(link.qty) for link in links), _ZERO)
    document = next((link.document for link in links if link.document), None)
    po_line_ids = [str(link.po_line_id) for link in links if link.po_line_id]
    arrivals: List[date] = []
    if po_line_ids:
        for line_date, order_date in (
            db.query(PurchaseOrderLine.expected_date, PurchaseOrder.expected_date)
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
            .filter(PurchaseOrderLine.id.in_(po_line_ids))
            .all()
        ):
            when = line_date or order_date
            if when:
                arrivals.append(when)
    if not arrivals:
        # Nothing on the document says when: the purchase was placed to meet the date the
        # row asked for, so that is the honest expectation.
        arrivals = [r.delivery_date for r in rows if r.delivery_date]
    return {
        "qty": qty_text(total),
        "document": document,
        # The LATEST, because the line is only whole when the last of it lands.
        "arrival_date": max(arrivals).isoformat() if arrivals else None,
    }


def _reallocation_target(
    db: Session,
    project_line_id: Optional[str],
    product_id: Optional[str],
    dealer_hot_selling: bool,
) -> str:
    """Where freed stock or freed document quantity would go, IN WORDS (rule 6, AC-D6).

    Naming only - Slice D is what actually moves it - so this answers the same question the
    linking engine will, in the same order: the dealer pool if the product is dealer
    hot-selling (retail wins over a waiting project row, the grill page's own 3.1); else
    the raised or partly-linked ORDER row with unlinked quantity that the linking engine
    would deal to first (`_rank_raised_rows`, the one priority policy); else the pool.
    """
    if dealer_hot_selling:
        return "dealer pool"
    if not product_id:
        return "pool"
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    candidates = (
        db.query(OrderInquiryRow)
        .join(
            ProjectSalesOrderLine,
            ProjectSalesOrderLine.id == OrderInquiryRow.so_line_id,
        )
        .filter(
            ProjectSalesOrderLine.product_id == product_id,
            OrderInquiryRow.so_line_id != project_line_id,
            OrderInquiryRow.verb.in_((IV_ORDER, IV_RESERVE_AND_ORDER)),
            OrderInquiryRow.state.in_(("raised", INQUIRY_PARTLY_LINKED)),
        )
        .order_by(
            OrderInquiryRow.delivery_date.asc().nullslast(),
            OrderInquiryRow.created_at.asc(),
        )
        .all()
    )
    if not candidates:
        return "pool"
    linked_by_row: Dict[str, Decimal] = defaultdict(lambda: _ZERO)
    for row_id, qty in (
        db.query(OrderInquiryLink.row_id, OrderInquiryLink.qty)
        .filter(OrderInquiryLink.row_id.in_([str(r.id) for r in candidates]))
        .all()
    ):
        linked_by_row[str(row_id)] += _dec(qty)
    open_rows = [
        (r, _dec(r.qty) - linked_by_row[str(r.id)])
        for r in candidates
    ]
    open_rows = [(r, unlinked) for r, unlinked in open_rows if unlinked > _ZERO]
    if not open_rows:
        return "pool"
    try:
        ranked = ProjectOrderInquiryService(db)._rank_raised_rows([r for r, _ in open_rows])
        best = ranked[0] if ranked else open_rows[0][0]
    except Exception:  # noqa: BLE001 - naming a target is a nicety, never a build blocker
        logger.exception("planning change: ranking reallocation candidates failed")
        best = open_rows[0][0]
    unlinked = next((q for r, q in open_rows if str(r.id) == str(best.id)), _ZERO)
    so_number = (
        db.query(ProjectSalesOrder)
        .join(
            ProjectSalesOrderLine,
            ProjectSalesOrderLine.project_sales_order_id == ProjectSalesOrder.id,
        )
        .filter(ProjectSalesOrderLine.id == best.so_line_id)
        .with_entities(ProjectSalesOrder.autocount_doc_no, ProjectSalesOrder.provisional_ref)
        .first()
    )
    label = (so_number[0] or so_number[1]) if so_number else None
    verb = "ORDER BACK" if best.verb == IV_ORDER_BACK else "ORDER"
    return f"{label} {verb} {qty_text(unlinked)}" if label else "pool"


def _is_immediate(new_date: Optional[date]) -> bool:
    """Is the line due inside the ladder's own immediate window?

    The window is the LADDER's (`DEFAULT_IMMEDIATE_WINDOW_DAYS`), read from it rather than
    restated here: rule 2 retired this service's own `RESERVE_WINDOW_DAYS` for exactly the
    reason a second constant would disagree with the engine that decides.
    """
    from app.services.scm.front_planning_engine import DEFAULT_IMMEDIATE_WINDOW_DAYS

    if new_date is None:
        return False
    from datetime import timedelta

    return new_date <= date.today() + timedelta(days=DEFAULT_IMMEDIATE_WINDOW_DAYS)


def _proposal_for(
    db: Session, board_cache: Dict[Tuple[str, Optional[str]], dict], so_number: str,
    core_line_id: str, project_line_id: Optional[str],
) -> Optional[dict]:
    """The board's own contribution for this line - the FULL `BoardContribution` a `replan`
    row shows its ladder from, not a slimmed-down copy of it.

    An active decision still covers most `replan` lines (their own hold has not been touched
    yet - Apply is what excludes them), so a plain `build()` would find them `covered` and
    hand back the FROZEN composition (one source, no trail) rather than the fresh proposal
    the row's own `why` promises. `exclude_covered_line_ids` previews this ONE line as if that
    hold did not exist, the same carve-out `confirm` gives a line it is about to replace, so
    the ladder is actually walked and the trail/sources/rank_factors are the real ones.

    Cached per `(so_number, project_line_id)` rather than per `so_number` alone: two different
    `replan` lines on the same order need two different builds, each excluding only its OWN
    line - every other line of the order stays covered by its real, undisturbed hold.
    """
    from app.services.project_fulfilment_board_service import FulfilmentBoardService

    cache_key = (so_number, project_line_id)
    board = board_cache.get(cache_key)
    if board is None:
        try:
            board = FulfilmentBoardService(db).build(
                [so_number],
                granularity="week",
                exclude_covered_line_ids=[project_line_id] if project_line_id else None,
            )
        except Exception:  # noqa: BLE001 - a proposal is a nicety, never a build blocker
            logger.exception("planning change proposal build failed for %s", so_number)
            board = {}
        board_cache[cache_key] = board
    for cell in board.get("cells", []) or []:
        for contribution in cell.get("contributions", []) or []:
            if contribution.get("line_id") == core_line_id or (
                project_line_id and contribution.get("project_line_id") == project_line_id
            ):
                return contribution
    return None


def _placed_offset_note(qty: Decimal, po_number: Optional[str]) -> str:
    po_text = f" on {po_number}" if po_number else ""
    return f"{qty_text(qty)} already placed{po_text}, kept as the buy"


def _trim_sources_for_offset(
    sources: List[dict], kind: str, take: Decimal
) -> Tuple[List[dict], List[Tuple[Optional[str], Decimal]]]:
    """Removes `take` from `sources`' own entries of `kind`, LARGEST-first - the same
    convention `_confirm_payload_reduce` already trims Reserve/Borrow components by - so
    the sources list keeps agreeing with whatever `_apply_placed_offset` just moved off
    the matching aggregate. Returns the trimmed list and, in the order trimmed, each
    cut's `(location, qty)` for `_annotate_trail_for_offset` to match against the trail.
    """
    if take <= _ZERO:
        return sources, []
    order = sorted(
        (i for i, s in enumerate(sources) if s.get("kind") == kind),
        key=lambda i: -_dec(sources[i].get("qty")),
    )
    remaining = take
    cuts: List[Tuple[Optional[str], Decimal]] = []
    out = list(sources)
    drop: set = set()
    for i in order:
        if remaining <= _ZERO:
            break
        qty = _dec(sources[i].get("qty"))
        cut = min(qty, remaining)
        if cut <= _ZERO:
            continue
        cuts.append((sources[i].get("location"), cut))
        left = qty - cut
        if left > _ZERO:
            out[i] = dict(sources[i], qty=qty_text(left))
        else:
            drop.add(i)
        remaining -= cut
    if drop:
        out = [s for idx, s in enumerate(out) if idx not in drop]
    return out, cuts


def _annotate_trail_for_offset(
    trail: List[dict], cuts: List[Tuple[Optional[str], Decimal]], trail_kinds: frozenset,
    po_number: Optional[str],
) -> List[dict]:
    """Narrates what `_trim_sources_for_offset` just did, on the trail step that matches
    each cut's location - so a step reading "pool took 432 at BRW" does not stand next to
    a Buy that quietly grew by the same 432 with nothing on screen explaining why. The
    trail's own `taken`/`remaining_after` are left alone: they are a historical, honest
    record of what the ladder actually walked; only a `note` is appended, saying what
    happened to that quantity AFTER the ladder ran.

    THE LOCATION MATCH FALLS BACK TO THE KIND (ladder v5). A step carries ONE location -
    question 1's is the line's own - while the water it drew may be coming to a sibling, so
    an exact match on the code silently annotated nothing and the step went on claiming a
    quantity the aggregate no longer credited it with. Matching the code is still tried
    first, because it is the precise answer when there is one; the kind is what is left when
    the step and the cut disagree about where, and they are still talking about the same
    rung."""
    if not cuts or not trail:
        return trail
    out = [dict(step) for step in trail]
    pending = list(cuts)
    for step in out:
        if not pending or step.get("kind") not in trail_kinds:
            continue
        match_idx = next(
            (idx for idx, c in enumerate(pending) if c[0] == step.get("location")), None
        )
        if match_idx is None:
            match_idx = 0
        _location, qty = pending.pop(match_idx)
        note = _placed_offset_note(qty, po_number)
        existing = step.get("note")
        step["note"] = f"{existing}; {note}" if existing else note
    return out


def _apply_placed_offset(
    proposal: dict, placed_qty: Decimal, po_number: Optional[str] = None
) -> dict:
    """Reconciles a fresh proposal against quantity this line's already PLACED on a real
    purchase order, which the board's own ladder cannot see (`_proposal_for`'s docstring).

    **The captain's ruling, 21 Aug 2026** (reversing this function's first cut, on
    SO397450 / SRT382-6-DIY: an advance whose proposal took 432 from the pool at BRW while
    432 was already placed on a PO to the line's own bin): "instead of taking the 432 from
    this PO to BRW-BB, it needs to be placed to the BRW: now that the advancement has
    taken the stock from BRW, there needs to be some replenishment to BRW, hence this
    order inquiry should change to location BRW, and it takes the outstanding PO to BRW."

    So when the fresh proposal itself draws on the shared pool, **the pool take STANDS** -
    the composition keeps that Reserve, and the placed PO(s) behind the overlapping
    quantity are REDIRECTED (by `_apply_placed_redirect`, at Apply, once a line's
    composition is actually posted) to replenish the pool instead of being relabelled onto
    Buy as if they no longer existed. `redirect_qty` below is that overlap - never more
    than `reserve`, which is already the ladder's own capacity-capped, affordable figure,
    so a redirect never claims more pool cover than the line was actually offered.

    **THE WATER IS OFFSET FIRST** (ladder v5's second pass, 27 August 2026). A placed PO is
    expected supply this line has already ordered, and so is the SPO share question 1 draws
    off the ownership group's net (`timely_spo`) - two promises of the same delivery, and
    counting both would promise the line twice. So `incoming` is relabelled onto Buy before
    anything is redirected: a PO replaces expected supply before it displaces stock on a
    floor, which is what the pool redirect does. Under v4 the live ladder proposed no
    incoming at all, so the order was invisible; under v5 it decides the answer.

    **Whatever `placed_qty` the water cannot cover then falls to the pool redirect**, capped
    at `reserve` so it never claims more pool cover than the line was actually offered. A
    pure-Buy proposal with no pool source at all (`reserve == 0`) redirects nothing, and the
    whole `placed_qty` is relabelled off `incoming` and added onto Buy exactly as before the
    ruling, with `sources`/`trail` trimmed in step (`_trim_sources_for_offset` /
    `_annotate_trail_for_offset`) so a stored proposal's own trail narrative never again
    claims a rung took stock the aggregate no longer credits it with (the original defect
    this function shipped with, on the same live row).
    """
    if placed_qty <= _ZERO:
        return proposal
    out = dict(proposal)
    reserve = _dec(out.get("qty_proposed_reserve"))
    incoming = _dec(out.get("qty_proposed_incoming"))
    buy = _dec(out.get("qty_proposed_buy"))
    sources = list(out.get("sources") or [])
    trail = list(out.get("trail") or [])

    # 1. The water. Relabelled onto Buy, because the PO already bought it.
    take = min(placed_qty, incoming)
    if take > _ZERO:
        incoming -= take
        buy += take
        sources, cuts = _trim_sources_for_offset(sources, "timely_spo", take)
        # `incoming` is the RETIRED rung 1's step key, kept for a stored proposal written
        # under it; `own` is where a v5 trail carries the water, because question 1 is what
        # draws it now. Both, so one function narrates a trail of either shape.
        trail = _annotate_trail_for_offset(
            trail, cuts, frozenset({"incoming", "own"}), po_number
        )

    # 2. What is left of the placed quantity, against the pool take. Capped at `reserve`
    #    (never invents cover the ladder did not offer). `reserve` itself is untouched -
    #    the redirect acts on the real PO rows at Apply (`_apply_placed_redirect`), never
    #    on this figure.
    redirect_qty = min(placed_qty - take, reserve)

    out["qty_proposed_reserve"] = qty_text(reserve)
    out["qty_proposed_incoming"] = qty_text(incoming)
    out["qty_proposed_buy"] = qty_text(buy)
    out["sources"] = sources
    out["trail"] = trail
    # Read back at Apply (`_apply_placed_redirect`) to know how much already-placed PO
    # quantity the pool take covers, and so needs redirecting rather than leaving on the
    # line. "0" (never absent) so a reader never has to guess whether the key was skipped.
    out["placed_redirect_qty"] = qty_text(redirect_qty)
    return out


def _moved_transfers(db: Session, core_line_ids: Sequence[str]) -> Dict[str, str]:
    """Stock that has ALREADY physically moved for each of these lines, in one phrase.

    AC-P3-9, the captain's own rule: "a Transfer already MOVED for a line now retired -
    flag on the change row, no automatic reverse. Stock moves are physical; a person
    decides." So this states the fact and nothing else writes anything because of it.

    Only `moved` rows: a `proposed` or `approved` transfer is paperwork the confirmation
    already supersedes on its own (`project_supply_service._write_transfers`), and saying
    a warehouse moved something it has not is worse than saying nothing.
    """
    wanted = [str(line_id) for line_id in core_line_ids if line_id]
    if not wanted:
        return {}
    # Two plain reads rather than one aliased join: the company-scope filter this session
    # carries rewrites a joined `warehouses` predicate against the table name, and an
    # ALIASED join then references a FROM entry that is not there (Postgres says so
    # outright). The warehouse codes are a handful of rows either way.
    rows = (
        db.query(StockTransfer)
        .filter(
            StockTransfer.so_line_id.in_(wanted),
            StockTransfer.state == TRANSFER_MOVED,
        )
        .order_by(StockTransfer.moved_at.asc().nullslast())
        .all()
    )
    if not rows:
        return {}
    warehouse_ids = {str(t.from_warehouse_id) for t in rows} | {
        str(t.to_warehouse_id) for t in rows
    }
    codes = {
        str(wid): code
        for wid, code in db.query(Warehouse.id, Warehouse.warehouse_code)
        .filter(Warehouse.id.in_(list(warehouse_ids)))
        .all()
    }
    out: Dict[str, List[str]] = defaultdict(list)
    for transfer in rows:
        source = codes.get(str(transfer.from_warehouse_id)) or "somewhere"
        target = codes.get(str(transfer.to_warehouse_id)) or "somewhere"
        out[str(transfer.so_line_id)].append(
            f"{qty_text(_dec(transfer.qty))} moved {source} -> {target}"
        )
    return {line_id: ", ".join(parts) for line_id, parts in out.items()}


def _build_row(
    db: Session,
    batch: PlanningChangeBatch,
    order: ProjectSalesOrder,
    entry: dict,
    frozen: Dict[str, dict],
    revision_no: int,
    dealer_where: Dict[str, List[str]],
    project_where: Dict[str, List[str]],
    discontinued_ids: set,
    product_names: Dict[str, str],
    board_cache: Dict[Tuple[str, Optional[str]], dict],
    so_number: str,
    moved_transfers: Optional[Dict[str, str]] = None,
    order_has_held_or_inquiry: bool = False,
) -> Optional[PlanningChangeRow]:
    c = entry["change"]
    project_line: Optional[ProjectSalesOrderLine] = entry["project_line"]
    product_id = entry.get("product_id")
    kind = _map_kind(c)
    from_json, to_json = _from_to(c)
    days_moved = c.days_moved

    project_line_id = str(project_line.id) if project_line else None
    frozen_entry = frozen.get(project_line_id) if project_line_id else None
    held = _held_from_frozen(frozen_entry, revision_no) if frozen_entry else None

    new_date = _as_date(to_json.get("required_date")) or _as_date(from_json.get("required_date"))
    old_date = _as_date(from_json.get("required_date"))

    inquiry_rows, buy_actioned = _inquiry_rows_and_buy_actioned(db, project_line_id)

    if held is None and not inquiry_rows:
        # `PLAN-scm-planning-change-gate-held-or-inquiry.md`, AC-G1: a change to a line
        # nobody has decided on invalidates nothing a person committed to, so it raises no
        # row. Checked before any of the expensive work below (`_proposal_for` walks the
        # fulfilment board's ladder) since most changed lines take this exit.
        #
        # `added` is the one exception (`PLAN-scm-change-management-one-engine.md` Slice A
        # rule 5): a new line has no mirror line to hold or inquire about YET, so the gate
        # is asked of the ORDER instead - an order with a held or inquired line already
        # carries a commitment the new line changes the shape of.
        if not (c.kind == ADDED and order_has_held_or_inquiry):
            return None

    dealer_hot_selling = bool(product_id and product_id in dealer_where)
    placed = _placed_links(db, project_line_id)
    facts = {
        "dealer_hot_selling": {
            "value": dealer_hot_selling,
            "where": dealer_where.get(product_id, []) if product_id else [],
        },
        "project_hot_selling": {
            "value": bool(product_id and product_id in project_where),
            "where": project_where.get(product_id, []) if product_id else [],
        },
        "discontinued": bool(product_id and product_id in discontinued_ids),
        "days_moved": days_moved or 0,
        "buy_actioned": buy_actioned,
        # What is already on a purchase order for this line, and when it lands (S2, S12).
        "placed": placed,
        # The three the DIFF needs that are not on the line itself. Stored on `facts_json`
        # rather than passed around, so a row can be re-read later and say what its own
        # suggestion was composed against; not on the wire (like `moved_transfer`, which
        # `row_out` lifts out of here), because nothing on screen compares them.
        "new_date": new_date.isoformat() if new_date else None,
        "old_date": old_date.isoformat() if old_date else None,
        "qty_was": from_json.get("qty"),
        "qty_now": to_json.get("qty"),
        "immediate": _is_immediate(new_date),
    }
    if _dec(placed.get("qty")) > _ZERO or _dec((held or {}).get("timely_spo_qty")) > _ZERO:
        # Only asked when something could actually be freed - it ranks every waiting row
        # for the product, and most changed lines free nothing.
        facts["reallocate_to"] = _reallocation_target(
            db, project_line_id, product_id, dealer_hot_selling
        )
    if kind == "product_changed":
        facts["item_code_was"] = from_json.get("item_code")
        facts["item_code_now"] = to_json.get("item_code") or c.item_code

    # AC-P3-9: stock that has already physically moved for this line. On `facts_json`
    # rather than a column of its own - it is a fact the row states, exactly like the
    # others here, and it needs no migration to say it. `row_out` lifts it to the wire,
    # where a phrase reads better than a fact object nobody compares against anything.
    moved = (moved_transfers or {}).get(str(entry["core_line_id"]))
    if moved:
        facts["moved_transfer"] = (
            f"{moved}, line cancelled" if kind == "cancelled" else moved
        )

    # THE RE-RUN, for every kind on a line that still exists (rule 3): the suggestion is
    # the diff of it against the hold, so a row without it has nothing to diff. Skipped for
    # `cancelled` alone - the line is gone, so there is nothing to walk the ladder for.
    proposal = None
    if kind != "cancelled":
        proposal = _json_safe(
            _proposal_for(db, board_cache, so_number, entry["core_line_id"], project_line_id)
        )
        if proposal:
            proposal = _apply_placed_offset(
                proposal, _dec(buy_actioned.get("qty")), buy_actioned.get("po_number")
            )

    suggestion = compose_suggestion(kind, held, proposal, facts)
    # PRE-FILLED (Slice C contract A): Confirm posts this unchanged and Amend edits it, so
    # the composition a row shows is the one it will actually post. `set_row_decision`
    # still validates it against the line's open quantity when the decision is taken.
    composition = composition_from_proposal(proposal) or None

    board_link = _board_link(so_number, c.item_code, new_date or old_date)

    return PlanningChangeRow(
        batch_id=batch.id,
        project_sales_order_id=str(order.id),
        project_line_id=project_line_id,
        core_line_id=entry["core_line_id"],
        line_no=(project_line.line_no if project_line else None),
        item_code=c.item_code,
        product_name=product_names.get(product_id) if product_id else None,
        kind=kind,
        from_json=from_json,
        to_json=to_json,
        days_moved=days_moved,
        held_json=held,
        facts_json=facts,
        inquiry_rows_json=inquiry_rows,
        suggestion_json=suggestion,
        proposal_json=proposal,
        composition_json=composition,
        # UNDECIDED until CS says otherwise (AC-C7). There is no default agreement any
        # more: a row is Confirmed or Amended by a person, and nothing else applies it.
        decision=None,
        applied_state=PLANNING_CHANGE_STATE_PENDING,
        board_link=board_link,
    )


# ============================================================================
# Reading a batch back
# ============================================================================


def _user_name(db: Session, user_id: Optional[str]) -> Optional[str]:
    if not user_id:
        return None
    row = db.query(User.name).filter(User.id == user_id).first()
    return row[0] if row else None


def _exc_message(exc: Exception) -> str:
    if isinstance(exc, AppException) and isinstance(exc.detail, dict):
        return str(exc.detail.get("message") or exc.detail)
    return str(exc)


def _exc_failing_lines(exc: Exception) -> List[dict]:
    """The lines a refusal named, or nothing.

    `SupplyLinesRefused` carries them on `detail["failing_lines"]` (line number, item code
    and the reason that line was refused) precisely because a sentence cannot tell a sheet
    which row to mark. A caller that re-raises only the sentence throws that away."""
    if isinstance(exc, AppException) and isinstance(exc.detail, dict):
        return list(exc.detail.get("failing_lines") or [])
    return []


def _batch_or_404(db: Session, batch_id: str) -> PlanningChangeBatch:
    batch = (
        db.query(PlanningChangeBatch).filter(PlanningChangeBatch.id == batch_id).one_or_none()
    )
    if batch is None:
        raise AppException(
            status_code=404,
            message="This planning change batch could not be found.",
            code="planning_change_batch_not_found",
        )
    return batch


def _source_out(batch: PlanningChangeBatch) -> dict:
    return {
        "upload_id": str(batch.import_job_id) if batch.import_job_id else str(batch.id),
        "file_name": batch.upload_file_name or "",
        "kind": batch.source_kind,
        "import_job_id": str(batch.import_job_id) if batch.import_job_id else None,
    }


def _row_is_superseded(db: Session, row: PlanningChangeRow) -> bool:
    from app.services.project_supply_service import ProjectSupplyService

    if not row.held_json:
        return False
    snapshot_rev = row.held_json.get("revision_no")
    if snapshot_rev is None:
        return False
    supply = ProjectSupplyService(db)
    pso_id = str(row.project_sales_order_id)
    active = supply.active_decision(pso_id)
    latest = supply.latest_decision(pso_id)
    current = active.revision_no if active else (latest.revision_no if latest else 0)
    return current != snapshot_rev


def row_out(db: Session, row: PlanningChangeRow) -> dict:
    applied_state = row.applied_state
    if applied_state == PLANNING_CHANGE_STATE_PENDING and _row_is_superseded(db, row):
        applied_state = PLANNING_CHANGE_STATE_SUPERSEDED
    return {
        "id": str(row.id),
        "project_line_id": str(row.project_line_id) if row.project_line_id else None,
        "line_no": row.line_no or 0,
        "item_code": row.item_code or "",
        "product_name": row.product_name,
        "kind": row.kind,
        "from": row.from_json or {},
        "to": row.to_json or {},
        "days_moved": row.days_moved,
        "held": row.held_json,
        "facts": row.facts_json,
        "suggestion": row.suggestion_json,
        "moved_transfer": (row.facts_json or {}).get("moved_transfer"),
        "proposal": row.proposal_json,
        "inquiry_rows": row.inquiry_rows_json or [],
        "decision": row.decision,
        "composition": row.composition_json,
        "applied_state": applied_state,
        "applied_reason": row.applied_reason,
        "board_link": row.board_link,
    }


def _order_labels(db: Session, order: ProjectSalesOrder) -> Tuple[Optional[str], Optional[str]]:
    customer_name = None
    project_label = None
    if order.project_id:
        row = db.query(Project.title).filter(Project.id == order.project_id).first()
        project_label = row[0] if row else None
    if order.so_id:
        row = db.query(SalesOrder.customer_id).filter(SalesOrder.id == order.so_id).first()
        if row and row[0]:
            cust = db.query(Customer.customer_name).filter(Customer.id == row[0]).first()
            customer_name = cust[0] if cust else None
    return customer_name, project_label


def get_batch(db: Session, batch_id: str) -> dict:
    from app.services.project_supply_service import ProjectSupplyService

    batch = _batch_or_404(db, batch_id)
    rows = (
        db.query(PlanningChangeRow)
        .filter(PlanningChangeRow.batch_id == batch.id)
        .order_by(PlanningChangeRow.created_at.asc())
        .all()
    )
    by_order: Dict[str, List[PlanningChangeRow]] = defaultdict(list)
    for r in rows:
        by_order[str(r.project_sales_order_id)].append(r)

    orders_map: Dict[str, ProjectSalesOrder] = {}
    if by_order:
        for o in (
            db.query(ProjectSalesOrder)
            .filter(ProjectSalesOrder.id.in_(list(by_order.keys())))
            .all()
        ):
            orders_map[str(o.id)] = o

    supply = ProjectSupplyService(db)
    orders_out = []
    for pso_id, order_rows in by_order.items():
        order = orders_map.get(pso_id)
        if order is None:
            continue
        active = supply.active_decision(pso_id)
        latest = supply.latest_decision(pso_id)
        revision_no = active.revision_no if active else (latest.revision_no if latest else 0)
        customer_name, project_label = _order_labels(db, order)
        orders_out.append(
            {
                "project_sales_order_id": pso_id,
                "so_number": _so_number(order),
                "customer_name": customer_name,
                "project_label": project_label,
                "revision_no": revision_no,
                "rows": [row_out(db, r) for r in order_rows],
                "is_adopted": bool(order.so_id) and order.project_id is None,
                "core_sales_order_id": str(order.so_id) if order.so_id else None,
                "project_id": str(order.project_id) if order.project_id else None,
            }
        )

    return {
        "id": str(batch.id),
        "created_at": batch.created_at,
        "created_by_name": _user_name(db, batch.created_by),
        "source": _source_out(batch),
        "applied_at": batch.applied_at,
        "applied_by_name": _user_name(db, batch.applied_by) if batch.applied_by else None,
        "result": batch.result_json,
        "orders": orders_out,
    }


def _summary_out(
    db: Session,
    batch: PlanningChangeBatch,
    rows: Sequence[Tuple[Optional[str], Optional[str]]],
    so_numbers_by_pso: Dict[str, str],
) -> dict:
    """One batch's list row. `rows` and `so_numbers_by_pso` are read ONCE for the whole
    page by `list_batches` - reading them here made the listing two queries per row."""
    pending = sum(1 for (state, _pso) in rows if state == PLANNING_CHANGE_STATE_PENDING)
    failed = sum(1 for (state, _pso) in rows if state == PLANNING_CHANGE_STATE_FAILED)
    # The orders this batch moved, by NUMBER (AC-P3-1): the list row's Plan action opens
    # the board on exactly these, and a second call per row to find that out would be one
    # per row on a paged list.
    return {
        "so_numbers": sorted(
            {
                so_numbers_by_pso[str(pso)]
                for _state, pso in rows
                if pso and str(pso) in so_numbers_by_pso
            }
        ),
        "id": str(batch.id),
        "created_at": batch.created_at,
        "created_by_name": _user_name(db, batch.created_by),
        "source": _source_out(batch),
        "order_count": batch.order_count,
        "line_count": batch.line_count,
        "pending_count": pending,
        "failed_count": failed,
        "applied_at": batch.applied_at,
        "applied_by_name": _user_name(db, batch.applied_by) if batch.applied_by else None,
    }


def list_batches(
    db: Session,
    *,
    page: int = 1,
    limit: int = 25,
    query: Optional[str] = None,
    state: Optional[str] = None,
    sort: Optional[str] = None,
    direction: Optional[str] = None,
) -> dict:
    q = db.query(PlanningChangeBatch)
    if state == "pending":
        q = q.filter(PlanningChangeBatch.applied_at.is_(None))
    elif state == "applied":
        q = q.filter(PlanningChangeBatch.applied_at.isnot(None))
    needle = (query or "").strip()
    if needle:
        q = q.filter(PlanningChangeBatch.upload_file_name.ilike(f"%{needle}%"))
    q = q.order_by(
        PlanningChangeBatch.created_at.asc()
        if (direction or "desc") == "asc"
        else PlanningChangeBatch.created_at.desc()
    )
    total = q.count()
    offset = max(page - 1, 0) * max(limit, 1)
    batches = q.offset(offset).limit(limit).all()

    # TWO queries for the whole page, never two per row: every row of every batch on the
    # page, then every sales-order number those rows name.
    batch_ids = [str(b.id) for b in batches]
    rows_by_batch: Dict[str, List[Tuple[Optional[str], Optional[str]]]] = defaultdict(list)
    if batch_ids:
        for batch_id, state, pso in (
            db.query(
                PlanningChangeRow.batch_id,
                PlanningChangeRow.applied_state,
                PlanningChangeRow.project_sales_order_id,
            )
            .filter(PlanningChangeRow.batch_id.in_(batch_ids))
            .all()
        ):
            rows_by_batch[str(batch_id)].append((state, pso))
    pso_ids = {
        str(pso)
        for rows in rows_by_batch.values()
        for _state, pso in rows
        if pso
    }
    so_numbers_by_pso: Dict[str, str] = {}
    if pso_ids:
        for order in (
            db.query(ProjectSalesOrder)
            .filter(ProjectSalesOrder.id.in_(list(pso_ids)))
            .all()
        ):
            so_numbers_by_pso[str(order.id)] = _so_number(order)

    return {
        "data": [
            _summary_out(db, b, rows_by_batch.get(str(b.id), []), so_numbers_by_pso)
            for b in batches
        ],
        "total": total,
        "page": page,
        "limit": limit,
    }


def _row_open_qty(row: PlanningChangeRow) -> Decimal:
    """What the line's composition must sum to - the SAME figure the board's own editor
    balances against (`amendDraftFrom`'s `open_qty`): the proposal's own outstanding
    quantity when there is one, else the row's own new quantity."""
    proposal = row.proposal_json or {}
    if proposal.get("qty_outstanding") is not None:
        return _dec(proposal.get("qty_outstanding"))
    if proposal.get("qty") is not None:
        return _dec(proposal.get("qty"))
    return _dec((row.to_json or {}).get("qty"))


def composition_from_proposal(proposal: Optional[dict]) -> dict:
    """The board's own proposal for a row (`proposal_json`, a `BoardContribution`), turned
    into a `ConfirmLine`-shaped composition - the same reading the board's own Confirm gives
    an untouched proposal (`fulfilmentBoard.ts`'s `lineFor`, the non-amended branch): the
    engine's own Reserve/incoming/Buy figures, addressed to the warehouses it proposed them
    against. Pure; no I/O. `{}` when there is nothing to compose (no proposal, or one with
    no line to post against)."""
    if not proposal:
        return {}
    project_line_id = proposal.get("project_line_id")
    if not project_line_id:
        return {}
    sources = proposal.get("sources") or []
    incoming = _proposal_qty(proposal.get("qty_proposed_incoming"), sources, "timely_spo")
    reserve_qty = _proposal_qty(proposal.get("qty_proposed_reserve"), sources, "reserve")
    # The cheap guard (the captain, 20 Aug, diagnosing SO397450 / SRT382-6-DIY): the
    # aggregate is authoritative - `_proposal_qty` above already prefers it over the
    # sources' own total whenever it is present - but a mismatch must never pass in
    # silence. Left unlogged, a future producer bug that stops keeping `sources`/`trail`
    # in step with the aggregate (the defect `_apply_placed_offset` shipped with) would
    # once again change what Apply writes without anything on screen or in the logs
    # disagreeing with it first.
    sources_reserve_total = sum(
        (_dec(s.get("qty")) for s in sources if s.get("kind") == "reserve"), _ZERO
    )
    if sources_reserve_total != reserve_qty:
        logger.warning(
            "planning change composition: sources reserve total %s disagrees with the "
            "proposed reserve %s on row %s - trusting the aggregate.",
            qty_text(sources_reserve_total),
            qty_text(reserve_qty),
            proposal.get("key") or project_line_id,
        )
    # No `qty_proposed_borrow` aggregate exists on `BoardContribution` (unlike reserve and
    # incoming) - LADDER V7.1's `order_borrow`/`supply_borrow` rungs are newer than that
    # field, and every reader of a whole-unit Borrow sums `sources` itself (`rank_score`
    # sources, `_group_sibling_warehouses`). Summed over the SAME filtered list
    # `_borrow_components_from_sources` builds from (a source without a `warehouse_id`
    # cannot be addressed as a component), so the two never disagree about how much borrow
    # the sources themselves account for.
    borrow_sources_all = [s for s in sources if s.get("kind") == "borrow"]
    borrow_qty = sum(
        (_dec(s.get("qty")) for s in borrow_sources_all if s.get("warehouse_id")), _ZERO
    )
    sources_borrow_total = sum((_dec(s.get("qty")) for s in borrow_sources_all), _ZERO)
    if sources_borrow_total != borrow_qty:
        logger.warning(
            "planning change composition: sources borrow total %s disagrees with the "
            "addressable borrow %s on row %s - a borrow source is missing its "
            "warehouse_id; trusting the addressable total.",
            qty_text(sources_borrow_total),
            qty_text(borrow_qty),
            proposal.get("key") or project_line_id,
        )
    owed = _dec(
        proposal.get("qty_outstanding")
        if proposal.get("qty_outstanding") is not None
        else proposal.get("qty")
    )
    buy_raw = proposal.get("qty_proposed_buy")
    buy = (
        _dec(buy_raw) if buy_raw is not None
        else max(owed - incoming - reserve_qty - borrow_qty, _ZERO)
    )
    return {
        "project_line_id": project_line_id,
        "timely_spo_qty": qty_text(incoming),
        "reserve": _reserve_components_from_sources(sources, reserve_qty),
        # LADDER V7.1's `order_borrow` rung (S1/AC-B2) DOES propose a whole-unit Borrow
        # off a later donor's own committed stock - built the same way Reserve is, from
        # the proposal's own `sources`. An amendment still takes the `amend` path and
        # posts whatever the planner composed by hand; this is only the "take the
        # proposal as it stands" (`confirm`) reading of it.
        "borrow": _borrow_components_from_sources(sources, borrow_qty),
        "buy_qty": qty_text(buy),
        "buy_reason": None,
        "amend_reason": None,
    }


def _proposal_qty(value: Any, sources: List[dict], kind: str) -> Decimal:
    if value is not None:
        return _dec(value)
    return sum((_dec(s.get("qty")) for s in sources if s.get("kind") == kind), _ZERO)


def _reserve_components_from_sources(sources: List[dict], reserve_qty: Decimal) -> List[dict]:
    reserve_sources = [s for s in sources if s.get("kind") == "reserve" and s.get("warehouse_id")]
    out: List[dict] = []
    remaining = reserve_qty
    for s in reserve_sources:
        if remaining <= _ZERO:
            break
        take = min(_dec(s.get("qty")), remaining)
        if take > _ZERO:
            out.append({"warehouse_id": s["warehouse_id"], "qty": qty_text(take)})
            remaining -= take
    # Whatever the sources could not address (the proposal rounded, or asked for more than
    # any one source stated) lands on the last addressable warehouse - the only one this
    # side can name it against.
    if remaining > _ZERO and out:
        out[-1]["qty"] = qty_text(_dec(out[-1]["qty"]) + remaining)
    return out


def _borrow_components_from_sources(sources: List[dict], borrow_qty: Decimal) -> List[dict]:
    """A `ConfirmBorrowComponent`-shaped dict per borrow source, in the same take-until-
    covered order `_reserve_components_from_sources` uses.

    `donor_core_line_id` (plus the display-only `donor_so_number`/`donor_line_no`/
    `donor_agent_code`/`same_agent`/`donor_required_date`) is what makes this a Borrow the
    confirm mechanics can actually act on - `ProjectSupplyService._check_line` only takes
    the "another order's own committed quantity" branch when it is present
    (`item.source == ALLOC_SOURCE_OTHER_LOCATION and donor_core_line_id`), and
    `_borrow_shortfalls` reads the SAME attribute to raise the donor's ORDER_BACK row.
    `source` is always `ALLOC_SOURCE_OTHER_LOCATION` here: every rung the board proposes a
    Borrow on today (`order_borrow`, the pool's borrow half, `supply_borrow`) takes stock
    already committed to, or moving for, a NAMED sales-order line or document, never a
    cross-project claim (`ALLOC_SOURCE_OTHER_PROJECT`, which only the `amend` dialog's own
    hand-built composition uses) - and `_check_line`'s `supply_key` branch (step 3) returns
    before ever reading `source` at all, so the value is inert there.
    """
    borrow_sources = [s for s in sources if s.get("kind") == "borrow" and s.get("warehouse_id")]
    out: List[dict] = []
    remaining = borrow_qty
    for s in borrow_sources:
        if remaining <= _ZERO:
            break
        take = min(_dec(s.get("qty")), remaining)
        if take <= _ZERO:
            continue
        out.append({
            "source": ALLOC_SOURCE_OTHER_LOCATION,
            "warehouse_id": s["warehouse_id"],
            "donor_project_id": None,
            "qty": qty_text(take),
            "reason": s.get("reason") or "",
            "donor_core_line_id": s.get("donor_core_line_id"),
            "donor_so_number": s.get("donor_so_number"),
            "donor_line_no": s.get("donor_line_no"),
            "donor_agent_code": s.get("donor_agent_code"),
            "same_agent": bool(s.get("same_agent", False)),
            "donor_required_date": s.get("donor_required_date"),
            "supply_key": s.get("supply_key"),
            "supply_document": s.get("supply_document"),
            "arrival_date": s.get("arrival_date"),
        })
        remaining -= take
    # Same rounding carry `_reserve_components_from_sources` does - whatever the sources
    # could not address lands on the last addressable one.
    if remaining > _ZERO and out:
        out[-1]["qty"] = qty_text(_dec(out[-1]["qty"]) + remaining)
    return out


def _validate_composition_shape(
    composition: dict, row: PlanningChangeRow, open_qty: Decimal
) -> dict:
    """The PUT-time check (module docstring, PLAN section 1): shape + total == open quantity,
    mirroring the board editor's own `lineBalance`/`lineBlockers`. `_check_line` runs the FULL
    recheck (stock, donor reasons, discontinued reason) at Apply, against live facts - this is
    only the shape a composition must have to be storable at all."""

    def fail(message: str, code: str) -> None:
        raise AppException(status_code=422, message=message, code=code)

    if not isinstance(composition, dict) or not composition.get("project_line_id"):
        fail("This composition needs a line.", "planning_change_composition_invalid")
    if row.project_line_id and str(composition.get("project_line_id")) != str(row.project_line_id):
        fail(
            "This composition is for a different line.",
            "planning_change_composition_wrong_line",
        )
    reserve = composition.get("reserve") or []
    borrow = composition.get("borrow") or []
    timely = _dec(composition.get("timely_spo_qty"))
    buy = _dec(composition.get("buy_qty"))
    quantities = [timely, buy]
    for item in reserve:
        if not item.get("warehouse_id"):
            fail("Every Reserve component needs a warehouse.", "planning_change_composition_invalid")
        quantities.append(_dec(item.get("qty")))
    for item in borrow:
        if not item.get("warehouse_id"):
            fail("Every Borrow component needs a warehouse.", "planning_change_composition_invalid")
        quantities.append(_dec(item.get("qty")))
    if min(quantities, default=_ZERO) < _ZERO:
        fail("A component quantity is negative.", "planning_change_composition_invalid")

    total = timely + sum((_dec(i.get("qty")) for i in reserve), _ZERO) + \
        sum((_dec(i.get("qty")) for i in borrow), _ZERO) + buy
    if total != open_qty:
        fail(
            f"The components add up to {qty_text(total)} and the line is open for "
            f"{qty_text(open_qty)}.",
            "planning_change_composition_mismatch",
        )

    return {
        "project_line_id": str(composition.get("project_line_id")),
        "timely_spo_qty": qty_text(timely),
        "reserve": [
            {"warehouse_id": i["warehouse_id"], "qty": qty_text(_dec(i.get("qty")))}
            for i in reserve
        ],
        "borrow": [
            {
                "source": i.get("source"),
                "warehouse_id": i["warehouse_id"],
                "donor_project_id": i.get("donor_project_id"),
                "qty": qty_text(_dec(i.get("qty"))),
                "reason": i.get("reason") or "",
                # Round-tripped, not re-derived (`ConfirmBorrowComponent`'s own docstring:
                # "display only; never validated") - `donor_core_line_id` is what the
                # confirm mechanics act ON (`_check_line`'s group-borrow branch,
                # `_borrow_shortfalls`'s order-back), so dropping it here would store a
                # composition the confirm path cannot execute the way it was proposed.
                "donor_core_line_id": i.get("donor_core_line_id"),
                "donor_so_number": i.get("donor_so_number"),
                "donor_line_no": i.get("donor_line_no"),
                "donor_agent_code": i.get("donor_agent_code"),
                "same_agent": bool(i.get("same_agent", False)),
                "donor_required_date": i.get("donor_required_date"),
                "supply_key": i.get("supply_key"),
                "supply_document": i.get("supply_document"),
                "arrival_date": i.get("arrival_date"),
            }
            for i in borrow
        ],
        "buy_qty": qty_text(buy),
        "buy_reason": composition.get("buy_reason"),
        "amend_reason": composition.get("amend_reason"),
    }


def set_row_decision(
    db: Session,
    batch_id: str,
    row_id: str,
    decision: Optional[str],
    composition: Optional[dict] = None,
) -> dict:
    batch = _batch_or_404(db, batch_id)
    if batch.applied_at is not None:
        raise AppException(
            status_code=409,
            message="This batch has already been applied.",
            code="planning_change_batch_applied",
        )
    row = (
        db.query(PlanningChangeRow)
        .filter(PlanningChangeRow.id == row_id, PlanningChangeRow.batch_id == batch.id)
        .one_or_none()
    )
    if row is None:
        raise AppException(
            status_code=404,
            message="This row could not be found.",
            code="planning_change_row_not_found",
        )
    # Confirm or Amend, and nothing else (AC-C7). The route's own Literal refuses any
    # other word with a 422 before this is ever reached; this is the service-level half of
    # the same rule, for the callers that are not the route.
    if decision is not None and decision not in ("confirm", "amend"):
        raise AppException(
            status_code=422,
            message="A planning change row is either confirmed or amended.",
            code="planning_change_decision_invalid",
        )
    if decision in ("confirm", "amend") and _row_is_superseded(db, row):
        raise AppException(
            status_code=409,
            message=(
                "The board confirmed a newer revision on this line since this batch was "
                "built."
            ),
            code="planning_change_row_superseded",
        )

    if decision in ("confirm", "amend"):
        if row.kind == "cancelled":
            # A cancelled line has nothing to compose FOR - the line is gone from the book
            # - and Apply retires it off the kind, not off a composition. Confirming it is
            # still allowed (the board pre-marks every changed line it shows), it simply
            # records the decision and posts no composition.
            row.decision = decision
            row.composition_json = None
            db.flush()
            return row_out(db, row)
        if not row.project_line_id:
            raise AppException(
                status_code=422,
                message="This line has no planning record yet, so there is nothing to confirm.",
                code="planning_change_row_no_line",
            )
        open_qty = _row_open_qty(row)
        if decision == "confirm":
            if not row.proposal_json:
                raise AppException(
                    status_code=422,
                    message="This row has no proposal to confirm.",
                    code="planning_change_row_no_proposal",
                )
            composed = composition_from_proposal(row.proposal_json)
        else:
            if not composition:
                raise AppException(
                    status_code=422,
                    message="An amendment needs a composition.",
                    code="planning_change_composition_required",
                )
            composed = composition
        row.composition_json = _validate_composition_shape(composed, row, open_qty)
    else:
        row.composition_json = None

    row.decision = decision
    db.flush()
    return row_out(db, row)


# ============================================================================
# Apply
# ============================================================================


def _confirm_payload(project_line_id: str, frozen_entry: dict) -> dict:
    """One covered line's FROZEN composition, in the shape a `ConfirmLine` is built from.

    No caller in the apply path since Slice C - a row is applied from the composition CS
    confirmed, never from a verb Apply re-decided off the snapshot - but kept as the one
    place that reads a frozen entry back into confirm shape;
    `tests/scm/test_ladder_v7_supply_borrow_fixes.py` pins its donor-field handling.
    """
    components = frozen_entry.get("components") or []
    reserve = [
        {"warehouse_id": c.get("source_warehouse_id"), "qty": _dec(c.get("qty"))}
        for c in components
        if c.get("kind") == RESERVE and c.get("source_warehouse_id")
    ]
    borrow = [
        {
            "source": c.get("source") or ALLOC_SOURCE_OTHER_LOCATION,
            "warehouse_id": c.get("source_warehouse_id"),
            "donor_project_id": c.get("donor_project_id"),
            "qty": _dec(c.get("qty")),
            "reason": c.get("cs_reason") or "",
            # LADDER v7.1 STEP 3 (S4): the DOCUMENT this borrow comes off, carried verbatim.
            # A keep or a reduce re-posts the frozen composition, and without these three a
            # step-3 borrow was re-confirmed as an ordinary free-stock borrow: its placement
            # link came down, the quantity was re-checked against on-hand capacity at a bin
            # holding a container that has not landed, and the phantom hold that survived
            # held nothing at all.
            "supply_key": c.get("supply_key"),
            "supply_document": c.get("supply_document"),
            "arrival_date": c.get("arrival_date"),
        }
        for c in components
        if c.get("kind") == BORROW and c.get("source_warehouse_id")
    ]
    buy_qty = sum((_dec(c.get("qty")) for c in components if c.get("kind") == BUY), _ZERO)
    timely_qty = sum(
        (_dec(c.get("qty")) for c in components if c.get("kind") == TIMELY_SPO), _ZERO
    )
    return {
        "project_line_id": project_line_id,
        "timely_spo_qty": timely_qty,
        "reserve": reserve,
        "borrow": borrow,
        "buy_qty": buy_qty,
        "buy_reason": frozen_entry.get("buy_reason"),
        "amend_reason": frozen_entry.get("amend_reason"),
    }


def _released_reserve(held: Optional[dict]) -> dict:
    """What AC-R06's `released` result names: the location(s) and quantity a `release` row
    gave up. Read off the row's own frozen `held_json` (what it said at build time), never a
    `ConfirmLine` - the line is excluded from the new revision entirely (module docstring)."""
    reserve = (held or {}).get("reserve") or []
    qty = sum((_dec(r.get("qty")) for r in reserve), _ZERO)
    locations = sorted({r.get("location") for r in reserve if r.get("location")})
    return {"location": ", ".join(locations) or None, "qty": qty_text(qty)}


def _to_confirm_line(payload: dict):
    from app.schemas.project_supply import (
        ConfirmBorrowComponent,
        ConfirmLine,
        ConfirmReserveComponent,
    )

    return ConfirmLine(
        project_line_id=payload["project_line_id"],
        timely_spo_qty=payload["timely_spo_qty"],
        reserve=[
            ConfirmReserveComponent(warehouse_id=c["warehouse_id"], qty=c["qty"])
            for c in payload["reserve"]
        ],
        borrow=[
            ConfirmBorrowComponent(
                source=c["source"],
                warehouse_id=c["warehouse_id"],
                donor_project_id=c.get("donor_project_id"),
                qty=c["qty"],
                reason=c.get("reason") or "",
                # Same fields `_validate_composition_shape` stores - dropped here, an
                # apply built off a `confirm`/`amend` decision would post a Borrow that
                # takes free stock rather than a NAMED donor line's committed quantity,
                # and `_borrow_shortfalls` would raise no ORDER_BACK row for it at all.
                donor_core_line_id=c.get("donor_core_line_id"),
                donor_so_number=c.get("donor_so_number"),
                donor_line_no=c.get("donor_line_no"),
                donor_agent_code=c.get("donor_agent_code"),
                same_agent=bool(c.get("same_agent", False)),
                donor_required_date=c.get("donor_required_date"),
                supply_key=c.get("supply_key"),
                supply_document=c.get("supply_document"),
                arrival_date=c.get("arrival_date"),
            )
            for c in payload["borrow"]
        ],
        buy_qty=payload["buy_qty"],
        buy_reason=payload.get("buy_reason"),
        amend_reason=payload.get("amend_reason"),
    )


def _pool_code_for_core_line(
    db: Session, core_line_id: Optional[str], _cache: Dict[str, Optional[str]]
) -> Optional[str]:
    """The line's OWN fulfilment warehouse's pool, by the same `pool_warehouse_id` hop
    the ladder resolves everywhere else (`ProjectSupplyService`'s `_LineFacts.pool_code`).
    `None` when the line states no warehouse, or that warehouse has no pool."""
    if not core_line_id:
        return None
    if core_line_id in _cache:
        return _cache[core_line_id]
    own_id = (
        db.query(SalesOrderLine.warehouse_id)
        .filter(SalesOrderLine.id == core_line_id)
        .scalar()
    )
    code = None
    if own_id:
        pool_id = (
            db.query(Warehouse.pool_warehouse_id).filter(Warehouse.id == own_id).scalar()
        )
        if pool_id:
            code = (
                db.query(Warehouse.warehouse_code).filter(Warehouse.id == pool_id).scalar()
            )
    _cache[core_line_id] = code
    return code


def _apply_placed_redirect(
    db: Session,
    row: PlanningChangeRow,
    batch: PlanningChangeBatch,
    so_number: str,
    pool_cache: Dict[str, Optional[str]],
) -> int:
    """The captain's ruling, 21 Aug 2026: a line confirmed AS PROPOSED whose fresh
    proposal drew on the shared pool for quantity this line already had PLACED on a real
    purchase order does not relabel that PO onto Buy - the pool take stands, and the
    placed row is REDIRECTED to replenish the pool instead ("it takes the outstanding PO
    to BRW"). Runs only for `decision == "confirm"` (never `amend`): that is the one case
    where `row.composition_json` IS `composition_from_proposal(row.proposal_json)`
    verbatim, so the fresh proposal's own `placed_redirect_qty` is still the true basis
    for the composed Reserve - an amendment may have removed or resized that Reserve by
    hand, and this function has no way to tell that apart from one the planner meant.

    Redirects WHOLE rows only, largest-first (`_confirm_payload_reduce`'s own
    convention), up to the budget `_apply_placed_offset` computed. A row bigger than what
    is left of the budget is left alone rather than split - the genuine leftover, if the
    budget cannot be exactly matched by whole rows, still nets to a `CANCEL_BALANCE`
    exception at `refresh_for_decision`, which is the honest answer for placed quantity
    the redirect could not actually reach.
    """
    proposal = row.proposal_json or {}
    redirect_qty = _dec(proposal.get("placed_redirect_qty"))
    if redirect_qty <= _ZERO or not row.project_line_id:
        return 0
    pool_code = _pool_code_for_core_line(db, row.core_line_id, pool_cache)
    if not pool_code:
        return 0
    candidates = (
        db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.so_line_id == row.project_line_id,
            OrderInquiryRow.state.in_((INQUIRY_ACTIONED, INQUIRY_PLACED)),
            OrderInquiryRow.verb.in_((IV_ORDER, IV_RESERVE_AND_ORDER)),
            OrderInquiryRow.redirected_to_pool.is_(False),
        )
        .order_by(OrderInquiryRow.qty.desc(), OrderInquiryRow.created_at.asc())
        .all()
    )
    remaining = redirect_qty
    count = 0
    for candidate in candidates:
        if remaining <= _ZERO:
            break
        qty = _dec(candidate.qty)
        if qty > remaining:
            continue
        previous_location = candidate.stock_location or "no location"
        note = (
            f"Redirected to replenish {pool_code} (was {previous_location}) - planning "
            f"change batch {str(batch.id)[:8]}, {so_number} line {row.line_no or '?'}: "
            "the pool now covers this need."
        )
        candidate.redirected_to_pool = True
        candidate.stock_location = pool_code
        candidate.note = f"{candidate.note}\n{note}" if candidate.note else note
        remaining -= qty
        count += 1
    return count


def _oi_demand_rows(
    db: Session,
    live_rows: Sequence[PlanningChangeRow],
    so_number: str,
    settled_line_ids: Sequence[str] = (),
) -> Tuple[List[dict], Dict[str, int]]:
    """What purchasing is told, beyond what the rows themselves now say.

    `settled_line_ids` are the lines whose OWN inquiry row this apply just updated in place
    (AC-P3-5): it carries the new quantity, the new date and the previous value on its
    note, so a separate DELAY / ADVANCE / CANCEL_BALANCE row beside it would be the same
    instruction told twice - the duplicate "one row per sales-order line" exists to stop.
    Those lines are skipped here. A line the plan did NOT carry still gets its change row,
    because nothing else said anything about it.
    """
    from app.services.project_order_inquiry_engine import (
        CHANGE_DATE_EARLIER,
        CHANGE_DATE_LATER,
        CHANGE_QTY_DECREASE,
        CHANGE_RELEASE,
    )

    core_ids = [r.core_line_id for r in live_rows if r.core_line_id]
    product_by_core: Dict[str, Optional[str]] = {}
    if core_ids:
        for cid, pid in (
            db.query(SalesOrderLine.id, SalesOrderLine.product_id)
            .filter(SalesOrderLine.id.in_(core_ids))
            .all()
        ):
            product_by_core[str(cid)] = str(pid) if pid else None

    pool_cache: Dict[str, Optional[str]] = {}
    settled = {str(line_id) for line_id in (settled_line_ids or [])}
    out: List[dict] = []
    counts: Dict[str, int] = {}
    for r in live_rows:
        if not r.project_line_id:
            continue
        held = r.held_json or {}
        location = None
        reserve = held.get("reserve") or []
        if reserve:
            location = reserve[0].get("location")
        product_id = product_by_core.get(r.core_line_id or "")

        # The row itself now says what moved (AC-P3-5), so nothing more is raised for it.
        if str(r.project_line_id) in settled:
            continue

        if r.kind in ("delayed", "advanced"):
            qty = _dec((r.to_json or {}).get("qty"))
            if qty <= _ZERO:
                continue
            from_date = (r.from_json or {}).get("required_date")
            out.append(
                {
                    "line_id": r.project_line_id,
                    "product_id": product_id,
                    "item_code": r.item_code,
                    "qty": qty,
                    "delivery_date": _as_date((r.to_json or {}).get("required_date")),
                    "stock_location": location,
                    "change": CHANGE_DATE_LATER if r.kind == "delayed" else CHANGE_DATE_EARLIER,
                    "note": f"Was {from_date}" if from_date else "No previous delivery date",
                }
            )
            counts["DELAY" if r.kind == "delayed" else "ADVANCE"] = (
                counts.get("DELAY" if r.kind == "delayed" else "ADVANCE", 0) + 1
            )
        elif r.kind == "qty_down":
            from_qty = _dec((r.from_json or {}).get("qty"))
            to_qty = _dec((r.to_json or {}).get("qty"))
            drop = from_qty - to_qty
            if drop <= _ZERO:
                continue
            out.append(
                {
                    "line_id": r.project_line_id,
                    "product_id": product_id,
                    "item_code": r.item_code,
                    "qty": drop,
                    "delivery_date": _as_date((r.to_json or {}).get("required_date")),
                    "stock_location": location,
                    "change": CHANGE_QTY_DECREASE,
                    "note": f"Was {qty_text(from_qty)}, now {qty_text(to_qty)}",
                }
            )
            counts["CANCEL_BALANCE"] = counts.get("CANCEL_BALANCE", 0) + 1
    return out, counts


def _retire_inquiry_rows(
    db: Session, project_line_id: Optional[str], reason: str
) -> List[str]:
    """`closed` (AC-R06, amended by AC-P3-6): the line is gone from the book, so what it
    asked purchasing for is cancelled - never deleted, because a cancelled row is still
    what purchasing was told.

    A LINKED row is cancelled too, and that is the correction part 3 makes. It used to be
    left alone on the grounds that a placement is real supply already bought - but the
    supply does not vanish with the row: `_shift_links_off_retired_lines` moves it to the
    line that still needs it, and whatever no line needs is unlinked and free for the next
    row waiting. Leaving the row raised instead would have told purchasing to buy for a
    line the book has closed.

    An `actioned` row is still left alone bar the note. That state is a PERSON's word that
    purchasing dealt with it (`mark_rows` is its only writer), and a plan does not get to
    overrule it.

    Returns THE ROWS IT CANCELLED, by id, and the shift below takes exactly those: a row
    somebody cancelled last month is not this apply's to move documents off."""
    if not project_line_id:
        return []
    rows = (
        db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.so_line_id == project_line_id,
            OrderInquiryRow.state != INQUIRY_CANCELLED,
        )
        .all()
    )
    cancelled: List[str] = []
    for row in rows:
        note = f"{row.note}\n{reason}" if row.note else reason
        if row.state == INQUIRY_ACTIONED:
            row.note = note
        else:
            row.state = INQUIRY_CANCELLED
            row.note = note
            cancelled.append(str(row.id))
    return cancelled


def _took_note(
    note: Optional[str], qty: Decimal, document: Optional[str], who: Optional[str]
) -> str:
    """What a survivor's row says about a placement it inherited, and who applied it."""
    stamp = (
        f"Took {qty_text(qty)} on {document or 'an unnamed document'} from a line the "
        "book closed"
    )
    if who:
        stamp = f"{stamp} ({who})"
    return f"{note}; {stamp}" if note else stamp


def _shift_links_off_retired_lines(
    db: Session,
    order: ProjectSalesOrder,
    cancelled_row_ids: Sequence[str],
    actor: Optional[str],
) -> int:
    """A closed line's placements move to the row that still needs them (AC-P3-6).

    The captain, 25 August 2026: "PO / SPO allocated to the 0 lines shift to the 25 line".
    A closed line's row is cancelled rather than deleted, so its links would otherwise sit
    on a row whose quantity nobody owes - real purchase-order quantity, arranged by a
    buyer, attached to an instruction that has been withdrawn.

    THE SURVIVOR IS THE SAME PRODUCT ON THE SAME SALES ORDER, and only as much as it can
    hold: the sum of a row's links may never exceed its own quantity (`order_inquiry_links`
    says so in a CHECK, and `committed_v` nets on it).

    **AS MUCH AS IT CAN HOLD IS A SPLIT, not a choice between all and nothing.** A survivor
    short of the whole placement used to be offered none of it and the entire link went
    back to the cascade - so a survivor with 6 of headroom against a 10-unit link ended up
    holding nothing, and a stranger's row took the lot. It now takes its 6 on a link of its
    own (the same document, the same purchase-order line, the same claim) and only the
    remaining 4 goes back, which is what "whatever that row cannot take goes back through
    the cascade" says. Going back means UNLINKED: the purchase-order line is free again and
    the next raised row waiting for that product can claim it. Nothing is dropped in
    silence - the removal writes its own "Unlinked from ..." stamp on the cancelled row,
    exactly as a person's Unlink does.

    `cancelled_row_ids` are the rows THIS apply just cancelled (`_retire_inquiry_rows`
    returns them). Read off the line instead, an old cancelled row that still carried links
    would have its documents re-dealt by a change that was never about it.

    Returns how many placements moved.
    """
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    service = ProjectOrderInquiryService(db)
    row_ids = [str(row_id) for row_id in cancelled_row_ids if row_id]
    if not row_ids:
        return 0

    cancelled_rows = (
        db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.id.in_(row_ids),
            OrderInquiryRow.state == INQUIRY_CANCELLED,
        )
        .all()
    )
    if not cancelled_rows:
        return 0

    # The product each retired line named, and every line of this order, so a survivor is
    # found by PRODUCT rather than by item code (two codes can spell one product).
    product_by_line: Dict[str, Optional[str]] = {}
    order_lines = (
        db.query(ProjectSalesOrderLine)
        .filter(ProjectSalesOrderLine.project_sales_order_id == order.id)
        .all()
    )
    for line in order_lines:
        product_by_line[str(line.id)] = str(line.product_id) if line.product_id else None

    survivors_by_product: Dict[str, List[OrderInquiryRow]] = defaultdict(list)
    live_rows = (
        db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.so_line_id.in_([str(line.id) for line in order_lines]),
            OrderInquiryRow.state != INQUIRY_CANCELLED,
            # The same verbs `_settle_row_in_place` reads as "a row that still owes this
            # line something". An ORDER BACK is a Buy said differently (part 2 section 4b),
            # so a survivor carrying one has headroom a shifted placement can fill.
            OrderInquiryRow.verb.in_((IV_ORDER, IV_ORDER_BACK, IV_RESERVE_AND_ORDER)),
        )
        .order_by(OrderInquiryRow.delivery_date.asc().nullslast(),
                  OrderInquiryRow.created_at.asc())
        .all()
    )
    for row in live_rows:
        product_id = product_by_line.get(str(row.so_line_id))
        if product_id:
            survivors_by_product[product_id].append(row)

    moved = 0
    who = _user_name(db, actor)
    touched: List[OrderInquiryRow] = []
    for cancelled in cancelled_rows:
        links = service._links_of(cancelled.id)
        if not links:
            continue
        product_id = product_by_line.get(str(cancelled.so_line_id))
        candidates = survivors_by_product.get(product_id or "", [])
        for link in links:
            whole = _dec(link.qty)
            remaining = whole
            repointed = False
            for taker in candidates:
                if remaining <= _ZERO:
                    break
                headroom = service._unlinked_need(taker)
                if headroom <= _ZERO:
                    continue
                take = min(headroom, remaining)
                if take == whole:
                    # One survivor holds the whole placement: the link itself moves, id,
                    # claim and linking history intact. Nothing is split, so nothing is
                    # rewritten.
                    link.row_id = taker.id
                    repointed = True
                else:
                    db.add(
                        OrderInquiryLink(
                            company_id=link.company_id,
                            row_id=taker.id,
                            po_line_id=link.po_line_id,
                            spo_allocation_id=link.spo_allocation_id,
                            document=link.document,
                            qty=take,
                            linked_by=actor,
                            linked_at=datetime.utcnow(),
                            auto=bool(link.auto),
                            # The SAME claim: it is the document's, not the row's, and two
                            # links on one document already share one.
                            claim_id=link.claim_id,
                        )
                    )
                remaining -= take
                db.flush()
                service._invalidate_link_cache()
                taker.note = _took_note(taker.note, take, link.document, who)
                if taker not in touched:
                    touched.append(taker)
                moved += 1
            if not repointed:
                # Whatever the survivors did not take goes back to the cascade, and the
                # part they DID take now lives on links of their own - so the original is
                # removed either way, and the purchase-order line is free for its balance.
                service._remove_links(cancelled, [link])
        if cancelled not in touched:
            touched.append(cancelled)

    if touched:
        service.refresh_link_state(touched)
        db.flush()
    return moved


def _notify_purchasing(
    db: Session, order: ProjectSalesOrder, so_number: str, batch: PlanningChangeBatch
) -> bool:
    """AC-R09: purchasing told once per order, by a batch link. Best-effort - Apply has
    already written the plan and Order Inquiry changes by the time this runs."""
    try:
        from app.services.notification_service import NotificationService
        from app.services.project_order_inquiry_service import ProjectOrderInquiryService

        user_ids = ProjectOrderInquiryService(db)._purchasing_user_ids()
        if not user_ids:
            return False
        service = NotificationService(db)
        for user_id in user_ids:
            service.create_with_channel_preferences(
                user_id=str(user_id),
                type="project_order_inquiry_raised",
                title=f"Planning change applied - {so_number}",
                body=f"The SO book moved lines on {so_number}; review what changed.",
                data={"planning_change_batch_id": str(batch.id), "so_number": so_number},
                source_entity_type="planning_change_batch",
                source_entity_id=str(batch.id),
                dedup_key=f"{batch.id}:{order.id}:planning_change_applied",
                event_type="project_order_inquiry_raised",
                send_in_app=True,
                send_email=False,
            )
        return True
    except Exception:  # noqa: BLE001 - a notify failure must not undo a written plan
        logger.exception("planning change purchasing notify failed for order %s", order.id)
        return False


def _bystander_returned_to_review(
    db: Session,
    supply,
    order: ProjectSalesOrder,
    so_number: str,
    previous_decision,
    previous_frozen: Dict[str, dict],
    previous_reason: Optional[str],
    handled_line_ids: set,
    revised: bool,
) -> List[dict]:
    """The applied-order surface's answer to B1 (code review, 20 Aug 2026): applying a batch
    that (deliberately, module docstring) drops uncarried lines back to undecided used to say
    nothing about it - `applied_orders`/`failed_orders` alone can't tell a clean apply from
    one that just silently returned nine bystander lines to review. This does NOT change
    what gets carried (still nothing, from a challenged revision, or a materially-superseded
    one) - it only NAMES what already happened, derived from the decision rows themselves
    rather than guessed: a line the PREVIOUS revision (whatever its state - `previous_decision`
    is the order's LATEST decision as it stood before this apply, ACTIVE or CHALLENGED alike)
    covered that the new one (or, for a material-change supersede, no revision at all) does
    not, and that THIS batch never decided about at all - `handled_line_ids` already covers
    kept/confirmed/replanned/released/retired/reduced lines, which are visible on the batch's
    own rows and are not "silent". `previous_reason` is read by the caller AFTER the apply
    runs, by id, so it reflects the genuine drift/supersede reason `confirm()`/
    `supersede_for_material_change()` write onto this row - not a caption read too early."""
    if not revised or previous_decision is None or not previous_frozen:
        return []
    pso_id = str(order.id)
    new_active = supply.active_decision(pso_id)
    new_covered_ids = set((supply.frozen_lines_of(new_active) if new_active else {}).keys())
    bystander_ids = set(previous_frozen.keys()) - new_covered_ids - handled_line_ids
    if not bystander_ids:
        return []
    line_nos = sorted(
        r[0]
        for r in db.query(ProjectSalesOrderLine.line_no)
        .filter(ProjectSalesOrderLine.id.in_(list(bystander_ids)))
        .all()
        if r[0] is not None
    )
    reason = previous_reason or (
        "The confirmed revision no longer matched the sales order."
    )
    return [
        {
            "so_number": so_number,
            # Derived from `line_nos`, not `bystander_ids`: a bystander line with no
            # `line_no` is dropped from the list, and the count must match what is shown,
            # never a larger number the reader cannot account for.
            "line_count": len(line_nos),
            "line_nos": line_nos,
            "reason": reason,
        }
    ]


def _record_lateness(
    db: Session, supply, pso_id: str, live_rows: Sequence[PlanningChangeRow]
) -> None:
    """A unit kept LATE is recorded as late, on both things a person reads it from.

    Rule 8's second half: "a unit kept late (S12) is shown as late, never silently kept".
    The board warned before Confirm; after it, the revision itself carries `late_days` on
    the line's own snapshot (so the next reader of the decision sees it without recomputing
    an arrival) and purchasing's row says it in words. Both are records of what was
    decided, so neither is derived again later.
    """
    late_by_line = {
        str(r.project_line_id): int((r.suggestion_json or {}).get("late_days") or 0)
        for r in live_rows
        if r.project_line_id and (r.suggestion_json or {}).get("late_days")
    }
    if not late_by_line:
        return
    decision = supply.active_decision(pso_id)
    if decision is not None and decision.line_snapshots:
        snapshots = list(decision.line_snapshots)
        touched = False
        for index, snapshot in enumerate(snapshots):
            days = late_by_line.get(str(snapshot.get("project_line_id")))
            if not days:
                continue
            snapshots[index] = dict(snapshot, late_days=days)
            touched = True
        if touched:
            from sqlalchemy.orm.attributes import flag_modified

            decision.line_snapshots = snapshots
            flag_modified(decision, "line_snapshots")
    rows = (
        db.query(OrderInquiryRow)
        .filter(
            OrderInquiryRow.so_line_id.in_(list(late_by_line)),
            OrderInquiryRow.state != INQUIRY_CANCELLED,
        )
        .all()
    )
    for row in rows:
        days = late_by_line.get(str(row.so_line_id))
        if not days:
            continue
        phrase = f"Kept, late by {_days_word(days)}"
        if row.note and phrase in row.note:
            continue
        row.note = f"{row.note}; {phrase}" if row.note else phrase
    db.flush()


def _apply_one_order(
    db: Session,
    supply,
    order: ProjectSalesOrder,
    order_rows: Sequence[PlanningChangeRow],
    actor: Optional[str],
    batch: PlanningChangeBatch,
    extra_lines: Sequence[dict] = (),
) -> dict:
    from app.schemas.project_supply import ConfirmSupplyBody
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    pso_id = str(order.id)
    so_number = _so_number(order)
    active_decision = supply.active_decision(pso_id)
    latest_decision = supply.latest_decision(pso_id)
    current_revision = (
        active_decision.revision_no
        if active_decision
        else (latest_decision.revision_no if latest_decision else 0)
    )
    frozen = supply.frozen_lines_of(active_decision)
    # Fix-cluster (20 Aug 2026, S4): `latest_decision`, not `active_decision`, is what the
    # bystander report needs. The headline case IS a CHALLENGED revision - a drift challenge
    # leaves it the latest row but no longer ACTIVE, so `active_decision` reads None and the
    # report silently has nothing to compare against, in exactly the case it exists to catch.
    # `previous_frozen_for_report` is read here, before `confirm()`/`supersede_for_material_
    # change()` run below - both call `challenge_if_drifted`/`_write_decision`, which mutate
    # THIS SAME ORM-tracked row in place, and a drift challenge can drop it out of
    # `active_decision` entirely. The REASON, by contrast, is read back by id AFTER the apply
    # (below) rather than off this pre-run reference: the genuine drift reason is only known
    # once `challenge_if_drifted` runs inside `confirm()`, so reading it now would just get
    # None and hide it behind the generic fallback every time.
    previous_frozen_for_report = supply.frozen_lines_of(latest_decision)
    previous_decision_id_for_report = str(latest_decision.id) if latest_decision else None

    # Confirm or Amend, and a line the book CANCELLED - nothing else is applied (AC-C7).
    # A row still undecided is simply left pending: the batch waits for CS.
    accepted = [
        r
        for r in order_rows
        if (r.decision in ("confirm", "amend") or r.kind == "cancelled")
        and r.applied_state == PLANNING_CHANGE_STATE_PENDING
    ]
    empty_result = {
        "revised": False,
        "revision_no": current_revision,
        "lines_replanned": 0,
        "lines_confirmed": 0,
        "inquiry_counts": {},
        "notified": False,
        "returned_to_review": [],
        "confirm_result": None,
    }
    if not accepted and not extra_lines:
        return empty_result

    live: List[PlanningChangeRow] = []
    for r in accepted:
        snapshot_rev = (r.held_json or {}).get("revision_no")
        if snapshot_rev is not None and snapshot_rev != current_revision:
            r.applied_state = PLANNING_CHANGE_STATE_SUPERSEDED
            r.applied_reason = (
                "The board confirmed a newer revision on this line after this batch was "
                "built."
            )
        else:
            live.append(r)
    if not live and not extra_lines:
        return empty_result

    by_line_id = {r.project_line_id: r for r in live if r.project_line_id}
    confirm_lines: List[dict] = []
    replanned = 0
    retired = 0
    confirmed = 0
    handled_line_ids: set = set()
    pool_cache: Dict[str, Optional[str]] = {}
    # Every covered line this batch means to DROP, not carry (the un-decide seam,
    # `ProjectSupplyService.confirm`'s docstring) - a `release`/`replan`/`retire` row is
    # deliberately excluded from `confirm_lines` below so it returns to the board
    # undecided (or, for `retire`, drops out entirely), but the moment ANY other line on
    # this SAME order is named, `confirm()`'s own "union is the server's" rule would carry
    # this one forward verbatim unless it is named here instead (seen live: SO403765 rev 5
    # kept line 12's old Buy and old date after an ADVANCE had been raised for it).
    uncover_line_ids: List[str] = []
    # Part 3: the lines this apply is RE-STATING (their inquiry row is updated in place,
    # AC-P3-5) and the lines it is closing (their rows are cancelled and their links move
    # to the survivor, AC-P3-6). The retire runs AFTER the confirm, because the survivor
    # only has its new quantity - and so the headroom to take those links - once the
    # revision is written.
    settle_line_ids: List[str] = []
    retired_line_ids: List[str] = []
    for line_id, frozen_entry in frozen.items():
        row = by_line_id.get(line_id)
        if row is None:
            # This line has no row in THIS batch - nobody on the board decided anything
            # about it. Leave it OUT of the payload entirely rather than re-naming it
            # from its frozen snapshot: `confirm()`'s own carry-forward rule (13.4, "the
            # union is the server's") already copies an unnamed covered line into the
            # new revision verbatim - same snapshot, same holds, no re-validation against
            # live facts. Naming every covered line here used to force the WHOLE order
            # through `_facts_for`'s live check on every apply, so a batch that decided
            # ONE line failed on unrelated bystander lines it was never asked to move
            # (live: SO391698 rev 2, "9 lines cannot be confirmed" from a 1-line batch,
            # 20 August 2026).
            continue
        handled_line_ids.add(line_id)
        # TWO THINGS APPLY A ROW, and nothing else (Slice C contract D): the composition
        # CS confirmed or amended, and the book having CANCELLED the line. The rule
        # table's own verbs used to fork here five ways - keep, reduce, replan, release,
        # retire - and every one of them was Apply re-deciding the line for itself off a
        # verb nobody composed.
        if row.decision in ("confirm", "amend") and row.composition_json:
            confirm_lines.append(row.composition_json)
            settle_line_ids.append(line_id)
            confirmed += 1
            if row.decision == "confirm":
                _apply_placed_redirect(db, row, batch, so_number, pool_cache)
            continue
        if row.kind == "cancelled":
            # The line is gone from the book: it leaves the revision entirely and its
            # inquiry rows are cancelled below. Nothing to compose - there is no line left
            # to compose for.
            retired += 1
            uncover_line_ids.append(line_id)
            retired_line_ids.append(line_id)
            continue

    # A `confirm`/`amend` row whose line NO active decision covers - AC-R03's "Not
    # decided", the common case a `replan` row starts in - never appears in `frozen`
    # above; compose it here, or accepting it is once again a no-op.
    for row in live:
        if not row.project_line_id or row.project_line_id in handled_line_ids:
            continue
        if row.decision in ("confirm", "amend") and row.composition_json:
            confirm_lines.append(row.composition_json)
            settle_line_ids.append(str(row.project_line_id))
            confirmed += 1
            if row.decision == "confirm":
                _apply_placed_redirect(db, row, batch, so_number, pool_cache)

    # A cancelled line whose order has NO active decision covering it never reached the
    # loop above; the book still closed it, and its rows still have to be cancelled.
    for row in live:
        if row.kind != "cancelled" or not row.project_line_id:
            continue
        if row.project_line_id in retired_line_ids:
            continue
        retired_line_ids.append(str(row.project_line_id))

    # Lines the board decided that this batch does not carry (part 3, AC-P3-4): the press
    # was ONE press, so dropping them would tell the planner they confirmed something they
    # did not. Posted as an ordinary confirmation beside the batch's own rows.
    for payload in extra_lines or ():
        confirm_lines.append(payload)
        confirmed += 1

    # The book closed these lines. Their rows are CANCELLED, never deleted - they are what
    # purchasing was told - and this apply owns that cancellation, so it happens BEFORE the
    # confirm rather than after (CI round, 28 Aug). The confirm has a retirement of its own
    # (`_retire_uncovered_rows`, B3) for any line that leaves the revision, and it takes a
    # drafted row's links DOWN - correct where nothing else is going to want them, and
    # exactly wrong here, because part 3's whole rule is that a closed line's placements
    # move to the line that still needs them (AC-P3-6). Cancelling first leaves the rows
    # already out of that retirement's reach WITH their links still on them, which is what
    # `_shift_links_off_retired_lines` below is waiting for. The SHIFT itself still runs
    # after the confirm, so the survivor already carries its new quantity and has the
    # headroom to take them.
    cancelled_row_ids: List[str] = []
    for line_id in retired_line_ids:
        cancelled_row_ids.extend(
            _retire_inquiry_rows(
                db, line_id, "The line was closed by a planning change batch."
            )
        )
    if cancelled_row_ids:
        # FLUSH FIRST. The application's session runs `autoflush=False`
        # (`app.database.SessionLocal`), so the cancellations above are pending ORM state
        # and the confirm's own reads - and the shift's query below - would come back
        # empty, which is exactly what happened live on SO381895 (26 August 2026): both
        # closed rows kept their links while the test suite, on an autoflushing session,
        # saw them move.
        db.flush()

    revised = False
    revision_no = current_revision
    confirm_result: Optional[dict] = None
    settled_in_place: List[str] = []
    auto_place_products: List[str] = []
    if confirm_lines:
        body = ConfirmSupplyBody(lines=[_to_confirm_line(p) for p in confirm_lines])
        result = supply.confirm(
            order, body, actor_user_id=actor, uncover_line_ids=uncover_line_ids,
            settle_in_place_line_ids=settle_line_ids,
            # The cascade waits for the shift below. Run inside `confirm`, it filled the
            # survivor's headroom from ANY free purchase-order line first, so the closed
            # lines' own documents arrived a moment later to a row with nothing left to
            # give them and were re-dealt to a stranger - the opposite of AC-P3-6, which
            # sends a closed line's placements to the line that still needs them.
            defer_auto_place=True,
        )
        revision_no = result["revision_no"]
        confirm_result = result
        settled_in_place = list(result.get("settled_in_place") or [])
        auto_place_products = list(result.get("auto_place_products") or [])
        revised = True
    elif active_decision is not None and (replanned or retired):
        supply.supersede_for_material_change(
            order,
            "Every covered line moved to Replan or Retire in a planning change batch.",
        )
        revised = True

    # NOW the closed lines' placements move to the surviving row of the same product on the
    # same order (AC-P3-6). After the confirm, so the survivor already carries its new
    # quantity and has the headroom to take them; the rows themselves were cancelled above.
    if cancelled_row_ids:
        db.flush()
        _shift_links_off_retired_lines(db, order, cancelled_row_ids, actor)

    # NOW the cascade, once every document this order already owns has found its own row.
    # Whatever headroom is still open after the shift is what genuinely needs a stranger's
    # purchase order, and that is what this fills.
    if auto_place_products:
        supply.auto_place_for_confirmed_products(
            auto_place_products, actor_user_id=actor
        )

    # What the suggestion warned about, recorded on what it decided (rule 8).
    if revised:
        _record_lateness(db, supply, pso_id, live)

    # A press whose batch rows were only `release` / `retire` composes nothing: those lines
    # LEAVE the revision (`supersede_for_material_change`) rather than being confirmed into
    # one. It still applied - rows moved to the pool, rows were cancelled, links shifted -
    # so the board's Confirm answers with what happened rather than refusing 422 over work
    # that was written.
    if confirm_result is None and revised:
        confirm_result = {
            "revision_no": revision_no,
            "confirmed_at": datetime.utcnow(),
            "review_state": supply._review_state(order) or "needs_cs_review",
            "inquiry_rows_created": 0,
            "exceptions": [],
            "lines_decided": 0,
            "lines_undecided": replanned + retired,
            "transfers_written": 0,
            "transfers_failed": 0,
        }

    # Read the previous revision's OWN reason back by id, now that `confirm()`/
    # `supersede_for_material_change()` have run: the genuine drift reason
    # (`challenge_if_drifted`) or supersede reason is only written during that call, so
    # reading it any earlier would just see None and hide it behind the generic fallback.
    previous_reason_for_report = (
        db.query(SOSupplyDecision.superseded_reason)
        .filter(SOSupplyDecision.id == previous_decision_id_for_report)
        .scalar()
        if previous_decision_id_for_report
        else None
    )
    returned_to_review = _bystander_returned_to_review(
        db, supply, order, so_number, latest_decision, previous_frozen_for_report,
        previous_reason_for_report, handled_line_ids, revised,
    )

    demand_rows, inquiry_counts = _oi_demand_rows(db, live, so_number, settled_in_place)
    if demand_rows:
        ProjectOrderInquiryService(db).derive_for_book_change(
            order, demand_rows, batch_id=str(batch.id), actor_user_id=actor
        )

    for r in live:
        r.applied_state = PLANNING_CHANGE_STATE_APPLIED
        if r.decision in ("confirm", "amend") and r.composition_json:
            r.result_json = {"board_link": r.board_link, "confirmed": True}
        elif r.kind == "cancelled":
            r.result_json = {
                "board_link": r.board_link,
                "released": _released_reserve(r.held_json),
                "back_on_board": True,
            }
        else:
            r.result_json = {"board_link": r.board_link}

    # Purchasing is notified by `apply()`, AFTER this order's savepoint has committed, not
    # here: `NotificationService.create_with_channel_preferences` commits on its own, and
    # calling it while still inside `db.begin_nested()` closes that savepoint's transaction,
    # so the caller's `savepoint.commit()` then raises `ResourceClosedError` ("This
    # transaction is closed") and a perfectly applied order is reported as failed.

    return {
        "revised": revised,
        "revision_no": revision_no,
        "lines_replanned": replanned,
        "lines_confirmed": confirmed,
        "inquiry_counts": inquiry_counts,
        "notified": False,
        "returned_to_review": returned_to_review,
        # What `ProjectSupplyService.confirm` itself answered, kept whole: the board's own
        # Confirm posts through here now (AC-P3-4) and its caller needs the revision, the
        # rows handed over and the transfers - not a summary of them.
        "confirm_result": confirm_result,
    }


def apply(
    db: Session,
    batch_id: str,
    actor: Optional[str],
    *,
    extra_confirm_lines: Optional[Dict[str, List[dict]]] = None,
    refuse_if_applied: bool = False,
    only_pso_ids: Optional[Sequence[str]] = None,
) -> dict:
    """AC-R05: one new revision per affected order, atomic per order. Applying twice is a
    no-op (`already_applied`).

    `refuse_if_applied` turns that no-op into a REFUSAL, which is what the board's own
    Confirm needs (AC-P3-4): pressing Confirm twice must say the change is already applied
    rather than answer 200 with a revision number that belongs to the first press.
    `extra_confirm_lines` carries the lines that same press decided that this batch does
    not carry, keyed by project sales order.

    `only_pso_ids` NARROWS the apply to the orders named, and the board's own Confirm is
    why it exists: a book upload moves many orders at once, and the board's Confirm is
    pressed per order (`OrderCommitRow`). Applying the whole batch off one press wrote
    revisions for orders nobody had confirmed, skipped the per-order permission check
    those orders would have had, and locked every remaining order's rows behind
    `applied_at` - so the planner could neither decide nor confirm them afterwards. An
    apply with no `only_pso_ids` is the whole batch, exactly as before.
    """
    from app.services.project_supply_service import ProjectSupplyService

    batch = _batch_or_404(db, batch_id)
    if refuse_if_applied and batch.applied_at is not None:
        who = _user_name(db, batch.applied_by)
        when = batch.applied_at.date().isoformat()
        raise AppException(
            status_code=409,
            message=(
                f"This planning change was already applied on {when}"
                + (f" by {who}" if who else "")
                + "."
            ),
            code="planning_change_batch_applied",
        )
    rows = db.query(PlanningChangeRow).filter(PlanningChangeRow.batch_id == batch.id).all()

    pso_ids = sorted({str(r.project_sales_order_id) for r in rows})
    orders_map: Dict[str, ProjectSalesOrder] = {}
    if pso_ids:
        for o in db.query(ProjectSalesOrder).filter(ProjectSalesOrder.id.in_(pso_ids)).all():
            orders_map[str(o.id)] = o

    def so_number_of(pso_id: str) -> str:
        order = orders_map.get(pso_id)
        return _so_number(order) if order else pso_id

    if batch.applied_at is not None:
        applied_orders = sorted(
            {
                so_number_of(str(r.project_sales_order_id))
                for r in rows
                if r.applied_state == PLANNING_CHANGE_STATE_APPLIED
            }
        )
        return {
            "applied_orders": applied_orders,
            "failed_orders": [],
            "already_applied": True,
            "returned_to_review": (batch.result_json or {}).get("returned_to_review", []),
            "outcomes": {},
        }

    wanted = {str(pso_id) for pso_id in only_pso_ids} if only_pso_ids is not None else None
    by_order: Dict[str, List[PlanningChangeRow]] = defaultdict(list)
    for r in rows:
        pso_id = str(r.project_sales_order_id)
        if wanted is not None and pso_id not in wanted:
            continue
        by_order[pso_id].append(r)

    supply = ProjectSupplyService(db)

    applied_orders: List[str] = []
    failed_orders: List[dict] = []
    orders_revised: List[dict] = []
    inquiry_counts: Dict[str, int] = {}
    lines_replanned = 0
    lines_confirmed = 0
    purchasing_notified = False
    returned_to_review: List[dict] = []
    outcomes: Dict[str, dict] = {}
    extra_by_order = dict(extra_confirm_lines or {})

    # An order the batch never touched, whose lines the same press decided anyway.
    for pso_id in extra_by_order:
        if pso_id not in by_order:
            by_order[pso_id] = []
            if pso_id not in orders_map:
                order = (
                    db.query(ProjectSalesOrder)
                    .filter(ProjectSalesOrder.id == pso_id)
                    .one_or_none()
                )
                if order is not None:
                    orders_map[pso_id] = order

    for pso_id, order_rows in by_order.items():
        order = orders_map.get(pso_id)
        so_number = so_number_of(pso_id)
        if order is None:
            reason = "This sales order no longer exists."
            for r in order_rows:
                if (
                    r.decision in ("accept", "confirm", "amend")
                    and r.applied_state == PLANNING_CHANGE_STATE_PENDING
                ):
                    r.applied_state = PLANNING_CHANGE_STATE_FAILED
                    r.applied_reason = reason
            failed_orders.append({"so_number": so_number, "reason": reason})
            continue

        savepoint = db.begin_nested()
        try:
            outcome = _apply_one_order(
                db, supply, order, order_rows, actor, batch,
                extra_lines=extra_by_order.get(pso_id, ()),
            )
            savepoint.commit()
        except Exception as exc:  # noqa: BLE001 - one order's failure must not sink the rest
            savepoint.rollback()
            reason = _exc_message(exc)
            logger.exception("planning change apply failed for order %s", so_number)
            for r in order_rows:
                if (
                    r.decision in ("accept", "confirm", "amend")
                    and r.applied_state == PLANNING_CHANGE_STATE_PENDING
                ):
                    r.applied_state = PLANNING_CHANGE_STATE_FAILED
                    r.applied_reason = reason
            # The lines the refusal NAMED, beside the sentence that summarises them: a
            # `SupplyLinesRefused` says which line and why ("Borrowing takes a reason"),
            # and the board's own Confirm has to be able to say the same thing an
            # ordinary Confirm does rather than "N lines cannot be confirmed" alone.
            failed_orders.append(
                {
                    "so_number": so_number,
                    "reason": reason,
                    "failing_lines": _exc_failing_lines(exc),
                }
            )
            continue

        # Notified AFTER `savepoint.commit()` has returned, never inside the savepoint:
        # `NotificationService.create_with_channel_preferences` commits on its own, and that
        # commit closes the savepoint's transaction out from under us if it runs first, so
        # `savepoint.commit()` raises `ResourceClosedError` and an order that applied cleanly
        # gets reported as failed. Still best-effort - a notify failure here cannot undo the
        # order, which is already committed by this point.
        notified = _notify_purchasing(db, order, so_number, batch)

        applied_orders.append(so_number)
        outcomes[pso_id] = outcome
        if outcome["revised"]:
            orders_revised.append({"so_number": so_number, "revision_no": outcome["revision_no"]})
        lines_replanned += outcome["lines_replanned"]
        lines_confirmed += outcome["lines_confirmed"]
        for verb, count in outcome["inquiry_counts"].items():
            inquiry_counts[verb] = inquiry_counts.get(verb, 0) + count
        purchasing_notified = purchasing_notified or notified
        returned_to_review.extend(outcome["returned_to_review"])

    # A batch is DONE only once it has written something. Stamping `applied_at` when
    # `orders_revised` is empty - nothing was actually written, whether because every
    # order failed or because a retry found nothing left `pending` to act on - locked the
    # batch forever: the row decision PUT and a retry of this same POST both gate on
    # `applied_at is not None` (PLAN section 10), so the planner could neither correct a
    # row's decision nor apply again, with `pending: 2` on the list beside `Applied ...`
    # on the same row. `applied_orders` alone is not enough to gate on - an order that hit
    # `_apply_one_order`'s early return (nothing left `pending` to accept) lands in
    # `applied_orders` without writing anything, so a batch stuck failing would flip to
    # "done" on nothing more than a harmless retry. Left pending instead, the rows keep
    # their `failed` state and reasons, decisions stay editable, and this same call can
    # simply be retried once the cause is fixed.
    #
    # AND only once no order this apply LEFT OUT is still pending. `applied_at` is the
    # batch-wide lock (`set_row_decision` and a retry of this call both gate on it), so
    # stamping it after a narrowed apply froze every other order of the same upload at
    # `pending` with no way to decide or confirm them - the planner saw `Applied ...` and
    # `pending: 2` on the same row. An apply that visited every order is unchanged: there
    # is nothing left out, so the stamp lands exactly as it did before.
    left_out_pending = wanted is not None and any(
        str(r.project_sales_order_id) not in wanted
        and r.applied_state == PLANNING_CHANGE_STATE_PENDING
        for r in rows
    )
    if orders_revised and not left_out_pending:
        batch.applied_at = datetime.utcnow()
        batch.applied_by = actor
        batch.result_json = {
            "orders_revised": orders_revised,
            "orders_failed": failed_orders,
            "inquiry_rows_changed": [
                {"verb": verb, "count": count} for verb, count in inquiry_counts.items()
            ],
            "lines_replanned": lines_replanned,
            "lines_confirmed": lines_confirmed,
            "purchasing_notified": purchasing_notified,
            "returned_to_review": returned_to_review,
        }
    db.flush()

    return {
        "applied_orders": applied_orders,
        "failed_orders": failed_orders,
        "already_applied": False,
        "returned_to_review": returned_to_review,
        "outcomes": outcomes,
    }
