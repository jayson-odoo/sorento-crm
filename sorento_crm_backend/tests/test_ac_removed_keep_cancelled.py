"""AC-REMOVED-KEEP-CANCELLED: a PO / SO line AutoCount removes stays, Cancelled.

UAC: documentation/plans/scm/ac-removed-keep-cancelled-27oct-acceptance-criteria.md
     AC-KC-1 .. 5.

Owner ruling (27 Oct 2026): "it stays cancelled, but the linkage is gone". Before this
fix `DocumentIngestService._sync_lines` hard-deleted any leftover line nothing pointed
at, so a removed line with no link (or one whose links AC-REMOVED-LINES had just
released) vanished on the next push (PO 202607-S0081, SRTSA-SS 546).

Postgres only, driven through the real HTTP ingest routes. No real customer names.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from app.models.project_so import INQUIRY_RAISED, OrderInquiryLink

from .test_ac_removed_lines_ingest import (
    QTY,
    _oi_row_on,
    _po_line_row,
    _push_po,
    _push_so,
    _remove_so_line_x,
    _repush_without_a,
    _row_snapshot,
)
from .test_ingest_documents import env  # noqa: F401 - pytest fixture, imported for reuse
from .test_oi_cancelled_line_used_confirm import _uid

__all__ = ["env"]


def _line(env, table, line_id):
    env.db.expire_all()
    row = env.db.execute(
        text(f"SELECT * FROM {table} WHERE id = :i"), {"i": line_id}
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


def _sweep_counts(res):
    return res.json()["records"][0]["lines"]


# ======================================================================== AC-KC-1
def test_ac_kc_1_a_removed_po_line_nothing_points_at_is_cancelled_not_deleted(env):
    w = _push_po(env)
    assert _line(env, "purchase_order_lines", w.line_a)["line_status"] == "open"

    res = _repush_without_a(env, w)

    line = _line(env, "purchase_order_lines", w.line_a)
    assert line is not None, "an AutoCount-removed line must never be deleted"
    assert line["line_status"] == "cancelled"
    assert line["qty_ordered"] == Decimal(QTY)
    assert line["source_ref"] == w.payload_a["source_ref"]
    counts = _sweep_counts(res)
    assert counts["deleted"] == 0 and counts["cancelled"] == 1, counts


def test_ac_kc_1_a_fully_received_removed_line_is_kept_with_its_received_qty(env):
    """The 546 shape: received in full (closed), no FK, then removed in AutoCount."""
    w = _push_po(env, a_received=QTY)

    _repush_without_a(env, w)

    line = _line(env, "purchase_order_lines", w.line_a)
    assert line is not None
    assert line["line_status"] == "cancelled"
    assert line["qty_received"] == Decimal(QTY)


# ======================================================================== AC-KC-2
def test_ac_kc_2_an_already_cancelled_line_absent_again_still_exists(env):
    w = _push_po(env)
    _repush_without_a(env, w)
    assert _line(env, "purchase_order_lines", w.line_a)["line_status"] == "cancelled"

    res = _repush_without_a(env, w)
    _repush_without_a(env, w)

    line = _line(env, "purchase_order_lines", w.line_a)
    assert line is not None
    assert line["line_status"] == "cancelled"
    assert _sweep_counts(res)["deleted"] == 0


# ======================================================================== AC-KC-3
def test_ac_kc_3_release_on_push_1_then_push_2_keeps_the_line_cancelled_unlinked(env):
    w = _push_po(env)
    row_id, inquiry_id, _ = _oi_row_on(env, w)

    _repush_without_a(env, w)  # push 1: cancel + release
    after_1 = _row_snapshot(env, row_id, inquiry_id)
    assert after_1["link_lines"] == [] and after_1["state"] == INQUIRY_RAISED, after_1

    _repush_without_a(env, w)  # push 2: the line now has no FK at all

    line = _line(env, "purchase_order_lines", w.line_a)
    assert line is not None, "push 2 must not delete the released line"
    assert line["line_status"] == "cancelled"
    assert (
        env.db.query(OrderInquiryLink).filter(OrderInquiryLink.po_line_id == w.line_a).count()
        == 0
    )
    assert _row_snapshot(env, row_id, inquiry_id)["state"] == INQUIRY_RAISED


# ======================================================================== AC-KC-4
def test_ac_kc_4_a_removed_so_line_is_cancelled_not_deleted_on_every_push(env):
    record, header, line_x, y = _push_so(env)

    _remove_so_line_x(env, record, y)
    first = _line(env, "sales_order_lines", line_x["id"])
    assert first is not None, "an AutoCount-removed SO line must never be deleted"
    assert first["line_status"] == "cancelled"

    _remove_so_line_x(env, record, y)

    second = _line(env, "sales_order_lines", line_x["id"])
    assert second is not None
    assert second["line_status"] == "cancelled"
    assert second["source_ref"] == line_x["source_ref"]


# ======================================================================== AC-KC-5
def test_ac_kc_5_a_ref_less_leftover_nothing_points_at_is_still_deleted(env):
    """Unchanged: an xlsx-era line (no DtlKey) is the duplicate-count guard's case, not
    an AutoCount line, so an unreferenced one still goes."""
    from app.models.procurement import PurchaseOrderLine

    w = _push_po(env)
    refless = PurchaseOrderLine(
        id=_uid(), company_id=env.company_a, purchase_order_id=w.header_id,
        product_id=w.product_id, qty_ordered=Decimal(QTY), line_status="cancelled",
        source_ref=None, source_system=None,
    )
    env.db.add(refless)
    env.db.commit()
    refless_id = str(refless.id)

    res = _repush_without_a(env, w)

    assert _line(env, "purchase_order_lines", refless_id) is None
    assert _sweep_counts(res)["deleted"] == 1
    assert _line(env, "purchase_order_lines", w.line_a)["line_status"] == "cancelled"
