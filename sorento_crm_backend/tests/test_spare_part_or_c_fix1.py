"""SPARE-PART-OR-B C fix round 1, red-first. Security S1-S3 and review R1, R2, R4-R8.

Contract: documentation/plans/purchasing/spare-part-or-c-14nov-acceptance-criteria.md plus the
lead's fix-round rulings (relayed 14 Nov). Postgres only; every row seeded here.

NAMED CONTRACT CHOICES (the rulings leave them open):
1. S1: "approver" needs exactly ONE terminal active level reachable from the start level
   (the active level whose start_event names `submitted`, followed by `next_config_id`), and
   the user an ACTIVE member: user status ACTIVE and the level's AccessAgent active. Admin
   stays an approver.
2. S2 / S3 / R4: the revision-mode save (`update` while a revision is open) raises
   AppException at SAVE: 409 naming the line's item code for a product change on a row with
   a document link, or whose current item code is not a catalogue product, or for any edit to
   a row the settle will not take (here: a `redirected_to_pool` row); 422 for a blank qty on
   an existing line.
3. R1: the worklist route takes `view=request` (the OR page's fetch). Without it (the OI
   page, purchasing) a `draft` row of an APPROVED request is never returned, also with
   `include_history=true`; with it, the requester / approver read the revision's added draft
   row.
4. R2: a revision product swap with no description sent takes the new product's name on
   settle (Create's G1); a description the requester typed is kept.
5. R6: `mark_purchasing_email_trigger.__doc__` names every caller in the allowlist of
   `tests/test_lessons_learnt_regressions.py` (`_raise_to_purchasing` included).
6. R7: no test needs the header-revision EXISTS in `oi_waiting_for_cs.revision_moved_clause`:
   every path that closes a revision clears the revised fields (`_clear_revision`), so a
   moved row with no open revision cannot exist. None is written; the coder may drop it.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.services.error_handler import AppException

from ._forms_chain_support import SORENTO, sla_chain
from ._spare_part_or_c_support import (  # noqa: F401  (fixtures)
    KIND,
    ONE_STAGE,
    approve_as,
    change_qty,
    create_as,
    dated_line,
    form_lines,
    make_product,
    plain,
    plain_two,
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
from ._spare_part_request_support import HEADERS, WORKLIST


def _raised(w):
    return approve_as(w, submit_as(w, create_as(w, w.requester), w.requester), w.stage1.tier1)


def _edit(lines, row, **values):
    for entry in lines:
        if entry["id"] == str(row.id):
            entry.update(values)
    return lines


# =============================================================================
# S1 - who is an approver
# =============================================================================


def test_S1_a_member_of_one_of_two_parallel_terminal_levels_is_not_an_approver(world):
    w = world
    a = sla_chain(w.db, KIND, [dict(ONE_STAGE[0])])
    b = sla_chain(w.db, KIND, [dict(ONE_STAGE[0])])
    assert svc().is_final_approver(w.db, a.stages[0].tier1, SORENTO) is False
    assert svc().is_final_approver(w.db, b.stages[0].tier1, SORENTO) is False


def test_S1_a_member_of_a_stray_unreachable_level_is_not_an_approver(plain):
    w = plain
    stray = sla_chain(
        w.db, KIND, [{"start_event": "spare_part_never_emitted", "resolve_event": "approved,rejected"}]
    )
    assert svc().is_final_approver(w.db, stray.stages[0].tier1, SORENTO) is False
    assert svc().is_final_approver(w.db, w.stage1.tier1, SORENTO) is True, (
        "the reachable terminal level still counts"
    )


def test_S1_an_inactive_user_on_the_final_level_is_not_an_approver(plain):
    from app.models.user import User

    w = plain
    w.db.query(User).filter(User.id == w.stage1.tier1).update({"status": "INACTIVE"})
    w.db.commit()
    assert svc().is_final_approver(w.db, w.stage1.tier1, SORENTO) is False


def test_S1_an_inactive_agent_of_the_final_level_makes_no_approver(plain):
    from app.models.access import AccessAgent

    w = plain
    w.db.query(AccessAgent).filter(AccessAgent.code == w.stage1.config.agent_code).update(
        {"is_active": False}
    )
    w.db.commit()
    assert svc().is_final_approver(w.db, w.stage1.tier1, SORENTO) is False


def test_S1_the_single_terminal_level_of_a_linear_chain_is_the_approver(plain_two):
    w = plain_two
    assert svc().is_final_approver(w.db, w.stage2.tier1, SORENTO) is True
    assert svc().is_final_approver(w.db, w.stage1.tier1, SORENTO) is False


def test_S1_a_parallel_level_member_submit_goes_to_approval(world):
    w = world
    a = sla_chain(w.db, KIND, [dict(ONE_STAGE[0])])
    sla_chain(w.db, KIND, [dict(ONE_STAGE[0])])
    from ._spare_part_request_support import CREATE, role_grant

    member = a.stages[0].tier1
    role_grant(w.db, member, CREATE)
    w.db.commit()
    inquiry = submit_as(w, create_as(w, member), member)
    assert inquiry.state == "pending_approval", inquiry.state


# =============================================================================
# S2 - a product change is refused on a linked or non-catalogue row
# =============================================================================


def _link(w, row):
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine
    from app.models.project_so import OrderInquiryLink

    from ._pg_fixture import unique_code

    po = PurchaseOrder(
        company_id=w.company_id, po_number=unique_code("ZZT-PO")[:30],
        issue_date=date.today(), status="active",
    )
    w.db.add(po)
    w.db.flush()
    po_line = PurchaseOrderLine(
        company_id=w.company_id, purchase_order_id=po.id, product_id=row.product_id,
        warehouse_id=w.loc_a.id, qty_ordered=Decimal("10"), qty_received=Decimal("0"),
        expected_date=date.today(), line_status="open",
    )
    w.db.add(po_line)
    w.db.flush()
    w.db.add(
        OrderInquiryLink(
            company_id=w.company_id, row_id=row.id, po_line_id=po_line.id,
            document=po.po_number, qty=Decimal("10"), linked_by=w.buyer, auto=False,
        )
    )
    row.state = "placed"
    w.db.commit()


def test_S2_a_product_change_on_a_linked_row_is_refused_at_save(plain):
    w = plain
    product_c = make_product(w.db, "bearing kit")
    w.db.commit()
    inquiry = _raised(w)
    _link(w, row_for(w.db, inquiry, w.product_a))
    inquiry = revise_as(w, inquiry, w.requester)
    row_a = row_for(w.db, inquiry, w.product_a)
    lines = _edit(form_lines(w, inquiry), row_a, product_id=str(product_c.id))
    with pytest.raises(AppException) as excinfo:
        save_form(w, inquiry, w.requester, lines)
    assert excinfo.value.status_code == 409
    assert row_a.item_code in excinfo.value.message, excinfo.value.message
    w.db.rollback()


def test_S2_a_qty_and_date_change_on_a_linked_row_is_still_allowed(plain):
    w = plain
    inquiry = _raised(w)
    _link(w, row_for(w.db, inquiry, w.product_a))
    inquiry = revise_as(w, inquiry, w.requester)
    row_a = row_for(w.db, inquiry, w.product_a)
    save_form(
        w, inquiry, w.requester,
        _edit(form_lines(w, inquiry), row_a, qty="12", delivery_date="2027-01-20"),
    )
    row = row_for(w.db, inquiry, w.product_a)
    assert Decimal(str(row.revised_qty)) == Decimal("12")


def test_S2_a_product_change_on_a_non_catalogue_code_row_is_refused_at_save(plain):
    w = plain
    product_c = make_product(w.db, "bearing kit")
    w.db.commit()
    inquiry = _raised(w)
    row_a = row_for(w.db, inquiry, w.product_a)
    row_a.item_code = "ZZT-NOT-IN-CATALOGUE"
    w.db.commit()
    inquiry = revise_as(w, inquiry, w.requester)
    lines = _edit(form_lines(w, inquiry), row_a, product_id=str(product_c.id))
    with pytest.raises(AppException) as excinfo:
        save_form(w, inquiry, w.requester, lines)
    assert excinfo.value.status_code == 409
    assert "ZZT-NOT-IN-CATALOGUE" in excinfo.value.message, excinfo.value.message
    w.db.rollback()


# =============================================================================
# S3 - a row the settle will not take is refused at save
# =============================================================================


def test_S3_an_edit_to_a_row_the_settle_will_not_take_is_refused_at_save(plain):
    w = plain
    inquiry = _raised(w)
    row_a = row_for(w.db, inquiry, w.product_a)
    row_a.redirected_to_pool = True
    w.db.commit()
    inquiry = revise_as(w, inquiry, w.requester)
    lines = _edit(form_lines(w, inquiry), row_a, qty="12")
    with pytest.raises(AppException) as excinfo:
        save_form(w, inquiry, w.requester, lines)
    assert excinfo.value.status_code == 409
    assert row_a.item_code in excinfo.value.message, excinfo.value.message
    w.db.rollback()


# =============================================================================
# R1 - the OI page / purchasing never read a revision's added draft row
# =============================================================================


def _with_added_line(w):
    product_c = make_product(w.db, "bearing kit")
    w.db.commit()
    inquiry = revise_as(w, _raised(w), w.requester)
    save_form(
        w, inquiry, w.requester, form_lines(w, inquiry) + [dated_line(product_c, w.loc_a, qty="3")]
    )
    return inquiry, row_for(w.db, inquiry, product_c)


def _ids(w, user, inquiry, **params):
    res = w.as_user(user).get(
        WORKLIST, params={"inquiry_id": str(inquiry.id), "limit": 100, **params}
    )
    assert res.status_code == 200, res.text
    return {r["id"] for r in res.json()["data"]}


def test_R1_the_oi_page_history_fetch_never_returns_the_added_draft_row(plain):
    w = plain
    inquiry, added = _with_added_line(w)
    assert added.state == "draft", "precondition"
    assert str(added.id) not in _ids(w, w.buyer, inquiry, include_history="true")
    assert str(added.id) not in _ids(w, w.requester, inquiry, include_history="true"), (
        "the OI page reads purchasing's view, whoever opens it"
    )


def test_R1_the_or_page_fetch_returns_the_added_draft_row(plain):
    w = plain
    inquiry, added = _with_added_line(w)
    assert str(added.id) in _ids(w, w.requester, inquiry, include_history="true", view="request")


# =============================================================================
# R2 - a product swap takes the new product's name
# =============================================================================


def _swap(w, **extra):
    product_c = make_product(w.db, "bearing kit")
    w.db.commit()
    inquiry = revise_as(w, _raised(w), w.requester)
    row_a = row_for(w.db, inquiry, w.product_a)
    save_form(
        w, inquiry, w.requester,
        _edit(form_lines(w, inquiry), row_a, product_id=str(product_c.id), **extra),
    )
    inquiry = approve_as(w, submit_as(w, inquiry, w.requester), w.stage1.tier1)
    return next(r for r in rows_of(w.db, inquiry) if str(r.id) == str(row_a.id)), product_c


def test_R2_a_product_swap_moves_the_description_to_the_new_name(plain):
    row, product_c = _swap(plain)
    assert str(row.product_id) == str(product_c.id), "precondition: settled"
    assert row.description == product_c.product_name, row.description


def test_R2_a_typed_description_is_kept_on_a_product_swap(plain):
    row, _product_c = _swap(plain, description="Seal for the rear pump")
    assert row.description == "Seal for the rear pump", row.description


# =============================================================================
# R4 - a cancelled row stays cancelled; a blank qty is a 422
# =============================================================================


def test_R4_a_line_purchasing_cancelled_while_the_form_was_open_is_not_brought_back(plain):
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    w = plain
    inquiry = revise_as(w, _raised(w), w.requester)
    lines = form_lines(w, inquiry)  # the form, opened while row B was live
    row_b = row_for(w.db, inquiry, w.product_b)
    ProjectOrderInquiryService(w.db).cancel_row_told(
        row_b, cause="zzt_purchasing_cancel", stamp="Cancelled", actor_user_id=w.buyer
    )
    w.db.commit()
    row_a = row_for(w.db, inquiry, w.product_a)
    save_form(w, inquiry, w.requester, _edit(lines, row_a, qty="12"))
    b_rows = [r for r in rows_of(w.db, inquiry) if str(r.product_id) == str(w.product_b.id)]
    assert [(str(r.id), r.state) for r in b_rows] == [(str(row_b.id), "cancelled")], b_rows
    inquiry = approve_as(w, submit_as(w, inquiry, w.requester), w.stage1.tier1)
    b_rows = [r for r in rows_of(w.db, inquiry) if str(r.product_id) == str(w.product_b.id)]
    assert all(r.state == "cancelled" for r in b_rows), [(r.id, r.state) for r in b_rows]


def test_R4_a_blank_qty_on_an_existing_line_is_a_422_not_zero(plain):
    w = plain
    inquiry = revise_as(w, _raised(w), w.requester)
    row_a = row_for(w.db, inquiry, w.product_a)
    lines = _edit(form_lines(w, inquiry), row_a, qty=None)
    with pytest.raises(AppException) as excinfo:
        save_form(w, inquiry, w.requester, lines)
    assert excinfo.value.status_code == 422
    w.db.rollback()
    assert dec_or_none(row_for(w.db, reload(w.db, inquiry), w.product_a).revised_qty) != Decimal("0")


def dec_or_none(value):
    return None if value is None else Decimal(str(value))


# =============================================================================
# R5 - the request-only branches of `_settle_row_in_place` (guards)
# =============================================================================


@pytest.mark.parametrize("state", ["actioned", "placed"])
def test_R5_an_unlinked_actioned_or_placed_row_settles_cleanly(plain, state):
    w = plain
    inquiry = _raised(w)
    row_a = row_for(w.db, inquiry, w.product_a)
    row_a.state = state
    w.db.commit()
    inquiry = revise_as(w, inquiry, w.requester)
    change_qty(w, inquiry, w.product_a, "12", w.requester)
    inquiry = approve_as(w, submit_as(w, inquiry, w.requester), w.stage1.tier1)
    assert inquiry.revision_state is None
    row = row_for(w.db, inquiry, w.product_a)
    assert Decimal(str(row.qty)) == Decimal("12")
    assert Decimal(str(row.previous_qty)) == Decimal("10")


# =============================================================================
# R6 - the purchasing-trigger docstring names the OR callers
# =============================================================================


def test_R6_the_trigger_docstring_names_every_allowed_caller():
    from app.services.project_order_inquiry_service import mark_purchasing_email_trigger

    from .test_lessons_learnt_regressions import _PURCHASING_TRIGGER_CALLERS

    doc = mark_purchasing_email_trigger.__doc__ or ""
    for _path, function in _PURCHASING_TRIGGER_CALLERS:
        assert function in doc, f"{function} is not named in the docstring"


# =============================================================================
# R8 - an OR never raised has no inquiry history
# =============================================================================


def test_R8_view_inquiry_on_a_request_never_raised_returns_no_events(plain):
    w = plain
    inquiry = submit_as(w, create_as(w, w.requester), w.requester)
    assert inquiry.state == "pending_approval", "precondition"
    res = w.as_user(w.admin).get(f"{HEADERS}/{inquiry.id}/history", params={"view": "inquiry"})
    assert res.status_code == 200, res.text
    assert res.json()["events"] == []


# =============================================================================
# F2 - a product-only revision moves the product, never the qty
# (mirrors tests/test_oi_product_follow_apply.py's SO product swap)
# =============================================================================


@pytest.fixture
def told(monkeypatch):
    """Every handover item queued: (row_id, kind, was)."""
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    calls: list = []
    real = ProjectOrderInquiryService._record_handover

    def spy(self, row, *, kind, was=None, **kw):
        calls.append((str(row.id), kind, dict(was) if was else None))
        return real(self, row, kind=kind, was=was, **kw)

    monkeypatch.setattr(ProjectOrderInquiryService, "_record_handover", spy)
    return calls


def test_F2_a_product_only_revision_restates_the_product_and_keeps_the_old_as_was(plain, told):
    w = plain
    product_c = make_product(w.db, "bearing kit")
    w.db.commit()
    inquiry = revise_as(w, _raised(w), w.requester)
    row_a = row_for(w.db, inquiry, w.product_a)
    due = row_a.delivery_date
    save_form(
        w, inquiry, w.requester, _edit(form_lines(w, inquiry), row_a, product_id=str(product_c.id))
    )
    inquiry = submit_as(w, inquiry, w.requester)
    told.clear()
    inquiry = approve_as(w, inquiry, w.stage1.tier1)
    row = next(r for r in rows_of(w.db, inquiry) if str(r.id) == str(row_a.id))
    assert row.item_code == product_c.product_code
    assert row.previous_item_code == w.product_a.product_code
    assert Decimal(str(row.qty)) == Decimal("10")
    assert row.delivery_date == due
    assert w.product_a.product_code in (row.note or ""), "the note says what it was"
    assert row.previous_qty is None and row.previous_delivery_date is None, (
        "a product-only change is no qty or date change"
    )
    mine = [t for t in told if t[0] == str(row_a.id)]
    assert len(mine) == 1, told
    was = mine[0][2] or {}
    assert was.get("item_code") == w.product_a.product_code, was
    assert "qty" not in was and "delivery_date" not in was, was


# =============================================================================
# F3 - a revision that leaves the date alone records no date move
# =============================================================================


@pytest.mark.parametrize(
    "line_dates",
    [("2026-12-20", "2027-01-05"), (None, None)],
    ids=["own_line_dates", "header_default_dates"],
)
def test_F3_a_qty_revision_through_the_form_records_no_date_move(plain, told, line_dates):
    w = plain
    lines = [
        dated_line(w.product_a, w.loc_a, qty="10", delivery_date=line_dates[0]),
        dated_line(w.product_b, w.loc_b, qty="4", unit_price="12.50", delivery_date=line_dates[1]),
    ]
    inquiry = approve_as(
        w, submit_as(w, create_as(w, w.requester, lines=lines), w.requester), w.stage1.tier1
    )
    row_a = row_for(w.db, inquiry, w.product_a)
    due = row_a.delivery_date
    assert due is not None, "precondition: the raised row carries its line date"
    inquiry = revise_as(w, inquiry, w.requester)
    save_form(w, inquiry, w.requester, _edit(form_lines(w, inquiry), row_a, qty="12"))
    assert row_for(w.db, inquiry, w.product_a).revised_delivery_date in (None, due)
    inquiry = submit_as(w, inquiry, w.requester)
    told.clear()
    inquiry = approve_as(w, inquiry, w.stage1.tier1)
    row = row_for(w.db, inquiry, w.product_a)
    assert row.delivery_date == due
    assert row.previous_delivery_date is None, row.previous_delivery_date
    mine = [t for t in told if t[0] == str(row_a.id)]
    assert mine and "delivery_date" not in (mine[0][2] or {}), mine


def test_F3_a_qty_revision_through_edit_line_records_no_date_move(plain, told):
    w = plain
    inquiry = revise_as(w, _raised(w), w.requester)
    row_a = row_for(w.db, inquiry, w.product_a)
    due = row_a.delivery_date
    change_qty(w, inquiry, w.product_a, "12", w.requester)
    inquiry = submit_as(w, inquiry, w.requester)
    told.clear()
    inquiry = approve_as(w, inquiry, w.stage1.tier1)
    row = row_for(w.db, inquiry, w.product_a)
    assert row.delivery_date == due
    assert row.previous_delivery_date is None, row.previous_delivery_date
    mine = [t for t in told if t[0] == str(row_a.id)]
    assert mine and "delivery_date" not in (mine[0][2] or {}), mine
