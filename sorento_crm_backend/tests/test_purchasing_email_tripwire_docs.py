"""FP-EMAIL-ONE-TRIGGER regression guard, part 2: AutoCount Cancel SO documents, delivery orders
and goods received notes never email purchasing.

Owner rule, 6 Nov 2026: the purchasing email has one trigger, the board Confirm (Publish
amendment is his named exception); if any integration / sync path ever emails purchasing again,
a test must fail. Each scenario runs the real ingest route
(`/api/v1/external/ingest/cancel_sales_orders|delivery_orders|goods_receive_notes`, its commit
and its hooks) with the purchasing automations ENABLED and passing
(`tests/_purchasing_email_tripwire.py`), on an order inquiry row the document touches. Part 1
(SO and PO pushes): `tests/test_purchasing_email_tripwire_so_po.py`. Listed in
`tests/test_lessons_learnt_regressions.py`.

Postgres only, every chain seeded here.
"""
from __future__ import annotations

import copy

from app.models.order import SalesOrderLine
from app.models.procurement import PurchaseOrder, PurchaseOrderLine
from app.models.project_so import INQUIRY_PLACED, INQUIRY_RAISED

from ._purchasing_email_tripwire import Tripwire
from .test_ingest_autocount_cancel_docs import XS_INGEST, _detail, _so, _xs
from .test_ingest_autocount_do_grn import (  # noqa: F401 - env is a fixture
    _records,
    _seed_so,
    _with_from,
    do_records,
    env,
    grn_records,
)
from .test_oi_cancelled_line_used_confirm import _mirror_for_ingest_line
from .test_order_inquiry_kinds import _link

__all__ = ["env"]


def _row_on(env, so_id: str, line_id: str, *, state=INQUIRY_RAISED, po_line_id=None):
    mirror, row = _mirror_for_ingest_line(
        env, so_id, line_id, env.p1, qty="10", row_state=state,
    )
    if po_line_id:
        _link(env.db, env.company, row.id, "10", po_line_id=po_line_id, document="ZZPO-0001")
        env.db.commit()
    return row


def test_an_autocount_cancel_so_document_emails_purchasing_nothing(env, monkeypatch):
    """A Cancel SO (XS) that cancels a line with a live order inquiry row: the line is
    cancelled and the Transfer to Cancel SO waits on the board (#1679); nobody is emailed."""
    lines = _so(env, lines=((5001, "p1", 10, 0, "wh1"),))
    so_id = str(env.db.get(SalesOrderLine, lines[5001]).sales_order_id)
    _row_on(env, so_id, lines[5001])
    wire = Tripwire.arm(env.db, monkeypatch)
    before = wire.snapshot()

    res = env.post(XS_INGEST, [_xs(details=[_detail(951001, qty=10.0, from_dtl=5001)])])
    assert res.status_code == 200, res.text
    env.db.expire_all()
    cancelled = env.db.get(SalesOrderLine, lines[5001]).qty_cancelled
    assert cancelled == 10, "fixture: the XS must cancel the line"

    wire.assert_silent_since(before, "Cancel SO document")


def test_an_autocount_delivery_order_emails_purchasing_nothing(env, monkeypatch):
    so_id, line_id = _seed_so(env)
    _row_on(env, so_id, line_id)
    wire = Tripwire.arm(env.db, monkeypatch)
    before = wire.snapshot()

    rec = _with_from(copy.deepcopy(do_records()[0]), 0, "SO", "ZZSO-0001", 5001)
    _records(env.push_do([rec]))

    wire.assert_silent_since(before, "DO arrival")


def test_an_autocount_goods_received_note_emails_purchasing_nothing(env, monkeypatch):
    so_id, line_id = _seed_so(env)
    po = PurchaseOrder(po_number="ZZPO-0001", company_id=env.company)
    env.db.add(po)
    env.db.flush()
    po_line = PurchaseOrderLine(purchase_order_id=po.id, product_id=env.p1, qty_ordered=100,
                                source_ref="SRT_DB:7001:7101", company_id=env.company)
    env.db.add(po_line)
    env.db.commit()
    _row_on(env, so_id, line_id, state=INQUIRY_PLACED, po_line_id=str(po_line.id))
    wire = Tripwire.arm(env.db, monkeypatch)
    before = wire.snapshot()

    rec = _with_from(copy.deepcopy(grn_records()[0]), 0, "PO", "ZZPO-0001", 7101)
    _records(env.push_grn([rec]))

    wire.assert_silent_since(before, "GRN arrival")


def test_positive_control_the_tripwire_sees_a_confirm_shaped_write(env, monkeypatch):
    """The same harness DOES see an email when the write is marked the way the board Confirm
    marks it, so the zero assertions above are not blind."""
    from app.services.project_order_inquiry_service import (
        ProjectOrderInquiryService,
        mark_purchasing_email_trigger,
    )

    so_id, line_id = _seed_so(env)
    _row_on(env, so_id, line_id)
    wire = Tripwire.arm(env.db, monkeypatch)
    before = wire.snapshot()

    mark_purchasing_email_trigger(env.db)
    ProjectOrderInquiryService(env.db).retire_rows_for_removed_so_lines(
        [env.db.get(SalesOrderLine, line_id)]
    )
    env.db.commit()

    wire.assert_tripped_since(before)
