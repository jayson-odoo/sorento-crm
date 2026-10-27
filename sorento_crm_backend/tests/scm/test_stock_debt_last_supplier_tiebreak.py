"""STOCKDEBT-PERF PR1: the board's LAST supplier is deterministic on a tie.

Two non-cancelled PO lines tied on issue_date AND created_at (a bulk import) are ranked
by `PurchaseOrder.po_number desc`, then `PurchaseOrderLine.id desc`. Written before the
implementation: today the tie is broken by query plan.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from tests.scm.conftest import SORENTO_COMPANY_ID, requires_pg
from tests.scm.test_stock_debt_routes import _client, _product, _supplier, _u

pytestmark = requires_pg

STAMP = datetime(2026, 9, 1, 8, 0, 0)


def _tied_po(db, product, supplier, po_number):
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine

    po = PurchaseOrder(
        id=_u(), po_number=po_number, supplier_id=supplier.id,
        issue_date=date(2026, 9, 1), status="active", company_id=SORENTO_COMPANY_ID,
        created_at=STAMP,
    )
    db.add(po)
    db.flush()
    db.add(
        PurchaseOrderLine(
            id=_u(), purchase_order_id=po.id, product_id=product.id, warehouse_id=None,
            qty_ordered=Decimal("5"), qty_received=Decimal("0"), line_status="open",
            company_id=SORENTO_COMPANY_ID, created_at=STAMP,
        )
    )
    db.flush()


def test_last_supplier_on_a_full_tie_is_the_higher_po_number(scm_app):
    """Product k: PO-A-000k (one supplier) and PO-B-000k (the other), inserted in
    alternating order with alternating supplier roles; the higher po_number always wins."""
    from app.services.scm.stock_debt_service import StockDebtService

    app, db = _client(scm_app)
    tag = _u()[:6].upper()
    s1 = _supplier(db, f"ZZTS1{tag}")
    s2 = _supplier(db, f"ZZTS2{tag}")
    expected = {}
    for k in range(8):
        product = _product(db, f"ZZTLS{tag}-{k}")
        low_sup, high_sup = (s1, s2) if k % 2 == 0 else (s2, s1)
        low, high = f"PO-A-{tag}{k}", f"PO-B-{tag}{k}"
        if k % 4 < 2:
            _tied_po(db, product, low_sup, low)
            _tied_po(db, product, high_sup, high)
        else:
            _tied_po(db, product, high_sup, high)
            _tied_po(db, product, low_sup, low)
        expected[str(product.id)] = str(high_sup.id)

    got = StockDebtService(db)._last_supplier_map(list(expected))
    wrong = {pid: got[pid]["id"] for pid in expected if got[pid]["id"] != expected[pid]}
    assert not wrong, f"higher po_number did not win for {len(wrong)} of {len(expected)}"
