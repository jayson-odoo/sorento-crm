"""OI-AUTO-CONFIRM slice 2, AC-AC-17c / 23 / 24: the one-time data pass.

Contract (fixed name): `app.services.oi_auto_confirm_backfill.backfill_auto_confirm(connection)
-> int` (rows changed), driven like `backfill_to_confirm` (scratch-schema connection). It
re-derives every live, not-rejected row by AC-AC-1..10c; it NEVER writes `ack_override`
(a press before this shipped is not a manual decision, AC-AC-17c).

Links are seeded straight into `order_inquiry_links` (not through the service, whose writers
would already derive the state), then `ack_state` is set to the pre-feature value.
Red today: the module does not exist (ImportError at the call).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import text

from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    ACK_AWAITING,
    ACK_CHANGED,
    ACK_REJECTED,
    OrderInquiryLink,
)

from .test_order_inquiry_bundles import _World, _projects, world as bundle_world  # noqa: F401
from . import test_order_inquiry_bundles as _bundles

STAMP = datetime(2026, 9, 1, 12, 0, 0)


def _uid() -> str:
    return str(uuid.uuid4())


def _set(w, row, *, ack, state=None, extra=""):
    p = _bundles.P
    sets = "ack_state = :a, acknowledged_at = :at, acknowledged_by = NULL" if ack == ACK_ACKNOWLEDGED else "ack_state = :a"
    if state:
        sets += ", state = :s"
    w.db.execute(
        text(f"UPDATE {p}.order_inquiry_rows SET {sets}{extra} WHERE id = :i"),
        {"a": ack, "at": STAMP, "s": state, "i": row.id},
    )
    w.db.flush()


def _po_link(w, row, product, qty, *, line_status="open"):
    line = w.purchase_order(product, f"ZZT-BF-PO-{_uid()[:6]}", "S1", qty)
    if line_status != "open":
        w.db.execute(
            text("UPDATE purchase_order_lines SET line_status = :s WHERE id = :l"),
            {"s": line_status, "l": line},
        )
    w.db.add(
        OrderInquiryLink(
            id=_uid(), company_id=w.company_id, row_id=row.id, po_line_id=line,
            document="ZZT-BF", qty=Decimal(qty),
        )
    )
    w.db.flush()


def _spo_link(w, row, product, qty):
    alloc = w.spo_allocation(product, f"ZZT-BF-SPO-{_uid()[:6]}", qty)
    w.db.add(
        OrderInquiryLink(
            id=_uid(), company_id=w.company_id, row_id=row.id, spo_allocation_id=alloc,
            document="ZZT-BF-SPO", qty=Decimal(qty),
        )
    )
    w.db.flush()


def _read(w, row):
    w.db.refresh(row)
    return row


def _seed(w):
    """One row per AC-AC-23 case, pre-feature `ack_state` values."""
    s = {}
    s["ack_full_po"] = w.row("CKS1050", 10)
    _po_link(w, s["ack_full_po"], "CKS1050", 10)
    _set(w, s["ack_full_po"], ack=ACK_ACKNOWLEDGED, state="placed")

    s["ack_no_link"] = w.row("CKS1050", 10)
    _set(w, s["ack_no_link"], ack=ACK_ACKNOWLEDGED)
    w.db.execute(
        text(f"UPDATE {_bundles.P}.order_inquiry_rows SET acknowledged_by = :u WHERE id = :i"),
        {"u": None, "i": s["ack_no_link"].id},
    )

    s["await_full_spo"] = w.row("X", 5)
    _spo_link(w, s["await_full_spo"], "X", 5)
    _set(w, s["await_full_spo"], ack=ACK_AWAITING, state="placed")

    s["await_partial"] = w.row("Y", 10)
    _po_link(w, s["await_partial"], "Y", 6)
    _set(w, s["await_partial"], ack=ACK_AWAITING, state="partly_linked")

    s["actioned"] = w.row("OTHER", 3)
    _set(w, s["actioned"], ack=ACK_AWAITING, state="actioned")

    s["delay"] = w.row("OTHER", 1, verb="DELAY")
    _set(w, s["delay"], ack=ACK_AWAITING)

    s["rejected"] = w.row("OTHER", 2)
    _set(w, s["rejected"], ack=ACK_REJECTED)

    s["cancelled"] = w.row("OTHER", 2)
    _set(w, s["cancelled"], ack=ACK_ACKNOWLEDGED, state="cancelled")

    s["changed_partial"] = w.row("SC", 10)
    _po_link(w, s["changed_partial"], "SC", 4)
    _set(w, s["changed_partial"], ack=ACK_CHANGED, state="partly_linked")

    s["dead_link"] = w.row("H2", 10)
    _po_link(w, s["dead_link"], "H2", 10, line_status="cancelled")
    _set(w, s["dead_link"], ack=ACK_ACKNOWLEDGED, state="placed")
    return s


def _companion(w, host_done: bool):
    host = w.row("C2", 1)
    if host_done:
        _po_link(w, host, "C2", 1)
        _set(w, host, ack=ACK_ACKNOWLEDGED, state="placed")
    else:
        _set(w, host, ack=ACK_ACKNOWLEDGED)
    comp = w.row("CKSW015", 1)
    w.db.execute(
        text(
            f"UPDATE {_bundles.P}.order_inquiry_rows SET bundled_qty = 1, "
            "bundled_with_row_id = :h WHERE id = :i"
        ),
        {"h": host.id, "i": comp.id},
    )
    _set(w, comp, ack=ACK_AWAITING, state="placed")
    return host, comp


def test_ac_ac_23_the_backfill_derives_every_row_and_17c_writes_no_override(bundle_world):
    from app.services.oi_auto_confirm_backfill import backfill_auto_confirm

    w = bundle_world
    s = _seed(w)
    done_host, done_comp = _companion(w, True)
    undone_host, undone_comp = _companion(w, False)
    w.db.flush()

    changed = backfill_auto_confirm(w.db.connection())
    w.db.flush()

    assert _read(w, s["ack_full_po"]).ack_state == ACK_ACKNOWLEDGED
    assert _read(w, s["ack_full_po"]).acknowledged_at == STAMP, "unchanged row not re-stamped"

    r = _read(w, s["ack_no_link"])
    assert r.ack_state == ACK_AWAITING
    assert r.acknowledged_by is None and r.acknowledged_at is None

    r = _read(w, s["await_full_spo"])
    assert r.ack_state == ACK_ACKNOWLEDGED and r.acknowledged_by is None
    assert r.acknowledged_at is not None

    assert _read(w, s["await_partial"]).ack_state == ACK_AWAITING
    assert _read(w, s["actioned"]).ack_state == ACK_ACKNOWLEDGED
    assert _read(w, s["delay"]).ack_state == ACK_ACKNOWLEDGED
    assert _read(w, s["rejected"]).ack_state == ACK_REJECTED
    assert _read(w, s["cancelled"]).ack_state == ACK_ACKNOWLEDGED, "cancelled rows are skipped"
    assert _read(w, s["changed_partial"]).ack_state == ACK_CHANGED
    assert _read(w, s["dead_link"]).ack_state != ACK_ACKNOWLEDGED, "its PO line is cancelled"

    assert _read(w, done_comp).ack_state == ACK_ACKNOWLEDGED, "host is done"
    assert _read(w, undone_host).ack_state == ACK_AWAITING
    assert _read(w, undone_comp).ack_state != ACK_ACKNOWLEDGED, "host is not done"

    # 8 changes: no_link, full_spo, actioned, delay, dead_link, done_comp, undone_host, plus
    # the undone companion only if it moved (it stays awaiting, so not counted).
    assert changed == 7, changed

    # AC-AC-17c: a person's earlier press is not a manual decision.
    overrides = w.db.execute(
        text(f"SELECT count(*) FROM {_bundles.P}.order_inquiry_rows WHERE ack_override IS NOT NULL")
    ).scalar()
    assert overrides == 0


def test_ac_ac_24_a_second_run_changes_nothing(bundle_world):
    from app.services.oi_auto_confirm_backfill import backfill_auto_confirm

    w = bundle_world
    s = _seed(w)
    _companion(w, True)
    w.db.flush()
    connection = w.db.connection()

    first = backfill_auto_confirm(connection)
    w.db.flush()
    before = {k: (_read(w, r).ack_state, r.acknowledged_at) for k, r in s.items()}

    second = backfill_auto_confirm(connection)
    w.db.flush()

    assert first > 0
    assert second == 0
    assert before == {k: (_read(w, r).ack_state, r.acknowledged_at) for k, r in s.items()}
