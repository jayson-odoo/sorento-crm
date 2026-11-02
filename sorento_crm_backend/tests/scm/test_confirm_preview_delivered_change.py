"""CONFIRM-PREVIEW-STALE (owner, 2 Nov 2026): popup = email = Excel for a line delivered in
full that a PENDING AutoCount change names.

Shape of the owner's order: every line delivered in full; AutoCount moves one line's date
28/09 -> 02/11. The purchasing email takes Was -> Now off the change row (28/09 -> 02/11), so
the Review split (the line-split read) must print the same: DELIVERY DATE 28/09, NEW DATE
02/11 and the change word, never a blank NEW DATE.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.scm.outstanding_diff import DATE_MOVED
from tests.scm.test_line_splits_api import _get, _line, _mirror
from tests.test_planning_change_apply_on_board import _build, _change, _confirm, api, world  # noqa: F401
from tests.test_planning_changes import _core_so, _line_payload, _project_so

WAS = date(2026, 9, 28)
NOW = date(2026, 11, 2)


class _S:
    pass


def _seed(api, *, pending: bool):
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    s = _S()
    s.client, s.world, s.db, s.core_so, s.order = client, world, db, core_so, order
    # Line 10: 3 ordered on 28/09, confirmed as Buy 3, then delivered in full.
    s.c10, s.l10 = _mirror(db, order, core_so, world.product, world.own_wh,
                           line_no=10, qty=3, when=WAS)
    # Line 20: delivered in full, nothing pending.
    s.c20, s.l20 = _mirror(db, order, core_so, world.product, world.own_wh,
                           line_no=20, qty=5, when=WAS)
    s.c20.qty_delivered = Decimal("5")
    db.commit()
    resp = _confirm(client, order.id, [_line_payload(s.l10.id, buy_qty="3")])
    assert resp.status_code == 200, resp.text
    s.c10.qty_delivered = Decimal("3")
    db.commit()
    if pending:
        # AutoCount moves line 10 to 02/11 (the book re-upload already wrote the new date).
        s.c10.required_date = NOW
        s.l10.delivery_date = NOW
        db.commit()
        s.batch = _build(world, [
            _change(DATE_MOVED, s.c10, so_number=core_so.so_number,
                    old_date=WAS, new_date=NOW, old_qty="3", new_qty="3"),
        ], core_so, [str(s.c10.id)])
        assert s.batch is not None, "premise: the pending change row exists"
    return s


def test_a_delivered_line_named_by_a_pending_date_change_shows_the_email_was_now(api):
    s = _seed(api, pending=True)
    l10 = _line(_get(s), s.l10.id)
    assert l10["pending_change"] is True
    assert l10["base_date"] == "2026-09-28", "DELIVERY DATE is the date before the change"
    assert l10["new_date"] == "2026-11-02", "NEW DATE is the change's Now, as the email prints"
    assert l10["new_qty"] is None, "the qty did not move"
    assert "DELAY" in (l10["remark_generated"] or ""), l10["remark_generated"]


def test_a_delivered_line_with_no_pending_change_still_has_no_new_cells(api):
    s = _seed(api, pending=True)
    l20 = _line(_get(s), s.l20.id)
    assert l20["delivered_in_full"] is True
    assert l20["pending_change"] is False
    assert (l20["new_qty"], l20["new_date"]) == (None, None)


def test_a_delivered_line_named_by_a_pending_change_is_still_listed_read_only(api):
    """No split on a delivered line: the read still marks it delivered in full (the sheet's
    lock), it only stops hiding the change."""
    s = _seed(api, pending=True)
    l10 = _line(_get(s), s.l10.id)
    assert l10["delivered_in_full"] is True
    assert l10["splits"] == []


def test_a_delivered_line_autocount_closed_reads_its_change_word_not_cancel_all(api):
    """Crew browser pass (2 Nov): on the copy every delivered-in-full line's AutoCount line is
    CLOSED (closed by the delivery, not cancelled). Its words are the change's (DELAY), never
    the cancelled-line words CANCEL ALL."""
    s = _seed(api, pending=True)
    s.c10.line_status = "closed"
    s.db.commit()
    l10 = _line(_get(s), s.l10.id)
    assert l10["new_date"] == "2026-11-02"
    assert "CANCEL" not in (l10["remark_generated"] or ""), l10["remark_generated"]
    assert "DELAY" in (l10["remark_generated"] or ""), l10["remark_generated"]
