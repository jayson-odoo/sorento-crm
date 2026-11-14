"""SPARE-PART-OR-B C, red-first (Phase 2). C4: Revise mirrors an SO change.

Contract: documentation/plans/purchasing/spare-part-or-c-14nov-acceptance-criteria.md C4.1-C4.5.
The Waiting for CS assertions mirror tests/test_oi_waiting_for_cs.py (worklist
`waiting_for_cs`, the header's `lines_to_confirm`, purchasing's acknowledge refused 409
`order_inquiry_waiting_for_cs`). Postgres only; every row seeded here.

NAMED CONTRACT CHOICES (the UAC leaves them open):
1. Revision-mode save = `spare_part_request_service.update(...)` while a revision is open
   (support module, choice 3). Columns: `OrderInquiryRow.revised_qty` (exists),
   `revised_product_id`, `revised_delivery_date` (new, C4.1 / Migration).
2. The settle is observed by wrapping `ProjectOrderInquiryService._settle_row_in_place`,
   `restate_row` and `cancel_row_told` on the class; the handover queue by wrapping
   `_record_handover` (the one writer of the pending email queue).
3. An added line is a row on the same inquiry in state `draft` until the re-approval; the
   worklist (purchasing's read) never lists it.
4. The SO-side acknowledge refusal is the HTTP route `POST /order-inquiries/acknowledge`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from ._spare_part_or_c_support import (  # noqa: F401  (fixtures)
    approve_as,
    change_qty,
    create_as,
    dated_line,
    form_lines,
    handovers,
    header_row,
    make_product,
    plain,
    reload,
    revise_as,
    row_for,
    rows_of,
    save_form,
    sent,
    submit_as,
    svc,
    worklist_rows,
    world,
)
from ._spare_part_request_support import WORKLIST


@pytest.fixture
def calls(monkeypatch):
    """Which shared OI writers ran, by name: (name, row_id)."""
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService as OI

    seen: list = []
    for name in ("_settle_row_in_place", "restate_row", "cancel_row_told"):
        real = getattr(OI, name)

        def spy(self, *args, __real=real, __name=name, **kw):
            row_id = None
            for value in list(args) + list(kw.values()):
                if hasattr(value, "ack_state") and hasattr(value, "order_inquiry_id"):
                    row_id = str(value.id)
                    break
                if isinstance(value, (list, tuple)) and value and hasattr(value[0], "ack_state"):
                    row_id = str(value[0].id)
                    break
            seen.append((__name, row_id))
            return __real(self, *args, **kw)

        monkeypatch.setattr(OI, name, spy)
    return seen


def _raised(w):
    return approve_as(w, submit_as(w, create_as(w, w.requester), w.requester), w.stage1.tier1)


def _ack(w, inquiry, product):
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    row = row_for(w.db, inquiry, product)
    ProjectOrderInquiryService(w.db).acknowledge_rows([str(row.id)], actor_user_id=w.buyer)
    w.db.commit()
    return row_for(w.db, inquiry, product)


def _edit(lines, row, **values):
    for entry in lines:
        if entry["id"] == str(row.id):
            entry.update(values)
    return lines


# =============================================================================
# C4.1 - Revise opens the same edit form; values go to the revision fields
# =============================================================================


def test_C4_1_the_edit_form_saves_a_revision_into_the_revision_fields(plain):
    w = plain
    product_c = make_product(w.db, "bearing kit")
    w.db.commit()
    inquiry = revise_as(w, _raised(w), w.requester)
    row_a = row_for(w.db, inquiry, w.product_a)
    before = (row_a.qty, row_a.item_code, str(row_a.product_id), row_a.delivery_date)
    lines = _edit(
        form_lines(w, inquiry), row_a,
        product_id=str(product_c.id), qty="12", delivery_date="2027-01-20",
    )
    save_form(w, inquiry, w.requester, lines)
    w.db.expire_all()
    row = next(r for r in rows_of(w.db, inquiry) if str(r.id) == str(row_a.id))
    assert Decimal(str(row.revised_qty)) == Decimal("12")
    assert str(row.revised_product_id) == str(product_c.id)
    assert row.revised_delivery_date == date(2027, 1, 20)
    assert (row.qty, row.item_code, str(row.product_id), row.delivery_date) == before, (
        "the approved values stand until the re-approval"
    )


def test_C4_1_a_removed_line_stays_live_until_the_re_approval(plain):
    w = plain
    inquiry = revise_as(w, _raised(w), w.requester)
    row_b = row_for(w.db, inquiry, w.product_b)
    lines = [l for l in form_lines(w, inquiry) if l["id"] != str(row_b.id)]
    save_form(w, inquiry, w.requester, lines)
    row = row_for(w.db, inquiry, w.product_b)
    assert row.state == "raised", "purchasing still sees it until the re-approval"
    assert str(row.id) in worklist_rows(w, inquiry)


def test_C4_1_an_added_line_is_a_draft_row_purchasing_never_sees(plain):
    w = plain
    product_c = make_product(w.db, "bearing kit")
    w.db.commit()
    inquiry = revise_as(w, _raised(w), w.requester)
    lines = form_lines(w, inquiry) + [dated_line(product_c, w.loc_a, qty="3")]
    save_form(w, inquiry, w.requester, lines)
    added = row_for(w.db, inquiry, product_c)
    assert added.state == "draft"
    assert str(added.id) not in worklist_rows(w, inquiry)


# =============================================================================
# C4.2 / C4.3 - Waiting for CS while a revision with a moved row is open
# =============================================================================


def test_C4_2_a_moved_row_waits_for_cs_and_an_unmoved_row_does_not(plain):
    w = plain
    inquiry = revise_as(w, _raised(w), w.requester)
    row_a = change_qty(w, inquiry, w.product_a, "12", w.requester)
    row_b = row_for(w.db, inquiry, w.product_b)
    rows = worklist_rows(w, inquiry)
    assert rows[str(row_a.id)].get("waiting_for_cs") is True
    assert rows[str(row_b.id)].get("waiting_for_cs") is False


def test_C4_2_a_product_or_date_change_also_waits(plain):
    w = plain
    product_c = make_product(w.db, "bearing kit")
    w.db.commit()
    inquiry = revise_as(w, _raised(w), w.requester)
    row_a = row_for(w.db, inquiry, w.product_a)
    row_b = row_for(w.db, inquiry, w.product_b)
    lines = _edit(form_lines(w, inquiry), row_a, product_id=str(product_c.id))
    lines = _edit(lines, row_b, delivery_date="2027-02-01")
    save_form(w, inquiry, w.requester, lines)
    rows = worklist_rows(w, inquiry)
    assert rows[str(row_a.id)].get("waiting_for_cs") is True, "product moved"
    assert rows[str(row_b.id)].get("waiting_for_cs") is True, "date moved"


def test_C4_2_a_row_to_be_removed_waits(plain):
    w = plain
    inquiry = revise_as(w, _raised(w), w.requester)
    row_b = row_for(w.db, inquiry, w.product_b)
    save_form(
        w, inquiry, w.requester, [l for l in form_lines(w, inquiry) if l["id"] != str(row_b.id)]
    )
    assert worklist_rows(w, inquiry)[str(row_b.id)].get("waiting_for_cs") is True


def test_C4_2_a_revision_with_nothing_moved_waits_on_nothing(plain):
    w = plain
    inquiry = revise_as(w, _raised(w), w.requester)
    assert all(r.get("waiting_for_cs") is False for r in worklist_rows(w, inquiry).values())


def test_C4_2_the_header_leaves_the_waiting_row_out_of_lines_to_confirm(plain):
    w = plain
    inquiry = _raised(w)
    assert header_row(w, inquiry)["lines_to_confirm"] == 2, "precondition"
    inquiry = revise_as(w, inquiry, w.requester)
    change_qty(w, inquiry, w.product_a, "12", w.requester)
    header = header_row(w, inquiry)
    assert header["lines_to_confirm"] == 1, header
    assert header["status"] == "outstanding", header


def test_C4_2_purchasing_cannot_confirm_a_waiting_row(plain):
    w = plain
    inquiry = revise_as(w, _raised(w), w.requester)
    row_a = change_qty(w, inquiry, w.product_a, "12", w.requester)
    res = w.as_user(w.buyer).post(f"{WORKLIST}/acknowledge", json={"row_ids": [str(row_a.id)]})
    assert res.status_code == 409, res.text
    assert "order_inquiry_waiting_for_cs" in res.text or "Waiting for CS" in res.text, res.text
    assert row_for(w.db, inquiry, w.product_a).ack_state == "awaiting"


def test_C4_2_purchasing_can_still_confirm_an_unmoved_row(plain):
    w = plain
    inquiry = revise_as(w, _raised(w), w.requester)
    change_qty(w, inquiry, w.product_a, "12", w.requester)
    row_b = row_for(w.db, inquiry, w.product_b)
    res = w.as_user(w.buyer).post(f"{WORKLIST}/acknowledge", json={"row_ids": [str(row_b.id)]})
    assert res.status_code == 200, res.text


def test_C4_3_a_rejected_revision_keeps_waiting(plain):
    w = plain
    inquiry = revise_as(w, _raised(w), w.requester)
    row_a = change_qty(w, inquiry, w.product_a, "12", w.requester)
    inquiry = submit_as(w, inquiry, w.requester)
    svc().reject(w.db, reload(w.db, inquiry), w.stage1.tier1, "Keep ten")
    w.db.commit()
    assert reload(w.db, inquiry).revision_state == "rejected", "precondition"
    assert worklist_rows(w, inquiry)[str(row_a.id)].get("waiting_for_cs") is True


# =============================================================================
# C4.4 - the re-approval settles through the SO path
# =============================================================================


def _approved_revision(w, *, ack=False, edit=None):
    inquiry = _raised(w)
    if ack:
        _ack(w, inquiry, w.product_a)
    inquiry = revise_as(w, inquiry, w.requester)
    if edit is None:
        change_qty(w, inquiry, w.product_a, "12", w.requester)
    else:
        edit(inquiry)
    return submit_as(w, inquiry, w.requester)


def test_C4_4_a_moved_row_settles_through_settle_row_in_place_not_restate_row(plain, calls):
    w = plain
    inquiry = _approved_revision(w)
    row_a = row_for(w.db, inquiry, w.product_a)
    calls.clear()
    approve_as(w, inquiry, w.stage1.tier1)
    names = [c[0] for c in calls]
    assert "_settle_row_in_place" in names, calls
    assert ("_settle_row_in_place", str(row_a.id)) in calls, calls
    assert "restate_row" not in names, f"no second path for ORs: {calls}"


def test_C4_4_a_qty_settle_writes_previous_qty_and_a_was_note(plain, handovers):
    w = plain
    inquiry = approve_as(w, _approved_revision(w), w.stage1.tier1)
    row = row_for(w.db, inquiry, w.product_a)
    assert Decimal(str(row.qty)) == Decimal("12")
    assert Decimal(str(row.previous_qty)) == Decimal("10")
    assert "Was 10" in (row.note or ""), row.note


def test_C4_4_a_date_settle_moves_the_row_date_with_previous_date(plain, handovers):
    w = plain

    def edit(inquiry):
        row_b = row_for(w.db, inquiry, w.product_b)
        save_form(
            w, inquiry, w.requester,
            _edit(form_lines(w, inquiry), row_b, delivery_date="2027-02-01"),
        )

    inquiry = _approved_revision(w, edit=edit)
    old = row_for(w.db, inquiry, w.product_b).delivery_date
    inquiry = approve_as(w, inquiry, w.stage1.tier1)
    row = row_for(w.db, inquiry, w.product_b)
    assert row.delivery_date == date(2027, 2, 1)
    assert row.previous_delivery_date == old


def test_C4_4_a_product_settle_restates_item_code_and_product(plain, handovers):
    w = plain
    product_c = make_product(w.db, "bearing kit")
    w.db.commit()
    ids = {}

    def edit(inquiry):
        row_a = row_for(w.db, inquiry, w.product_a)
        ids["a"] = str(row_a.id)
        save_form(
            w, inquiry, w.requester,
            _edit(form_lines(w, inquiry), row_a, product_id=str(product_c.id)),
        )

    inquiry = approve_as(w, _approved_revision(w, edit=edit), w.stage1.tier1)
    row = next(r for r in rows_of(w.db, inquiry) if str(r.id) == ids["a"])
    assert str(row.product_id) == str(product_c.id)
    assert row.item_code == product_c.product_code


def test_C4_4_an_acknowledged_moved_row_goes_back_as_changed(plain, handovers):
    w = plain
    inquiry = approve_as(w, _approved_revision(w, ack=True), w.stage1.tier1)
    assert row_for(w.db, inquiry, w.product_a).ack_state == "changed"


def test_C4_4_a_settled_row_records_one_settled_handover_line(plain, handovers):
    w = plain
    inquiry = _approved_revision(w)
    row_a = row_for(w.db, inquiry, w.product_a)
    row_b = row_for(w.db, inquiry, w.product_b)
    handovers.clear()
    approve_as(w, inquiry, w.stage1.tier1)
    told = [h for h in handovers if h[0] in (str(row_a.id), str(row_b.id))]
    assert told and all(h[0] == str(row_a.id) for h in told), told
    assert told[0][1] == "settled", told


def test_C4_4_a_removed_line_is_cancelled_through_cancel_row_told(plain, calls, handovers):
    w = plain
    ids = {}

    def edit(inquiry):
        row_b = row_for(w.db, inquiry, w.product_b)
        ids["b"] = str(row_b.id)
        save_form(
            w, inquiry, w.requester,
            [l for l in form_lines(w, inquiry) if l["id"] != str(row_b.id)],
        )

    inquiry = _approved_revision(w, edit=edit)
    calls.clear()
    inquiry = approve_as(w, inquiry, w.stage1.tier1)
    assert ("cancel_row_told", ids["b"]) in calls, calls
    assert row_for(w.db, inquiry, w.product_b).state == "cancelled"


def test_C4_4_an_added_line_is_raised_with_its_own_raised_handover_line(plain, handovers):
    w = plain
    product_c = make_product(w.db, "bearing kit")
    w.db.commit()

    def edit(inquiry):
        save_form(
            w, inquiry, w.requester,
            form_lines(w, inquiry) + [dated_line(product_c, w.loc_a, qty="3")],
        )

    inquiry = _approved_revision(w, edit=edit)
    handovers.clear()
    inquiry = approve_as(w, inquiry, w.stage1.tier1)
    added = row_for(w.db, inquiry, product_c)
    assert added.state == "raised"
    assert (str(added.id), "raised", None) in handovers, handovers
    assert str(added.id) in worklist_rows(w, inquiry)


# =============================================================================
# C4.5 - after the settle
# =============================================================================


def test_C4_5_the_revision_fields_clear_and_nothing_waits(plain, handovers):
    w = plain
    product_c = make_product(w.db, "bearing kit")
    w.db.commit()

    def edit(inquiry):
        row_a = row_for(w.db, inquiry, w.product_a)
        save_form(
            w, inquiry, w.requester,
            _edit(
                form_lines(w, inquiry), row_a,
                product_id=str(product_c.id), qty="12", delivery_date="2027-01-20",
            ),
        )

    inquiry = _approved_revision(w, edit=edit)
    number = inquiry.oi_no
    inquiry = approve_as(w, inquiry, w.stage1.tier1)
    assert inquiry.revision_state is None
    assert inquiry.oi_no == number and number
    for row in rows_of(w.db, inquiry):
        assert row.revised_qty is None
        assert row.revised_product_id is None
        assert row.revised_delivery_date is None
    assert all(r.get("waiting_for_cs") is False for r in worklist_rows(w, inquiry).values())
