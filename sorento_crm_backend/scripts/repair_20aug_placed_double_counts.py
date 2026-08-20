#!/usr/bin/env python3
"""Repair the two live double-counts the 20 Aug placed/actioned state-vocabulary
regression left on SO349754 (the captain, 20 Aug, diagnosing section G live).

Before the fix (`app/services/project_order_inquiry_service.py`,
`app/services/planning_change_service.py`), every netting predicate that decides "how much
of this line's need is already covered" recognised only `INQUIRY_ACTIONED` - never
`INQUIRY_PLACED`, which is the state the live "Place on PO" workflow (section G) actually
writes. Live DB, 20 Aug: 145 placed rows, 0 actioned. Two results, both on SO349754:

  Case A (WESERP10B): the SO line's qty moved 5 -> 10. A placed row (5, PO-2026/07-0029)
  was already real supply, but the reconfirm's netting read it as 0, so it RE-RAISED the
  FULL new need (10) as a second row on top of the untouched placed one - 15 against a
  10-unit line. Fix: reduce the spurious raised row's own qty by the placed row's qty.

  Case B (SRTWC287A-RL): same qty move, a placed row (5, 202604-S0027) but NO active
  decision at the time. `buy_actioned` read false for the same reason, so the planning-
  change ladder proposed a fresh Reserve for the WHOLE new quantity (10) - 15 against a
  10-unit line (10 reserved + 5 already placed). No OI row was ever wrongly raised here
  (the buggy composition's own Buy leg was 0, so `refresh_for_decision` created nothing);
  the double-count lives entirely in the active decision's own reserve claim. Fix: trim
  the reserve component by the placed row's qty, in BOTH places a decision's Reserve is
  recorded - the frozen `line_snapshots` entry (display/audit) and the
  `so_line_allocations` rows (`SOSupplyDecision`'s own docstring: "the normalized
  so_line_allocations rows remain the components; [line_snapshots] is the header that
  groups them") - and relabel the trimmed amount onto a Buy component, the same
  recategorization `planning_change_service._apply_placed_offset` now does going forward,
  so the decision's total still balances the line's full open quantity.

Neither fix hardcodes "5". Both compute the corrected value at run time as
`currently stored qty - sum(currently placed qty on that line)`, so a value that has
moved since this was written is still handled correctly rather than a stale figure being
stamped over it.

Idempotent via an explicit marker rather than re-deriving from numbers a second time:
Case A stamps the corrected row's own `note`, Case B stamps the new Buy component's own
`reason` - a re-run recognises the marker and reports "already repaired" without touching
the row again, which the arithmetic alone cannot promise once the reserve figure is no
longer the original wrong one.

Run from sorento_crm_backend/:
    python scripts/repair_20aug_placed_double_counts.py            # dry run (default)
    python scripts/repair_20aug_placed_double_counts.py --apply    # write

Scoped to SO349754 only - this is not a general sweep for the same shape elsewhere. A row
found with the same symptom on another order is a DIFFERENT incident and needs its own
review before this script (or anything like it) touches it.
"""
from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.order import SalesOrder
from app.models.project_so import (
    ALLOC_SOURCE_BRW,
    ALLOC_SOURCE_GROUP_TAKE,
    ALLOC_SOURCE_ORDER,
    ALLOC_SOURCE_OWN,
    DECISION_ACTIVE,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    IV_ORDER,
    OrderInquiry,
    OrderInquiryRow,
    ProjectSalesOrder,
    SOLineAllocation,
    SOSupplyDecision,
)
from app.services.scm.front_planning_engine import BUY, RESERVE, qty_text

SO_NUMBER = "SO349754"
CASE_A_ITEM_CODE = "WESERP10B"
CASE_B_ITEM_CODE = "SRTWC287A-RL"
_ZERO = Decimal("0")
_RESERVE_SOURCE_TYPES = (ALLOC_SOURCE_OWN, ALLOC_SOURCE_BRW, ALLOC_SOURCE_GROUP_TAKE)
_CASE_A_NOTE_MARKER = "repair_20aug_placed_double_counts: netted against a real placed row"
_CASE_B_REASON_MARKER = "repair_20aug_placed_double_counts: already covered by a placed purchase order"


def _dec(value: Any) -> Decimal:
    if value is None:
        return _ZERO
    return Decimal(str(value))


def _find_order(db) -> Optional[ProjectSalesOrder]:
    order = (
        db.query(ProjectSalesOrder)
        .filter(ProjectSalesOrder.autocount_doc_no == SO_NUMBER)
        .one_or_none()
    )
    if order is not None:
        return order
    core = db.query(SalesOrder).filter(SalesOrder.so_number == SO_NUMBER).one_or_none()
    if core is None:
        return None
    return (
        db.query(ProjectSalesOrder)
        .filter(ProjectSalesOrder.so_id == core.id)
        .one_or_none()
    )


def _inquiry_rows_for_item(db, order: ProjectSalesOrder, item_code: str) -> List[OrderInquiryRow]:
    return (
        db.query(OrderInquiryRow)
        .join(OrderInquiry, OrderInquiry.id == OrderInquiryRow.order_inquiry_id)
        .filter(
            OrderInquiry.project_sales_order_id == order.id,
            OrderInquiryRow.item_code == item_code,
            OrderInquiryRow.verb == IV_ORDER,
        )
        .all()
    )


def repair_case_a(db, order: ProjectSalesOrder, *, apply: bool) -> None:
    print(f"\n[case A] {SO_NUMBER} / {CASE_A_ITEM_CODE}")
    rows = _inquiry_rows_for_item(db, order, CASE_A_ITEM_CODE)
    placed = [r for r in rows if r.state == INQUIRY_PLACED]
    raised = [r for r in rows if r.state == INQUIRY_RAISED]
    placed_qty = sum((_dec(r.qty) for r in placed), _ZERO)

    print(f"  placed rows: {[(r.id, str(r.qty), r.po_ref) for r in placed]}")
    print(f"  raised rows: {[(r.id, str(r.qty)) for r in raised]}")

    if placed_qty <= _ZERO or not raised:
        print("  nothing to repair (no placed supply, or no raised row to net it against)")
        return
    if len(raised) != 1:
        print(
            f"  WARNING: expected exactly one spurious raised row, found {len(raised)} - "
            "skipping rather than guessing which one to correct"
        )
        return

    row = raised[0]
    if _CASE_A_NOTE_MARKER in (row.note or ""):
        print(f"  row {row.id}: already repaired (marker present) - skipping")
        return

    before = _dec(row.qty)
    corrected = before - placed_qty
    print(f"  row {row.id}: qty {before} -> {corrected} (placed {placed_qty}, re-derived, not hardcoded)")
    if corrected <= _ZERO:
        print(
            "  WARNING: the placed supply covers this raised row entirely (or more) - "
            "that needs a human CANCEL_BALANCE decision, not a silent qty edit. Skipping."
        )
        return

    if apply:
        row.qty = corrected
        row.note = f"{row.note}\n{_CASE_A_NOTE_MARKER}" if row.note else _CASE_A_NOTE_MARKER
        print(f"  WROTE row {row.id}: qty={corrected}")
    else:
        print("  (dry run - nothing written)")


def _reserve_components(components: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [c for c in components if c.get("kind") == RESERVE]


def _trim_reserve_components(
    components: List[Dict[str, Any]], offset: Decimal
) -> List[Dict[str, Any]]:
    """Trim `offset` off the reserve components, largest-qty first, dropping any emptied
    to zero - the same trim order `_apply_placed_offset` uses going forward."""
    remaining = offset
    out: List[Dict[str, Any]] = []
    reserve_first = sorted(
        (c for c in components if c.get("kind") == RESERVE),
        key=lambda c: -_dec(c.get("qty")),
    )
    trimmed_ids = {id(c) for c in reserve_first}
    for component in reserve_first:
        qty = _dec(component.get("qty"))
        if remaining > _ZERO:
            take = min(qty, remaining)
            qty -= take
            remaining -= take
        if qty > _ZERO:
            out.append({**component, "qty": qty_text(qty)})
    return [c for c in components if id(c) not in trimmed_ids] + out


def repair_case_b(db, order: ProjectSalesOrder, *, apply: bool) -> None:
    print(f"\n[case B] {SO_NUMBER} / {CASE_B_ITEM_CODE}")
    rows = _inquiry_rows_for_item(db, order, CASE_B_ITEM_CODE)
    placed = [r for r in rows if r.state == INQUIRY_PLACED]
    placed_qty = sum((_dec(r.qty) for r in placed), _ZERO)
    print(f"  placed rows: {[(r.id, str(r.qty), r.po_ref) for r in placed]}")

    if placed_qty <= _ZERO or not placed:
        print("  nothing to repair (no placed row found)")
        return
    so_line_id = placed[0].so_line_id
    if not so_line_id:
        print("  WARNING: the placed row names no sales-order line - skipping")
        return

    decision = (
        db.query(SOSupplyDecision)
        .filter(
            SOSupplyDecision.project_sales_order_id == order.id,
            SOSupplyDecision.state == DECISION_ACTIVE,
        )
        .one_or_none()
    )
    if decision is None:
        print("  no active decision on this order - nothing to repair")
        return

    snapshots = decision.line_snapshots or []
    target_index = next(
        (i for i, s in enumerate(snapshots) if s.get("project_line_id") == str(so_line_id)),
        None,
    )
    if target_index is None:
        print("  this line is not covered by the active decision - nothing to repair")
        return
    target = snapshots[target_index]
    components = target.get("components") or []

    already = any(
        c.get("kind") == BUY and c.get("reason") == _CASE_B_REASON_MARKER for c in components
    )
    if already:
        print("  already repaired (marker present) - skipping")
        return

    reserve_total = sum((_dec(c.get("qty")) for c in _reserve_components(components)), _ZERO)
    offset = min(placed_qty, reserve_total)
    print(f"  reserve (decision snapshot): {reserve_total}, placed: {placed_qty}, trim: {offset}")
    if offset <= _ZERO:
        print("  reserve already at or below what the placed row covers - nothing to trim")
        return

    print(f"  decision {decision.id} (revision {decision.revision_no})")
    print(f"  BEFORE components: {components}")
    new_components = _trim_reserve_components(components, offset) + [
        {
            "kind": BUY,
            "qty": qty_text(offset),
            "reason": _CASE_B_REASON_MARKER,
            "cs_reason": None,
        }
    ]
    print(f"  AFTER  components: {new_components}")

    alloc_rows = (
        db.query(SOLineAllocation)
        .filter(
            SOLineAllocation.decision_id == decision.id,
            SOLineAllocation.so_line_id == so_line_id,
            SOLineAllocation.source_type.in_(_RESERVE_SOURCE_TYPES),
        )
        .order_by(SOLineAllocation.qty.desc())
        .all()
    )
    print(f"  reserve allocation rows: {[(r.id, r.source_type, str(r.qty)) for r in alloc_rows]}")

    if not apply:
        print("  (dry run - nothing written)")
        return

    remaining = offset
    for alloc in alloc_rows:
        if remaining <= _ZERO:
            break
        take = min(_dec(alloc.qty), remaining)
        new_qty = _dec(alloc.qty) - take
        remaining -= take
        if new_qty <= _ZERO:
            db.delete(alloc)
        else:
            alloc.qty = new_qty
    db.add(
        SOLineAllocation(
            company_id=order.company_id,
            so_line_id=so_line_id,
            source_type=ALLOC_SOURCE_ORDER,
            warehouse_id=None,
            qty=offset,
            decision_id=decision.id,
            reason=_CASE_B_REASON_MARKER,
            confirmed_by=decision.confirmed_by,
            confirmed_at=decision.confirmed_at,
        )
    )

    new_snapshots = list(snapshots)
    new_snapshots[target_index] = {**target, "components": new_components}
    decision.line_snapshots = new_snapshots  # reassign the whole JSONB value, not mutate in place
    print(f"  WROTE decision {decision.id} line {so_line_id}: reserve trimmed by {offset}, buy +{offset}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Write the fix. Default is dry-run.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        order = _find_order(db)
        if order is None:
            print(f"{SO_NUMBER}: sales order not found - nothing to do")
            return 1
        print(f"{SO_NUMBER}: project_sales_order {order.id}")

        repair_case_a(db, order, apply=args.apply)
        repair_case_b(db, order, apply=args.apply)

        if args.apply:
            db.commit()
            print("\nCommitted.")
        else:
            db.rollback()
            print("\nDry run only - rolled back, nothing written. Re-run with --apply to write.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
