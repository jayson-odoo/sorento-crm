"""OI-AUTO-CONFIRM review round 1: an AutoCount cancel document on a PO line reopens the
row it covered (hook coverage, should-fix 4). Own file: the cancel-doc `env` differs.
"""
from __future__ import annotations

from app.models.procurement import PurchaseOrder, PurchaseOrderLine
from app.models.product import Product
from app.models.project_so import ACK_ACKNOWLEDGED, ACK_AWAITING
from app.services.project_order_inquiry_service import ProjectOrderInquiryService

from .test_ingest_autocount_cancel_docs import XP_INGEST, _detail, _xp
from .test_ingest_autocount_do_grn import env  # noqa: F401  (fixture)
from .test_oi_cancelled_line_used_confirm import _inquiry, _line_chain, _oi_row
from .test_order_inquiry_kinds import _link


def _reload(db, row):
    db.refresh(row)
    return row


def test_hook_an_autocount_cancel_doc_on_the_po_line_reopens_the_row(env):
    po = PurchaseOrder(po_number="ZZPO-R1-001", company_id=env.company)
    env.db.add(po)
    env.db.flush()
    pol = PurchaseOrderLine(
        purchase_order_id=po.id, product_id=env.p1, qty_ordered=100, qty_received=0,
        source_ref="SRT_DB:7001:7101", company_id=env.company,
    )
    env.db.add(pol)
    env.db.flush()
    product = env.db.get(Product, env.p1)
    _so, _core, pso, mirror = _line_chain(env.db, env.company, product, qty="10")
    inquiry = _inquiry(env.db, env.company, pso.id)
    row = _oi_row(env.db, env.company, inquiry.id, mirror.id, product.product_code, "10",
                  ack_state=ACK_AWAITING)
    _link(env.db, env.company, row.id, "10", po_line_id=pol.id, document="ZZPO-R1-001")
    env.db.commit()
    ProjectOrderInquiryService(env.db).auto_confirm([row.id])
    env.db.commit()
    assert _reload(env.db, row).ack_state == ACK_ACKNOWLEDGED, "fixture: fully linked"

    rec = _xp(details=[_detail(961001, qty=100, from_no="ZZPO-R1-001", from_dtl=7101,
                               from_type="PO")])
    assert env.post(XP_INGEST, [rec]).status_code == 200
    env.db.expire_all()

    assert env.db.get(PurchaseOrderLine, str(pol.id)).line_status == "cancelled"
    assert _reload(env.db, row).ack_state == ACK_AWAITING, "the PO line behind the link died"


