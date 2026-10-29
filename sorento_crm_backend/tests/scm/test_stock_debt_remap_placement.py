"""STOCKDEBT-PERF PR1: a remapped placement keeps its DOCUMENT product's stock in the walk.

A placement on an open SO line of product Q names a document of product P (a remap: the
mirror line carries P, the core line Q; `_holds` reads `coalesce(SPOAllocation.product_id,
PurchaseOrderLine.product_id)`). P holds stock at the bin but has no open demand. Narrowing
the default view to demand-bearing products must not drop P's on-hand event from the walk, or
`found_empty` drops the hold and Q reads short on the default view only.
"""
from __future__ import annotations

from datetime import timedelta

from tests.scm.conftest import requires_pg
from tests.scm.test_stock_debt_routes import (
    TODAY,
    _client,
    _demand,
    _months_ahead,
    _order_back_link_on_spo,
    _product,
    _project_line_for,
    _spo,
    _stock,
    _u,
    _warehouse,
)

pytestmark = requires_pg


def test_remapped_placement_reads_covered_on_the_default_view(scm_app):
    from app.services.scm.stock_debt_service import StockDebtService

    app, db = _client(scm_app)
    marker = f"ZZTRV{_u()[:6]}".upper()
    wh = _warehouse(db, f"ZZTBRW{_u()[:4]}-BB")
    q = _product(db, f"{marker}-Q")
    p = _product(db, f"{marker}-P")
    _stock(db, p, wh, 50)
    due = _months_ahead(1)
    _order, core_line = _demand(
        db, q, wh, qty=50, required_date=due, so_number=f"{marker}-SO1"
    )
    project_order, project_line = _project_line_for(db, core_line)
    project_line.product_id = p.id  # the remap
    db.flush()
    allocation = _spo(
        db, p, wh, qty=50, arrives=TODAY - timedelta(days=20),
        received=50, receipt_status="fully_received",
    )
    _order_back_link_on_spo(db, project_order, project_line, allocation=allocation, qty=50)
    db.flush()

    svc = StockDebtService(db)
    everything = svc.list(query=marker, only_debt=False)
    default = svc.list(query=marker, only_debt=True)

    # (2) the full board reads Q covered: 0 owed
    q_full = [r for r in everything["data"] if r["product_code"] == q.product_code]
    assert len(q_full) == 1
    assert q_full[0]["total"] == 0
    # (1) so the default view has no row for Q, and its figures are the full board's
    q_default = [r for r in default["data"] if r["product_code"] == q.product_code]
    assert q_default == [], [(r["product_code"], r["total"]) for r in q_default]
    assert default["totals"]["total"] == 0
