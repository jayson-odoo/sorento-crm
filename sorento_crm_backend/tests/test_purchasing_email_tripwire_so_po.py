"""FP-EMAIL-ONE-TRIGGER regression guard, part 1: AutoCount / ESB sales order and purchase order
pushes never email purchasing.

Owner rule, 6 Nov 2026: the purchasing email has one trigger, the board Confirm (Publish
amendment is his named exception). Owner, 18:10: if any integration / sync path ever emails
purchasing again, a test must fail. This is that test for the SO and PO ingest
(`POST /api/v1/external/ingest/sales_orders|purchase_orders`, the real route, its commit and its
post-write hooks), with the purchasing automations ENABLED and their conditions passing
(`tests/_purchasing_email_tripwire.py`), on order inquiry rows a change would have told
purchasing about: one raised, one placed on a PO line. Part 2 (Cancel SO documents, DO, GRN):
`tests/test_purchasing_email_tripwire_docs.py`. Listed in
`tests/test_lessons_learnt_regressions.py`.

Postgres only, every chain seeded here.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.models.order import SalesOrderLine
from app.models.project_so import INQUIRY_PLACED, INQUIRY_RAISED

from ._purchasing_email_tripwire import Tripwire
from .test_ac_removed_lines_ingest import (
    QTY,
    _oi_row_on,
    _push_po,
    _push_so,
    _repush_without_a,
    _so_mirror_row,
)
from .test_ingest_documents import (  # noqa: F401 - env is a fixture
    INGEST_PO,
    INGEST_SO,
    _ref,
    _so_line,
    env,
)

__all__ = ["env"]


def _so_world(env):
    """A pushed two-line SO (x, y) with a raised row and a PO-placed row on line x."""
    po = _push_po(env)
    record, header, line_x, y = _push_so(env)
    _so_mirror_row(env, header, line_x, state=INQUIRY_RAISED)
    _so_mirror_row(
        env, header, line_x, state=INQUIRY_PLACED, links=1, qty="4",
        po_line_id=po.line_b, po_number=po.po_number, share=_so_mirror_row.last,
    )
    x = next(line for line in record["lines"] if line["source_ref"] == line_x["source_ref"])
    return record, x, y


def _push(env, record) -> None:
    res = env.post(INGEST_SO, [record])
    assert res.status_code == 200, res.text
    env.db.expire_all()


def _removed(env, record, x, y):
    return dict(record, lines=[y])


def _added(env, record, x, y):
    return dict(record, lines=[x, y, _so_line(env, qty_ordered=3)])


def _qty_changed(env, record, x, y):
    return dict(record, lines=[dict(x, qty_ordered=QTY + 5), y])


def _date_changed(env, record, x, y):
    return dict(record, lines=[dict(x, required_date=date(2027, 3, 15).isoformat()), y])


def _item_changed(env, record, x, y):
    swapped = {k: v for k, v in x.items() if k != "product_code"}
    swapped["product_ref"] = env.product2_ref
    return dict(record, lines=[_so_line(env, ref=x["source_ref"], product_ref=env.product2_ref,
                                        qty_ordered=x["qty_ordered"]), y])


def _rekeyed(env, record, x, y):
    return dict(record, lines=[dict(x, source_ref=_ref("SOL")), y])


def _header_cancelled(env, record, x, y):
    return dict(record, status="cancelled")


SO_SCENARIOS = {
    "SO line removed": _removed,
    "SO line added": _added,
    "SO qty changed": _qty_changed,
    "SO date changed": _date_changed,
    "SO item changed": _item_changed,
    "SO line re-keyed": _rekeyed,
    "SO header cancelled": _header_cancelled,
}


@pytest.mark.parametrize("scenario", list(SO_SCENARIOS))
def test_an_autocount_so_push_emails_purchasing_nothing(env, monkeypatch, scenario):
    record, x, y = _so_world(env)
    wire = Tripwire.arm(env.db, monkeypatch)
    before = wire.snapshot()

    _push(env, SO_SCENARIOS[scenario](env, record, x, y))

    wire.assert_silent_since(before, scenario)


def test_an_autocount_po_push_removing_a_linked_line_emails_purchasing_nothing(env, monkeypatch):
    po = _push_po(env)
    _oi_row_on(env, po)
    wire = Tripwire.arm(env.db, monkeypatch)
    before = wire.snapshot()

    _repush_without_a(env, po)

    wire.assert_silent_since(before, "PO line removed")


def test_an_autocount_po_push_that_reruns_auto_confirm_emails_purchasing_nothing(env, monkeypatch):
    """Every PO push re-reads its linked rows' done-ness (`auto_confirm_rows_on_po_lines`); a
    receipt on the linked line moves it, and nobody is emailed."""
    po = _push_po(env)
    _oi_row_on(env, po)
    wire = Tripwire.arm(env.db, monkeypatch)
    before = wire.snapshot()

    received = [dict(po.payload_a, qty_received=QTY), po.payload_b]
    res = env.post(INGEST_PO, [dict(po.record, lines=received)])
    assert res.status_code == 200, res.text

    wire.assert_silent_since(before, "PO auto-confirm (line received)")


def test_positive_control_the_tripwire_sees_a_confirm_shaped_write(env, monkeypatch):
    """The same harness DOES see an email when the write is marked the way the board Confirm
    marks it, so the zero assertions above are not blind."""
    from app.services.project_order_inquiry_service import (
        ProjectOrderInquiryService,
        mark_purchasing_email_trigger,
    )

    record, x, y = _so_world(env)
    wire = Tripwire.arm(env.db, monkeypatch)
    before = wire.snapshot()
    core = env.db.query(SalesOrderLine).filter(SalesOrderLine.source_ref == x["source_ref"]).one()

    mark_purchasing_email_trigger(env.db)
    ProjectOrderInquiryService(env.db).retire_rows_for_removed_so_lines([core])
    env.db.commit()

    wire.assert_tripped_since(before)
