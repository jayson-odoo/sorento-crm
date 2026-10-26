"""AC-REMOVED-LINES, red tests: an SPO line AutoCount drops releases its links.

UAC: documentation/plans/scm/ac-removed-lines-26oct-acceptance-criteria.md
     AC-RL-10 (SPO line removed, `retired_at` newly set) and AC-RL-31 (a whole-document
     cancelled push keeps its links; `force_closed`, no `retired_at`).

Driven through the real shipping-order ingest route (the `env` fixture of
tests/test_ingest_documents.py), so the release may live in the service or a route hook.
Today the leftover sweep (`ShippingOrderIngestService`, `retired_refs`) closes the row and
stamps `retired_at` but keeps every link, so the RED tests fail on "the link is still there".

Postgres only; every test seeds its own chain; no real names.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import text

from app.models.project_so import (
    ACK_ACKNOWLEDGED,
    INQUIRY_ACTIONED,
    INQUIRY_PARTLY_LINKED,
    INQUIRY_PLACED,
    INQUIRY_RAISED,
    IV_ORDER_BACK,
    OrderInquiry,
    OrderInquiryLink,
    OrderInquiryRow,
)
from app.models.product import Product
from app.models.scm import OrderLinkClaim

from .test_ac_removed_lines_ingest import Quiet
from .test_ingest_documents import (
    MARKER,
    _ref,
    env,  # noqa: F401 - pytest fixture, imported for reuse
)
from .test_ingest_documents_v2_links import INGEST_SPO, _product_code
from .test_oi_cancelled_line_used_confirm import _inquiry, _line_chain, _oi_row
from .test_order_inquiry_kinds import _link

__all__ = ["env"]

QTY = 10


class SpoWorld:
    def __init__(self, env, record):
        self.env = env
        self.record = record
        self.spo_number = record["spo_number"]
        self.payload_a, self.payload_b = record["lines"]
        rows = env.db.execute(
            text("SELECT id, source_ref, product_id FROM spo_allocations WHERE spo_number = :n"),
            {"n": self.spo_number},
        ).mappings().all()
        by_ref = {r["source_ref"]: r for r in rows}
        self.alloc_a = str(by_ref[self.payload_a["source_ref"]]["id"])
        self.alloc_b = str(by_ref[self.payload_b["source_ref"]]["id"])
        self.product_id = str(by_ref[self.payload_a["source_ref"]]["product_id"])
        self.product_code = _product_code(env, env.product_ref)


def _push_spo(env, *, status="open") -> SpoWorld:
    spo_number = f"SPO-{uuid.uuid4().hex[:4]}/01-{uuid.uuid4().hex[:4]}"
    lines = [
        {
            "source_ref": _ref("SPOL"),
            "product_ref": env.product_ref,
            "product_code": _product_code(env, env.product_ref),
            "qty_ordered": QTY,
        }
        for _ in range(2)
    ]
    record = {
        "source_ref": _ref("SPO"),
        "spo_number": spo_number,
        "supplier_ref": env.supplier_ref,
        "status": status,
        "lines": lines,
    }
    res = env.post(INGEST_SPO, [record])
    assert res.status_code == 200, res.text
    assert res.json()["records"][0]["outcome"] == "created", res.text
    return SpoWorld(env, record)


def _repush(env, w: SpoWorld, *, lines, **extra):
    res = env.post(INGEST_SPO, [dict(w.record, lines=lines, **extra)])
    assert res.status_code == 200, res.text
    assert res.json()["records"][0]["outcome"] in ("updated", "unchanged"), res.text
    env.db.expire_all()


def _row_on_spo(env, w: SpoWorld, *, links, row_qty=QTY, state=INQUIRY_PLACED,
                inquiry_state=INQUIRY_ACTIONED, note="ZZT earlier note"):
    """An ORDER_BACK row (the only verb that may name an SPO) with `links` = [(alloc, qty)]."""
    db = env.db
    product = db.get(Product, w.product_id)
    _so, _core, pso, mirror = _line_chain(db, env.company_a, product, qty=str(row_qty))
    inquiry = _inquiry(db, env.company_a, pso.id)
    inquiry.state = inquiry_state
    row = _oi_row(
        db, env.company_a, inquiry.id, mirror.id, w.product_code, str(row_qty),
        delivery_date=date(2027, 1, 1), state=state, ack_state=ACK_ACKNOWLEDGED,
    )
    row.verb = IV_ORDER_BACK
    row.note = note
    link_ids = []
    for alloc, qty in links:
        link = _link(db, env.company_a, row.id, str(qty), spo_allocation_id=alloc,
                     document=w.spo_number)
        link_ids.append(str(link.id))
    row.po_ref = w.spo_number
    row.spo_ref = w.spo_number
    db.commit()
    return str(row.id), str(inquiry.id), link_ids


def _snapshot(env, row_id, inquiry_id):
    env.db.expire_all()
    row = env.db.get(OrderInquiryRow, row_id)
    links = env.db.query(OrderInquiryLink).filter(OrderInquiryLink.row_id == row_id).all()
    return {
        "state": row.state,
        "ack_state": row.ack_state,
        "note": row.note,
        "changed_at": row.changed_at,
        "link_allocs": sorted(str(l.spo_allocation_id) for l in links),
        "link_ids": {str(l.id) for l in links},
        "inquiry_state": env.db.get(OrderInquiry, inquiry_id).state,
    }


def _retired_at(env, alloc_id):
    return env.db.execute(
        text("SELECT retired_at FROM spo_allocations WHERE id = :i"), {"i": alloc_id}
    ).scalar()


# ============================================================ AC-RL-10 (with 02 / 03)
def test_ac_rl_10_a_retired_spo_line_releases_its_only_link(env, monkeypatch):
    w = _push_spo(env)
    row_id, inquiry_id, _ = _row_on_spo(env, w, links=[(w.alloc_a, QTY)])
    quiet = Quiet(env, monkeypatch)

    _repush(env, w, lines=[w.payload_b])

    assert _retired_at(env, w.alloc_a) is not None, "fixture: the sweep retired the line"
    after = _snapshot(env, row_id, inquiry_id)
    assert after["link_allocs"] == [], after  # AC-RL-10
    assert after["state"] == INQUIRY_RAISED, after  # AC-RL-02
    assert after["inquiry_state"] == INQUIRY_RAISED, after
    assert after["ack_state"] == ACK_ACKNOWLEDGED, after  # AC-RL-03
    assert after["note"] == "ZZT earlier note", after
    assert after["changed_at"] is None
    quiet.assert_nothing_queued()


def test_ac_rl_10_a_row_with_a_second_link_on_a_live_spo_line_goes_partly_linked(
    env, monkeypatch
):
    w = _push_spo(env)
    row_id, inquiry_id, link_ids = _row_on_spo(
        env, w, links=[(w.alloc_a, 6), (w.alloc_b, 4)]
    )
    quiet = Quiet(env, monkeypatch)

    _repush(env, w, lines=[w.payload_b])

    after = _snapshot(env, row_id, inquiry_id)
    assert after["link_ids"] == {link_ids[1]}, after
    assert after["state"] == INQUIRY_PARTLY_LINKED, after
    assert after["note"] == "ZZT earlier note"
    quiet.assert_nothing_queued()


def test_ac_rl_10_an_actioned_row_stays_actioned_and_loses_the_link(env, monkeypatch):
    w = _push_spo(env)
    row_id, inquiry_id, _ = _row_on_spo(
        env, w, links=[(w.alloc_a, QTY)], state=INQUIRY_ACTIONED
    )
    quiet = Quiet(env, monkeypatch)

    _repush(env, w, lines=[w.payload_b])

    after = _snapshot(env, row_id, inquiry_id)
    assert after["link_allocs"] == [], after
    assert after["state"] == INQUIRY_ACTIONED, after
    assert after["ack_state"] == ACK_ACKNOWLEDGED
    quiet.assert_nothing_queued()


def test_ac_rl_10_open_claims_on_the_retired_spo_line_are_deleted(env):
    w = _push_spo(env)
    _row_on_spo(env, w, links=[(w.alloc_a, QTY)])
    claims = []
    for alloc in (w.alloc_a, w.alloc_b):
        claim = OrderLinkClaim(
            so_number=f"ZZT-SO-{uuid.uuid4().hex[:6]}", po_number=w.spo_number,
            item_code=w.product_code, source="manual", spo_allocation_id=alloc,
            company_id=env.company_a,
        )
        env.db.add(claim)
        env.db.flush()
        claims.append(str(claim.id))
    env.db.commit()

    _repush(env, w, lines=[w.payload_b])

    def _count(claim_id, *, open_only=False):
        extra = " AND resolved_at IS NULL AND spo_allocation_id IS NOT NULL" if open_only else ""
        return env.db.execute(
            text(f"SELECT count(*) FROM order_link_claim WHERE id = :i{extra}"),
            {"i": claim_id},
        ).scalar()

    assert _count(claims[0]) == 0, "the retired line's claim row must be gone"
    assert _count(claims[1], open_only=True) == 1, "the live line's claim must stay open"


# ================================================================ AC-RL-31 (guard)
def test_ac_rl_31_guard_a_cancelled_spo_document_keeps_its_links(env):
    # guard: a whole-document cancelled push closes every line (`force_closed`) with no
    # `retired_at`; AutoCount cancelled it, it did not remove lines.
    w = _push_spo(env)
    row_id, inquiry_id, link_ids = _row_on_spo(env, w, links=[(w.alloc_a, QTY)])

    _repush(env, w, lines=w.record["lines"], status="cancelled")

    assert _retired_at(env, w.alloc_a) is None
    after = _snapshot(env, row_id, inquiry_id)
    assert after["link_ids"] == set(link_ids), after
    assert after["state"] == INQUIRY_PLACED, after


def test_ac_rl_33_guard_a_line_retired_earlier_and_absent_again_changes_nothing(env):
    # guard: release runs only when this push NEWLY sets `retired_at`. Retire A with no
    # links on it, hand-link it afterwards, push again without A: the link stays.
    w = _push_spo(env)
    _repush(env, w, lines=[w.payload_b])
    assert _retired_at(env, w.alloc_a) is not None
    row_id, inquiry_id, link_ids = _row_on_spo(env, w, links=[(w.alloc_a, QTY)])

    _repush(env, w, lines=[w.payload_b])

    after = _snapshot(env, row_id, inquiry_id)
    assert after["link_ids"] == set(link_ids), after
    assert after["state"] == INQUIRY_PLACED, after


def test_ac_rl_31_guard_a_cancelled_push_that_also_drops_a_line_keeps_that_lines_links(env):
    # guard: cancelled document AND a line it no longer carries: cancel, not removal.
    w = _push_spo(env)
    row_id, inquiry_id, link_ids = _row_on_spo(env, w, links=[(w.alloc_a, QTY)])

    _repush(env, w, lines=[w.payload_b], status="cancelled")

    after = _snapshot(env, row_id, inquiry_id)
    assert after["link_ids"] == set(link_ids), after
    assert after["state"] == INQUIRY_PLACED, after


def test_ac_rl_07_a_zero_line_spo_push_releases_nothing(env):
    w = _push_spo(env)
    row_id, inquiry_id, link_ids = _row_on_spo(env, w, links=[(w.alloc_a, QTY)])
    claim = OrderLinkClaim(
        so_number=f"ZZT-SO-{uuid.uuid4().hex[:6]}", po_number=w.spo_number,
        item_code=w.product_code, source="manual", spo_allocation_id=w.alloc_a,
        company_id=env.company_a,
    )
    env.db.add(claim)
    env.db.flush()
    env.db.commit()

    res = env.post(INGEST_SPO, [dict(w.record, lines=[])])
    assert res.status_code == 200, res.text
    env.db.expire_all()

    after = _snapshot(env, row_id, inquiry_id)
    assert after["link_ids"] == set(link_ids), after
    assert after["state"] == INQUIRY_PLACED, after
    assert env.db.execute(
        text("SELECT count(*) FROM order_link_claim WHERE id = :i AND resolved_at IS NULL"),
        {"i": str(claim.id)},
    ).scalar() == 1
