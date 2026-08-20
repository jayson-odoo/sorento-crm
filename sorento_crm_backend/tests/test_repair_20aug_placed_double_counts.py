"""Pins for the four should-fix defects in `scripts/repair_20aug_placed_double_counts.py`
(code review, 20 Aug 2026, S6). The script itself is never run against a real database from
here - every world below lives in `blank_session()`'s scratch schema, rolled back at
teardown, the same substrate `tests/test_planning_changes.py` uses for the service this
script repairs after the fact.
"""
from __future__ import annotations

import importlib.util
import os
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from app.models.base import company_scope
from app.models.company import Company
from app.models.project_so import (
    ALLOC_RESERVE_SOURCES,
    ALLOC_SOURCE_OWN,
    DECISION_ACTIVE,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    IV_ORDER,
    OrderInquiry,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
    SOLineAllocation,
    SOSupplyDecision,
)
from app.services.scm.front_planning_engine import BUY, RESERVE

from ._pg_fixture import blank_session, unique_code

# Load the script as a module (it lives under scripts/, not a package - same pattern
# `test_attachment_keys.py` uses for `migrate_attachment_keys_to_uuid.py`).
_REPAIR_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "repair_20aug_placed_double_counts.py",
)
_spec = importlib.util.spec_from_file_location("repair_20aug", _REPAIR_PATH)
repair = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(repair)


def _uid() -> str:
    return str(uuid.uuid4())


def _company(db, code: str) -> Company:
    row = Company(id=_uid(), name=f"ZZT repair {code}", code=unique_code(code)[:50], is_active=True)
    db.add(row)
    db.flush()
    return row


def _pso(db, company_id: str, *, autocount_doc_no: str | None) -> ProjectSalesOrder:
    row = ProjectSalesOrder(
        id=_uid(), company_id=company_id, provisional_ref=f"ZZT-PSO-{_uid()[:8]}",
        area_group="TOWER", status="published", autocount_doc_no=autocount_doc_no,
    )
    db.add(row)
    db.flush()
    return row


def _project_line(db, order: ProjectSalesOrder, *, line_no: int, qty="10") -> ProjectSalesOrderLine:
    row = ProjectSalesOrderLine(
        id=_uid(), company_id=order.company_id, project_sales_order_id=order.id,
        line_no=line_no, product_id=None, description=f"ZZT line {line_no}",
        qty=Decimal(qty), uom="SET", unit_price=Decimal("0"), amount=Decimal("0"),
        delivery_date=None,
    )
    db.add(row)
    db.flush()
    return row


def _inquiry(db, order: ProjectSalesOrder) -> OrderInquiry:
    row = OrderInquiry(id=_uid(), company_id=order.company_id, project_sales_order_id=order.id,
                       state=INQUIRY_RAISED)
    db.add(row)
    db.flush()
    return row


def _row(db, inquiry: OrderInquiry, *, item_code: str, qty: str, state: str,
         so_line_id: str | None = None, created_at: datetime | None = None,
         po_ref: str | None = None) -> OrderInquiryRow:
    row = OrderInquiryRow(
        id=_uid(), company_id=inquiry.company_id, order_inquiry_id=inquiry.id,
        item_code=item_code, qty=Decimal(qty), verb=IV_ORDER, state=state,
        so_line_id=so_line_id, po_ref=po_ref,
        created_at=created_at or datetime(2026, 8, 15, 0, 0, 0),
    )
    db.add(row)
    db.flush()
    return row


# ============================================================================
# S6a: a cross-company duplicate must abort, not raise MultipleResultsFound
# ============================================================================


def test_find_order_reports_a_cross_company_duplicate_instead_of_crashing():
    with blank_session() as db:
        company_a = _company(db, "A")
        company_b = _company(db, "B")
        with company_scope(db, frozenset({company_a.id, company_b.id})):
            _pso(db, company_a.id, autocount_doc_no=repair.SO_NUMBER)
            _pso(db, company_b.id, autocount_doc_no=repair.SO_NUMBER)
            db.flush()

            # The old code's `.one_or_none()` would raise MultipleResultsFound here and
            # kill the whole run mid-way; the fix reports it and returns None instead.
            found = repair._find_order(db)
            assert found is None


def test_find_order_still_resolves_the_ordinary_single_match():
    with blank_session() as db:
        company = _company(db, "C")
        with company_scope(db, frozenset({company.id})):
            order = _pso(db, company.id, autocount_doc_no=repair.SO_NUMBER)
            db.flush()

            found = repair._find_order(db)
            assert found is not None
            assert found.id == order.id


# ============================================================================
# S6b: Case A's marker-less idempotency guard on `created_at`
# ============================================================================


def test_case_a_skips_a_row_created_after_the_netting_fix_even_with_no_marker():
    """A reconfirm between diagnosis and --apply cancels the original buggy row and raises
    a NEW one, already correctly netted by the fixed code path and carrying no marker of
    its own. The guard must recognise it by `created_at` and leave it alone."""
    with blank_session() as db:
        company = _company(db, "D")
        with company_scope(db, frozenset({company.id})):
            order = _pso(db, company.id, autocount_doc_no=repair.SO_NUMBER)
            inquiry = _inquiry(db, order)
            _row(db, inquiry, item_code=repair.CASE_A_ITEM_CODE, qty="5", state=INQUIRY_PLACED,
                 po_ref="ZZT-PO-1")
            after_fix = repair._FIX_DEPLOYED_AT_UTC + timedelta(hours=1)
            raised = _row(db, inquiry, item_code=repair.CASE_A_ITEM_CODE, qty="10",
                          state=INQUIRY_RAISED, created_at=after_fix)
            db.flush()

            repair.repair_case_a(db, order, apply=True)
            db.flush()

            db.refresh(raised)
            assert raised.qty == Decimal("10"), "a row from the fixed code path must not be re-netted"
            assert repair._CASE_A_NOTE_MARKER not in (raised.note or "")


def test_case_a_still_repairs_a_row_created_before_the_netting_fix():
    """The regression itself: unchanged behaviour for the row this script exists to fix."""
    with blank_session() as db:
        company = _company(db, "E")
        with company_scope(db, frozenset({company.id})):
            order = _pso(db, company.id, autocount_doc_no=repair.SO_NUMBER)
            inquiry = _inquiry(db, order)
            _row(db, inquiry, item_code=repair.CASE_A_ITEM_CODE, qty="5", state=INQUIRY_PLACED,
                 po_ref="ZZT-PO-1")
            before_fix = repair._FIX_DEPLOYED_AT_UTC - timedelta(hours=1)
            raised = _row(db, inquiry, item_code=repair.CASE_A_ITEM_CODE, qty="15",
                          state=INQUIRY_RAISED, created_at=before_fix)
            db.flush()

            repair.repair_case_a(db, order, apply=True)
            db.flush()

            db.refresh(raised)
            assert raised.qty == Decimal("10")  # 15 - 5 placed, re-derived
            assert repair._CASE_A_NOTE_MARKER in (raised.note or "")


# ============================================================================
# S6c: Case B must not trim one line's reserve by a DIFFERENT line's placed qty
# ============================================================================


def test_case_b_refuses_to_guess_when_placed_rows_span_two_different_lines():
    """The item on two lines of the same SO, each with its own placed row. Without the
    guard, `placed_qty` sums both lines' supply and trims whichever line `placed[0]`
    happens to be on by the OTHER line's quantity too."""
    with blank_session() as db:
        company = _company(db, "F")
        with company_scope(db, frozenset({company.id})):
            order = _pso(db, company.id, autocount_doc_no=repair.SO_NUMBER)
            line_1 = _project_line(db, order, line_no=1)
            line_2 = _project_line(db, order, line_no=2)
            inquiry = _inquiry(db, order)
            _row(db, inquiry, item_code=repair.CASE_B_ITEM_CODE, qty="5", state=INQUIRY_PLACED,
                 so_line_id=line_1.id, po_ref="ZZT-PO-1")
            _row(db, inquiry, item_code=repair.CASE_B_ITEM_CODE, qty="3", state=INQUIRY_PLACED,
                 so_line_id=line_2.id, po_ref="ZZT-PO-2")
            decision = SOSupplyDecision(
                id=_uid(), company_id=company.id, project_sales_order_id=order.id,
                revision_no=1, state=DECISION_ACTIVE,
                line_snapshots=[
                    {
                        "project_line_id": str(line_1.id),
                        "components": [{"kind": RESERVE, "qty": "10", "reason": "seed"}],
                    },
                ],
            )
            db.add(decision)
            db.flush()

            repair.repair_case_b(db, order, apply=True)
            db.flush()

            db.refresh(decision)
            # Untouched: the ambiguity guard must refuse rather than trim line 1 by line
            # 2's placed qty (or vice versa).
            components = decision.line_snapshots[0]["components"]
            assert components == [{"kind": RESERVE, "qty": "10", "reason": "seed"}]


def test_case_b_still_repairs_the_ordinary_single_line_case():
    with blank_session() as db:
        company = _company(db, "G")
        with company_scope(db, frozenset({company.id})):
            order = _pso(db, company.id, autocount_doc_no=repair.SO_NUMBER)
            line_1 = _project_line(db, order, line_no=1)
            inquiry = _inquiry(db, order)
            _row(db, inquiry, item_code=repair.CASE_B_ITEM_CODE, qty="5", state=INQUIRY_PLACED,
                 so_line_id=line_1.id, po_ref="ZZT-PO-1")
            decision = SOSupplyDecision(
                id=_uid(), company_id=company.id, project_sales_order_id=order.id,
                revision_no=1, state=DECISION_ACTIVE,
                line_snapshots=[
                    {
                        "project_line_id": str(line_1.id),
                        "components": [{"kind": RESERVE, "qty": "10", "reason": "seed"}],
                    },
                ],
            )
            db.add(decision)
            db.flush()  # the decision must exist before the allocation below references it
            db.add(SOLineAllocation(
                id=_uid(), company_id=company.id, so_line_id=line_1.id,
                source_type=ALLOC_SOURCE_OWN, qty=Decimal("10"), decision_id=decision.id,
            ))
            db.flush()

            repair.repair_case_b(db, order, apply=True)
            db.flush()

            db.refresh(decision)
            components = decision.line_snapshots[0]["components"]
            reserve = next(c for c in components if c["kind"] == RESERVE)
            buy = next(c for c in components if c["kind"] == BUY)
            assert Decimal(reserve["qty"]) == Decimal("5")
            assert Decimal(buy["qty"]) == Decimal("5")
            assert buy["reason"] == repair._CASE_B_REASON_MARKER

            alloc_rows = db.query(SOLineAllocation).filter(
                SOLineAllocation.decision_id == decision.id
            ).all()
            by_source = {r.source_type: r.qty for r in alloc_rows}
            assert by_source[ALLOC_SOURCE_OWN] == Decimal("5")
            assert by_source["order"] == Decimal("5")


# ============================================================================
# S6d: `_RESERVE_SOURCE_TYPES` is `ALLOC_RESERVE_SOURCES`, not a re-typed copy
# ============================================================================


def test_reserve_source_types_is_the_shared_constant_not_a_duplicate():
    assert repair._RESERVE_SOURCE_TYPES is ALLOC_RESERVE_SOURCES
