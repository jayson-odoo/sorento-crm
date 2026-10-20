"""OI-SPLIT-SUPERSEDE-FIX: a saved split edit Confirmed on a line whose split rows are ALL
raised and UNLINKED moves the one row it changed (one DELAY), never CANCEL x3 + an unsplit ORDER.

Plan: `documentation/plans/scm/PLAN-oi-split-supersede-fix-20oct.md`. The owner's case
(SO417636 480, masked): after the New-line plan applied, 480 holds three raised rows 14 / 236 /
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
