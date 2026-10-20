"""OI-SPLIT-SUPERSEDE-FIX: a saved split edit Confirmed on a line whose split rows are ALL
raised and UNLINKED moves the one row it changed (one DELAY), never CANCEL x3 + an unsplit ORDER.

Plan: `documentation/plans/scm/PLAN-oi-split-supersede-fix-20oct.md`. The case seen on the dev
DB (SO417636 480, masked): after the New-line plan applied, 480 holds three raised rows 14 / 236 /
167 with no `order_inquiry_links` at all; staff move the 167's date and Save; the next Confirm
cancelled all three and raised ORDER 417 @ 20/09/2026, and still stamped the plan as applied.

`test_line_splits_round3.py`'s P1 cases seed rows LINKED to a PO for their 417, so the netting
counted them as placed and never superseded anything. The `api` fixture's session is built with
`autoflush=False`, the way `app.database.SessionLocal` is, so a row the netting only `db.add`ed is
invisible to the next query, exactly as in production.
"""
from __future__ import annotations

from tests.scm.test_line_splits_outputs import emails  # noqa: F401 - the SENT handover
from tests.scm.test_line_splits_round3 import (
    D_167,
    D_167_EDIT,
    D_480_NEW,
    D_608,
    _confirm_batch,
    _d,
    _edit_480,
    _excel_rows,
    _live,
    _new_line_plan,
    _reconfirm,
    _save,
    _seed,
    _sent_since,
    _worklist,
)
from tests.test_oi_handover_excel import stored  # noqa: F401 - autouse storage stub
from tests.test_planning_change_apply_on_board import api, world  # noqa: F401


def _rows_of_480(s):
    from app.models.project_so import OrderInquiryRow

    return s.db.query(OrderInquiryRow).filter(OrderInquiryRow.so_line_id == s.line[480].id).all()


def _unlinked_new_line_plan_applied(api, emails):
    """Owner seed with NO PO behind 480, the New-line plan confirmed: 480 holds three raised
    rows 14 / 236 / 167, none of them linked."""
    from app.models.project_so import INQUIRY_CANCELLED, INQUIRY_RAISED
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService

    s = _seed(api)
    _save(s, _new_line_plan())
    _confirm_batch(s, emails)
    assert _live(_worklist(s, s.line[480])) == sorted(
        [(_d("14"), D_480_NEW), (_d("236"), D_608), (_d("167"), D_167)]
    ), ("premise: the New-line plan applied", _worklist(s, s.line[480]))
    svc = ProjectOrderInquiryService(s.db)
    live = [row for row in _rows_of_480(s) if row.state != INQUIRY_CANCELLED]
    assert len(live) == 3 and all(row.state == INQUIRY_RAISED for row in live), (
        "premise: all three split rows are still raised", _worklist(s, s.line[480]))
    assert not [link for row in live for link in svc._links_of(row.id)], (
        "premise: no split row carries a link")
    return s


def test_editing_one_date_of_an_all_raised_unlinked_split_sends_one_delay(api, emails):
    """The 167's date is edited to 20/12/2029 and saved. The next Confirm moves that one row
    (one DELAY), cancels nothing, raises no fresh ORDER, the 14 and 236 rows stand, and the
    edited plan is the one recorded as applied (the board's Confirm flag clears)."""
    from app.models.project_so import INQUIRY_CANCELLED
    from app.services.project_line_split_service import LineSplitService, split_plan_edited

    s = _unlinked_new_line_plan_applied(api, emails)
    before = {str(row.id): (row.state, row.qty, row.delivery_date) for row in _rows_of_480(s)}
    live_ids = {row_id for row_id, (state, _q, _w) in before.items() if state != INQUIRY_CANCELLED}
    _edit_480(s, [(14, D_480_NEW, "own", ""), (236, D_608, "new", ""), (167, D_167_EDIT, "new", "")])
    start = len(emails)
    _reconfirm(s)

    after = {str(row.id): row for row in _rows_of_480(s)}
    assert set(after) == set(before), (
        "no fresh row is raised for 480", _worklist(s, s.line[480]))
    assert {row_id for row_id, row in after.items() if row.state != INQUIRY_CANCELLED} == live_ids, (
        "none of the three split rows is cancelled", _worklist(s, s.line[480]))
    assert _live(_worklist(s, s.line[480])) == sorted(
        [(_d("14"), D_480_NEW), (_d("236"), D_608), (_d("167"), D_167_EDIT)]
    ), ("only the 167 row moves, to 20/12/2029", _worklist(s, s.line[480]))
    from app.models.project_so import SOSupplyDecision

    latest = (
        s.db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == s.order.id)
        .order_by(SOSupplyDecision.revision_no.desc())
        .first()
    )
    assert {str(row.supply_decision_id) for row in after.values() if row.state != INQUIRY_CANCELLED} == {
        str(latest.id)
    }, ("every live 480 row is filed under this Confirm, so a later Reject retires it")
    moved = [row for row in after.values() if row.delivery_date == D_167_EDIT]
    assert len(moved) == 1 and moved[0].previous_delivery_date == D_167, (
        "the moved row keeps its old date as its Was", [(r.qty, r.previous_delivery_date) for r in moved])

    sent = _sent_since(emails, start)
    told = [(l["qty"], l["delivery_date"], str(l["remark"])) for l in sent]
    assert len(sent) == 1 and sent[0]["qty"] == "167" and sent[0]["delivery_date"] == "20/12/2029", (
        "the Confirm emails one line: the 167's new date", told)
    assert str(sent[0]["remark"]).startswith("DELAY"), told
    assert not [l for l in sent if "CANCEL" in str(l["remark"]) or str(l["remark"]).startswith("ORDER")], told
    assert not [r for r in _excel_rows(s) if r[3] == D_167], ("nothing reads 20/11/2029", _excel_rows(s))

    service = LineSplitService(s.db)
    recorded = service.recorded_split_plans([str(s.order.id)])
    splits = service.splits_of_lines({str(s.line[480].id)})[str(s.line[480].id)]
    assert not split_plan_edited(splits, (recorded.get(str(s.line[480].id)) or {}).get("plan")), (
        "the edited plan is recorded as applied", recorded.get(str(s.line[480].id)))


def test_a_re_plan_netted_on_the_last_confirmed_line_still_reaches_its_plan(api, emails):
    """The flush half: a re-plan that changes the total (480: 10 + 4 against its 14 / 236 / 167)
    still nets, cancelling the three rows and raising the 14 fresh. With 480 the LAST line the
    Confirm reads, nothing writes that fresh row before `_keep_split_rows` queries for it on the
    non-autoflushing session, so the plan was never cut: 480 kept one unsplit 14."""
    from tests.scm.test_line_splits_round3 import (
        _assert_dropped_403_is_told,
        _confirm,
        _line_payload,
    )

    s = _unlinked_new_line_plan_applied(api, emails)
    _edit_480(s, [(10, D_480_NEW, "own", ""), (4, D_608, "new", "")])
    start = len(emails)
    r = _confirm(s.client, s.order.id, [
        _line_payload(s.line[608].id, buy_qty="632"),
        _line_payload(s.line[752].id, buy_qty="649"),
        _line_payload(s.line[480].id, buy_qty="14"),
    ])
    assert r.status_code == 200, r.text
    s.db.commit()
    s.db.expire_all()
    _assert_dropped_403_is_told(s, _sent_since(emails, start))


# ---------------------------------------------------------------------------
# Crew, 20 Oct: the REDUCE case staff are about to run. A 104 line split by date into two raised,
# unlinked rows (52 + 52) is cut to 28 + 24 with a "Cancel this qty" split of 52. The two rows are
# cut in place (QTY 52 -> NEW QTY 28 / 24) and the 52 is one CANCEL BALANCE; nothing is cancelled
# and raised again, so purchasing's acknowledgement stays on the rows they read.
# ---------------------------------------------------------------------------

D_A = D_480_NEW
D_B = D_608


def _confirm_104(s):
    from tests.scm.test_line_splits_round3 import _confirm, _line_payload

    r = _confirm(s.client, s.order.id, [_line_payload(s.line[480].id, buy_qty="104")])
    assert r.status_code == 200, r.text
    s.db.commit()
    s.db.expire_all()


def test_a_cancel_split_cuts_the_unlinked_date_split_rows_in_place(api, emails):
    from app.models.project_so import (
        ACK_ACKNOWLEDGED,
        INQUIRY_CANCELLED,
        INQUIRY_RAISED,
        IV_CANCEL_BALANCE,
        IV_ORDER,
    )
    from app.services.project_line_split_service import LineSplitService, split_plan_edited
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService
    from tests.scm.test_line_splits_round3 import _one_line

    s = _one_line(api, 104, D_A)
    _save(s, {480: [(52, D_A, 480, ""), (52, D_B, "new", "")]})
    _confirm_104(s)
    rows = [r for r in _rows_of_480(s) if r.state != INQUIRY_CANCELLED]
    assert sorted((r.verb, r.state, r.qty, r.delivery_date) for r in rows) == [
        (IV_ORDER, INQUIRY_RAISED, _d("52"), D_A), (IV_ORDER, INQUIRY_RAISED, _d("52"), D_B)
    ], ("premise: two raised date-split rows", _worklist(s, s.line[480]))
    svc = ProjectOrderInquiryService(s.db)
    assert not [link for r in rows for link in svc._links_of(r.id)], "premise: unlinked"
    for r in rows:
        r.ack_state, r.acknowledged_by = ACK_ACKNOWLEDGED, s.world.actor
    s.db.commit()
    kept_ids = {str(r.id) for r in rows}
    before_ids = {str(r.id) for r in _rows_of_480(s)}

    _save(s, {480: [(28, D_A, 480, ""), (24, D_B, "new", ""), (52, None, "cancel", "")]})
    start = len(emails)
    _confirm_104(s)

    after = _rows_of_480(s)
    live = [r for r in after if r.state != INQUIRY_CANCELLED]
    assert {str(r.id) for r in live if r.verb == IV_ORDER} == kept_ids, (
        "the two rows are cut in place, none cancelled and raised again", _worklist(s, s.line[480]))
    assert not [r for r in after if r.verb == IV_ORDER and str(r.id) not in before_ids], (
        "no fresh ORDER row", _worklist(s, s.line[480]))
    assert sorted((r.qty, r.delivery_date, r.previous_qty) for r in live if r.verb == IV_ORDER) == [
        (_d("24"), D_B, _d("52")), (_d("28"), D_A, _d("52"))
    ], ("QTY 52 -> NEW QTY 28 / 24", [(r.qty, r.delivery_date, r.previous_qty) for r in live])
    assert {r.ack_state for r in live if r.verb == IV_ORDER} == {"changed"}, (
        "purchasing's acknowledgement turns CHANGED on the cut rows", [r.ack_state for r in live])
    assert sorted((r.qty for r in live if r.verb == IV_CANCEL_BALANCE)) == [_d("52")], (
        "the cut is one CANCEL BALANCE of 52", _worklist(s, s.line[480]))

    sent = _sent_since(emails, start)
    told = [(l["qty"], l.get("new_qty"), l["delivery_date"], str(l["remark"])) for l in sent]
    assert not [l for l in sent if str(l["remark"]).startswith("ORDER")], ("no fresh ORDER told", told)
    assert [l for l in sent if "CANCEL" in str(l["remark"])], ("the CANCEL BALANCE is told", told)

    service = LineSplitService(s.db)
    recorded = service.recorded_split_plans([str(s.order.id)])
    splits = service.splits_of_lines({str(s.line[480].id)})[str(s.line[480].id)]
    assert not split_plan_edited(splits, (recorded.get(str(s.line[480].id)) or {}).get("plan"))


def _live_order_ids(s):
    from app.models.project_so import INQUIRY_CANCELLED, IV_ORDER

    return {str(r.id) for r in _rows_of_480(s) if r.state != INQUIRY_CANCELLED and r.verb == IV_ORDER}


def test_a_date_edit_after_a_told_cancel_split_still_moves_one_row(api, emails):
    """Reviewer round 2: a cancel split an earlier Confirm already told (its CANCEL BALANCE is
    live) is not asked of the rows again. 104 = 52 @ A + 42 @ B + Cancel 10, confirmed; then only
    the 42's date moves: the same rows stand and one DELAY is told."""
    from tests.scm.test_line_splits_round3 import _one_line

    s = _one_line(api, 104, D_A)
    _save(s, {480: [(52, D_A, 480, ""), (42, D_B, "new", ""), (10, None, "cancel", "")]})
    _confirm_104(s)
    kept = _live_order_ids(s)
    assert len(kept) == 2, ("premise: two split rows", _worklist(s, s.line[480]))
    _save(s, {480: [(52, D_A, 480, ""), (42, D_167_EDIT, "new", ""), (10, None, "cancel", "")]})
    start = len(emails)
    _confirm_104(s)
    assert _live_order_ids(s) == kept, ("the rows stand", _worklist(s, s.line[480]))
    assert _live(_worklist(s, s.line[480])) == sorted([(_d("52"), D_A), (_d("42"), D_167_EDIT)])
    told = [str(l["remark"]) for l in _sent_since(emails, start)]
    assert len(told) == 1 and told[0].startswith("DELAY"), told


def test_a_linked_reduce_keeps_the_po_cover_on_the_line(api, emails):
    """Reviewer round 2: the reduce with the 52 @ A row linked to a PO for 52. The cut keeps all
    52 of cover on the line (28 + 24, the join path), never gives 24 back while asking
    purchasing to buy 24 again."""
    from datetime import date as _date
    from decimal import Decimal

    from app.models.project_so import INQUIRY_CANCELLED, IV_ORDER
    from app.services.project_order_inquiry_service import ProjectOrderInquiryService
    from tests.scm.test_line_splits_round3 import _one_line
    from tests.test_planning_change_apply_on_board import _link, _po_line, _supplier

    s = _one_line(api, 104, D_A)
    _save(s, {480: [(52, D_A, 480, ""), (52, D_B, "new", "")]})
    _confirm_104(s)
    row_a = next(r for r in _rows_of_480(s)
                 if r.delivery_date == D_A and r.state != INQUIRY_CANCELLED and r.verb == IV_ORDER)
    _po, po_line = _po_line(s.world, _supplier(s.world), qty=52, expected_date=_date(2026, 10, 10))
    _link(s.world, row_a, po_line, qty=52, document="ZZT-S0480")
    s.db.commit()
    s.db.expire_all()
    _save(s, {480: [(28, D_A, 480, ""), (24, D_B, "new", ""), (52, None, "cancel", "")]})
    _confirm_104(s)
    svc = ProjectOrderInquiryService(s.db)
    linked = {
        (r.qty, r.delivery_date): sum((Decimal(str(l.qty)) for l in svc._links_of(r.id)), Decimal(0))
        for r in _rows_of_480(s) if r.state != INQUIRY_CANCELLED and r.verb == IV_ORDER
    }
    assert linked == {(_d("28"), D_A): _d("28"), (_d("24"), D_B): _d("24")}, (
        "the PO cover stays with the line", linked, _worklist(s, s.line[480]))


def test_a_re_confirm_after_the_reduce_changes_nothing(api, emails):
    s = _one_line_reduced(api)
    before = sorted(map(str, _worklist(s, s.line[480])))
    start = len(emails)
    _confirm_104(s)
    assert sorted(map(str, _worklist(s, s.line[480]))) == before
    assert _sent_since(emails, start) == []


def _one_line_reduced(api):
    from tests.scm.test_line_splits_round3 import _one_line

    s = _one_line(api, 104, D_A)
    _save(s, {480: [(52, D_A, 480, ""), (52, D_B, "new", "")]})
    _confirm_104(s)
    _save(s, {480: [(28, D_A, 480, ""), (24, D_B, "new", ""), (52, None, "cancel", "")]})
    _confirm_104(s)
    return s
