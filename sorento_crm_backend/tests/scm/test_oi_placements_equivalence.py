"""CONFIRM-DIALOG-SPEED PR 2: `_oi_placements` answers exactly as it did.

Prod clone, 3 Nov 2026: as one statement the read filtered 1.45M `spo_allocations` rows by
1,331 SO line refs, and the planner nested-looped over them (~2 s warm per call, up to 6.5 s
per board read, 2.5 s in the Confirm dry run). It now starts from the lines' own order-inquiry
placements and reads only the SPO rows those name, by id.

The OLD statement is kept here, verbatim, as the oracle. Every case is compared row for row
(as a multiset: neither read promises an order), and the callers that consume it
(`_oi_linked_landed_by_ref`, `_po_received_by_product`, Stock Debt's landed holds) are
compared end to end with the oracle swapped in.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal

from tests.scm.conftest import SORENTO_COMPANY_ID, requires_pg
from tests.scm.test_goods_chain import _World
from tests.scm.test_stock_debt_routes import _order_back_link_on_spo, _product, _spo, _u

pytestmark = requires_pg


def _old_oi_placements(self, refs, product_ids, *, company_id=None):
    """The statement as it stood before CONFIRM-DIALOG-SPEED (main at ebb6b573)."""
    from app.models.order import SalesOrderLine
    from app.models.procurement import SPOAllocation
    from app.models.project_so import (
        INQUIRY_CANCELLED,
        OrderInquiryLink,
        OrderInquiryRow,
        ProjectSalesOrderLine,
    )

    query = (
        self.db.query(
            SalesOrderLine.source_ref,
            SalesOrderLine.product_id,
            SalesOrderLine.company_id,
            SPOAllocation.spo_number,
            OrderInquiryLink.qty,
            SPOAllocation.quantity_received,
        )
        .join(
            ProjectSalesOrderLine,
            ProjectSalesOrderLine.core_sales_order_line_id == SalesOrderLine.id,
        )
        .join(OrderInquiryRow, OrderInquiryRow.so_line_id == ProjectSalesOrderLine.id)
        .join(OrderInquiryLink, OrderInquiryLink.row_id == OrderInquiryRow.id)
        .join(
            SPOAllocation,
            (SPOAllocation.id == OrderInquiryLink.spo_allocation_id)
            & (SPOAllocation.product_id == SalesOrderLine.product_id)
            & (SPOAllocation.company_id == SalesOrderLine.company_id),
        )
        .filter(
            SalesOrderLine.source_ref.in_(list(refs)),
            SalesOrderLine.product_id.in_(list(product_ids)),
            OrderInquiryRow.state != INQUIRY_CANCELLED,
        )
    )
    if company_id is not None:
        query = query.filter(SalesOrderLine.company_id == company_id)
    return query.all()


def _norm(rows):
    return Counter(
        (
            str(ref),
            str(product),
            str(company),
            spo_number,
            Decimal(str(placed)),
            Decimal(str(received)),
        )
        for ref, product, company, spo_number, placed, received in rows
    )


def _another_row(db, inquiry, project_line, allocation, qty):
    """A second order-inquiry row on the same inquiry (one inquiry per sales order)."""
    from app.models.project_so import IV_ORDER_BACK, OrderInquiryLink, OrderInquiryRow

    row = OrderInquiryRow(
        id=_u(), company_id=SORENTO_COMPANY_ID, order_inquiry_id=inquiry.id,
        so_line_id=project_line.id, qty=Decimal(str(qty)), verb=IV_ORDER_BACK,
    )
    db.add(row)
    db.flush()
    db.add(OrderInquiryLink(
        id=_u(), company_id=SORENTO_COMPANY_ID, row_id=row.id,
        spo_allocation_id=allocation.id, qty=Decimal(str(qty)),
    ))
    db.flush()
    return row


def _core_line(db, project_line):
    from app.models.order import SalesOrderLine

    return db.get(SalesOrderLine, project_line.core_sales_order_line_id)


def _seed(db):
    """Every shape the read meets. Returns (world, refs by name, other product)."""
    from app.models.project_so import INQUIRY_CANCELLED

    w = _World(db)
    other = _product(db, f"{w.marker}-B")
    refs = {}

    def line(name, qty=10):
        order, project_line = w._project_line(qty)
        core = _core_line(db, project_line)
        core.source_ref = f"ZZTEQ{name}{_u()[:6]}"
        db.flush()
        refs[name] = core.source_ref
        return order, project_line, core

    def spo(product=None, *, qty=10, received=0, status="pending"):
        return _spo(
            db, product or w.product, w.b1, qty=qty, arrives=w.due, received=received,
            receipt_status=status,
            line_status="closed" if status == "fully_received" else "open",
        )

    # Received in full: placement 5 on an SPO that landed 5.
    order, pl, _ = line("FULL")
    _order_back_link_on_spo(db, order, pl, allocation=spo(qty=5, received=5,
                            status="fully_received"), qty=5)
    # Partial: placement 10 on an SPO that has landed 4 so far.
    order, pl, _ = line("PART")
    _order_back_link_on_spo(db, order, pl, allocation=spo(received=4,
                            status="partially_received"), qty=10)
    # Not landed yet.
    order, pl, _ = line("NONE")
    _order_back_link_on_spo(db, order, pl, allocation=spo(), qty=6)
    # Cancelled order-inquiry row: places nothing.
    order, pl, _ = line("CANC")
    _inq, row, _link = _order_back_link_on_spo(
        db, order, pl, allocation=spo(received=10, status="fully_received"), qty=10
    )
    row.state = INQUIRY_CANCELLED
    # Multi-SPO: one line placed on two SPOs, by two rows; and a second link on one row.
    order, pl, _ = line("MULTI")
    inquiry, _row, _link = _order_back_link_on_spo(
        db, order, pl, allocation=spo(received=3, status="partially_received"), qty=4
    )
    row = _another_row(db, inquiry, pl, spo(received=6, status="fully_received"), 6)
    from app.models.project_so import OrderInquiryLink

    db.add(OrderInquiryLink(
        id=_u(), company_id=SORENTO_COMPANY_ID, row_id=row.id,
        spo_allocation_id=spo(received=2, status="partially_received").id,
        qty=Decimal("2"),
    ))
    # Two placements on the SAME SPO (both rows must come back, not one).
    order, pl, _ = line("SAME")
    shared = spo(qty=20, received=20, status="fully_received")
    inquiry, _row, _link = _order_back_link_on_spo(db, order, pl, allocation=shared, qty=8)
    _another_row(db, inquiry, pl, shared, 7)
    # The SPO is for another product: the AC-6 pairing refuses it.
    order, pl, _ = line("WRONGPROD")
    _order_back_link_on_spo(db, order, pl, allocation=spo(other, received=9,
                            status="fully_received"), qty=9)
    # The SPO names no company: NULL equals nothing.
    order, pl, _ = line("NOCOMPANY")
    nulled = spo(received=5, status="fully_received")
    _order_back_link_on_spo(db, order, pl, allocation=nulled, qty=5)
    nulled.company_id = None
    # Two core lines sharing one source_ref: both answer.
    order, pl, core = line("DUP")
    _order_back_link_on_spo(db, order, pl, allocation=spo(received=1,
                            status="partially_received"), qty=3)
    order, pl2, core2 = line("DUP2")
    core2.source_ref = core.source_ref
    refs["DUP2"] = core.source_ref
    _order_back_link_on_spo(db, order, pl2, allocation=spo(received=2,
                            status="partially_received"), qty=2)
    # A line with no placement at all, and one placed on a PO line (no SPO).
    line("BARE")
    db.flush()
    return w, refs, other


def _both(svc, monkeypatch, refs, product_ids, **kwargs):
    new = svc._oi_placements(refs, product_ids, **kwargs)
    old = _old_oi_placements(svc, refs, product_ids, **kwargs)
    return _norm(new), _norm(old)


def test_new_read_equals_the_old_statement_row_for_row(scm_app, monkeypatch):
    from app.services.project_supply_service import ProjectSupplyService

    db = scm_app[1]
    w, refs, other = _seed(db)
    svc = ProjectSupplyService(db)
    pid, oid = str(w.product.id), str(other.id)
    every = list(refs.values()) + [f"ZZTEQPAD{i:04d}" for i in range(40)]

    new, old = _both(svc, monkeypatch, every, [pid, oid])
    assert new == old
    # The seed is not vacuous: every placement shape that should answer, answers.
    answered = {ref for ref, *_ in new}
    for name in ("FULL", "PART", "NONE", "MULTI", "SAME", "DUP"):
        assert refs[name] in answered, name
    for name in ("CANC", "WRONGPROD", "NOCOMPANY", "BARE"):
        assert refs[name] not in answered, name
    assert sum(1 for row in new.elements() if row[0] == refs["MULTI"]) == 3
    assert sum(1 for row in new.elements() if row[0] == refs["SAME"]) == 2
    assert sum(1 for row in new.elements() if row[0] == refs["DUP"]) == 2

    # Every narrower question too: one product, one ref, the company filter, nothing at all.
    for case_refs, case_products, kwargs in [
        (every, [pid], {}),
        (every, [oid], {}),
        ([refs["MULTI"]], [pid], {}),
        (every, [pid], {"company_id": SORENTO_COMPANY_ID}),
        (every, [pid], {"company_id": "00000000-0000-0000-0000-0000000000ff"}),
        ([f"ZZTEQNONE{_u()[:6]}"], [pid], {}),
        (every, [str(_u())], {}),
    ]:
        new, old = _both(svc, monkeypatch, case_refs, case_products, **kwargs)
        assert new == old, (case_refs[:2], case_products, kwargs)


def test_empty_inputs_answer_nothing_without_a_query(scm_app):
    from app.services.project_supply_service import ProjectSupplyService

    svc = ProjectSupplyService(scm_app[1])
    assert svc._oi_placements([], ["x"]) == []
    assert svc._oi_placements(["x"], []) == []
    assert svc._oi_placements(iter(()), iter(())) == []


def test_callers_answer_the_same_with_the_old_statement(scm_app, monkeypatch):
    """`_oi_linked_landed_by_ref` and the batched `_po_received_by_product` (Stock Debt's
    landed holds read this) give the same landed answer on the new read as on the oracle."""
    from app.services.project_supply_service import ProjectSupplyService

    db = scm_app[1]
    w, refs, other = _seed(db)
    pid = str(w.product.id)
    every = sorted(set(refs.values()))

    def answers():
        svc = ProjectSupplyService(db)
        return (
            svc._oi_linked_landed_by_ref(every, product_id=pid, company_id=None),
            svc._oi_linked_landed_by_ref(every, product_id=pid, company_id=SORENTO_COMPANY_ID),
            svc._po_received_by_product({pid: every, str(other.id): every}),
        )

    new = answers()
    monkeypatch.setattr(ProjectSupplyService, "_oi_placements", _old_oi_placements)
    old = answers()
    assert new == old
    # Landed is min(placed, received) per placement: PART 4 of 10, MULTI 3 + 6 + 2.
    landed = new[0]
    assert sum(landed[refs["PART"]].values()) == Decimal("4")
    assert sum(landed[refs["MULTI"]].values()) == Decimal("11")
    assert refs["CANC"] not in landed
