"""SPARE-PART-OR-B (slice 2 of #2381): a revision's final approval emails purchasing.

Owner, 14 Nov ~15:54: "follow the OI route to also send order inquiry email of same format to
purchasing, when quantity changes after purchasing seen it" (UAC U4.5). The approval is the
third press `mark_purchasing_email_trigger` names (`tests/test_lessons_learnt_regressions.py`
allowlist), so the handover queued for a restated row is DISPATCHED at the commit, not only
queued; a revision whose approval moved nothing marks nothing and sends nothing.

Observed through the shared purchasing-email harness (`tests/_purchasing_email_tripwire.py`):
its dispatch spy records what the post-commit drain actually fires. Postgres only, every row
seeded here.
"""
from __future__ import annotations

from ._purchasing_email_tripwire import Tripwire
from ._spare_part_request_support import (  # noqa: F401  (fixtures)
    approve,
    raised,
    reload,
    row_for,
    sent,
    staged,
    svc,
    world,
)

HANDOVER = "order_inquiry_handover"


def _revision_pending(w, qty):
    inquiry = raised(w)
    svc().revise(w.db, reload(w.db, inquiry), w.requester)
    w.db.commit()
    row = row_for(w.db, inquiry, w.product_a)
    svc().edit_line(w.db, reload(w.db, inquiry), row.id, w.requester, qty=qty)
    w.db.commit()
    svc().submit(w.db, reload(w.db, inquiry), w.requester)
    w.db.commit()
    return reload(w.db, inquiry)


def test_a_restated_row_sends_the_order_inquiry_email_at_commit(staged, monkeypatch):
    w = staged
    inquiry = _revision_pending(w, "12")
    wire = Tripwire.arm(w.db, monkeypatch)
    before = wire.dispatches.count(HANDOVER)

    approve(w, inquiry, w.stage1.tier1)

    assert wire.dispatches.count(HANDOVER) == before + 1, wire.dispatches
    trigger, context, _kind, _source = next(p for p in wire.pending if p[0] == HANDOVER)
    assert trigger == HANDOVER
    lines = (context.get("handover") or {}).get("lines") or []
    codes = [line.get("item_code") for line in lines]
    assert w.product_a.product_code in codes, context


def test_a_revision_approval_that_moved_nothing_sends_nothing(staged, monkeypatch):
    """The decider puts the requester's 12 back to the approved 10 before approving."""
    w = staged
    inquiry = _revision_pending(w, "12")
    row = row_for(w.db, inquiry, w.product_a)
    svc().edit_line(w.db, reload(w.db, inquiry), row.id, w.stage1.tier1, qty="10")
    w.db.commit()
    wire = Tripwire.arm(w.db, monkeypatch)
    before = wire.snapshot()

    inquiry = approve(w, reload(w.db, inquiry), w.stage1.tier1)

    assert inquiry.revision_state is None, "precondition: the revision closed"
    wire.assert_silent_since(before, "a revision approval with nothing moved")
