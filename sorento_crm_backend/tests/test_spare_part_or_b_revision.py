"""SPARE-PART-OR-B (slice 2 of #2381), red-first (Phase 2). R4: a revision on the same record.

Contract: documentation/plans/purchasing/spare-part-or-b-14nov-acceptance-criteria.md
U4.2 - U4.6 (backend half; U4.7 is the FE History icon). Postgres only (`blank_session`
via the shared world); every row seeded here.

NAMED CONTRACT CHOICES (the UAC leaves them open):

1. Columns: `OrderInquiry.revision_state` (null | draft | pending_approval | rejected) and
   `OrderInquiryRow.revised_qty` numeric(15,4), on the model and in the oi_no migration.
2. During a revision the qty change goes through the existing
   `spare_part_request_service.edit_line(db, inquiry, row_id, actor, qty=...)`, for the
   requester (revision draft / rejected) and the decider (revision pending_approval). It
   writes `revised_qty`, never `qty`. `unit_price=` and `update(...)` raise AppException 409.
3. `submit`, `reject`, `approve` are the existing service functions; they read
   `revision_state` to know a revision is open.
4. The handover email item is observed by wrapping
   `ProjectOrderInquiryService._record_handover` (the one writer of the
   `db.info[_HANDOVER_PENDING_KEY]` queue), so the assertion does not depend on when the
   after-commit drain runs. A restated row records `kind="settled"` with `was={"qty": ...}`.
5. U4.5 regression guard for the shared restate method: the existing
   `tests/test_oi_reconfirm_delta.py` (borrow holes: `test_a_changed_order_back_keeps_its_row_and_tells_old_to_new`,
   `test_two_holes_on_one_key_each_keep_their_own_row`,
   `test_a_date_move_restates_the_same_row_with_its_was_date`,
   `test_an_unchanged_hole_takes_the_new_wording_without_a_word_to_purchasing`) must stay
   green after `_restate_borrow_hole` calls the extracted method.
"""
from __future__ import annotations

import re
from decimal import Decimal

import pytest

from app.services.error_handler import AppException

from ._forms_chain_support import open_tracker, trackers
from ._spare_part_request_support import (  # noqa: F401  (fixtures)
    HEADERS,
    KIND,
    SPR,
    WORKLIST,
    approve,
    body,
    dec,
    raised,
    reload,
    row_for,
    rows_of,
    sent,
    staged,
    submitted,
    svc,
    two_staged,
    world,
)


@pytest.fixture
def handovers(monkeypatch):
    """Every handover email item queued: (row_id, kind, was)."""
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    calls: list = []
    real = ProjectOrderInquiryService._record_handover

    def spy(self, row, *, kind, was=None, **kw):
        calls.append((str(row.id), kind, dict(was) if was else None))
        return real(self, row, kind=kind, was=was, **kw)

    monkeypatch.setattr(ProjectOrderInquiryService, "_record_handover", spy)
    return calls


def _ack(w, inquiry, product):
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    row = row_for(w.db, inquiry, product)
    ProjectOrderInquiryService(w.db).acknowledge_rows([str(row.id)], actor_user_id=w.buyer)
    w.db.commit()
    return row_for(w.db, inquiry, product)


def _revise(w, inquiry):
    svc().revise(w.db, reload(w.db, inquiry), w.requester)
    w.db.commit()
    return reload(w.db, inquiry)


def _change(w, inquiry, product, qty, actor=None):
    row = row_for(w.db, inquiry, product)
    svc().edit_line(w.db, reload(w.db, inquiry), row.id, actor or w.requester, qty=qty)
    w.db.commit()
    return row_for(w.db, inquiry, product)


def _submit(w, inquiry):
    svc().submit(w.db, reload(w.db, inquiry), w.requester)
    w.db.commit()
    return reload(w.db, inquiry)


def _snap(row) -> dict:
    return {
        "state": row.state,
        "qty": dec(row.qty),
        "ack_state": row.ack_state,
        "acknowledged_by": row.acknowledged_by,
        "previous_qty": row.previous_qty,
    }


# =============================================================================
# U4.2 - Revise opens a revision on the same record
# =============================================================================


def test_U4_2_revise_opens_a_revision_and_leaves_the_approved_request_working(staged):
    w = staged
    inquiry = raised(w)
    before = {str(r.id): _snap(r) for r in rows_of(w.db, inquiry)}
    approved_at = inquiry.approved_at
    inquiry = _revise(w, inquiry)
    assert inquiry.revision_state == "draft"
    assert inquiry.state == "raised", "the header stays raised for purchasing"
    assert inquiry.approved_at == approved_at, "the approval stands"
    for row in rows_of(w.db, inquiry):
        assert dec(row.revised_qty) == dec(row.qty), "revised_qty starts at qty"
        assert _snap(row) == before[str(row.id)], "the row itself is untouched"
    assert not trackers(w.db, KIND, inquiry.id, open_only=True)


def test_U4_2_revise_is_allowed_after_purchasing_acknowledged_a_row(staged):
    w = staged
    inquiry = raised(w)
    acked = _ack(w, inquiry, w.product_a)
    assert acked.ack_state == "acknowledged", "precondition"
    inquiry = _revise(w, inquiry)
    assert inquiry.revision_state == "draft"
    still = row_for(w.db, inquiry, w.product_a)
    assert still.ack_state == "acknowledged", "purchasing's work is kept"
    assert still.acknowledged_by == acked.acknowledged_by


def test_U4_2_revise_writes_spr_revised(staged):
    from app.models.audit import AuditLog

    w = staged
    inquiry = _revise(w, raised(w))
    events = [
        a.event
        for a in w.db.query(AuditLog).filter(
            AuditLog.entity_type == "project_order_inquiries",
            AuditLog.entity_id == str(inquiry.id),
        )
    ]
    assert "SPR_REVISED" in events


def test_U4_2_only_the_requester_revises(staged):
    w = staged
    inquiry = raised(w)
    with pytest.raises(AppException) as excinfo:
        svc().revise(w.db, inquiry, w.outsider)
    assert excinfo.value.status_code == 403


def test_U4_2_a_second_revise_while_one_is_open_is_409(staged):
    w = staged
    inquiry = _revise(w, raised(w))
    with pytest.raises(AppException) as excinfo:
        svc().revise(w.db, reload(w.db, inquiry), w.requester)
    assert excinfo.value.status_code == 409
    w.db.rollback()


def test_U4_2_revise_of_a_pending_request_is_409(staged):
    w = staged
    inquiry = submitted(w)
    with pytest.raises(AppException) as excinfo:
        svc().revise(w.db, inquiry, w.requester)
    assert excinfo.value.status_code == 409
    w.db.rollback()


# =============================================================================
# U4.3 - only qty changes during a revision
# =============================================================================


def test_U4_3_the_requester_changes_revised_qty_not_qty(staged):
    w = staged
    inquiry = _revise(w, raised(w))
    row = _change(w, inquiry, w.product_a, "12")
    assert dec(row.revised_qty) == Decimal("12")
    assert dec(row.qty) == Decimal("10"), "the approved qty stands until approval"


def test_U4_3_zero_is_allowed(staged):
    w = staged
    inquiry = _revise(w, raised(w))
    row = _change(w, inquiry, w.product_b, "0")
    assert dec(row.revised_qty) == Decimal("0")


def test_U4_3_a_decider_changes_revised_qty_while_the_revision_is_pending(staged):
    w = staged
    inquiry = _revise(w, raised(w))
    _change(w, inquiry, w.product_a, "12")
    inquiry = _submit(w, inquiry)
    row = _change(w, inquiry, w.product_a, "11", actor=w.stage1.tier1)
    assert dec(row.revised_qty) == Decimal("11")
    assert dec(row.qty) == Decimal("10")


def test_U4_3_a_unit_price_change_during_a_revision_is_409(staged):
    w = staged
    inquiry = _revise(w, raised(w))
    row = row_for(w.db, inquiry, w.product_a)
    with pytest.raises(AppException) as excinfo:
        svc().edit_line(w.db, reload(w.db, inquiry), row.id, w.requester, unit_price="30")
    assert excinfo.value.status_code == 409
    w.db.rollback()


def test_U4_3_the_edit_form_during_a_revision_saves_the_revision_only(staged):
    """SPARE-PART-OR-B C (C4.1, lead sign-off 14 Nov): Revise opens the same edit form; its
    save writes the revision fields only, the header and the approved values stand."""
    w = staged
    inquiry = _revise(w, raised(w))
    row_a = row_for(w.db, inquiry, w.product_a)
    lines = []
    for row in rows_of(w.db, inquiry):
        lines.append(
            {
                "id": str(row.id), "product_id": str(row.product_id),
                "stock_location": row.stock_location,
                "qty": "12" if row.id == row_a.id else str(row.qty),
                "unit_price": str(row.unit_price),
            }
        )
    svc().update(w.db, reload(w.db, inquiry), body(w, reason="Another reason", lines=lines), w.requester)
    w.db.commit()
    inquiry = reload(w.db, inquiry)
    assert inquiry.reason == "Spare parts for the service van", "the header is not revised"
    row = row_for(w.db, inquiry, w.product_a)
    assert dec(row.qty) == Decimal("10"), "qty stands until the re-approval"
    assert dec(row.revised_qty) == Decimal("12")


def test_U4_3_each_change_is_audited_old_to_new(staged):
    from app.models.audit import AuditLog

    w = staged
    inquiry = _revise(w, raised(w))
    row = _change(w, inquiry, w.product_a, "12")
    changes = [
        a
        for a in w.db.query(AuditLog).filter(
            AuditLog.entity_type == "project_order_inquiries",
            AuditLog.entity_id == str(inquiry.id),
            AuditLog.event == "SPR_LINE_CHANGED",
        )
        if (a.new_values or {}).get("row_id") == str(row.id)
    ]
    assert changes, "SPR_LINE_CHANGED written"
    last = changes[-1]
    assert dec(last.old_values["qty"]) == Decimal("10")
    assert dec(last.new_values["qty"]) == Decimal("12")


# =============================================================================
# U4.4 - submit, reject, non-final approve
# =============================================================================


def test_U4_4_submitting_an_unchanged_revision_is_422_nothing_changed(staged):
    w = staged
    inquiry = _revise(w, raised(w))
    with pytest.raises(AppException) as excinfo:
        svc().submit(w.db, reload(w.db, inquiry), w.requester)
    assert excinfo.value.status_code == 422
    assert re.search(r"nothing changed", excinfo.value.message, re.I), excinfo.value.message
    w.db.rollback()


def test_U4_4_submit_puts_the_revision_to_approval(staged):
    w = staged
    inquiry = _revise(w, raised(w))
    _change(w, inquiry, w.product_a, "12")
    inquiry = _submit(w, inquiry)
    assert inquiry.revision_state == "pending_approval"
    assert inquiry.state == "raised", "the header stays raised"
    assert inquiry.submitted_at is not None
    tracker = open_tracker(w.db, KIND, inquiry.id)
    assert tracker.team_set_code == w.stage1.team_set, "the same Form SLA submit"


def test_U4_4_reject_sends_the_revision_back(staged):
    w = staged
    inquiry = _revise(w, raised(w))
    _change(w, inquiry, w.product_a, "12")
    inquiry = _submit(w, inquiry)
    svc().reject(w.db, inquiry, w.stage1.tier1, "Keep the ten")
    w.db.commit()
    inquiry = reload(w.db, inquiry)
    assert inquiry.revision_state == "rejected"
    assert inquiry.reject_reason == "Keep the ten"
    assert inquiry.state == "raised"
    row = _change(w, inquiry, w.product_a, "11")
    assert dec(row.revised_qty) == Decimal("11"), "the requester amends a rejected revision"


def test_U4_4_a_non_final_approval_of_a_revision_moves_to_the_next_level(two_staged):
    w = two_staged
    inquiry = approve(w, approve(w, submitted(w), w.stage1.tier1), w.stage2.tier1)
    assert inquiry.state == "raised", "precondition"
    inquiry = _revise(w, inquiry)
    _change(w, inquiry, w.product_a, "12")
    inquiry = approve(w, _submit(w, inquiry), w.stage1.tier1)
    assert inquiry.revision_state == "pending_approval"
    assert dec(row_for(w.db, inquiry, w.product_a).qty) == Decimal("10"), "nothing restated yet"
    tracker = open_tracker(w.db, KIND, inquiry.id)
    assert tracker.team_set_code == w.stage2.team_set


# =============================================================================
# U4.5 - final approval restates moved rows through the SO-change path
# =============================================================================


def _approved_revision(w, *, ack=True, b_qty=None):
    inquiry = raised(w)
    if ack:
        _ack(w, inquiry, w.product_a)
    inquiry = _revise(w, inquiry)
    _change(w, inquiry, w.product_a, "12")
    if b_qty is not None:
        _change(w, inquiry, w.product_b, b_qty)
    inquiry = _submit(w, inquiry)
    return inquiry


def test_U4_5_a_moved_row_is_restated_with_previous_qty_and_a_was_note(staged, handovers):
    w = staged
    inquiry = _approved_revision(w)
    inquiry = approve(w, inquiry, w.stage1.tier1)
    row = row_for(w.db, inquiry, w.product_a)
    assert dec(row.qty) == Decimal("12")
    assert dec(row.previous_qty) == Decimal("10")
    assert re.search(r"\bWas 10\b", row.note or ""), row.note


def test_U4_5_an_acknowledged_moved_row_goes_back_to_purchasing_as_changed(staged, handovers):
    w = staged
    inquiry = approve(w, _approved_revision(w), w.stage1.tier1)
    assert row_for(w.db, inquiry, w.product_a).ack_state == "changed"


def test_U4_5_one_handover_item_for_the_moved_row_only(staged, handovers):
    w = staged
    inquiry = _approved_revision(w)
    row_a = row_for(w.db, inquiry, w.product_a)
    row_b = row_for(w.db, inquiry, w.product_b)
    handovers.clear()
    approve(w, inquiry, w.stage1.tier1)
    told = [h for h in handovers if h[0] in (str(row_a.id), str(row_b.id))]
    assert len(told) == 1, told
    row_id, kind, was = told[0]
    assert row_id == str(row_a.id)
    assert kind == "settled"
    assert was and dec(was.get("qty")) == Decimal("10")


def test_U4_5_an_unchanged_row_is_untouched(staged, handovers):
    w = staged
    inquiry = _approved_revision(w)
    before = _snap(row_for(w.db, inquiry, w.product_b))
    inquiry = approve(w, inquiry, w.stage1.tier1)
    after = row_for(w.db, inquiry, w.product_b)
    assert _snap(after) == before
    assert after.previous_qty is None


def test_U4_5_a_row_revised_to_zero_is_cancelled(staged, handovers):
    w = staged
    inquiry = _approved_revision(w, b_qty="0")
    inquiry = approve(w, inquiry, w.stage1.tier1)
    assert row_for(w.db, inquiry, w.product_b).state == "cancelled"


def test_U4_5_the_revision_closes_and_the_number_stays(staged, handovers):
    w = staged
    inquiry = _approved_revision(w)
    number = reload(w.db, inquiry).oi_no
    inquiry = approve(w, inquiry, w.stage1.tier1)
    assert inquiry.revision_state is None
    assert all(r.revised_qty is None for r in rows_of(w.db, inquiry))
    assert inquiry.state in ("raised", "actioned")
    assert str(inquiry.approved_by) == str(w.stage1.tier1)
    assert inquiry.oi_no == number and number


def test_U4_5_the_restate_method_is_shared_with_the_borrow_hole_path():
    """ONE method extracted from `_restate_borrow_hole`, which now calls it (behaviour of the
    borrow-hole path itself: tests/test_oi_reconfirm_delta.py)."""
    import inspect

    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    hole = inspect.getsource(ProjectOrderInquiryService._restate_borrow_hole)
    assert "handover_moves(" not in hole and "_record_handover(" not in hole, (
        "the borrow-hole path delegates the restate to the shared method"
    )


# =============================================================================
# U4.6 - reads
# =============================================================================


def test_U4_6_the_or_detail_shows_revised_qty_and_revision_state(staged):
    w = staged
    inquiry = _revise(w, raised(w))
    row = _change(w, inquiry, w.product_a, "12")
    res = w.as_user(w.requester).get(f"{SPR}/{inquiry.id}")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data.get("revision_state") == "draft"
    line_a = next(l for l in data["lines"] if l["id"] == str(row.id))
    assert dec(line_a["qty"]) == Decimal("12")


def test_U4_6_the_or_list_rows_carry_revision_state(staged):
    w = staged
    inquiry = _revise(w, raised(w))
    other = raised(w)
    res = w.as_user(w.requester).get(SPR, params={"limit": 50})
    assert res.status_code == 200, res.text
    rows = {r["id"]: r for r in res.json()["data"]}
    assert rows[str(inquiry.id)].get("revision_state") == "draft"
    assert "revision_state" in rows[str(other.id)] and rows[str(other.id)]["revision_state"] is None


def test_U4_6_the_oi_worklist_and_header_list_read_the_approved_qty(staged):
    w = staged
    inquiry = _revise(w, raised(w))
    row = _change(w, inquiry, w.product_a, "12")
    assert dec(row.revised_qty) == Decimal("12"), "precondition: a revision is open"
    res = w.as_user(w.buyer).get(WORKLIST, params={"inquiry_id": str(inquiry.id), "limit": 100})
    assert res.status_code == 200, res.text
    line_a = next(r for r in res.json()["data"] if r["id"] == str(row.id))
    assert dec(line_a["qty"]) == Decimal("10")
    res = w.as_user(w.buyer).get(HEADERS, params={"state": "all", "limit": 100})
    assert res.status_code == 200, res.text
    header = next(r for r in res.json()["data"] if r["id"] == str(inquiry.id))
    assert dec(header["qty_total"]) == Decimal("14"), "10 + 4, never the revised 12"
