"""AC-REMOVED-LINES, red tests: a PO / SO line AutoCount REMOVES releases its links.

UAC: documentation/plans/scm/ac-removed-lines-26oct-acceptance-criteria.md
     AC-RL-01 .. 06, 20 and the guards AC-RL-30, 32, 33, 34.
     (AC-RL-10 / 31 live in tests/test_ac_removed_lines_spo_ingest.py,
      AC-RL-40..43 in tests/test_release_removed_autocount_lines.py.)

TEST-FIRST: written before any implementation. Driven through the real HTTP ingest
routes (the `env` fixture of tests/test_ingest_documents.py), so the release can live in
the service or in a route hook and these tests do not care which.

Shape of every PO test: push a two-line AutoCount purchase order (line A is the one that
will be removed, line B stays), seed a sales-order mirror line + order inquiry row linked
to line A, then push the SAME order again carrying only line B. Today the sweep
(`DocumentIngestService._sync_lines`, `is_referenced` true because the link points at the
line) marks A `cancelled` in place and keeps every link, so each RED test fails on
"the link is still there", not on a fixture error.

Row states used (project_so.py): placed = fully covered by links, partly_linked, raised =
no link, actioned = a person's word, never overwritten by a link change.

Postgres only. Every test seeds its own chain (the `env` fixture builds a blank schema).
No real customer names anywhere in this file.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.audit import AuditLog
from app.models.order import SalesOrderLine
from app.models.procurement import PurchaseOrder
from app.models.product import Product
from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    ACK_AWAITING,
    ACK_CHANGED,
    INQUIRY_ACTIONED,
    INQUIRY_CANCELLED,
    INQUIRY_PARTLY_LINKED,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    IV_ORDER,
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryRow,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
)
from app.models.scm import OrderLinkClaim

from .test_ingest_documents import (
    INGEST_PO,
    INGEST_SO,
    _po_line,
    _po_record,
    _so_line,
    _so_record,
    env,  # noqa: F401 - pytest fixture, imported for reuse
)
from .test_oi_cancelled_line_used_confirm import (
    _inquiry,
    _line_chain,
    _mirror_for_ingest_line,
    _oi_row,
    _uid,
)
from .test_order_inquiry_handover_automation import (
    _captured_dispatches,
    _handover_calls,
    _register,
)
from .test_order_inquiry_kinds import _link

__all__ = ["env"]

QTY = 10


# --------------------------------------------------------------------------- helpers
class PoWorld:
    """A pushed two-line AutoCount PO: line A (to be removed) and line B (stays)."""

    def __init__(self, env, record, line_a, line_b):
        self.env = env
        self.record = record
        self.po_number = record["po_number"]
        self.payload_a = record["lines"][0]
        self.payload_b = record["lines"][1]
        header = env.header("purchase_orders", record["source_ref"])
        self.header_id = str(header["id"])
        by_ref = {l["source_ref"]: l for l in env.po_lines(self.header_id)}
        self.line_a = str(by_ref[self.payload_a["source_ref"]]["id"])
        self.line_b = str(by_ref[self.payload_b["source_ref"]]["id"])
        self.product_id = str(by_ref[self.payload_a["source_ref"]]["product_id"])
        self.product_code = env.db.execute(
            text("SELECT product_code FROM products WHERE id = :i"), {"i": self.product_id}
        ).scalar()


def _push_po(env, *, a_received=0, a_extra=None, header_extra=None) -> PoWorld:
    """Two lines of the SAME product, ordered QTY each. `a_received=QTY` is the 546 case:
    the removed line was fully received and so `closed` before AutoCount deleted it."""
    a = _po_line(env, qty_ordered=QTY, qty_received=a_received, **(a_extra or {}))
    b = _po_line(env, qty_ordered=QTY)
    record = _po_record(env, lines=[a, b], **(header_extra or {}))
    res = env.post(INGEST_PO, [record])
    assert res.status_code == 200, res.text
    assert res.json()["records"][0]["outcome"] == "created", res.text
    return PoWorld(env, record, a, b)


def _repush_without_a(env, w: PoWorld, **header_extra):
    """The removing push: the same PO, line A no longer carried."""
    record = dict(w.record, lines=[w.payload_b], **header_extra)
    res = env.post(INGEST_PO, [record])
    assert res.status_code == 200, res.text
    assert res.json()["records"][0]["outcome"] in ("updated", "unchanged"), res.text
    env.db.expire_all()
    return res


def _oi_row_on(
    env,
    w: PoWorld,
    *,
    row_qty=QTY,
    state=INQUIRY_PLACED,
    ack=ACK_ACKNOWLEDGED,
    links=((None, QTY),),
    inquiry_state=INQUIRY_ACTIONED,
    note="ZZT earlier note",
):
    """A sales-order mirror line + inquiry + ONE row, linked as `links` says
    ((po line id or None for line A, qty) pairs). Committed."""
    db = env.db
    product = db.get(__import__("app.models.product", fromlist=["Product"]).Product, w.product_id)
    _so, _core, pso, mirror = _line_chain(db, env.company_a, product, qty=str(row_qty))
    inquiry = _inquiry(db, env.company_a, pso.id)
    inquiry.state = inquiry_state
    row = _oi_row(
        db, env.company_a, inquiry.id, mirror.id, w.product_code, str(row_qty),
        delivery_date=date(2027, 1, 1), state=state, ack_state=ack,
    )
    row.note = note
    link_ids = []
    for line_id, qty in links:
        link = _link(
            db, env.company_a, row.id, str(qty),
            po_line_id=line_id or w.line_a, document=w.po_number,
        )
        link_ids.append(str(link.id))
    row.po_ref = w.po_number if links else None
    row.po_line_id = (links[0][0] or w.line_a) if links else None
    db.commit()
    return str(row.id), str(inquiry.id), link_ids


def _row_snapshot(env, row_id, inquiry_id=None) -> dict:
    env.db.expire_all()
    row = env.db.get(OrderInquiryRow, row_id)
    links = env.db.query(OrderInquiryLink).filter(OrderInquiryLink.row_id == row_id).all()
    snap = {
        "state": row.state,
        "ack_state": row.ack_state,
        "note": row.note,
        "changed_at": row.changed_at,
        "po_ref": row.po_ref,
        "po_line_id": str(row.po_line_id) if row.po_line_id else None,
        "link_lines": sorted(str(l.po_line_id) for l in links if l.po_line_id),
        "link_ids": {str(l.id) for l in links},
    }
    if inquiry_id:
        snap["inquiry_state"] = env.db.get(OrderInquiry, inquiry_id).state
    return snap


def _count_outbound(env) -> dict:
    return {
        "notifications": env.db.execute(text("SELECT count(*) FROM notifications")).scalar(),
        "email_outbox": env.db.execute(text("SELECT count(*) FROM email_outbox")).scalar(),
    }


class Quiet:
    """AC-RL-03: no notification, no email, no automation dispatch is queued."""

    def __init__(self, env, monkeypatch):
        _register(None)
        self.env = env
        self.calls = _captured_dispatches(monkeypatch)
        self.before = _count_outbound(env)

    def assert_nothing_queued(self):
        assert _count_outbound(self.env) == self.before
        oi_calls = [c for c in self.calls if str(c["trigger_type"]).startswith("order_inquiry")]
        assert oi_calls == [], oi_calls


def _po_line_row(env, line_id) -> dict:
    env.db.expire_all()
    return dict(
        env.db.execute(
            text("SELECT * FROM purchase_order_lines WHERE id = :i"), {"i": line_id}
        ).mappings().one()
    )


# ================================================================ AC-RL-01 / 02 / 03
def test_ac_rl_01_02_03_a_placed_row_with_one_link_goes_raised(env, monkeypatch):
    """The removed line carried the row's only link: link gone, row placed -> raised,
    inquiry header recomputed, ack_state / note / changed_at untouched, nothing queued."""
    w = _push_po(env)
    row_id, inquiry_id, _ = _oi_row_on(env, w)
    before = _row_snapshot(env, row_id, inquiry_id)
    assert before["state"] == INQUIRY_PLACED and before["inquiry_state"] == INQUIRY_ACTIONED
    quiet = Quiet(env, monkeypatch)

    _repush_without_a(env, w)

    after = _row_snapshot(env, row_id, inquiry_id)
    assert after["link_lines"] == [], after  # AC-RL-01
    assert after["state"] == INQUIRY_RAISED, after  # AC-RL-02
    assert after["inquiry_state"] == INQUIRY_RAISED, after  # AC-RL-02 header refreshed
    assert after["po_ref"] is None and after["po_line_id"] is None, after
    # AC-RL-03 + OI-AUTO-CONFIRM AC-AC-9: the release flags nothing (note / changed_at below),
    # but the row lost its only link, so the system takes it back to To order.
    assert before["ack_state"] == ACK_ACKNOWLEDGED
    assert after["ack_state"] == ACK_AWAITING
    assert after["note"] == before["note"] == "ZZT earlier note"  # AC-RL-03 no "Unlinked from"
    assert after["changed_at"] == before["changed_at"]
    quiet.assert_nothing_queued()  # AC-RL-03


def test_ac_rl_01_02_03_the_546_case_a_fully_received_removed_line_still_releases(
    env, monkeypatch
):
    """The behaviour-card case: the removed line was received in full (qty_received ==
    qty_ordered, `closed`) before AutoCount deleted it. Released all the same, and the
    line itself is written exactly as today (AC-RL-05)."""
    w = _push_po(env, a_received=QTY)
    assert _po_line_row(env, w.line_a)["line_status"] == "closed"
    row_id, inquiry_id, _ = _oi_row_on(env, w)
    quiet = Quiet(env, monkeypatch)

    _repush_without_a(env, w)

    after = _row_snapshot(env, row_id, inquiry_id)
    assert after["link_lines"] == [], after
    assert after["state"] == INQUIRY_RAISED, after
    assert after["ack_state"] == ACK_AWAITING  # AC-AC-9: no longer covered, nobody pressed
    assert after["note"] == "ZZT earlier note"
    quiet.assert_nothing_queued()
    line = _po_line_row(env, w.line_a)
    assert line["line_status"] == "cancelled"  # AC-RL-05, as today
    assert line["qty_ordered"] == Decimal(QTY)
    assert line["qty_received"] == Decimal(QTY)  # received qty untouched


def test_ac_rl_01_02_03_a_row_with_two_links_keeps_the_other_and_goes_partly_linked(
    env, monkeypatch
):
    """6 on the removed line A, 4 on the live line B: A's link goes, B's stays, the row
    reads partly linked (4 of 10) and its inquiry stays open."""
    w = _push_po(env)
    row_id, inquiry_id, link_ids = _oi_row_on(
        env, w, links=((w.line_a, 6), (w.line_b, 4))
    )
    quiet = Quiet(env, monkeypatch)

    _repush_without_a(env, w)

    after = _row_snapshot(env, row_id, inquiry_id)
    assert after["link_lines"] == [w.line_b], after  # only the removed line's link went
    assert after["link_ids"] == {link_ids[1]}, after
    assert after["state"] == INQUIRY_PARTLY_LINKED, after
    assert after["inquiry_state"] == INQUIRY_RAISED, after
    assert after["ack_state"] == ACK_AWAITING  # AC-AC-9: no longer covered, nobody pressed
    assert after["note"] == "ZZT earlier note"
    quiet.assert_nothing_queued()


def test_ac_rl_01_02_03_an_actioned_row_stays_actioned_and_loses_the_link(env, monkeypatch):
    """`actioned` is a person's word: the state is kept, the link still goes, and the row
    is NOT flagged to confirm."""
    w = _push_po(env)
    row_id, inquiry_id, _ = _oi_row_on(env, w, state=INQUIRY_ACTIONED)
    quiet = Quiet(env, monkeypatch)

    _repush_without_a(env, w)

    after = _row_snapshot(env, row_id, inquiry_id)
    assert after["link_lines"] == [], after
    assert after["state"] == INQUIRY_ACTIONED, after
    assert after["ack_state"] == ACK_ACKNOWLEDGED
    assert after["note"] == "ZZT earlier note"
    quiet.assert_nothing_queued()


def test_ac_rl_01_a_draft_link_on_an_unacknowledged_row_goes_too(env, monkeypatch):
    """Whatever the row state: a drafted link (row still awaiting purchasing) is released
    and the row stays awaiting."""
    w = _push_po(env)
    row_id, inquiry_id, _ = _oi_row_on(env, w, ack=ACK_AWAITING)
    quiet = Quiet(env, monkeypatch)

    _repush_without_a(env, w)

    after = _row_snapshot(env, row_id, inquiry_id)
    assert after["link_lines"] == [], after
    assert after["state"] == INQUIRY_RAISED, after
    assert after["ack_state"] == ACK_AWAITING, after
    assert after["note"] == "ZZT earlier note"
    quiet.assert_nothing_queued()


def test_ac_rl_01_every_row_linked_to_the_removed_line_is_released(env, monkeypatch):
    """Two different rows (two sales orders) on the same removed line: both released."""
    w = _push_po(env)
    row_1, inq_1, _ = _oi_row_on(env, w, links=((w.line_a, 6),), row_qty=6)
    row_2, inq_2, _ = _oi_row_on(env, w, links=((w.line_a, 4),), row_qty=4)

    _repush_without_a(env, w)

    assert _row_snapshot(env, row_1, inq_1)["link_lines"] == []
    assert _row_snapshot(env, row_2, inq_2)["link_lines"] == []
    assert _row_snapshot(env, row_1)["state"] == INQUIRY_RAISED
    assert _row_snapshot(env, row_2)["state"] == INQUIRY_RAISED


# ======================================================================== AC-RL-04
def test_ac_rl_04_open_claims_on_the_removed_line_are_deleted(env):
    """An open `scm.order_link_claim` on the removed line is DELETED (not stamped resolved:
    a resolved claim would read "matched to PO X"); a claim on the live line B stays open."""
    w = _push_po(env)
    _oi_row_on(env, w)
    claims = []
    for line_id in (w.line_a, w.line_b):
        claim = OrderLinkClaim(
            so_number=f"ZZT-SO-{uuid.uuid4().hex[:6]}",
            po_number=w.po_number,
            item_code=w.product_code,
            source="manual",
            po_line_id=line_id,
            company_id=env.company_a,
        )
        env.db.add(claim)
        env.db.flush()
        claims.append(str(claim.id))
    env.db.commit()

    _repush_without_a(env, w)

    def _count(claim_id, *, open_only=False):
        extra = " AND resolved_at IS NULL AND po_line_id IS NOT NULL" if open_only else ""
        return env.db.execute(
            text(f"SELECT count(*) FROM order_link_claim WHERE id = :i{extra}"),
            {"i": claim_id},
        ).scalar()

    assert _count(claims[0]) == 0, "the removed line's claim row must be gone"
    assert _count(claims[1], open_only=True) == 1, "the live line's claim must stay open"


# ======================================================================== AC-RL-05
def test_ac_rl_05_the_removed_line_is_written_exactly_as_today(env):
    """line_status cancelled; quantities, from_so_line_ref untouched; no new column."""
    w = _push_po(env, a_extra={"from_so_line_ref": "ZZT_DB:4001:777001"})
    _oi_row_on(env, w)
    before = _po_line_row(env, w.line_a)

    _repush_without_a(env, w)

    after = _po_line_row(env, w.line_a)
    assert after["line_status"] == "cancelled"
    for column in ("qty_ordered", "qty_received", "qty_cancelled", "from_so_line_ref",
                   "source_ref", "unit_cost", "cancelled_by_cancel_doc"):
        assert after[column] == before[column], column
    assert set(after) == set(before), "no new column on purchase_order_lines"


# ======================================================================== AC-RL-06
def test_ac_rl_06_po_detail_placed_reads_zero_after_the_push(env):
    """`_allocations_for` (the PO detail Placed panel) carries a block for line A before the
    push and none that places anything on it after."""
    from app.services.scm.purchase_order_service import PurchaseOrderService

    w = _push_po(env)
    _oi_row_on(env, w)

    def _placed_on_a():
        env.db.expire_all()
        po = env.db.get(PurchaseOrder, w.header_id)
        blocks = PurchaseOrderService(env.db)._allocations_for(po)
        return [b for b in blocks if b["line_id"] == w.line_a and (b["allocated"] or b["placements"])]

    assert _placed_on_a(), "fixture: the line carries a placement before the push"

    _repush_without_a(env, w)

    assert _placed_on_a() == []


# ================================================================== AC-RL-20, SO line
def _push_so(env, *, qty=QTY):
    """A two-line AutoCount SO: x (to be removed) and y (stays)."""
    x = _so_line(env, qty_ordered=qty)
    y = _so_line(env, product_ref=env.product2_ref, qty_ordered=qty)
    record = _so_record(env, lines=[x, y])
    res = env.post(INGEST_SO, [record])
    assert res.status_code == 200, res.text
    header = env.header("sales_orders", record["source_ref"])
    by_ref = {l["source_ref"]: l for l in env.so_lines(header["id"])}
    line_x = by_ref[x["source_ref"]]
    return record, header, line_x, y


def _so_mirror_row(env, header, line_x, *, state, ack=ACK_ACKNOWLEDGED, links=0, qty="10",
                   po_line_id=None, po_number=None, share=None):
    """One OI row on the removed SO line. `share` = the (mirror, inquiry_id) of an earlier
    call: a core order has exactly one project mirror, so further rows ride on it."""
    if share is None:
        mirror, row = _mirror_for_ingest_line(
            env, header["id"], line_x["id"], line_x["product_id"], qty=qty,
            row_state=state, row_ack=ack,
        )
    else:
        mirror, inquiry_id = share
        row = _oi_row(
            env.db, env.company_a, inquiry_id, mirror.id, "ZZT-CL-PUSH", qty,
            delivery_date=date(2027, 1, 1), state=state, ack_state=ack,
        )
    link_ids = []
    for _ in range(links):
        link = _link(
            env.db, env.company_a, row.id, "4", po_line_id=po_line_id, document=po_number
        )
        link_ids.append(str(link.id))
    if links:
        row.po_ref = po_number
        row.po_line_id = po_line_id
    env.db.commit()
    _so_mirror_row.last = (mirror, row.order_inquiry_id)
    return str(row.id), link_ids


def _remove_so_line_x(env, record, y):
    res = env.post(INGEST_SO, [dict(record, lines=[y])])
    assert res.status_code == 200, res.text
    env.db.expire_all()


def test_ac_rl_20_a_removed_so_line_retires_its_live_rows_like_transfer_to_cancel_so(
    env, monkeypatch
):
    """Live raised / partly linked / placed rows on the removed SO line: links back, row
    `cancelled`, OI_ROW_CANCELLED audit per row. The core line is `cancelled` but gets NO
    `cancelled_at` / `cancelled_by_id` (those mean the CS board)."""
    po = _push_po(env)
    record, header, line_x, y = _push_so(env)
    raised, _ = _so_mirror_row(env, header, line_x, state=INQUIRY_RAISED)
    shared = _so_mirror_row.last
    placed, placed_links = _so_mirror_row(
        env, header, line_x, state=INQUIRY_PLACED, links=1, qty="4",
        po_line_id=po.line_b, po_number=po.po_number, share=shared,
    )
    partly, partly_links = _so_mirror_row(
        env, header, line_x, state=INQUIRY_PARTLY_LINKED, links=1, qty="10",
        po_line_id=po.line_b, po_number=po.po_number, share=shared,
    )

    _remove_so_line_x(env, record, y)

    for row_id in (raised, placed, partly):
        snap = _row_snapshot(env, row_id)
        assert snap["state"] == INQUIRY_CANCELLED, (row_id, snap)
        assert snap["link_lines"] == [], (row_id, snap)
        audits = (
            env.db.query(AuditLog)
            .filter(AuditLog.entity_id == row_id, AuditLog.event == "OI_ROW_CANCELLED")
            .count()
        )
        assert audits == 1, (row_id, audits)
        note = snap["note"] or ""
        assert "Removed in AutoCount" in note, (row_id, note)
        assert "Transferred to Cancel SO" not in note, (row_id, note)
    core = env.db.execute(
        text("SELECT line_status, cancelled_at, cancelled_by_id FROM sales_order_lines WHERE id = :i"),
        {"i": str(line_x["id"])},
    ).mappings().one()
    assert core["line_status"] == "cancelled"
    assert core["cancelled_at"] is None and core["cancelled_by_id"] is None


def test_ac_rl_20_a_removed_so_line_hands_the_cancelled_rows_over_to_purchasing(
    env, monkeypatch
):
    """The same purchasing handover Transfer to Cancel SO produces: one
    `order_inquiry_handover` dispatch, every line a plain CANCEL."""
    po = _push_po(env)
    record, header, line_x, y = _push_so(env)
    _so_mirror_row(
        env, header, line_x, state=INQUIRY_PLACED, links=1, qty="4",
        po_line_id=po.line_b, po_number=po.po_number,
    )
    _register(None)
    calls = _captured_dispatches(monkeypatch)

    _remove_so_line_x(env, record, y)

    matches = _handover_calls(calls)
    assert len(matches) == 1, [c["trigger_type"] for c in calls]
    lines = matches[0]["context"]["handover"]["lines"]
    assert lines and all(line["remark"] == "CANCEL" for line in lines), lines


def test_ac_rl_20_an_actioned_row_on_a_removed_so_line_is_only_flagged(env):
    """Actioned rows are only flagged (`ack_state = changed`), as today; not cancelled."""
    record, header, line_x, y = _push_so(env)
    actioned, _ = _so_mirror_row(env, header, line_x, state=INQUIRY_ACTIONED)

    _remove_so_line_x(env, record, y)

    snap = _row_snapshot(env, actioned)
    assert snap["state"] == INQUIRY_ACTIONED, snap
    assert snap["ack_state"] == ACK_CHANGED, snap


# ============================================================== guards (AC-RL-30..34)
def test_ac_rl_30_guard_a_line_cancelled_by_a_cancel_doc_keeps_its_links(env):
    # guard: a Cancel PO document cancelled the whole line (`cancelled_by_cancel_doc`);
    # a later push that no longer carries it is not a removal.
    w = _push_po(env)
    env.db.execute(
        text(
            "UPDATE purchase_order_lines SET cancelled_by_cancel_doc = true, "
            "qty_cancelled = qty_ordered, line_status = 'cancelled' WHERE id = :i"
        ),
        {"i": w.line_a},
    )
    row_id, inquiry_id, link_ids = _oi_row_on(env, w)

    _repush_without_a(env, w)

    after = _row_snapshot(env, row_id, inquiry_id)
    assert after["link_ids"] == set(link_ids), after
    assert after["state"] == INQUIRY_PLACED, after


def test_ac_rl_30_guard_a_line_on_a_header_the_push_cancels_keeps_its_links(env):
    # guard: the push cancels the whole header; lines absent from it are not "removed".
    w = _push_po(env)
    row_id, inquiry_id, link_ids = _oi_row_on(env, w)

    _repush_without_a(env, w, status="cancelled")

    after = _row_snapshot(env, row_id, inquiry_id)
    assert after["link_ids"] == set(link_ids), after
    assert after["state"] == INQUIRY_PLACED, after


def test_ac_rl_30_guard_a_cs_board_cancelled_so_line_keeps_its_links_and_rows(env):
    # guard: SO-CANCEL-LINE: the CS board cancelled this line (`cancelled_at` set); the
    # AutoCount push dropping it later neither releases nor re-retires anything.
    po = _push_po(env)
    record, header, line_x, y = _push_so(env)
    placed, links = _so_mirror_row(
        env, header, line_x, state=INQUIRY_PLACED, links=1, qty="4",
        po_line_id=po.line_b, po_number=po.po_number,
    )
    env.db.execute(
        text(
            "UPDATE sales_order_lines SET line_status = 'cancelled', cancelled_at = now() "
            "WHERE id = :i"
        ),
        {"i": str(line_x["id"])},
    )
    env.db.commit()

    _remove_so_line_x(env, record, y)

    snap = _row_snapshot(env, placed)
    assert snap["link_ids"] == set(links), snap
    assert snap["state"] == INQUIRY_PLACED, snap


def test_ac_rl_32_guard_a_ref_less_line_swept_by_the_push_keeps_its_links(env):
    # guard: an xlsx-era line with no DtlKey is not an AutoCount line; the sweep may
    # cancel it in place but its links stay (Q4 a: out of scope).
    from app.models.procurement import PurchaseOrderLine

    w = _push_po(env)
    refless = PurchaseOrderLine(
        id=_uid(), company_id=env.company_a, purchase_order_id=w.header_id,
        product_id=w.product_id, qty_ordered=Decimal(QTY), line_status="open",
        source_ref=None, source_system=None,
    )
    env.db.add(refless)
    env.db.flush()
    env.db.commit()
    w.line_a = str(refless.id)  # the links go on the ref-less line
    row_id, inquiry_id, link_ids = _oi_row_on(env, w)

    _repush_without_a(env, w)  # carries only line B: the ref-less line is a pool leftover

    after = _row_snapshot(env, row_id, inquiry_id)
    assert after["link_ids"] == set(link_ids), after
    assert after["state"] == INQUIRY_PLACED, after


def test_ac_rl_32_guard_a_duplicate_ref_row_swept_by_the_push_keeps_its_links(env):
    # guard: a second row sharing a DtlKey another row already claims is swept as a
    # leftover; it is not "a line AutoCount removed" and keeps its links.
    from app.models.procurement import PurchaseOrderLine

    w = _push_po(env)
    dup = PurchaseOrderLine(
        id=_uid(), company_id=env.company_a, purchase_order_id=w.header_id,
        product_id=w.product_id, qty_ordered=Decimal(QTY), line_status="open",
        source_ref=w.payload_b["source_ref"], source_system="autocount",
    )
    env.db.add(dup)
    env.db.flush()
    env.db.commit()
    w.line_a = str(dup.id)
    row_id, inquiry_id, link_ids = _oi_row_on(env, w)

    _repush_without_a(env, w)

    after = _row_snapshot(env, row_id, inquiry_id)
    assert after["link_ids"] == set(link_ids), after


def test_ac_rl_33_guard_an_already_cancelled_line_absent_again_changes_nothing(env):
    # guard: release runs on the TRANSITION only. Push 2 removes A (whatever it does);
    # purchasing then re-links A by hand; push 3 (A still absent, already cancelled)
    # must leave that fresh link alone. Never a backlog sweep on a later push.
    w = _push_po(env)
    first_row, _, _ = _oi_row_on(env, w)
    _repush_without_a(env, w)
    # whatever push 2 did to the first link, start the second scenario from a clean line
    env.db.query(OrderInquiryLink).filter(OrderInquiryLink.po_line_id == w.line_a).delete()
    env.db.commit()
    assert _po_line_row(env, w.line_a)["line_status"] == "cancelled"
    row_id, inquiry_id, link_ids = _oi_row_on(env, w)  # a link re-added by hand afterwards

    _repush_without_a(env, w)

    after = _row_snapshot(env, row_id, inquiry_id)
    assert after["link_ids"] == set(link_ids), after
    assert after["state"] == INQUIRY_PLACED, after


@pytest.mark.parametrize("a_received", [0, QTY])
def test_ac_rl_34_guard_a_line_the_push_still_carries_keeps_its_links(env, a_received):
    # guard: matched by DtlKey => not removed, whatever its status (open or closed).
    w = _push_po(env, a_received=a_received)
    row_id, inquiry_id, link_ids = _oi_row_on(env, w)

    res = env.post(INGEST_PO, [w.record])  # both lines again
    assert res.status_code == 200, res.text
    env.db.expire_all()

    after = _row_snapshot(env, row_id, inquiry_id)
    assert after["link_ids"] == set(link_ids), after
    assert after["state"] == INQUIRY_PLACED, after


# ================================================================ AC-RL-07 zero-line push
def _assert_claim_open(env, claim_id):
    assert env.db.execute(
        text("SELECT count(*) FROM order_link_claim WHERE id = :i AND resolved_at IS NULL"),
        {"i": claim_id},
    ).scalar() == 1


def test_ac_rl_07_a_zero_line_po_push_releases_and_retires_nothing(env):
    w = _push_po(env)
    row_id, inquiry_id, link_ids = _oi_row_on(env, w)
    claim = OrderLinkClaim(
        so_number=f"ZZT-SO-{uuid.uuid4().hex[:6]}", po_number=w.po_number,
        item_code=w.product_code, source="manual", po_line_id=w.line_a,
        company_id=env.company_a,
    )
    env.db.add(claim)
    env.db.flush()
    env.db.commit()

    res = env.post(INGEST_PO, [dict(w.record, lines=[])])
    assert res.status_code == 200, res.text
    env.db.expire_all()

    after = _row_snapshot(env, row_id, inquiry_id)
    assert after["link_ids"] == set(link_ids), after
    assert after["state"] == INQUIRY_PLACED, after
    _assert_claim_open(env, str(claim.id))


def test_ac_rl_07_a_zero_line_so_push_retires_no_row(env):
    po = _push_po(env)
    record, header, line_x, y = _push_so(env)
    placed, links = _so_mirror_row(
        env, header, line_x, state=INQUIRY_PLACED, links=1, qty="4",
        po_line_id=po.line_b, po_number=po.po_number,
    )
    raised, _ = _so_mirror_row(
        env, header, line_x, state=INQUIRY_RAISED, share=_so_mirror_row.last
    )

    res = env.post(INGEST_SO, [dict(record, lines=[])])
    assert res.status_code == 200, res.text
    env.db.expire_all()

    snap = _row_snapshot(env, placed)
    assert snap["link_ids"] == set(links), snap
    assert snap["state"] == INQUIRY_PLACED, snap
    assert _row_snapshot(env, raised)["state"] == INQUIRY_RAISED


# ============================================== AC-RL-04 / 06: every claim, resolved too
def _claim_on(env, w, line_id, *, source, resolved):
    """A claim on `line_id` naming a REAL sales-order line with need left, so it reserves
    (a dedication in PO detail Placed) while it stands. `resolved` stamps `resolved_at`."""
    product = env.db.get(Product, w.product_id)
    so, core, _pso, _mirror = _line_chain(env.db, env.company_a, product, qty="10")
    claim = OrderLinkClaim(
        so_number=so.so_number, po_number=w.po_number, item_code=w.product_code,
        source=source, po_line_id=line_id, so_line_id=core.id,
        resolved_at=datetime(2026, 10, 1) if resolved else None,
        company_id=env.company_a,
    )
    env.db.add(claim)
    env.db.flush()
    env.db.commit()
    return str(claim.id)


def _claims_on_line(env, line_id) -> int:
    env.db.expire_all()
    return env.db.execute(
        text("SELECT count(*) FROM order_link_claim WHERE po_line_id = :i"), {"i": line_id}
    ).scalar()


def _placed_blocks(env, w, line_id):
    from app.services.scm.purchase_order_service import PurchaseOrderService

    env.db.expire_all()
    po = env.db.get(PurchaseOrder, w.header_id)
    return [
        b for b in PurchaseOrderService(env.db)._allocations_for(po)
        if b["line_id"] == line_id
        and (b["allocated"] or b["placements"] or b["dedicated_to"])
    ]


def test_ac_rl_04_06_a_resolved_and_an_open_claim_both_go_and_placed_reads_zero(env):
    w = _push_po(env)
    _oi_row_on(env, w)
    _claim_on(env, w, w.line_a, source="autocount", resolved=True)
    _claim_on(env, w, w.line_a, source="manual", resolved=False)
    live_b = _claim_on(env, w, w.line_b, source="autocount", resolved=True)
    assert _placed_blocks(env, w, w.line_a), "fixture: the line carries Placed before the push"

    _repush_without_a(env, w)

    assert _claims_on_line(env, w.line_a) == 0, "every claim on the removed line is deleted"
    assert _placed_blocks(env, w, w.line_a) == [], "PO detail Placed reads 0"
    assert _claims_on_line(env, w.line_b) == 1, "the live line's claim stays"


def test_ac_rl_04_06_a_claim_only_removed_line_loses_the_claim_and_placed_reads_zero(env):
    w = _push_po(env)  # no OI link at all on line A
    _claim_on(env, w, w.line_a, source="autocount", resolved=True)
    assert _placed_blocks(env, w, w.line_a), "fixture: the claim alone dedicates the line"

    _repush_without_a(env, w)

    assert _claims_on_line(env, w.line_a) == 0
    assert _placed_blocks(env, w, w.line_a) == []


def test_ac_rl_47_guard_a_claim_naming_a_removed_so_line_is_left_in_place(env):
    # guard: the live PO line's own book still names the SO line, so deleting the claim
    # would only be undone by the next PO push (owner Q3); the script reports it instead.
    po = _push_po(env)
    record, header, line_x, y = _push_so(env)
    so_number = header["so_number"]
    claim = OrderLinkClaim(
        so_number=so_number, po_number=po.po_number, item_code=po.product_code,
        source="autocount", po_line_id=po.line_b, so_line_id=str(line_x["id"]),
        resolved_at=datetime(2026, 10, 1), company_id=env.company_a,
    )
    env.db.add(claim)
    env.db.flush()
    env.db.commit()

    _remove_so_line_x(env, record, y)

    row = env.db.execute(
        text("SELECT so_line_id, po_line_id FROM order_link_claim WHERE id = :i"),
        {"i": str(claim.id)},
    ).mappings().first()
    assert row is not None, "the claim must stay"
    assert str(row["so_line_id"]) == str(line_x["id"]) and str(row["po_line_id"]) == po.line_b
