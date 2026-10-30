"""OI-AUTO-CONFIRM slice 2, AC-AC-22 (Q4 = b): the reorder plan counts every live,
not-rejected project buy row that is To order (`awaiting` / `changed`) for its uncovered
qty; a Done row (automatic or manual) adds nothing; the SO picker drops `rows_awaiting`.

Seeds through `tests/test_reorder_plan_demand_scope.py`'s own single-ORDER-row chain and
reads the plan's committed figure through `demand.horizon_committed_select_sql`.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    ACK_AWAITING,
    ACK_CHANGED,
    ACK_REJECTED,
    OrderInquiryLink,
)
from app.services.scm import demand
from tests.scm.conftest import requires_pg, scm_app  # noqa: F401 - pytest fixture
from tests.scm.test_m3_run import _client, _mk_product, _mk_warehouse

from .test_reorder_plan_demand_scope import (
    _code,
    _project_so_with_lines,
    _project_so_single_order_row,
)

pytestmark = requires_pg


def _u() -> str:
    return str(uuid.uuid4())


def _project_figure(db, pid: str, wid: str) -> float:
    sql = demand.horizon_committed_select_sql(demand_class="project", so_scoped=False)
    rows = db.execute(text(sql), {"horizon": None, "horizon_start": None}).mappings().all()
    return {
        str(r["warehouse_id"]): float(r["project_committed"])
        for r in rows
        if str(r["product_id"]) == pid
    }.get(wid, 0.0)


def _one_row(db, *, ack_state, qty=10):
    wid = _mk_warehouse(db, _code("WH"))
    pid = _mk_product(db, _code("P"))
    db.flush()
    seeded = _project_so_single_order_row(
        db, product_id=pid, warehouse_id=wid, line_ordered=qty, line_delivered=0,
        row_qty=qty, line_status="open",
    )
    seeded["row"].ack_state = ack_state
    db.flush()
    return pid, wid, seeded["row"]


def _link_po(db, row, pid, wid, qty) -> None:
    from app.models.product import Product  # noqa: F401

    company_id = row.company_id
    supplier = Supplier(
        id=_u(), company_id=company_id, supplier_code=_code("SUP"), supplier_name="ZZT sup"
    )
    db.add(supplier)
    db.flush()
    po = PurchaseOrder(
        id=_u(), company_id=company_id, po_number=_code("PO"), supplier_id=supplier.id,
        issue_date=date(2026, 6, 1), status="active",
    )
    db.add(po)
    db.flush()
    line = PurchaseOrderLine(
        id=_u(), company_id=company_id, purchase_order_id=po.id, product_id=pid,
        warehouse_id=wid, qty_ordered=Decimal(qty), qty_received=Decimal("0"),
        expected_date=date(2026, 12, 1), line_status="open",
    )
    db.add(line)
    db.flush()
    db.add(
        OrderInquiryLink(
            id=_u(), company_id=company_id, row_id=row.id, po_line_id=line.id,
            document=po.po_number, qty=Decimal(qty),
        )
    )
    db.flush()


def test_ac_ac_22_an_awaiting_uncovered_row_counts_in_full(scm_app):
    _, db, _, _ = scm_app
    pid, wid, _row = _one_row(db, ack_state=ACK_AWAITING)

    assert _project_figure(db, pid, wid) == 10.0


def test_ac_ac_22_a_changed_row_covered_six_of_ten_counts_four(scm_app):
    _, db, _, _ = scm_app
    pid, wid, row = _one_row(db, ack_state=ACK_CHANGED)
    _link_po(db, row, pid, wid, 6)

    assert _project_figure(db, pid, wid) == 4.0


def test_ac_ac_22_a_manually_confirmed_row_with_no_link_counts_nothing(scm_app):
    _, db, _, _ = scm_app
    pid, wid, row = _one_row(db, ack_state=ACK_ACKNOWLEDGED)
    row.ack_override = "confirmed"  # column lands with slice 2; red at setup until then
    db.flush()

    assert _project_figure(db, pid, wid) == 0.0


def test_ac_ac_22_a_rejected_row_counts_nothing(scm_app):
    _, db, _, _ = scm_app
    pid, wid, _row = _one_row(db, ack_state=ACK_REJECTED)

    assert _project_figure(db, pid, wid) == 0.0


def test_ac_ac_22_the_so_picker_no_longer_carries_rows_awaiting(scm_app):
    app, db = _client(scm_app, "purchasing")
    wid = _mk_warehouse(db, _code("WH"))
    pid = _mk_product(db, _code("P"))
    db.flush()
    so = _project_so_with_lines(db, lines=[
        {"product_id": pid, "warehouse_id": wid, "qty": 3,
         "delivery_date": date(2026, 9, 10), "ack_state": ACK_AWAITING},
    ])

    with TestClient(app) as c:
        resp = c.get(
            "/api/v1/scm/reorder-runs/candidate-orders",
            params={"from": "2026-09-01", "to": "2026-10-31"},
        )

    assert resp.status_code == 200, resp.text
    item = {r["so_number"]: r for r in resp.json()}[so["so_number"]]
    assert "rows_awaiting" not in item
    assert item["rows_total"] == 1
