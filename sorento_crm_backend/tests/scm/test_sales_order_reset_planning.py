"""Reset planning: one sales order back to never-planned, from the Sales Orders page.

The captain, 27 Aug: a UAT walk has to be repeatable without a script. The action takes
every planning artefact the order grew (inquiries, rows, links, claims, allocations,
transfers, supply decisions, planning-change rows) and leaves the order, its lines, and
every other order alone.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.project_so import (
    DECISION_ACTIVE,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    OrderInquiry,
    OrderInquiryRow,
    SOLineAllocation,
    SOSupplyDecision,
    ProjectSalesOrderLine,
)
from app.models.scm import OrderLinkClaim
from tests.scm.conftest import requires_pg
from tests.scm.test_sales_order_inquiries import _as, _core_order, _inquiry, _planned

pytestmark = requires_pg

MARKER = "ZZTSORESET"


def _uid() -> str:
    return str(uuid.uuid4())


def _grow(db, core, pso, *, number):
    """Everything a confirm and an acknowledge leave behind, in miniature."""
    line = ProjectSalesOrderLine(
        id=_uid(), company_id=pso.company_id, project_sales_order_id=pso.id, line_no=1,
        description=f"{MARKER} line", qty=Decimal("5"),
    )
    db.add(line)
    db.flush()
    decision = SOSupplyDecision(
        id=_uid(), company_id=pso.company_id, project_sales_order_id=pso.id,
        revision_no=1, state=DECISION_ACTIVE, confirmed_at=datetime.utcnow(),
        line_snapshots=[{"line_no": 1}],
    )
    db.add(decision)
    db.flush()
    db.add(SOLineAllocation(
        id=_uid(), company_id=pso.company_id, so_line_id=line.id, source_type="own",
        qty=Decimal("5"), decision_id=decision.id,
    ))
    _inquiry(db, pso, number=number, rows=((INQUIRY_RAISED, 2), (INQUIRY_PLACED, 1)))
    db.add(OrderLinkClaim(
        id=_uid(), company_id=pso.company_id, so_number=core.so_number,
        po_number=f"{MARKER}-PO", item_code=f"{MARKER}-ITEM", source="order_inquiry",
    ))
    db.flush()


def _counts(db, pso_id, so_number):
    return {
        "inquiries": db.query(OrderInquiry).filter_by(project_sales_order_id=pso_id).count(),
        "rows": db.query(OrderInquiryRow).join(OrderInquiry).filter(
            OrderInquiry.project_sales_order_id == pso_id).count(),
        "decisions": db.query(SOSupplyDecision).filter_by(project_sales_order_id=pso_id).count(),
        "allocations": db.query(SOLineAllocation).join(ProjectSalesOrderLine).filter(
            ProjectSalesOrderLine.project_sales_order_id == pso_id).count(),
        "claims": db.query(OrderLinkClaim).filter_by(so_number=so_number, source="order_inquiry").count(),
        "lines": db.query(ProjectSalesOrderLine).filter_by(project_sales_order_id=pso_id).count(),
    }


def test_reset_takes_the_planning_and_leaves_the_order_and_its_neighbour(scm_app):
    app, db, uid = _as(scm_app, "purchasing")
    core = _core_order(db)
    pso = _planned(db, core)
    _grow(db, core, pso, number=f"{MARKER}-OI-1")
    other_core = _core_order(db)
    other = _planned(db, other_core)
    _grow(db, other_core, other, number=f"{MARKER}-OI-2")
    db.commit()
    before = _counts(db, pso.id, core.so_number)
    assert before == {"inquiries": 1, "rows": 3, "decisions": 1, "allocations": 1, "claims": 1, "lines": 1}

    with TestClient(app) as c:
        res = c.post(f"/api/v1/scm/sales-orders/{core.id}/reset-planning", json={})

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["so_number"] == core.so_number
    assert body["removed"]["order_inquiries"] == 1
    assert body["removed"]["order_inquiry_rows"] == 3
    assert body["removed"]["supply_decisions"] == 1
    assert body["removed"]["allocations"] == 1
    assert body["removed"]["claims"] == 1

    db.expire_all()
    after = _counts(db, pso.id, core.so_number)
    assert after == {"inquiries": 0, "rows": 0, "decisions": 0, "allocations": 0, "claims": 0, "lines": 1}
    # The order itself, and the neighbour, are as they were.
    assert db.execute(text("SELECT count(*) FROM sales_orders WHERE id = :i"), {"i": core.id}).scalar() == 1
    assert _counts(db, other.id, other_core.so_number)["rows"] == 3


def test_reset_on_an_order_never_planned_is_a_no_op(scm_app):
    app, db, uid = _as(scm_app, "purchasing")
    core = _core_order(db)
    db.commit()
    with TestClient(app) as c:
        res = c.post(f"/api/v1/scm/sales-orders/{core.id}/reset-planning", json={})
    assert res.status_code == 200, res.text
    assert res.json()["removed"]["order_inquiries"] == 0


def test_reset_needs_the_write_permission(scm_app):
    app, db, uid = _as(scm_app, None)
    core = _core_order(db)
    db.commit()
    with TestClient(app) as c:
        res = c.post(f"/api/v1/scm/sales-orders/{core.id}/reset-planning", json={})
    assert res.status_code == 403, res.text
