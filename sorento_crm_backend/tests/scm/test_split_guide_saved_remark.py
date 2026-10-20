"""OI-SPLIT-GUIDE (UAC F3, F10 to F12): the BOARD's own line data carries the email's words.

Each board contribution gets `saved_remark`: the purchasing email's own words for the line's SAVED
draft (`saved_line_remark`, one function), the email's cancel word ("CANCEL ALL",
`handover_remark("cancelled", ...)`) for a covered book-cancelled line with no draft, null
otherwise. The shared split read (`LineSplitService.read`) stays exactly as on main: no
`saved_remark`, no book-cancelled line. Every row is seeded here (CI's database has no data).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.services.project_order_inquiry_service import saved_line_remark
from tests.scm.test_line_splits_api import _put, _sp, _url
from tests.scm.test_line_splits_round3 import _excel_rows, api, emails, world  # noqa: F401 - fixtures reused
from tests.test_planning_changes import BASE, _core_line, _core_so, _project_line, _project_so

D = date(2026, 11, 20)


class _S:
    pass


def _seed(api):
    """Six lines on one order, nothing confirmed: 10 own reserve, 20 pool reserve + buy, 30 order
    back, 40 no draft, 50 delivered in full, 60 cancelled in the book."""
    client, world = api
    db = world.db
    core_so = _core_so(db, world.company_id)
    order = _project_so(db, world.project, so_id=core_so.id, autocount_doc_no=core_so.so_number)
    s = _S()
    s.client, s.world, s.db, s.core_so, s.order = client, world, db, core_so, order
    s.core, s.line = {}, {}
    for no in (10, 20, 30, 40, 50, 60):
        core = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10", required_date=D)
        core.line_no = no
        line = _project_line(db, order, line_no=no, product=world.product, core_line=core)
        line.stock_location = world.own_wh.warehouse_code
        s.core[no], s.line[no] = core, line
    db.commit()
    return s


def _confirm_buy(s, no):
    """Line `no` confirmed as Buy 10 under revision 1 (so the book can cancel a COVERED line)."""
    from tests.test_planning_changes import _line_payload

    r = s.client.post(
        f"{BASE}/sales-orders/{s.order.id}/confirm",
        json={"lines": [_line_payload(s.line[no].id, buy_qty="10")]},
    )
    assert r.status_code == 200, f"premise: line {no} confirms: {r.text}"
    s.db.commit()
    s.db.expire_all()


def _book_cancel(s, no):
    """AutoCount cancels covered line `no`: closed in the book with a PENDING change row, which is
    what puts a cancelled line back on the board (`_cancelled_pending_change_rows`)."""
    from app.services.scm.outstanding_diff import CLOSED
    from tests.test_planning_change_apply_on_board import _build, _change

    _confirm_buy(s, no)
    core, line = s.core[no], s.line[no]
    core.line_status = "cancelled"
    line.qty = Decimal("0")
    s.db.commit()
    batch = _build(s.world, [_change(CLOSED, core, so_number=s.core_so.so_number, old_date=D,
                                     new_date=None, old_qty="10", new_qty="0")],
                   s.core_so, [str(core.id)])
    assert batch is not None, "premise: the close is a pending change"
    s.db.expire_all()


def _reserve_only_payload(s, no):
    """A confirm body reserving the whole line from its own location (no Buy, no Borrow)."""
    from tests.test_planning_changes import _line_payload

    return _line_payload(
        s.line[no].id, reserve=[{"warehouse_id": str(s.world.own_wh.id), "qty": "10"}], buy_qty="0"
    )


def _save_draft(s, no, decision):
    board = s.client.get(
        f"{BASE}/fulfilment-planning/board",
        params={"orders": s.core_so.so_number, "granularity": "week"},
    )
    assert board.status_code == 200, board.text
    key = next(
        c["key"] for c in board.json()["contributions"] if c.get("project_line_id") == str(s.line[no].id)
    )
    r = s.client.put(f"{BASE}/fulfilment-planning/lines/{key}/draft", json={"decision": decision})
    assert r.status_code == 200, f"premise: the draft of line {no} saves: {r.text}"


def _own(s, qty):
    w = s.world.own_wh
    return {"warehouse_id": str(w.id), "location": w.warehouse_code, "qty": str(qty)}


def _pool(s, qty):
    w = s.world.pool_wh
    return {"warehouse_id": str(w.id), "location": w.warehouse_code, "qty": str(qty), "rung": "pool"}


def _amend(reserve=(), buy="0", **extra):
    return {"verdict": "amended", "reserve": list(reserve), "borrow": [], "buy_qty": str(buy),
            "reason": "Planner choice.", **extra}


def _board(s):
    r = s.client.get(
        f"{BASE}/fulfilment-planning/board",
        params={"orders": s.core_so.so_number, "granularity": "week"},
    )
    assert r.status_code == 200, r.text
    return {c["project_line_id"]: c for c in r.json()["contributions"] if c.get("project_line_id")}


def _words(s, no):
    got = _board(s).get(str(s.line[no].id))
    assert got is not None, f"premise: line {no} is on the board"
    assert "saved_remark" in got, ("BoardContribution declares saved_remark", sorted(got))
    return got["saved_remark"]


def _email_words(reserve=(), buy=None, order_back=False, own=None):
    """What the email's own function says for the same decision (one function)."""
    components = [
        {"kind": "reserve", "qty": c["qty"], "rung": c.get("rung"), "source_location": c["location"]}
        for c in reserve
    ]
    if buy:
        components.append({"kind": "buy", "qty": str(buy)})
    return saved_line_remark(
        {"components": components, "order_back": order_back, "location": own}
    )[0]


def test_f3_own_location_reserve_reads_use_and_the_location(api):
    s = _seed(api)
    _save_draft(s, 10, _amend([_own(s, 10)]))
    assert _words(s, 10) == f"USE {s.world.own_wh.warehouse_code}"
    assert _words(s, 10) == _email_words([_own(s, 10)])


def test_f3_pool_reserve_and_buy_read_in_the_emails_words(api):
    s = _seed(api)
    _save_draft(s, 20, _amend([_pool(s, 6)], buy=4))
    pool = s.world.pool_wh.warehouse_code
    assert _words(s, 20) == f"USE {pool} 6 & ORDER 4"
    assert _words(s, 20) == _email_words([_pool(s, 6)], buy=4)


def test_f3_order_back_reads_order_back(api):
    s = _seed(api)
    _save_draft(s, 30, _amend(buy=10, order_back=True))
    assert _words(s, 30) == "ORDER BACK" == _email_words(buy=10, order_back=True)


def test_f3_a_line_with_no_saved_draft_has_a_null_saved_remark(api):
    s = _seed(api)
    _save_draft(s, 10, _amend([_own(s, 10)]))
    assert _words(s, 40) is None


def test_f10_a_covered_book_cancelled_line_with_no_draft_reads_the_emails_cancel_word(api):
    """The word the handover email prints for a cancelled line: `handover_remark("cancelled")`."""
    from app.services.project_order_inquiry_service import handover_remark

    s = _seed(api)
    _book_cancel(s, 60)
    assert _board(s)[str(s.line[60].id)].get("cancelled") is True, "premise: the board says cancelled"
    assert handover_remark("cancelled", type("R", (), {"qty": Decimal("10")})(), {"qty": Decimal("10")}) == "CANCEL ALL"
    assert _words(s, 60) == "CANCEL ALL"


def test_f10_the_shared_split_read_stays_as_on_main(api):
    """No `saved_remark` on any line, and a book-cancelled line with a saved draft is NOT listed
    (the #1794 edit sheet and the SO/OI popups must never see it as editable)."""
    s = _seed(api)
    _save_draft(s, 10, _amend([_own(s, 10)]))
    _save_draft(s, 60, _amend([_own(s, 10)]))
    s.core[60].line_status = "cancelled"
    s.db.commit()
    r = s.client.get(_url(s.order.id))
    assert r.status_code == 200, r.text
    lines = {x["line_no"]: x for x in r.json()["lines"]}
    assert 60 not in lines, "a book-cancelled line stays off the shared read"
    assert 10 in lines
    assert all("saved_remark" not in x for x in lines.values()), sorted(lines[10])


def test_f10_saving_splits_on_a_book_cancelled_line_is_unaffected_by_a_saved_draft(api):
    s = _seed(api)
    _save_draft(s, 60, _amend([_own(s, 10)]))
    s.core[60].line_status = "cancelled"
    s.core[50].line_status = "cancelled"
    s.db.commit()
    plan = lambda n: [{"line_id": str(s.line[n].id), "splits": [
        _sp(6, D, on=str(s.line[n].id)), _sp(4, date(2026, 12, 18), on=None)]}]
    with_draft = _put(s, plan(60)).status_code
    without = _put(s, plan(50)).status_code
    assert with_draft == without, (with_draft, without)


def test_f3_a_line_delivered_in_full_with_a_saved_draft_reads_its_words(api):
    s = _seed(api)
    s.core[50].qty_delivered = Decimal("10")
    s.db.commit()
    _save_draft(s, 50, _amend([_own(s, 10)]))
    assert _words(s, 50) == f"USE {s.world.own_wh.warehouse_code}"


def test_f11_incoming_stock_prints_the_spo_numbers_the_email_prints(api):
    """Arrival on or before the line's required date at the line's own location: the SPO number,
    not "INCOMING"."""
    from app.models.procurement import InboundShipment, SPOAllocation
    import uuid

    s = _seed(api)
    shipment = InboundShipment(
        id=str(uuid.uuid4()), shipment_number=f"ZZT-SHIP-{uuid.uuid4().hex[:8]}",
        shipment_date=date(2026, 9, 1), estimated_arrival_date=date(2026, 10, 1),
    )
    s.db.add(shipment)
    s.db.flush()
    s.db.add(SPOAllocation(
        id=str(uuid.uuid4()), spo_number="ZZT-SPO-F11A", spo_line_number=1,
        inbound_shipment_id=shipment.id, warehouse_id=s.world.own_wh.id,
        product_id=s.world.product.id, allocated_quantity=10, quantity_received=0,
        receipt_status="pending",
    ))
    s.db.commit()
    _save_draft(s, 10, {"verdict": "approved", "timely_spo_qty": "10", "reserve": [], "borrow": [], "buy_qty": "0"})
    assert _words(s, 10) == "ZZT-SPO-F11A"


@pytest.mark.parametrize("kind", ["buy", "order_back"])
def test_f12_the_guides_words_equal_the_emails_words_from_the_confirmed_snapshot(api, kind):
    """Saves a draft, reads the guide's words, confirms for real, then reads the words the email
    gives from the confirmed revision's frozen snapshot: one function, same text."""
    from app.models.project_so import SOSupplyDecision
    from tests.test_planning_changes import _line_payload as payload

    s = _seed(api)
    back = kind == "order_back"
    _save_draft(s, 10, _amend(buy=10, order_back=back))
    guide = _words(s, 10)
    line = payload(s.line[10].id, buy_qty="10")
    if back:
        line["order_back"] = True
    r = s.client.post(f"{BASE}/sales-orders/{s.order.id}/confirm", json={"lines": [line]})
    assert r.status_code == 200, f"premise: the confirm saves: {r.text}"
    s.db.commit()
    s.db.expire_all()
    decision = (
        s.db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == str(s.order.id))
        .order_by(SOSupplyDecision.revision_no.desc())
        .first()
    )
    snap = next(x for x in decision.line_snapshots if x["project_line_id"] == str(s.line[10].id))
    assert guide == saved_line_remark(snap)[0], (guide, saved_line_remark(snap))


def test_f15_a_saved_reject_on_a_confirmed_line_reads_the_emails_withdrawal_word(api):
    """The press retires the withdrawn line's raised row with a handover of kind `cancelled`
    (`project_order_inquiry_service.py` retire path, `_record_handover(row, kind="cancelled")`),
    whose REMARK is `CANCEL ALL` (`handover_remark`, project_order_inquiry_service.py:776-777).
    The guide's word for a saved Reject is that one, never blank."""
    from app.services.project_order_inquiry_service import handover_remark

    s = _seed(api)
    _confirm_buy(s, 10)
    _save_draft(s, 10, {"verdict": "rejected", "reason": "wrong site"})
    word = _words(s, 10)
    assert word, ("a saved Reject on a confirmed line is never blank", word)
    assert word == handover_remark(
        "cancelled", type("R", (), {"qty": Decimal("10")})(), {"qty": Decimal("10")}
    ) == "CANCEL ALL"


def test_f17_a_saved_reject_on_a_reserve_only_confirmed_line_has_no_words(api):
    """The email prints nothing for a withdrawn line that raised no order inquiry rows (no Buy,
    no Borrow): a reserve-only line has no raised rows, so a saved Reject on it reads null.
    The F15 case (a line WITH raised rows) keeps "CANCEL ALL"."""
    from app.models.project_so import OrderInquiryRow

    s = _seed(api)
    r = s.client.post(
        f"{BASE}/sales-orders/{s.order.id}/confirm",
        json={"lines": [_reserve_only_payload(s, 10)]},
    )
    assert r.status_code == 200, f"premise: the reserve-only confirm saves: {r.text}"
    s.db.commit()
    s.db.expire_all()
    assert s.db.query(OrderInquiryRow).filter(OrderInquiryRow.so_line_id == s.line[10].id).count() == 0, (
        "premise: a reserve-only line raises no order inquiry row"
    )
    _save_draft(s, 10, {"verdict": "rejected", "reason": "wrong site"})
    assert _words(s, 10) is None


def _placed_row(s, no, *, with_link, auto=True):
    """Line `no` confirmed as Buy 10, its raised row then PLACED. With `with_link` it is placed
    through the real placement path (one link on a real PO line), the link marked `auto` (the
    cascade's own guess) or manual."""
    from app.models.project_so import INQUIRY_PLACED, OrderInquiryLink, OrderInquiryRow
    from tests.test_planning_changes import _place_row_on_a_real_po

    _confirm_buy(s, no)
    row = s.db.query(OrderInquiryRow).filter(OrderInquiryRow.so_line_id == s.line[no].id).one()
    if with_link:
        _place_row_on_a_real_po(s.db, s.world, row, qty_ordered=10)
        for link in s.db.query(OrderInquiryLink).filter(OrderInquiryLink.row_id == row.id):
            link.auto = auto
    else:
        row.state = INQUIRY_PLACED
    s.db.commit()
    s.db.expire_all()
    return row


def test_f20_a_saved_reject_on_a_placed_row_with_cascade_only_links_reads_cancel_all(api):
    """The email's cancel rule (`project_order_inquiry_service.py` retire loop ~5885-5900): a
    withdrawn line's row that is not RAISED is still retired and cancelled when its links are
    cascade-only, `_cascade_only(links) = bool(links) and all(link.auto ...)`
    (project_order_inquiry_service.py:9861). Placed with one auto link reads `CANCEL ALL`."""
    s = _seed(api)
    _placed_row(s, 10, with_link=True, auto=True)
    _save_draft(s, 10, {"verdict": "rejected", "reason": "wrong site"})
    assert _words(s, 10) == "CANCEL ALL"


def test_f20_a_saved_reject_on_a_placed_row_with_a_manual_link_has_no_words(api):
    """A person's link is purchasing's word: `_cascade_only` is False, the row stays, nothing is
    printed."""
    s = _seed(api)
    _placed_row(s, 10, with_link=True, auto=False)
    _save_draft(s, 10, {"verdict": "rejected", "reason": "wrong site"})
    assert _words(s, 10) is None


def test_f20_a_saved_reject_on_a_placed_linkless_row_has_no_words(api):
    """A LINKLESS placed row is NOT cascade-only (`bool(links)` is False, line 9861, PR #471 S1):
    the press leaves it placed and the email prints nothing for it."""
    s = _seed(api)
    _placed_row(s, 10, with_link=False)
    _save_draft(s, 10, {"verdict": "rejected", "reason": "wrong site"})
    assert _words(s, 10) is None


# ---------------------------------------------------------------------------
# F25 to F27 (round 9): an editable remark on an unsplit saved line, stored and emailed
# ---------------------------------------------------------------------------

REMARK = "ORDER BACK URGENT"


def _confirm_with(s, no, *, remark=None, buy="10"):
    """The real Confirm of line `no` as Buy, optionally carrying the planner's own remark
    (`ConfirmLine.remark`)."""
    from tests.test_planning_changes import _line_payload

    line = _line_payload(s.line[no].id, buy_qty=buy)
    if remark is not None:
        line["remark"] = remark
    r = s.client.post(f"{BASE}/sales-orders/{s.order.id}/confirm", json={"lines": [line]})
    assert r.status_code == 200, r.text
    s.db.commit()
    s.db.expire_all()
    return r


def _sent(emails, start=0):
    return [ln for h in emails[start:] for ln in h.get("lines") or []]


def _snapshot_of(s, no):
    from app.models.project_so import SOSupplyDecision

    decision = (
        s.db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == str(s.order.id))
        .order_by(SOSupplyDecision.revision_no.desc())
        .first()
    )
    return next(x for x in decision.line_snapshots if x["project_line_id"] == str(s.line[no].id))


def test_f26_the_confirmed_revision_snapshot_keeps_the_remark(api, emails):
    s = _seed(api)
    _confirm_with(s, 10, remark=REMARK)
    assert _snapshot_of(s, 10).get("remark") == REMARK


def test_f27_the_email_prints_the_edited_remark_instead_of_the_default_words(api, emails):
    s = _seed(api)
    start = len(emails)
    _confirm_with(s, 10, remark=REMARK)
    assert [ln["remark"] for ln in _sent(emails, start)] == [REMARK], _sent(emails, start)


def test_f27_the_excel_remark_of_the_unsplit_row_reads_the_same_text(api, emails):
    s = _seed(api)
    _confirm_with(s, 10, remark=REMARK)
    remarks = [row[4] for row in _excel_rows(s)]
    assert REMARK in remarks, remarks


def test_f27_a_remark_only_change_on_a_confirmed_line_is_told_again(api, emails):
    s = _seed(api)
    _confirm_with(s, 10)
    start = len(emails)
    _confirm_with(s, 10, remark=REMARK)
    assert [ln["remark"] for ln in _sent(emails, start)] == [REMARK], _sent(emails, start)


def test_f27_pin_no_remark_prints_todays_words_and_an_unchanged_reconfirm_tells_nothing(api, emails):
    s = _seed(api)
    start = len(emails)
    _confirm_with(s, 10)
    assert [ln["remark"] for ln in _sent(emails, start)] == ["ORDER"], _sent(emails, start)
    start = len(emails)
    _confirm_with(s, 10)
    assert _sent(emails, start) == []


def test_f26_pin_a_remark_in_the_saved_draft_never_turns_the_line_into_a_split_edit(api):
    """Typing a remark on an unsplit row is stored in the draft decision, not as a one-row split:
    the board's `split_edited` flag stays false."""
    s = _seed(api)
    _save_draft(s, 10, {**_amend([_own(s, 10)]), "remark": REMARK})
    got = _board(s)[str(s.line[10].id)]
    assert got.get("split_edited") is False, got.get("split_edited")


def test_f27_a_remark_only_edit_of_an_applied_split_plan_is_told_again(api, emails):
    """`split_plan_key` includes the remark, so after the plan was applied a remark-only split
    edit counts as a split edit AND the next Confirm tells purchasing."""
    from tests.scm.test_line_splits_round3 import D_167, D_480_NEW, D_608, _new_line_plan_applied
    from tests.scm.test_split_view_board import _edit_480

    from tests.scm.test_split_view_board import _board_flag

    s, _po_line = _new_line_plan_applied(api, emails)
    start = len(emails)
    _edit_480(s, [(14, D_480_NEW, "own", ""), (236, D_608, "new", "SITE HOLD"), (167, D_167, "new", "")])
    assert _board_flag(s, 480) is True, "a remark-only edit counts as a split edit (owner hand test 4)"
    r = s.client.post(
        f"{BASE}/fulfilment-planning/confirm-all",
        json={"orders": [{"pso_id": str(s.order.id), "lines": []}]},
    )
    assert r.status_code == 200, r.text
    s.db.commit()
    assert "SITE HOLD" in [ln["remark"] for ln in _sent(emails, start)], _sent(emails, start)


# ---------------------------------------------------------------------------
# F30: a plan stamped in the OLD remark-free spelling (before b140e1d1d6) stays compatible
# ---------------------------------------------------------------------------


def _legacy_stamp(s):
    """Rewrite every stamped `split_plan` of the order's revisions into the spelling
    `split_plan_key` produced before remarks counted: base, then "qty@date@sits on@cancel"
    per split, sorted, no remark part."""
    from app.models.project_so import SOSupplyDecision

    for decision in s.db.query(SOSupplyDecision).filter(
        SOSupplyDecision.project_sales_order_id == str(s.order.id)
    ):
        out = []
        for snap in decision.line_snapshots or []:
            snap = dict(snap)
            plan = snap.get("split_plan")
            if plan:
                snap["split_plan"] = [plan[0]] + sorted("@".join(e.split("@")[:4]) for e in plan[1:])
            out.append(snap)
        decision.line_snapshots = out
    s.db.commit()
    s.db.expire_all()


def _applied_with_remark(api, emails, remark="LEGACY WORDS"):
    from tests.scm import test_line_splits_round3 as r3

    s = r3._seed(api)
    r3._save(s, r3._owner_plan(remark_14=remark))
    r3._confirm_batch(s, emails)
    return s


def _confirm_order(s):
    r = s.client.post(
        f"{BASE}/fulfilment-planning/confirm-all",
        json={"orders": [{"pso_id": str(s.order.id), "lines": []}]},
    )
    assert r.status_code == 200, r.text
    s.db.commit()
    s.db.expire_all()


def test_f30_a_legacy_stamped_plan_that_already_carries_a_remark_is_not_a_split_edit(api, emails):
    from tests.scm.test_split_view_board import _board_flag
    from tests.scm.test_split_view_read import _one, _views

    s = _applied_with_remark(api, emails)
    _legacy_stamp(s)
    assert _board_flag(s, 480) is False, "a remark the stamp never spelled is not a change"
    assert _one(_views(s, 480))["status"] == "confirmed"
    start = len(emails)
    _confirm_order(s)
    assert _sent(emails, start) == [], _sent(emails, start)


def test_f30_editing_the_remark_after_a_legacy_stamp_counts_once_and_is_told_once(api, emails):
    from tests.scm.test_line_splits_round3 import _applied_480, _put
    from tests.scm.test_split_view_board import _board_flag

    s = _applied_with_remark(api, emails)
    _legacy_stamp(s)
    r = _put(s, [_applied_480(s, remark_14="NEW WORDS")])
    assert r.status_code == 200, r.text
    assert _board_flag(s, 480) is True
    start = len(emails)
    _confirm_order(s)
    assert "NEW WORDS" in [ln["remark"] for ln in _sent(emails, start)], _sent(emails, start)
    assert _board_flag(s, 480) is False
    start = len(emails)
    _confirm_order(s)
    assert _sent(emails, start) == [], "told once, not again"


def test_f30_pin_a_new_stamped_plan_with_a_remark_is_not_a_split_edit_until_edited(api, emails):
    from tests.scm.test_split_view_board import _board_flag

    s = _applied_with_remark(api, emails)
    assert _board_flag(s, 480) is False


# ---------------------------------------------------------------------------
# F32: a confirmed remark round-trips; re-approving a confirmed line unchanged tells nothing
# ---------------------------------------------------------------------------


def _confirmed_with_remark(api, emails):
    s = _seed(api)
    _save_draft(s, 10, {**_amend(buy=10), "remark": REMARK})
    start = len(emails)
    _confirm_with(s, 10, remark=REMARK)
    assert [ln["remark"] for ln in _sent(emails, start)] == [REMARK], "premise: purchasing was told the remark"
    return s


def test_f32_the_board_carries_the_confirmed_remark_of_a_confirmed_line(api, emails):
    """The draft is gone after Confirm; the remark lives in the confirmed revision. The board's
    contribution for the line carries it as `confirmed_remark` (field name for the coder)."""
    s = _confirmed_with_remark(api, emails)
    got = _board(s)[str(s.line[10].id)]
    assert got.get("confirmed_remark") == REMARK, sorted(got)


def test_f32_re_approving_the_confirmed_line_with_its_remark_carried_tells_nothing(api, emails):
    s = _confirmed_with_remark(api, emails)
    carried = _board(s)[str(s.line[10].id)].get("confirmed_remark")
    assert carried == REMARK, ("the board hands the remark back so a re-approve can carry it", carried)
    start = len(emails)
    _confirm_with(s, 10, remark=carried)
    assert _sent(emails, start) == [], _sent(emails, start)


def test_f32_pin_re_approving_after_clearing_the_remark_is_a_change_told_once_with_todays_words(api, emails):
    s = _confirmed_with_remark(api, emails)
    start = len(emails)
    _confirm_with(s, 10, remark="")
    assert [ln["remark"] for ln in _sent(emails, start)] == ["ORDER"], _sent(emails, start)
    start = len(emails)
    _confirm_with(s, 10, remark="")
    assert _sent(emails, start) == [], "told once, not again"
